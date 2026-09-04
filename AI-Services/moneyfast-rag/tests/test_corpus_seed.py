"""Commit'lenmiş haber derleminin yükleyicisi.

En önemli iddia SAHİPSİZLİK: dışa aktarılan belgeler herkese açık derleme
girmeli. Bir sahip atansaydı iki türlü de yanlış olurdu -- dışa aktaranın
id'si klonda kimseye ait değil ve belgeler görünmez olurdu; klonun ilk
kullanıcısına atansa ortak haber derlemi bir kişinin özel dosyaları olurdu.
"""

from __future__ import annotations

import csv
import gzip
import io
from contextlib import asynccontextmanager

import pytest

import corpus_seed

HEADER = (
    "title", "source", "source_url", "category", "language", "ticker",
    "document_type", "period", "published_at", "content_hash",
    "chunk_index", "content", "embedding",
)


def row(content_hash="a" * 64, chunk_index=0, content="Halkbank kaynak sağladı"):
    return (
        "Halkbank haberi", "Patronlar Dünyası", "https://x", "NEWS", "tr", "",
        "NEWS", "", "2026-08-25T00:00:00Z", content_hash,
        chunk_index, content, "[0.1,0.2]",
    )


def write(path, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    for r in rows:
        writer.writerow(r)
    path.write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), 9, mtime=0))


class FakeCursor:
    def __init__(self, result):
        self._result = result

    async def fetchone(self):
        return self._result


class FakeConnection:
    def __init__(self, insert_result):
        self.executed = []
        self._insert_result = insert_result

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeCursor(self._insert_result if "INSERT INTO rag.documents" in sql else None)

    @asynccontextmanager
    async def transaction(self):
        yield self


class FakePool:
    def __init__(self, insert_result):
        self.conn = FakeConnection(insert_result)

    @asynccontextmanager
    async def connection(self):
        yield self.conn


def pool_factory(insert_result={"id": "doc-1"}):
    pool = FakePool(insert_result)

    async def _open():
        return pool

    _open.pool = pool
    return _open


@pytest.fixture
def seed_file(tmp_path, monkeypatch):
    path = tmp_path / "corpus.csv.gz"
    monkeypatch.setattr(corpus_seed, "SEED_FILE", path)
    return path


class TestOwnership:
    @pytest.mark.asyncio
    async def test_documents_are_written_without_an_owner(self, seed_file):
        write(seed_file, [row()])
        factory = pool_factory()

        await corpus_seed.load(factory)

        sql, params = factory.pool.conn.executed[0]
        assert "owner_user_id" in sql
        assert "NULL" in sql
        # Sahip alanı parametrelerde HİÇ yok: bir gün oraya bir değer
        # geçmesi, ortak derlemi bir kişinin dosyaları yapardı.
        assert "owner_user_id" not in params

    @pytest.mark.asyncio
    async def test_the_conflict_target_is_the_public_index(self, seed_file):
        """Açık derlemin tekilliği kısmi bir indeks; başka bir hedef ya
        çakışmayı kaçırır ya da özel belgelerinkine dokunurdu."""
        write(seed_file, [row()])
        factory = pool_factory()

        await corpus_seed.load(factory)

        sql, _ = factory.pool.conn.executed[0]
        assert "ON CONFLICT (content_hash) WHERE owner_user_id IS NULL" in sql


class TestLoading:
    @pytest.mark.asyncio
    async def test_a_documents_chunks_travel_with_it(self, seed_file):
        write(seed_file, [row(chunk_index=0), row(chunk_index=1, content="ikinci")])
        factory = pool_factory()

        assert await corpus_seed.load(factory) == 1
        chunk_calls = [
            c for c in factory.pool.conn.executed if "INSERT INTO rag.chunks" in c[0]
        ]
        assert len(chunk_calls) == 2

    @pytest.mark.asyncio
    async def test_vectors_come_from_the_file_not_recomputed(self, seed_file):
        """`fastembed` yerelde çalışıyor, yani klon gömmeleri kendisi de
        üretebilirdi -- bu, bayt bayt aynı sonuç için harcanan CPU zamanı
        olurdu."""
        write(seed_file, [row()])
        factory = pool_factory()

        await corpus_seed.load(factory)

        chunk = next(
            c for c in factory.pool.conn.executed if "INSERT INTO rag.chunks" in c[0]
        )
        assert chunk[1]["vec"] == "[0.1,0.2]"
        assert "::vector" in chunk[0]

    @pytest.mark.asyncio
    async def test_an_existing_document_writes_no_chunks(self, seed_file):
        """Aynı içeriğin iki kopyası aynı arama sırasında yarışırdı."""
        write(seed_file, [row()])
        factory = pool_factory(insert_result=None)

        assert await corpus_seed.load(factory) == 0
        assert not [
            c for c in factory.pool.conn.executed if "INSERT INTO rag.chunks" in c[0]
        ]

    @pytest.mark.asyncio
    async def test_an_empty_cell_becomes_null(self, seed_file):
        write(seed_file, [row()])
        factory = pool_factory()

        await corpus_seed.load(factory)

        _, params = factory.pool.conn.executed[0]
        assert params["ticker"] is None
        assert params["period"] is None


class TestItNeverBlocksStartup:
    @pytest.mark.asyncio
    async def test_a_missing_file_is_not_an_error(self, seed_file):
        assert await corpus_seed.load(pool_factory()) == 0

    @pytest.mark.asyncio
    async def test_an_unreadable_file_is_not_an_error(self, seed_file):
        """Aranacak haber olmaması, servisin hiç açılmamasından iyidir."""
        seed_file.write_bytes("bu gzip değil".encode("utf-8"))
        assert await corpus_seed.load(pool_factory()) == 0

    @pytest.mark.asyncio
    async def test_an_unreachable_database_is_not_an_error(self, seed_file):
        write(seed_file, [row()])

        async def _boom():
            raise RuntimeError("connection refused")

        assert await corpus_seed.load(_boom) == 0
