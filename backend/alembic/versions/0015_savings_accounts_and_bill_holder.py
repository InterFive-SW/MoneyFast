"""a second account per customer, and a name on every bill

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-27

Two small things that together make the app look like a bank rather than a
demo.

**A `vadeli` account.** Everyone had exactly one account, so "para gönder"
could only ever send money away, and the transfer screen had nothing to
transfer between. The savings account opens EMPTY on purpose: an account that
arrives with money in it is a gift, not savings.

**`holder_name` on a bill.** A real bill has a name printed on it. Without one
the admin panel could only show a subscriber number, which says nothing about
who the bill is for -- and since a bill deliberately belongs to nobody until
it is paid, the number was the only handle anyone had.

Existing customers are backfilled here rather than left to open an account on
their next login, which would mean the seeded demo users never get one.
"""

from typing import Sequence, Union

import hashlib

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _digits_for(user_id: str, length: int) -> str:
    """Same derivation `banking/service.py` uses, so a backfilled account
    number is indistinguishable from one opened by the application."""
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return str(int(digest[:16], 16))[:length].ljust(length, "0")


def _iban_for(account_number: str) -> str:
    return f"TR{account_number.zfill(24)}"


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column("holder_name", sa.String(length=120), nullable=True),
        schema="banking",
    )

    # Backfill a vadeli account for every customer who lacks one.
    connection = op.get_bind()
    users = connection.execute(sa.text("SELECT id FROM public.users")).fetchall()
    for (user_id,) in users:
        exists = connection.execute(
            sa.text(
                "SELECT 1 FROM banking.accounts"
                " WHERE user_id = :uid AND account_type = 'vadeli'"
            ),
            {"uid": str(user_id)},
        ).first()
        if exists:
            continue
        number = f"2{_digits_for(str(user_id), 12)}"
        connection.execute(
            sa.text(
                "INSERT INTO banking.accounts"
                " (id, user_id, account_number, iban, account_type, currency_code,"
                "  balance, status, created_at, updated_at)"
                " VALUES (gen_random_uuid()::text, :uid, :num, :iban, 'vadeli', 'TRY',"
                "         0, 'active', now(), now())"
                " ON CONFLICT DO NOTHING"
            ),
            {"uid": str(user_id), "num": number, "iban": _iban_for(number)},
        )


def downgrade() -> None:
    op.execute("DELETE FROM banking.accounts WHERE account_type = 'vadeli'")
    op.drop_column("bills", "holder_name", schema="banking")
