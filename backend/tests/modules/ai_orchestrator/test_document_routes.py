"""Belge uçları: yükle, listele, sil.

Bu üçünün ortak iddiası kimlik. Anonim bir yükleme, sahibi olmayan bir belge
demek -- paylaşılan derleme giren ve bir daha silinemeyen bir dosya.
"""

import contextlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.main import app
from app.modules.ai_orchestrator import document_service
from app.modules.ai_orchestrator.deps import ChatIdentity, resolve_chat_identity

USER = "11111111-1111-1111-1111-111111111111"
BASE = "/api/ai_orchestrator/documents"


@contextlib.contextmanager
def as_identity(user_id):
    app.dependency_overrides[resolve_chat_identity] = lambda: ChatIdentity(
        user_id=user_id, token_present=user_id is not None
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(resolve_chat_identity, None)


def record(**overrides):
    row = {
        "id": "doc-1", "filename": "bilanco.pdf", "kind": "PDF",
        "size_bytes": 1024, "units": 12, "char_count": 4096,
        "truncated": False, "created_at": "2026-08-31T10:00:00Z",
    }
    row.update(overrides)
    return SimpleNamespace(**row)


class TestUpload:
    def test_an_anonymous_upload_is_refused(self, client):
        """Sahibi olmayan bir belge paylaşılan derleme girer ve silinemez."""
        with as_identity(None):
            response = client.post(
                BASE, files={"file": ("a.txt", b"metin", "text/plain")}
            )
        assert response.status_code == 401

    def test_it_stores_under_the_caller(self, client, mocker):
        store = mocker.patch.object(
            document_service, "store", return_value=record()
        )
        mocker.patch.object(
            document_service, "as_dict",
            return_value={
                "id": "doc-1", "filename": "bilanco.pdf", "kind": "PDF",
                "size_bytes": 1024, "units": 12, "char_count": 4096,
                "truncated": False, "created_at": "2026-08-31T10:00:00Z",
            },
        )

        with as_identity(USER):
            response = client.post(
                BASE,
                files={"file": ("bilanco.pdf", b"%PDF-1.4", "application/pdf")},
                data={"thread_id": "t1"},
            )

        assert response.status_code == 201
        assert store.call_args.kwargs["user_id"] == USER
        assert store.call_args.kwargs["thread_id"] == "t1"

    def test_a_service_refusal_reaches_the_caller(self, client, mocker):
        mocker.patch.object(
            document_service, "store",
            side_effect=HTTPException(status_code=415, detail="okunamıyor"),
        )
        with as_identity(USER):
            response = client.post(
                BASE, files={"file": ("a.docx", b"x", "application/octet-stream")}
            )
        assert response.status_code == 415


class TestListing:
    def test_an_anonymous_caller_gets_an_empty_list_not_a_401(self, client):
        """Yüklediği bir şey yok ve "belgeniz yok" doğru cevap."""
        with as_identity(None):
            body = client.get(BASE).json()

        assert body["documents"] == []
        assert ".pdf" in body["accepted"]
        assert body["max_bytes"] > 0

    def test_it_lists_only_the_callers_documents(self, client, mocker):
        listing = mocker.patch.object(
            document_service, "listing", return_value=[record()]
        )
        with as_identity(USER):
            body = client.get(BASE).json()

        assert listing.call_args.args[1] == USER
        assert body["documents"][0]["filename"] == "bilanco.pdf"

    def test_the_accepted_formats_are_advertised(self, client):
        """Arayüz dosya seçiciyi buna göre kuruyor; iki listenin ayrışması,
        seçilebilen ama reddedilen bir dosya demek."""
        with as_identity(USER):
            body = client.get(BASE).json()
        assert set(body["accepted"]) >= {".pdf", ".csv", ".txt", ".xlsx", ".pptx"}


class TestDelete:
    def test_an_anonymous_delete_is_refused(self, client):
        with as_identity(None):
            assert client.delete(f"{BASE}/doc-1").status_code == 401

    def test_the_caller_is_passed_as_the_owner(self, client, mocker):
        delete = mocker.patch.object(document_service, "delete")
        with as_identity(USER):
            response = client.delete(f"{BASE}/doc-1")

        assert response.status_code == 204
        assert delete.call_args.args[1] == USER
        assert delete.call_args.args[2] == "doc-1"

    def test_someone_elses_document_is_not_found(self, client, mocker):
        mocker.patch.object(
            document_service, "delete",
            side_effect=HTTPException(status_code=404, detail="Belge bulunamadı."),
        )
        with as_identity(USER):
            assert client.delete(f"{BASE}/doc-1").status_code == 404
