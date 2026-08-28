"""Return-series mathematics.

Pure functions over lists of closing prices. No database, no I/O — the caller
supplies the series, which keeps this testable against hand-checked inputs
where an off-by-one in a window is actually visible.

Everything here is **ex-post**: a measurement of what already happened. None of
it forecasts. Parametric VaR in particular is a model estimate under a
normality assumption that financial returns are known to violate in the tails,
which is why the caller labels it as such rather than as a loss bound.

Written with the standard library only. numpy would be a reasonable dependency,
but the backend image currently has none of the scientific stack and pulling it
in to compute a standard deviation over 250 numbers is not a trade worth making.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional, Sequence

#: BIST and US markets both trade roughly 252 days a year. The square-root-of-
#: time scaling this implies is itself an approximation; it is the convention,
#: and it is disclosed in `assumptions.annualization_factor`.
TRADING_DAYS = 252

#: Below this many observations a volatility figure is noise dressed as a
#: number. The caller surfaces it through `is_statistically_reliable` rather
#: than refusing to compute.
MIN_RELIABLE_OBSERVATIONS = 60

#: Lookback windows the contract accepts, in trading days.
LOOKBACK_DAYS = {
    "1M": 22, "3M": 66, "6M": 126, "1Y": 252, "3Y": 756, "5Y": 1260, "MAX": 10_000,
}


def window_for(lookback: str) -> int:
    return LOOKBACK_DAYS.get((lookback or "1Y").upper(), LOOKBACK_DAYS["1Y"])


def simple_returns(closes: Sequence[float]) -> list[float]:
    """Period-over-period returns.

    Non-positive prices are skipped rather than divided by: a zero or negative
    close is bad data, and letting it through produces an infinite return that
    then poisons every downstream statistic.
    """
    out: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous <= 0:
            continue
        out.append(current / previous - 1.0)
    return out


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    """Sample standard deviation (n-1).

    The sample form, not the population form: these returns are a sample of a
    process, not the whole of it, and with 22 observations the difference is
    about 2%.
    """
    if len(values) < 2:
        return 0.0
    average = mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def annualised_volatility(returns: Sequence[float]) -> Optional[float]:
    if len(returns) < 2:
        return None
    return stdev(returns) * math.sqrt(TRADING_DAYS)


def downside_deviation(returns: Sequence[float], threshold: float = 0.0) -> Optional[float]:
    """Volatility of losses only.

    Uses the full observation count as the denominator, not just the losing
    days — the standard definition. Dividing by the number of losses would
    make a portfolio that rarely loses look more volatile than one that
    always does.
    """
    if len(returns) < 2:
        return None
    shortfalls = [min(0.0, value - threshold) ** 2 for value in returns]
    return math.sqrt(sum(shortfalls) / (len(returns) - 1)) * math.sqrt(TRADING_DAYS)


def max_drawdown(
    closes: Sequence[float], stamps: Optional[Sequence[datetime]] = None
) -> Optional[dict[str, Any]]:
    """Deepest peak-to-trough decline, with its dates.

    `recovery_date` is None when the series never regained the prior peak —
    which is meaningfully different from "recovered today" and must not be
    filled in with the last date.
    """
    if len(closes) < 2:
        return None

    peak = closes[0]
    peak_index = trough_index = 0
    worst = 0.0
    best_peak_index = 0

    for index, price in enumerate(closes):
        if price > peak:
            peak, peak_index = price, index
        decline = price / peak - 1.0 if peak > 0 else 0.0
        if decline < worst:
            worst, trough_index, best_peak_index = decline, index, peak_index

    if worst == 0.0:
        return None

    recovery_index = None
    peak_price = closes[best_peak_index]
    for index in range(trough_index + 1, len(closes)):
        if closes[index] >= peak_price:
            recovery_index = index
            break

    def stamp(index: Optional[int]) -> Optional[str]:
        """The date at `index`, whether the caller indexed by day or instant.

        `value_series` works in whole days and hands back `date`; callers that
        pass raw candle timestamps hand back `datetime`. Insisting on one of
        them would make this helper's type the reason a date is missing.
        """
        if index is None or not stamps or index >= len(stamps):
            return None
        moment = stamps[index]
        return (moment.date() if hasattr(moment, "date") else moment).isoformat()

    return {
        "value": round(worst, 6),
        "peak_date": stamp(best_peak_index),
        "trough_date": stamp(trough_index),
        "recovery_date": stamp(recovery_index),
        "duration_days": (trough_index - best_peak_index),
    }


def historical_var(
    returns: Sequence[float], confidence: float = 0.95
) -> Optional[float]:
    """Empirical quantile of the loss distribution. Negative, as a fraction."""
    if len(returns) < 20:
        return None
    ordered = sorted(returns)
    index = int((1.0 - confidence) * len(ordered))
    return round(ordered[min(index, len(ordered) - 1)], 6)


def conditional_var(
    returns: Sequence[float], confidence: float = 0.95
) -> Optional[float]:
    """Mean loss beyond the VaR threshold — expected shortfall."""
    if len(returns) < 20:
        return None
    ordered = sorted(returns)
    cutoff = max(1, int((1.0 - confidence) * len(ordered)))
    return round(mean(ordered[:cutoff]), 6)


def parametric_var(returns: Sequence[float], confidence: float = 0.95) -> Optional[float]:
    """Gaussian VaR.

    A model estimate under an assumption returns are known to violate: real
    tails are fatter than normal, so this understates extreme losses. The
    caller must present it as such, never as a bound.
    """
    if len(returns) < 20:
        return None
    # Inverse normal CDF at the common confidence levels. A table rather than
    # an approximation, because only three values are ever asked for and an
    # approximation would be less accurate for no benefit.
    z = {0.90: 1.2816, 0.95: 1.6449, 0.99: 2.3263}.get(round(confidence, 2), 1.6449)
    return round(mean(returns) - z * stdev(returns), 6)


def covariance(left: Sequence[float], right: Sequence[float]) -> float:
    size = min(len(left), len(right))
    if size < 2:
        return 0.0
    left, right = left[-size:], right[-size:]
    left_mean, right_mean = mean(left), mean(right)
    return sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left, right)
    ) / (size - 1)


def correlation(left: Sequence[float], right: Sequence[float]) -> Optional[float]:
    denominator = stdev(left) * stdev(right)
    if denominator == 0:
        return None
    return round(covariance(left, right) / denominator, 6)


def beta(asset: Sequence[float], benchmark: Sequence[float]) -> Optional[float]:
    """Sensitivity to the benchmark.

    Undefined when the benchmark never moves — returning 0.0 there would claim
    the asset is uncorrelated rather than that the question is unanswerable.
    """
    variance = stdev(benchmark) ** 2
    if variance == 0:
        return None
    return round(covariance(asset, benchmark) / variance, 6)


def sharpe(returns: Sequence[float], risk_free_rate: float) -> Optional[float]:
    """Annualised excess return per unit of volatility.

    Uninterpretable without the rate it was computed against, which is why the
    contract requires `assumptions.risk_free_rate` alongside it.
    """
    volatility = annualised_volatility(returns)
    if not volatility:
        return None
    annual_return = mean(returns) * TRADING_DAYS
    return round((annual_return - risk_free_rate) / volatility, 4)


def _currency_of(holding: Any, base_currency: str) -> str:
    """The instrument's own currency, under either key the callers use.

    `risk` builds positions with `instrument_currency`; `analytics` reads
    holdings straight from `market_service` where the key is `currency`. The
    two grew separately and neither is wrong, so this reads both rather than
    forcing one caller to rename a field the MCP contract has frozen.
    """
    return (
        holding.get("instrument_currency")
        or holding.get("currency")
        or base_currency
    ).upper()


def _day_map(bars: Sequence[tuple]) -> dict[Any, float]:
    """[(timestamp, close), ...] -> {date: close}, dropping unusable prices."""
    out: dict[Any, float] = {}
    for stamp, close in bars:
        value = float(close)
        if value <= 0:
            # A zero or negative close is bad data. Kept, it produces an
            # infinite return that poisons every statistic downstream.
            continue
        out[stamp.date() if hasattr(stamp, "date") else stamp] = value
    return out


def value_series(
    holdings: Sequence[Any],
    closes_for: Any,
    base_currency: str = "TRY",
) -> tuple[list[Any], list[float], list[str]]:
    """Portfolio value per day, in the base currency, on real shared dates.

    Returns `(dates, values, excluded_symbols)` oldest first.

    **One series, two consumers.** `risk` and `analytics` each built their own
    and the two disagreed about the same portfolio, in three separate ways:

    1. *Alignment.* `risk` lined series up by tail INDEX. Measured on live
       data: DOAS had 395 bars and XU100 392 — four days missing from the
       index (2025-12-24, 2026-05-26/27/28) — so everything before May 2026
       was compared against prices three days out of step, and beta against
       XU100 for a 94%-DOAS portfolio came out as 0.0062. A Turkish equity
       portfolio is not uncorrelated with the Turkish index; the number was
       not missing, it was wrong. Only dates where EVERY holding traded are
       used here.

    2. *What was being computed.* A weighted average of constituent returns
       with FIXED weights is a DAILY-REBALANCED portfolio. `assumptions`
       reported `BUY_AND_HOLD`. Deriving returns from a value series is
       buy-and-hold, so the label becomes true.

    3. *Currency.* `analytics` summed `quantity x close` across holdings with
       no conversion, adding dollars to lira. Each holding is converted here,
       per day, at that day's rate.

    Quantities are never read. Each holding is carried as its market value
    scaled by its own price index, so the last day reproduces exactly the
    portfolio's current value. `market_value` is always present and already
    in the base currency; `quantity` defaults to 0 in the MCP schema, and a
    caller that omitted it would otherwise have its holding silently valued
    at nothing.
    """
    priced, values, excluded = _base_prices(holdings, closes_for, base_currency)
    if not priced:
        return [], [], excluded

    common = sorted(set.intersection(*(set(days) for days in priced.values())))
    if len(common) < 2:
        return [], [], excluded

    last = common[-1]
    series = []
    for day in common:
        series.append(
            sum(
                values[symbol] * (days[day] / days[last])
                for symbol, days in priced.items()
            )
        )
    return common, series, excluded


def _base_prices(
    holdings: Sequence[Any], closes_for: Any, base_currency: str = "TRY"
) -> tuple[dict[str, dict[Any, float]], dict[str, float], list[str]]:
    """Each holding's price history, converted to the base currency per day.

    Shared by `value_series` and `rebalanced_returns` so the currency rule --
    convert at THAT day's rate, drop a day with no rate rather than invent one
    -- has a single implementation. Returns `(prices, market_values, excluded)`.
    """
    base = (base_currency or "TRY").upper()
    priced: dict[str, dict[Any, float]] = {}
    values: dict[str, float] = {}
    excluded: list[str] = []
    fx_cache: dict[str, dict[Any, float]] = {}

    for holding in holdings:
        symbol = holding["symbol"]
        market_value = abs(float(holding.get("market_value") or 0.0))
        if market_value == 0:
            # Contributes nothing either way. Skipped silently rather than
            # named as excluded: it is not missing history, and letting its
            # trading days constrain the shared date set would shorten the
            # window for every other holding on account of a holding worth
            # nothing.
            continue

        bars = _day_map(list(closes_for(symbol)) if closes_for else [])
        if len(bars) < 3:
            # Same threshold the return series needs: three closes give two
            # returns, which is the least that can be called a series.
            excluded.append(symbol)
            continue

        currency = _currency_of(holding, base)
        if currency != base:
            if currency not in fx_cache:
                fx_cache[currency] = _day_map(
                    list(closes_for(f"{currency}{base}")) if closes_for else []
                )
            rates = fx_cache[currency]
            # Only days with BOTH a price and a rate. Valuing a dollar holding
            # in lira on a day with no rate would need an invented one, and
            # CLAUDE.md's currency rule is explicit that 1.0 is never assumed.
            bars = {day: close * rates[day] for day, close in bars.items() if day in rates}
            if len(bars) < 3:
                excluded.append(symbol)
                continue

        priced[symbol] = bars
        values[symbol] = market_value

    return priced, values, sorted(excluded)


def rebalanced_returns(
    holdings: Sequence[Any], closes_for: Any, base_currency: str = "TRY"
) -> list[float]:
    """Portfolio returns under DAILY_REBALANCE, on the shared dates.

    Weights are reset to target every day, so this is the weighted average of
    the constituents' daily returns rather than the return of a value series
    that drifts with them. The two are genuinely different portfolios and the
    contract lets the caller pick; before this, the parameter was accepted,
    echoed, and ignored -- whichever assumption was asked for, one fixed
    computation came back under its name.
    """
    priced, values, _ = _base_prices(holdings, closes_for, base_currency)
    if not priced:
        return []

    common = sorted(set.intersection(*(set(days) for days in priced.values())))
    if len(common) < 3:
        return []

    # No zero guard: `_base_prices` skips worthless holdings before they reach
    # here, so a non-empty `priced` always carries a positive total.
    total = sum(values[symbol] for symbol in priced)

    per_symbol = {
        symbol: simple_returns([days[day] for day in common])
        for symbol, days in priced.items()
    }
    length = min(len(r) for r in per_symbol.values())
    return [
        sum(per_symbol[symbol][index] * values[symbol] for symbol in priced) / total
        for index in range(length)
    ]


def align_to(
    dates: Sequence[Any], bars: Sequence[tuple]
) -> list[float]:
    """Another instrument's closes, on exactly `dates`.

    Days the instrument did not trade are dropped along with the portfolio's
    value for that day, which is what `paired_returns` handles. Returning a
    short list here rather than padding is deliberate: a forward-filled
    benchmark shows the index flat on a day it was simply closed.
    """
    day_map = _day_map(bars)
    return [day_map[day] for day in dates if day in day_map]


def paired_returns(
    dates: Sequence[Any], values: Sequence[float], bars: Sequence[tuple]
) -> tuple[list[float], list[float]]:
    """Portfolio and benchmark returns over the dates BOTH actually have.

    Beta and correlation were computed from `portfolio[-size:]` against
    `benchmark[-size:]`, which lines up two series by length rather than by
    date. When the benchmark is missing days the holdings have — and it was,
    four of them — every earlier observation is paired with the wrong day.
    """
    day_map = _day_map(bars)
    shared = [(day, value) for day, value in zip(dates, values) if day in day_map]
    if len(shared) < 3:
        return [], []
    return (
        simple_returns([value for _, value in shared]),
        simple_returns([day_map[day] for day, _ in shared]),
    )
