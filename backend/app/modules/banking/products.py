"""Cards and loans: the two surfaces that were still `MOCK_BANKING_DATA`.

Everything derived is computed at read time -- a card's available limit, a
loan's progress -- so a screen can never show a figure that disagrees with the
numbers it was derived from. `portfolio_positions` follows the same rule for
market value and for the same reason.

Paying a card or an instalment goes through `payments.stage` / `confirm` like
every other way money leaves an account, so there is one confirm step and one
audit trail rather than a second, quieter path.
"""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from .models import Card, Loan

log = logging.getLogger("moneyfast.banking.products")


class ProductError(Exception):
    """Well-formed but not applicable."""


def _masked_number(brand: str) -> str:
    """A display number. There is no PAN in this system to protect, but a
    stored value that looks like one should still look masked."""
    prefix = "5" if brand == "mastercard" else "4"
    return f"{prefix}{random.randint(100, 999)} **** **** {random.randint(1000, 9999)}"


def cards_for(db: Session, user_id: str) -> list[dict[str, Any]]:
    """The user's cards, with the limit arithmetic done here."""
    rows = (
        db.query(Card)
        .filter(Card.user_id == user_id, Card.status == "active")
        .order_by(Card.created_at)
        .all()
    )
    return [
        {
            "id": card.id,
            "name": card.name,
            "brand": card.brand,
            "card_number": card.card_number,
            "limit": float(card.credit_limit),
            "current_debt": float(card.current_debt),
            # Derived, never stored.
            "available_limit": round(float(card.credit_limit) - float(card.current_debt), 2),
            "due_day": card.due_day,
            "color": card.color,
            "is_digital": card.is_digital,
            "settings": card.settings or {},
            "linked_account_id": card.linked_account_id,
        }
        for card in rows
    ]


def loans_for(db: Session, user_id: str) -> list[dict[str, Any]]:
    """The user's loans, with progress and remaining months derived."""
    rows = (
        db.query(Loan)
        .filter(Loan.user_id == user_id, Loan.status == "active")
        .order_by(Loan.created_at)
        .all()
    )
    out: list[dict[str, Any]] = []
    for loan in rows:
        total = float(loan.principal)
        remaining = float(loan.remaining_amount)
        paid = total - remaining
        out.append({
            "id": loan.id,
            "title": loan.title,
            "total_amount": total,
            "remaining_amount": remaining,
            "installment_amount": float(loan.installment_amount),
            "installment_count": loan.installment_count,
            "paid_installments": loan.paid_installments,
            "remaining_months": max(loan.installment_count - loan.paid_installments, 0),
            "next_due": loan.next_due,
            # Derived: a stored percentage drifts from its own numerator the
            # moment an instalment is paid.
            "progress_percentage": round((paid / total) * 100, 1) if total else 0.0,
        })
    return out


def issue_card(
    db: Session, *, user_id: str, name: str, brand: str, credit_limit: float,
    due_day: int = 10, current_debt: float = 0.0, linked_account_id: Optional[str] = None,
    color: Optional[str] = None, is_digital: bool = False,
) -> Card:
    if credit_limit <= 0:
        raise ProductError("Kart limiti sıfırdan büyük olmalı.")
    if current_debt < 0 or current_debt > credit_limit:
        raise ProductError("Borç, sıfır ile limit arasında olmalı.")

    card = Card(
        user_id=user_id, name=name, brand=brand,
        card_number=_masked_number(brand),
        credit_limit=round(float(credit_limit), 2),
        current_debt=round(float(current_debt), 2),
        due_day=int(due_day), color=color, is_digital=is_digital,
        linked_account_id=linked_account_id, settings={},
    )
    db.add(card)
    db.commit()
    log.info("issued card for %s: %s limit %.2f", user_id, name, credit_limit)
    return card


def update_card_settings(
    db: Session, user_id: str, card_id: str, settings: dict[str, Any]
) -> Card:
    """Freeze, contactless, online shopping -- what CardSettingsModal edits."""
    card = (
        db.query(Card)
        .filter(Card.id == card_id, Card.user_id == user_id)
        .first()
    )
    if card is None:
        raise ProductError("Kart bulunamadı.")
    card.settings = {**(card.settings or {}), **settings}
    db.commit()
    return card


def close_card(db: Session, user_id: str, card_id: str) -> bool:
    card = (
        db.query(Card).filter(Card.id == card_id, Card.user_id == user_id).first()
    )
    if card is None:
        return False
    if float(card.current_debt) > 0:
        raise ProductError("Borcu olan kart kapatılamaz.")
    card.status = "closed"
    db.commit()
    return True


def issue_loan(
    db: Session, *, user_id: str, title: str, principal: float,
    installment_count: int, installment_amount: Optional[float] = None,
) -> Loan:
    if principal <= 0:
        raise ProductError("Kredi tutarı sıfırdan büyük olmalı.")
    if installment_count <= 0:
        raise ProductError("Taksit sayısı sıfırdan büyük olmalı.")

    monthly = installment_amount or round(float(principal) / installment_count, 2)
    loan = Loan(
        user_id=user_id, title=title,
        principal=round(float(principal), 2),
        remaining_amount=round(float(principal), 2),
        installment_amount=monthly,
        installment_count=int(installment_count),
        paid_installments=0,
        next_due=date.today() + timedelta(days=30),
    )
    db.add(loan)
    db.commit()
    log.info("issued loan for %s: %s %.2f over %d", user_id, title, principal, installment_count)
    return loan


def apply_card_payment(db: Session, user_id: str, card_id: str, amount: float) -> float:
    """Reduce a card's debt. Called by `payments.confirm`, never directly.

    Returns the debt afterwards. Overpaying is refused rather than leaving a
    negative debt, which would read as the bank owing the customer money.
    """
    card = db.query(Card).filter(Card.id == card_id, Card.user_id == user_id).first()
    if card is None:
        raise ProductError("Kart bulunamadı.")
    debt = float(card.current_debt)
    if amount > debt:
        raise ProductError(
            f"Kart borcu {debt:,.2f}; bundan fazlası ödenemez."
        )
    card.current_debt = round(debt - float(amount), 2)
    return float(card.current_debt)


def apply_loan_payment(db: Session, user_id: str, loan_id: str, amount: float) -> float:
    """Record one instalment. Called by `payments.confirm`, never directly."""
    loan = db.query(Loan).filter(Loan.id == loan_id, Loan.user_id == user_id).first()
    if loan is None:
        raise ProductError("Kredi bulunamadı.")
    remaining = float(loan.remaining_amount)
    if amount > remaining:
        raise ProductError(f"Kalan borç {remaining:,.2f}; bundan fazlası ödenemez.")

    loan.remaining_amount = round(remaining - float(amount), 2)
    loan.paid_installments = min(loan.paid_installments + 1, loan.installment_count)
    if loan.remaining_amount <= 0:
        loan.status = "closed"
        loan.next_due = None
    elif loan.next_due is not None:
        loan.next_due = loan.next_due + timedelta(days=30)
    return float(loan.remaining_amount)
