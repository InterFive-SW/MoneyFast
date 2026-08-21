"""Ex-post risk statistics, computed from real price history.

Every figure here is a measurement of what already happened. None of it is a
forecast, and the tool contract forbids presenting it as one.

Two kinds of metric, with different reliability:

**Concentration** is exact. HHI, effective N, top-k weights and the
asset-class/currency/sector breakdowns are pure functions of the submitted
positions and need no history at all.

**History-dependent metrics** — volatility, drawdown, VaR, CVaR, beta,
correlation, Sharpe — are computed from daily closes in
`investment.market_candles`. An instrument with too little history is named in
`data_quality.excluded_symbols` rather than being filled in from its neighbours,
and `coverage` reports what fraction of the portfolio's market value actually
had usable bars. A metric that cannot be computed stays None: an invented
volatility figure is worse than an absent one, because the absent one is
obviously absent.
"""

import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import returns as returns_math

log = logging.getLogger("moneyfast.risk")

#: TCMB one-week repo rate, as a fixture. Not a live feed — labelled as
#: `FIXTURE_POLICY_RATE` in assumptions so nothing downstream can present it
#: as a quoted rate.
DEFAULT_RISK_FREE_RATE = float(os.getenv("TR_POLICY_RATE", "0.425"))

SOURCE = "MONEYFAST_FIXTURE_ANALYTICS"

TRADING_DAYS_PER_YEAR = returns_math.TRADING_DAYS

#: The index every relative metric is measured against unless the caller names
#: another one.
DEFAULT_BENCHMARK = "XU100"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _weights(positions: List[Dict[str, Any]]) -> Dict[str, float]:
    total = sum(abs(float(p["market_value"])) for p in positions)
    if total == 0:
        return {p["symbol"]: 0.0 for p in positions}
    return {p["symbol"]: abs(float(p["market_value"])) / total for p in positions}


def concentration(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Herfindahl-Hirschman concentration and its breakdowns.

    Exact: derived entirely from the submitted market values, so it carries
    none of the caveats the history-dependent metrics do.
    """
    weights = _weights(positions)
    ordered = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    hhi = sum(weight**2 for weight in weights.values())

    by_asset_class: Dict[str, float] = defaultdict(float)
    by_currency: Dict[str, float] = defaultdict(float)
    by_sector: Dict[str, float] = defaultdict(float)
    for position in positions:
        weight = weights[position["symbol"]]
        by_asset_class[position.get("asset_class") or "EQUITY"] += weight
        by_currency[position.get("instrument_currency") or "TRY"] += weight
        # UNCLASSIFIED only when the caller genuinely has no sector for the
        # instrument. It used to be hardcoded for every portfolio because the
        # position contract did not carry the field; it does now.
        by_sector[position.get("sector") or "UNCLASSIFIED"] += weight

    def top(count: int) -> float:
        return round(sum(weight for _, weight in ordered[:count]), 6)

    return {
        "hhi": round(hhi, 6),
        # 1/hhi is undefined for an all-zero portfolio; 0.0 reads correctly as
        # "no effective positions" where inf would render as a number.
        "effective_n": round(1 / hhi, 4) if hhi > 0 else 0.0,
        "top_1_weight": top(1),
        "top_3_weight": top(3),
        "top_5_weight": top(5),
        "largest_position": (
            {"symbol": ordered[0][0], "weight": round(ordered[0][1], 6)} if ordered else None
        ),
        "by_asset_class": {key: round(value, 6) for key, value in by_asset_class.items()},
        "by_sector": {key: round(value, 6) for key, value in by_sector.items()},
        "by_currency": {key: round(value, 6) for key, value in by_currency.items()},
    }


def calculate(
    positions: List[Dict[str, Any]],
    lookback: str = "1Y",
    benchmark_symbol: Optional[str] = None,
    metrics: Optional[List[str]] = None,
    confidence_level: float = 0.95,
    risk_free_rate: Optional[float] = None,
    rebalance_assumption: str = "BUY_AND_HOLD",
    closes_for: Optional[Callable[[str], List[tuple]]] = None,
) -> Dict[str, Any]:
    """Compute the requested metrics.

    `closes_for(symbol)` returns [(timestamp, close), ...] oldest first; the
    router passes `market_service.candle_closes`. Injected rather than imported
    so this module stays free of database concerns and testable against
    hand-built series.
    """
    requested = [metric.upper() for metric in metrics] if metrics else None
    symbols = [position["symbol"] for position in positions]

    def wanted(name: str) -> bool:
        # Default (None) computes everything except the correlation matrix.
        if requested is None:
            return name != "CORRELATION_MATRIX"
        return name in requested

    window = returns_math.window_for(lookback)
    benchmark = benchmark_symbol or DEFAULT_BENCHMARK

    # ---- gather history --------------------------------------------------
    series: Dict[str, List[float]] = {}
    stamps: Dict[str, List[Any]] = {}
    excluded: List[str] = []

    for symbol in symbols:
        bars = list(closes_for(symbol)) if closes_for else []
        bars = bars[-(window + 1):]
        if len(bars) < 3:
            # Too little to say anything. Named rather than silently treated
            # as flat, which would drag portfolio volatility toward zero.
            excluded.append(symbol)
            continue
        stamps[symbol] = [stamp for stamp, _ in bars]
        series[symbol] = returns_math.simple_returns([close for _, close in bars])

    benchmark_bars = list(closes_for(benchmark)) if closes_for else []
    benchmark_bars = benchmark_bars[-(window + 1):]
    benchmark_returns = (
        returns_math.simple_returns([close for _, close in benchmark_bars])
        if len(benchmark_bars) >= 3
        else []
    )

    weights = _weights(positions)
    covered_value = sum(
        abs(float(p["market_value"])) for p in positions if p["symbol"] in series
    )
    total_value = sum(abs(float(p["market_value"])) for p in positions)
    coverage = round(covered_value / total_value, 4) if total_value else 0.0

    portfolio = returns_math.portfolio_returns(series, weights)
    observations = len(portfolio)
    reliable = observations >= returns_math.MIN_RELIABLE_OBSERVATIONS and coverage >= 0.90

    # ---- metrics ---------------------------------------------------------
    computed: Dict[str, Any] = {}

    if wanted("CONCENTRATION"):
        computed["concentration"] = concentration(positions)

    if wanted("VOLATILITY"):
        computed["volatility_annualized"] = returns_math.annualised_volatility(portfolio)
        computed["downside_deviation_annualized"] = returns_math.downside_deviation(portfolio)

    if wanted("MAX_DRAWDOWN"):
        computed["max_drawdown"] = _portfolio_drawdown(portfolio, stamps)

    if wanted("VAR"):
        computed["var"] = _var_block(
            portfolio, confidence_level, total_value, method="HISTORICAL"
        )
    if wanted("CVAR"):
        computed["cvar"] = _var_block(
            portfolio, confidence_level, total_value, method="HISTORICAL", conditional=True
        )

    if wanted("SHARPE"):
        computed["sharpe_ratio"] = returns_math.sharpe(
            portfolio,
            risk_free_rate if risk_free_rate is not None else DEFAULT_RISK_FREE_RATE,
        )

    if wanted("BETA"):
        if benchmark_returns and portfolio:
            size = min(len(portfolio), len(benchmark_returns))
            computed["beta"] = returns_math.beta(portfolio[-size:], benchmark_returns[-size:])
            computed["correlation_to_benchmark"] = returns_math.correlation(
                portfolio[-size:], benchmark_returns[-size:]
            )
        else:
            # No benchmark history is not the same as zero sensitivity.
            computed["beta"] = None
            computed["correlation_to_benchmark"] = None

    if wanted("CORRELATION_MATRIX"):
        computed["correlation_matrix"] = _correlation_matrix(series)

    resolved_rate = risk_free_rate if risk_free_rate is not None else DEFAULT_RISK_FREE_RATE
    window_stamps = next(iter(stamps.values()), [])

    return {
        "as_of": _iso(window_stamps[-1]) if window_stamps else _now_iso(),
        "source": SOURCE,
        # The terminal bar is the provider's most recent daily close, which is
        # settled by the time we hold it.
        "is_delayed": False,
        "window": {
            "start_date": _date(window_stamps[0]) if window_stamps else "",
            "end_date": _date(window_stamps[-1]) if window_stamps else "",
            "observation_count": observations,
            "frequency": "DAILY",
        },
        "metrics": computed,
        "assumptions": {
            "lookback": lookback,
            # Echoes what was requested, not what was obtainable. The MCP
            # normalizer forces beta to None when this field is empty, so
            # blanking it after successfully computing a beta would discard
            # the number we just produced. Whether history existed is reported
            # separately.
            "benchmark_symbol": benchmark,
            "benchmark_history_available": bool(benchmark_returns),
            "requested_metrics": metrics,
            "rebalance_assumption": rebalance_assumption,
            "confidence_level": confidence_level,
            # Required by the contract: Sharpe cannot be interpreted without
            # the rate it was computed against.
            "risk_free_rate": resolved_rate,
            "risk_free_rate_source": (
                "CALLER_SUPPLIED" if risk_free_rate is not None else "FIXTURE_POLICY_RATE"
            ),
            "annualization_factor": TRADING_DAYS_PER_YEAR,
            "price_history_available": bool(series),
        },
        "data_quality": {
            "coverage": coverage,
            "excluded_symbols": excluded,
            "gap_filled_days": 0,
            "is_statistically_reliable": reliable,
        },
    }


def _portfolio_drawdown(portfolio: List[float], stamps: Dict[str, List[Any]]) -> Optional[Dict]:
    """Drawdown of the synthetic portfolio index built from its return series."""
    if len(portfolio) < 2:
        return None
    level = 100.0
    levels = [level]
    for value in portfolio:
        level *= 1.0 + value
        levels.append(level)
    dates = next(iter(stamps.values()), None)
    aligned = dates[-len(levels):] if dates and len(dates) >= len(levels) else None
    return returns_math.max_drawdown(levels, aligned)


def _var_block(
    portfolio: List[float],
    confidence: float,
    total_value: float,
    method: str,
    conditional: bool = False,
) -> Optional[Dict[str, Any]]:
    fraction = (
        returns_math.conditional_var(portfolio, confidence)
        if conditional
        else returns_math.historical_var(portfolio, confidence)
    )
    if fraction is None:
        return None
    return {
        "method": method,
        "confidence_level": confidence,
        "horizon_days": 1,
        "value_fraction": fraction,
        "value_currency": round(fraction * total_value, 2),
    }


def _correlation_matrix(series: Dict[str, List[float]]) -> Optional[Dict[str, Any]]:
    symbols = sorted(series)
    if len(symbols) < 2:
        return None
    length = min(len(series[s]) for s in symbols)
    trimmed = {s: series[s][-length:] for s in symbols}
    return {
        "symbols": symbols,
        "matrix": [
            [
                1.0 if a == b else (returns_math.correlation(trimmed[a], trimmed[b]) or 0.0)
                for b in symbols
            ]
            for a in symbols
        ],
    }


def _date(stamp: Any) -> str:
    return stamp.date().isoformat() if hasattr(stamp, "date") else str(stamp)


def _iso(stamp: Any) -> str:
    if hasattr(stamp, "astimezone"):
        return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(stamp)
