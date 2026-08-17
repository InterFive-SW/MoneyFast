# filename: transaction_tools.py
"""Transaction and execution domain tools.

MoneyFast MCP server, mock skeleton.
Contracts are frozen against "MCP Tools Interface Definitions v2.1".
All business logic is mocked; no network, database, or broker call is made.
Mock values are deterministic so orchestrator routing tests are reproducible.
"""

#from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP



def prepare_transaction_proposal(
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
    # MOCK: replace with the staging service client.
    # This mock stages nothing. It NEVER executes, and no future revision of
    # this module may add an execution path: settlement lives behind the
    # frontend confirmation control, in a separate service.
    symbol = (instrument or {}).get("symbol", "THYAO")
    qty = quantity if quantity is not None else 100.0
    price = limit_price if limit_price is not None else 291.75
    gross = round(qty * price, 2)
    commission = round(gross * 0.001, 2)
    bsmv = round(commission * 0.05, 2)

    return {
        "proposal_id": "prp_8d31f04c",
        "status": "PENDING_USER_CONFIRMATION",
        "expires_at": "2026-08-13T15:25:00Z",
        "confirmation_required": True,
        "summary": {
            "transaction_type": transaction_type,
            "instrument_display": f"{symbol} (XIST)",
            "quantity": qty,
            "notional": notional_amount,
            "order_type": order_type,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "time_in_force": time_in_force,
            "source_account_display": f"Yatırım Hesabı {source_account_id[-4:]}",
            "destination_display": None,
        },
        "estimate": {
            "indicative_price": price,
            "indicative_price_timestamp": "2026-08-13T15:09:45Z",
            "indicative_price_basis": (
                "LIMIT_PRICE" if limit_price is not None else "LAST_TRADE"
            ),
            "gross_amount": gross,
            "currency": "TRY",
            "fees": [{"name": "Aracı kurum komisyonu", "amount": commission}],
            "taxes": [{"name": "BSMV", "amount": bsmv}],
            "total_cost": round(gross + commission + bsmv, 2),
            "fx": None,
            "price_certainty": "INDICATIVE",
        },
        "impact": {
            "resulting_position_quantity": 600.0,
            "resulting_weight": 0.7891,
            "resulting_cash_balance": 12344.36,
        },
        "blockers": [],
        "warnings": [
            {
                "code": "WIDE_SPREAD",
                "message": "Spread is wider than the 20-day average for this instrument.",
            }
        ],
        "missing_fields": [],
        "disclosures": [
            "Emir, ekrandaki onay adımı tamamlanmadan iletilmez.",
            "Gösterilen fiyat göstergeseldir; gerçekleşen fiyat farklı olabilir.",
        ],
        "audit_id": "aud_7a20be31",
    }


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(prepare_transaction_proposal)
