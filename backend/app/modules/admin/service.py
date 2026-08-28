"""Operator actions on customer accounts.

Everything here writes through the SAME paths a customer's own activity takes:
cash moves via the banking ledger, positions settle the way a confirmed order
settles. Nothing does `UPDATE ... SET balance`. An adjustment that changes a
number without appearing in the history is how a demo acquires a balance
nobody can explain -- and the banking module's own comment already says the
accounts are not the source of truth, the transactions are.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.modules.banking import service as banking_service
from app.modules.banking.models import Bill

log = logging.getLogger("moneyfast.admin")


class AdminActionError(Exception):
    """A request that is well-formed but cannot be applied."""


def list_customers(db: Session) -> list[dict[str, Any]]:
    """Every customer, with what they hold.

    Portfolio value is converted through `ai_service.holding_value`, the one
    implementation the rest of the app already shares. A holding whose currency
    has no rate is excluded rather than counted at an invented one, so the
    figure an operator sees is the same figure the customer's own screens show.
    """
    from app.modules.auth.models import User
    from app.modules.investment import ai_service, market_service

    # One FX source for the whole app: the live USD/TRY quote, with no
    # hardcoded fallback. A holding whose currency has no rate is excluded
    # rather than counted at an invented one.
    rates = ai_service.fx_rates(market_service.latest_quotes(db))
    rows: list[dict[str, Any]] = []

    for user in db.query(User).order_by(User.created_at).all():
        uid = str(user.id)
        account = banking_service.deposit_account(db, uid)

        # Resolved WITHOUT the demo fallback. `holdings()` would otherwise hand
        # back the shared demo portfolio for a customer who has no investment
        # account, and an operator reading this screen would act on holdings
        # that are not theirs. Reading the demo portfolio is harmless; showing
        # it under someone's name is not.
        investment_account = market_service.account(
            db, user_id=uid, allow_demo_fallback=False,
        )
        holdings = (
            market_service.holdings(db, user_id=uid)
            if investment_account is not None else []
        )

        base = account.currency_code if account is not None else "TRY"
        value = 0.0
        for holding in holdings:
            converted = ai_service.holding_value(holding, rates, base_currency=base)
            if converted is not None:
                value += converted

        rows.append({
            "id": uid,
            "tc_no": user.tc_no,
            "email": user.email,
            "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "is_active": bool(user.is_active),
            "cash_balance": float(account.balance) if account is not None else 0.0,
            "currency_code": base,
            "portfolio_value": round(value, 2),
            "position_count": len(holdings),
            "created_at": user.created_at,
        })
    return rows


def adjust_cash(
    db: Session, user_id: str, amount: float, description: Optional[str], actor: str,
    account_id: Optional[str] = None,
) -> dict[str, Any]:
    """Credit or debit one of a customer's accounts, through the ledger.

    `account_id` names WHICH account. Without it this silently took the first
    banking row, which is why crediting a customer never reached their
    investment cash: that lives in a different table entirely and no banking
    account is it.

    The investment account is handled separately because it is not a
    `banking.accounts` row -- there is no leg to write, only a balance the
    settlement code owns.
    """
    from app.modules.investment import market_service

    label = description or ("Yönetici para yatırma" if amount > 0 else "Yönetici para çekme")

    investment = market_service.account(db, user_id=user_id, allow_demo_fallback=False)
    if investment is not None and account_id in {investment.id, investment.account_number}:
        before = float(investment.cash_balance)
        after = round(before + float(amount), 2)
        if after < 0:
            raise AdminActionError(
                f"Bakiye eksiye düşemez: yatırım hesabında {before:,.2f} var, "
                f"{abs(float(amount)):,.2f} düşülemez."
            )
        investment.cash_balance = after
        db.commit()
        log.info("investment cash adjustment %+.2f for %s by %s", amount, user_id, actor)
        return {
            "reference_number": None,
            "balance_after": after,
            "message": f"Yatırım hesabına {abs(amount):,.2f} "
                       f"{investment.currency_code or 'TRY'} işlendi.",
        }

    account = None
    if account_id:
        account = next(
            (a for a in banking_service.accounts_for(db, user_id)
             if account_id in {a.id, a.account_number}),
            None,
        )
        if account is None:
            raise AdminActionError("Seçilen hesap bulunamadı.")
    else:
        account = banking_service.deposit_account(db, user_id)
    if account is None:
        raise AdminActionError("Kullanıcının mevduat hesabı bulunamadı.")

    try:
        result = banking_service.post_adjustment(
            db, account, amount, description=label, actor=actor,
        )
    except banking_service.TransferError as exc:
        raise AdminActionError(str(exc)) from exc

    return {
        "reference_number": result["reference_number"],
        "balance_after": result["balance_after"],
        "message": f"{abs(amount):,.2f} {result['currency']} işlendi.",
    }


def adjust_position(
    db: Session, user_id: str, symbol: str, quantity: float, actor: str
) -> dict[str, Any]:
    """Grant or remove a holding.

    Granting uses the CURRENT market price as the average cost. A position
    handed out at a cost of zero would show an infinite return on the
    customer's own portfolio screen, which is worse than no position at all.
    """
    from app.modules.investment import market_service
    from app.modules.investment.models import PortfolioPosition

    if quantity == 0:
        raise AdminActionError("Adet sıfır olamaz.")

    product = market_service.resolve_symbol(db, symbol, strict=True)
    if product is None:
        raise AdminActionError(f"Enstrüman bulunamadı: {symbol}")

    owner = market_service.account(db, user_id=user_id, allow_demo_fallback=False)
    if owner is None:
        raise AdminActionError("Kullanıcının yatırım hesabı bulunamadı.")

    position = (
        db.query(PortfolioPosition)
        .filter(
            PortfolioPosition.investment_account_id == owner.id,
            PortfolioPosition.product_id == product.id,
        )
        .first()
    )
    held = float(position.quantity) if position is not None else 0.0
    after = round(held + float(quantity), 6)
    if after < 0:
        raise AdminActionError(
            f"{product.symbol} için {held:g} adet var, {abs(quantity):g} çıkarılamaz."
        )

    quote = market_service.latest_quotes(db, [product.symbol]).get(product.symbol) or {}
    price = quote.get("price")

    if position is None:
        if price is None:
            raise AdminActionError(
                f"{product.symbol} için güncel fiyat yok; maliyetsiz pozisyon açılamaz."
            )
        position = PortfolioPosition(
            investment_account_id=owner.id,
            product_id=product.id,
            quantity=after,
            average_buy_price=float(price),
        )
        db.add(position)
    elif after == 0:
        # A zero-quantity row is a holding the customer does not hold. Removing
        # it keeps the portfolio screen honest.
        db.delete(position)
    else:
        if quantity > 0 and price is not None:
            # Weighted average, the same rule a confirmed buy applies.
            total_cost = held * float(position.average_buy_price) + float(quantity) * float(price)
            position.average_buy_price = round(total_cost / after, 6)
        position.quantity = after

    db.commit()
    log.info("position adjustment: %s %+g for %s by %s", product.symbol, quantity, user_id, actor)
    return {
        "message": f"{product.symbol}: {held:g} → {after:g} adet.",
        "quantity_after": after,
    }


def issue_bill(
    db: Session, *, institution: str, bill_type: str, subscriber_no: str,
    amount: float, due_day: int, actor: str, holder_name: Optional[str] = None,
) -> Bill:
    """Put a bill into the system for a subscriber number to find.

    Refuses a second OPEN bill for the same (institution, subscriber): the
    partial unique index would reject it anyway, and a caught duplicate reads
    better than a 500.
    """
    existing = (
        db.query(Bill)
        .filter(
            Bill.institution == institution,
            Bill.subscriber_no == subscriber_no,
            Bill.status == "pending",
        )
        .first()
    )
    if existing is not None:
        raise AdminActionError(
            f"{institution} / {subscriber_no} için ödenmemiş bir fatura zaten var."
        )

    # A real bill has a name on it. If nobody supplied one, use the customer
    # this subscriber number is assigned to -- which is usually who meant to
    # receive it anyway.
    if not holder_name:
        holder_name = _assigned_customer_name(db, institution, subscriber_no)

    bill = Bill(
        holder_name=holder_name,
        institution=institution,
        bill_type=bill_type,
        subscriber_no=subscriber_no,
        amount=round(float(amount), 2),
        due_day=int(due_day),
        status="pending",
        issued_by=actor,
    )
    db.add(bill)
    db.commit()
    log.info("bill issued: %s / %s, %.2f by %s", institution, subscriber_no, amount, actor)
    return bill


def withdraw_bill(db: Session, bill_id: str) -> bool:
    """Remove an unpaid bill. A paid one is history and stays."""
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if bill is None:
        return False
    if bill.status == "paid":
        raise AdminActionError("Ödenmiş bir fatura silinemez.")
    db.delete(bill)
    db.commit()
    return True


def _assigned_customer(db: Session, institution: str, subscriber_no: str):
    """The saved-payee row that ties a subscriber number to a customer."""
    from app.modules.banking.models import SavedPayee

    return (
        db.query(SavedPayee)
        .filter(
            SavedPayee.institution == institution,
            SavedPayee.subscriber_no == subscriber_no,
        )
        .first()
    )


def _full_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    from app.modules.auth.models import User

    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None
    return f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email


def _assigned_customer_name(
    db: Session, institution: str, subscriber_no: str
) -> Optional[str]:
    payee = _assigned_customer(db, institution, subscriber_no)
    return _full_name(db, payee.user_id) if payee is not None else None


def describe_bills(db: Session) -> list[dict[str, Any]]:
    """Bills with the two names the admin panel needs.

    A bill still belongs to nobody until it is paid -- that is the design.
    But "meant for" and "settled by" are both knowable, and showing neither
    left an operator staring at a subscriber number that told them nothing.
    """
    rows: list[dict[str, Any]] = []
    for bill in db.query(Bill).order_by(Bill.created_at.desc()).all():
        rows.append({
            "id": bill.id,
            "holder_name": bill.holder_name,
            "assigned_to": _assigned_customer_name(db, bill.institution, bill.subscriber_no),
            "paid_by_name": _full_name(db, bill.paid_by),
            "institution": bill.institution,
            "bill_type": bill.bill_type,
            "subscriber_no": bill.subscriber_no,
            "amount": float(bill.amount),
            "due_day": bill.due_day,
            "status": bill.status,
            "paid_by": bill.paid_by,
            "paid_at": bill.paid_at,
            "created_at": bill.created_at,
        })
    return rows


def assign_subscription(
    db: Session, *, user_id: str, institution: str, subscriber_no: str,
    label: Optional[str] = None,
) -> dict[str, Any]:
    """Give a subscriber number to a customer.

    Deliberately writes a `saved_payees` row rather than inventing a second
    registry: the customer gets the number in their Kayıtlı İşlemler ready to
    pay, and the admin panel gets the link it needs to name whose bill a
    number is. One table, two jobs it was already shaped for.
    """
    from app.modules.banking import payments

    if _full_name(db, user_id) is None:
        raise AdminActionError("Kullanıcı bulunamadı.")

    payee = payments.save_payee(
        db, user_id, label or institution, institution, subscriber_no,
    )
    return {
        "id": payee.id,
        "user_id": user_id,
        "full_name": _full_name(db, user_id),
        "label": payee.label,
        "institution": payee.institution,
        "subscriber_no": payee.subscriber_no,
    }


def list_subscriptions(db: Session, user_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Every assigned subscriber number, so an operator can read one off and
    pay it in the demo."""
    from app.modules.banking.models import SavedPayee

    query = db.query(SavedPayee)
    if user_id:
        query = query.filter(SavedPayee.user_id == user_id)
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "full_name": _full_name(db, row.user_id),
            "label": row.label,
            "institution": row.institution,
            "subscriber_no": row.subscriber_no,
        }
        for row in query.order_by(SavedPayee.created_at).all()
    ]
