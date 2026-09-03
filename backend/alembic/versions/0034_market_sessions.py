"""market sessions — hangi piyasa şu an açık

Revision ID: 0034
Revises: 0033
"""

from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_sessions",
        # Piyasa kodu birincil anahtar: piyasa başına TEK satır ve "şu an"ın
        # iki farklı cevabı olamaz.
        sa.Column("market", sa.String(32), primary_key=True),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="investment",
    )


def downgrade() -> None:
    op.drop_table("market_sessions", schema="investment")
