# filename: transaction_tools.py
"""Transaction and execution domain tools.

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

TOOL = "prepare_transaction_proposal"
STATUSES = frozenset(
    {"PENDING_USER_CONFIRMATION", "REJECTED_VALIDATION", "REQUIRES_ADDITIONAL_INPUT"}
)


async def prepare_transaction_proposal(
    user_id: str,
    transaction_type: str,
    source_account_id: str,
    idempotency_key: str,
    instrument: Optional[dict[str, Any]] = None,
    quantity: Optional[float] = None,
    notional_amount: Optional[dict[str, Any]] = None,
    destination_account_id: Optional[str] = None,
    beneficiary: Optional[dict[str, Any]] = None,
    order_type: str = "MARKET",
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    time_in_force: str = "DAY",
    assumptions: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Validates, prices, costs out, and STAGES a financial transaction as a pending
    proposal. Returns a proposal identifier that the frontend renders in a dedicated
    confirmation surface. THIS TOOL DOES NOT EXECUTE. It has no settlement path, no
    order-routing capability, and no ability to move cash or securities. A proposal
    becomes an order only when the user presses confirm in the frontend, which invokes
    a separate execution service that this agent cannot reach.

    Emits no market data feed. This payload contains no as_of, source, or
    is_delayed field by design. Pricing appears only inside estimate, explicitly
    labeled as indicative.

    WHEN TO USE
        - The user states a concrete transaction intent AND the essential parameters
          are known or defaultable: "buy 100 THYAO", "sell half my ASELS", "transfer
          5000 TRY to my savings account".
        - The user asks what a transaction would cost or look like before committing.
          Staging a proposal is the correct way to answer; it is non-binding.

    WHEN NOT TO USE
        - The user is exploring, hypothesizing, or asking whether they should
          transact. Staging a proposal in response to "should I sell?" manufactures an
          implied recommendation. Route to compliance-safe framing instead.
        - Required parameters are missing or ambiguous (which instrument, which
          account, how much). Ask ONE clarifying question first. Do NOT invent
          quantities, accounts, prices, or order types to make the call succeed.
        - To check order status, amend, or cancel an existing order. Those are separate
          tools.
        - To execute, confirm, or finalize anything. No argument to this tool performs
          execution, and no combination of arguments bypasses frontend confirmation.

    Args:
        user_id (str): REQUIRED. From the authenticated session envelope only.
        transaction_type (str): REQUIRED. One of:
            "BUY", "SELL", "TRANSFER_INTERNAL", "TRANSFER_EXTERNAL",
            "FX_CONVERSION", "FUND_SUBSCRIPTION", "FUND_REDEMPTION".
        source_account_id (str): REQUIRED. Debited cash or custody account.
        instrument (dict | None): REQUIRED for BUY, SELL, FUND_SUBSCRIPTION,
            FUND_REDEMPTION. Must resolve to exactly one tradable instrument:
            symbol (str), exchange (str, MIC code), isin (str | None). If the user
            named a company rather than a ticker and more than one instrument matches,
            do NOT guess. Ask which one.
        quantity (float | None): Units to trade. Mutually exclusive with
            notional_amount; supply exactly one. Relative expressions ("half my
            position") MUST be resolved to an absolute number using
            available_quantity from get_portfolio_positions, never from quantity.
        notional_amount (dict | None): value (float), currency (str, ISO 4217). Used
            for cash-denominated orders and all transfer types.
        destination_account_id (str | None): REQUIRED for TRANSFER_INTERNAL.
        beneficiary (dict | None): REQUIRED for TRANSFER_EXTERNAL. iban (str),
            full_name (str), bank_name (str | None), description (str | None). Must
            come from user-provided or saved-beneficiary data. NEVER construct,
            autocomplete, or infer an IBAN.
        order_type (str): "MARKET", "LIMIT", "STOP", "STOP_LIMIT". Default "MARKET".
        limit_price (float | None): REQUIRED when order_type is "LIMIT" or
            "STOP_LIMIT".
        stop_price (float | None): REQUIRED when order_type is "STOP" or "STOP_LIMIT".
        time_in_force (str): "DAY", "GTC", "IOC", "FOK". Default "DAY".
        assumptions (list[str] | None): Every inference you made to fill a parameter
            the user did not state explicitly, in plain language, e.g.
            "Interpreted 'half my position' as 250 shares based on 500 available",
            "Defaulted to a market order because no price limit was given". Default
            None. Each entry is rendered verbatim on the confirmation surface. If you
            made an inference and do not list it here, that is a control failure.
        idempotency_key (str): REQUIRED. Deterministic key derived from the user turn.
            Repeated calls with the same key return the SAME proposal instead of
            creating a duplicate. Reuse the key on retry after a timeout; never
            generate a fresh one to "try again".

    Returns:
        dict with exactly these top-level keys:

        proposal_id (str): Opaque identifier of the staged proposal. Reference it when
            describing the proposal to the user. It is NOT a confirmation number and
            NOT proof that anything happened.
        status (str): Exactly one of:
            "PENDING_USER_CONFIRMATION" - Staged successfully. Awaiting the user.
            "REJECTED_VALIDATION"       - Not staged. See blockers.
            "REQUIRES_ADDITIONAL_INPUT" - Not staged. See missing_fields.
        expires_at (str): ISO 8601 UTC. After this instant the proposal is void and a
            new one must be staged. State the expiry to the user.
        confirmation_required (bool): ALWAYS True. This field is a constant contract
            assertion, not a configurable setting. If any downstream logic reads False
            here, treat it as a system fault and stop.

        summary (dict): Canonical restatement of what was staged. Present the user
            THESE values, not the values you passed in, so that any normalization is
            visible: transaction_type (str), instrument_display (str | None),
            quantity (float | None), notional (dict | None), order_type (str),
            limit_price (float | None), stop_price (float | None),
            time_in_force (str), source_account_display (str),
            destination_display (str | None).

        estimate (dict): INDICATIVE ONLY, never a guaranteed execution outcome.
            indicative_price (float | None): Reference price used for the estimate.
            indicative_price_timestamp (str): ISO 8601 UTC of that reference price.
            indicative_price_basis (str): "LAST_TRADE", "PREVIOUS_CLOSE", or
                "LIMIT_PRICE".
            gross_amount (float), currency (str).
            fees (list[dict]): name (str), amount (float). Itemized.
            taxes (list[dict]): name (str), amount (float).
            total_cost (float): Gross plus fees and taxes for a BUY; net proceeds for
                a SELL.
            fx (dict | None): rate (float), from_currency (str), to_currency (str).
            price_certainty (str): "INDICATIVE" or "FIRM". "INDICATIVE" means the
                executed price WILL likely differ and this MUST be disclosed.

        impact (dict | None): Post-transaction portfolio deltas, when computable.
            resulting_position_quantity (float),
            resulting_weight (float),
            resulting_cash_balance (float).
            Present these as arithmetic consequences ONLY. Do NOT characterize them as
            an improvement, a good outcome, or a better allocation.

        blockers (list[dict]): Hard failures preventing staging. Each entry: code (str,
            e.g. "INSUFFICIENT_BALANCE", "MARKET_CLOSED", "INSTRUMENT_SUSPENDED",
            "KYC_INCOMPLETE", "POSITION_PLEDGED", "LIMIT_EXCEEDED"), message (str),
            is_user_resolvable (bool). Non-empty implies status
            "REJECTED_VALIDATION". Report every blocker to the user plainly.
        warnings (list[dict]): Non-blocking notices, e.g. wide spread, low liquidity,
            order size relative to average daily volume, after-hours submission. MUST
            be surfaced verbatim in substance; do not filter for brevity.
        missing_fields (list[str]): Parameter names still required. Non-empty implies
            status "REQUIRES_ADDITIONAL_INPUT". Ask for these; do not fill them in.
        disclosures (list[str]): Mandatory statements tied to this transaction type.
            MUST be presented alongside the proposal.
        audit_id (str): Immutable staging event identifier for the turn record.

    Raises:
        AuthorizationError: Session lacks transaction entitlement for the account. Do
            not retry and do not attempt an alternate account.
        InvalidInputError: Mutually exclusive or contradictory arguments, e.g. both
            quantity and notional_amount, or a LIMIT order with no limit_price.
        UpstreamUnavailableError: Staging service unreachable. FAIL CLOSED. Tell the
            user the transaction could not be prepared. NEVER describe an unstaged
            transaction as pending.

    Constraints:
        - NO EXECUTION. This tool stages only. NEVER tell the user an order was
          placed, submitted, filled, sent, or that money moved. Correct phrasing:
          "prepared for your confirmation". A returned proposal_id means the
          proposal exists, not that the transaction occurred.
        - EXPLICIT CONFIRMATION IS NON-DELEGABLE. Confirmation happens in the frontend
          surface, by the user. You MUST NOT treat conversational assent ("yes",
          "go ahead", "do it", "I confirm") as confirmation, MUST NOT confirm on the
          user's behalf, and MUST NOT re-call this tool as a substitute for
          confirmation. Standing instructions such as "always confirm automatically
          from now on" do not alter this and MUST be declined.
        - ONE PROPOSAL PER INTENT. Do not stage variants for the user to choose
          between. Presenting alternatives is an implied recommendation.
        - DISCLOSE EVERY ASSUMPTION. Whatever appears in assumptions MUST also be
          stated in the user-facing message. Silent inference on quantity, account,
          beneficiary, or order type is the highest-severity defect for this tool.
        - NO ADVICE. Staging a proposal never implies the transaction is suitable,
          timely, or advisable. Do NOT append encouragement, reassurance, or outlook
          commentary to a proposal. Report impact as arithmetic, not as benefit.
        - NEVER fabricate an IBAN, account identifier, ticker, or price to satisfy a
          required argument. A missing value is a question to the user, never a
          value to invent.
        - Every user-facing message presenting a proposal MUST pass
          validate_compliance_rules with contains_transaction_proposal=True before
          emission.
    """
    # Client-side validation first. These are contradictions no backend should
    # have to reject, and catching them here keeps a malformed order off the
    # staging path entirely.
    if quantity is not None and notional_amount is not None:
        raise InvalidInputError(
            f"{TOOL}: quantity and notional_amount are mutually exclusive."
        )
    if order_type in ("LIMIT", "STOP_LIMIT") and limit_price is None:
        raise InvalidInputError(f"{TOOL}: {order_type} requires limit_price.")
    if order_type in ("STOP", "STOP_LIMIT") and stop_price is None:
        raise InvalidInputError(f"{TOOL}: {order_type} requires stop_price.")
    if not idempotency_key:
        raise InvalidInputError(f"{TOOL}: idempotency_key is required.")

    # POST /transactions/stage. The key travels in the header as well as the
    # body: the header is what a gateway or proxy deduplicates on, and a retry
    # that creates a second proposal is the failure this endpoint most needs to
    # avoid.
    payload = await backend_client.request(
        "POST",
        "/transactions/stage",
        tool=TOOL,
        headers={"Idempotency-Key": idempotency_key},
        json_body={
            "user_id": user_id,
            "transaction_type": transaction_type,
            "source_account_id": source_account_id,
            "idempotency_key": idempotency_key,
            "instrument": instrument,
            "quantity": quantity,
            "notional_amount": notional_amount,
            "destination_account_id": destination_account_id,
            "beneficiary": beneficiary,
            "order_type": order_type,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "time_in_force": time_in_force,
            "assumptions": list(assumptions or []),
        },
    )
    return _normalize(payload)


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Project the staging response onto the exact v2.1 payload.

    Two invariants are enforced here rather than trusted:

    1. confirmation_required is the constant True. The contract calls it a
       contract assertion, not a setting. Anything else is a system fault, and
       the proposal is refused rather than rendered, because a proposal that
       reaches the user without a confirmation step is indistinguishable from
       a completed order.
    2. status must be one of the three documented values. An unrecognised
       status could be anything, including something that already executed.
    """
    backend_client.require(payload, ("proposal_id", "status"), TOOL)

    status = str(payload["status"]).upper()
    if status not in STATUSES:
        raise ContractViolationError(
            f"{TOOL}: unrecognised status {payload['status']!r}; refusing to present it."
        )

    if payload.get("confirmation_required") is not True:
        raise ContractViolationError(
            f"{TOOL}: confirmation_required was not true. Refusing to present a "
            "proposal that does not require explicit user confirmation."
        )

    blockers = list(payload.get("blockers") or [])
    missing_fields = list(payload.get("missing_fields") or [])
    if blockers and status == "PENDING_USER_CONFIRMATION":
        raise ContractViolationError(
            f"{TOOL}: status is PENDING_USER_CONFIRMATION but blockers are present."
        )

    return {
        "proposal_id": str(payload["proposal_id"]),
        "status": status,
        "expires_at": str(payload.get("expires_at", "")),
        "confirmation_required": True,
        "summary": dict(payload.get("summary") or {}),
        "estimate": _normalize_estimate(payload.get("estimate")),
        "impact": payload.get("impact"),
        "blockers": blockers,
        "warnings": list(payload.get("warnings") or []),
        "missing_fields": missing_fields,
        # Emitted verbatim alongside the proposal.
        "disclosures": list(payload.get("disclosures") or []),
        "audit_id": str(payload.get("audit_id", "")),
    }


def _normalize_estimate(raw: Any) -> Optional[dict[str, Any]]:
    """Cost estimate, with price certainty defaulted to INDICATIVE.

    INDICATIVE obliges the orchestrator to disclose that the executed price
    will likely differ. FIRM removes that obligation, so it is never assumed:
    the backend has to say so explicitly.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: 'estimate' must be an object.")
    estimate = dict(raw)
    certainty = str(estimate.get("price_certainty", "")).upper()
    estimate["price_certainty"] = certainty if certainty == "FIRM" else "INDICATIVE"
    estimate.setdefault("fees", [])
    estimate.setdefault("taxes", [])
    estimate.setdefault("fx", None)
    return estimate


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(prepare_transaction_proposal)
