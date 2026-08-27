"""Market news storage.

News lands in two places, on purpose. Rows here serve the dashboard feed —
"latest twenty, newest first" is a cheap indexed query. The same articles are
also chunked and embedded into `vector-db` by the ingestor so the chatbot can
retrieve and cite them; that is a semantic-similarity access pattern and a
completely different query.

Storing it once and serving both from either side would mean the dashboard
paying an embedding search to list headlines, or the retriever having no
corpus. See docs/VECTOR_DB_ARCHITECTURE.md, "Corpus boundary".
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEMA = "market"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        Index("idx_news_items_published", "published_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    #: SHA-256 of the article text. The deduplication key: re-running a feed
    #: must be a no-op, not a second copy of every headline.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="tr")
    #: Tickers the feed itself tagged. Never inferred from the headline text:
    #: a wrong tag would put an unrelated company's news on an instrument page.
    related_symbols: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, default=list
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


SOCIAL_SOURCE_TYPES = (
    "official_company",
    "official_disclosure",
    "disclosure_aggregator",
    "news_agency",
    "financial_media",
    "analyst",
)
SOCIAL_POST_KINDS = ("original", "reply", "repost", "quote")
SOCIAL_VERIFICATION_STATUSES = (
    "unverified",
    "corroborated",
    "officially_verified",
    "contradicted",
)


class SocialAccount(Base):
    """A deliberately monitored public account on a social platform."""

    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_account_id",
            name="uq_social_accounts_platform_external",
        ),
        UniqueConstraint(
            "platform",
            "handle",
            name="uq_social_accounts_platform_handle",
        ),
        CheckConstraint("platform IN ('x')", name="ck_social_accounts_platform"),
        CheckConstraint(
            "source_type IN "
            "('official_company','official_disclosure','disclosure_aggregator',"
            "'news_agency','financial_media','analyst')",
            name="ck_social_accounts_source_type",
        ),
        CheckConstraint(
            "trust_score >= 0 AND trust_score <= 1",
            name="ck_social_accounts_trust_score",
        ),
        Index("idx_social_accounts_active", "platform", "is_active"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="x")
    external_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    handle: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    trust_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class SocialPost(Base):
    """One collected public post, retained as unverified source material."""

    __tablename__ = "social_posts"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_post_id",
            name="uq_social_posts_platform_external",
        ),
        CheckConstraint("platform IN ('x')", name="ck_social_posts_platform"),
        CheckConstraint(
            "post_kind IN ('original','reply','repost','quote')",
            name="ck_social_posts_kind",
        ),
        CheckConstraint(
            "verification_status IN "
            "('unverified','corroborated','officially_verified','contradicted')",
            name="ck_social_posts_verification",
        ),
        CheckConstraint(
            "is_tombstoned OR length(btrim(content_text)) > 0",
            name="ck_social_posts_active_content",
        ),
        Index("idx_social_posts_published", "published_at"),
        Index("idx_social_posts_account_published", "account_id", "published_at"),
        Index("idx_social_posts_verification", "verification_status"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.social_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="x")
    external_post_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    post_url: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    post_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    referenced_external_post_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_tombstoned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified"
    )
    underlying_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    underlying_source_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    underlying_source_domain: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class SocialPostInstrument(Base):
    """Latest accepted canonical instrument references for a social post."""

    __tablename__ = "social_post_instruments"
    __table_args__ = (
        UniqueConstraint(
            "post_id",
            "product_id",
            name="uq_social_post_instruments_post_product",
        ),
        CheckConstraint(
            "match_confidence IS NULL OR "
            "(match_confidence >= 0 AND match_confidence <= 1)",
            name="ck_social_post_instruments_confidence",
        ),
        Index("idx_social_post_instruments_product", "product_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.social_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("investment.investment_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    canonical_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    match_method: Mapped[str] = mapped_column(String(32), nullable=False)
    match_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
