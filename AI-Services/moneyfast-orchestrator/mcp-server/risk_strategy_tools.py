# filename: risk_strategy_tools.py
"""Risk and strategy domain tools.

MoneyFast MCP server, mock skeleton.
Contracts are frozen against "MCP Tools Interface Definitions v2.1".
All business logic is mocked; no network, database, or broker call is made.
Mock values are deterministic so orchestrator routing tests are reproducible.
"""

#from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

AS_OF = "2026-08-12T18:10:00Z"


def calculate_portfolio_risk_metrics(
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
    # MOCK: replace with the price-history client and the metric engine.
    # Real implementation must recompute weights from market_value and
    # inspect coverage before returning. The mock ignores positions.
    resolved_risk_free_rate = 0.4200 if risk_free_rate is None else risk_free_rate

    return {
        "as_of": AS_OF,
        "source": "BIST_EOD",
        "is_delayed": False,
        "window": {
            "start_date": "2025-08-13",
            "end_date": "2026-08-12",
            "observation_count": 249,
            "frequency": "DAILY",
        },
        "metrics": {
            "volatility_annualized": 0.3418,
            "downside_deviation_annualized": 0.2477,
            "max_drawdown": {
                "value": -0.2914,
                "peak_date": "2026-01-22",
                "trough_date": "2026-04-09",
                "recovery_date": None,
                "duration_days": 77,
            },
            "var": {
                "method": "HISTORICAL",
                "confidence_level": confidence_level,
                "horizon_days": 1,
                "value_fraction": -0.0331,
                "value_currency": -6406.34,
            },
            "cvar": {
                "method": "HISTORICAL",
                "confidence_level": confidence_level,
                "horizon_days": 1,
                "value_fraction": -0.0472,
                "value_currency": -9135.32,
            },
            "beta": 1.14 if benchmark_symbol else None,
            "correlation_to_benchmark": 0.81 if benchmark_symbol else None,
            "sharpe_ratio": 0.27,
            "concentration": {
                "hhi": 0.6288,
                "effective_n": 1.5903,
                "top_1_weight": 0.7537,
                "top_3_weight": 1.0000,
                "top_5_weight": 1.0000,
                "largest_position": {"symbol": "THYAO", "weight": 0.7537},
                "by_asset_class": {"EQUITY": 1.0000},
                "by_sector": {"INDUSTRIALS": 0.7537, "UNCLASSIFIED": 0.2463},
                "by_currency": {"TRY": 1.0000},
            },
            "correlation_matrix": None,
        },
        "assumptions": {
            "lookback": lookback,
            "risk_free_rate": resolved_risk_free_rate,
            "risk_free_rate_source": "DOMESTIC_POLICY_RATE",
            "rebalance_assumption": rebalance_assumption,
            "annualization_factor": 252,
            "benchmark_symbol": benchmark_symbol,
            "requested_metrics": metrics,
        },
        "data_quality": {
            "coverage": 1.0,
            "excluded_symbols": [],
            "gap_filled_days": 3,
            "is_statistically_reliable": True,
        },
    }


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(calculate_portfolio_risk_metrics)
