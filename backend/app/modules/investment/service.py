"""Settlement — the write side of a confirmed transaction.

Confirming a proposal used to set `status = 'CONFIRMED'` and commit. Nothing
else happened: cash was untouched, holdings were untouched, and the order list
then showed "Gerçekleşti" next to a trade that had changed nothing. An order
that reports itself executed while the portfolio disagrees is the exact
inconsistency FOG-GB-01 forbids, and it is worse than an error because nothing
signals it.

What settlement is and is not: this moves an internal ledger. No order reaches
a venue, nothing is routed to a custodian, and the prices are the delayed
reference prices the proposal was costed with. It makes the app's own numbers
agree with each other, which is all it claims to do.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    AllocationTarget,
    CashMovement,
    InvestmentAccount,
    InvestmentProduct,
    PortfolioPosition,
)

log = logging.getLogger("moneyfast.investment.settlement")

#: Transaction types that consume cash and add to a holding.
BUY_TYPES = frozenset({"BUY", "ALIS", "ALIŞ"})

#: Transaction types that release a holding and return cash.
SELL_TYPES = frozenset({"SELL", "SATIS", "SATIŞ"})

#: Quantities below this are treated as a closed position rather than a
#: residue. Float arithmetic on a full sell can leave 1e-15 behind, and a row
#: claiming a billionth of a share is noise pretending to be a holding.
DUST = 1e-9


#: Opening cash for a newly created account. Synthetic, like every other
#: balance in this system — see migration 0006 on where the fiction lives.
STARTING_CASH = 25000.0


class SettlementError(Exception):
    """The proposal cannot be settled. Carries a user-facing Turkish reason."""


def iban_for(account_number: str) -> str:
    """Yatırım hesabının sentetik ama biçimi doğru IBAN'ı.

    Kasıtlı olarak TR00: gerçek bir kontrol hanesi bu hesapları
    yönlendirilebilir gibi gösterirdi ve buradaki hiçbir şey bir ödeme ağına
    çıkmıyor. Numaranın kendisi değil özeti kullanılıyor -- `TR-0003-28BFBC42`
    gibi bir numarada yalnızca birkaç rakam var ve rakamları alıp doldurmak
    iki farklı hesabı aynı IBAN'a düşürebilirdi.

    `alembic/versions/0017_*.py` aynı hesabı yapıyor; ikisi ayrışırsa geri
    doldurulan IBAN ile yeni açılan hesabınki farklı biçimde olur.
    """
    digest = hashlib.sha256(str(account_number).encode("utf-8")).hexdigest()
    body = str(int(digest[:20], 16)).zfill(16)[:16]
    return f"TR00{body}00000{body[:2]}"


def record_cash_movement(
    db: Session,
    account: InvestmentAccount,
    *,
    amount: float,
    balance_before: float,
    balance_after: float,
    description: str,
    reference: Optional[str] = None,
    when: Optional[datetime] = None,
) -> CashMovement:
    """Nakit defterine tek satır yazar. Commit ETMEZ -- çağıran sahibidir.

    Bakiyeyi değiştiren her yol buradan geçmeli. Üç yazar vardı (takas,
    bankacılık köprüsü, yönetici düzeltmesi) ve hiçbiri iz bırakmadığı için
    hesabın gösterebileceği bir hareket dökümü yoktu.

    Yön tutardan değil, bakiyenin gidiş yönünden okunur: `amount` işaretli
    gelir, artı ise para girmiştir.
    """
    movement = CashMovement(
        account_id=account.id,
        direction="CREDIT" if amount >= 0 else "DEBIT",
        amount=abs(round(float(amount), 2)),
        balance_before=round(float(balance_before), 2),
        balance_after=round(float(balance_after), 2),
        reference=reference,
        description=description[:255],
        created_at=when or datetime.now(timezone.utc),
    )
    db.add(movement)
    return movement


def ensure_account(db: Session, user_id: str) -> InvestmentAccount:
    """The user's investment account, created if they do not have one yet.

    Called at registration so cash and holdings are per-user from the first
    login. Before this there was a single shared account, which meant one
    person's purchase spent everybody's money.

    Does not commit — the caller owns the transaction.
    """
    existing = (
        db.query(InvestmentAccount)
        .filter(InvestmentAccount.user_id == user_id)
        .first()
    )
    if existing is not None:
        return existing

    account = InvestmentAccount(
        user_id=user_id,
        # Unique per account and stable: derived from the user id rather than
        # a counter, so two concurrent registrations cannot collide on it.
        account_number=f"TR-{str(user_id).replace('-', '')[:12].upper()}",
        iban=iban_for(f"TR-{str(user_id).replace('-', '')[:12].upper()}"),
        name="Yatırım Hesabı",
        currency_code="TRY",
        cash_balance=STARTING_CASH,
        status="active",
    )
    db.add(account)
    log.info("created investment account for user %s", user_id)
    return account



def cash_statement(
    db: Session, account: InvestmentAccount, limit: int = 50
) -> dict:
    """Yatırım hesabının hareket dökümü.

    Defterden okunur, bakiyeden yeniden oynatılarak üretilmez: bakiyeyi üç ayrı
    yer yazıyor ve biri (yönetici düzeltmesi) hiçbir zaman bir işleme
    bağlanmıyor, dolayısıyla geriye doğru hesap sessizce kayardı.

    Karşı taraf alanı bilerek doldurulmuyor: bir alım işleminin karşısında bir
    IBAN yoktur, açıklama zaten enstrümanı söylüyor.
    """
    rows = (
        db.query(CashMovement)
        .filter(CashMovement.account_id == account.id)
        .order_by(CashMovement.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "account_number": account.account_number,
        "iban": account.iban or iban_for(account.account_number),
        "balance": float(account.cash_balance),
        "currency_code": account.currency_code or "TRY",
        "movements": [
            {
                "reference_number": row.reference,
                "direction": row.direction,
                "amount": float(row.amount),
                "balance_after": float(row.balance_after),
                "counterparty_iban": None,
                "description": row.description,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }

def _position(
    db: Session, account_id: str, product_id: str
) -> Optional[PortfolioPosition]:
    return (
        db.query(PortfolioPosition)
        .filter(
            PortfolioPosition.investment_account_id == account_id,
            PortfolioPosition.product_id == product_id,
        )
        .first()
    )


def _cash_amount(estimate: dict, account: InvestmentAccount) -> float:
    """`net_amount` expressed in the ACCOUNT's currency.

    The instrument's currency and the account's are different things: AAPL is
    priced in USD, the account holds TRY. Applying `net_amount` directly to
    `cash_balance` debited 315 TL for a 15.098 TL purchase and — far worse —
    credited 4.723 TL for a 226.468 TL sale.

    The rate is read from the proposal, not fetched fresh: the user approved a
    cost computed at staging time, and a rate that moved since then would change
    the amount they agreed to.
    """
    amount = float(estimate["net_amount"])
    trade_currency = estimate.get("currency") or account.currency_code
    account_currency = account.currency_code or "TRY"
    if trade_currency == account_currency:
        return amount

    fx = estimate.get("fx") or {}
    rate = fx.get("rate")
    if (
        rate is None
        or fx.get("from_currency") != trade_currency
        or fx.get("to_currency") != account_currency
    ):
        # Without the rate the proposal was priced at, this trade cannot be
        # applied at all. Refusing is the only safe outcome — settling at 1.0
        # is what destroyed 97% of a foreign position's value.
        raise SettlementError(
            f"Bu öneri {trade_currency} cinsinden hazırlanmış ama hesabınız "
            f"{account_currency}; uygulanacak kur bilgisi eksik olduğu için "
            f"işlem tamamlanamadı."
        )
    return amount * float(rate)


def settle(db: Session, proposal, account: InvestmentAccount) -> dict:
    """Apply a confirmed proposal to cash and holdings.

    Does NOT commit. The caller commits once, together with the proposal's
    status change, so a crash between the two cannot leave money moved and the
    proposal still pending — or the reverse.

    Returns a summary of what moved, for the confirmation message.
    """
    transaction_type = (proposal.transaction_type or "").upper()
    estimate = (proposal.payload or {}).get("estimate") or {}
    net_amount = estimate.get("net_amount")

    if net_amount is None:
        # Re-pricing here would settle at a figure the user never saw. The
        # proposal is costed at staging time and that is the number they
        # approved.
        raise SettlementError("Bu önerinin tutar bilgisi eksik, işlem uygulanamadı.")

    # Two amounts, deliberately kept apart:
    #   cash_amount  -- the account's currency, the only thing cash_balance can
    #                   be compared or added to.
    #   native_amount -- the instrument's currency, which is what the cost
    #                   basis is denominated in.
    native_amount = float(net_amount)
    cash_amount = _cash_amount(estimate, account)
    quantity = float(proposal.quantity or 0)

    if transaction_type in BUY_TYPES:
        return _settle_buy(db, proposal, account, cash_amount, quantity, native_amount)
    if transaction_type in SELL_TYPES:
        return _settle_sell(db, proposal, account, cash_amount, quantity)

    # Transfers and anything else reach confirm without a settlement path. The
    # banking module does not exist, so pretending one had run would be the
    # same lie in a new place.
    raise SettlementError(
        f"'{transaction_type or 'bilinmeyen'}' türü için uygulanabilir bir takas adımı yok."
    )


def _product(db: Session, symbol: str) -> InvestmentProduct:
    product = (
        db.query(InvestmentProduct).filter(InvestmentProduct.symbol == symbol).first()
    )
    if product is None:
        raise SettlementError(f"{symbol} için enstrüman kaydı bulunamadı.")
    return product


def _settle_buy(
    db: Session,
    proposal,
    account: InvestmentAccount,
    net_amount: float,
    quantity: float,
    native_amount: Optional[float] = None,
) -> dict:
    cash = float(account.cash_balance)
    if net_amount > cash:
        # Checked again here, not only at staging. Two proposals can be staged
        # against the same balance before either is confirmed, and the second
        # one must not overdraw the account.
        currency = account.currency_code or "TRY"
        raise SettlementError(
            f"Bakiye yetersiz: işlem {net_amount:,.2f} {currency} tutuyor, "
            f"hesabınızda {cash:,.2f} {currency} var."
        )

    product = _product(db, proposal.symbol)
    position = _position(db, account.id, product.id)
    now = datetime.now(timezone.utc)

    if position is None:
        db.add(
            PortfolioPosition(
                investment_account_id=account.id,
                product_id=product.id,
                quantity=quantity,
                # Cost basis is the reference price, not the all-in net. Fees
                # are an expense, not part of what the shares are worth, and
                # folding them in would overstate the break-even price.
                average_buy_price=_reference_price(proposal, native_amount, quantity),
                opened_at=now,
                updated_at=now,
            )
        )
    else:
        held = float(position.quantity)
        new_quantity = held + quantity
        # Weighted average: the old basis keeps its weight in the shares it
        # applies to. Overwriting with the latest price would erase the
        # history of what the position actually cost.
        position.average_buy_price = (
            float(position.average_buy_price) * held
            + _reference_price(proposal, native_amount, quantity) * quantity
        ) / new_quantity
        position.quantity = new_quantity
        position.updated_at = now

    account.cash_balance = cash - net_amount
    record_cash_movement(
        db,
        account,
        amount=-net_amount,
        balance_before=cash,
        balance_after=float(account.cash_balance),
        description=f"Alım — {proposal.symbol} x{quantity:g}",
        reference=proposal.id,
        when=now,
    )
    log.info(
        "settled BUY %s x%s for %s, cash %.2f -> %.2f",
        proposal.symbol, quantity, proposal.id, cash, float(account.cash_balance),
    )
    return {
        "direction": "BUY",
        "symbol": proposal.symbol,
        "quantity": quantity,
        "cash_delta": -net_amount,
        "cash_after": float(account.cash_balance),
    }


def _settle_sell(
    db: Session, proposal, account: InvestmentAccount, net_amount: float, quantity: float
) -> dict:
    product = _product(db, proposal.symbol)
    position = _position(db, account.id, product.id)
    held = float(position.quantity) if position is not None else 0.0

    if quantity > held:
        raise SettlementError(
            f"Satılabilir miktar yetersiz: {proposal.symbol} için {held:g} adet var, "
            f"{quantity:g} adet satılmak isteniyor."
        )

    cash = float(account.cash_balance)
    remaining = held - quantity
    if remaining <= DUST:
        # The position is closed. Average cost has no meaning without shares,
        # so the row goes rather than lingering at quantity zero.
        db.delete(position)
    else:
        position.quantity = remaining
        # Average cost is unchanged by a sale: selling does not alter what the
        # remaining shares cost to acquire.
        position.updated_at = datetime.now(timezone.utc)

    account.cash_balance = cash + net_amount
    record_cash_movement(
        db,
        account,
        amount=net_amount,
        balance_before=cash,
        balance_after=float(account.cash_balance),
        description=f"Satım — {proposal.symbol} x{quantity:g}",
        reference=proposal.id,
    )
    log.info(
        "settled SELL %s x%s for %s, cash %.2f -> %.2f",
        proposal.symbol, quantity, proposal.id, cash, float(account.cash_balance),
    )
    return {
        "direction": "SELL",
        "symbol": proposal.symbol,
        "quantity": quantity,
        "cash_delta": net_amount,
        "cash_after": float(account.cash_balance),
    }


def _reference_price(proposal, native_amount: Optional[float], quantity: float) -> float:
    """Per-share price the proposal was costed at, in the INSTRUMENT's currency.

    Deliberately not converted: `average_buy_price` sits beside a price feed
    quoted in the instrument's own currency, and `build_portfolio` converts the
    pair together at read time. Converting here would double-convert the P&L.

    Prefers the stored reference price; falls back to dividing the net by the
    quantity so a proposal missing that field still books a sane basis rather
    than zero.
    """
    estimate = (proposal.payload or {}).get("estimate") or {}
    price = estimate.get("reference_price")
    if price is not None:
        return float(price)
    if native_amount is None or not quantity:
        return 0.0
    return native_amount / quantity

def block_funds(db: Session, proposal, account: InvestmentAccount) -> dict:
    """
    Finansal Güvenlik (Phase 1): İşlem 'PENDING' durumuna alınırken bakiye veya hisse blokajı.
    
    Alım işlemlerinde nakit anında düşülür (çift harcamayı önlemek için).
    Satım işlemlerinde hisse adedi anında düşülür (çift satışı önlemek için).
    
    Hata fırlatırsa bakiye/hisse yetersiz demektir ve işlem reddedilir.
    """
    transaction_type = (proposal.transaction_type or "").upper()
    estimate = (proposal.payload or {}).get("estimate") or {}
    net_amount = estimate.get("net_amount")
    
    if net_amount is None:
        raise SettlementError("Bu önerinin tutar bilgisi eksik, işlem uygulanamadı.")
        
    cash_amount = _cash_amount(estimate, account)
    quantity = float(proposal.quantity or 0)
    now = datetime.now(timezone.utc)
    
    if transaction_type in BUY_TYPES:
        cash = float(account.cash_balance)
        if cash_amount > cash:
            currency = account.currency_code or "TRY"
            raise SettlementError(
                f"Bakiye yetersiz: işlem {cash_amount:,.2f} {currency} tutuyor, "
                f"hesabınızda {cash:,.2f} {currency} var."
            )
        # Nakit blokajı
        account.cash_balance = cash - cash_amount
        record_cash_movement(
            db, account, amount=-cash_amount, balance_before=cash, balance_after=float(account.cash_balance),
            description=f"Alım İşlemi Blokesi — {proposal.symbol} x{quantity:g}",
            reference=proposal.id, when=now
        )
        log.info("BLOCKED BUY cash for %s", proposal.id)
        return {"cash_after": float(account.cash_balance), "cash_delta": -cash_amount}
        
    if transaction_type in SELL_TYPES:
        product = _product(db, proposal.symbol)
        position = _position(db, account.id, product.id)
        held = float(position.quantity) if position is not None else 0.0
        if quantity > held:
            raise SettlementError(
                f"Satılabilir miktar yetersiz: {proposal.symbol} için {held:g} adet var, "
                f"{quantity:g} adet satılmak isteniyor."
            )
        # Hisse blokajı
        remaining = held - quantity
        if remaining <= DUST:
            db.delete(position)
        else:
            position.quantity = remaining
            position.updated_at = now
        log.info("BLOCKED SELL shares for %s", proposal.id)
        return {"cash_after": float(account.cash_balance), "cash_delta": 0.0}
        
    raise SettlementError(f"'{transaction_type or 'bilinmeyen'}' türü için blokaj adımı yok.")

def finalize_settlement(db: Session, proposal, account: InvestmentAccount) -> dict:
    """
    Finansal Güvenlik (Phase 2 - Başarılı): 'PENDING' süresi dolduğunda işlemi tamamla.
    
    Alım işlemlerinde bloke edilen nakit karşılığında hisse teslim edilir.
    Satım işlemlerinde bloke edilen hisse karşılığında nakit teslim edilir.
    """
    transaction_type = (proposal.transaction_type or "").upper()
    estimate = (proposal.payload or {}).get("estimate") or {}
    native_amount = float(estimate.get("net_amount", 0))
    cash_amount = _cash_amount(estimate, account)
    quantity = float(proposal.quantity or 0)
    now = datetime.now(timezone.utc)
    cash = float(account.cash_balance)
    
    if transaction_type in BUY_TYPES:
        product = _product(db, proposal.symbol)
        position = _position(db, account.id, product.id)
        if position is None:
            db.add(
                PortfolioPosition(
                    investment_account_id=account.id, product_id=product.id, quantity=quantity,
                    average_buy_price=_reference_price(proposal, native_amount, quantity),
                    opened_at=now, updated_at=now
                )
            )
        else:
            held = float(position.quantity)
            new_quantity = held + quantity
            position.average_buy_price = (
                float(position.average_buy_price) * held + _reference_price(proposal, native_amount, quantity) * quantity
            ) / new_quantity
            position.quantity = new_quantity
            position.updated_at = now
        log.info("FINALIZED BUY shares for %s", proposal.id)
        return {"cash_after": float(account.cash_balance), "cash_delta": 0.0}

    if transaction_type in SELL_TYPES:
        account.cash_balance = cash + cash_amount
        record_cash_movement(
            db, account, amount=cash_amount, balance_before=cash, balance_after=float(account.cash_balance),
            description=f"Satım İşlemi (Gerçekleşen) — {proposal.symbol} x{quantity:g}",
            reference=proposal.id, when=now
        )
        log.info("FINALIZED SELL cash for %s", proposal.id)
        return {"cash_after": float(account.cash_balance), "cash_delta": cash_amount}

    raise SettlementError("Bilinmeyen işlem türü.")

def rollback_funds(db: Session, proposal, account: InvestmentAccount) -> None:
    """
    Finansal Güvenlik (Phase 2 - Başarısız): İşlem iptal olursa bloke edilen varlığı geri ver.
    
    Alım işlemlerinde düşülen nakit iade edilir.
    Satım işlemlerinde düşülen hisse iade edilir.
    """
    transaction_type = (proposal.transaction_type or "").upper()
    estimate = (proposal.payload or {}).get("estimate") or {}
    cash_amount = _cash_amount(estimate, account)
    quantity = float(proposal.quantity or 0)
    now = datetime.now(timezone.utc)
    cash = float(account.cash_balance)
    
    if transaction_type in BUY_TYPES:
        account.cash_balance = cash + cash_amount
        record_cash_movement(
            db, account, amount=cash_amount, balance_before=cash, balance_after=float(account.cash_balance),
            description=f"Alım İptali (İade) — {proposal.symbol} x{quantity:g}",
            reference=proposal.id, when=now
        )
        log.info("ROLLED BACK BUY cash for %s", proposal.id)

    elif transaction_type in SELL_TYPES:
        product = _product(db, proposal.symbol)
        position = _position(db, account.id, product.id)
        if position is None:
            db.add(
                PortfolioPosition(
                    investment_account_id=account.id, product_id=product.id, quantity=quantity,
                    average_buy_price=_reference_price(proposal, float(estimate.get("net_amount", 0)), quantity),
                    opened_at=now, updated_at=now
                )
            )
        else:
            position.quantity = float(position.quantity) + quantity
            position.updated_at = now
        log.info("ROLLED BACK SELL shares for %s", proposal.id)


def allocation_targets(db: Session, user_id: Optional[str]) -> dict[str, float]:
    """Kullanıcının kendi belirlediği hedef ağırlıklar, kova -> yüzde.

    Burada, router'da değil: risk modülü de bunu okuyor ve modüller
    birbirinin ORM sınıfını import etmiyor (bkz. CLAUDE.md shared/ kuralı).
    Tabloyu sahibi olan modül okur, çağıran düz bir sözlük alır.
    """
    if not user_id:
        return {}
    rows = (
        db.query(AllocationTarget)
        .filter(AllocationTarget.user_id == user_id)
        .all()
    )
    return {row.bucket: float(row.target_percent) for row in rows}
