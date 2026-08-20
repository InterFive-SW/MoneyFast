"""Chat widget construction.

The chat UI can render three interactive widgets alongside the prose reply
(see `frontend/src/types/chat.ts`). They are built here, deterministically,
from the specialist's tool payload.

**They are never asked of the model.** A model that can emit widget JSON can
emit a *fabricated* transaction proposal — a confirm button wired to an order
that was never staged, or a portfolio table with invented figures. Everything
below is a projection of data a tool actually returned; if the tool did not
return it, no widget is emitted.

This lives in the orchestrator rather than in the backend because building it
in the backend would mean shipping `specialist_output` across the service
boundary, and `api.py` withholds those internal fields on purpose.
"""

from __future__ import annotations

from typing import Any, Optional

#: Statuses that mean "a real proposal exists". Anything else — a rejected
#: validation, a missing field, an upstream error — must not render a button
#: that looks confirmable.
_CONFIRMABLE = "PENDING_USER_CONFIRMATION"

_BUY_TYPES = frozenset({"BUY", "ALIS", "ALIŞ"})
_SELL_TYPES = frozenset({"SELL", "SATIS", "SATIŞ"})
_TRANSFER_TYPES = frozenset({"TRANSFER", "EFT", "HAVALE"})


def _tr_amount(value: float) -> str:
    """Turkish number formatting: 1.250,50 rather than 1,250.50.

    Done by hand because `locale` would need the tr_TR locale installed in the
    image, and a missing locale fails at runtime by silently formatting in
    en_US — which reads as a hundredfold error to a Turkish user.
    """
    whole, _, fraction = f"{float(value):,.2f}".partition(".")
    return f"{whole.replace(',', '.')},{fraction}"


def build(state: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Return (widget, context_topic) for a finished turn.

    Both are optional and both default to None: a turn with nothing
    structured to show renders as prose, which is the correct outcome for
    education, smalltalk and handoff.
    """
    output = state.get("specialist_output") or {}
    if output.get("status") != "OK":
        # EMPTY, ERROR, NEEDS_INPUT and HANDOFF all mean there is no payload
        # worth rendering. The prose already explains why.
        return None, None

    data = output.get("data") or {}
    agent = output.get("agent")

    # Defence in depth against stale state. The graph checkpoints on
    # thread_id, so a specialist_output left by an earlier turn can still be
    # present on a turn that ran no tool. run_turn clears it, and this second
    # check means a future caller that forgets to cannot end up rendering a
    # confirm button for a proposal the user is not currently being shown.
    if agent != state.get("target_agent"):
        return None, None

    if agent == "TRANSACTION_AGENT":
        return _action_widget(data)
    if agent == "PORTFOLIO_AGENT":
        return _portfolio_widget(data)
    # Market research cites sources in prose; a widget would compete with the
    # citations rather than add to them. Risk output is a table of caveated
    # figures and is better read as text.
    return None, None


def _action_widget(data: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Confirmation surface for a staged proposal.

    Refuses to render unless the backend both staged the proposal AND asserted
    confirmation_required. That flag is a contract constant, and a proposal
    reaching the user without a confirmation step is indistinguishable from a
    completed order.
    """
    if data.get("status") != _CONFIRMABLE or data.get("confirmation_required") is not True:
        return None, None

    proposal_id = data.get("proposal_id")
    if not proposal_id:
        return None, None

    summary = data.get("summary") or {}
    symbol = summary.get("symbol") or ""
    quantity = summary.get("quantity")
    transaction_type = str(summary.get("transaction_type") or "").upper()
    is_buy = transaction_type in _BUY_TYPES
    is_sell = transaction_type in _SELL_TYPES
    is_transfer = transaction_type in _TRANSFER_TYPES

    estimate = data.get("estimate") or {}
    net = estimate.get("net_amount")
    currency = estimate.get("currency") or "TRY"

    cost = f" · yaklaşık {_tr_amount(net)} {currency}" if net else ""
    amount_label = f"{quantity:g} adet " if quantity else ""

    if is_transfer:
        destination = summary.get("destination_account_id") or ""
        message = f"{destination} hesabına {_tr_amount(net)} {currency} transfer önerisi"
        action = "transfer"
        # No instrument, so no context panel. The panel shows a live price and
        # instrument news; a transfer has neither.
        topic = None
    else:
        # Named explicitly rather than "buy or else sell": an unrecognised type
        # used to render as "Satım", so a type nobody handled was displayed to
        # the user as a sale.
        action_tr = "Alım" if is_buy else "Satım" if is_sell else "İşlem"
        message = f"{amount_label}{symbol} {action_tr} önerisi{cost}"
        action = "buy" if is_buy else "sell" if is_sell else "unknown"
        # Only a real ticker opens the panel. "İşlem" was being sent as a
        # topic and rendered as though it were an instrument.
        topic = symbol or None

    return {
        "type": "action",
        "payload": {
            "message": message,
            "confirmLabel": "Onayla",
            "cancelLabel": "Vazgeç",
            # The real staged proposal, not a synthetic order id. This is what
            # the confirm endpoint validates against.
            "actionId": proposal_id,
            "proposalId": proposal_id,
            "expiresAt": data.get("expires_at") or "",
            "asset": symbol,
            "action": action,
            "amount": quantity or 0,
        },
    }, topic


def _portfolio_widget(data: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    positions = data.get("positions") or []
    if not positions:
        # An empty portfolio is a complete answer, but there is no table to
        # draw. The prose says so.
        return None, None

    totals = data.get("totals") or {}
    return {
        "type": "portfolio",
        "payload": {
            "total_value": totals.get("total_market_value", 0.0),
            "total_profit_loss": totals.get("total_unrealized_pnl", 0.0),
            "base_currency": data.get("base_currency") or "TRY",
            "as_of": data.get("as_of") or "",
            "is_delayed": bool(data.get("is_delayed")),
            "positions": [
                {
                    "symbol": p.get("symbol", ""),
                    "quantity": p.get("quantity", 0.0),
                    "avg_cost": p.get("avg_cost", 0.0),
                    "last_price": p.get("last_price", 0.0),
                    "market_value": p.get("market_value", 0.0),
                    "unrealized_pnl": p.get("unrealized_pnl", 0.0),
                    "unrealized_pnl_pct": p.get("unrealized_pnl_pct", 0.0),
                }
                for p in positions
            ],
        },
        # The portfolio widget is already rendered inline in the message. A
        # context panel repeating it added nothing, and it opened showing a
        # price for "Portföy" — which is not an instrument.
    }, None
