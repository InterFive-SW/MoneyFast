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

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
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
