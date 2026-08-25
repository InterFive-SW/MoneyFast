"""a watchlist the user actually chooses

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-22

`GET /api/investment/watchlist` returned the first eight priced stocks per
market in alphabetical order. It was not a watchlist: it showed the same rows
to everyone, ignored what anyone was interested in, and could not be changed
from the interface at all.

This adds the missing thing — a per-user set of followed instruments — so the
endpoint can return the user's own picks and the Piyasalar screen can add to
and remove from them.

`user_id` is a plain column, not a foreign key into `auth.users`: modules do
not reference each other's tables through the ORM (CLAUDE.md, "shared/
kuralı"). The unique constraint on (user_id, product_id) is what makes
starring an instrument twice a no-op instead of an error.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["investment.investment_products.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "product_id", name="uq_watchlist_user_product"),
        schema="investment",
    )
    op.create_index(
        "ix_watchlist_items_user_id",
        "watchlist_items",
        ["user_id"],
        schema="investment",
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_items_user_id", table_name="watchlist_items", schema="investment")
    op.drop_table("watchlist_items", schema="investment")
