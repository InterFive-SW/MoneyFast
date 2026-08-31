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

from typing import Any, TYPE_CHECKING

import backend_client

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_technical_signals"


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
