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


class TestTrimHistory:
    """The context window, in one place.

    It used to be decided in three: the frontend sliced 6, load_history
    limited 6, and the orchestrator sliced 6 again. Nobody could say what the
    model actually saw without reading all three files.
    """

    def test_empty_history_stays_empty(self):
        assert service.trim_history([]) == []

    def test_a_short_conversation_passes_through_unchanged(self):
        turns = [
            {"role": "user", "content": "merhaba"},
            {"role": "assistant", "content": "selam"},
        ]
        assert service.trim_history(turns) == turns

    def test_only_the_newest_messages_survive_the_message_cap(self):
        turns = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"tur {i}"}
            for i in range(service.CONTEXT_MAX_MESSAGES + 10)
        ]
        trimmed = service.trim_history(turns)
        assert len(trimmed) == service.CONTEXT_MAX_MESSAGES
        assert trimmed[-1] == turns[-1]
        assert turns[0] not in trimmed

    def test_an_oversized_message_is_truncated_not_dropped(self):
        trimmed = service.trim_history([{"role": "user", "content": "u" * 9000}])
        assert len(trimmed) == 1
        assert len(trimmed[0]["content"]) == service.MESSAGE_MAX_CHARS
        assert trimmed[0]["content"].endswith("…")

    def test_the_newest_message_survives_however_large_it_is(self):
        """Returning nothing would hand the router a prompt with no question
        in it, which is worse than handing it one long one."""
        trimmed = service.trim_history(
            [{"role": "user", "content": "x" * service.CONTEXT_MAX_CHARS * 3}]
        )
        assert len(trimmed) == 1

    def test_the_character_budget_evicts_the_oldest_turns(self):
        turns = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": "y" * 2000}
            for i in range(6)
        ]
        trimmed = service.trim_history(turns)
        total = sum(len(t["role"]) + len(t["content"]) + 2 for t in trimmed)
        assert total <= service.CONTEXT_MAX_CHARS
        assert len(trimmed) < len(turns)
        assert trimmed[-1]["content"] == turns[-1]["content"]

    def test_a_window_opening_on_an_answer_drops_it(self):
        """An answer whose question was trimmed away invites the model to
        infer what was asked."""
        trimmed = service.trim_history(
            [
                {"role": "assistant", "content": "önceki cevap"},
                {"role": "user", "content": "soru"},
                {"role": "assistant", "content": "cevap"},
            ]
        )
        assert [t["role"] for t in trimmed] == ["user", "assistant"]

    def test_an_orphan_created_by_the_character_walk_is_also_dropped(self):
        """The budget walk can strand an answer that the message cap did not:
        dropping an old user turn leaves the reply that followed it leading."""
        turns = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": "z" * 2000}
            for i in range(6)
        ]
        trimmed = service.trim_history(turns)
        assert trimmed[0]["role"] == "user"

    def test_consecutive_leading_answers_are_all_dropped(self):
        """Normal alternation makes this a one-element skip; a turn whose user
        row failed to insert leaves two assistant rows adjacent."""
        trimmed = service.trim_history(
            [
                {"role": "assistant", "content": "bir"},
                {"role": "assistant", "content": "iki"},
                {"role": "user", "content": "soru"},
            ]
        )
        assert trimmed == [{"role": "user", "content": "soru"}]

    def test_a_history_of_answers_only_yields_nothing(self):
        assert service.trim_history([{"role": "assistant", "content": "cevap"}]) == []

    def test_missing_keys_default_rather_than_raise(self):
        assert service.trim_history([{}]) == [{"role": "user", "content": ""}]


class TestPersistenceStatus:
    """Four outcomes, two of which the user needs different words for."""

    def test_no_token_is_anonymous(self):
        assert service.persistence_status(None, False, None) == "anonymous"

    def test_a_token_that_did_not_resolve_is_an_expired_session(self):
        """Collapsing this into "anonymous" is what made the session drop
        silent: the user kept chatting and nothing was being stored."""
        assert service.persistence_status(None, True, None) == "session_expired"

    def test_a_stored_turn_is_saved(self):
        assert service.persistence_status("user-1", True, "conv-1") == "saved"

    def test_a_signed_in_turn_with_no_row_is_a_failure(self):
        """record_turn swallows database errors so the answer survives. With
        server-side history that means the model will not see this turn next
        time, which the user is owed an explanation for."""
        assert service.persistence_status("user-1", True, None) == "failed"


class TestMessageOrdering:
    def test_the_answer_is_timestamped_after_the_question(self):
        """load_history sorts on (created_at DESC, id DESC) and `id` is a
        random UUID, so two rows written in the same microsecond order by a
        coin flip — which can put the answer before the question."""
        db = make_db()
        service.record_turn(db, "user-1", "t-1", "soru", "cevap")
        user_msg, assistant_msg = [
            c.args[0] for c in db.add.call_args_list if hasattr(c.args[0], "role")
        ]
        assert assistant_msg.created_at > user_msg.created_at


class TestLoadHistoryWindow:
    def test_the_query_limit_is_the_context_window(self):
        db = make_db(existing_conversation=SimpleNamespace(id="conv-1"), messages=[])
        service.load_history(db, "user-1", "t-1")
        limit = db.query.return_value.filter.return_value.order_by.return_value.limit
        limit.assert_called_once_with(service.CONTEXT_MAX_MESSAGES)

    def test_stored_history_is_trimmed_like_any_other(self):
        rows = [
            SimpleNamespace(role="assistant", content="a" * 9000),
            SimpleNamespace(role="user", content="soru"),
        ]
        db = make_db(existing_conversation=SimpleNamespace(id="conv-1"), messages=rows)
        trimmed = service.load_history(db, "user-1", "t-1")
        assert len(trimmed[-1]["content"]) == service.MESSAGE_MAX_CHARS


def make_listing_db(rows=None, total=0):
    """A Session double for the list/paginate chain."""
    db = MagicMock(spec=Session)
    scoped = db.query.return_value.filter.return_value
    scoped.count.return_value = total
    scoped.order_by.return_value.limit.return_value.offset.return_value.all.return_value = (
        rows or []
    )
    return db


def make_message_db(rows=None):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        rows or []
    )
    return db


class TestListConversations:
    def test_returns_the_page_and_the_total(self):
        rows = [SimpleNamespace(id="conv-1")]
        db = make_listing_db(rows=rows, total=12)
        assert service.list_conversations(db, "user-1", 20, 0) == (rows, 12)

    def test_the_page_window_reaches_the_query(self):
        db = make_listing_db()
        service.list_conversations(db, "user-1", 5, 10)
        ordered = db.query.return_value.filter.return_value.order_by.return_value
        ordered.limit.assert_called_once_with(5)
        ordered.limit.return_value.offset.assert_called_once_with(10)


class TestGetConversation:
    def test_returns_the_row_when_the_user_owns_it(self):
        existing = SimpleNamespace(id="conv-1")
        db = make_db(existing_conversation=existing)
        assert service.get_conversation(db, "user-1", "t-1") is existing

    def test_returns_none_for_a_thread_the_user_does_not_own(self):
        """Scoped in the WHERE clause, so someone else's thread resolves to
        nothing rather than to a row that then needs an ownership check."""
        db = make_db(existing_conversation=None)
        assert service.get_conversation(db, "user-1", "t-1") is None


class TestListMessages:
    def test_returns_messages_oldest_first(self):
        rows = [
            SimpleNamespace(id="m2", role="assistant"),
            SimpleNamespace(id="m1", role="user"),
        ]
        db = make_message_db(rows)
        messages, has_more = service.list_messages(db, "conv-1", 10)
        assert [m.id for m in messages] == ["m1", "m2"]
        assert has_more is False

    def test_one_extra_row_answers_has_more_without_a_second_count(self):
        rows = [SimpleNamespace(id=f"m{i}") for i in range(3)]
        db = make_message_db(rows)
        messages, has_more = service.list_messages(db, "conv-1", 2)
        assert len(messages) == 2
        assert has_more is True
        limit = db.query.return_value.filter.return_value.order_by.return_value.limit
        limit.assert_called_once_with(3)


class TestRenameConversation:
    def test_sets_the_title_and_commits(self):
        existing = SimpleNamespace(id="conv-1", title="eski")
        db = make_db(existing_conversation=existing)
        result = service.rename_conversation(db, "user-1", "t-1", "yeni başlık")
        assert result is existing
        assert existing.title == "yeni başlık"
        assert db.commit.called

    def test_an_unknown_thread_changes_nothing(self):
        db = make_db(existing_conversation=None)
        assert service.rename_conversation(db, "user-1", "t-1", "yeni") is None
        assert db.commit.called is False


class TestDeleteConversation:
    def test_deletes_the_row_and_reports_success(self):
        """Hard delete; ai.messages cascades. A soft delete would mean
        load_history filters a status forever, and the one time someone
        forgets, a deleted conversation returns as model context."""
        existing = SimpleNamespace(id="conv-1")
        db = make_db(existing_conversation=existing)
        assert service.delete_conversation(db, "user-1", "t-1") is True
        db.delete.assert_called_once_with(existing)
        assert db.commit.called

    def test_an_unknown_thread_reports_failure_without_deleting(self):
        db = make_db(existing_conversation=None)
        assert service.delete_conversation(db, "user-1", "t-1") is False
        assert db.delete.called is False
