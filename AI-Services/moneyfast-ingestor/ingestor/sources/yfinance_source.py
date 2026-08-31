"""Price and history from Yahoo Finance via `yfinance`.

Free, no API key, and it knows BIST tickers as `<SYMBOL>.IS`. It is also the
source of the OHLCV history that makes ex-post risk metrics computable at all
— without bars, volatility, drawdown, beta and Sharpe have nothing to be
computed from.

The data is delayed. That is disclosed rather than hidden: every quote carries
the provider's own timestamp, and the backend derives `is_delayed` and
`delay_minutes` from it. Presenting delayed prices as live is the failure this
whole freshness contract exists to prevent.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional

from .. import config

log = logging.getLogger("moneyfast.ingestor.yfinance")


def _to_utc(value: Any) -> Optional[datetime]:
    """pandas Timestamp or datetime -> aware UTC datetime."""
    if value is None:
        return None
    moment = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if not isinstance(moment, datetime):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


#: Seconds any single provider request may take. Without it the underlying
#: curl uses its own generous default, and one unreachable symbol cost ~10s of
#: a 10s cycle -- observed as `quote cycle: 89 fetched ... 61.39s (budget 10s)`
#: with the scheduler skipping every run in between.
REQUEST_TIMEOUT_SECONDS = 8

#: Symbols per request. A single batch of the whole universe means one slow
#: chunk stalls everything; at ~190 symbols that is the difference between a
#: cycle that fits its budget and one that never does. Small enough to fail
#: cheaply, large enough that the request count stays far below the rate limit.
CHUNK_SIZE = 40


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_quotes(products: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Latest price per product, in batched requests.

    Measured on the ~95-symbol universe: a daily-bar batch takes 3.3-5.4s,
    while the same batch with minute bars takes 6.8-11.4s. During an open
    session the last row is today's partially formed bar whose close tracks
    the current price, and the row before it is the previous close.

    The window is FIVE days, not two, because two is not reliably two bars.
    `period` is a calendar span, and how many trading days fall inside it
    varies by venue: measured on a Saturday, US symbols returned two bars
    while every `.IS` symbol returned one. With a single bar there is no
    previous close, so `change_percent` stayed null -- and the watchlist, the
    heatmap and the top-movers list all drop rows whose change is unknown.
    The observable result was 87 of 88 BIST stocks silently vanishing from
    those screens every weekend. Only the last two bars are ever read, so a
    wider window costs nothing but a slightly larger response.

    The per-symbol alternative (`Ticker(s).fast_info` in a loop) would be one
    HTTP request per symbol per cycle, which is how you get rate limited and
    then blocked.

    Chunked rather than one request for the lot: `yf.download` swallows
    per-symbol failures and still returns a frame, so a stalled symbol shows
    up only as elapsed time. Chunking bounds what one stall can cost.
    """
    import yfinance as yf

    catalogue = {p["data_symbol"]: p["symbol"] for p in products if p.get("data_symbol")}
    if not catalogue:
        return []

    closes = None
    volumes = None
    stamp = datetime.now(timezone.utc)
    frames = []
    for chunk in _chunks(list(catalogue), CHUNK_SIZE):
        try:
            part = yf.download(
                " ".join(chunk),
                period="5d",
                interval="1d",
                progress=False,
                threads=True,
                auto_adjust=True,
                group_by="column",
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            # One bad chunk is not a failed cycle. The symbols in it simply go
            # unpriced this round and are reported as missing, which the
            # caller reads as a slow-down signal.
            log.warning("chunk of %d symbols failed: %s", len(chunk), exc)
            continue
        if part is not None and not part.empty:
            frames.append(part)

    if not frames:
        log.warning("batch quote download returned nothing")
        return []

    import pandas as pd

    frame = frames[0] if len(frames) == 1 else pd.concat(frames, axis=1)
    closes = frame["Close"]
    volumes = frame["Volume"] if "Volume" in frame else None
    stamp = _to_utc(closes.index[-1]) or datetime.now(timezone.utc)

    rows: list[dict[str, Any]] = []
    for data_symbol, symbol in catalogue.items():
        try:
            series = closes[data_symbol].dropna() if data_symbol in closes else None
        except (KeyError, TypeError):
            series = None
        if series is None or series.empty:
            # Delisted, suspended, or simply unknown to the provider. Skipped
            # with a warning; one dead ticker must not blank the batch.
            log.debug("no price for %s (%s)", symbol, data_symbol)
            continue

        price = float(series.iloc[-1])
        previous = float(series.iloc[-2]) if len(series) > 1 else None
        change = price - previous if previous else None

        volume = None
        if volumes is not None and data_symbol in volumes:
            tail = volumes[data_symbol].dropna()
            volume = _int_or_none(tail.iloc[-1]) if not tail.empty else None

        rows.append(
            {
                "symbol": symbol,
                "price": price,
                "change_amount": float(change) if change is not None else None,
                "change_percent": (
                    float(change / previous * 100) if change is not None and previous else None
                ),
                "previous_close": previous,
                "volume": volume,
                # The provider's own bar timestamp, not our clock. The backend
                # derives the disclosed delay from it, so using now() here
                # would make delayed data look live.
                "market_timestamp": stamp,
                "source": "yfinance",
            }
        )

    log.info(
        "batched %d/%d symbols in %d request(s)",
        len(rows), len(catalogue), (len(catalogue) + CHUNK_SIZE - 1) // CHUNK_SIZE,
    )
    return rows


def fetch_fundamentals(products: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Valuation ratios and company facts.

    Per-symbol, because the provider exposes no batch form for this. That is
    why it runs daily rather than every cycle.

    **Paralel.** Sağlayıcı toplu bir uç sunmuyor, dolayısıyla sembol başına bir
    istek gerekiyor; sırayla yapıldığında 190 enstrüman için kabul edilebilirdi
    ama evren 1009'a çıkınca saatler sürüyor. Ölçüm: 12 iş parçacığıyla 513
    sembol 48 saniyede geldi. Eşzamanlılık sınırı düşük tutuluyor -- amaç turu
    hızlandırmak, sağlayıcıyı zorlamak değil; 429 gelirse zaten geri çekilme
    merdiveni devreye giriyor.

    Missing values are passed through as None. Coverage is genuinely partial --
    THYAO has no trailing P/E while AAPL does -- and coalescing a gap to zero
    would put a company with no published earnings at the top of a "lowest
    P/E" screen.
    """
    import yfinance as yf

    wanted = [p for p in products if p.get("data_symbol")]
    if not wanted:
        return []

    def one(product: dict[str, str]) -> Optional[dict[str, Any]]:
        data_symbol = product["data_symbol"]
        try:
            info = yf.Ticker(data_symbol).info or {}
        except Exception as exc:
            log.warning("fundamentals failed for %s: %s", data_symbol, exc)
            return None

        return {
            "symbol": product["symbol"],
            # The company's real name. 84 of 97 products are stored with
            # name = ticker, so "Aselsan" could not be resolved at all:
            # 'ASELS' LIKE '%ASELSAN%' is false because the stored name is
            # SHORTER than what the user typed.
            "name": info.get("longName") or info.get("shortName") or None,
            "pe_ratio": _clean_number(info.get("trailingPE")),
            "pb_ratio": _clean_number(info.get("priceToBook")),
            "market_cap": _int_or_none(info.get("marketCap")),
            "dividend_yield": _clean_number(info.get("dividendYield")),
            "sector": info.get("sector") or None,
            "industry": info.get("industry") or None,
            "week52_high": _clean_number(info.get("fiftyTwoWeekHigh")),
            "week52_low": _clean_number(info.get("fiftyTwoWeekLow")),

            # Gelir tablosu ve kârlılık. Aynı `.info` çağrısının atılan
            # kısmı: yeni istek yok, yeni kota maliyeti yok.
            "total_revenue": _int_or_none(info.get("totalRevenue")),
            "revenue_growth": _clean_number(info.get("revenueGrowth")),
            "gross_margin": _margin(info.get("grossMargins")),
            "operating_margin": _margin(info.get("operatingMargins")),
            "ebitda_margin": _margin(info.get("ebitdaMargins")),
            "profit_margin": _margin(info.get("profitMargins")),
            "return_on_equity": _clean_number(info.get("returnOnEquity")),
            "return_on_assets": _clean_number(info.get("returnOnAssets")),
            "debt_to_equity": _clean_number(info.get("debtToEquity")),
            "current_ratio": _clean_number(info.get("currentRatio")),
            "total_debt": _int_or_none(info.get("totalDebt")),
            "total_cash": _int_or_none(info.get("totalCash")),
            "free_cash_flow": _int_or_none(info.get("freeCashflow")),
            "operating_cash_flow": _int_or_none(info.get("operatingCashflow")),
            "enterprise_value": _int_or_none(info.get("enterpriseValue")),
            "beta": _clean_number(info.get("beta")),
            "trailing_eps": _clean_number(info.get("trailingEps")),
            "forward_eps": _clean_number(info.get("forwardEps")),
            "forward_pe": _clean_number(info.get("forwardPE")),
            "earnings_growth": _clean_number(info.get("earningsGrowth")),
            "payout_ratio": _clean_number(info.get("payoutRatio")),
            "dividend_rate": _clean_number(info.get("dividendRate")),

            # Analist görüşü: başkasının değerlendirmesi, aktarılabilir bir
            # olgu. "none" sağlayıcının "görüş yok" yazma biçimi.
            "recommendation_key": _recommendation(info.get("recommendationKey")),
            "analyst_count": _int_or_none(info.get("numberOfAnalystOpinions")),
            "target_mean_price": _clean_number(info.get("targetMeanPrice")),

            "ex_dividend_date": _epoch_to_iso(info.get("exDividendDate")),
            "earnings_date": _epoch_to_iso(info.get("earningsTimestamp")),
        }

    with ThreadPoolExecutor(max_workers=config.fundamentals_workers()) as pool:
        return [row for row in pool.map(one, wanted) if row is not None]


def _margin(value: Any) -> Optional[float]:
    """Bir marj, ya da None. TAM SIFIR yoktur.

    Ölçüldü: AKBNK `grossMargins: 0.0` ve `ebitdaMargins: 0.0` dönüyor --
    None değil, sıfır. Banka muhasebesinde brüt marj diye bir kalem yok ve
    sağlayıcı "yok"u sıfır olarak veriyor. Olduğu gibi saklanırsa ekranda
    "%0,0 brüt marj" yazar: olmayan bir ölçüm, olgu diye sunulmuş olur.

    Gerçek bir şirketin marjı tam 0,0000 çıkmaz; kayıp bilgi, yanlış
    bilgiden iyidir. `instrument_fundamentals`'ın kendi kuralı bu:
    "defaulting a missing ratio to zero would make a stock with no earnings
    data look like the cheapest name on the screen."
    """
    number = _clean_number(value)
    return None if number == 0.0 else number


def _recommendation(value: Any) -> Optional[str]:
    """Analist konsensüsü. Sağlayıcı "görüş yok"u `"none"` diye yazıyor ve o
    bir tavsiye değil; metin olarak saklanırsa ekranda tavsiye sütununda
    "none" görünür."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text or None if text not in ("none", "n/a") else None


def _epoch_to_iso(value: Any) -> Optional[str]:
    """Unix saniyesi -> ISO. Sağlayıcı tarihleri epoch olarak veriyor."""
    number = _clean_number(value)
    if number is None or number <= 0:
        return None
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _clean_number(value: Any) -> Optional[float]:
    """A number, or None. Never a coerced zero, never a NaN, never infinite.

    Sonsuz da eleniyor, yalnızca NaN değil: ikisi de JSON'a girmiyor
    (`Out of range float values are not JSON compliant`) ve tek bir tanesi
    bütün partiyi düşürüyor. 828 enstrümanlık temel veri turu tam bu yüzden
    hiçbir şey yazmadan dönmüştü -- sıfır bölmesinden gelen bir oran yetiyor.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None



def _finite_ohlc(bar: Any) -> Optional[tuple[float, float, float, float]]:
    """Barın OHLC değerleri, hepsi sonlu sayıysa.

    Sağlayıcı gün içi serilerde işlem olmayan aralıklar için NaN döndürüyor.
    Bunları taşımak JSON'u geçersiz kılıyor (`Out of range float values are not
    JSON compliant`) ve tek bir NaN bütün partiyi düşürüyor.
    """
    try:
        values = (
            float(bar["Open"]), float(bar["High"]),
            float(bar["Low"]), float(bar["Close"]),
        )
    except (TypeError, ValueError, KeyError):
        return None
    return values if all(math.isfinite(value) for value in values) else None


def fetch_candles(
    products: Iterable[dict[str, str]],
    days: int = 400,
    interval: str = "1d",
) -> list[dict[str, Any]]:
    """OHLCV bars.

    Re-requesting the same window every night is intentional and cheap: the
    backend's unique constraint on (product, interval, timestamp) discards
    what it already holds, so a backfill is idempotent and a gap left by a
    failed run repairs itself on the next one.

    `interval` gün içi barlar için de kullanılıyor (`15m`). Bunlar sağlayıcıdan
    GERÇEK OHLC olarak geliyor; anlık fiyattan bar üretmek, açılış-yüksek-düşük
    değerlerini uydurmak olurdu ve mum grafiği o uydurma fitilleri gerçekmiş
    gibi çizerdi. Sağlayıcı gün içi barları yalnızca son ~60 gün için veriyor,
    dolayısıyla bu seri geçmişe doğru derin değil -- gün görünümü için yeterli.
    """
    import yfinance as yf

    rows: list[dict[str, Any]] = []
    for product in products:
        data_symbol = product.get("data_symbol")
        if not data_symbol:
            continue
        try:
            frame = yf.Ticker(data_symbol).history(period=f"{days}d", interval=interval)
            if frame is None or frame.empty:
                log.warning("no history for %s", data_symbol)
                continue
            for index, bar in frame.iterrows():
                timestamp = _to_utc(index)
                if timestamp is None:
                    continue
                prices = _finite_ohlc(bar)
                if prices is None:
                    # Sağlayıcı, işlem olmayan gün içi aralıklar için NaN'lı
                    # satırlar döndürüyor. NaN bir bar değil, boşluktur --
                    # ve JSON'a girmez: bir tanesi otuz günlük 94.055 barlık
                    # partinin tamamını düşürüyordu.
                    continue
                rows.append(
                    {
                        "symbol": product["symbol"],
                        "interval": interval,
                        "timestamp": timestamp,
                        "open": prices[0],
                        "high": prices[1],
                        "low": prices[2],
                        "close": prices[3],
                        "volume": _int_or_none(bar.get("Volume")),
                        "source": "yfinance",
                    }
                )
        except Exception as exc:
            log.warning("history fetch failed for %s: %s", data_symbol, exc)
    return rows


def _first_number(info: Any, *names: str) -> Optional[float]:
    """fast_info exposes both snake_case and camelCase across versions."""
    for name in names:
        try:
            value = info[name] if hasattr(info, "__getitem__") else getattr(info, name, None)
        except (KeyError, TypeError, AttributeError):
            value = getattr(info, name, None)
        if isinstance(value, (int, float)) and value == value:  # NaN check
            return float(value)
    return None


def _int_or_none(value: Any) -> Optional[int]:
    """Bir tamsayı, ya da None. Sonsuz ve NaN elenir -- ikisi de JSON'a
    girmiyor ve `int(float("inf"))` zaten OverflowError veriyor."""
    try:
        if value is None or not math.isfinite(float(value)):
            return None
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None
