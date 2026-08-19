# filename: risk_strategy_tools.py
"""Risk and strategy domain tools.

MoneyFast MCP server.
Contracts are frozen against "MCP Tools Interface Definitions v2.1".
Data comes from the core backend over HTTP; see backend_client for the base
URL, timeout, retry and error-mapping policy. Nothing in this module returns
canned data, and nothing falls back to canned data on failure.
"""

# from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

import backend_client
from backend_client import (
    AuthorizationError,
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)

TOOL = "calculate_portfolio_risk_metrics"


async def calculate_portfolio_risk_metrics(
    positions: list[dict[str, Any]],
    lookback: str = "1Y",
    benchmark_symbol: Optional[str] = None,
    metrics: Optional[list[str]] = None,
    confidence_level: float = 0.95,
    risk_free_rate: Optional[float] = None,
    rebalance_assumption: str = "BUY_AND_HOLD",
) -> dict[str, Any]:
    """
    Computes ex-post (historical, backward-looking) risk statistics for a set of
    positions over a specified lookback window. All outputs are descriptive
    measurements of past behavior. They are NOT forecasts, NOT risk-tolerance
    judgments, and NOT an assessment of portfolio suitability.

    WHEN TO USE
        - "How risky is my portfolio", "what is my volatility", "am I too
          concentrated", "what was my worst drawdown", "how correlated am I to XU100".
        - To quantify a risk statement before explaining it. NEVER state a volatility,
          drawdown, beta, or concentration figure this tool did not return.

    WHEN NOT TO USE
        - To forecast future returns, future volatility, or probability of loss beyond
          the explicitly labeled parametric VaR output.
        - To decide whether the user SHOULD reduce a position. That is a suitability
          judgment and is out of scope for this system.
        - On a position set with insufficient price history. Inspect data_quality
          before presenting any figure.

    Args:
        positions (list[dict]): REQUIRED. Normally passed straight from
            get_portfolio_positions["positions"]. Each element must contain at minimum:
            symbol (str), quantity (float), market_value (float), asset_class (str).
            Extra keys are ignored. Weights are recomputed internally from
            market_value; do not pre-normalize.
        lookback (str): Return-series window. One of "1M", "3M", "6M", "1Y", "3Y",
            "5Y", "MAX". Default "1Y". Windows shorter than "3M" yield statistically
            unstable volatility and beta and MUST carry an explicit reliability caveat.
        benchmark_symbol (str | None): Index for beta, tracking error, and correlation,
            e.g. "XU100". Default None suppresses all relative metrics.
        metrics (list[str] | None): Subset selection. Allowed: "VOLATILITY",
            "MAX_DRAWDOWN", "VAR", "CVAR", "BETA", "SHARPE", "CONCENTRATION",
            "CORRELATION_MATRIX". Default None computes all except CORRELATION_MATRIX.
        confidence_level (float): Tail probability for VaR and CVaR. One of 0.90, 0.95,
            0.99. Default 0.95.
        risk_free_rate (float | None): Annualized decimal for Sharpe, e.g. 0.42 for
            42%. Default None sources the domestic policy rate and reports the resolved
            value in assumptions.
        rebalance_assumption (str): "BUY_AND_HOLD" or "DAILY_REBALANCE".
            Default "BUY_AND_HOLD". Shapes the synthetic portfolio return series.

    Returns:
        dict with exactly these top-level keys:

        as_of (str): ISO 8601 UTC timestamp of the last price bar included. All
            metrics are stated as of this instant.
        source (str): Price history provider, e.g. "BIST_EOD", "REFINITIV_TR".
        is_delayed (bool): True when the terminal bar is not final or settled. If True,
            figures MUST be labeled provisional.

        window (dict): start_date (str), end_date (str), observation_count (int),
            frequency (str, "DAILY" or "WEEKLY").

        metrics (dict): Only requested keys present.
            volatility_annualized (float): Annualized stdev of returns, as a fraction.
            downside_deviation_annualized (float): Fraction.
            max_drawdown (dict): value (float, negative fraction), peak_date (str),
                trough_date (str), recovery_date (str | None, None if not recovered),
                duration_days (int).
            var (dict): method (str, "HISTORICAL" or "PARAMETRIC"),
                confidence_level (float), horizon_days (int),
                value_fraction (float, negative), value_currency (float, negative).
            cvar (dict): Same shape as var. Expected shortfall beyond the threshold.
            beta (float | None): Versus benchmark_symbol. None when unspecified.
            correlation_to_benchmark (float | None): In [-1.0, 1.0].
            sharpe_ratio (float): Annualized, net of risk_free_rate.
            concentration (dict):
                hhi (float): Herfindahl-Hirschman Index on weights, in (0.0, 1.0].
                    Higher is more concentrated. 1.0 is a single holding.
                effective_n (float): 1 / hhi. The equivalent number of equally
                    weighted positions.
                top_1_weight, top_3_weight, top_5_weight (float): Fractions.
                largest_position (dict): symbol (str), weight (float).
                by_asset_class (dict[str, float]): Weight per asset class.
                by_sector (dict[str, float]): Weight per GICS-equivalent sector.
                    Unmapped instruments group under "UNCLASSIFIED".
                by_currency (dict[str, float]): Weight per instrument currency.
            correlation_matrix (dict | None): symbols (list[str]) and
                matrix (list[list[float]]), row-aligned to symbols.

        assumptions (dict): Echo of every parameter that materially shaped the result,
            including resolved risk_free_rate, rebalance_assumption, and annualization
            factor. MUST be disclosed when presenting Sharpe, VaR, or CVaR.

        data_quality (dict):
            coverage (float): Fraction of portfolio market value with usable history.
                Below 0.90, portfolio-level metrics MUST be presented as partial and
                the excluded symbols named.
            excluded_symbols (list[str]): Dropped for insufficient history, typically
                newly listed or illiquid instruments.
            gap_filled_days (int): Bars imputed by forward fill.
            is_statistically_reliable (bool): False when observation_count is below the
                minimum for the selected metrics. When False, figures MUST be framed as
                indicative only.

    Raises:
        InsufficientHistoryError: No symbol has enough history for the requested
            lookback. Do NOT silently fall back to a shorter window; tell the user the
            window was not computable.
        InvalidInputError: positions is empty or missing required keys.

    Constraints:
        - These are HISTORICAL measurements. Never present output as a prediction, an
          expected loss, or a probability of a future event. Parametric VaR in
          particular MUST be described as a model estimate under a distributional
          assumption, not as a bound on loss.
        - Do NOT convert a metric into a directive. "Your HHI is 0.41, indicating high
          concentration" is permitted. "Your HHI is 0.41, you should diversify" is
          prohibited.
        - Do NOT compare the user's metrics against an unstated "acceptable" threshold.
          This system holds no risk-tolerance profile and MUST NOT imply one.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    # Fail before the network call: an empty position set cannot produce a
    # meaningful metric, and the contract documents this as InvalidInputError
    # rather than an empty result.
    if not positions:
        raise InvalidInputError(f"{TOOL}: positions is empty.")

    # POST /risk/calculate. risk_free_rate is passed through as None when unset
    # so the backend resolves the policy rate and reports it in assumptions;
    # backend_client drops None keys, so the field is omitted rather than null.
    payload = await backend_client.request(
        "POST",
        "/risk/calculate",
        tool=TOOL,
        json_body={
            "positions": positions,
            "lookback": lookback,
            "benchmark_symbol": benchmark_symbol,
            "metrics": metrics,
            "confidence_level": confidence_level,
            "risk_free_rate": risk_free_rate,
            "rebalance_assumption": rebalance_assumption,
        },
    )
    return _normalize(payload, benchmark_symbol, metrics, lookback, rebalance_assumption)


def _normalize(
    payload: dict[str, Any],
    benchmark_symbol: Optional[str],
    metrics: Optional[list[str]],
    lookback: str,
    rebalance_assumption: str,
) -> dict[str, Any]:
    """Project the backend response onto the exact v2.1 payload."""
    freshness = backend_client.freshness(payload, TOOL)
    backend_client.require(payload, ("window", "metrics", "assumptions", "data_quality"), TOOL)

    computed = payload["metrics"]
    if not isinstance(computed, dict):
        raise ContractViolationError(f"{TOOL}: 'metrics' must be an object.")

    # Relative metrics are meaningless without a benchmark. If none was
    # requested, force them to None rather than trusting the backend not to
    # return a stale beta from a default index.
    if not benchmark_symbol:
        computed["beta"] = None
        computed["correlation_to_benchmark"] = None
    computed.setdefault("correlation_matrix", None)

    assumptions = dict(payload["assumptions"])
    assumptions.setdefault("lookback", lookback)
    assumptions.setdefault("benchmark_symbol", benchmark_symbol)
    assumptions.setdefault("requested_metrics", metrics)
    assumptions.setdefault("rebalance_assumption", rebalance_assumption)
    if "risk_free_rate" not in assumptions:
        # Sharpe is uninterpretable without the rate it was computed against,
        # and the contract requires this to be disclosed.
        raise ContractViolationError(
            f"{TOOL}: assumptions.risk_free_rate is missing; Sharpe cannot be disclosed."
        )

    return {
        **freshness,
        "window": payload["window"],
        "metrics": computed,
        "assumptions": assumptions,
        "data_quality": _normalize_quality(payload["data_quality"]),
    }


def _normalize_quality(raw: Any) -> dict[str, Any]:
    """Data quality block, defaulted conservatively.

    When the backend does not state reliability, assume it is NOT reliable.
    The optimistic default would let a three-observation window be presented
    as a firm volatility figure.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: 'data_quality' must be an object.")
    return {
        "coverage": float(raw.get("coverage", 0.0)),
        "excluded_symbols": list(raw.get("excluded_symbols") or []),
        "gap_filled_days": int(raw.get("gap_filled_days", 0)),
        "is_statistically_reliable": bool(raw.get("is_statistically_reliable", False)),
    }


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(calculate_portfolio_risk_metrics)
