"""Bekleyen limit emirlerini piyasa fiyatıyla eşleştiren iş.

Limit emri bir FİYATLAMA girdisi değil, bir TETİKLEYİCİ. Bu ayrım burada
yapılmasaydı bugünkü davranış sürerdi: `ai_service._estimate` limit fiyatı
gördüğünde onu referans fiyatın yerine koyuyor, dolayısıyla emir piyasa ne
olursa olsun kullanıcının yazdığı fiyattan ANINDA gerçekleşiyordu.

Akış:

    PENDING_USER_CONFIRMATION --onay--> WAITING_PRICE --eşleşme--> CONFIRMED
                                              |
                                              +--iptal--> CANCELLED (iade)

`block_funds` onay anında, `finalize_settlement` eşleşme anında,
`rollback_funds` iptalde çalışıyor; üçü de zaten vardı.

Durum veritabanında tutuluyor, bir `asyncio.sleep` içinde değil: eskiden
onaydan sonra 15 saniye uyuyan bir arka plan görevi vardı ve süreç o aralıkta
ölürse satır `PENDING` kalıyor, para bloke kalıyor ve onu bitirecek ya da geri
alacak hiçbir şey olmuyordu. Bir emir günlerce bekleyeceğine göre kalıcılık
şart.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.modules.market.models import Fund
from app.modules.notification.models import Notification

from . import ai_service, market_service, service
from .models import InvestmentProduct, TransactionProposal

log = logging.getLogger(__name__)

WAITING_PRICE = "WAITING_PRICE"

#: `PENDING` bir GEÇİŞ durumu: para bloke edilmiş, takas henüz yazılmamış.
#: Bu kadar dakikadır orada duran bir satır, süreç ölürken orada kalmıştır.
STALE_PENDING_MINUTES = 15

#: Fonun NAV'ı bundan eskiyse eşleşme yapılmıyor. Fon günde bir fiyat
#: yayımlıyor ve hafta sonu/tatil boşlukları normal; aylık eski bir NAV ise
#: veri akmıyor demektir ve o fiyattan doldurmak, bugün olmayan bir fiyattan
#: işlem uydurmak olurdu.
FUND_NAV_MAX_AGE_DAYS = 7


def is_match(transaction_type: str, market_price: float, limit_price: float) -> bool:
    """ALIŞ için `piyasa <= limit`, SATIŞ için `piyasa >= limit`."""
    kind = (transaction_type or "").upper()
    if kind in service.BUY_TYPES:
        return market_price <= limit_price
    if kind in service.SELL_TYPES:
        return market_price >= limit_price
    return False


def _fund_price(fund: Optional[Fund], today: date) -> Optional[float]:
    """Fonun bugün geçerli NAV'ı, ya da güvenilmiyorsa None."""
    if fund is None or fund.price is None or fund.as_of is None:
        return None
    if (today - fund.as_of).days > FUND_NAV_MAX_AGE_DAYS:
        return None
    return float(fund.price)


def _stock_price(
    symbol: str,
    product: InvestmentProduct,
    quotes: dict[str, dict[str, Any]],
    trading: Optional[set[str]],
) -> Optional[float]:
    """Hissenin eşleşmeye SAYILABİLİR fiyatı, ya da None.

    Üç ayrı ret sebebi var ve üçü de aynı şeyi söylüyor: şu an bu enstrüman
    için geçerli bir piyasa fiyatı yok.

    * Kotasyon yoksa.
    * Kotasyon BAYATSA -- bayat bir fiyat, o fiyata gelinmiş olduğunun kanıtı
      değil.
    * Borsa KAPALIYSA. `trading` None ise kapalılık İDDİA EDİLMİYOR (ingestor
      söylemiyor demektir) ve karar tazeliğe bırakılıyor; kapalı bir piyasada
      "fiyat geldi" demek, olmamış bir işlemi uydurmak olurdu.
    """
    quote = quotes.get(symbol)
    if quote is None or quote.get("price") is None:
        return None
    if trading is not None and (product.market or "").upper() not in trading:
        return None
    _, _, _, is_stale = market_service.freshness({symbol: quote})
    if is_stale:
        return None
    return float(quote["price"])


def _notify(db: Session, proposal: TransactionProposal, title: str, description: str, kind: str) -> None:
    db.add(
        Notification(
            user_id=proposal.user_id,
            title=title,
            description=description,
            type=kind,
            link_url="/portfolio",
        )
    )


def fill(db: Session, proposal: TransactionProposal, market_price: float) -> None:
    """Bir emri, eşleşmeyi sağlayan piyasa fiyatından doldurur.

    Öneri limit fiyattan hazırlandığı için bloke edilen nakit de o fiyattan
    hesaplanmıştı. Alışta piyasa limitin ALTINDA olduğu için gerçek maliyet
    daha düşük; aradaki fark iade edilmezse kullanıcının parası eşleşmeden
    sonra da tutulmuş olurdu.

    Commit ETMİYOR: durum değişikliği ile para hareketi tek transaction'da
    commit edilmeli, yoksa para hareket edip emir bekliyor görünebilir.
    """
    owner = market_service.account(db, user_id=proposal.user_id, allow_demo_fallback=False)
    if owner is None:
        raise service.SettlementError("Emri uygulayacak bir yatırım hesabı bulunamadı.")

    payload = dict(proposal.payload or {})
    old_estimate = payload.get("estimate") or {}
    blocked = service._cash_amount(old_estimate, owner)

    new_estimate = ai_service.reprice_estimate(
        old_estimate,
        proposal.transaction_type or "",
        float(proposal.quantity or 0),
        market_price,
    )
    if new_estimate is None:
        raise service.SettlementError("Emir yeniden fiyatlanamadı.")

    payload["estimate"] = new_estimate
    proposal.payload = payload

    quantity = float(proposal.quantity or 0)
    if (proposal.transaction_type or "").upper() in service.BUY_TYPES:
        refund = blocked - service._cash_amount(new_estimate, owner)
        # Negatif fark, dolumun bloke edilenden PAHALI olması demek --
        # eşleşme kuralı (`piyasa <= limit`) bunu imkânsız kılıyor, ama
        # olursa doğru cevap parayı fazladan almak değil, doldurmamak:
        # kullanıcı en çok limit fiyattan hesaplanmış maliyeti onayladı.
        if refund < -0.005:
            raise service.SettlementError(
                "Emrin maliyeti onaylanan tutarı aşıyor, dolum yapılmadı."
            )
        if refund > 0.005:
            before = float(owner.cash_balance)
            owner.cash_balance = before + refund
            service.record_cash_movement(
                db,
                owner,
                amount=refund,
                balance_before=before,
                balance_after=float(owner.cash_balance),
                description=f"Emir Dolumu Fark İadesi — {proposal.symbol} x{quantity:g}",
                reference=proposal.id,
                when=datetime.now(timezone.utc),
            )

    service.finalize_settlement(db, proposal, owner)
    proposal.status = "CONFIRMED"
    proposal.confirmed_at = datetime.now(timezone.utc)
    _notify(
        db,
        proposal,
        "Emriniz Gerçekleşti",
        f"{proposal.symbol} {market_service.direction_tr(proposal.transaction_type).lower()} "
        f"emriniz {quantity:g} adet, {market_price:,.2f} fiyattan gerçekleşti.",
        "SUCCESS",
    )


def run_matching(db: Session) -> dict[str, Any]:
    """Bekleyen bütün emirleri bir kez tarar.

    Sembolleri toplayıp TEK sorguda fiyatlıyor: emir başına kotasyon çekmek,
    aynı hisseyi bekleyen elli emirde elli sorgu demek olurdu.
    """
    waiting = (
        db.query(TransactionProposal)
        .filter(TransactionProposal.status == WAITING_PRICE)
        .all()
    )
    result: dict[str, Any] = {
        "scanned": len(waiting),
        "filled": 0,
        "skipped": 0,
        "failed": 0,
        "filled_ids": [],
    }
    if not waiting:
        return result

    symbols = sorted({p.symbol for p in waiting if p.symbol})
    products = {
        product.symbol: product
        for product in db.query(InvestmentProduct)
        .filter(InvestmentProduct.symbol.in_(symbols))
        .all()
    }
    quotes = market_service.latest_quotes(db, symbols)
    funds = {
        fund.code: fund
        for fund in db.query(Fund).filter(Fund.code.in_(symbols)).all()
    }
    trading = market_service.open_markets(db)
    today = datetime.now(timezone.utc).date()

    for proposal in waiting:
        product = products.get(proposal.symbol or "")
        if product is None or proposal.limit_price is None:
            result["skipped"] += 1
            continue

        if (product.product_type or "").lower() == "fund":
            price = _fund_price(funds.get(proposal.symbol or ""), today)
        else:
            price = _stock_price(proposal.symbol or "", product, quotes, trading)

        if price is None or not is_match(
            proposal.transaction_type or "", price, float(proposal.limit_price)
        ):
            result["skipped"] += 1
            continue

        try:
            fill(db, proposal, price)
            db.commit()
            result["filled"] += 1
            result["filled_ids"].append(proposal.id)
        except Exception as exc:  # noqa: BLE001 -- bir emir diğerlerini düşürmemeli
            db.rollback()
            log.error("Emir doldurulamadı %s: %s", proposal.id, exc)
            result["failed"] += 1

    return result


def sweep_stale_pending(db: Session) -> int:
    """Süreç ölürken `PENDING` kalmış satırların blokajını çözer.

    `PENDING` artık YAZILMIYOR: onay ya doğrudan gerçekleştiriyor (piyasa
    emri) ya da `WAITING_PRICE`a alıyor (limit emri). Bu süpürücü, eski
    yoldan -- onaydan sonra 15 saniye uyuyup takası yazan arka plan
    görevinden -- kalmış satırlar için. O görev süreç ölürken satırı `PENDING`
    bırakıyordu ve parayı serbest bırakacak hiçbir şey yoktu.

    Ölçüt `created_at`: öneri en fazla 15 dakika onaylanabiliyor
    (`expires_at`), dolayısıyla bundan eski bir `PENDING` satır artık
    ilerleyemez.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_PENDING_MINUTES)
    rows = (
        db.query(TransactionProposal)
        .filter(TransactionProposal.status == "PENDING")
        .filter(TransactionProposal.created_at < cutoff)
        .all()
    )
    released = 0
    for proposal in rows:
        owner = market_service.account(
            db, user_id=proposal.user_id, allow_demo_fallback=False
        )
        if owner is None:
            continue
        try:
            service.rollback_funds(db, proposal, owner)
            proposal.status = "FAILED"
            _notify(
                db,
                proposal,
                "Emir Tamamlanamadı",
                f"{proposal.symbol} emriniz tamamlanamadı; bloke edilen tutar iade edildi.",
                "ERROR",
            )
            db.commit()
            released += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.error("Bloke çözülemedi %s: %s", proposal.id, exc)
    return released


async def match_open_orders_job() -> None:
    """Scheduler girişi. Kendi oturumunu açıyor -- `send_daily_market_briefing_to_all`
    ile aynı desen; bir zamanlanmış işin isteğe bağlı bir `Session`'ı yok."""
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        summary = run_matching(db)
        summary["released"] = sweep_stale_pending(db)
        for proposal_id in summary["filled_ids"]:
            await _send_fill_email(db, proposal_id)
    log.info("Emir eşleştirme turu: %s", summary)


async def _send_fill_email(db: Session, proposal_id: str) -> None:
    """Dolan emrin bildirimi e-postayla da gider.

    Uygulama içi bildirim kullanıcı ekranı açtığında görünüyor; bir emir ise
    günler sonra ve kullanıcı bakmıyorken dolabiliyor. Hata YUTULUYOR: bir
    posta sunucusu arızası, gerçekleşmiş ve commit edilmiş bir emri geri
    almaz.
    """
    from app.core.email import send_transaction_email
    from app.modules.auth.models import User

    proposal = db.get(TransactionProposal, proposal_id)
    if proposal is None:
        return
    user = db.get(User, proposal.user_id)
    if user is None or not user.email:
        return
    prefs = getattr(user, "notification_preferences", {}) or {}
    if not prefs.get("transactions", {}).get("email", True):
        return

    quantity = float(proposal.quantity or 0)
    estimate = (proposal.payload or {}).get("estimate") or {}
    total = abs(float(estimate.get("net_amount", 0)))
    try:
        await send_transaction_email(
            email_to=user.email,
            transaction_type=proposal.transaction_type,
            asset_symbol=proposal.symbol,
            quantity=quantity,
            price=(total / quantity) if quantity else 0.0,
            total_amount=total,
            transaction_date=proposal.confirmed_at,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Dolum e-postası gönderilemedi %s: %s", proposal_id, exc)
