"""Operator endpoints.

Every route here is behind `require_admin`. None of them is exposed as an MCP
tool and none ever will be: the chatbot must have no path to crediting a
balance, however the conversation is phrased.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_admin_token, verify_password
from . import service
from .deps import require_admin
from .schemas import (
    AssignSubscriptionRequest,
    IssueCardRequest,
    IssueLoanRequest,
    SubscriptionOut,
    AdminLoginRequest,
    AdminTokenResponse,
    AdminUserRow,
    AdjustmentResult,
    BillListOut,
    BillOut,
    CashAdjustmentRequest,
    IssueBillRequest,
    PositionAdjustmentRequest,
)

log = logging.getLogger("moneyfast.admin")

router = APIRouter(tags=["Admin"])


@router.post("/login", response_model=AdminTokenResponse, summary="Yönetici girişi")
def admin_login(request: AdminLoginRequest, db: Session = Depends(get_db)):
    """Authenticate an administrator.

    Separate from `/api/auth/login` because the identities are separate: this
    resolves against `admin.admin_users` and mints a token the customer side
    refuses. A wrong username and a wrong password give the same answer -- the
    caller should not learn which administrators exist.
    """
    from .models import AdminUser

    administrator = (
        db.query(AdminUser).filter(AdminUser.username == request.username).first()
    )
    if (
        administrator is None
        or not administrator.is_active
        or not verify_password(request.password, administrator.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya parola hatalı.")

    return AdminTokenResponse(
        access_token=create_admin_token({"sub": administrator.username}),
        full_name=administrator.full_name,
    )


@router.get("/users", response_model=List[AdminUserRow], summary="Tüm müşteriler")
def list_users(db: Session = Depends(get_db), admin=Depends(require_admin)):
    """Every customer with their cash and portfolio value."""
    return [AdminUserRow(**row) for row in service.list_customers(db)]


@router.post(
    "/users/{user_id}/cash",
    response_model=AdjustmentResult,
    summary="Bakiye düzeltmesi",
)
def adjust_cash(
    user_id: str,
    request: CashAdjustmentRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Credit or debit a customer's deposit account.

    Goes through the banking ledger, so the movement appears in the customer's
    own statement. An adjustment they cannot see is one they cannot reconcile.
    """
    try:
        result = service.adjust_cash(
            db, user_id, request.amount, request.description, actor=admin.username,
            account_id=request.account_id,
        )
    except service.AdminActionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AdjustmentResult(**result)


@router.post(
    "/users/{user_id}/positions",
    response_model=AdjustmentResult,
    summary="Pozisyon düzeltmesi",
)
def adjust_position(
    user_id: str,
    request: PositionAdjustmentRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Grant or remove a holding, at the current market price."""
    try:
        result = service.adjust_position(
            db, user_id, request.symbol, request.quantity, actor=admin.username,
        )
    except service.AdminActionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AdjustmentResult(**result)


@router.post("/bills", response_model=BillOut, summary="Fatura tanımla")
def issue_bill(
    request: IssueBillRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Put a bill into the system, found later by its subscriber number."""
    try:
        bill = service.issue_bill(
            db,
            institution=request.institution,
            bill_type=request.bill_type,
            subscriber_no=request.subscriber_no,
            amount=request.amount,
            due_day=request.due_day,
            actor=admin.username,
            holder_name=request.holder_name,
        )
    except service.AdminActionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BillOut.model_validate(bill, from_attributes=True)


@router.get("/bills", response_model=BillListOut, summary="Tanımlı faturalar")
def list_bills(db: Session = Depends(get_db), admin=Depends(require_admin)):
    """Faturalar; üzerindeki ad, atandığı müşteri ve ödeyen kişiyle birlikte."""
    return BillListOut(bills=[BillOut(**row) for row in service.describe_bills(db)])


@router.get(
    "/users/{user_id}/accounts",
    summary="Müşterinin para gönderilebilir hesapları",
)
def user_accounts(
    user_id: str, db: Session = Depends(get_db), admin=Depends(require_admin),
):
    """Vadesiz, vadeli ve yatırım -- hangisine para yatırılacağı seçilebilsin."""
    from app.modules.banking import service as banking_service

    return banking_service.portfolio_accounts(db, user_id)


@router.post(
    "/subscriptions", response_model=SubscriptionOut, summary="Abone numarası ata",
)
def assign_subscription(
    request: AssignSubscriptionRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Bir abone numarasını müşteriye atar.

    Numara müşterinin Kayıtlı İşlemler'ine düşer, böylece demo sırasında tek
    dokunuşla ödenebilir; panel de faturanın kime ait olduğunu buradan çözer.
    """
    try:
        return SubscriptionOut(**service.assign_subscription(
            db, user_id=request.user_id, institution=request.institution,
            subscriber_no=request.subscriber_no, label=request.label,
        ))
    except service.AdminActionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/subscriptions", response_model=List[SubscriptionOut], summary="Atanmış abone numaraları",
)
def list_subscriptions(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    return [SubscriptionOut(**row) for row in service.list_subscriptions(db, user_id)]


@router.delete("/bills/{bill_id}", status_code=204, summary="Faturayı geri çek")
def withdraw_bill(
    bill_id: str, db: Session = Depends(get_db), admin=Depends(require_admin),
):
    try:
        removed = service.withdraw_bill(db, bill_id)
    except service.AdminActionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı.")


@router.post("/cards", summary="Kart tanımla")
def issue_card(
    request: IssueCardRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Müşteriye kredi kartı tanımlar."""
    from app.modules.banking import products

    try:
        card = products.issue_card(
            db, user_id=request.user_id, name=request.name, brand=request.brand,
            credit_limit=request.credit_limit, current_debt=request.current_debt,
            due_day=request.due_day,
        )
    except products.ProductError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": card.id, "name": card.name, "card_number": card.card_number}


@router.post("/loans", summary="Kredi tanımla")
def issue_loan(
    request: IssueLoanRequest,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """Müşteriye taksitli kredi tanımlar."""
    from app.modules.banking import products

    try:
        loan = products.issue_loan(
            db, user_id=request.user_id, title=request.title,
            principal=request.principal, installment_count=request.installment_count,
            installment_amount=request.installment_amount,
        )
    except products.ProductError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": loan.id, "title": loan.title, "remaining_amount": float(loan.remaining_amount)}
