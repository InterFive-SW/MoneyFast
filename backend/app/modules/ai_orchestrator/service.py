"""Conversation persistence helpers.

Persistence is best-effort by design: a database hiccup must not cost the user
their answer. The orchestrator has already done the expensive work by the time
these run, and returning a 500 because a log row failed to insert would throw
away a completed turn. Failures are logged and swallowed.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Conversation, Message

log = logging.getLogger("moneyfast.ai_orchestrator")

#: Conversation titles are shown in the session list, so the first user
#: message is truncated rather than sent to a model for summarising: one more
#: LLM call per new conversation is not worth a nicer label.
TITLE_MAX_CHARS = 60


def get_or_create_conversation(
    db: Session, user_id: str, thread_id: str, first_message: str
) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.thread_id == thread_id)
        .first()
    )
    if conversation is not None:
        return conversation

    title = first_message.strip()
    if len(title) > TITLE_MAX_CHARS:
        title = title[: TITLE_MAX_CHARS - 1].rstrip() + "…"

    # The id is generated here rather than left to the column default, which
    # SQLAlchemy only applies at flush time. The caller returns this id to the
    # client, so it has to exist the moment the object does.
    conversation = Conversation(
        id=str(uuid.uuid4()), user_id=user_id, thread_id=thread_id, title=title
    )
    db.add(conversation)
    db.flush()
    return conversation


def record_turn(
    db: Session,
    user_id: Optional[str],
    thread_id: str,
    user_message: str,
    assistant_message: str,
    meta: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Persist one exchange. Returns the conversation id, or None if not stored.

    Anonymous turns are NOT persisted. Conversations are keyed on
    (user_id, thread_id), so a NULL user_id would put every anonymous visitor
    who ever used the default thread into one shared conversation — each of
    them reading the others' messages back as their own history. Dropping the
    record is the only safe option until an anonymous session carries its own
    identifier.
    """
    if not user_id:
        return None
    try:
        conversation = get_or_create_conversation(db, user_id, thread_id, user_message)
        db.add(Message(conversation_id=conversation.id, role="user", content=user_message, meta={}))
        db.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message,
                meta=meta or {},
            )
        )
        # Bumps the session list ordering.
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        return conversation.id
    except Exception as exc:
        # Never fatal. The turn already happened; losing its record is a
        # smaller harm than telling the user their answer failed.
        log.warning("could not persist conversation turn: %s", exc)
        db.rollback()
        return None


def list_conversations(db: Session, user_id: str) -> list[dict[str, Any]]:
    """Every stored conversation for one user, newest activity first.

    Turns were being written here from the first day and nothing ever read
    them back: the chat UI restored its sessions from `localStorage`, so the
    history lived in one browser rather than in the database. A teammate who
    loaded the seed data got the rows and an empty sidebar.

    Ordered by `updated_at` to match `idx_conversations_user_updated`, and
    filtered on `user_id` because that is the only thing separating one
    person's threads from another's.
    """
    rows = (
        db.query(
            Conversation.thread_id,
            Conversation.title,
            Conversation.updated_at,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .filter(Conversation.user_id == user_id)
        .group_by(Conversation.id, Conversation.thread_id, Conversation.title,
                  Conversation.updated_at)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return [
        {
            "thread_id": row.thread_id,
            "title": row.title,
            "updated_at": row.updated_at,
            "message_count": row.message_count,
        }
        for row in rows
    ]


def conversation_messages(
    db: Session, user_id: str, thread_id: str
) -> Optional[list[dict[str, Any]]]:
    """One thread's turns, oldest first. None when the thread is not theirs.

    The `user_id` filter is the access check: a thread id is guessable, and
    without it anyone could read anyone's conversation by asking for it.
    None rather than [] so the router can answer 404 -- "you have no such
    conversation" and "that conversation is empty" are different answers.

    `meta` is deliberately not returned. It carries `target_agent`,
    `primary_intent` and `compliance_verdict`: an operational record of how
    the turn was handled, never anything the reader should see.
    """
    conversation = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.thread_id == thread_id)
        .first()
    )
    if conversation is None:
        return None

    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    return [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def delete_conversation(db: Session, user_id: str, thread_id: str) -> bool:
    """Remove one of the caller's conversations. False when it is not theirs.

    Exists because the sidebar has always had a delete button. While the
    session list came from `localStorage` that button only had to forget a
    browser copy; now that the list is served from here, a delete that did not
    reach the database would undo itself on the next reload.

    Messages go with it through `ondelete="CASCADE"` on
    `messages.conversation_id`.
    """
    conversation = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.thread_id == thread_id)
        .first()
    )
    if conversation is None:
        return False
    db.delete(conversation)
    db.commit()
    return True


def load_history(
    db: Session, user_id: Optional[str], thread_id: str, limit: int = 6
) -> list[dict[str, str]]:
    """Recent turns for coreference resolution.

    Read server-side rather than trusting the client's copy: history decides
    which instrument a follow-up like "peki ya o?" resolves to, so a client
    able to rewrite it could steer a tool call at a different holding.

    Returns [] for anonymous callers, who have nothing stored; the router
    falls back to the history they supplied, which can only mislead them
    about their own conversation.
    """
    if not user_id:
        return []

    conversation = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.thread_id == thread_id)
        .first()
    )
    if conversation is None:
        return []

    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in reversed(rows)]
