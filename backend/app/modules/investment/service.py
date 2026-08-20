"""Settlement — the write side of a confirmed transaction.

Confirming a proposal used to set `status = 'CONFIRMED'` and commit. Nothing
else happened: cash was untouched, holdings were untouched, and the order list
then showed "Gerçekleşti" next to a trade that had changed nothing. An order
that reports itself executed while the portfolio disagrees is the exact
inconsistency FOG-GB-01 forbids, and it is worse than an error because nothing
signals it.

What settlement is and is not: this moves an internal ledger. No order reaches
a venue, nothing is routed to a custodian, and the prices are the delayed
reference prices the proposal was costed with. It makes the app's own numbers
agree with each other, which is all it claims to do.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import InvestmentAccount, InvestmentProduct, PortfolioPosition

log = logging.getLogger("moneyfast.investment.settlement")

#: Transaction types that consume cash and add to a holding.
BUY_TYPES = frozenset({"BUY", "ALIS", "ALIŞ"})

#: Transaction types that release a holding and return cash.
SELL_TYPES = frozenset({"SELL", "SATIS", "SATIŞ"})

#: Quantities below this are treated as a closed position rather than a
#: residue. Float arithmetic on a full sell can leave 1e-15 behind, and a row
#: claiming a billionth of a share is noise pretending to be a holding.
DUST = 1e-9


#: Opening cash for a newly created account. Synthetic, like every other
#: balance in this system — see migration 0006 on where the fiction lives.
STARTING_CASH = 25000.0


class SettlementError(Exception):
    """The proposal cannot be settled. Carries a user-facing Turkish reason."""


def ensure_account(db: Session, user_id: str) -> InvestmentAccount:
    """The user's investment account, created if they do not have one yet.

    Called at registration so cash and holdings are per-user from the first
    login. Before this there was a single shared account, which meant one
    person's purchase spent everybody's money.

    Does not commit — the caller owns the transaction.
    """
    existing = (
        db.query(InvestmentAccount)
        .filter(InvestmentAccount.user_id == user_id)
        .first()
    )
    if existing is not None:
        return existing

    account = InvestmentAccount(
        user_id=user_id,
        # Unique per account and stable: derived from the user id rather than
        # a counter, so two concurrent registrations cannot collide on it.
        account_number=f"TR-{str(user_id).replace('-', '')[:12].upper()}",
        name="Yatırım Hesabı",
        currency_code="TRY",
        cash_balance=STARTING_CASH,
        status="active",
    )
    db.add(account)
    log.info("created investment account for user %s", user_id)
    return account


def _position(
    db: Session, account_id: str, product_id: str
) -> Optional[PortfolioPosition]:
    return (
        db.query(PortfolioPosition)
        .filter(
            PortfolioPosition.investment_account_id == account_id,
            PortfolioPosition.product_id == product_id,
        )
        .first()
    )


def settle(db: Session, proposal, account: InvestmentAccount) -> dict:
    """Apply a confirmed proposal to cash and holdings.

    Does NOT commit. The caller commits once, together with the proposal's
    status change, so a crash between the two cannot leave money moved and the
    proposal still pending — or the reverse.

    Returns a summary of what moved, for the confirmation message.
    """
    transaction_type = (proposal.transaction_type or "").upper()
    estimate = (proposal.payload or {}).get("estimate") or {}
    net_amount = estimate.get("net_amount")

    if net_amount is None:
        # Re-pricing here would settle at a figure the user never saw. The
        # proposal is costed at staging time and that is the number they
        # approved.
        raise SettlementError("Bu önerinin tutar bilgisi eksik, işlem uygulanamadı.")

    net_amount = float(net_amount)
    quantity = float(proposal.quantity or 0)

    if transaction_type in BUY_TYPES:
        return _settle_buy(db, proposal, account, net_amount, quantity)
    if transaction_type in SELL_TYPES:
        return _settle_sell(db, proposal, account, net_amount, quantity)

    # Transfers and anything else reach confirm without a settlement path. The
    # banking module does not exist, so pretending one had run would be the
    # same lie in a new place.
    raise SettlementError(
        f"'{transaction_type or 'bilinmeyen'}' türü için uygulanabilir bir takas adımı yok."
    )


def _product(db: Session, symbol: str) -> InvestmentProduct:
    product = (
        db.query(InvestmentProduct).filter(InvestmentProduct.symbol == symbol).first()
    )
    if product is None:
        raise SettlementError(f"{symbol} için enstrüman kaydı bulunamadı.")
    return product


def _settle_buy(
    db: Session, proposal, account: InvestmentAccount, net_amount: float, quantity: float
) -> dict:
    cash = float(account.cash_balance)
    if net_amount > cash:
        # Checked again here, not only at staging. Two proposals can be staged
        # against the same balance before either is confirmed, and the second
        # one must not overdraw the account.
        raise SettlementError(
            f"Bakiye yetersiz: işlem {net_amount:,.2f} TL tutuyor, "
            f"hesabınızda {cash:,.2f} TL var."
        )

    product = _product(db, proposal.symbol)
    position = _position(db, account.id, product.id)
    now = datetime.now(timezone.utc)

    if position is None:
        db.add(
            PortfolioPosition(
                investment_account_id=account.id,
                product_id=product.id,
                quantity=quantity,
                # Cost basis is the reference price, not the all-in net. Fees
                # are an expense, not part of what the shares are worth, and
                # folding them in would overstate the break-even price.
                average_buy_price=_reference_price(proposal, net_amount, quantity),
                opened_at=now,
                updated_at=now,
            )
        )
    else:
        held = float(position.quantity)
        new_quantity = held + quantity
        # Weighted average: the old basis keeps its weight in the shares it
        # applies to. Overwriting with the latest price would erase the
        # history of what the position actually cost.
        position.average_buy_price = (
            float(position.average_buy_price) * held
            + _reference_price(proposal, net_amount, quantity) * quantity
        ) / new_quantity
        position.quantity = new_quantity
        position.updated_at = now

    account.cash_balance = cash - net_amount
    log.info(
        "settled BUY %s x%s for %s, cash %.2f -> %.2f",
        proposal.symbol, quantity, proposal.id, cash, float(account.cash_balance),
    )
    return {
        "direction": "BUY",
        "symbol": proposal.symbol,
        "quantity": quantity,
        "cash_delta": -net_amount,
        "cash_after": float(account.cash_balance),
    }


def _settle_sell(
    db: Session, proposal, account: InvestmentAccount, net_amount: float, quantity: float
) -> dict:
    product = _product(db, proposal.symbol)
    position = _position(db, account.id, product.id)
    held = float(position.quantity) if position is not None else 0.0

    if quantity > held:
        raise SettlementError(
            f"Satılabilir miktar yetersiz: {proposal.symbol} için {held:g} adet var, "
            f"{quantity:g} adet satılmak isteniyor."
        )

    cash = float(account.cash_balance)
    remaining = held - quantity
    if remaining <= DUST:
        # The position is closed. Average cost has no meaning without shares,
        # so the row goes rather than lingering at quantity zero.
        db.delete(position)
    else:
        position.quantity = remaining
        # Average cost is unchanged by a sale: selling does not alter what the
        # remaining shares cost to acquire.
        position.updated_at = datetime.now(timezone.utc)

    account.cash_balance = cash + net_amount
    log.info(
        "settled SELL %s x%s for %s, cash %.2f -> %.2f",
        proposal.symbol, quantity, proposal.id, cash, float(account.cash_balance),
    )
    return {
        "direction": "SELL",
        "symbol": proposal.symbol,
        "quantity": quantity,
        "cash_delta": net_amount,
        "cash_after": float(account.cash_balance),
    }


def _reference_price(proposal, net_amount: float, quantity: float) -> float:
    """Per-share price the proposal was costed at.

    Prefers the stored reference price; falls back to dividing the net by the
    quantity so a proposal missing that field still books a sane basis rather
    than zero.
    """
    estimate = (proposal.payload or {}).get("estimate") or {}
    price = estimate.get("reference_price")
    if price is not None:
        return float(price)
    return net_amount / quantity if quantity else 0.0
