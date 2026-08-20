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
