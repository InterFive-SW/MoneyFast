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

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
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
    related_symbols: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
