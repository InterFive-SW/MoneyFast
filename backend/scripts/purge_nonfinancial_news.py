"""Delete off-topic news already stored in the backend copy.

Why this exists: the ingestor used to read `dunya.com/rss?dunya` and
`ekonomim.com/rss`, which are the sites' SITE-WIDE feeds. A finance app
therefore accumulated football transfers, exam results and earthquake
bulletins. `rss_source.is_financial` now filters new items at ingest; this
removes the ones that got in before it existed.

DESTRUCTIVE and one-off. Run it deliberately:

    docker compose exec backend python -m scripts.purge_nonfinancial_news --dry-run
    docker compose exec backend python -m scripts.purge_nonfinancial_news --apply

The vector-store copy is separate and lives behind the rag service, which holds
the only vector-db credential — see
AI-Services/moneyfast-rag/scripts/purge_nonfinancial.py.
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

from sqlalchemy import text

from app.core.database import SessionLocal

#: A copy of ingestor `rss_source.NON_FINANCIAL_SECTIONS`. Duplicated rather
#: than imported because the services share no library by design — the ingestor
#: cannot reach this database and this process cannot import from it. Kept in
#: sync by hand; this is a one-off cleanup, not a running component.
NON_FINANCIAL_SECTIONS = {
    "spor", "gundem", "magazin", "saglik", "egitim", "yasam",
    "kultur-sanat", "kultur", "sanat", "otomobil", "seyahat", "astroloji",
    "foto-galeri", "video-galeri", "galeri", "video",
}


def section(url: str | None) -> str | None:
    if not url:
        return None
    parts = [segment for segment in urlparse(url).path.split("/") if segment]
    if not parts:
        return None
    if len(parts[0]) == 2 and parts[0].isalpha():
        parts = parts[1:]
    return parts[0].lower() if parts else None


def is_financial(url: str | None) -> bool:
    """Unknown section => keep. See the ingestor for the reasoning."""
    found = section(url)
    return found is None or found not in NON_FINANCIAL_SECTIONS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="list what would go")
    group.add_argument("--apply", action="store_true", help="actually delete")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT id, url, title FROM market.news_items")).all()
        doomed = [row for row in rows if not is_financial(row.url)]

        print(f"{len(rows)} haber var, {len(doomed)} tanesi finans dışı.")
        for row in doomed[:20]:
            print(f"  [{section(row.url)}] {row.title[:70]}")
        if len(doomed) > 20:
            print(f"  ... ve {len(doomed) - 20} tane daha")

        if args.dry_run or not doomed:
            return 0

        db.execute(
            text("DELETE FROM market.news_items WHERE id = ANY(:ids)"),
            {"ids": [row.id for row in doomed]},
        )
        db.commit()
        print(f"{len(doomed)} haber silindi.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
