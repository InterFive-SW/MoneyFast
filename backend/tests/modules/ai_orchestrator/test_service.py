"""Conversation persistence.

Two properties matter more than the CRUD:

* an anonymous turn is never stored, because conversations are keyed on
  (user_id, thread_id) and a NULL user_id would pool every anonymous visitor
  into one shared conversation; and
* a persistence failure never costs the user their answer.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.ai_orchestrator import service


def make_db(existing_conversation=None, messages=None) -> MagicMock:
    db = MagicMock(spec=Session)
    query = db.query.return_value
    query.filter.return_value.first.return_value = existing_conversation
    query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        messages or []
    )
    return db


class TestAnonymousIsolation:
    def test_anonymous_turn_is_not_persisted(self):
        """Conversations are keyed on (user_id, thread_id). Storing a NULL
        user_id would put every anonymous visitor on the default thread into
        one conversation, each reading the others' messages back as history."""
        db = make_db()
        assert service.record_turn(db, None, "default", "merhaba", "selam") is None
        assert db.add.called is False

    def test_anonymous_history_is_empty_rather_than_shared(self):
        db = make_db()
        assert service.load_history(db, None, "default") == []
        assert db.query.called is False


class TestRecordTurn:
    def test_stores_both_sides_of_the_exchange(self):
        db = make_db()
        conversation_id = service.record_turn(
            db, "user-1", "t-1", "portföyüm?", "Portföyünüz...", meta={"target_agent": "PORTFOLIO_AGENT"}
        )
        assert conversation_id is not None
        # One conversation plus two messages.
        assert db.add.call_count == 3
        roles = [call.args[0].role for call in db.add.call_args_list if hasattr(call.args[0], "role")]
        assert roles == ["user", "assistant"]

    def test_meta_is_attached_to_the_assistant_message_only(self):
        db = make_db()
        service.record_turn(db, "user-1", "t-1", "soru", "cevap", meta={"compliance_verdict": "PASS"})
        added = [c.args[0] for c in db.add.call_args_list if hasattr(c.args[0], "role")]
        user_msg, assistant_msg = added
        assert user_msg.meta == {}
        assert assistant_msg.meta == {"compliance_verdict": "PASS"}

    def test_reuses_an_existing_conversation(self):
        existing = SimpleNamespace(id="conv-1", updated_at=None)
        db = make_db(existing_conversation=existing)
        assert service.record_turn(db, "user-1", "t-1", "ikinci soru", "cevap") == "conv-1"
        # Only the two messages; no second conversation row.
        assert db.add.call_count == 2
        assert existing.updated_at is not None

    def test_a_database_failure_does_not_cost_the_user_their_answer(self):
        """The expensive work is already done by the time this runs. Raising
        here would discard a completed turn over a failed log row."""
        db = make_db()
        db.commit.side_effect = RuntimeError("connection reset")
        assert service.record_turn(db, "user-1", "t-1", "soru", "cevap") is None
        assert db.rollback.called


class TestTitle:
    def test_title_is_the_first_message(self):
        db = make_db()
        service.record_turn(db, "user-1", "t-1", "THYAO ne durumda?", "cevap")
        conversation = db.add.call_args_list[0].args[0]
        assert conversation.title == "THYAO ne durumda?"

    def test_long_first_message_is_truncated_with_an_ellipsis(self):
        db = make_db()
        service.record_turn(db, "user-1", "t-1", "u" * 200, "cevap")
        conversation = db.add.call_args_list[0].args[0]
        assert len(conversation.title) == service.TITLE_MAX_CHARS
        assert conversation.title.endswith("…")


class TestLoadHistory:
    def test_returns_turns_oldest_first(self):
        """The query pulls newest-first to apply the limit, so the result has
        to be reversed — handing the model a backwards conversation would
        break coreference rather than help it."""
        rows = [
            SimpleNamespace(role="assistant", content="ikinci"),
            SimpleNamespace(role="user", content="birinci"),
        ]
        db = make_db(existing_conversation=SimpleNamespace(id="conv-1"), messages=rows)
        assert service.load_history(db, "user-1", "t-1") == [
            {"role": "user", "content": "birinci"},
            {"role": "assistant", "content": "ikinci"},
        ]

    def test_unknown_conversation_yields_no_history(self):
        db = make_db(existing_conversation=None)
        assert service.load_history(db, "user-1", "t-1") == []


class TestReadingHistoryBack:
    """The read path that was missing entirely.

    Turns were written from the first day and nothing ever returned them: the
    chat UI restored its sessions from `localStorage`, so the history lived in
    one browser rather than in the database. A teammate who loaded the seed
    data received 45 conversations and saw an empty sidebar.
    """

    def test_conversations_are_listed_newest_first(self):
        db = MagicMock(spec=Session)
        rows = [
            SimpleNamespace(thread_id="t-2", title="Yeni", updated_at="2026-08-26",
                            message_count=4),
            SimpleNamespace(thread_id="t-1", title="Eski", updated_at="2026-08-20",
                            message_count=2),
        ]
        chain = db.query.return_value.outerjoin.return_value.filter.return_value
        chain.group_by.return_value.order_by.return_value.all.return_value = rows

        result = service.list_conversations(db, "user-1")

        assert [r["thread_id"] for r in result] == ["t-2", "t-1"]
        assert result[0]["message_count"] == 4

    def test_messages_come_back_oldest_first_without_meta(self):
        """`meta` holds target_agent, primary_intent and compliance_verdict —
        an operational record of how the turn was handled. Returning it would
        put internal names on screen, the thing sanitize.py exists to stop."""
        conversation = SimpleNamespace(id="c-1")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = conversation
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            SimpleNamespace(id="m-1", role="user", content="merhaba",
                            created_at="2026-08-26T10:00", meta={"target_agent": "X"}),
        ]

        rows = service.conversation_messages(db, "user-1", "t-1")

        assert rows == [{"id": "m-1", "role": "user", "content": "merhaba",
                         "created_at": "2026-08-26T10:00"}]
        assert "meta" not in rows[0]

    def test_a_thread_that_is_not_yours_reads_as_absent(self):
        """The user_id filter is the access check. A thread id is guessable,
        so without it anyone could read anyone's conversation by asking."""
        db = make_db(existing_conversation=None)
        assert service.conversation_messages(db, "user-1", "someone-elses") is None


class TestDeletingAConversation:
    def test_deleting_removes_it(self):
        """The sidebar's delete button used to forget a browser copy. Now the
        list is served from the database, so a delete that did not reach it
        would undo itself on the next reload."""
        conversation = SimpleNamespace(id="c-1")
        db = make_db(existing_conversation=conversation)

        assert service.delete_conversation(db, "user-1", "t-1") is True
        db.delete.assert_called_once_with(conversation)
        db.commit.assert_called_once()

    def test_deleting_someone_elses_conversation_is_refused(self):
        db = make_db(existing_conversation=None)
        assert service.delete_conversation(db, "user-1", "t-1") is False
        db.delete.assert_not_called()
