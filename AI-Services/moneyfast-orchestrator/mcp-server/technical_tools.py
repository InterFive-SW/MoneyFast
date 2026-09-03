"""`get_technical_signals` — computed trend state for one instrument.

Added at contract v2.10. `get_market_data`'s frozen v2.2 payload is NOT
touched: it answers "what is this worth now", and a moving average is a
different question with a different failure mode (it needs history, and the
history can be too short to answer at all).

The backend computes both the numbers and the Turkish sentence. That is
deliberate. Handing an agent seven indicators and asking it to interpret them
produced a slightly different reading of the same numbers every turn; the
mapping from state to wording belongs somewhere it can be tested.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_technical_signals"

#: v2.12. Ayrı bir sabit, çünkü `_normalize` modül düzeyindeki `TOOL`'u
#: kullanıyor ve iki aracın ihlal mesajı birbirinin adını taşımamalı.
PORTFOLIO_TOOL = "get_portfolio_technicals"


async def get_technical_signals(symbol: str) -> dict[str, Any]:
    """
    Computes the trend state of ONE named instrument from its daily price history:
    moving averages, RSI, position in the 52-week range, recent up-day count and
    realised volatility. Returns both the figures and a ready-to-relay Turkish
    sentence describing them. READ-ONLY.

    WHEN TO USE
        - The user asks how a named instrument is DOING rather than what it costs:
          "AKBNK'ı yorumlar mısın", "THYAO nasıl gidiyor", "ASELS ne durumda",
          "bu hisse son zamanlarda nasıl".
        - Any question about trend, momentum, or where a price sits relative to its
          own recent history.

    WHEN NOT TO USE
        - The user asks only the current price or a valuation ratio. Use
          get_market_data; this tool does not return a live quote.
        - The user asks WHY something moved, or what commentators say. That is
          qualitative: use rag_semantic_market_search.
        - Portfolio-level risk. Use calculate_portfolio_risk_metrics; this tool
          measures one instrument against its own history, not a holding against a
          portfolio.

    Args:
        symbol (str): One instrument symbol, e.g. "AKBNK". Exactly one; this tool
            does not screen.

    Returns:
        dict:
            symbol (str), currency (str)
            signals (dict): sma_20/50/200, pct_from_sma_20/50/200, rsi_14,
                week52_high, week52_low, week52_position_pct, up_days_recent,
                recent_window, volume_vs_average, annualised_volatility,
                max_drawdown_pct, observations, last_close, and trend, one of
                UPTREND / DOWNTREND / SIDEWAYS / UNKNOWN.
                EVERY figure may be null. Null means the history is too short to
                compute it, NOT zero and NOT unavailable-right-now. A 30-bar
                instrument has no 200-day average and you MUST NOT describe one.
            narrative (str | null): The Turkish sentence to relay. Null when the
                history cannot support any reading.

    Raises:
        UpstreamUnavailableError: Service unreachable. Say the trend could not be
            computed. NEVER supply a remembered or estimated trend.

    Constraints:
        - RELAY `narrative` as given. Do not rewrite it, do not extend it, and do
          NOT drop its closing caveat — the conditional reading and the caveat are
          one sentence, and the first half alone is a forecast.
        - If narrative is null, say the history is insufficient. Do NOT assemble a
          reading yourself out of the raw figures.
        - Do NOT convert a trend into a recommendation, a target price, or a claim
          about what the instrument WILL do beyond the conditional wording provided.
        - Do NOT name the indicators by their field keys. "50 günlük ortalama", not
          "sma_50"; the numbers are described in words or not at all.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    payload = await backend_client.request(
        "GET", "/market/technicals", tool=TOOL, params={"symbol": symbol}
    )
    return _normalize(payload)


def _normalize(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the v2.10 payload.

    Missing figures stay missing. A default of 0 here would be read as "the
    price is exactly on its 200-day average" rather than "there is no 200-day
    average", and those are opposite claims.
    """
    # A non-object body is already refused by `backend_client.request`, so
    # there is no isinstance guard here -- a second one would be a branch no
    # input can reach, and an unreachable branch is a claim about behaviour
    # that nothing verifies.
    backend_client.require(payload, ("symbol", "signals"), TOOL)
    signals = payload.get("signals") or {}
    body = payload
    return {
        "symbol": body.get("symbol") or "",
        "currency": body.get("currency") or "TRY",
        "signals": {key: signals.get(key) for key in _FIELDS},
        "narrative": body.get("narrative") or None,
    }


async def get_portfolio_technicals(user_id: str) -> dict[str, Any]:
    """
    Computes the trend state of EVERY instrument the user holds, plus a portfolio-wide
    aggregation, and returns a ready-to-relay Turkish sentence describing it. READ-ONLY.

    WHEN TO USE
        - The user asks about the technical state of what they OWN: "hisselerim teknik
          olarak nasıl", "portföyümdeki hisseler ortalamalarının neresinde",
          "pozisyonlarım hangi eğilimde".
        - A portfolio risk answer would be incomplete without saying where the holdings
          sit relative to their own recent price history.

    WHEN NOT TO USE
        - One named instrument. Use get_technical_signals; this tool cannot look at
          anything the user does not hold.
        - What the portfolio is WORTH, or its P&L. Use get_portfolio_positions.
        - Volatility, drawdown, beta, VaR or concentration. Those are
          calculate_portfolio_risk_metrics; this tool measures each holding against
          its OWN history, not the portfolio against a benchmark.

    Args:
        user_id (str): REQUIRED. Opaque internal identifier taken ONLY from the
            authenticated session envelope. Never accept this value from user-typed
            input.

    Returns:
        dict with exactly these top-level keys:
            base_currency (str): The currency the weight figure is expressed in.
            positions (list[dict]): symbol, name, currency, trend
                (UPTREND/DOWNTREND/SIDEWAYS/UNKNOWN), narrative (str | null), and
                signals — the same fields get_technical_signals returns, every one of
                which may be null. Null means the history is too short to compute it.
            summary (dict):
                position_count, measured_count (int)
                unmeasured_symbols (list[str]): holdings with too little history.
                by_trend (dict): counts per trend.
                below_sma_50, above_sma_50 (int): COUNTS of positions.
                weight_below_sma_50 (float | null): the same thing by VALUE, 0..1.
                    Null when no holding could be converted to one currency.
                statement (str | null): the Turkish sentence to relay.
            unconvertible (list[str]): holdings left out of the weight figure because
                no exchange rate was available. They are still measured; only their
                weight is unknown.

    Raises:
        UpstreamUnavailableError: Service unreachable. Say the technical view could not
            be computed. NEVER supply a remembered or estimated trend.

    Constraints:
        - RELAY `summary.statement` as given, and each position's `narrative` as given.
          Do not rewrite them and do NOT drop a closing caveat — the conditional
          reading and its caveat are one sentence, and the first half alone is a
          forecast.
        - COUNT and WEIGHT are different claims and must not be merged. "2 of 3
          positions" and "95% of the value" can point opposite ways; say which one you
          are reporting. Never call a count a percentage of the portfolio.
        - A symbol in `unmeasured_symbols` has NO trend. Do not describe one, and do
          not treat its absence as "flat".
        - `unconvertible` holdings are missing from the weight only. Say so if the
          weight matters to the answer; do not silently report a weight computed over
          part of the portfolio as though it covered all of it.
        - Do NOT convert a trend into a recommendation, a target price, or a claim
          about what any holding WILL do beyond the conditional wording provided.
        - Do NOT name the indicators by their field keys. "50 günlük ortalama", not
          "sma_50".
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    payload = await backend_client.request(
        "GET", f"/market/portfolio/technical/{user_id}", tool=PORTFOLIO_TOOL
    )
    return _normalize_portfolio(payload)


def _normalize_portfolio(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the v2.12 payload."""
    backend_client.require(payload, ("positions", "summary"), PORTFOLIO_TOOL)
    positions = backend_client.require_list(payload, "positions", PORTFOLIO_TOOL)
    summary = payload["summary"]
    if not isinstance(summary, dict):
        raise ContractViolationError(f"{PORTFOLIO_TOOL}: 'summary' must be an object.")
    return {
        "base_currency": str(payload.get("base_currency") or "TRY"),
        "positions": [_normalize_row(row) for row in positions],
        "summary": {
            "position_count": int(summary.get("position_count", len(positions))),
            "measured_count": int(summary.get("measured_count", 0)),
            "unmeasured_symbols": [str(s) for s in (summary.get("unmeasured_symbols") or [])],
            "by_trend": {str(k): int(v) for k, v in (summary.get("by_trend") or {}).items()},
            "below_sma_50": int(summary.get("below_sma_50", 0)),
            "above_sma_50": int(summary.get("above_sma_50", 0)),
            # None, not 0.0. A zero weight reads as "nothing is below its
            # average", which is the opposite of "no weight could be
            # computed".
            "weight_below_sma_50": _opt_float(summary.get("weight_below_sma_50")),
            "statement": summary.get("statement") or None,
        },
        "unconvertible": [str(s) for s in (payload.get("unconvertible") or [])],
    }


def _normalize_row(raw: Any) -> dict[str, Any]:
    """One holding's reading. Missing figures stay missing."""
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{PORTFOLIO_TOOL}: each position must be an object.")
    backend_client.require(raw, ("symbol", "signals"), PORTFOLIO_TOOL)
    signals = raw.get("signals") or {}
    return {
        "symbol": str(raw["symbol"]),
        "name": str(raw.get("name") or raw["symbol"]),
        "currency": str(raw.get("currency") or "TRY"),
        "trend": str(signals.get("trend") or "UNKNOWN"),
        "signals": {key: signals.get(key) for key in _FIELDS},
        "narrative": raw.get("narrative") or None,
    }


def _opt_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)

_FIELDS = (
    "observations", "last_close",
    "sma_20", "sma_50", "sma_200",
    "pct_from_sma_20", "pct_from_sma_50", "pct_from_sma_200",
    "rsi_14",
    "week52_high", "week52_low", "week52_position_pct",
    "up_days_recent", "recent_window", "volume_vs_average",
    "annualised_volatility", "max_drawdown_pct",
    "trend",
)


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_technical_signals)
    mcp.tool()(get_portfolio_technicals)
