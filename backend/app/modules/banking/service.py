"""Transfers, as a double-entry ledger.

Every rule here exists because its absence has a specific failure mode:

* Both legs and the transaction row commit **together**. Committing the debit
  before the credit leaves money that has left one account and arrived nowhere.
* The balance is re-read inside the transaction, not trusted from a staging
  check. Two transfers staged against the same balance would otherwise both
  pass and overdraw the account.
* A transfer to yourself is refused rather than silently netting to zero — it
  is always a mistake, and processing it produces a ledger entry that says
  nothing happened.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AccountTransaction, BankAccount, BankTransaction, SavingsGoal

log = logging.getLogger("moneyfast.banking")

#: Opening balance for a new deposit account. Synthetic, like every figure in
#: this system.
STARTING_BALANCE = 50000.0

#: What a transfer costs. Zero between a user's own accounts — charging someone
#: to move their own money between their own accounts is a fee with no service
#: behind it.
TRANSFER_FEE = 0.0
EXTERNAL_TRANSFER_FEE = 2.50


class TransferError(Exception):
    """The transfer cannot be made. Carries a user-facing Turkish reason."""


def _digits_for(user_id: str, length: int) -> str:
    """A stable digit string derived from the user id.

    Hashed rather than sliced. Account numbers and IBANs are numeric, but user
    ids are hex — taking the id's own characters kept only its digits, so two
    users whose ids differed solely in their letters produced the SAME IBAN and
    the second account hit the unique constraint at registration.
    """
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    return str(int(digest[:16], 16)).zfill(length)[:length]


def _iban_for(account_number: str) -> str:
    """A synthetic but well-formed IBAN.

    Deliberately marked TR00 — a real check digit would make these look like
    routable accounts, and nothing here reaches a payment network.
    """
    body = "".join(ch for ch in account_number if ch.isdigit()).zfill(16)[-16:]
    return f"TR00{body}00000{body[:2]}"


def ensure_account(db: Session, user_id: str) -> BankAccount:
    """The user's deposit account, opened if they have none.

    Does not commit — the caller owns the transaction.
    """
    existing = (
        db.query(BankAccount)
        .filter(BankAccount.user_id == user_id, BankAccount.account_type == "vadesiz")
        .first()
    )
    if existing is not None:
        return existing

    number = f"1{_digits_for(user_id, 12)}"
    account = BankAccount(
        user_id=user_id,
        account_number=number,
        iban=_iban_for(number),
        account_type="vadesiz",
        currency_code="TRY",
        balance=STARTING_BALANCE,
        status="active",
    )
    db.add(account)
    log.info("opened deposit account for user %s", user_id)
    return account


def ensure_savings_account(db: Session, user_id: str) -> BankAccount:
    """The user's `vadeli` account, opened if they have none.

    Opened empty. A savings account that arrives with money in it is a gift,
    not a savings account -- the balance should be whatever the user moved
    into it.
    """
    existing = (
        db.query(BankAccount)
        .filter(BankAccount.user_id == user_id, BankAccount.account_type == "vadeli")
        .first()
    )
    if existing is not None:
        return existing

    number = f"2{_digits_for(user_id, 12)}"
    account = BankAccount(
        user_id=user_id,
        account_number=number,
        iban=_iban_for(number),
        account_type="vadeli",
        currency_code="TRY",
        balance=0,
        status="active",
    )
    db.add(account)
    log.info("opened savings account for user %s", user_id)
    return account


def accounts_for(db: Session, user_id: str) -> list[BankAccount]:
    """Every REAL banking account row. Not the investment account.

    The investment account's cash lives in `investment.investment_accounts`
    and is deliberately not copied here; see `portfolio_accounts` for the
    display list that includes it.
    """
    return (
        db.query(BankAccount)
        .filter(BankAccount.user_id == user_id)
        .order_by(BankAccount.created_at)
        .all()
    )


def deposit_account(db: Session, user_id: str) -> Optional[BankAccount]:
    """The user's `vadesiz` account -- the one money moves through by default.

    Callers used to say `accounts_for(...)[0]` and mean this. That worked only
    because everyone had exactly one account; the moment a `vadeli` account
    exists, "first by creation date" is a coincidence rather than a rule, and
    a payment could be staged against the wrong pot.
    """
    return (
        db.query(BankAccount)
        .filter(
            BankAccount.user_id == user_id,
            BankAccount.account_type == "vadesiz",
        )
        .order_by(BankAccount.created_at)
        .first()
    )


#: What the investment account looks like in an account list. It is NOT a
#: `banking.accounts` row and must never be treated as one -- its balance is
#: `investment_accounts.cash_balance`, which `settle()` reads directly.
INVESTMENT_ACCOUNT_TYPE = "yatirim"


def portfolio_accounts(db: Session, user_id: str) -> list[dict[str, Any]]:
    """Every account the user can see or move money between.

    Banking rows plus the investment account, in one shape, so the transfer
    screen and the admin panel do not each have to know that investment cash
    lives somewhere else. `is_investment` marks the one that does.
    """
    from app.modules.investment import market_service
    from app.modules.investment import service as investment_service

    rows: list[dict[str, Any]] = [
        {
            "id": account.id,
            "account_number": account.account_number,
            "iban": account.iban,
            "account_type": account.account_type,
            "currency_code": account.currency_code,
            "balance": float(account.balance),
            "interest_rate": (
                float(account.interest_rate) if account.interest_rate is not None else None
            ),
            "term_days": account.term_days,
            "is_investment": False,
        }
        for account in accounts_for(db, user_id)
    ]

    owner = market_service.account(db, user_id=user_id, allow_demo_fallback=False)
    if owner is not None:
        rows.append({
            "id": owner.id,
            "account_number": owner.account_number,
            # Artık gerçek: hesap "para gönder" ekranında adreslenebilsin ve
            # bankacılık arayüzü dökümünü isteyebilsin diye (migration 0017).
            "iban": owner.iban or investment_service.iban_for(owner.account_number),
            "account_type": INVESTMENT_ACCOUNT_TYPE,
            "currency_code": owner.currency_code or "TRY",
            "balance": float(owner.cash_balance),
            "is_investment": True,
        })
    return rows


def find_account(db: Session, reference: str) -> Optional[BankAccount]:
    """Resolve an account by number or IBAN.

    People paste either, and with or without spaces.
    """
    cleaned = (reference or "").replace(" ", "").strip().upper()
    if not cleaned:
        return None
    return (
        db.query(BankAccount)
        .filter(
            (BankAccount.account_number == cleaned) | (BankAccount.iban == cleaned)
        )
        .first()
    )


def _reference_number() -> str:
    return f"TRF-{secrets.token_hex(6).upper()}"


def transfer(
    db: Session,
    user_id: str,
    source_reference: str,
    destination_reference: str,
    amount: float,
    description: Optional[str] = None,
) -> dict:
    """Move money between two accounts, both legs in one transaction.

    Commits once at the end. A failure at any point leaves both balances as
    they were, which is the only acceptable outcome for a half-applied
    transfer.
    """
    if amount is None or amount <= 0:
        raise TransferError("Transfer tutarı sıfırdan büyük olmalı.")

    # Either side may be the investment account, which is not a banking row.
    # Routed here rather than in the router so every caller -- the panel, the
    # chat's confirm, the admin -- gets the same behaviour.
    from app.modules.investment import market_service

    investment = market_service.account(db, user_id=user_id, allow_demo_fallback=False)
    investment_number = investment.account_number if investment is not None else None

    def _is_investment(reference: Optional[str]) -> bool:
        cleaned = (reference or "").replace(" ", "").strip().upper()
        return bool(investment_number) and cleaned == investment_number.upper()

    if _is_investment(destination_reference) or _is_investment(source_reference):
        to_investment = _is_investment(destination_reference)
        other = source_reference if to_investment else destination_reference
        bank_account = find_account(db, other)
        if bank_account is None:
            raise TransferError(f"Hesap bulunamadı: {other}")
        if _is_investment(source_reference) and _is_investment(destination_reference):
            raise TransferError("Gönderen ve alıcı hesap aynı olamaz.")
        return transfer_with_investment(
            db, user_id=user_id, bank_account=bank_account, amount=amount,
            to_investment=to_investment, description=description,
        )

    source = find_account(db, source_reference)
    if source is None:
        raise TransferError(f"Gönderen hesap bulunamadı: {source_reference}")
    if source.user_id != user_id:
        # Indistinguishable from "not found" on purpose: confirming that an
        # account exists but belongs to someone else is already more than the
        # caller should learn.
        raise TransferError(f"Gönderen hesap bulunamadı: {source_reference}")
    if source.status != "active":
        raise TransferError("Gönderen hesap aktif değil.")

    destination = find_account(db, destination_reference)
    if destination is None:
        raise TransferError(f"Alıcı hesap bulunamadı: {destination_reference}")
    if destination.status != "active":
        raise TransferError("Alıcı hesap aktif değil.")

    if destination.id == source.id:
        raise TransferError("Gönderen ve alıcı hesap aynı olamaz.")

    if source.currency_code != destination.currency_code:
        # Cross-currency transfer needs a rate and a disclosed conversion.
        # Refusing is honest; applying 1:1 is the bug this codebase already
        # paid for once on the trading side.
        raise TransferError(
            f"Farklı para birimleri arasında transfer desteklenmiyor "
            f"({source.currency_code} → {destination.currency_code})."
        )

    fee = TRANSFER_FEE if source.user_id == destination.user_id else EXTERNAL_TRANSFER_FEE
    total = round(float(amount) + fee, 2)

    source_before = float(source.balance)
    if total > source_before:
        # İK-07: the balance must cover the amount AND the fee.
        raise TransferError(
            f"Bakiye yetersiz: transfer ücretle birlikte {total:,.2f} "
            f"{source.currency_code} tutuyor, hesabınızda "
            f"{source_before:,.2f} {source.currency_code} var."
        )

    destination_before = float(destination.balance)
    now = datetime.now(timezone.utc)

    record = BankTransaction(
        reference_number=_reference_number(),
        transaction_type="havale" if source.user_id != destination.user_id else "virman",
        status="completed",
        amount=round(float(amount), 2),
        currency_code=source.currency_code,
        description=description,
        completed_at=now,
    )
    db.add(record)
    db.flush()  # the legs need the transaction id

    source.balance = round(source_before - total, 2)
    destination.balance = round(destination_before + float(amount), 2)
    source.updated_at = now
    destination.updated_at = now

    db.add(
        AccountTransaction(
            transaction_id=record.id,
            account_id=source.id,
            direction="DEBIT",
            amount=total,
            balance_before=source_before,
            balance_after=float(source.balance),
            counterparty_iban=destination.iban,
            description=description,
            created_at=now,
        )
    )
    db.add(
        AccountTransaction(
            transaction_id=record.id,
            account_id=destination.id,
            direction="CREDIT",
            amount=round(float(amount), 2),
            balance_before=destination_before,
            balance_after=float(destination.balance),
            counterparty_iban=source.iban,
            description=description,
            created_at=now,
        )
    )

    db.commit()
    log.info(
        "transfer %s: %s -> %s, %.2f (fee %.2f)",
        record.reference_number, source.account_number,
        destination.account_number, amount, fee,
    )
    return {
        "reference_number": record.reference_number,
        "status": "completed",
        "amount": round(float(amount), 2),
        "fee": fee,
        "currency": source.currency_code,
        "source_balance_after": float(source.balance),
        "destination_account": destination.account_number,
    }


def transfer_with_investment(
    db: Session,
    user_id: str,
    bank_account: BankAccount,
    amount: float,
    *,
    to_investment: bool,
    description: Optional[str] = None,
) -> dict:
    """Move money between a banking account and the investment account.

    This is the bridge that was missing: investment cash lives in
    `investment.investment_accounts.cash_balance`, a different table from
    `banking.accounts.balance`, so no amount of transferring between banking
    accounts could ever fund a trade. That is why "add money" reached the
    deposit account and the portfolio never saw it.

    Both sides move in ONE transaction. A commit between them would leave
    money that has left the deposit account and not arrived at the investment
    one -- the exact failure the double-entry ledger exists to prevent.

    Only the banking leg is written to the ledger, because only the banking
    side has one; the investment side is a single balance the settlement code
    already owns. The leg still records before/after, so the statement
    explains where the money went.
    """
    from app.modules.investment import market_service
    from app.modules.investment import service as investment_service

    if amount is None or amount <= 0:
        raise TransferError("Transfer tutarı sıfırdan büyük olmalı.")

    owner = market_service.account(db, user_id=user_id, allow_demo_fallback=False)
    if owner is None:
        raise TransferError("Yatırım hesabınız bulunamadı.")
    if bank_account.user_id != user_id:
        raise TransferError("Hesap bulunamadı.")
    if bank_account.status != "active":
        raise TransferError("Gönderen hesap aktif değil.")

    currency = (owner.currency_code or "TRY")
    if bank_account.currency_code != currency:
        # A cross-currency move needs a rate and a disclosed conversion.
        # Refusing is honest; applying 1:1 is the bug this codebase has
        # already paid for once.
        raise TransferError(
            f"Farklı para birimleri arasında transfer desteklenmiyor "
            f"({bank_account.currency_code} → {currency})."
        )

    bank_before = float(bank_account.balance)
    cash_before = float(owner.cash_balance)
    moved = round(float(amount), 2)

    if to_investment and moved > bank_before:
        raise TransferError(
            f"Bakiye yetersiz: {moved:,.2f} {currency} gerekiyor, hesabınızda "
            f"{bank_before:,.2f} {currency} var."
        )
    if not to_investment and moved > cash_before:
        raise TransferError(
            f"Yatırım hesabınızda yetersiz bakiye: {moved:,.2f} {currency} "
            f"gerekiyor, {cash_before:,.2f} {currency} var."
        )

    now = datetime.now(timezone.utc)
    label = description or (
        "Yatırım hesabına transfer" if to_investment else "Yatırım hesabından transfer"
    )
    record = BankTransaction(
        reference_number=_reference_number(),
        transaction_type="virman",
        status="completed",
        amount=moved,
        currency_code=currency,
        description=label,
        completed_at=now,
    )
    db.add(record)
    db.flush()

    bank_after = round(bank_before - moved, 2) if to_investment else round(bank_before + moved, 2)
    bank_account.balance = bank_after
    bank_account.updated_at = now
    cash_after = (
        round(cash_before + moved, 2) if to_investment else round(cash_before - moved, 2)
    )
    owner.cash_balance = cash_after

    # Yatırım tarafı da artık iz bırakıyor. Önceden yalnızca bankacılık bacağı
    # yazılıyordu; para yatırım hesabına varıyor ama o hesabın dökümünde hiçbir
    # şey görünmüyordu.
    investment_service.record_cash_movement(
        db,
        owner,
        amount=moved if to_investment else -moved,
        balance_before=cash_before,
        balance_after=cash_after,
        description=label,
        reference=record.reference_number,
        when=now,
    )

    db.add(
        AccountTransaction(
            transaction_id=record.id,
            account_id=bank_account.id,
            direction="DEBIT" if to_investment else "CREDIT",
            amount=moved,
            balance_before=bank_before,
            balance_after=bank_after,
            counterparty_iban=owner.account_number,
            description=label,
            created_at=now,
        )
    )
    db.commit()
    log.info(
        "investment transfer %s: %s %s %.2f",
        record.reference_number, bank_account.account_number,
        "->" if to_investment else "<-", moved,
    )
    return {
        "reference_number": record.reference_number,
        "status": "completed",
        "amount": moved,
        "fee": 0.0,
        "currency": currency,
        "source_balance_after": bank_after if to_investment else float(owner.cash_balance),
        "destination_account": owner.account_number if to_investment else bank_account.account_number,
    }



#: Faizin gün sayısına bölündüğü taban. 365, ticari 360 değil: müşteri lehine
#: olan ve açıklaması daha kolay olan.
DAYS_IN_YEAR = 365

#: Tek bir işletmede ödenecek azami gün. Uzun süre kapalı kalmış bir kurulum
#: açıldığında aylarca birikmiş faizi tek kalemde ödemesin: vaat edilen günlük
#: bir vadeydi, geriye dönük bir ikramiye değil.
MAX_ACCRUAL_DAYS = 31


def accrue_interest(
    db: Session, user_id: Optional[str] = None, now: Optional[datetime] = None
) -> list[dict]:
    """Vadeli hesaplara hak edilen faizi işler.

    Bakiyeyi doğrudan büyütmüyor: faiz, `post_adjustment` üzerinden
    `transaction_type='faiz'` ile gerçek bir hareket olarak yazılıyor.
    Dökümde açıklaması olmayan bir bakiye artışı, kimsenin hesabını
    veremeyeceği bir para demek -- bu modülün kendi kuralı.

    Aynı gün ikinci kez çalışmaz. `last_accrued_at` gün bazında karşılaştırılır,
    dolayısıyla bir yeniden başlatma faizi ikinci kez ödemez.

    Sıfır ya da eksi bakiyeye faiz işlemez ve oranı olmayan hesabı atlar:
    varsayılan bir oran uydurmak, hesabın vaat etmediği bir getiriyi ödemek
    olurdu.
    """
    moment = now or datetime.now(timezone.utc)
    today = moment.date()

    query = db.query(BankAccount).filter(
        BankAccount.status == "active",
        BankAccount.interest_rate.isnot(None),
    )
    if user_id is not None:
        query = query.filter(BankAccount.user_id == user_id)

    posted: list[dict] = []
    for account in query.all():
        rate = float(account.interest_rate or 0)
        balance = float(account.balance)
        if rate <= 0 or balance <= 0:
            continue

        last = account.last_accrued_at
        if last is not None:
            # Naive bir damga UTC sayılır; karşılaştırmanın kendisi patlamamalı.
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last.date() >= today:
                continue
            days = min((today - last.date()).days, MAX_ACCRUAL_DAYS)
        else:
            # İlk işletme tek gün öder. Hesabın açılışından bugüne kadar
            # geriye dönük ödemek, hiç vaat edilmemiş bir parayı vermek olurdu.
            days = 1

        interest = round(balance * (rate / 100.0) * (days / DAYS_IN_YEAR), 2)
        if interest <= 0:
            # Küçük bakiyede bir günün faizi kuruşun altında kalabilir. Sıfır
            # tutarlı bir hareket yazmak dökümü kirletir; damga yine de
            # ilerletilir ki her gün yeniden denenmesin.
            account.last_accrued_at = moment
            continue

        label = f"Vadeli hesap faizi ({days} gün, yıllık %{rate:.2f})"
        # Damga ÖNCE atılıyor. `post_adjustment` commit ediyor; damgayı ondan
        # sonra yazmak, ödemenin kalıcı olduğu ama "ödendi" kaydının olmadığı
        # bir aralık bırakırdı ve o aralıkta düşen bir servis, açıldığında
        # faizi ikinci kez öderdi. Aynı commit'e girsin diye önce yazılıyor.
        account.last_accrued_at = moment
        result = post_adjustment(
            db, account, interest, label, transaction_type="faiz",
        )
        posted.append({
            "account_number": account.account_number,
            "amount": interest,
            "days": days,
            "reference_number": result["reference_number"],
            "balance_after": result["balance_after"],
        })
        log.info(
            "accrued %.2f %s interest on %s for %d day(s)",
            interest, account.currency_code, account.account_number, days,
        )

    return posted

def post_adjustment(
    db: Session,
    account: BankAccount,
    amount: float,
    description: str,
    actor: Optional[str] = None,
    transaction_type: str = "duzeltme",
) -> dict:
    """Credit or debit one account against the bank itself.

    An admin topping up a demo balance is not a transfer -- there is no second
    account -- so it writes ONE leg. It still goes through the ledger rather
    than `UPDATE accounts SET balance`: an adjustment that moves a balance
    without appearing in the statement is how a demo ends up with a number
    nobody can explain, and this codebase's own comment says it -- the accounts
    are not the source of truth, the transactions are.

    A negative `amount` debits. The balance is not allowed below zero: an admin
    should be told they are over-withdrawing rather than discovering it as a
    negative balance on the customer's screen.
    """
    if amount == 0:
        raise TransferError("Düzeltme tutarı sıfır olamaz.")

    before = float(account.balance)
    after = round(before + float(amount), 2)
    if after < 0:
        raise TransferError(
            f"Bakiye eksiye düşemez: hesapta {before:,.2f} "
            f"{account.currency_code} var, {abs(float(amount)):,.2f} düşülemez."
        )

    now = datetime.now(timezone.utc)
    record = BankTransaction(
        reference_number=_reference_number(),
        transaction_type=transaction_type,
        status="completed",
        amount=round(abs(float(amount)), 2),
        currency_code=account.currency_code,
        description=description,
        completed_at=now,
    )
    db.add(record)
    db.flush()

    account.balance = after
    account.updated_at = now
    db.add(
        AccountTransaction(
            transaction_id=record.id,
            account_id=account.id,
            direction="CREDIT" if amount > 0 else "DEBIT",
            amount=round(abs(float(amount)), 2),
            balance_before=before,
            balance_after=after,
            description=description,
            created_at=now,
        )
    )
    db.commit()
    log.info(
        "adjustment %s on %s: %+.2f by %s",
        record.reference_number, account.account_number, amount, actor or "-",
    )
    return {
        "reference_number": record.reference_number,
        "amount": round(float(amount), 2),
        "currency": account.currency_code,
        "balance_after": after,
    }


# ---------------------------------------------------------------------------
# Reporting — derived from the ledger, never stored as a separate total
# ---------------------------------------------------------------------------

def spending_by_category(
    db: Session, user_id: str, since: datetime
) -> list[dict[str, Any]]:
    """Outgoing money grouped by what it was for.

    DEBIT legs only: a transfer between your own accounts appears as both a
    debit and a credit, and counting the debit as spending would make moving
    your own money look like an expense.
    """
    account_ids = [account.id for account in accounts_for(db, user_id)]
    if not account_ids:
        return []

    rows = db.execute(
        select(
            BankTransaction.category,
            func.sum(AccountTransaction.amount),
        )
        .join(BankTransaction, BankTransaction.id == AccountTransaction.transaction_id)
        .where(
            AccountTransaction.account_id.in_(account_ids),
            AccountTransaction.direction == "DEBIT",
            AccountTransaction.created_at >= since,
            BankTransaction.category.isnot(None),
        )
        .group_by(BankTransaction.category)
        .order_by(func.sum(AccountTransaction.amount).desc())
    ).all()

    return [
        {"category": category, "amount": round(float(total), 2)}
        for category, total in rows
    ]


def income_total(db: Session, user_id: str, since: datetime) -> float:
    """Money that arrived from OUTSIDE the user's own accounts.

    The mirror of `spending_by_category`, and it has the same trap in reverse:
    moving your own money between two of your accounts writes a CREDIT leg,
    and counting that as income would let anyone raise their apparent salary
    by shuffling funds back and forth.

    So a credit only counts when the same transaction has no debit leg on any
    account this user owns. Salary arrives from an employer, which by
    definition has no account here.
    """
    account_ids = [account.id for account in accounts_for(db, user_id)]
    if not account_ids:
        return 0.0

    internal = (
        select(AccountTransaction.transaction_id)
        .where(
            AccountTransaction.account_id.in_(account_ids),
            AccountTransaction.direction == "DEBIT",
        )
        .scalar_subquery()
    )

    total = db.execute(
        select(func.sum(AccountTransaction.amount)).where(
            AccountTransaction.account_id.in_(account_ids),
            AccountTransaction.direction == "CREDIT",
            AccountTransaction.created_at >= since,
            AccountTransaction.transaction_id.notin_(internal),
        )
    ).scalar()

    return round(float(total or 0.0), 2)


def balance_history(
    db: Session, user_id: str, limit: int = 30
) -> list[dict[str, Any]]:
    """The running balance after each movement.

    Read from `balance_after`, which the ledger already records, rather than
    replayed from the movements — the whole reason that column exists.
    """
    account_ids = [account.id for account in accounts_for(db, user_id)]
    if not account_ids:
        return []

    rows = db.execute(
        select(AccountTransaction.created_at, AccountTransaction.balance_after)
        .where(AccountTransaction.account_id.in_(account_ids))
        .order_by(AccountTransaction.created_at.desc())
        .limit(limit)
    ).all()

    return [
        {"at": created_at, "balance": round(float(balance), 2)}
        for created_at, balance in reversed(rows)
    ]


def goals_for(db: Session, user_id: str) -> list[SavingsGoal]:
    return (
        db.query(SavingsGoal)
        .filter(SavingsGoal.user_id == user_id)
        .order_by(SavingsGoal.created_at)
        .all()
    )
