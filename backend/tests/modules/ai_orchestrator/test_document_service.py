"""Yüklenen belgelerin yaşam döngüsü.

En önemli iddialar sahiplik ve SIRA ile ilgili: bir belge ya hem listede hem
aramada vardır ya da ikisinde de yoktur. Arada kalan her durum, kullanıcının
gördüğüyle sistemin bildiğinin ayrışması demek.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.ai_orchestrator import document_service, documents

USER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def db():
    session = MagicMock(spec=Session)
    session.refresh.side_effect = lambda record: setattr(record, "id", "doc-1")
    return session


class TestStore:
    def test_it_embeds_with_the_uploader_as_owner(self, db, mocker):
        """Sahipsiz gömülen bir belge PAYLAŞILAN derleme girer."""
        post = mocker.patch.object(
            document_service.httpx, "post",
            return_value=SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"document_id": "rag-1"},
            ),
        )

        document_service.store(
            db, user_id=USER, thread_id="t1",
            filename="bilanco.txt", payload=b"Hasilat 585 milyar TL.",
        )

        assert post.call_args.kwargs["json"]["owner_user_id"] == USER

    def test_the_record_describes_what_was_read(self, db, mocker):
        mocker.patch.object(
            document_service.httpx, "post",
            return_value=SimpleNamespace(
                raise_for_status=lambda: None, json=lambda: {"document_id": "rag-1"},
            ),
        )

        record = document_service.store(
            db, user_id=USER, thread_id=None,
            filename="tablo.csv", payload=b"a,b\nc,d",
        )

        assert record.kind == "CSV"
        assert record.units == 2
        assert record.rag_document_id == "rag-1"
        assert db.commit.called

    def test_an_oversized_file_is_refused_before_it_is_parsed(self, db, mocker):
        parse = mocker.patch.object(documents, "extract")

        with pytest.raises(HTTPException) as exc:
            document_service.store(
                db, user_id=USER, thread_id=None, filename="big.txt",
                payload=b"x" * (documents.MAX_UPLOAD_BYTES + 1),
            )

        assert exc.value.status_code == 413
        assert parse.called is False

    def test_an_unsupported_format_is_415(self, db):
        with pytest.raises(HTTPException) as exc:
            document_service.store(
                db, user_id=USER, thread_id=None,
                filename="a.docx", payload=b"anything",
            )
        assert exc.value.status_code == 415

    def test_an_unreadable_file_is_422(self, db):
        with pytest.raises(HTTPException) as exc:
            document_service.store(
                db, user_id=USER, thread_id=None, filename="a.pdf", payload=b"nope",
            )
        assert exc.value.status_code == 422

    def test_an_unreachable_embedder_refuses_the_upload(self, db, mocker):
        """Aranamayan bir belge, kullanıcının yüklediğini sandığı ama hiçbir
        soruya cevap vermeyen bir satırdır. Kaydedilmiyor."""
        mocker.patch.object(
            document_service.httpx, "post",
            side_effect=httpx.ConnectError("connection refused"),
        )

        with pytest.raises(HTTPException) as exc:
            document_service.store(
                db, user_id=USER, thread_id=None, filename="a.txt", payload=b"metin",
            )

        assert exc.value.status_code == 503
        assert db.commit.called is False


class TestListing:
    def test_it_filters_by_the_caller(self, db):
        document_service.listing(db, USER)
        assert db.query.return_value.filter.called


class TestDelete:
    def _found(self, db, record):
        db.query.return_value.filter.return_value.first.return_value = record
        return db

    def test_a_missing_document_is_404(self, db):
        self._found(db, None)
        with pytest.raises(HTTPException) as exc:
            document_service.delete(db, USER, "doc-1")
        assert exc.value.status_code == 404

    def test_it_removes_the_embedded_copy_too(self, db, mocker):
        """Yalnızca uygulama satırını silmek, arayüzde görünmeyen ama aramada
        çıkmaya devam eden bir belge bırakırdı."""
        delete = mocker.patch.object(
            document_service.httpx, "delete",
            return_value=SimpleNamespace(status_code=200, raise_for_status=lambda: None),
        )
        self._found(db, SimpleNamespace(id="doc-1", rag_document_id="rag-1"))

        document_service.delete(db, USER, "doc-1")

        assert "rag-1" in delete.call_args.args[0]
        assert delete.call_args.kwargs["params"]["owner_user_id"] == USER
        assert db.delete.called

    def test_a_failed_vector_delete_keeps_the_row(self, db, mocker):
        """"Sildim" deyip aranmaya devam eden bir belge bırakmak, silme
        düğmesini yalan söyleyen bir düğme yapar."""
        mocker.patch.object(
            document_service.httpx, "delete",
            side_effect=httpx.ConnectError("connection refused"),
        )
        self._found(db, SimpleNamespace(id="doc-1", rag_document_id="rag-1"))

        with pytest.raises(HTTPException) as exc:
            document_service.delete(db, USER, "doc-1")

        assert exc.value.status_code == 503
        assert db.delete.called is False

    def test_a_vector_side_404_is_not_an_error(self, db, mocker):
        """Gömülü kopya zaten yoksa silme tamamlanmalı: aksi hâlde kullanıcı
        silinemeyen bir satırla kalırdı."""
        mocker.patch.object(
            document_service.httpx, "delete",
            return_value=SimpleNamespace(
                status_code=404,
                raise_for_status=lambda: (_ for _ in ()).throw(AssertionError("çağrılmamalı")),
            ),
        )
        self._found(db, SimpleNamespace(id="doc-1", rag_document_id="rag-1"))

        document_service.delete(db, USER, "doc-1")

        assert db.delete.called

    def test_a_record_without_an_embedded_copy_is_just_deleted(self, db, mocker):
        delete = mocker.patch.object(document_service.httpx, "delete")
        self._found(db, SimpleNamespace(id="doc-1", rag_document_id=None))

        document_service.delete(db, USER, "doc-1")

        assert delete.called is False
        assert db.delete.called
