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


#: A daily bar older than this is stale rather than merely settled. One
#: calendar day covers the ordinary case (yesterday's close, read this
#: morning); a weekend or a holiday pushes past it, which is correct -- on a
#: Sunday the newest close really is two days old.
FRESH_WITHIN_DAYS = 1


def _is_delayed(newest: Any) -> bool:
    """Whether the terminal observation lags today.

    Was hardcoded `False` on every response, with the reasoning that a daily
    close is settled by the time we hold it. Settled and current are different
    claims: after a long weekend the newest close is three days old, and the
    contract's `is_delayed` is what the assistant renders as freshness. An
    unreadable or missing stamp counts as delayed -- the cautious direction,
    since the alternative asserts currency we cannot demonstrate.
    """
    if not hasattr(newest, "astimezone"):
        return True
    age = datetime.now(timezone.utc) - newest.astimezone(timezone.utc)
    return age.days > FRESH_WITHIN_DAYS


def history_limit(lookback: str) -> int:
    """Bars to read for `lookback`, including the one the first return needs.

    Lives here rather than in the router so the window arithmetic has one
    home. The router passes this to `market_service.candle_closes`, whose own
    default cap of 260 was silently truncating every window longer than a
    year.
    """
    return returns_math.window_for(lookback) + 1


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
    # What the window would need. Reported alongside what was actually
    # obtained, because the two diverge silently: the candle reader has its
    # own row cap, so a 5Y request came back as roughly one year while the
    # response still said "5Y".
    bars_requested = window + 1

    # ---- gather history --------------------------------------------------
    def windowed(symbol: str) -> List[tuple]:
        """The requested window of one instrument's closes, oldest first."""
        bars = list(closes_for(symbol)) if closes_for else []
        return bars[-(window + 1):]

    # Per-symbol return series, kept for the correlation matrix. These are in
    # each instrument's OWN currency and are not what the portfolio figures
    # are built from -- see `value_series`.
    series: Dict[str, List[float]] = {}
    for symbol in symbols:
        bars = windowed(symbol)
        if len(bars) >= 3:
            series[symbol] = returns_math.simple_returns([close for _, close in bars])

    # The single portfolio series. Date-aligned, base-currency, buy-and-hold.
    # Both this module and `analytics` read it, so the two can no longer
    # report different volatility for the same portfolio.
    dates, values, excluded = returns_math.value_series(positions, windowed)
    # The value series IS the buy-and-hold portfolio. Daily rebalancing is a
    # different portfolio -- weights reset every day -- and the caller picks.
    # Until now the parameter was accepted, echoed and ignored: whichever
    # assumption was requested, one fixed computation came back under its name.
    portfolio = (
        returns_math.rebalanced_returns(positions, windowed)
        if (rebalance_assumption or "").upper() == "DAILY_REBALANCE"
        else returns_math.simple_returns(values)
    )
    observations = len(portfolio)

    benchmark_bars = windowed(benchmark)

    dropped = set(excluded)
    covered_value = sum(
        abs(float(p["market_value"])) for p in positions if p["symbol"] not in dropped
    )
    total_value = sum(abs(float(p["market_value"])) for p in positions)
    coverage = round(covered_value / total_value, 4) if total_value else 0.0
    reliable = observations >= returns_math.MIN_RELIABLE_OBSERVATIONS and coverage >= 0.90

    # ---- metrics ---------------------------------------------------------
    computed: Dict[str, Any] = {}

    if wanted("CONCENTRATION"):
        computed["concentration"] = concentration(positions)

    if wanted("VOLATILITY"):
        computed["volatility_annualized"] = returns_math.annualised_volatility(portfolio)
        computed["downside_deviation_annualized"] = returns_math.downside_deviation(portfolio)

    if wanted("MAX_DRAWDOWN"):
        # From the SAME series every other metric uses, so a drawdown and a
        # volatility on one screen always describe one portfolio. Reading it
        # off the value series instead would be right for buy-and-hold and
        # quietly wrong for a rebalanced one, which is the shape of bug this
        # whole change exists to remove.
        #
        # Drawdown is scale-invariant, so the level the path starts at is
        # arbitrary; the dates are the portfolio's own.
        levels = [100.0]
        for value in portfolio:
            levels.append(levels[-1] * (1.0 + value))
        computed["max_drawdown"] = (
            returns_math.max_drawdown(levels, dates[-len(levels):])
            if len(levels) >= 2
            else None
        )

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
        # Paired on the dates BOTH the portfolio and the index actually have.
        # Lining the two up by length instead was measurably wrong: XU100 is
        # missing four days the holdings have, so every observation before the
        # gap was compared against a different day and beta for a 94%-DOAS
        # portfolio came out as 0.0062 against the Turkish index.
        paired_portfolio, paired_benchmark = returns_math.paired_returns(
            dates, values, benchmark_bars
        )
        if paired_portfolio and paired_benchmark:
            computed["beta"] = returns_math.beta(paired_portfolio, paired_benchmark)
            computed["correlation_to_benchmark"] = returns_math.correlation(
                paired_portfolio, paired_benchmark
            )
        else:
            # No overlapping history is not the same as zero sensitivity.
            computed["beta"] = None
            computed["correlation_to_benchmark"] = None

    if wanted("CORRELATION_MATRIX"):
        computed["correlation_matrix"] = _correlation_matrix(series)

    resolved_rate = risk_free_rate if risk_free_rate is not None else DEFAULT_RISK_FREE_RATE

    return {
        # The portfolio's own dates now, not whichever symbol came first out
        # of a dict. The window reported and the window measured are the same
        # thing for the first time.
        "as_of": _iso(dates[-1]) if dates else _now_iso(),
        "source": SOURCE,
        "is_delayed": _is_delayed(dates[-1] if dates else None),
        "window": {
            "start_date": _date(dates[0]) if dates else "",
            "end_date": _date(dates[-1]) if dates else "",
            "observation_count": observations,
            "frequency": "DAILY",
        },
        "metrics": computed,
        "assumptions": {
            "lookback": lookback,
            #: How many bars the requested window needs. `window.observation_count`
            #: says how many were actually usable; when the two differ the
            #: history simply is not there, and the reader can see that rather
            #: than trusting the label.
            "lookback_bars_requested": bars_requested,
            # Echoes what was requested, not what was obtainable. The MCP
            # normalizer forces beta to None when this field is empty, so
            # blanking it after successfully computing a beta would discard
            # the number we just produced. Whether history existed is reported
            # separately.
            "benchmark_symbol": benchmark,
            "benchmark_history_available": bool(
                returns_math.align_to(dates, benchmark_bars)
            ),
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


# ---------------------------------------------------------------------------
# "What if" simulation
# ---------------------------------------------------------------------------
def apply_changes(
    positions: List[Dict[str, Any]], changes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """A hypothetical portfolio: today's holdings plus the caller's deltas.

    Pure, and deliberately so -- the whole simulation needs no new mathematics
    because `calculate` already takes an arbitrary position list. The only new
    thing is producing a different list.

    Each change is pre-resolved by the caller and carries `unit_value`: the
    value of ONE unit in the base currency. Prices belong to the router's
    database work, not here.

    Two rules that keep the result honest:

    * A delta that would take a holding below zero closes it at zero. Nobody
      can sell more than they hold, and a negative weight would give the
      concentration maths a share of the portfolio that does not exist.
    * A position reduced to nothing is REMOVED rather than kept at zero. A
      zero-value row still counts as a name in `effective_n`, so leaving it
      would report a diversification the user no longer has.
    """
    merged = {position["symbol"]: dict(position) for position in positions}

    for change in changes:
        symbol = change["symbol"]
        delta = float(change["quantity_delta"])
        unit_value = float(change["unit_value"])

        existing = merged.get(symbol)
        if existing is None:
            if delta <= 0:
                # Selling something that is not held is not a portfolio, it is
                # a typo. Ignored rather than modelled as a short.
                continue
            merged[symbol] = {
                "symbol": symbol,
                "quantity": delta,
                "market_value": delta * unit_value,
                "asset_class": change.get("asset_class") or "EQUITY",
                "sector": change.get("sector") or "UNCLASSIFIED",
                "instrument_currency": change.get("instrument_currency") or "TRY",
            }
            continue

        quantity = max(0.0, float(existing["quantity"]) + delta)
        if quantity == 0.0:
            del merged[symbol]
            continue
        existing["quantity"] = quantity
        existing["market_value"] = quantity * unit_value

    return list(merged.values())


def summarise_for_simulation(metrics: Dict[str, Any], scored: Dict[str, Any]) -> Dict[str, Any]:
    """The handful of figures the before/after comparison shows.

    A subset on purpose: putting the full metric block on both sides would
    invite the reader to diff twenty numbers, most of which move for reasons
    the change did not cause.
    """
    concentration = metrics.get("concentration") or {}
    drawdown = metrics.get("max_drawdown") or {}
    return {
        "score": scored.get("score"),
        "level": scored.get("level"),
        "volatility": metrics.get("volatility_annualized"),
        "hhi": concentration.get("hhi"),
        "effective_n": concentration.get("effective_n"),
        "max_drawdown": drawdown.get("value"),
    }


def summarise_for_agent(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """The figures the score is actually built from, flattened.

    A subset, and for a different reason than the simulation's: this payload
    goes to a language model, which will quote whatever it is handed. The
    full metric block travels on `calculate_portfolio_risk_metrics` in the
    same turn, so repeating twenty numbers here only creates a second place
    for them to be quoted from -- and two sources for one figure is how a
    turn ends up stating both.

    Nested values are lifted out (`max_drawdown.value` rather than the dict)
    because the model reads these as plain facts, not as a structure to
    navigate.
    """
    concentration = metrics.get("concentration") or {}
    drawdown = metrics.get("max_drawdown") or {}
    return {
        "volatility_annualized": metrics.get("volatility_annualized"),
        "max_drawdown": drawdown.get("value"),
        "hhi": concentration.get("hhi"),
        "effective_n": concentration.get("effective_n"),
        "top_3_weight": concentration.get("top_3_weight"),
        "largest_position": concentration.get("largest_position"),
    }


def _delta(after: Optional[float], before: Optional[float]) -> Optional[float]:
    """Difference, or None when either side could not be measured.

    Zero would read as "no change", which is a different claim from "we could
    not tell".
    """
    if after is None or before is None:
        return None
    return round(after - before, 6)


def simulation_deltas(
    current: Dict[str, Any], hypothetical: Dict[str, Any]
) -> Dict[str, Optional[float]]:
    return {
        key: _delta(hypothetical.get(key), current.get(key))
        for key in ("score", "volatility", "hhi", "effective_n", "max_drawdown")
    }
