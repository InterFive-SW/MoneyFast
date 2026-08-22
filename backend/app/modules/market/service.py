"""News storage and retrieval for the dashboard feed."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import NewsItem

log = logging.getLogger("moneyfast.market")


def upsert_news(db: Session, items: list[dict[str, Any]]) -> int:
    """Store articles, ignoring ones already held.

    Deduplicated on content_hash rather than URL: the same wire story is
    republished under different URLs, and a feed that renumbers its links
    would otherwise re-import its whole history every poll.
    """
    if not items:
        return 0

    payload = [
        {
            "id": item.get("id") or _new_id(),
            "content_hash": item["content_hash"],
            "title": item["title"],
            "summary": item.get("summary"),
            "source": item["source"],
            "url": item.get("url"),
            "language": item.get("language", "tr"),
            "related_symbols": item.get("related_symbols") or [],
            "published_at": item["published_at"],
            "ingested_at": datetime.now(timezone.utc),
        }
        for item in items
    ]
    statement = insert(NewsItem).values(payload).on_conflict_do_nothing(
        index_elements=["content_hash"]
    )
    result = db.execute(statement)
    db.commit()
    return result.rowcount or 0


def latest_news(db: Session, limit: int = 20) -> list[NewsItem]:
    return (
        db.query(NewsItem)
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit)
        .all()
    )


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())
