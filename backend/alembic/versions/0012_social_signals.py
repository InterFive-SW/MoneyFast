"""dedicated storage for collected social signals

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-27

Social posts are not news and are never written to ``market.news_items``.
Accounts are deactivated and posts are tombstoned rather than hard-deleted.
The account and product foreign keys therefore restrict deletion; only the
pure relation rows cascade when a post is explicitly removed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("external_account_id", sa.String(length=64), nullable=False),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("trust_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("platform IN ('x')", name="ck_social_accounts_platform"),
        sa.CheckConstraint(
            "source_type IN "
            "('official_company','official_disclosure','disclosure_aggregator',"
            "'news_agency','financial_media','analyst')",
            name="ck_social_accounts_source_type",
        ),
        sa.CheckConstraint(
            "trust_score >= 0 AND trust_score <= 1",
            name="ck_social_accounts_trust_score",
        ),
        sa.UniqueConstraint(
            "platform",
            "external_account_id",
            name="uq_social_accounts_platform_external",
        ),
        sa.UniqueConstraint(
            "platform", "handle", name="uq_social_accounts_platform_handle"
        ),
        schema="market",
    )
    op.create_index(
        "idx_social_accounts_active",
        "social_accounts",
        ["platform", "is_active"],
        schema="market",
    )

    op.create_table(
        "social_posts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("external_post_id", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("post_url", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("post_kind", sa.String(length=16), nullable=False),
        sa.Column("referenced_external_post_id", sa.String(length=64), nullable=True),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column(
            "is_tombstoned", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "raw_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("underlying_source_url", sa.Text(), nullable=True),
        sa.Column("underlying_source_type", sa.String(length=32), nullable=True),
        sa.Column("underlying_source_domain", sa.String(length=128), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["market.social_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("platform IN ('x')", name="ck_social_posts_platform"),
        sa.CheckConstraint(
            "post_kind IN ('original','reply','repost','quote')",
            name="ck_social_posts_kind",
        ),
        sa.CheckConstraint(
            "verification_status IN "
            "('unverified','corroborated','officially_verified','contradicted')",
            name="ck_social_posts_verification",
        ),
        sa.CheckConstraint(
            "is_tombstoned OR length(btrim(content_text)) > 0",
            name="ck_social_posts_active_content",
        ),
        sa.UniqueConstraint(
            "platform",
            "external_post_id",
            name="uq_social_posts_platform_external",
        ),
        schema="market",
    )
    op.create_index(
        "idx_social_posts_published",
        "social_posts",
        ["published_at"],
        schema="market",
    )
    op.create_index(
        "idx_social_posts_account_published",
        "social_posts",
        ["account_id", "published_at"],
        schema="market",
    )
    op.create_index(
        "idx_social_posts_verification",
        "social_posts",
        ["verification_status"],
        schema="market",
    )

    op.create_table(
        "social_post_instruments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("post_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("canonical_symbol", sa.String(length=32), nullable=False),
        sa.Column("match_method", sa.String(length=32), nullable=False),
        sa.Column("match_confidence", sa.Numeric(4, 3), nullable=True),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["market.social_posts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["investment.investment_products.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "match_confidence IS NULL OR "
            "(match_confidence >= 0 AND match_confidence <= 1)",
            name="ck_social_post_instruments_confidence",
        ),
        sa.UniqueConstraint(
            "post_id",
            "product_id",
            name="uq_social_post_instruments_post_product",
        ),
        schema="market",
    )
    op.create_index(
        "idx_social_post_instruments_product",
        "social_post_instruments",
        ["product_id"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_social_post_instruments_product",
        table_name="social_post_instruments",
        schema="market",
    )
    op.drop_table("social_post_instruments", schema="market")
    op.drop_index(
        "idx_social_posts_verification",
        table_name="social_posts",
        schema="market",
    )
    op.drop_index(
        "idx_social_posts_account_published",
        table_name="social_posts",
        schema="market",
    )
    op.drop_index(
        "idx_social_posts_published",
        table_name="social_posts",
        schema="market",
    )
    op.drop_table("social_posts", schema="market")
    op.drop_index(
        "idx_social_accounts_active",
        table_name="social_accounts",
        schema="market",
    )
    op.drop_table("social_accounts", schema="market")
