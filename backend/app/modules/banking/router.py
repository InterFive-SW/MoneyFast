"""Banking uç noktaları — hesaplar ve transferler.

Transfer, sohbetteki işlem akışıyla aynı disiplini izler: para yalnızca
kullanıcının kendi eylemiyle hareket eder, ajan kendi başına transfer
başlatamaz.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id

from . import service
from .models import AccountTransaction, BankTransaction
from .models import SavingsGoal
from .schemas import (
    BalanceHistoryOut,
    BankAccountOut,
    SavingsGoalIn,
    SavingsGoalOut,
    SpendingSummaryOut,
    StatementOut,
    TransferOut,
    TransferRequest,
)

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


@router.get("/spending", response_model=SpendingSummaryOut, summary="Aylık harcama özeti")
async def spending_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Kategorilere göre harcama — yalnızca DEBIT bacaklarından.

    Kendi hesapları arasındaki transfer hem borç hem alacak bacağı üretir;
    borç bacağını harcama saymak, kendi parasını taşımayı gider gibi
    gösterirdi. Kategorisi olmayan hareketler toplama girmez.
    """
    now = datetime.now(timezone.utc)
    window = timedelta(days=days)
    current = service.spending_by_category(db, user_id, since=now - window)
    previous = service.spending_by_category(db, user_id, since=now - 2 * window)

    total = sum(row["amount"] for row in current)
    # `previous` covers both windows, so the earlier one is the difference.
    earlier = sum(row["amount"] for row in previous) - total
    change = round((total - earlier) / earlier * 100, 2) if earlier else None

    return {
        "period": f"Son {days} gün",
        "currency_code": "TRY",
        "total_expense": round(total, 2),
        "change_percent": change,
        "categories": current,
    }


@router.get("/balance-history", response_model=BalanceHistoryOut, summary="Bakiye geçmişi")
async def balance_history(
    limit: int = Query(default=30, ge=2, le=200),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Her hareketten sonraki bakiye — `balance_after` sütunundan okunuyor.

    Hareketleri yeniden oynatarak hesaplamak yerine saklanan değeri okumak,
    o sütunun var olma sebebi.
    """
    points = service.balance_history(db, user_id, limit=limit)
    accounts = service.accounts_for(db, user_id)
    total = sum(float(account.balance) for account in accounts)

    first = points[0]["balance"] if points else None
    change_amount = round(total - first, 2) if first is not None else 0.0
    # Only meaningful against a positive starting balance. Dividing by zero or
    # by a negative opening balance produces a percentage that reads backwards.
    change_percent = (
        round(change_amount / first * 100, 2) if first and first > 0 else None
    )

    return {
        "currency_code": accounts[0].currency_code if accounts else "TRY",
        "total": round(total, 2),
        "change_amount": change_amount,
        "change_percent": change_percent,
        "points": points,
    }


@router.get("/savings-goals", response_model=List[SavingsGoalOut], summary="Birikim hedefleri")
async def list_savings_goals(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Kullanıcının koyduğu hedefler. Gözlem değil, niyet."""
    return service.goals_for(db, user_id)


@router.post("/savings-goals", response_model=SavingsGoalOut, summary="Birikim hedefi ekle")
async def create_savings_goal(
    request: SavingsGoalIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    goal = SavingsGoal(user_id=user_id, **request.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("/health", summary="Banking modülü sağlık durumu")
async def health_check():
    """
    Banking modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "banking"}
