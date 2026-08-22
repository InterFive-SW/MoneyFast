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
        if index is None or not stamps or index >= len(stamps):
            return None
        return stamps[index].date().isoformat()

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


def portfolio_returns(
    series: dict[str, list[float]], weights: dict[str, float]
) -> list[float]:
    """Weighted return series for the whole portfolio.

    Truncated to the shortest constituent history so every date has a value
    from every holding. Padding a short series would silently assume the
    missing days were flat, understating the portfolio's volatility.
    """
    usable = {s: r for s, r in series.items() if len(r) >= 2 and weights.get(s)}
    if not usable:
        return []

    length = min(len(r) for r in usable.values())
    total_weight = sum(weights[s] for s in usable)
    if total_weight == 0:
        return []

    combined = []
    for index in range(-length, 0):
        combined.append(
            sum(usable[s][index] * weights[s] for s in usable) / total_weight
        )
    return combined
