"""Conversation persistence and the context-window authority.

Persistence is best-effort by design: a database hiccup must not cost the user
their answer. The orchestrator has already done the expensive work by the time
these run, and returning a 500 because a log row failed to insert would throw
away a completed turn. Failures are logged and swallowed — but no longer
silently: the router turns a dropped record into a `persistence` status the
client shows the user, because with server-side history a turn that was not
stored is a turn the model will not remember next time.

This module is also where the context window is decided. It used to be decided
in three places at once -- the frontend sliced 6, `load_history` limited 6, and
the orchestrator's `_history_summary` sliced 6 again -- so nobody could say
what the model actually saw without reading all three. `trim_history` is now
the single authority, and both the stored and the client-supplied path go
through it.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from sqlalchemy.orm import Session

from .models import Conversation, Message

log = logging.getLogger("moneyfast.ai_orchestrator")

#: Conversation titles are shown in the session list, so the first user
#: message is truncated rather than sent to a model for summarising: one more
#: LLM call per new conversation is not worth a nicer label.
TITLE_MAX_CHARS = 60

#: How far back the assistant remembers, expressed the way a person reasons
#: about it. Was 3 (six messages), which meant a follow-up two questions later
#: had already fallen out of the window.
CONTEXT_MAX_EXCHANGES = 10

#: The database and the wire both count messages, so the exchange figure is
#: converted once, here, rather than at each call site.
CONTEXT_MAX_MESSAGES = CONTEXT_MAX_EXCHANGES * 2

#: Characters, not tokens. A character budget is deterministic, needs no
#: tokenizer in the test suite, and is the same number in the test as in the
#: code. Turkish runs roughly 2.5-3 characters per token on Groq's tokenizer,
#: so this is on the order of 2.5-3k tokens.
CONTEXT_MAX_CHARS = 7500

#: A single turn cannot monopolise the budget. A pasted balance sheet would
#: otherwise evict every other turn and leave the model with one message and
#: no conversation.
MESSAGE_MAX_CHARS = 2000

#: What happened to this turn's record, as far as the user is concerned.
#: `anonymous` and `session_expired` are deliberately distinct: the first is a
#: visitor who never had history to lose, the second is someone who did.
PersistenceStatus = Literal["saved", "anonymous", "session_expired", "failed"]


def _truncate(content: str) -> str:
    if len(content) <= MESSAGE_MAX_CHARS:
        return content
    return content[: MESSAGE_MAX_CHARS - 1].rstrip() + "…"


def _drop_leading_assistant(turns: list[dict[str, str]]) -> list[dict[str, str]]:
    """Make the window open on a user turn.

    An answer whose question has been trimmed away is worse than no context:
    it invites the model to infer what was asked. Normal alternation makes
    this a one-element skip, but a turn whose user row failed to insert can
    leave two assistant rows adjacent, so this consumes all of them.
    """
    index = 0
    while index < len(turns) and turns[index]["role"] == "assistant":
        index += 1
    return turns[index:]


def trim_history(turns: list[dict[str, str]]) -> list[dict[str, str]]:
    """Reduce a transcript to what the model should see.

    Applied to BOTH the stored history and the history an anonymous caller
    supplies. The client-supplied path was previously unbounded server-side:
    a caller could post five hundred turns and the orchestrator's own slice
    was the only thing between that and the router prompt.
    """
    if not turns:
        return []

    window = [
        {
            "role": str(turn.get("role", "user")),
            "content": _truncate(str(turn.get("content", ""))),
            #: Metin değil, veri. Bir turun kaynakları o turla birlikte
            #: taşınıyor: "bana kaynakça verir misin" sorusunun cevabı
            #: önceki turun kaynakları ve onlar burada düşerse o soru bir
            #: aramaya dönüşüp boş dönüyor.
            "sources": list(turn.get("sources") or []),
        }
        for turn in turns[-CONTEXT_MAX_MESSAGES:]
    ]
    window = _drop_leading_assistant(window)

    # Walk newest to oldest so the turns nearest the question are the ones
    # that survive a tight budget.
    kept: list[dict[str, str]] = []
    budget = CONTEXT_MAX_CHARS
    for turn in reversed(window):
        # Bütçe İSTEM uzunluğunu sınırlıyor ve kaynaklar isteme girmiyor --
        # `_history_summary` yalnızca `role` ve `content` okuyor. Onları
        # saymak, modele hiç gitmeyen baytlar yüzünden gerçek turları
        # düşürmek olurdu.
        cost = len(turn["role"]) + len(turn["content"]) + 2
        if kept and cost > budget:
            break
        budget -= cost
        kept.append(turn)
    kept.reverse()

    # The character walk can re-orphan: dropping an old user turn strands the
    # assistant reply that followed it.
    return _drop_leading_assistant(kept)


def persistence_status(
    user_id: Optional[str], token_present: bool, conversation_id: Optional[str]
) -> PersistenceStatus:
    """Classify what happened to the turn's record.

    Four outcomes, two of which the user needs to be told about. Collapsing
    them -- as `conversation_id is None` alone does -- cannot distinguish a
    visitor who was never signed in from someone whose session quietly
    expired mid-conversation, and those need different words.
    """
    if user_id is None:
        return "session_expired" if token_present else "anonymous"
    return "saved" if conversation_id else "failed"


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

        # Explicit, ordered timestamps. `load_history` sorts on
        # (created_at DESC, id DESC) and `id` is a random UUID, so two rows
        # written in the same microsecond are ordered by a coin flip -- which
        # can put the answer before the question it answers. A millisecond of
        # separation makes the ordering total without adding a sequence
        # column, i.e. without a migration.
        now = datetime.now(timezone.utc)
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=user_message,
                meta={},
                created_at=now,
            )
        )
        db.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message,
                meta=meta or {},
                created_at=now + timedelta(milliseconds=1),
            )
        )
        # Bumps the session list ordering.
        conversation.updated_at = now
        db.commit()
        return conversation.id
    except Exception as exc:
        # Never fatal. The turn already happened; losing its record is a
        # smaller harm than telling the user their answer failed. The caller
        # reports it as `persistence="failed"` so it is not silent.
        log.warning("could not persist conversation turn: %s", exc)
        db.rollback()
        return None


def load_history(
    db: Session,
    user_id: Optional[str],
    thread_id: str,
    limit: int = CONTEXT_MAX_MESSAGES,
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
    # `sources` trim_history'nin dokunmadığı bir alan: kırpma metin
    # uzunluğuyla ilgili ve kaynak listesi metin değil. Turun kendisi
    # kırpılırsa kaynakları da onunla birlikte gider, ki doğru olan bu.
    turns = [
        {"role": row.role, "content": row.content,
         "sources": (row.meta or {}).get("sources") or []}
        for row in reversed(rows)
    ]
    return trim_history(turns)


# ---------------------------------------------------------------------------
# Reading conversations back
#
# These are the counterpart to record_turn, and they differ from it in one
# important way: they do NOT swallow. record_turn is best-effort because the
# answer already happened and losing its log row is the smaller harm. A read
# that swallows returns an empty list, and an empty list rendered into the
# session list reads to the user as "my history was deleted".
#
# Every query is scoped by user_id in the WHERE clause rather than fetched and
# then checked, so a thread_id guessed from another account resolves to
# nothing at all.
# ---------------------------------------------------------------------------
def list_conversations(
    db: Session, user_id: str, limit: int, offset: int
) -> tuple[list[Conversation], int]:
    query = db.query(Conversation).filter(Conversation.user_id == user_id)
    total = query.count()
    rows = (
        query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return rows, total


def get_conversation(
    db: Session, user_id: str, thread_id: str
) -> Optional[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.thread_id == thread_id)
        .first()
    )


def list_messages(
    db: Session, conversation_id: str, limit: int
) -> tuple[list[Message], bool]:
    """The newest `limit` messages, returned oldest-first.

    No offset paging: the chat opens at the bottom, so "the most recent N"
    is the primitive the UI actually needs. One extra row is fetched to
    answer `has_more` without a second COUNT.
    """
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    return list(reversed(rows[:limit])), has_more


def rename_conversation(
    db: Session, user_id: str, thread_id: str, title: str
) -> Optional[Conversation]:
    conversation = get_conversation(db, user_id, thread_id)
    if conversation is None:
        return None
    conversation.title = title
    db.commit()
    return conversation


def delete_conversation(db: Session, user_id: str, thread_id: str) -> bool:
    """Hard delete; `ai.messages.conversation_id` cascades.

    Not a soft delete on purpose. A `deleted_at` column would mean
    `load_history` has to filter it on every read forever, and the one time
    someone forgets, a deleted conversation comes back as model context —
    the worst possible outcome for a button labelled "sil".
    """
    conversation = get_conversation(db, user_id, thread_id)
    if conversation is None:
        return False
    db.delete(conversation)
    db.commit()
    return True
