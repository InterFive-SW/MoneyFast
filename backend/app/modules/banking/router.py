"""Banking uç noktaları — hesaplar ve transferler.

Transfer, sohbetteki işlem akışıyla aynı disiplini izler: para yalnızca
kullanıcının kendi eylemiyle hareket eder, ajan kendi başına transfer
başlatamaz.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id

from . import service
from .models import AccountTransaction, BankTransaction
from .schemas import BankAccountOut, StatementOut, TransferOut, TransferRequest

router = APIRouter(tags=["banking"])


@router.get("/accounts", response_model=List[BankAccountOut], summary="Hesaplarım")
async def list_accounts(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Kullanıcının mevduat hesapları. Yoksa açılır."""
    accounts = service.accounts_for(db, user_id)
    if not accounts:
        service.ensure_account(db, user_id)
        db.commit()
        accounts = service.accounts_for(db, user_id)
    return accounts


@router.post("/transfers", response_model=TransferOut, summary="Para transferi")
async def create_transfer(
    request: TransferRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Bir hesaptan diğerine para gönderir.

    İki bacak (DEBIT/CREDIT) ve işlem kaydı **tek** transaction içinde yazılır:
    borcu yazıp alacağı yazamamak, bir hesaptan çıkıp hiçbir yere varmamış para
    demek olurdu.

    `source` verilmezse kullanıcının kendi mevduat hesabı kullanılır — tek
    hesabı olan birine hesap numarasını sordurmak amaçsız bir sürtünme.
    """
    source = request.source
    if not source:
        own = service.ensure_account(db, user_id)
        db.commit()
        source = own.account_number

    try:
        return service.transfer(
            db,
            user_id=user_id,
            source_reference=source,
            destination_reference=request.destination,
            amount=request.amount,
            description=request.description,
        )
    except service.TransferError as exc:
        db.rollback()
        # 422: istek biçimsel olarak geçerli ama uygulanamaz (bakiye, hesap
        # durumu, aynı hesap). İstemcinin düzeltebileceği bir durum.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/accounts/{account_number}/statement",
    response_model=StatementOut,
    summary="Hesap hareketleri",
)
async def statement(
    account_number: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Hesabın hareket dökümü (FG-B-05)."""
    account = service.find_account(db, account_number)
    if account is None or account.user_id != user_id:
        # Başkasının hesabının var olduğunu doğrulamak bile fazla bilgi.
        raise HTTPException(status_code=404, detail="Hesap bulunamadı.")

    rows = db.execute(
        select(AccountTransaction, BankTransaction)
        .join(BankTransaction, BankTransaction.id == AccountTransaction.transaction_id)
        .where(AccountTransaction.account_id == account.id)
        .order_by(AccountTransaction.created_at.desc())
        .limit(limit)
    ).all()

    return {
        "account_number": account.account_number,
        "balance": float(account.balance),
        "currency_code": account.currency_code,
        "movements": [
            {
                "reference_number": transaction.reference_number,
                "direction": leg.direction,
                "amount": float(leg.amount),
                "balance_after": float(leg.balance_after),
                "counterparty_iban": leg.counterparty_iban,
                "description": leg.description,
                "created_at": leg.created_at,
            }
            for leg, transaction in rows
        ],
    }


@router.get("/health", summary="Banking modülü sağlık durumu")
async def health_check():
    """
    Banking modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "banking"}
