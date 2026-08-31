# filename: store.py
"""vector-db access for the rag service.

This module holds the only vector-db credential in the system. The backend
never receives it and neither does the MCP tool server; see
docs/VECTOR_DB_ARCHITECTURE.md. The connection is built from RAG_DB_USER,
which is NOSUPERUSER and limited to DML in the `rag` schema plus EXECUTE on
`rag.match_chunks`.

Retrieval goes through `rag.match_chunks` rather than an inline SELECT. The
function pins its own search_path, is STABLE, and validates top_k and the
threshold server-side, so those guarantees survive regardless of what this
client sends.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Sequence

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

log = logging.getLogger("moneyfast.rag.store")

#: The SQL function refuses anything above 20. The MCP contract allows a
#: top_k of 25, so the clamp happens here and is documented in the README
#: rather than surfacing as a Postgres exception the orchestrator would
#: report to the user as "sources could not be consulted".
MAX_TOP_K = 20

_pool: Optional[AsyncConnectionPool] = None


def database_url() -> str:
    url = os.getenv("RAG_DATABASE_URL")
    if not url:
        raise RuntimeError("RAG_DATABASE_URL is not set")
    return url


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            database_url(),
            min_size=1,
            max_size=int(os.getenv("RAG_DB_POOL_MAX", "5")),
            open=False,
            kwargs={"row_factory": dict_row},
        )
        await _pool.open(wait=True, timeout=30)
        log.info("vector-db pool opened")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def ping() -> bool:
    """Readiness probe. Proves the role can actually reach the database."""
    pool = await open_pool()
    async with pool.connection() as conn:
        await conn.execute("SELECT 1")
    return True


def _array(values: Optional[Sequence[str]]) -> Optional[list[str]]:
    """Normalise a filter list. Empty and absent both mean "no filter"."""
    if not values:
        return None
    return [str(value) for value in values]


async def match_chunks(
    query_vector: str,
    owner_user_id: Optional[str],
    top_k: int,
    min_similarity: Optional[float],
    tickers: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
    languages: Optional[Sequence[str]] = None,
    document_types: Optional[Sequence[str]] = None,
    published_after: Optional[str] = None,
    published_before: Optional[str] = None,
    publishers: Optional[Sequence[str]] = None,
) -> list[dict[str, Any]]:
    """Run exact (or HNSW, if the optional migration is applied) retrieval.

    `owner_user_id` is positional and has no default, here and in the SQL
    function, so a caller cannot omit it. NULL means anonymous: the public
    corpus only, because `owner_user_id = NULL` is never true for any row.
    """
    pool = await open_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT *
            FROM rag.match_chunks(
                %(embedding)s::vector,
                %(owner)s::uuid,
                %(top_k)s,
                %(threshold)s,
                %(tickers)s,
                %(categories)s,
                %(languages)s,
                %(document_types)s,
                %(published_after)s,
                %(published_before)s,
                %(publishers)s
            )
            """,
            {
                "embedding": query_vector,
                "owner": owner_user_id,
                "top_k": max(1, min(MAX_TOP_K, top_k)),
                "threshold": min_similarity,
                "tickers": _array(tickers),
                "categories": _array(categories),
                "languages": _array(languages),
                "document_types": _array(document_types),
                "published_after": published_after,
                "published_before": published_before,
                "publishers": _array(publishers),
            },
        )
        return await cursor.fetchall()


async def index_snapshot() -> dict[str, Any]:
    """Freshness of the corpus.

    `as_of` is the newest ingestion timestamp, which is the real ceiling of
    what retrieval can return. `newest_published_at` drives the lag figure:
    the contract's `is_delayed` means "the index has not caught up with the
    publication window", not "the database is slow".
    """
    pool = await open_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT
                max(updated_at)    AS as_of,
                max(published_at)  AS newest_published_at,
                count(*)           AS document_count
            FROM rag.documents
            WHERE status = 'active'
            """
        )
        row = await cursor.fetchone()
    return row or {"as_of": None, "newest_published_at": None, "document_count": 0}


async def upsert_document(
    conn: AsyncConnection,
    *,
    title: str,
    source: str,
    category: str,
    document_type: str,
    content_hash: str,
    source_url: Optional[str],
    language: str,
    ticker: Optional[str],
    period: Optional[str],
    published_at: Optional[str],
    owner_user_id: Optional[str] = None,
) -> Optional[str]:
    """Insert a document, or return None when this OWNER already has it.

    Deduplication keeps a re-ingested corpus from writing duplicate chunks
    that compete for the same retrieval slots. It is scoped per owner (0004):
    globally unique content hashes meant the second person to upload a given
    file got "duplicate" and no document of their own.

    Two partial indexes back this, so the conflict target differs by branch --
    `(content_hash) WHERE owner IS NULL` for the public corpus and
    `(owner_user_id, content_hash)` for private ones. A single statement
    cannot name both.
    """
    cursor = await conn.execute(
        """
        INSERT INTO rag.documents (
            title, source, source_url, category, language,
            ticker, document_type, period, published_at, content_hash,
            owner_user_id
        )
        VALUES (
            %(title)s, %(source)s, %(source_url)s, %(category)s, %(language)s,
            %(ticker)s, %(document_type)s, %(period)s, %(published_at)s,
            %(content_hash)s, %(owner_user_id)s::uuid
        )
        """
        + (
            "ON CONFLICT (content_hash) WHERE owner_user_id IS NULL DO NOTHING"
            if owner_user_id is None
            else "ON CONFLICT (owner_user_id, content_hash) "
                 "WHERE owner_user_id IS NOT NULL DO NOTHING"
        )
        + """
        RETURNING id
        """,
        {
            "owner_user_id": owner_user_id,
            "title": title,
            "source": source,
            "source_url": source_url,
            "category": category,
            "language": language,
            "ticker": ticker,
            "document_type": document_type,
            "period": period,
            "published_at": published_at,
            "content_hash": content_hash,
        },
    )
    row = await cursor.fetchone()
    return str(row["id"]) if row else None


async def insert_chunks(
    conn: AsyncConnection,
    document_id: str,
    chunks: Sequence[tuple[int, str, str]],
) -> int:
    """Store (chunk_index, content, pgvector literal) triples."""
    model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    count = 0
    for chunk_index, content, vector in chunks:
        await conn.execute(
            """
            INSERT INTO rag.chunks (
                document_id, chunk_index, content, embedding, embedding_model, token_count
            )
            VALUES (
                %(document_id)s, %(chunk_index)s, %(content)s,
                %(embedding)s::vector, %(model)s, %(token_count)s
            )
            """,
            {
                "document_id": document_id,
                "chunk_index": chunk_index,
                "content": content,
                "embedding": vector,
                "model": model,
                # Whitespace tokens are a coarse proxy; the column only exists
                # for budget accounting, never for billing.
                "token_count": max(1, len(content.split())),
            },
        )
        count += 1
    return count


async def ingest(conn_factory, document: dict[str, Any], chunks: Sequence[tuple[int, str, str]]):
    pool = await conn_factory()
    async with pool.connection() as conn:
        async with conn.transaction():
            document_id = await upsert_document(conn, **document)
            if document_id is None:
                return None, 0
            written = await insert_chunks(conn, document_id, chunks)
    return document_id, written
