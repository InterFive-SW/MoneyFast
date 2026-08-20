"""investment market data, transaction proposals, and ai conversations

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

Implements the parts of `infra/intertech.sql` this phase actually needs, in
one migration rather than three. CLAUDE.md calls migrations the single real
conflict point between team members, so fewer of them is better even when the
tables are unrelated.

Two schemas are created here — `investment` and `ai` — matching the reference
design. `users` stays in `public`, where migration 0001 put it; moving it is
the auth owner's call, and a foreign key across schemas works either way.

What is deliberately NOT created: `investment_accounts`, `investment_orders`,
`investment_trades`, `portfolio_positions`. Nothing in this phase reads them,
and creating tables no code touches makes the schema look more implemented
than it is.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS investment")
    op.execute("CREATE SCHEMA IF NOT EXISTS ai")

    # ---------------------------------------------------------------- products
    op.create_table(
        "investment_products",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        # The bridge between dummy holdings and live market data. Nullable:
        # an instrument with no upstream feed is legitimate, and NULL means
        # "do not price this" rather than "price it as zero".
        sa.Column("data_symbol", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("product_type", sa.String(length=50), nullable=False),
        sa.Column("market", sa.String(length=50), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
        schema="investment",
    )
    op.create_index(
        "ix_investment_products_symbol", "investment_products", ["symbol"], schema="investment"
    )
    op.create_index(
        "ix_investment_products_data_symbol",
        "investment_products",
        ["data_symbol"],
        schema="investment",
    )

    # ------------------------------------------------------------------ quotes
    op.create_table(
        "market_quotes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("price", sa.Numeric(19, 4), nullable=False),
        sa.Column("change_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("change_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("previous_close", sa.Numeric(19, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        # market_timestamp and received_at are separate on purpose: the gap
        # between them is the delay the AI contract obliges the assistant to
        # disclose. Collapsing them would let stale data read as live.
        sa.Column("market_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["investment.investment_products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="investment",
    )
    op.create_index(
        "idx_market_quotes_product_time",
        "market_quotes",
        ["product_id", "market_timestamp"],
        schema="investment",
    )

    # ----------------------------------------------------------------- candles
    op.create_table(
        "market_candles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("high_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("low_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("close_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"], ["investment.investment_products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # What makes re-running an ingest a no-op instead of a duplicate bar.
        sa.UniqueConstraint("product_id", "interval", "timestamp", name="uq_market_candles_bar"),
        schema="investment",
    )
    op.create_index(
        "idx_market_candles_product_interval_time",
        "market_candles",
        ["product_id", "interval", "timestamp"],
        schema="investment",
    )

    # --------------------------------------------------------------- proposals
    op.create_table(
        "transaction_proposals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("quantity", sa.Numeric(19, 6), nullable=True),
        sa.Column("source_account_id", sa.String(length=64), nullable=True),
        sa.Column("destination_account_id", sa.String(length=64), nullable=True),
        sa.Column("order_type", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="investment",
    )
    op.create_index(
        "idx_transaction_proposals_user",
        "transaction_proposals",
        ["user_id", "created_at"],
        schema="investment",
    )

    # ----------------------------------------------------------- conversations
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), nullable=False),
        # No FK to public.users: the chat serves anonymous visitors too, and a
        # NOT NULL FK would make an anonymous turn unstorable. Ownership is
        # enforced in the service layer instead.
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "thread_id", name="uq_conversations_user_thread"),
        schema="ai",
    )
    op.create_index(
        "idx_conversations_user_updated",
        "conversations",
        ["user_id", "updated_at"],
        schema="ai",
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Operational metadata for the turn record: routed agent, compliance
        # verdict, audit ids. Never shown to the user.
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["ai.conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="ai",
    )
    op.create_index(
        "idx_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        schema="ai",
    )


def downgrade() -> None:
    op.drop_table("messages", schema="ai")
    op.drop_table("conversations", schema="ai")
    op.drop_table("transaction_proposals", schema="investment")
    op.drop_table("market_candles", schema="investment")
    op.drop_table("market_quotes", schema="investment")
    op.drop_table("investment_products", schema="investment")
    op.execute("DROP SCHEMA IF EXISTS ai")
    op.execute("DROP SCHEMA IF EXISTS investment")
