"""Admin request and response shapes.

Nothing here echoes a password hash, and the customer list carries only what
an operator needs to act: who they are, what they hold, what they are worth.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    full_name: Optional[str] = None


class AdminUserRow(BaseModel):
    """One customer, as an operator needs to see them."""

    id: str
    tc_no: str
    email: str
    full_name: str
    is_active: bool
    #: Deposit balance, in the account's own currency.
    cash_balance: float
    currency_code: str
    #: Portfolio market value, already converted to the account's base currency.
    portfolio_value: float
    position_count: int
    created_at: datetime


class CashAdjustmentRequest(BaseModel):
    #: Negative debits. Signed rather than an amount plus a direction enum:
    #: one field cannot disagree with itself.
    amount: float = Field(..., description="Pozitif yatırır, negatif çeker.")
    description: Optional[str] = Field(default=None, max_length=200)
    #: WHICH account. Omitted means the vadesiz one. Without this the
    #: adjustment always landed on the deposit account, so crediting a
    #: customer could never reach their investment cash -- that lives in a
    #: different table and no banking account is it.
    account_id: Optional[str] = None


class PositionAdjustmentRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    #: Negative removes. Removing more than is held is refused, not clamped.
    quantity: float = Field(..., description="Pozitif ekler, negatif çıkarır.")


class AdjustmentResult(BaseModel):
    reference_number: Optional[str] = None
    message: str
    balance_after: Optional[float] = None
    quantity_after: Optional[float] = None


class IssueBillRequest(BaseModel):
    #: The name printed on the bill, as a real one carries. Optional: if the
    #: subscriber number is already assigned to a customer, their name is used.
    holder_name: Optional[str] = Field(default=None, max_length=120)
    institution: str = Field(..., min_length=1, max_length=80)
    bill_type: str = Field(..., min_length=1, max_length=20)
    subscriber_no: str = Field(..., min_length=1, max_length=40)
    amount: float = Field(..., gt=0)
    due_day: int = Field(..., ge=1, le=31)


class BillOut(BaseModel):
    id: str
    #: Printed on the bill.
    holder_name: Optional[str] = None
    #: The customer this subscriber number is assigned to, resolved through
    #: `saved_payees`. A bill still belongs to nobody until it is paid; this
    #: is who it was MEANT for, which is what the admin panel was missing.
    assigned_to: Optional[str] = None
    #: Who actually settled it.
    paid_by_name: Optional[str] = None
    institution: str
    bill_type: str
    subscriber_no: str
    amount: float
    due_day: int
    status: str
    paid_by: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime


class BillListOut(BaseModel):
    bills: List[BillOut] = Field(default_factory=list)


class AssignSubscriptionRequest(BaseModel):
    """Give a subscriber number to a customer.

    Writes it into that customer's `saved_payees`, so it shows up in their
    Kayıtlı İşlemler ready to pay -- and gives the admin panel the link it
    needs to say whose bill a subscriber number belongs to.
    """

    user_id: str
    institution: str = Field(..., min_length=1, max_length=80)
    subscriber_no: str = Field(..., min_length=1, max_length=40)
    label: Optional[str] = Field(default=None, max_length=80)


class SubscriptionOut(BaseModel):
    id: str
    user_id: str
    full_name: Optional[str] = None
    label: str
    institution: str
    subscriber_no: str


class IssueCardRequest(BaseModel):
    user_id: str
    name: str = Field(..., min_length=1, max_length=80)
    brand: str = Field(default="visa", max_length=20)
    credit_limit: float = Field(..., gt=0)
    #: Demo cards usually arrive with something owed, otherwise there is
    #: nothing to demonstrate paying.
    current_debt: float = Field(default=0, ge=0)
    due_day: int = Field(default=10, ge=1, le=31)


class IssueLoanRequest(BaseModel):
    user_id: str
    title: str = Field(..., min_length=1, max_length=80)
    principal: float = Field(..., gt=0)
    installment_count: int = Field(..., gt=0, le=360)
    installment_amount: Optional[float] = Field(default=None, gt=0)
