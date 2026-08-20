"""market news items

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

The dashboard's news feed. The same articles also go into `vector-db` as
embedded chunks for retrieval; these rows exist because "latest twenty by
time" should be an indexed scan, not a vector search.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market")
    op.create_table(
        "news_items",
        sa.Column("id", sa.String(), nullable=False),
        # Same hash the rag service dedupes on, so the two sinks agree about
        # what counts as the same article.
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("related_symbols", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash"),
        schema="market",
    )
    op.create_index("idx_news_items_published", "news_items", ["published_at"], schema="market")


def downgrade() -> None:
    op.drop_table("news_items", schema="market")
    op.execute("DROP SCHEMA IF EXISTS market")
