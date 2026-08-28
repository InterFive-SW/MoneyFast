"""Banking request and response shapes."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BankAccountOut(BaseModel):
    id: str
    account_number: str
    iban: str
    account_type: str
    currency_code: str
    balance: float
    status: str


class TransferRequest(BaseModel):
    #: Account number or IBAN. Omitted means "my deposit account" — the user
    #: has one, and making them look it up to move their own money is friction
    #: with no purpose.
    source: Optional[str] = None
    destination: str = Field(..., min_length=4)
    amount: float = Field(..., gt=0)
    description: Optional[str] = None


class TransferOut(BaseModel):
    reference_number: str
    status: str
    amount: float
    fee: float
    currency: str
    source_balance_after: float
    destination_account: str


class MovementOut(BaseModel):
    """One leg of a transfer, from this account's point of view."""

    reference_number: str
    direction: str
    amount: float
    balance_after: float
    counterparty_iban: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime


class StatementOut(BaseModel):
    account_number: str
    balance: float
    currency_code: str
    movements: List[MovementOut] = Field(default_factory=list)


class SpendingCategoryOut(BaseModel):
    category: str
    amount: float


class SpendingSummaryOut(BaseModel):
    """What went out, by category, over a window."""

    period: str
    currency_code: str = "TRY"
    total_expense: float = 0.0
    #: Change against the previous window of the same length. None when there
    #: is no earlier window to compare against — a first month has no trend,
    #: and rendering 0% would claim it was flat.
    change_percent: Optional[float] = None
    categories: List[SpendingCategoryOut] = Field(default_factory=list)


class BalancePointOut(BaseModel):
    at: datetime
    balance: float


class BalanceHistoryOut(BaseModel):
    currency_code: str = "TRY"
    total: float = 0.0
    change_amount: float = 0.0
    change_percent: Optional[float] = None
    points: List[BalancePointOut] = Field(default_factory=list)


class SavingsGoalOut(BaseModel):
    id: str
    name: str
    target_amount: float
    current_amount: float
    currency_code: str = "TRY"
    icon: Optional[str] = None
    color: Optional[str] = None
    deadline: Optional[str] = None


class SavingsGoalIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(default=0, ge=0)
    icon: Optional[str] = None
    color: Optional[str] = None
    deadline: Optional[str] = None


# ---------------------------------------------------------------------------
# Bills, staged payments, saved payees
# ---------------------------------------------------------------------------


class BillLookupOut(BaseModel):
    """What is owed for a subscriber number, or nothing.

    `found=False` rather than a 404: "there is no open bill for this number" is
    a perfectly good answer to a lookup, not a failed request.
    """

    found: bool
    id: Optional[str] = None
    institution: Optional[str] = None
    bill_type: Optional[str] = None
    subscriber_no: Optional[str] = None
    amount: Optional[float] = None
    due_day: Optional[int] = None


class StagePaymentRequest(BaseModel):
    #: Whose payment this is. Honoured ONLY for a service caller (`mcp`), which
    #: reaches this endpoint with a service identity rather than a user JWT and
    #: names the user in the body -- the same arrangement
    #: `investment/transactions/stage` already uses. When a user token IS
    #: present it wins, and a mismatch is refused: otherwise anyone could stage
    #: a payment in someone else's name.
    user_id: Optional[str] = None
    #: TRANSFER | BILL_PAYMENT | CARD_PAYMENT
    payment_type: str = Field(..., min_length=1, max_length=20)
    #: Ignored for a bill: the amount is the bill's, so a caller naming a
    #: different figure cannot under- or over-pay.
    amount: Optional[float] = Field(default=None, gt=0)
    destination: Optional[str] = None
    institution: Optional[str] = None
    subscriber_no: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=200)
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class PaymentProposalOut(BaseModel):
    proposal_id: str
    status: str
    payment_type: str
    amount: float
    currency: str
    destination: Optional[str] = None
    description: Optional[str] = None
    expires_at: datetime
    balance_before: Optional[float] = None


class PaymentConfirmOut(BaseModel):
    proposal_id: str
    status: str
    reference_number: str
    amount: float
    currency: str
    balance_after: Optional[float] = None


class SavePayeeRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    institution: str = Field(..., min_length=1, max_length=80)
    subscriber_no: str = Field(..., min_length=1, max_length=40)


class SavedPayeeOut(BaseModel):
    id: str
    label: str
    institution: str
    subscriber_no: str


class SavedPayeeListOut(BaseModel):
    payees: List[SavedPayeeOut] = Field(default_factory=list)


class PortfolioAccountOut(BaseModel):
    """One account in the unified list.

    `is_investment` marks the entry whose balance lives in
    `investment.investment_accounts.cash_balance` rather than in
    `banking.accounts` -- the caller needs to know, because that one has no
    IBAN and no ledger legs of its own.
    """

    id: str
    account_number: str
    iban: Optional[str] = None
    account_type: str
    currency_code: str
    balance: float
    is_investment: bool = False


class CardOut(BaseModel):
    """A card as the UI renders it. `available_limit` is derived, not stored."""

    id: str
    name: str
    brand: str
    card_number: str
    limit: float
    current_debt: float
    available_limit: float
    due_day: int
    color: Optional[str] = None
    is_digital: bool = False
    settings: dict = Field(default_factory=dict)
    linked_account_id: Optional[str] = None


class LoanOut(BaseModel):
    id: str
    title: str
    total_amount: float
    remaining_amount: float
    installment_amount: float
    installment_count: int
    paid_installments: int
    remaining_months: int
    next_due: Optional[date] = None
    progress_percentage: float


class CardSettingsRequest(BaseModel):
    """Whatever CardSettingsModal toggles. Merged over what is stored, so a
    screen that sends one switch does not clear the others."""

    settings: dict = Field(default_factory=dict)
