"""transaction categories and savings goals

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-21

The dashboard's personal-finance widgets were fed inline literals from
`Dashboard.tsx`: a ₺12.500 monthly spend with one invented category, a
₺500.000 car goal, a ₺145.000 balance with a fabricated sparkline, and a
permanently empty transaction list.

Banking now exists (0008), so three of the four can be real. What was missing
is a way to say what a movement was FOR — a ledger records that money moved,
not why — and somewhere to keep a savings target, which is user intent rather
than an observation. This adds both.

`category` is nullable on purpose: a transfer between your own accounts has no
spending category, and forcing one would invent a fact about every existing row.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("category", sa.String(40), nullable=True),
        schema="banking",
    )
    op.add_column(
        "transactions",
        sa.Column("counterparty", sa.String(120), nullable=True),
        schema="banking",
    )

    op.create_table(
        "savings_goals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("target_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("current_amount", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="TRY"),
        sa.Column("icon", sa.String(8), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("deadline", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="banking",
    )


def downgrade() -> None:
    op.drop_table("savings_goals", schema="banking")
    op.drop_column("transactions", "counterparty", schema="banking")
    op.drop_column("transactions", "category", schema="banking")
