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
