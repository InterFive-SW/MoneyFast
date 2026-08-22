"""Delete off-topic documents from the vector store.

The companion to backend/scripts/purge_nonfinancial_news.py. It lives here
because the rag service holds the only vector-db credential in the system, so
this is the only place a purge can run without breaking that boundary.

DESTRUCTIVE and one-off:

    docker compose exec rag python -m scripts.purge_nonfinancial --dry-run
    docker compose exec rag python -m scripts.purge_nonfinancial --apply

Chunks are removed with their document, so the embeddings go too. There is no
soft delete: a document nobody should retrieve should not be retrievable.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import urlparse

import store

#: A copy of ingestor `rss_source.NON_FINANCIAL_SECTIONS`; see the backend
#: purge script for why it is duplicated rather than imported.
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
    found = section(url)
    return found is None or found not in NON_FINANCIAL_SECTIONS


async def run(apply: bool) -> int:
    pool = await store.open_pool()
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                "SELECT id, source_url, title FROM rag.documents"
            )
            rows = await result.fetchall()
            # The pool is configured with a dict row factory, so columns are
            # addressed by name rather than position.
            doomed = [row for row in rows if not is_financial(row["source_url"])]

            print(f"{len(rows)} doküman var, {len(doomed)} tanesi finans dışı.")
            for row in doomed[:20]:
                print(f"  [{section(row['source_url'])}] {(row['title'] or '')[:70]}")
            if len(doomed) > 20:
                print(f"  ... ve {len(doomed) - 20} tane daha")

            if not apply or not doomed:
                return 0

            ids = [row["id"] for row in doomed]
            # Chunks first: the FK points this way, and leaving orphaned
            # embeddings behind would keep the text retrievable.
            await conn.execute("DELETE FROM rag.chunks WHERE document_id = ANY(%s)", (ids,))
            await conn.execute("DELETE FROM rag.documents WHERE id = ANY(%s)", (ids,))
            print(f"{len(doomed)} doküman ve chunk'ları silindi.")
        return 0
    finally:
        await store.close_pool()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    sys.exit(main())
