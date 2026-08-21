"""Banking request and response shapes."""

from __future__ import annotations

from datetime import datetime
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
