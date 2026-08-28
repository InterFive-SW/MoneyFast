"""bills issued by an admin, and the payees a user chooses to keep

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-26

Bills were `MOCK_BANKING_DATA`: the screen listed four of them and "paying"
one edited React state. Nothing left an account, and the invented movement sat
in the same list as real ledger rows until the next refresh removed it.

A bill is found by SUBSCRIBER NUMBER, not assigned to a user. That is how a
Turkish banking app works -- you pick the institution, type the number on the
paper, and the bank tells you what is owed -- and it is what makes a saved
payee worth having: the number is the tedious part, so keeping it is the whole
value of "Kayıtlı İşlemler".

`uq_bills_open_subscriber` is a PARTIAL unique index, over unpaid rows only.
The same subscriber number legitimately recurs every month, so uniqueness can
only mean "one OPEN bill at a time"; a plain constraint would make the second
month's electricity bill un-issuable.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bills",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("institution", sa.String(length=80), nullable=False),
        #: water | electricity | internet | phone -- the four the UI renders.
        sa.Column("bill_type", sa.String(length=20), nullable=False),
        sa.Column("subscriber_no", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        #: Day of month it falls due. A day rather than a date because these
        #: recur monthly and the admin is issuing "the March bill", not a
        #: one-off dated document.
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        #: Who issued it, so an admin action is attributable after the fact.
        sa.Column("issued_by", sa.String(), nullable=True),
        #: Who paid it. Null while open -- a bill belongs to whoever settles it,
        #: which is not known when it is issued.
        sa.Column("paid_by", sa.String(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="banking",
    )
    op.create_index(
        "ix_bills_lookup", "bills", ["institution", "subscriber_no"], schema="banking",
    )
    # One OPEN bill per (institution, subscriber). Paid rows fall out of the
    # index, so next month's bill for the same number is issuable.
    op.execute(
        "CREATE UNIQUE INDEX uq_bills_open_subscriber"
        " ON banking.bills (institution, subscriber_no)"
        " WHERE status = 'pending'"
    )

    op.create_table(
        "saved_payees",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("institution", sa.String(length=80), nullable=False),
        sa.Column("subscriber_no", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        # Saving the same payee twice is the same intent expressed twice, so it
        # is a no-op rather than an error the user has to read.
        sa.UniqueConstraint(
            "user_id", "institution", "subscriber_no", name="uq_saved_payee_per_user",
        ),
        schema="banking",
    )
    op.create_index(
        "ix_saved_payees_user", "saved_payees", ["user_id"], schema="banking",
    )


def downgrade() -> None:
    op.drop_table("saved_payees", schema="banking")
    op.execute("DROP INDEX IF EXISTS banking.uq_bills_open_subscriber")
    op.drop_table("bills", schema="banking")
