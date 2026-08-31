"""Yüklenen belgelerin yaşam döngüsü: yükle, listele, sil.

Metin `rag` servisine gömülmek üzere HTTP ile gidiyor. Backend'in vektör
veritabanı kredensiyeli yok ve olmamalı -- CLAUDE.md'ye göre o kredensiyeli
tutan TEK bileşen `rag` servisi.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings

from . import documents
from .models import ChatDocument

log = logging.getLogger(__name__)

#: `rag` servisine verilen kategori ve tür. Haber derleminden ayırıyor:
#: bir sonraki adımda "yalnızca kendi belgelerim" gibi bir filtre istenirse
#: dayanak bu alan olur.
CATEGORY = "USER_UPLOAD"
DOCUMENT_TYPE = "USER_DOCUMENT"

RAG_TIMEOUT_SECONDS = 60.0


def _rag_url(path: str) -> str:
    return f"{settings.RAG_URL.rstrip('/')}{path}"


def store(
    db: Session,
    *,
    user_id: str,
    thread_id: Optional[str],
    filename: str,
    payload: bytes,
) -> ChatDocument:
    """Bir dosyayı çıkar, gömdür ve kaydet.

    Sıra önemli: önce gömme, sonra kayıt. Ters olsaydı gömme başarısız
    olduğunda kullanıcı listesinde aramada hiç çıkmayan bir belge görürdü --
    "yüklendi" diyen ve hiçbir soruya cevap vermeyen bir satır.
    """
    if len(payload) > documents.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Dosya {documents.MAX_UPLOAD_BYTES // (1024 * 1024)} MB "
                "sınırını aşıyor."
            ),
        )

    try:
        extracted = documents.extract(filename, payload)
    except documents.UnsupportedDocument as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Bu dosya türü okunamıyor: {exc}",
        ) from exc
    except documents.UnreadableDocument as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dosya okunamadı: {exc}",
        ) from exc

    rag_document_id = _embed(
        user_id=user_id, filename=filename, text=extracted.text
    )

    record = ChatDocument(
        user_id=user_id,
        thread_id=thread_id,
        filename=filename[:255],
        kind=documents.SUPPORTED.get(documents.extension_of(filename), "Belge"),
        size_bytes=len(payload),
        units=extracted.units,
        char_count=len(extracted.text),
        truncated=extracted.truncated,
        rag_document_id=rag_document_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _embed(*, user_id: str, filename: str, text: str) -> Optional[str]:
    """Metni `rag` servisine gömdürür ve belge id'sini döner.

    Aynı dosyayı ikinci kez yükleyen kullanıcı "duplicate" alır ve mevcut
    belgesi korunur; bu bir hata değil. Servis erişilemezse yükleme
    reddediliyor: aranamayan bir belge, kullanıcının yüklediğini sandığı ama
    hiçbir soruya cevap vermeyen bir satırdır.
    """
    body = {
        "owner_user_id": user_id,
        "title": filename,
        "source": "Kullanıcı yüklemesi",
        "category": CATEGORY,
        "document_type": DOCUMENT_TYPE,
        "language": "tr",
        "content": text,
    }
    try:
        response = httpx.post(
            _rag_url("/ingest"), json=body, timeout=RAG_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.error("document embedding failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Belge şu anda işlenemiyor. Birazdan tekrar deneyin.",
        ) from exc
    return (response.json() or {}).get("document_id")


def listing(db: Session, user_id: str) -> list[ChatDocument]:
    """Kullanıcının kendi belgeleri, yeniden eskiye."""
    return (
        db.query(ChatDocument)
        .filter(ChatDocument.user_id == user_id)
        .order_by(ChatDocument.created_at.desc(), ChatDocument.id.desc())
        .all()
    )


def delete(db: Session, user_id: str, document_id: str) -> None:
    """Belgeyi hem listeden hem aramadan kaldırır.

    Sahiplik filtresi sorgunun İÇİNDE: önce getirip sonra sahibini kontrol
    etmek de doğru çalışır ama bir gün kontrolü düşürmek tek satırlık bir
    hata olur, filtreyi düşürmek ise sorguyu anlamsız yapar.

    Yalnızca uygulama satırını silmek, arayüzde görünmeyen ama aramada
    çıkmaya devam eden bir belge bırakırdı -- kullanıcının sildiğini sandığı
    ve hâlâ okunan bir dosya.
    """
    record = (
        db.query(ChatDocument)
        .filter(ChatDocument.id == document_id, ChatDocument.user_id == user_id)
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Belge bulunamadı."
        )

    if record.rag_document_id:
        _forget(user_id=user_id, rag_document_id=record.rag_document_id)

    db.delete(record)
    db.commit()


def _forget(*, user_id: str, rag_document_id: str) -> None:
    """Gömülü kopyayı `rag` servisinden siler.

    Vektör tarafı silinemezse uygulama satırı da SİLİNMEZ: kullanıcıya
    "sildim" deyip aranmaya devam eden bir belge bırakmak, silme düğmesini
    yalan söyleyen bir düğme yapar.
    """
    try:
        response = httpx.delete(
            _rag_url(f"/documents/{rag_document_id}"),
            params={"owner_user_id": user_id},
            timeout=RAG_TIMEOUT_SECONDS,
        )
        if response.status_code != status.HTTP_404_NOT_FOUND:
            response.raise_for_status()
    except httpx.HTTPError as exc:
        log.error("document deletion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Belge şu anda silinemiyor. Birazdan tekrar deneyin.",
        ) from exc


def as_dict(record: ChatDocument) -> dict[str, Any]:
    return {
        "id": record.id,
        "filename": record.filename,
        "kind": record.kind,
        "size_bytes": record.size_bytes,
        "units": record.units,
        "char_count": record.char_count,
        "truncated": record.truncated,
        "created_at": record.created_at,
    }
