"""Conversation persistence.

Implements the `ai.conversations` / `ai.messages` design from
`infra/intertech.sql`. Two deliberate departures from that sketch:

* `user_id` is nullable and carries no foreign key. The chat serves
  unauthenticated visitors for general questions, and a NOT NULL FK would
  make an anonymous turn unstorable — the alternative being a fake user row,
  which is worse. Ownership is enforced in the service layer.
* `thread_id` exists so the UI's multiple chat sessions map to separate
  conversations for the same user.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEMA = "ai"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("user_id", "thread_id", name="uq_conversations_user_thread"),
        Index("idx_conversations_user_updated", "user_id", "updated_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_conversation_created", "conversation_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: Turn record plus a small render envelope. The operational half (routed
    #: agent, intent, compliance verdict) is for debugging; `context_topic`
    #: and `disclosures` are read back when a conversation is reopened, so a
    #: historical bubble carries the notices it was first shown with. Being
    #: JSONB, adding either cost no migration.
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ChatDocument(Base):
    """Kullanıcının sohbete yüklediği bir dosyanın kaydı.

    Metnin KENDİSİ burada değil: o, gömülmüş hâliyle vektör veritabanında
    (`rag.documents`, sahibi bu kullanıcı). Burada duran, kullanıcının
    "Belgelerim" listesinde gördüğü ve sildiği şey.

    İki yerde tutulmasının sebebi listeleme ve silme: arayüz için vektör
    veritabanına sorgu atmak, uygulama verisini oraya taşımak olurdu ve
    `rag` servisi bilerek tek bir şey biliyor -- gömme ve arama.

    `rag_document_id` bir foreign key DEĞİL: ayrı bir veritabanındaki satıra
    işaret ediyor. Silme iki adım, ve sırası önemli (bkz. service.delete).
    """

    __tablename__ = "chat_documents"
    __table_args__ = (
        Index("idx_chat_documents_user_created", "user_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    #: Hangi sohbette yüklendiği. Belge kullanıcıya ait, sohbete değil --
    #: silinen bir sohbet, kullanıcının belgesini götürmemeli.
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    #: PDF / Excel / CSV / PowerPoint / Metin. Uzantı değil okunabilir ad:
    #: listede gösterilen şey bu.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    #: PDF'te sayfa, tabloda satır, sunumda slayt.
    units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Metin tavana takıldıysa doğru. Kırpıldığını söylememek, belgenin
    #: yarısını okuyup tamamını okumuş gibi cevap vermek olurdu.
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: `rag.documents.id`. Yükleme kısmen başarısız olduysa NULL olabilir.
    rag_document_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
