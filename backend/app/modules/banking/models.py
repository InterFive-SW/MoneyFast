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
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    #: Kullanıcının hesabına verdiği ad. Sihirbaz bunu bir dönem soruyor ama
    #: hiçbir yere yazmıyordu; sorulup atılan bir girdi, hiç sorulmamasından
    #: kötü. Boş olabilir -- adı olmayan hesap türünden ve para biriminden
    #: türetilen etiketle görünüyor.
    nickname: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    balance: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    #: Yıllık brüt faiz oranı, yüzde olarak. Yalnızca vadeli hesaplarda dolu.
    #: Arayüzde bir dönem `%42.50` diye SABİT yazılıydı ve hiçbir kayda
    #: dayanmıyordu -- gösterilen oranla ödenen faiz arasında bir bağ yoktu,
    #: çünkü ödenen faiz de yoktu.
    interest_rate: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    #: Vade, gün olarak. Ürün günlük hesaba çevrildi: her gün sonunda işler.
    term_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: En son işletilen faizin tarihi. Aynı gün ikinci kez çalışmayı bu
    #: engelliyor; yeniden başlatma faizi ikinci kez ödettirmemeli.
    last_accrued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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


class Bill(Base):
    """An issued bill, found by subscriber number rather than owned by a user.

    That is how the paper works: the number on it is the key, and whoever holds
    the paper can pay it. It is also what makes a saved payee worth having --
    the number is the tedious part.
    """

    __tablename__ = "bills"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    #: The name printed on the bill, as a real one carries. A bill still
    #: belongs to nobody until it is paid; this is only what is written on it.
    holder_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    institution: Mapped[str] = mapped_column(String(80), nullable=False)
    bill_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subscriber_no: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    due_day: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    issued_by: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Null while open. A bill belongs to whoever settles it, which is not
    #: known when it is issued.
    paid_by: Mapped[str | None] = mapped_column(String, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SavedPayee(Base):
    """A subscriber number the user chose to keep -- "Kayıtlı İşlemler"."""

    __tablename__ = "saved_payees"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "institution", "subscriber_no", name="uq_saved_payee_per_user",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    institution: Mapped[str] = mapped_column(String(80), nullable=False)
    subscriber_no: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class PaymentProposal(Base):
    """A staged payment. Nothing has moved until it is confirmed.

    The investment module has the same contract for orders; money movement gets
    its own because a bill payment answering `symbol`/`quantity` with NULL
    would be a row shaped like an order that is not one.
    """

    __tablename__ = "payment_proposals"
    __table_args__ = (
        Index("ix_payment_proposals_user", "user_id", "created_at"),
        {"schema": SCHEMA},
    )

    #: Derived from the idempotency key, so a retried staging call resolves to
    #: this row rather than stacking proposals against one balance.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Card(Base):
    """A credit card. Shape follows the `CreditCard` the UI already renders.

    `available_limit` is NOT stored: it is the limit minus the debt, and a
    stored copy can disagree with its own arithmetic the moment either moves.
    Same rule `portfolio_positions` follows for market value.
    """

    __tablename__ = "cards"
    __table_args__ = (
        Index("ix_cards_user", "user_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    brand: Mapped[str] = mapped_column(String(20), nullable=False, default="visa")
    card_number: Mapped[str] = mapped_column(String(25), nullable=False)
    credit_limit: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    current_debt: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_digital: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    linked_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class Loan(Base):
    """A loan and its instalment plan.

    `progress` is derived from paid instalments, not stored, for the same
    reason a card's available limit is not.
    """

    __tablename__ = "loans"
    __table_args__ = (
        Index("ix_loans_user", "user_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    principal: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    remaining_amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    installment_amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    installment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_installments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
