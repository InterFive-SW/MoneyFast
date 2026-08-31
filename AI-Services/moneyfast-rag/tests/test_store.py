"""vector-db adapter.

No Postgres here. What these tests protect is the part that fails silently:
`rag.match_chunks` is called positionally, so a parameter inserted in the
wrong place produces a query that runs and returns plausible-looking rows
filtered by the wrong column.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

import store


class FakeCursor:
    #: DELETE kaç satır etkiledi. `delete_document` bunu okuyor ve
    #: "gerçekten bir şey silindi mi" sorusunun cevabı bu.
    rowcount = 0

    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, rows):
        self._rows = rows
        self.executed: list[tuple] = []
        #: Testin ayarladığı DELETE sonucu.
        self.rowcount = 0

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        cursor = FakeCursor(self._rows)
        cursor.rowcount = self.rowcount
        return cursor

    @asynccontextmanager
    async def transaction(self):
        yield self


class FakePool:
    def __init__(self, rows=None):
        self.conn = FakeConnection(rows or [])
        self.closed = False

    @asynccontextmanager
    async def connection(self):
        yield self.conn

    async def close(self):
        self.closed = True


@pytest.fixture
def pool(monkeypatch):
    fake = FakePool()
    monkeypatch.setattr(store, "_pool", fake)
    return fake


class TestConfiguration:
    def test_missing_url_fails_loudly(self, monkeypatch):
        monkeypatch.delenv("RAG_DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="RAG_DATABASE_URL is not set"):
            store.database_url()

    def test_url_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("RAG_DATABASE_URL", "postgresql://rag_user:x@vector-db:5432/moneyfast_rag")
        assert store.database_url().endswith("/moneyfast_rag")


class TestFilterNormalisation:
    @pytest.mark.parametrize("value", [None, [], ()])
    def test_absent_and_empty_both_mean_no_filter(self, value):
        assert store._array(value) is None

    def test_values_are_stringified(self):
        assert store._array(["THYAO", 42]) == ["THYAO", "42"]


class TestMatchChunks:
    @pytest.mark.asyncio
    async def test_parameters_are_passed_by_name_in_the_documented_order(self, pool):
        await store.match_chunks(
            "[0.1,0.2]",
            None,
            top_k=5,
            min_similarity=0.7,
            tickers=["THYAO"],
            document_types=["FILING"],
            published_after="2025-01-01T00:00:00Z",
        )
        _sql, params = pool.conn.executed[-1]
        assert params["embedding"] == "[0.1,0.2]"
        assert params["threshold"] == 0.7
        assert params["tickers"] == ["THYAO"]
        assert params["document_types"] == ["FILING"]
        assert params["published_after"] == "2025-01-01T00:00:00Z"
        assert params["publishers"] is None

    @pytest.mark.asyncio
    async def test_top_k_is_clamped_to_the_sql_ceiling(self, pool):
        """The contract allows 25; rag.match_chunks raises above 20. Clamping
        here keeps a legal tool call from surfacing as "sources could not be
        consulted"."""
        await store.match_chunks("[0.1]", None, top_k=25, min_similarity=None)
        assert pool.conn.executed[-1][1]["top_k"] == store.MAX_TOP_K

    @pytest.mark.asyncio
    async def test_top_k_below_one_is_raised_to_one(self, pool):
        await store.match_chunks("[0.1]", None, top_k=0, min_similarity=None)
        assert pool.conn.executed[-1][1]["top_k"] == 1

    @pytest.mark.asyncio
    async def test_rows_are_returned_unchanged(self, monkeypatch):
        fake = FakePool(rows=[{"chunk_id": "c1"}])
        monkeypatch.setattr(store, "_pool", fake)
        assert await store.match_chunks(
            "[0.1]", None, top_k=5, min_similarity=None
        ) == [{"chunk_id": "c1"}]


class TestIndexSnapshot:
    @pytest.mark.asyncio
    async def test_returns_the_row(self, monkeypatch):
        fake = FakePool(rows=[{"as_of": None, "newest_published_at": None, "document_count": 0}])
        monkeypatch.setattr(store, "_pool", fake)
        assert (await store.index_snapshot())["document_count"] == 0

    @pytest.mark.asyncio
    async def test_empty_corpus_yields_a_usable_default(self, pool):
        """No rows at all must not become a None the caller then subscripts."""
        assert await store.index_snapshot() == {
            "as_of": None,
            "newest_published_at": None,
            "document_count": 0,
        }


class TestPing:
    @pytest.mark.asyncio
    async def test_issues_a_trivial_query(self, pool):
        assert await store.ping() is True
        assert "SELECT 1" in pool.conn.executed[-1][0]


class TestIngest:
    @pytest.mark.asyncio
    async def test_new_document_writes_its_chunks(self, monkeypatch):
        fake = FakePool(rows=[{"id": "11111111-1111-1111-1111-111111111111"}])
        monkeypatch.setattr(store, "_pool", fake)

        document_id, written = await store.ingest(
            store.open_pool,
            {
                "title": "T", "source": "KAP", "source_url": None, "category": "c",
                "language": "tr", "ticker": "THYAO", "document_type": "FILING",
                "period": None, "published_at": None, "content_hash": "a" * 64,
            },
            [(0, "ilk parça", "[0.1]"), (1, "ikinci parça", "[0.2]")],
        )
        assert document_id == "11111111-1111-1111-1111-111111111111"
        assert written == 2

    @pytest.mark.asyncio
    async def test_duplicate_hash_writes_nothing(self, pool):
        """ON CONFLICT DO NOTHING returns no row. Re-ingesting an unchanged
        corpus must not create a second set of chunks competing for the same
        retrieval slots."""
        document_id, written = await store.ingest(
            store.open_pool,
            {
                "title": "T", "source": "KAP", "source_url": None, "category": "c",
                "language": "tr", "ticker": None, "document_type": "FILING",
                "period": None, "published_at": None, "content_hash": "b" * 64,
            },
            [(0, "ilk parça", "[0.1]")],
        )
        assert document_id is None
        assert written == 0

    @pytest.mark.asyncio
    async def test_chunk_rows_carry_the_configured_model_name(self, monkeypatch):
        fake = FakePool(rows=[{"id": "22222222-2222-2222-2222-222222222222"}])
        monkeypatch.setattr(store, "_pool", fake)
        monkeypatch.setenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

        await store.insert_chunks(fake.conn, "doc", [(0, "iki kelime", "[0.1]")])
        params = fake.conn.executed[-1][1]
        assert params["model"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        assert params["token_count"] == 2


class TestPoolLifecycle:
    @pytest.mark.asyncio
    async def test_open_pool_is_idempotent(self, pool):
        assert await store.open_pool() is pool
        assert await store.open_pool() is pool

    @pytest.mark.asyncio
    async def test_close_pool_closes_and_clears(self, pool):
        await store.close_pool()
        assert pool.closed is True
        assert store._pool is None

    @pytest.mark.asyncio
    async def test_close_pool_without_a_pool_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(store, "_pool", None)
        await store.close_pool()
        assert store._pool is None


class TestPoolConstruction:
    @pytest.mark.asyncio
    async def test_pool_is_built_from_the_configured_url(self, monkeypatch):
        monkeypatch.setattr(store, "_pool", None)
        monkeypatch.setenv("RAG_DATABASE_URL", "postgresql://rag_user:x@vector-db:5432/moneyfast_rag")
        monkeypatch.setenv("RAG_DB_POOL_MAX", "3")
        built = {}

        class StubPool:
            def __init__(self, url, **kwargs):
                built["url"] = url
                built.update(kwargs)

            async def open(self, wait=False, timeout=None):
                built["opened"] = True

        monkeypatch.setattr(store, "AsyncConnectionPool", StubPool)
        pool = await store.open_pool()

        assert built["url"].endswith("/moneyfast_rag")
        assert built["max_size"] == 3
        assert built["opened"] is True
        # Constructed lazily and then reused; a second call must not rebuild.
        assert await store.open_pool() is pool
        monkeypatch.setattr(store, "_pool", None)


class TestOwnership:
    """Whose documents a search may reach.

    Retrieval was written for one shared public corpus of news. Once users can
    upload their own files, a document that any other user's query can return
    is a disclosure, not a bug in a feature. These tests pin the mechanism on
    the Python side; the SQL side is pinned by 0004 and the permissions test.
    """

    @pytest.mark.asyncio
    async def test_the_owner_is_passed_to_the_sql_function(self, pool):
        await store.match_chunks(
            "[0.1]", "11111111-1111-1111-1111-111111111111",
            top_k=5, min_similarity=None,
        )
        _sql, params = pool.conn.executed[-1]
        assert params["owner"] == "11111111-1111-1111-1111-111111111111"

    @pytest.mark.asyncio
    async def test_anonymous_passes_null_rather_than_a_wildcard(self, pool):
        """There is deliberately no value meaning "everyone's documents".
        NULL means the public corpus alone, because `owner = NULL` is never
        true for any row."""
        await store.match_chunks("[0.1]", None, top_k=5, min_similarity=None)
        _sql, params = pool.conn.executed[-1]
        assert params["owner"] is None

    @pytest.mark.asyncio
    async def test_the_owner_argument_cannot_be_omitted(self, pool):
        """The whole safety property. A call site that was never updated must
        break, not quietly widen its results."""
        with pytest.raises(TypeError):
            await store.match_chunks("[0.1]", top_k=5, min_similarity=None)

    @pytest.mark.asyncio
    async def test_the_owner_is_cast_so_a_text_id_cannot_widen_the_match(self, pool):
        sql, _params = pool.conn.executed[-1] if pool.conn.executed else ("", {})
        await store.match_chunks("[0.1]", None, top_k=5, min_similarity=None)
        sql, _ = pool.conn.executed[-1]
        assert "%(owner)s::uuid" in sql


class TestDeleteDocument:
    """Silmenin SQL tarafı: sahiplik WHERE'in içinde, açık derlem korunuyor."""

    @pytest.mark.asyncio
    async def test_the_owner_is_part_of_the_where_clause(self, pool):
        pool.conn.rowcount = 1
        await store.delete_document(
            "33333333-3333-3333-3333-333333333333",
            "11111111-1111-1111-1111-111111111111",
        )
        sql, params = pool.conn.executed[-1]
        assert "owner_user_id = %(owner)s::uuid" in sql
        assert params["owner"] == "11111111-1111-1111-1111-111111111111"

    @pytest.mark.asyncio
    async def test_the_public_corpus_cannot_be_deleted_through_this(self, pool):
        """`owner_user_id IS NOT NULL` ayrıca yazılı. Bir kullanıcı isteğinin
        ortak haber derleminden satır düşürebilmesi, silme yetkisinin
        sızması olurdu."""
        pool.conn.rowcount = 0
        await store.delete_document("id", "owner")
        sql, _ = pool.conn.executed[-1]
        assert "owner_user_id IS NOT NULL" in sql

    @pytest.mark.asyncio
    async def test_it_reports_whether_a_row_actually_went(self, pool):
        pool.conn.rowcount = 1
        assert await store.delete_document("id", "owner") is True
        pool.conn.rowcount = 0
        assert await store.delete_document("id", "owner") is False
