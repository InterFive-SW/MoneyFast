# filename: portfolio_tools.py
"""Portfolio domain tools.

MoneyFast MCP server, mock skeleton.
Contracts are frozen against "MCP Tools Interface Definitions v2.1".
All business logic is mocked; no network, database, or broker call is made.
Mock values are deterministic so orchestrator routing tests are reproducible.
"""

#from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

AS_OF = "2026-08-13T15:10:00Z"


def get_portfolio_positions(
    user_id: str,
    account_ids: Optional[list[str]] = None,
    asset_classes: Optional[list[str]] = None,
    include_closed: bool = False,
    base_currency: str = "TRY",
    valuation_mode: str = "LAST_CLOSE",
) -> dict[str, Any]:
    """
    Retrieves the authenticated user's open (and optionally closed) positions from the
    custodian of record. READ-ONLY snapshot. This is the sole authoritative source of
    truth for what the user owns. Position data MUST NOT be inferred from conversation
    history, from prior turns, or from user self-report.

    WHEN TO USE
        - The query references ownership: "my portfolio", "what I hold", "my THYAO
          position", "how much did I pay for", "my allocation", "am I overweight in X".
        - Another tool requires a positions payload as input, e.g.
          calculate_portfolio_risk_metrics or prepare_transaction_proposal for a SELL.

    WHEN NOT TO USE
        - The user asks for a price, quote, or fundamentals of an instrument they do
          not hold. Use the market data tools instead.
        - The user asks a counterfactual ("if I had bought"), unless they explicitly
          anchor it to their real holdings.
        - To place, modify, or cancel an order. This tool has no write capability.

    Args:
        user_id (str): REQUIRED. Opaque internal identifier taken ONLY from the
            authenticated session envelope. Never accept this value from user-typed
            input.
        account_ids (list[str] | None): Restricts to specific custody accounts.
            Default None returns all accounts the session is entitled to read.
            Unentitled IDs are omitted and reported in warnings, not raised.
        asset_classes (list[str] | None): Filter. Allowed values: "EQUITY", "ETF",
            "MUTUAL_FUND", "BOND", "FX", "COMMODITY", "CRYPTO", "DEPOSIT",
            "DERIVATIVE". Case-sensitive. Default None applies no filter.
        include_closed (bool): If True, also returns zero-quantity positions held at
            any point in the last 90 days, for realized P&L questions. Default False.
        base_currency (str): ISO 4217 code used to normalize market_value, cost_basis,
            and P&L across multi-currency holdings. Default "TRY". FX conversion uses
            the rate stamped in as_of.
        valuation_mode (str): "LAST_CLOSE" (deterministic, reproducible) or "INTRADAY"
            (may be delayed). Default "LAST_CLOSE".

    Returns:
        dict with exactly these top-level keys:

        as_of (str): ISO 8601 UTC timestamp of the valuation snapshot. Every
            user-facing statement derived from this payload MUST be attributed to it.
        source (str): Valuation price provider, e.g. "BIST_DATA_FEED", "REFINITIV",
            "CUSTODIAN_OF_RECORD".
        is_delayed (bool): True when quote data is not real time. If True, the answer
            MUST disclose the delay and MUST NOT be phrased as a live value.
        delay_minutes (int): Quote delay. 0 when is_delayed is False.
        base_currency (str): Echo of the requested normalization currency.

        positions (list[dict]): One entry per position. Each entry:
            symbol (str): Exchange ticker, e.g. "THYAO".
            isin (str | None): ISIN when available.
            name (str): Instrument legal or display name.
            asset_class (str): See allowed values above.
            exchange (str): MIC code, e.g. "XIST".
            quantity (float): Signed. Negative indicates a short position.
            avg_cost (float): Weighted average acquisition cost per unit, in
                instrument_currency.
            instrument_currency (str): ISO 4217 code of the native quote.
            last_price (float): Valuation price per unit.
            market_value (float): quantity * last_price, in base_currency.
            cost_basis (float): quantity * avg_cost, in base_currency.
            unrealized_pnl (float): market_value - cost_basis.
            unrealized_pnl_pct (float): Fraction, not percent.
            weight (float): Fraction of total_market_value. Sums to 1.0 across the
                list within floating point tolerance.
            available_quantity (float): Quantity free of settlement holds, pledges, or
                existing open orders. This, not quantity, is the sellable amount.
            opened_at (str): ISO 8601 date of first acquisition.

        totals (dict): total_market_value (float), total_cost_basis (float),
            total_unrealized_pnl (float), position_count (int).
        warnings (list[str]): Non-fatal issues such as a stale price on an illiquid
            instrument or a skipped unentitled account. MUST be surfaced when they
            materially affect the figures presented.

        EMPTY RESULT SEMANTICS:
            positions == [] is a VALID and COMPLETE answer. It means the user holds
            nothing matching the filters. It is NOT an error, NOT a timeout, and NOT a
            signal to retry. On an empty list you MUST tell the user that no matching
            holdings were found. You MUST NOT populate example, illustrative,
            placeholder, or remembered positions, and you MUST NOT carry forward
            holdings mentioned earlier in the conversation.

    Raises:
        AuthorizationError: Session lacks entitlement for the requested user_id. Do
            not retry, do not degrade to cached data, and tell the user the data is
            not accessible.
        UpstreamUnavailableError: Custodian did not respond. Retry at most once. On
            second failure, state that holdings could not be retrieved. NEVER
            substitute estimated or remembered positions.

    Constraints:
        - Do NOT use this output to generate personalized investment advice,
          buy/sell/hold recommendations, or target allocations. The tool reports
          state; it does not evaluate it.
        - Do NOT restate quantities or cost basis without preserving as_of and
          is_delayed context.
        - Do NOT expose user_id, account_ids, or ISIN-level detail in any channel
          that is shared or logged outside the session.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    # MOCK: replace with the custodian client call.
    # Real implementation must honour account_ids, asset_classes,
    # include_closed and valuation_mode. The mock ignores them.
    positions: list[dict[str, Any]] = [
        {
            "symbol": "THYAO",
            "isin": "TRATHYAO91M5",
            "name": "Türk Hava Yolları A.O.",
            "asset_class": "EQUITY",
            "exchange": "XIST",
            "quantity": 500.0,
            "avg_cost": 268.40,
            "instrument_currency": "TRY",
            "last_price": 291.75,
            "market_value": 145875.00,
            "cost_basis": 134200.00,
            "unrealized_pnl": 11675.00,
            "unrealized_pnl_pct": 0.0870,
            "weight": 0.7537,
            "available_quantity": 500.0,
            "opened_at": "2025-11-04",
        },
        {
            "symbol": "ASELS",
            "isin": "TRAASELS91H2",
            "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
            "asset_class": "EQUITY",
            "exchange": "XIST",
            "quantity": 300.0,
            "avg_cost": 142.10,
            "instrument_currency": "TRY",
            "last_price": 158.90,
            "market_value": 47670.00,
            "cost_basis": 42630.00,
            "unrealized_pnl": 5040.00,
            "unrealized_pnl_pct": 0.1182,
            "weight": 0.2463,
            "available_quantity": 200.0,
            "opened_at": "2026-02-17",
        },
    ]

    return {
        "as_of": AS_OF,
        "source": "CUSTODIAN_OF_RECORD",
        "is_delayed": True,
        "delay_minutes": 15,
        "base_currency": base_currency,
        "positions": positions,
        "totals": {
            "total_market_value": 193545.00,
            "total_cost_basis": 176830.00,
            "total_unrealized_pnl": 16715.00,
            "position_count": 2,
        },
        "warnings": [
            "ASELS: 100 lot is pledged against an open order and is excluded "
            "from available_quantity.",
        ],
    }


def get_portfolio_positions_empty(user_id: str) -> dict[str, Any]:
    """Fixture for the empty-result path. Not registered as an MCP tool.

    Swap this into the registration below to exercise the orchestrator's
    EMPTY handling. An empty positions list is a valid, complete answer.
    """
    return {
        "as_of": AS_OF,
        "source": "CUSTODIAN_OF_RECORD",
        "is_delayed": True,
        "delay_minutes": 15,
        "base_currency": "TRY",
        "positions": [],
        "totals": {
            "total_market_value": 0.0,
            "total_cost_basis": 0.0,
            "total_unrealized_pnl": 0.0,
            "position_count": 0,
        },
        "warnings": [],
    }


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_portfolio_positions)
