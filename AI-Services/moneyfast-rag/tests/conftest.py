"""Shared fixtures for the RAG service suite.

Neither the ONNX model nor a real Postgres is touched. The model is replaced
by a deterministic hash-based encoder so retrieval assertions are stable, and
the store is replaced by an in-memory double. Loading a real model in CI would
add ~90MB and several seconds per run to prove something the model's own
authors already tested.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings  # noqa: E402
import store  # noqa: E402


class FakeEmbedder:
    """Deterministic stand-in with the same call shape as fastembed."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.seen: list[str] = []

    def embed(self, texts):
        for text in texts:
            self.seen.append(text)
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            yield [digest[i % len(digest)] / 255.0 for i in range(self.dimension)]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSION",
        "RAG_CORPUS_VERSION",
        "RAG_INDEX_LAG_THRESHOLD_MINUTES",
        "RAG_DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    embedder = FakeEmbedder()
    monkeypatch.setattr(embeddings, "_model", embedder)
    return embedder


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Records calls and returns whatever the test stages."""
    state: dict[str, Any] = {
        "rows": [],
        "snapshot": {"as_of": None, "newest_published_at": None, "document_count": 0},
        "calls": [],
        "ingest_result": ("doc-1", 2),
        "ping": True,
    }

    async def _match_chunks(query_vector, **kwargs):
        state["calls"].append({"vector": query_vector, **kwargs})
        return state["rows"]

    async def _index_snapshot():
        return state["snapshot"]

    async def _ping():
        if state["ping"] is not True:
            raise state["ping"]
        return True

    async def _ingest(conn_factory, document, chunks):
        state["ingested"] = {"document": document, "chunks": chunks}
        return state["ingest_result"]

    async def _open_pool():
        return object()

    async def _close_pool():
        return None

    monkeypatch.setattr(store, "match_chunks", _match_chunks)
    monkeypatch.setattr(store, "index_snapshot", _index_snapshot)
    monkeypatch.setattr(store, "ping", _ping)
    monkeypatch.setattr(store, "ingest", _ingest)
    monkeypatch.setattr(store, "open_pool", _open_pool)
    monkeypatch.setattr(store, "close_pool", _close_pool)
    return state


@pytest.fixture
def client(fake_embedder, fake_store):
    """TestClient with lifespan active, so startup wiring is exercised."""
    from fastapi.testclient import TestClient

    import app as app_module

    with TestClient(app_module.app) as test_client:
        yield test_client
