# filename: app.py
"""MoneyFast RAG service.

Owns the vector database and the embedding model. Two consumers:

* `mcp` calls POST /search on behalf of the `rag_semantic_market_search`
  tool. The response body is shaped to the MCP v2.1 retrieval contract
  exactly, so `market_research_tools._normalize` passes it through without a
  single defaulted field.
* An operator calls POST /ingest to load the corpus.

What this service deliberately does NOT do: summarise, rank by investment
merit, or assert anything. It returns passages and provenance. Every
interpretation happens upstream, behind the compliance gate.
"""

from __future__ import annotations

import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import chunking
import embeddings
import corpus_seed
import store

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("moneyfast.rag")

#: Recognised metadata pre-filter keys. An unknown key is rejected rather than
#: ignored: the contract tells the model a filter was applied, and silently
#: dropping one turns "no results for this ticker" into a false negative the
#: orchestrator would report as fact.
ALLOWED_FILTERS = frozenset(
    {"tickers", "doc_types", "published_after", "published_before", "languages", "publishers", "categories"}
)

#: Ingestion lag beyond which the corpus is reported as not current.
DEFAULT_LAG_THRESHOLD_MINUTES = 24 * 60

#: Documents whose type is inherently editorial. The contract requires such
#: content to be attributed to its author and never restated as the
#: assistant's own view, so mislabelling here has downstream consequences.
OPINION_DOC_TYPES = frozenset({"ANALYST_REPORT", "OPINION", "EDITORIAL", "COMMENTARY"})

#: Turkish characters folded to ASCII before matching, so one entry covers
#: "şu", "ŞU" and "su". The sets below are therefore written PRE-FOLDED —
#: writing "şu" in them would never match, because the input is folded first.
_FOLD = str.maketrans("ıİşŞğĞüÜöÖçÇâÂîÎûÛ", "iisSgGuUoOcCaAiIuU")

#: Anaphora: words that point at something said earlier rather than naming it.
ANAPHORA = frozenset(
    {
        "bu", "bunu", "bunun", "bunda", "bundan", "bunlar", "bunlari",
        "o", "onu", "onun", "onda", "ondan", "onlar", "onlari",
        "su", "sunu", "sunun", "sunlar",
        "kendisi", "aynisi",
    }
)

#: Filler and pro-forms that carry no retrievable signal on their own.
#: "konu" is here because it stands in for a subject named earlier, exactly
#: like a pronoun; "peki bu konuda başka ne var?" is six tokens of pure
#: reference, which a length check happily lets through — and it embedded to
#: nothing in particular, so a corpus holding the answer returned no sources.
FILLER = frozenset(
    {
        "peki", "baska", "daha", "devami", "devaminda", "ayrica",
        "ne", "neler", "nedir", "var", "vardir", "yok",
        "konu", "konuda", "konuyla", "konusunda", "hakkinda", "ilgili",
        "bilgi", "ver", "verir", "soyle", "anlat", "goster",
        "misin", "musun", "misiniz", "musunuz", "mi", "mu",
        "icin", "ile", "ya", "ki", "de", "da", "bir",
    }
)

_UNINFORMATIVE = ANAPHORA | FILLER


class ContextTurn(BaseModel):
    role: str
    content: str


class SearchRequest(BaseModel):
    #: Whose private documents may be searched alongside the public corpus.
    #: Absent means anonymous, which is the public corpus alone -- never
    #: "everyone's". There is deliberately no value that means the latter.
    owner_user_id: Optional[str] = None
    query: str
    conversation_context: Optional[list[ContextTurn]] = None
    top_k: int = 8
    filters: Optional[dict[str, Any]] = None
    min_similarity: float = 0.62
    rerank: bool = True


class IngestDocument(BaseModel):
    #: NULL = public corpus (news). Non-NULL = private to that one user and
    #: retrievable by nobody else.
    owner_user_id: Optional[str] = None
    title: str
    source: str
    category: str
    document_type: str
    content: str
    source_url: Optional[str] = None
    language: str = "tr"
    ticker: Optional[str] = None
    period: Optional[str] = None
    published_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Both are loaded eagerly so /readyz flips only when the service can
    # genuinely answer. `mcp` waits on that healthcheck; a lazily-loaded model
    # would let it start against a retriever that still needs 30 seconds.
    embeddings.get_model()
    await store.open_pool()
    # Commit'lenmiş haber derleminin TABANI. Yeni bir klon RSS turunu ve
    # gömme işini beklemeden aranacak bir şeye sahip oluyor; ingestor üstüne
    # yazmaya devam ediyor. Açılışı hiçbir koşulda düşürmez.
    await corpus_seed.load(store.open_pool)
    yield
    await store.close_pool()


app = FastAPI(
    title="MoneyFast RAG",
    description="Retrieval over the curated market research corpus. Local embeddings, no external provider.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    """Ready means: model resident AND vector-db reachable by the RAG role."""
    try:
        embeddings.get_model()
        await store.ping()
    except Exception as exc:
        log.warning("readiness probe failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"rag not ready: {exc}")
    return {
        "status": "ready",
        "model": embeddings.model_name(),
        "dimension": embeddings.dimension(),
    }


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _needs_context(query: str) -> bool:
    """Does this query name its own subject, or point at an earlier one?

    Deliberately NOT a length check. A short query can be perfectly
    self-contained ("THYAO", "enflasyon ne durumda"), and a long one can be
    pure reference ("peki bu konuda başka ne var?"). Counting tokens gets
    both wrong in opposite directions; asking whether any word carries
    retrievable signal gets both right.
    """
    words = [word.strip("?!.,;:").translate(_FOLD).casefold() for word in query.split()]
    words = [word for word in words if word]
    if not words:
        # An empty query is rejected outright rather than silently becoming
        # the previous turn.
        return False
    # Every word points backwards or is filler: there is no subject to
    # search for, so the previous turn has to supply one.
    return all(word in _UNINFORMATIVE for word in words)


def _resolve_query(request: SearchRequest) -> str:
    """Fold the last user turn in when the query cannot stand alone.

    "peki ya o?" carries no retrievable signal by itself. Rather than embed
    it and return whatever the corpus centroid happens to be, the previous
    user turn is prepended and the combined string is reported back in
    query_echo so a wrong resolution is visible rather than mysterious.
    """
    query = request.query.strip()
    if not request.conversation_context or not _needs_context(query):
        return query
    for turn in reversed(request.conversation_context):
        if turn.role == "user" and turn.content.strip():
            return f"{turn.content.strip()} {query}".strip()
    return query


def _validate_filters(filters: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not filters:
        return {}
    unknown = sorted(set(filters) - ALLOWED_FILTERS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"unrecognised filter key(s): {', '.join(unknown)}",
        )
    return filters


def _row_to_result(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    doc_type = str(row.get("document_type") or "NEWS")
    ticker = row.get("ticker")
    return {
        "chunk_id": str(row["chunk_id"]),
        "doc_id": str(row["document_id"]),
        "title": str(row.get("title") or ""),
        # Verbatim. Any instruction-like text inside a passage is data, and
        # sanitising it here would hide an injection attempt from the layer
        # meant to detect it.
        "snippet": str(row["content"]),
        "publisher": str(row.get("source") or ""),
        "author": metadata.get("author"),
        "published_at": _iso(row.get("published_at")),
        "url": row.get("source_url"),
        "tickers": [ticker] if ticker else [],
        "doc_type": doc_type,
        "language": str(row.get("language") or "tr"),
        "score": float(row.get("similarity") or 0.0),
        "is_opinion": bool(metadata.get("is_opinion", doc_type.upper() in OPINION_DOC_TYPES)),
    }


@app.post("/search")
async def search(request: SearchRequest) -> dict[str, Any]:
    filters = _validate_filters(request.filters)
    resolved = _resolve_query(request)
    if not resolved:
        raise HTTPException(status_code=400, detail="query must not be empty")

    vector = embeddings.to_pgvector(embeddings.embed_query(resolved))

    try:
        rows = await store.match_chunks(
            vector,
            request.owner_user_id,
            top_k=request.top_k,
            min_similarity=request.min_similarity,
            tickers=filters.get("tickers"),
            categories=filters.get("categories"),
            languages=filters.get("languages"),
            document_types=filters.get("doc_types"),
            published_after=filters.get("published_after"),
            published_before=filters.get("published_before"),
            publishers=filters.get("publishers"),
        )
    except Exception as exc:
        log.exception("retrieval failed")
        # 503 maps to UpstreamUnavailableError in the MCP client, which the
        # orchestrator must report as "sources could not be consulted". It
        # must never look like an empty-but-valid corpus answer.
        raise HTTPException(status_code=503, detail=f"vector store unavailable: {exc}")

    snapshot = await store.index_snapshot()
    as_of = snapshot.get("as_of")
    now = datetime.now(timezone.utc)
    lag_minutes = int((now - as_of).total_seconds() // 60) if as_of else 0
    threshold = int(os.getenv("RAG_INDEX_LAG_THRESHOLD_MINUTES", str(DEFAULT_LAG_THRESHOLD_MINUTES)))

    return {
        "as_of": _iso(as_of or now),
        "source": f"VECTOR_STORE::{os.getenv('RAG_CORPUS_VERSION', 'market_corpus_v1')}",
        "is_delayed": lag_minutes > threshold,
        "index_lag_minutes": max(0, lag_minutes),
        "results": [_row_to_result(row) for row in rows],
        "query_echo": resolved,
    }


@app.delete("/documents/{document_id}")
async def delete_document(document_id: str, owner_user_id: str) -> dict[str, Any]:
    """Kullanıcının kendi belgesini derlemden kaldırır.

    `owner_user_id` ZORUNLU bir sorgu parametresi. Opsiyonel olsaydı, onu
    göndermeyen bir çağrı sahiplik denetimi olmadan silme yapardı -- ve o
    çağrıyı yazmak, unutmak kadar kolay olurdu.
    """
    try:
        deleted = await store.delete_document(document_id, owner_user_id)
    except Exception as exc:
        log.exception("document deletion failed")
        raise HTTPException(status_code=503, detail=f"vector store unavailable: {exc}")

    if not deleted:
        # Başkasının belgesi ile hiç olmayan belge AYNI cevabı alıyor: ikisini
        # ayırmak, id deneyerek başka kullanıcıların belgelerinin varlığını
        # keşfetmeye izin verirdi.
        raise HTTPException(status_code=404, detail="document not found")
    return {"status": "deleted", "document_id": document_id}


@app.post("/ingest")
async def ingest(document: IngestDocument) -> dict[str, Any]:
    """Load one document: split, embed, store. Idempotent by content hash."""
    text = document.content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="content must not be empty")

    pieces = chunking.split(text)
    if not pieces:  # pragma: no cover - unreachable while the splitter keeps
        # its current contract (non-empty input yields at least one chunk).
        # Kept so a future chunker change fails as a 400 rather than as an
        # empty document silently written with no retrievable content.
        raise HTTPException(status_code=400, detail="content produced no chunks")

    vectors = embeddings.embed_passages(pieces)
    triples = [
        (index, piece, embeddings.to_pgvector(vector))
        for index, (piece, vector) in enumerate(zip(pieces, vectors))
    ]

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    document_id, written = await store.ingest(
        store.open_pool,
        {
            "title": document.title,
            "source": document.source,
            "source_url": document.source_url,
            "category": document.category,
            "language": document.language,
            "ticker": document.ticker,
            "document_type": document.document_type,
            "period": document.period,
            "published_at": document.published_at,
            "content_hash": content_hash,
            "owner_user_id": document.owner_user_id,
        },
        triples,
    )

    if document_id is None:
        return {"status": "duplicate", "content_hash": content_hash, "chunks_written": 0}
    return {
        "status": "ingested",
        "document_id": document_id,
        "content_hash": content_hash,
        "chunks_written": written,
    }
