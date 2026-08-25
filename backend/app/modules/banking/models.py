"""Banking tables — a double-entry ledger.

Follows the design in `infra/intertech.sql:93-140`, which was written and never
migrated. The shape matters: a transfer is not "subtract here, add there" but a
`transaction` with two `account_transactions` legs, each recording the balance
before and after. That is what makes a transfer auditable after the fact —
without the legs, a wrong balance has no explanation attached to it.

The comment in the reference schema says it best: accounts are not the source
of truth, the transactions are.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEMA = "banking"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BankAccount(Base):
    """A deposit account. One `vadesiz` per user is opened at registration."""

    __tablename__ = "accounts"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    iban: Mapped[str] = mapped_column(String(34), unique=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, default="vadesiz")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    balance: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class BankTransaction(Base):
    """The transfer itself. Its legs carry the per-account movement."""

    __tablename__ = "transactions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    reference_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: What the money was FOR. A ledger records that money moved, not why, so
    #: this is the only place a spending breakdown can come from. Nullable: a
    #: transfer between your own accounts has no spending category, and
    #: forcing one would invent a fact.
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SavingsGoal(Base):
    """A target the user set. Intent, not an observation — so unlike every
    other row in this schema it is not derived from a movement."""

    __tablename__ = "savings_goals"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    current_amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    icon: Mapped[str | None] = mapped_column(String(8), nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class AccountTransaction(Base):
    """One side of a transfer.

    `balance_before` and `balance_after` are stored rather than recomputed:
    they are what lets someone reading the history later say what the balance
    *was*, without replaying every movement since the account opened.
    """

    __tablename__ = "account_transactions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    balance_before: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
