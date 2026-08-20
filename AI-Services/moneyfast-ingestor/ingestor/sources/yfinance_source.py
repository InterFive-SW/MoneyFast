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
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

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


def fetch_quotes(products: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Latest price per product, in ONE batched request.

    Measured on the ~95-symbol universe: a `period="2d", interval="1d"` batch
    takes 3.3-5.4s, while the same batch with minute bars takes 6.8-11.4s and
    does not fit a ten-second cycle. Two daily bars is exactly what is needed —
    during an open session the last row is today's partially formed bar whose
    close tracks the current price, and the row before it is yesterday's close.

    The per-symbol alternative (`Ticker(s).fast_info` in a loop) would be ~95
    HTTP requests every ten seconds, or 34,000 an hour, which is how you get
    rate limited and then blocked.
    """
    import yfinance as yf

    catalogue = {p["data_symbol"]: p["symbol"] for p in products if p.get("data_symbol")}
    if not catalogue:
        return []

    frame = yf.download(
        " ".join(catalogue),
        period="2d",
        interval="1d",
        progress=False,
        threads=True,
        auto_adjust=True,
        group_by="column",
    )
    if frame is None or frame.empty:
        log.warning("batch quote download returned nothing")
        return []

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

    log.info("batched %d/%d symbols in one request", len(rows), len(catalogue))
    return rows


def fetch_fundamentals(products: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    """Valuation ratios and company facts.

    Per-symbol, because the provider exposes no batch form for this. That is
    why it runs daily rather than every cycle.

    Missing values are passed through as None. Coverage is genuinely partial —
    THYAO has no trailing P/E while AAPL does — and coalescing a gap to zero
    would put a company with no published earnings at the top of a "lowest
    P/E" screen.
    """
    import yfinance as yf

    rows: list[dict[str, Any]] = []
    for product in products:
        data_symbol = product.get("data_symbol")
        if not data_symbol:
            continue
        try:
            info = yf.Ticker(data_symbol).info or {}
        except Exception as exc:
            log.warning("fundamentals failed for %s: %s", data_symbol, exc)
            continue

        rows.append(
            {
                "symbol": product["symbol"],
                "pe_ratio": _clean_number(info.get("trailingPE")),
                "pb_ratio": _clean_number(info.get("priceToBook")),
                "market_cap": _int_or_none(info.get("marketCap")),
                "dividend_yield": _clean_number(info.get("dividendYield")),
                "sector": info.get("sector") or None,
                "industry": info.get("industry") or None,
                "week52_high": _clean_number(info.get("fiftyTwoWeekHigh")),
                "week52_low": _clean_number(info.get("fiftyTwoWeekLow")),
            }
        )
    return rows


def _clean_number(value: Any) -> Optional[float]:
    """A number, or None. Never a coerced zero, never a NaN."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def fetch_candles(products: Iterable[dict[str, str]], days: int = 400) -> list[dict[str, Any]]:
    """Daily OHLCV bars.

    Re-requesting the same window every night is intentional and cheap: the
    backend's unique constraint on (product, interval, timestamp) discards
    what it already holds, so a backfill is idempotent and a gap left by a
    failed run repairs itself on the next one.
    """
    import yfinance as yf

    rows: list[dict[str, Any]] = []
    for product in products:
        data_symbol = product.get("data_symbol")
        if not data_symbol:
            continue
        try:
            frame = yf.Ticker(data_symbol).history(period=f"{days}d", interval="1d")
            if frame is None or frame.empty:
                log.warning("no history for %s", data_symbol)
                continue
            for index, bar in frame.iterrows():
                timestamp = _to_utc(index)
                if timestamp is None:
                    continue
                rows.append(
                    {
                        "symbol": product["symbol"],
                        "interval": "1d",
                        "timestamp": timestamp,
                        "open": float(bar["Open"]),
                        "high": float(bar["High"]),
                        "low": float(bar["Low"]),
                        "close": float(bar["Close"]),
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
    try:
        if value is None or value != value:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
