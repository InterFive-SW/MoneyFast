# filename: portfolio_tools.py
"""Portfolio domain tools.

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

TOOL = "get_portfolio_positions"


async def get_portfolio_positions(
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
    # GET /portfolio/{user_id}. List parameters are sent as repeated keys
    # (account_ids=a&account_ids=b); httpx renders bools as true/false.
    payload = await backend_client.request(
        "GET",
        f"/portfolio/{user_id}",
        tool=TOOL,
        params={
            "account_ids": account_ids,
            "asset_classes": asset_classes,
            "include_closed": include_closed,
            "base_currency": base_currency,
            "valuation_mode": valuation_mode,
        },
    )
    return _normalize(payload, base_currency)


def _normalize(payload: dict[str, Any], requested_currency: str) -> dict[str, Any]:
    """Project the backend response onto the exact v2.1 payload.

    Extra backend fields are dropped rather than passed through: the contract
    promises an exact key set, and an unexpected key is a figure the model has
    no instructions for.
    """
    freshness = backend_client.freshness(payload, TOOL)
    positions = backend_client.require_list(payload, "positions", TOOL)
    backend_client.require(payload, ("totals",), TOOL)

    delay_minutes = payload.get("delay_minutes")
    if delay_minutes is None:
        # Only inferable in the not-delayed direction. A delayed feed that does
        # not state its lag cannot have one guessed for it.
        if freshness["is_delayed"]:
            raise ContractViolationError(
                f"{TOOL}: is_delayed is true but delay_minutes is absent."
            )
        delay_minutes = 0

    totals = payload["totals"]
    if not isinstance(totals, dict):
        raise ContractViolationError(f"{TOOL}: 'totals' must be an object.")

    return {
        **freshness,
        "delay_minutes": int(delay_minutes),
        # Echo what the caller asked for, not what the backend echoed back: the
        # contract defines this field as the requested normalization currency.
        "base_currency": payload.get("base_currency", requested_currency),
        "positions": [_normalize_position(p) for p in positions],
        "totals": {
            "total_market_value": _num(totals, "total_market_value"),
            "total_cost_basis": _num(totals, "total_cost_basis"),
            "total_unrealized_pnl": _num(totals, "total_unrealized_pnl"),
            "position_count": int(totals.get("position_count", len(positions))),
        },
        "warnings": list(payload.get("warnings") or []),
    }


def _normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    """One position, with every documented key present.

    Numeric fields are required: defaulting a missing quantity or avg_cost to
    zero would render as a real holding worth nothing, which is worse than an
    error. available_quantity is the one exception, because a backend that
    does not model settlement holds means the whole position is sellable.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each position must be an object.")
    backend_client.require(
        raw,
        ("symbol", "quantity", "avg_cost", "last_price", "market_value", "cost_basis"),
        TOOL,
    )
    quantity = float(raw["quantity"])
    return {
        "symbol": str(raw["symbol"]),
        "isin": raw.get("isin"),
        "name": str(raw.get("name", raw["symbol"])),
        "asset_class": str(raw.get("asset_class", "EQUITY")),
        "exchange": str(raw.get("exchange", "XIST")),
        "quantity": quantity,
        "avg_cost": float(raw["avg_cost"]),
        "instrument_currency": str(raw.get("instrument_currency", "TRY")),
        "last_price": float(raw["last_price"]),
        "market_value": float(raw["market_value"]),
        "cost_basis": float(raw["cost_basis"]),
        "unrealized_pnl": float(raw["market_value"]) - float(raw["cost_basis"]),
        "unrealized_pnl_pct": _pnl_pct(raw),
        "weight": float(raw.get("weight", 0.0)),
        "available_quantity": float(raw.get("available_quantity", quantity)),
        "opened_at": str(raw.get("opened_at", "")),
    }


def _pnl_pct(raw: dict[str, Any]) -> float:
    """P&L as a fraction of cost basis, guarding the zero-cost case.

    A fully written-down or gifted position has cost_basis 0. Returning 0.0
    beats propagating inf into a table the user reads.
    """
    cost_basis = float(raw["cost_basis"])
    if cost_basis == 0:
        return 0.0
    return (float(raw["market_value"]) - cost_basis) / cost_basis


def _num(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key)
    if value is None:
        raise ContractViolationError(f"{TOOL}: totals.{key} is missing.")
    return float(value)


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_portfolio_positions)
