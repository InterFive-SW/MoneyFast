"""Transfers, as a double-entry ledger.

Every rule here exists because its absence has a specific failure mode:

* Both legs and the transaction row commit **together**. Committing the debit
  before the credit leaves money that has left one account and arrived nowhere.
* The balance is re-read inside the transaction, not trusted from a staging
  check. Two transfers staged against the same balance would otherwise both
  pass and overdraw the account.
* A transfer to yourself is refused rather than silently netting to zero — it
  is always a mistake, and processing it produces a ledger entry that says
  nothing happened.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AccountTransaction, BankAccount, BankTransaction, SavingsGoal

log = logging.getLogger("moneyfast.banking")

#: Opening balance for a new deposit account. Synthetic, like every figure in
#: this system.
STARTING_BALANCE = 50000.0

#: What a transfer costs. Zero between a user's own accounts — charging someone
#: to move their own money between their own accounts is a fee with no service
#: behind it.
TRANSFER_FEE = 0.0
EXTERNAL_TRANSFER_FEE = 2.50


class TransferError(Exception):
    """The transfer cannot be made. Carries a user-facing Turkish reason."""


def _digits_for(user_id: str, length: int) -> str:
    """A stable digit string derived from the user id.

    Hashed rather than sliced. Account numbers and IBANs are numeric, but user
    ids are hex — taking the id's own characters kept only its digits, so two
    users whose ids differed solely in their letters produced the SAME IBAN and
    the second account hit the unique constraint at registration.
    """
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    return str(int(digest[:16], 16)).zfill(length)[:length]


def _iban_for(account_number: str) -> str:
    """A synthetic but well-formed IBAN.

    Deliberately marked TR00 — a real check digit would make these look like
    routable accounts, and nothing here reaches a payment network.
    """
    body = "".join(ch for ch in account_number if ch.isdigit()).zfill(16)[-16:]
    return f"TR00{body}00000{body[:2]}"


def ensure_account(db: Session, user_id: str) -> BankAccount:
    """The user's deposit account, opened if they have none.

    Does not commit — the caller owns the transaction.
    """
    existing = (
        db.query(BankAccount)
        .filter(BankAccount.user_id == user_id, BankAccount.account_type == "vadesiz")
        .first()
    )
    if existing is not None:
        return existing

    number = f"1{_digits_for(user_id, 12)}"
    account = BankAccount(
        user_id=user_id,
        account_number=number,
        iban=_iban_for(number),
        account_type="vadesiz",
        currency_code="TRY",
        balance=STARTING_BALANCE,
        status="active",
    )
    db.add(account)
    log.info("opened deposit account for user %s", user_id)
    return account


def accounts_for(db: Session, user_id: str) -> list[BankAccount]:
    return (
        db.query(BankAccount)
        .filter(BankAccount.user_id == user_id)
        .order_by(BankAccount.created_at)
        .all()
    )


def find_account(db: Session, reference: str) -> Optional[BankAccount]:
    """Resolve an account by number or IBAN.

    People paste either, and with or without spaces.
    """
    cleaned = (reference or "").replace(" ", "").strip().upper()
    if not cleaned:
        return None
    return (
        db.query(BankAccount)
        .filter(
            (BankAccount.account_number == cleaned) | (BankAccount.iban == cleaned)
        )
        .first()
    )


def _reference_number() -> str:
    return f"TRF-{secrets.token_hex(6).upper()}"


def transfer(
    db: Session,
    user_id: str,
    source_reference: str,
    destination_reference: str,
    amount: float,
    description: Optional[str] = None,
) -> dict:
    """Move money between two accounts, both legs in one transaction.

    Commits once at the end. A failure at any point leaves both balances as
    they were, which is the only acceptable outcome for a half-applied
    transfer.
    """
    if amount is None or amount <= 0:
        raise TransferError("Transfer tutarı sıfırdan büyük olmalı.")

    source = find_account(db, source_reference)
    if source is None:
        raise TransferError(f"Gönderen hesap bulunamadı: {source_reference}")
    if source.user_id != user_id:
        # Indistinguishable from "not found" on purpose: confirming that an
        # account exists but belongs to someone else is already more than the
        # caller should learn.
        raise TransferError(f"Gönderen hesap bulunamadı: {source_reference}")
    if source.status != "active":
        raise TransferError("Gönderen hesap aktif değil.")

    destination = find_account(db, destination_reference)
    if destination is None:
        raise TransferError(f"Alıcı hesap bulunamadı: {destination_reference}")
    if destination.status != "active":
        raise TransferError("Alıcı hesap aktif değil.")

    if destination.id == source.id:
        raise TransferError("Gönderen ve alıcı hesap aynı olamaz.")

    if source.currency_code != destination.currency_code:
        # Cross-currency transfer needs a rate and a disclosed conversion.
        # Refusing is honest; applying 1:1 is the bug this codebase already
        # paid for once on the trading side.
        raise TransferError(
            f"Farklı para birimleri arasında transfer desteklenmiyor "
            f"({source.currency_code} → {destination.currency_code})."
        )

    fee = TRANSFER_FEE if source.user_id == destination.user_id else EXTERNAL_TRANSFER_FEE
    total = round(float(amount) + fee, 2)

    source_before = float(source.balance)
    if total > source_before:
        # İK-07: the balance must cover the amount AND the fee.
        raise TransferError(
            f"Bakiye yetersiz: transfer ücretle birlikte {total:,.2f} "
            f"{source.currency_code} tutuyor, hesabınızda "
            f"{source_before:,.2f} {source.currency_code} var."
        )

    destination_before = float(destination.balance)
    now = datetime.now(timezone.utc)

    record = BankTransaction(
        reference_number=_reference_number(),
        transaction_type="havale" if source.user_id != destination.user_id else "virman",
        status="completed",
        amount=round(float(amount), 2),
        currency_code=source.currency_code,
        description=description,
        completed_at=now,
    )
    db.add(record)
    db.flush()  # the legs need the transaction id

    source.balance = round(source_before - total, 2)
    destination.balance = round(destination_before + float(amount), 2)
    source.updated_at = now
    destination.updated_at = now

    db.add(
        AccountTransaction(
            transaction_id=record.id,
            account_id=source.id,
            direction="DEBIT",
            amount=total,
            balance_before=source_before,
            balance_after=float(source.balance),
            counterparty_iban=destination.iban,
            description=description,
            created_at=now,
        )
    )
    db.add(
        AccountTransaction(
            transaction_id=record.id,
            account_id=destination.id,
            direction="CREDIT",
            amount=round(float(amount), 2),
            balance_before=destination_before,
            balance_after=float(destination.balance),
            counterparty_iban=source.iban,
            description=description,
            created_at=now,
        )
    )

    db.commit()
    log.info(
        "transfer %s: %s -> %s, %.2f (fee %.2f)",
        record.reference_number, source.account_number,
        destination.account_number, amount, fee,
    )
    return {
        "reference_number": record.reference_number,
        "status": "completed",
        "amount": round(float(amount), 2),
        "fee": fee,
        "currency": source.currency_code,
        "source_balance_after": float(source.balance),
        "destination_account": destination.account_number,
    }


# ---------------------------------------------------------------------------
# Reporting — derived from the ledger, never stored as a separate total
# ---------------------------------------------------------------------------

def spending_by_category(
    db: Session, user_id: str, since: datetime
) -> list[dict[str, Any]]:
    """Outgoing money grouped by what it was for.

    DEBIT legs only: a transfer between your own accounts appears as both a
    debit and a credit, and counting the debit as spending would make moving
    your own money look like an expense.
    """
    account_ids = [account.id for account in accounts_for(db, user_id)]
    if not account_ids:
        return []

    rows = db.execute(
        select(
            BankTransaction.category,
            func.sum(AccountTransaction.amount),
        )
        .join(BankTransaction, BankTransaction.id == AccountTransaction.transaction_id)
        .where(
            AccountTransaction.account_id.in_(account_ids),
            AccountTransaction.direction == "DEBIT",
            AccountTransaction.created_at >= since,
            BankTransaction.category.isnot(None),
        )
        .group_by(BankTransaction.category)
        .order_by(func.sum(AccountTransaction.amount).desc())
    ).all()

    return [
        {"category": category, "amount": round(float(total), 2)}
        for category, total in rows
    ]


def income_total(db: Session, user_id: str, since: datetime) -> float:
    """Money that arrived from OUTSIDE the user's own accounts.

    The mirror of `spending_by_category`, and it has the same trap in reverse:
    moving your own money between two of your accounts writes a CREDIT leg,
    and counting that as income would let anyone raise their apparent salary
    by shuffling funds back and forth.

    So a credit only counts when the same transaction has no debit leg on any
    account this user owns. Salary arrives from an employer, which by
    definition has no account here.
    """
    account_ids = [account.id for account in accounts_for(db, user_id)]
    if not account_ids:
        return 0.0

    internal = (
        select(AccountTransaction.transaction_id)
        .where(
            AccountTransaction.account_id.in_(account_ids),
            AccountTransaction.direction == "DEBIT",
        )
        .scalar_subquery()
    )

    total = db.execute(
        select(func.sum(AccountTransaction.amount)).where(
            AccountTransaction.account_id.in_(account_ids),
            AccountTransaction.direction == "CREDIT",
            AccountTransaction.created_at >= since,
            AccountTransaction.transaction_id.notin_(internal),
        )
    ).scalar()

    return round(float(total or 0.0), 2)


def balance_history(
    db: Session, user_id: str, limit: int = 30
) -> list[dict[str, Any]]:
    """The running balance after each movement.

    Read from `balance_after`, which the ledger already records, rather than
    replayed from the movements — the whole reason that column exists.
    """
    account_ids = [account.id for account in accounts_for(db, user_id)]
    if not account_ids:
        return []

    rows = db.execute(
        select(AccountTransaction.created_at, AccountTransaction.balance_after)
        .where(AccountTransaction.account_id.in_(account_ids))
        .order_by(AccountTransaction.created_at.desc())
        .limit(limit)
    ).all()

    return [
        {"at": created_at, "balance": round(float(balance), 2)}
        for created_at, balance in reversed(rows)
    ]


def goals_for(db: Session, user_id: str) -> list[SavingsGoal]:
    return (
        db.query(SavingsGoal)
        .filter(SavingsGoal.user_id == user_id)
        .order_by(SavingsGoal.created_at)
        .all()
    )
