"""Generate a few months of categorised account activity.

The dashboard's spending widget needs movements that say what they were FOR,
and a fresh install has none — the ledger only contains whatever transfers
someone happened to make while testing.

This writes real rows through the real tables: a `transactions` record and its
two `account_transactions` legs, each carrying `balance_before`/`balance_after`,
exactly as `service.transfer` would. Nothing here is a fixture the API special-
cases; the endpoints read it back like any other data.

Synthetic but not arbitrary: amounts and frequencies are drawn per category so
groceries are frequent and small while rent is monthly and large, which is what
makes the resulting breakdown look like a real month rather than noise.

    docker compose exec backend python -m scripts.seed_banking_activity --apply
"""

from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.banking.models import AccountTransaction, BankAccount, BankTransaction, SavingsGoal

#: (category, counterparty, per-occurrence range, occurrences per month)
CATEGORIES = [
    ("Market", "Migros", (180, 900), 9),
    ("Kira", "Ev sahibi", (14000, 14000), 1),
    ("Faturalar", "Elektrik/Doğalgaz", (450, 1800), 3),
    ("Ulaşım", "İETT / Benzin", (60, 700), 7),
    ("Yeme İçme", "Restoran", (120, 850), 6),
    ("Sağlık", "Eczane", (150, 1200), 1),
    ("Eğlence", "Sinema / Dijital", (60, 400), 3),
]

#: Monthly salary, credited at the start of each month. Without it three
#: months of expenses drove the balance negative — an account that only ever
#: pays out is not a plausible history, and it made the balance sparkline a
#: straight line into the red.
SALARY = (52_000, 58_000)

GOALS = [
    ("Acil Durum Fonu", 120_000, 42_500, "🛟", "#0ea5e9", "2027-06"),
    ("Araba", 500_000, 150_000, "🚗", "#10b981", "2028-01"),
    ("Tatil", 80_000, 31_000, "✈️", "#f59e0b", "2027-07"),
]


def seed_for(db, account: BankAccount, months: int, rng: random.Random) -> int:
    """Write `months` of activity ending today. Returns the row count."""
    now = datetime.now(timezone.utc)
    written = 0
    # Walk forward so each leg's balance_before is the previous balance_after,
    # which is what makes the history reconcile.
    balance = float(account.balance)
    movements = []

    for month in range(months, 0, -1):
        # Salary first, on the 1st, so the month opens funded.
        movements.append((
            now - timedelta(days=month * 30 - 1), "Maaş", "İşveren",
            round(rng.uniform(*SALARY), 2), "CREDIT",
        ))
        for category, counterparty, (low, high), per_month in CATEGORIES:
            for _ in range(per_month):
                day = rng.randint(1, 28)
                when = now - timedelta(days=month * 30 - day)
                if when > now:
                    continue
                movements.append((
                    when, category, counterparty, round(rng.uniform(low, high), 2), "DEBIT",
                ))

    for when, category, counterparty, amount, direction in sorted(movements, key=lambda m: m[0]):
        record = BankTransaction(
            id=str(uuid.uuid4()),
            reference_number=f"SEED-{uuid.uuid4().hex[:10].upper()}",
            transaction_type="maas" if direction == "CREDIT" else "harcama",
            status="completed",
            amount=amount,
            currency_code=account.currency_code,
            description=counterparty,
            # Income is not a spending category: leaving it null keeps salary
            # out of the expense breakdown, which only reads categorised debits.
            category=None if direction == "CREDIT" else category,
            counterparty=counterparty,
            created_at=when,
            completed_at=when,
        )
        db.add(record)
        db.flush()

        delta = amount if direction == "CREDIT" else -amount
        before, balance = balance, round(balance + delta, 2)
        db.add(
            AccountTransaction(
                id=str(uuid.uuid4()),
                transaction_id=record.id,
                account_id=account.id,
                direction=direction,
                amount=amount,
                balance_before=before,
                balance_after=balance,
                counterparty_name=counterparty,
                description=category,
                created_at=when,
            )
        )
        written += 1

    account.balance = balance
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument("--months", type=int, default=3)
    args = parser.parse_args()

    # Seeded so a re-run against a fresh database produces the same history —
    # a demo whose numbers change every reset is hard to talk about.
    rng = random.Random(20260821)

    db = SessionLocal()
    try:
        accounts = db.query(BankAccount).all()
        if not accounts:
            print("Mevduat hesabı yok; önce migration 0008 çalıştırılmalı.")
            return 1

        existing = db.execute(
            text("SELECT count(*) FROM banking.transactions WHERE category IS NOT NULL")
        ).scalar_one()
        if existing:
            print(f"{existing} kategorili hareket zaten var, tekrar yazılmadı.")
            return 0

        total = 0
        for account in accounts:
            total += seed_for(db, account, args.months, rng)
            for name, target, current, icon, color, deadline in GOALS:
                db.add(
                    SavingsGoal(
                        id=str(uuid.uuid4()), user_id=account.user_id, name=name,
                        target_amount=target, current_amount=current,
                        currency_code=account.currency_code, icon=icon,
                        color=color, deadline=deadline,
                    )
                )

        print(f"{total} hareket ve {len(GOALS) * len(accounts)} hedef hazırlandı.")
        if args.dry_run:
            db.rollback()
            return 0

        db.commit()
        print("Yazıldı.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
