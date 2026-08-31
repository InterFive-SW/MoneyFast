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
from app.core.deps import get_current_user_id, get_optional_user_id
from app.modules.market.router import require_service_token

from . import payments, products, service
from .models import AccountTransaction, BankTransaction
from .models import SavingsGoal
from .schemas import (
    BalanceHistoryOut,
    BankAccountOut,
    BillLookupOut,
    CardOut,
    CardSettingsRequest,
    LoanOut,
    PaymentConfirmOut,
    PaymentProposalOut,
    PortfolioAccountOut,
    SavePayeeRequest,
    SavedPayeeListOut,
    SavedPayeeOut,
    SavingsGoalIn,
    SavingsGoalOut,
    SpendingSummaryOut,
    StagePaymentRequest,
    StatementOut,
    TransferOut,
    TransferRequest,
)

router = APIRouter(tags=["banking"])


@router.get("/accounts", response_model=List[BankAccountOut], summary="Hesaplarım")
def list_accounts(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Kullanıcının mevduat hesapları. Yoksa açılır."""
    accounts = service.accounts_for(db, user_id)
    if not accounts:
        service.ensure_account(db, user_id)
        service.ensure_savings_account(db, user_id)
        db.commit()
        accounts = service.accounts_for(db, user_id)
    return accounts



@router.post(
    "/interest/accrue",
    summary="Vadeli hesap faizlerini işle (servis işi)",
)
def accrue_interest(
    db: Session = Depends(get_db),
    _: None = Depends(require_service_token),
):
    """Hak edilmiş günlük faizi işler.

    Servis işi: müşteri token'ıyla çağrılamaz. Faiz ödemek bir kullanıcı
    eylemi değil, bankanın işi -- ve müşteriye kendi faizini tetikleme yetkisi
    vermek, aynı günü tekrar tekrar denemesine davetiye olurdu (işlem
    `last_accrued_at` sayesinde günde bir kez yazsa bile).

    Aynı gün ikinci kez çalıştırmak hiçbir şey ödemez; iş güvenle
    tekrarlanabilir.
    """
    posted = service.accrue_interest(db)
    return {"accrued": len(posted), "movements": posted}

@router.get(
    "/accounts/all",
    response_model=List[PortfolioAccountOut],
    summary="Para gönderilebilecek tüm hesaplar",
)
def list_all_accounts(
    db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id),
):
    """Bankacılık hesapları VE yatırım hesabı, tek biçimde.

    Yatırım hesabının nakiti başka bir tabloda durur; transfer ekranının ve
    yönetim panelinin bunu bilmek zorunda kalmaması için burada tek şekle
    getiriliyor. `is_investment` hangisinin o olduğunu söyler.
    """
    return [
        PortfolioAccountOut(**row) for row in service.portfolio_accounts(db, user_id)
    ]


@router.post("/transfers", response_model=TransferOut, summary="Para transferi")
def create_transfer(
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
def statement(
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
def spending_summary(
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
def balance_history(
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
def list_savings_goals(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Kullanıcının koyduğu hedefler. Gözlem değil, niyet."""
    return service.goals_for(db, user_id)


@router.post("/savings-goals", response_model=SavingsGoalOut, summary="Birikim hedefi ekle")
def create_savings_goal(
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


# ---------------------------------------------------------------------------
# Bills, staged payments, saved payees
#
# Every route below moves money only through `payments.confirm`. Staging is
# deliberately inert: the assistant can prepare a payment, but pressing the
# button is the user's act, not the model's.
# ---------------------------------------------------------------------------


@router.get(
    "/bills/lookup", response_model=BillLookupOut, summary="Abone no ile fatura sorgula",
)
def lookup_bill(
    institution: str,
    subscriber_no: str,
    db: Session = Depends(get_db),
    _caller: Optional[str] = Depends(get_optional_user_id),
):
    """What is owed for a subscriber number.

    Found by number rather than owned by a user: that is how the paper works,
    and it is what makes a saved payee worth having.
    """
    bill = payments.find_open_bill(db, institution, subscriber_no)
    if bill is None:
        return BillLookupOut(found=False)
    return BillLookupOut(
        found=True, id=bill.id, institution=bill.institution,
        bill_type=bill.bill_type, subscriber_no=bill.subscriber_no,
        amount=float(bill.amount), due_day=bill.due_day,
    )


@router.post(
    "/payments/stage", response_model=PaymentProposalOut, summary="Ödeme önerisi hazırla",
)
def stage_payment(
    request: StagePaymentRequest,
    db: Session = Depends(get_db),
    authenticated_user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Prepare a payment. **Nothing moves.**

    Reachable two ways, and the difference matters. A signed-in customer calls
    it with their own token. `mcp` calls it with a SERVICE identity on behalf
    of whoever is chatting, naming them in the body -- the same arrangement
    `investment/transactions/stage` uses.

    A token, when present, always wins over the body. Trusting the body while
    a different user is authenticated would let anyone stage a payment in
    someone else's name.

    Note what is NOT relaxed here: `confirm` still demands a user token. The
    assistant may prepare a payment; only the person whose money it is can
    make it happen.
    """
    user_id = authenticated_user_id or request.user_id
    if authenticated_user_id and request.user_id and request.user_id != authenticated_user_id:
        raise HTTPException(
            status_code=403, detail="Bir başkası adına ödeme hazırlanamaz.",
        )
    if not user_id:
        raise HTTPException(status_code=401, detail="Kimlik doğrulanamadı.")

    try:
        proposal = payments.stage(
            db,
            user_id=user_id,
            payment_type=request.payment_type,
            amount=request.amount,
            destination=request.destination,
            institution=request.institution,
            subscriber_no=request.subscriber_no,
            description=request.description,
            idempotency_key=request.idempotency_key,
        )
    except payments.PaymentError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    payload = proposal.payload or {}
    return PaymentProposalOut(
        proposal_id=proposal.id,
        status=proposal.status,
        payment_type=proposal.payment_type,
        amount=float(proposal.amount),
        currency=proposal.currency_code,
        destination=proposal.destination_reference,
        description=payload.get("description"),
        expires_at=proposal.expires_at,
        balance_before=payload.get("balance_before"),
    )


@router.post(
    "/payments/{proposal_id}/confirm",
    response_model=PaymentConfirmOut,
    summary="Ödemeyi onayla",
)
def confirm_payment(
    proposal_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Apply a staged payment. The only route here that moves money."""
    try:
        result = payments.confirm(db, user_id, proposal_id)
    except payments.PaymentError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaymentConfirmOut(**result)


@router.post("/payments/{proposal_id}/cancel", status_code=204, summary="Öneriyi iptal et")
def cancel_payment(
    proposal_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    if not payments.cancel(db, user_id, proposal_id):
        raise HTTPException(status_code=404, detail="Öneri bulunamadı.")


@router.get(
    "/saved-payees", response_model=SavedPayeeListOut, summary="Kayıtlı işlemlerim",
)
def list_saved_payees(
    db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id),
):
    rows = payments.saved_payees(db, user_id)
    return SavedPayeeListOut(
        payees=[
            SavedPayeeOut(
                id=r.id, label=r.label, institution=r.institution,
                subscriber_no=r.subscriber_no,
            )
            for r in rows
        ]
    )


@router.post(
    "/saved-payees", response_model=SavedPayeeOut, summary="Kayıtlı işlem ekle",
)
def add_saved_payee(
    request: SavePayeeRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Keep a subscriber number. Saving the same one twice is a no-op."""
    payee = payments.save_payee(
        db, user_id, request.label, request.institution, request.subscriber_no,
    )
    return SavedPayeeOut(
        id=payee.id, label=payee.label, institution=payee.institution,
        subscriber_no=payee.subscriber_no,
    )


@router.delete("/saved-payees/{payee_id}", status_code=204, summary="Kayıtlı işlemi sil")
def remove_saved_payee(
    payee_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    if not payments.delete_payee(db, user_id, payee_id):
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı.")


# ---------------------------------------------------------------------------
# Cards and loans
# ---------------------------------------------------------------------------


@router.get("/cards", response_model=List[CardOut], summary="Kartlarım")
def list_cards(
    db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id),
):
    return [CardOut(**row) for row in products.cards_for(db, user_id)]


@router.patch(
    "/cards/{card_id}/settings", response_model=CardOut, summary="Kart ayarları",
)
def update_card_settings(
    card_id: str,
    request: CardSettingsRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Dondurma, temassız, internetten alışveriş.

    Gelen ayarlar saklananın ÜZERİNE yazılır: tek bir anahtarı gönderen bir
    ekran diğerlerini sıfırlamamalı.
    """
    try:
        products.update_card_settings(db, user_id, card_id, request.settings)
    except products.ProductError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    card = next(c for c in products.cards_for(db, user_id) if c["id"] == card_id)
    return CardOut(**card)


@router.delete("/cards/{card_id}", status_code=204, summary="Kartı kapat")
def close_card(
    card_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    try:
        closed = products.close_card(db, user_id, card_id)
    except products.ProductError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not closed:
        raise HTTPException(status_code=404, detail="Kart bulunamadı.")


@router.get("/loans", response_model=List[LoanOut], summary="Kredilerim")
def list_loans(
    db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id),
):
    return [LoanOut(**row) for row in products.loans_for(db, user_id)]
