"""Portföy Analizi — composition, not re-implementation.

Asset allocation, sector breakdown and the full risk metric suite already
exist under `investment` and `risk`. This module assembles one report from the
same sources rather than growing a second copy of the arithmetic, so the
analysis screen and the dashboard can never disagree about what the portfolio
is worth.

What is genuinely new here is the portfolio TREND: a value series reconstructed
from daily candles at today's holdings. That is a backtest of the current
basket, not a record of what the account was worth historically — the system
has no position history to draw a true one from. The distinction is surfaced in
`warnings` rather than left for the reader to assume.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.modules.investment.ai_service import _convert
from app.modules.risk import returns as risk_returns

log = logging.getLogger("moneyfast.analytics")

#: Trading days below which a volatility or drawdown figure is not reported as
#: a measurement. Matches the risk module's stance: a number from a handful of
#: bars is arithmetic, not evidence.
MIN_RELIABLE_OBSERVATIONS = 60

#: Bars pulled per symbol for the trend. About TWO years of trading days --
#: the performance chart offers a two-year range and a 260-bar window could
#: only ever draw one.
TREND_WINDOW = 520

#: Gün içi görünüm: 15 dakikalık barlar. Bir işlem günü ~26 bar (BIST) ile
#: ~27 bar (ABD) arasında; 200 tavanı birkaç günü rahatça kapsıyor ve seri
#: yine de tek bir güne kırpılıyor.
INTRADAY_WINDOW = 200


#: The index the trend chart is drawn against. Same default the risk module
#: measures beta and correlation with, so the picture and the numbers beside
#: it describe the same comparison.
BENCHMARK_SYMBOL = "XU100"


def _benchmark_series(
    dates: list[Any], closes_for: Callable[[str], list[tuple[datetime, float]]]
) -> Optional[dict[str, Any]]:
    """The index's closes on `dates`, or None when there is no real overlap.

    Raw closes, not rescaled: the chart decides how to put two series with
    different units on one axis, and handing it an already-normalised number
    would leave the page unable to say what the index itself did.
    """
    by_day = {
        stamp.date(): float(close) for stamp, close in closes_for(BENCHMARK_SYMBOL)
    }
    points = [
        {
            "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            "value": round(by_day[day], 4),
        }
        for day in dates
        if day in by_day
    ]
    if len(points) < 2:
        return None
    return {"symbol": BENCHMARK_SYMBOL, "points": points}


def window_limit(lookback: str = "1Y") -> int:
    """Bars to read per symbol for `lookback`, including the one the first
    return needs.

    The same arithmetic `risk.service.history_limit` does, off the same table,
    so one period selector can drive both endpoints and mean the same thing.
    It replaced a fixed 260 -- "about a year" -- while risk asked for 253, and
    the two then measured the same portfolio over different spans. With one
    series behind both, a window that is merely close was the last thing that
    could still make them disagree, and on a single screen showing both that
    difference has nowhere to hide.
    """
    return risk_returns.window_for(lookback) + 1


def _percent(part: float, whole: float) -> float:
    return round((part / whole) * 100, 2) if whole else 0.0


def _normalise(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Force the percentages to sum to exactly 100.

    BR-02 states the allocation must always total 100%. Rounding each slice
    independently does not guarantee that — twelve positions rounded to two
    decimals landed on 100.02% — and a pie chart whose slices visibly do not
    add up undermines every other number on the screen.

    The residual goes on the LARGEST slice, where it is proportionally
    smallest and cannot flip a small holding's displayed share.
    """
    if not slices:
        return slices
    total = round(sum(entry["percentage"] for entry in slices), 2)
    residual = round(100.0 - total, 2)
    if residual:
        largest = max(slices, key=lambda entry: entry["percentage"])
        largest["percentage"] = round(largest["percentage"] + residual, 2)
    return slices


def build(
    db: Session,
    user_id: Optional[str],
    holdings: list[dict[str, Any]],
    cash: float,
    sector_map: dict[str, str],
    closes_for: Callable[[str], list[tuple[datetime, float]]],
    proposals: list[Any],
    as_of: Optional[datetime] = None,
    delay_minutes: int = 0,
    rates: Optional[dict[str, float]] = None,
    base_currency: str = "TRY",
    intraday: bool = False,
    fx_closes_for: Optional[Callable[[str], list[tuple[datetime, float]]]] = None,
) -> dict[str, Any]:
    """Assemble the report. Pure: every input is supplied by the router."""
    warnings: list[str] = []

    priced = [row for row in holdings if row.get("price") is not None]
    if len(priced) != len(holdings):
        missing = sorted(
            row["symbol"] for row in holdings if row.get("price") is None
        )
        warnings.append(
            "Fiyatı bulunamayan pozisyonlar değerlemeye dahil edilmedi: "
            + ", ".join(missing)
        )

    # Values in the ACCOUNT's currency, converted per holding.
    #
    # These sums used to add USD straight to TRY, so a portfolio holding AAPL,
    # MSFT and NVDA counted them at roughly 1/48th of their worth: this page
    # reported ₺404.467 while /portfolio/summary reported ₺1.087.834 for the
    # same holdings. A holding whose rate is missing is excluded and named
    # rather than converted at an invented rate.
    rates = rates or {"TRY": 1.0}
    valued, unconvertible = [], []
    for row in priced:
        try:
            market_value = _convert(
                row["quantity"] * row["price"], row.get("currency") or base_currency,
                base_currency, rates,
            )
            cost_basis = _convert(
                row["quantity"] * row["avg_cost"], row.get("currency") or base_currency,
                base_currency, rates,
            )
        except KeyError:
            unconvertible.append(row["symbol"])
            continue
        valued.append((row, market_value, cost_basis))

    if unconvertible:
        warnings.append(
            "Kuru alınamadığı için değerlemeye dahil edilmeyen pozisyonlar: "
            + ", ".join(sorted(unconvertible))
        )

    invested = sum(market_value for _, market_value, _ in valued)
    cost = sum(cost_basis for _, _, cost_basis in valued)
    total = invested + cash

    allocation = [
        {"label": "Nakit (TRY)", "value": round(cash, 2), "percentage": _percent(cash, total)}
    ]
    for row, value, _ in sorted(valued, key=lambda entry: entry[1], reverse=True):
        allocation.append(
            {
                "label": row["symbol"],
                "value": round(value, 2),
                "percentage": _percent(value, total),
            }
        )

    sectors: dict[str, float] = {}
    for row, value, _ in valued:
        # "Bilinmiyor" rather than a guess: assigning a sector by inference
        # would make the breakdown look more certain than it is.
        label = sector_map.get(row["symbol"]) or "Bilinmiyor"
        sectors[label] = sectors.get(label, 0.0) + value

    # İKİ seri, çünkü iki ayrı soru var ve tek bir cevap ikisini birden
    # doğru yanıtlayamıyor.
    #
    # ÖLÇÜM (`value_series`, main'den): oynaklık, düşüş ve beta için. Sabit
    # ağırlıklarla ve YALNIZCA her enstrümanın işlem gördüğü ortak günlerde
    # hesaplanıyor. Tarih hizası burada şart -- hizasız karşılaştırma, %94'ü
    # DOAS olan bir portföyün XU100 betasını 0,0062 gösteriyordu.
    #
    # GEÇMİŞ (`_trend`, bu daldan): grafikte çizilen değer. Miktar zamanın
    # fonksiyonu, kur o günün kuru, ve bir enstrümanın işlem görmediği gün
    # düşürülmüyor -- portföyün o gün de bir değeri vardı.
    #
    # Aynı seriyi ikisine birden vermek, birini bozmak olurdu: ölçüm serisiyle
    # çizilen grafik dün alınan hisseyi geçen yıla da koyar, geçmiş serisiyle
    # ölçülen beta ise taşınmış fiyatlar üzerinden çıkar.
    rate_at = _rate_lookup(
        [row for row, _, _ in valued], base_currency, fx_closes_for, rates
    )
    trend, chart_excluded = _trend(
        [row for row, _, _ in valued], closes_for, intraday, proposals, rate_at
    )

    # The same series `risk` measures. Built once, in `risk/returns.py`:
    # this page and the risk page were computing volatility and max drawdown
    # from two differently-built series and reporting different numbers for
    # one portfolio. It also fixes a currency bug this module had on its own --
    # `_trend` summed `quantity x close` with no conversion, adding dollars to
    # lira, while the allocation block three lines above converted properly.
    dates, trend_values, excluded = risk_returns.value_series(
        [
            {**row, "market_value": market_value}
            for row, market_value, _ in valued
        ],
        closes_for,
        base_currency,
    )
    trend = [
        {
            "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            "value": round(value, 2),
        }
        for day, value in zip(dates, trend_values)
    ]
    excluded = sorted(set(excluded) | set(chart_excluded))
    if excluded:
        # Names them AND says what their absence costs. The series ends at the
        # value of what it could measure, so with something left out the last
        # point sits below the total shown above it -- a gap the reader would
        # otherwise have to notice and explain to themselves.
        warnings.append(
            "Fiyat geçmişi yetersiz olduğu için trend hesabının dışında kalan "
            "enstrümanlar: " + ", ".join(excluded)
            + ". Grafikteki değer bu pozisyonları içermez, dolayısıyla "
            "yukarıdaki toplamın altında kalır."
        )
    # Eski uyarı ("bugünkü pozisyonların geçmiş fiyatlarla yeniden
    # değerlenmesi") artık DOĞRU DEĞİL: çizilen seri pozisyonların o
    # zamanki miktarını kullanıyor ve pozisyon açılmadan önceki günlere
    # katkı vermiyor. Doğru olmayan bir uyarıyı bırakmak, okuyanı grafiğe
    # olduğundan az güvenmeye iter.
    if trend:
        warnings.append(
            "Oynaklık ve düşüş, sabit ağırlıklı bir seri üzerinden ölçülür; "
            "grafikteki değer ise pozisyonların o günkü miktarını yansıtır."
        )

    # The index on the portfolio's OWN dates. Days the index did not trade are
    # dropped rather than carried forward, so the two lines only ever meet on
    # days both actually have -- a forward-filled index shows the market flat
    # on a day it was simply closed.
    benchmark = _benchmark_series(dates, closes_for)

    values = trend_values
    series = risk_returns.simple_returns(values)
    drawdown = risk_returns.max_drawdown(values, dates) if values else None

    performance = {
        "observations": len(values),
        "start_value": round(values[0], 2) if values else None,
        "end_value": round(values[-1], 2) if values else None,
        "total_return_percent": (
            round(((values[-1] / values[0]) - 1) * 100, 2)
            if len(values) >= 2 and values[0]
            else None
        ),
        "annualised_volatility": risk_returns.annualised_volatility(series),
        "max_drawdown_percent": (
            round(drawdown["value"] * 100, 2)
            if drawdown and drawdown.get("value") is not None
            else None
        ),
        "is_statistically_reliable": len(series) >= MIN_RELIABLE_OBSERVATIONS,
    }

    _normalise(allocation)

    return {
        "base_currency": base_currency,
        "as_of": as_of,
        "is_delayed": True,
        "delay_minutes": delay_minutes,
        "total_value": round(total, 2),
        "cash": round(cash, 2),
        "invested": round(invested, 2),
        "unrealised_pnl": round(invested - cost, 2),
        "unrealised_pnl_percent": (
            round(((invested - cost) / cost) * 100, 2) if cost else None
        ),
        "allocation": allocation,
        "sectors": _normalise([
            {"label": label, "value": round(value, 2), "percentage": _percent(value, invested)}
            for label, value in sorted(sectors.items(), key=lambda kv: kv[1], reverse=True)
        ]),
        "trend": trend,
        "benchmark": benchmark,
        "performance": performance,
        "activity": _activity(proposals),
        "excluded_symbols": excluded,
        "warnings": warnings,
    }



def _rate_lookup(
    priced: list[dict[str, Any]],
    base_currency: str,
    fx_closes_for: Optional[Callable[[str], list[tuple[datetime, float]]]],
    rates: Optional[dict[str, float]],
) -> Callable[[str, Any], Optional[float]]:
    """Bir para biriminin, verilen andaki taban para birimi karşılığı.

    Seri toplanmadan ÖNCE çevriliyor. Çevirmeden toplamak, 20.616 dolarlık ve
    388.550 liralık pozisyonları 409.166 diye toplamak demek -- grafiğin
    1.382.868 TL'lik bir portföyü 411.991'de göstermesinin sebebi buydu. Bu
    projenin bedelini bir kez ödediği hata (bkz. CLAUDE.md, "Para birimi
    kuralı").

    Kur GEÇMİŞTEN okunuyor: USDTRY'nin kendi mumları elimizde, dolayısıyla
    geçen yılın dolar pozisyonu geçen yılın kuruyla değerleniyor. Bugünün
    kuruyla bütün geçmişi çevirmek, portföyün geçmiş değerini bugünün kurunun
    hikâyesiyle karıştırırdı. Geçmiş kur yoksa güncel kura düşülür.

    Kuru hiç bilinmeyen bir pozisyon buraya HİÇ GELMEZ: `build`, değerlemeyi
    yaparken `_convert` üzerinden onu zaten eliyor ve adını uyarıya yazıyor.
    Burada dönen `None` yalnızca "bu noktada kur yok" demek ve o nokta
    toplama katılmaz -- 1.0 varsaymak uydurma bir toplam üretirdi.
    """
    base = (base_currency or "TRY").upper()
    wanted = {
        (row.get("currency") or base).upper()
        for row in priced
    } - {base}

    # Damgalar bir kez UTC'ye çevrilip sıralanıyor, sonra ikili aramayla
    # okunuyor. İlk hali her çağrıda geçmişin BAŞINDAN taramaya başlıyordu ve
    # her elemanda saat dilimi dönüşümü yapıyordu: aylık grafikte 3000 kurluk
    # bir geçmiş, on binlerce çağrıyla çarpılınca milyonlarca dönüşüm ediyor
    # ve tek başına o uç noktanın 4,4 saniyesini açıklıyordu.
    series: dict[str, tuple[list[datetime], list[float]]] = {}
    for code in sorted(wanted):
        history = list(fx_closes_for(code)) if fx_closes_for else []
        if history:
            ordered = sorted(
                ((_as_utc(stamp), value) for stamp, value in history),
                key=lambda row: row[0],
            )
            series[code] = (
                [stamp for stamp, _ in ordered],
                [value for _, value in ordered],
            )

    def rate_at(currency: str, moment: Any) -> Optional[float]:
        code = (currency or base).upper()
        if code == base:
            return 1.0
        found = series.get(code)
        if found is not None:
            stamps, values = found
            index = bisect_right(stamps, _as_utc(moment))
            if index:
                return values[index - 1]
        return (rates or {}).get(code)

    return rate_at


def _quantity_timeline(
    priced: list[dict[str, Any]], proposals: list[Any]
) -> dict[str, Callable[[Any], float]]:
    """Her enstrüman için "o anda kaç adet tutuluyordu" fonksiyonu.

    Trend, bugünkü pozisyonları geçmiş fiyatlarla yeniden değerliyordu: dün
    alınan bir hisse, geçen yılın portföy değerinde de görünüyordu. Grafiğin
    anlattığı şey portföyün geçmişi değil, bugünkü portföyün geçmişte ne
    edeceğiydi.

    Miktar artık zamanın fonksiyonu: bugünkü adetten, o andan SONRA yapılmış
    alım/satımlar geri alınıyor. Pozisyonun açıldığı tarihten öncesi sıfır --
    yeni eklenen bir hisse geçmişi değiştirmiyor.

    **Kırılım noktaları önceden hesaplanıyor.** İlk hali her çağrıda bütün
    işlem listesini yeniden topluyordu; aylık grafik ~2340 zaman noktasını 26
    sembolle gezdiği için bu, çağrı başına bir toplama ile 60.000 kez
    tekrarlanan bir iş demekti ve tek başına 4,4 saniye tutuyordu. Artık sembol
    başına bir kez sıralanıp ikili aramayla okunuyor.
    """
    deltas: dict[str, list[tuple[datetime, float]]] = {}
    for proposal in proposals:
        if (getattr(proposal, "status", "") or "").upper() != "CONFIRMED":
            continue
        stamp = getattr(proposal, "confirmed_at", None) or getattr(
            proposal, "created_at", None
        )
        symbol = getattr(proposal, "symbol", None)
        if stamp is None or not symbol:
            continue
        side = (getattr(proposal, "transaction_type", "") or "").upper()
        if side not in {"BUY", "SELL"}:
            continue
        try:
            quantity = float(getattr(proposal, "quantity", 0) or 0)
        except (TypeError, ValueError):
            continue
        deltas.setdefault(symbol, []).append(
            (_as_utc(stamp), quantity if side == "BUY" else -quantity)
        )

    timeline: dict[str, Callable[[Any], float]] = {}
    for row in priced:
        symbol = row["symbol"]
        current = float(row["quantity"])
        opened = row.get("opened_at")
        opened_utc = _as_utc(opened) if opened is not None else None

        moves = sorted(deltas.get(symbol, []), key=lambda move: move[0])
        # `edges[i]` zamanından İTİBAREN geçerli olan adet `levels[i]`.
        # Sondan geriye yürünüyor: son işlemden sonrası bugünkü adet, ondan
        # öncesi o işlemin etkisi geri alınmış hali.
        edges: list[datetime] = []
        levels: list[float] = []
        running = current
        for stamp, delta in reversed(moves):
            edges.append(stamp)
            levels.append(running)
            running = running - delta
        edges.reverse()
        levels.reverse()
        #: Herhangi bir işlemden önceki adet.
        opening_level = running

        def held_at(
            moment: Any,
            _edges=edges,
            _levels=levels,
            _opening=opening_level,
            _opened=opened_utc,
        ) -> float:
            target = _as_utc(moment)
            if _opened is not None and target < _opened:
                # Pozisyon henüz açılmamıştı. Katkısı sıfır; geçmişe dönük
                # olarak portföyde varmış gibi gösterilmez.
                return 0.0
            index = bisect_right(_edges, target)
            level = _levels[index - 1] if index else _opening
            # Eksiye düşmez: elde olan veri eksikse (tohumlanmış bir pozisyonun
            # kaydı olmayan geçmişi) sıfırda durur, negatif adet uydurmaz.
            return max(0.0, level)

        timeline[symbol] = held_at
    return timeline


def _as_utc(moment: Any) -> datetime:
    """Karşılaştırılabilir bir UTC damgası.

    Tarih ve zaman damgası birlikte geliyor (günlük seri `date`, gün içi seri
    `datetime`) ve saat dilimsiz damgalar UTC sayılıyor; karşılaştırmanın
    kendisi patlamamalı.
    """
    if isinstance(moment, datetime):
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return datetime(moment.year, moment.month, moment.day, tzinfo=timezone.utc)


def _trend(
    priced: list[dict[str, Any]],
    closes_for: Callable[[str], list[tuple[datetime, float]]],
    intraday: bool = False,
    proposals: Optional[list[Any]] = None,
    rate_at: Optional[Callable[[str, Any], Optional[float]]] = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Portföyün kendi değer serisi.

    İki kural değişti ve ikisi de kasıtlı.

    **Kesişim değil birleşim.** Önceden yalnızca HER sembolün barı olan günler
    kullanılıyordu; tek bir kısa geçmişli isim bütün seriyi kırpıyordu (grafik
    bu yüzden XAUUSD'nin ilk barında, 2025-05-01'de başlıyordu). Pozisyonlar
    girip çıkarken kesişimin bir anlamı da kalmıyor.

    **Son kapanış taşınıyor.** Eski yorum bunu "uydurma bir veri noktası" diye
    reddediyordu; o kural TEK BİR enstrümanın çizgisi için doğru -- işlem
    görmediği bir günde oynuyormuş gibi görünmemeli. Portföy için tersi
    geçerli: ABD borsası kapalıyken Nasdaq pozisyonları son kapanışları kadar
    eder ve o günü tamamen düşürmek portföyü yanlış anlatır.

    Miktar zamanın fonksiyonu (`_quantity_timeline`), dolayısıyla yeni alınan
    bir hisse geçmişi değiştirmiyor.
    """
    per_symbol: dict[str, list[tuple[Any, float]]] = {}
    excluded: list[str] = []

    for row in priced:
        closes = closes_for(row["symbol"])
        if len(closes) < 2:
            excluded.append(row["symbol"])
            continue
        # Gün içi seride anahtar TARİH DEĞİL tam zaman damgası olmalı:
        # `stamp.date()` bir günün bütün barlarını tek noktaya çökertir ve gün
        # görünümü tek bir sütuna inerdi.
        per_symbol[row["symbol"]] = sorted(
            ((stamp if intraday else stamp.date()), close) for stamp, close in closes
        )

    if not per_symbol:
        return [], sorted(excluded)

    held_at = _quantity_timeline(priced, proposals or [])
    currency_of = {row["symbol"]: (row.get("currency") or "TRY") for row in priced}
    axis = sorted({point for series in per_symbol.values() for point, _ in series})

    trend: list[dict[str, Any]] = []
    cursors = {symbol: 0 for symbol in per_symbol}
    last_close: dict[str, Optional[float]] = {symbol: None for symbol in per_symbol}

    for point in axis:
        total = 0.0
        priced_any = False
        for symbol, series in per_symbol.items():
            index = cursors[symbol]
            while index < len(series) and series[index][0] <= point:
                last_close[symbol] = series[index][1]
                index += 1
            cursors[symbol] = index

            close = last_close[symbol]
            if close is None:
                # Bu enstrümanın o noktada henüz hiç barı yok. Geriye doğru
                # fiyat uydurulmaz; katkısı yoktur.
                continue
            quantity = held_at[symbol](point)
            if quantity <= 0:
                continue
            # Toplamadan ÖNCE çevrilir. Farklı para birimlerini çevirmeden
            # toplamak, dolar pozisyonlarını lira sanmaktır.
            rate = rate_at(currency_of[symbol], point) if rate_at else 1.0
            if rate is None:
                continue
            total += quantity * close * rate
            priced_any = True

        if not priced_any:
            # Portföyde o anda hiçbir şey yoksa nokta yazılmaz: sıfır değerli
            # bir portföy ile "henüz portföy yoktu" aynı şey değil.
            continue
        trend.append({
            "date": point if intraday else datetime(
                point.year, point.month, point.day, tzinfo=timezone.utc
            ),
            "value": round(total, 2),
        })

    return trend, sorted(excluded)



#: Mum grafiğinin pencereleri: (kaynak aralık, kova genişliği sn, pencere gün).
#: Kova 0 = günlük kova. Her pencere yüzün üzerinde nokta verecek şekilde
#: seçildi; sayılar bir işlem gününe sığan 78 tane 5 dakikalık bardan türüyor.
#: (kaynak aralık, kova genişliği sn, pencere gün, sembol başına okunacak bar).
#: Okuma sınırı pencereyle birlikte büyümek ZORUNDA: 200 barlık sabit bir tavan,
#: 5 dakikalık seride iki buçuk gün eder ve aylık grafik iki günlük veriyle
#: çizilirdi.
CANDLE_RANGES: dict[str, tuple[str, int, int, int]] = {
    "gun": ("5m", 300, 1, 400),          # 5 dakikalık kovalar
    "hafta": ("5m", 900, 7, 1_200),      # 15 dakikalık kovalar, ~130 nokta
    "ay": ("5m", 3600, 30, 3_000),       # saatlik kovalar, ~150 nokta
    "yil": ("1d", 0, 365, 400),          # günlük, ~252 nokta
    "iki_yil": ("1d", 0, 730, 800),      # günlük, ~504 nokta
}


def portfolio_candles(
    priced: list[dict[str, Any]],
    bars_for: Callable[[str], list[tuple[datetime, float, float]]],
    proposals: Optional[list[Any]] = None,
    bucket_seconds: int = 0,
    rate_at: Optional[Callable[[str, Any], Optional[float]]] = None,
    window_days: int = 0,
) -> list[dict[str, Any]]:
    """Portföyün DEĞERİNİN mum serisi.

    Bu grafik uzun süre `XU100`'ü çizdi -- BIST 100 endeksini, "portföyünüz"
    başlığının altında. Endeks gerçek bir seri ama kullanıcının serisi değil;
    ekranın bir yerinde 1.382.868 TL yazarken grafiğin 14.623'te durmasının
    sebebi buydu.

    **Fitiller ancak gözlemlendiyse çizilir.** Gün içi barların olduğu kovada
    yüksek/düşük gerçekten gözlenmiş portföy değerleridir. Günlük veride ise
    kovada tek bir açılış-kapanış çifti vardır; mum GÖVDEDEN ibaret kalır.
    Enstrümanların günlük en yükseklerini toplamak cazip ama yanlış olurdu:
    o tepeler aynı anda oluşmadı, dolayısıyla toplamları portföyün hiçbir
    zaman ulaşmadığı bir değerdir.
    """
    per_symbol: dict[str, list[tuple[Any, float, float]]] = {}
    for row in priced:
        bars = bars_for(row["symbol"])
        if len(bars) < 2:
            continue
        per_symbol[row["symbol"]] = sorted(bars, key=lambda bar: bar[0])

    if not per_symbol:
        return []

    held_at = _quantity_timeline(priced, proposals or [])
    currency_of = {row["symbol"]: (row.get("currency") or "TRY") for row in priced}
    axis = sorted({stamp for series in per_symbol.values() for stamp, _, _ in series})

    cursors = {symbol: 0 for symbol in per_symbol}
    last: dict[str, Optional[tuple[float, float]]] = {s: None for s in per_symbol}
    points: list[tuple[datetime, float, float]] = []

    for stamp in axis:
        opened = closed = 0.0
        priced_any = False
        for symbol, series in per_symbol.items():
            index = cursors[symbol]
            while index < len(series) and series[index][0] <= stamp:
                last[symbol] = (series[index][1], series[index][2])
                index += 1
            cursors[symbol] = index

            bar = last[symbol]
            if bar is None:
                continue
            quantity = held_at[symbol](stamp)
            if quantity <= 0:
                continue
            rate = rate_at(currency_of[symbol], stamp) if rate_at else 1.0
            if rate is None:
                continue
            opened += quantity * bar[0] * rate
            closed += quantity * bar[1] * rate
            priced_any = True

        if priced_any:
            points.append((_as_utc(stamp), opened, closed))

    if window_days > 0 and points:
        # Pencere serinin SONUNDAN geriye sayılır, bugünden değil: piyasa
        # kapalıyken "son yedi takvim günü" boş bir hafta grafiği demek olurdu.
        cutoff = points[-1][0] - timedelta(days=window_days)
        points = [point for point in points if point[0] >= cutoff]

    return _bucket(points, bucket_seconds)


def _bucket(
    points: list[tuple[datetime, float, float]], bucket_seconds: int
) -> list[dict[str, Any]]:
    """Değer noktalarını mumlara toplar.

    Kova içindeki her gözlenen açılış ve kapanış yüksek/düşük hesabına girer;
    tek noktalı bir kovada mum gövdeden ibaret olur.
    """
    if not points:
        return []

    def key(moment: datetime):
        if bucket_seconds <= 0:
            return moment.date()
        stamp = int(moment.timestamp())
        return stamp - (stamp % bucket_seconds)

    buckets: dict[Any, list[tuple[datetime, float, float]]] = {}
    for point in points:
        buckets.setdefault(key(point[0]), []).append(point)

    candles = []
    for bucket_key in sorted(buckets):
        rows = sorted(buckets[bucket_key], key=lambda row: row[0])
        values = [value for row in rows for value in (row[1], row[2])]
        candles.append({
            "time": int(rows[0][0].timestamp()),
            "open": round(rows[0][1], 2),
            "close": round(rows[-1][2], 2),
            "high": round(max(values), 2),
            "low": round(min(values), 2),
        })
    return candles


def _activity(proposals: list[Any]) -> dict[str, Any]:
    """Realised activity from confirmed proposals — the only per-user
    transaction history that exists (FG-B-05, FG-B-08)."""
    confirmed = [p for p in proposals if (p.status or "").upper() == "CONFIRMED"]
    buys = [p for p in confirmed if (p.transaction_type or "").upper() in {"BUY", "ALIS", "ALIŞ"}]
    sells = [p for p in confirmed if (p.transaction_type or "").upper() in {"SELL", "SATIS", "SATIŞ"}]

    traded = 0.0
    for proposal in confirmed:
        estimate = (proposal.payload or {}).get("estimate") or {}
        amount = estimate.get("net_amount")
        if amount is not None:
            traded += float(amount)

    stamps = [p.confirmed_at for p in confirmed if p.confirmed_at is not None]
    return {
        "confirmed_count": len(confirmed),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "total_traded_value": round(traded, 2),
        "last_transaction_at": max(stamps) if stamps else None,
    }
