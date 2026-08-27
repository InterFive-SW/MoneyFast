"""The conversations REST surface.

Rows have been written to `ai.conversations` since the schema landed, but
nothing could read them back, so the session list came entirely from
localStorage: history died with the browser profile and the next person to use
the machine could read it. These endpoints are what make the database the
source of truth instead.

Two properties are load-bearing and both are asserted here rather than assumed:
every query is scoped by the authenticated user (a thread_id from another
account must 404, not leak), and an anonymous caller gets 401 rather than an
empty list, because "no conversations" and "your session expired" must not
look the same.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.deps import get_current_user_id
from app.main import app
from app.modules.ai_orchestrator import service

NOW = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)


@contextlib.contextmanager
def as_user(user_id="user-1"):
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)


def make_conversation(thread_id="t-1", title="THYAO ne durumda?"):
    return SimpleNamespace(
        id="conv-1",
        thread_id=thread_id,
        title=title,
        created_at=NOW,
        updated_at=NOW,
    )


def make_message(role, content, meta=None, offset=0):
    return SimpleNamespace(
        id=f"msg-{role}-{offset}",
        role=role,
        content=content,
        meta=meta or {},
        created_at=NOW + timedelta(seconds=offset),
    )


# --------------------------------------------------------------------------
# GET /conversations
# --------------------------------------------------------------------------
def test_list_returns_the_users_conversations_with_a_total(client, mocker):
    mocker.patch.object(
        service, "list_conversations", return_value=([make_conversation()], 7)
    )
    with as_user():
        body = client.get("/api/ai_orchestrator/conversations").json()
    assert body["total"] == 7
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["items"][0]["thread_id"] == "t-1"
    assert body["items"][0]["title"] == "THYAO ne durumda?"


def test_list_is_scoped_to_the_authenticated_user(client, mocker):
    """The user id comes from the token and reaches the WHERE clause. Fetching
    first and checking ownership afterwards is the shape that leaks."""
    listing = mocker.patch.object(service, "list_conversations", return_value=([], 0))
    with as_user("user-42"):
        client.get("/api/ai_orchestrator/conversations?limit=5&offset=10")
    args = listing.call_args.args
    assert args[1] == "user-42"
    assert args[2] == 5
    assert args[3] == 10


def test_list_with_no_conversations_is_an_empty_page(client, mocker):
    mocker.patch.object(service, "list_conversations", return_value=([], 0))
    with as_user():
        body = client.get("/api/ai_orchestrator/conversations").json()
    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_requires_authentication(client):
    """An empty list would make an expired session indistinguishable from a
    brand new account — the silent degradation this work exists to end."""
    assert client.get("/api/ai_orchestrator/conversations").status_code == 401


def test_list_rejects_an_out_of_range_limit(client):
    with as_user():
        assert (
            client.get("/api/ai_orchestrator/conversations?limit=0").status_code == 422
        )
        assert (
            client.get("/api/ai_orchestrator/conversations?limit=101").status_code
            == 422
        )


def test_list_rejects_a_negative_offset(client):
    with as_user():
        assert (
            client.get("/api/ai_orchestrator/conversations?offset=-1").status_code
            == 422
        )


# --------------------------------------------------------------------------
# GET /conversations/{thread_id}
# --------------------------------------------------------------------------
def test_detail_returns_the_transcript_oldest_first(client, mocker):
    rows = [
        make_message("user", "soru", offset=0),
        make_message("assistant", "cevap", offset=1),
    ]
    mocker.patch.object(service, "get_conversation", return_value=make_conversation())
    mocker.patch.object(service, "list_messages", return_value=(rows, False))
    with as_user():
        body = client.get("/api/ai_orchestrator/conversations/t-1").json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["has_more"] is False
    assert body["thread_id"] == "t-1"


def test_detail_reads_disclosures_back_from_the_message_meta(client, mocker):
    """A reopened bubble keeps the notices it was first shown with. They live
    in JSONB, which is why this needed no migration."""
    rows = [
        make_message("user", "soru", offset=0),
        make_message(
            "assistant",
            "cevap",
            meta={"disclosures": ["Yatırım tavsiyesi değildir."]},
            offset=1,
        ),
    ]
    mocker.patch.object(service, "get_conversation", return_value=make_conversation())
    mocker.patch.object(service, "list_messages", return_value=(rows, False))
    with as_user():
        body = client.get("/api/ai_orchestrator/conversations/t-1").json()
    assert body["messages"][0]["disclosures"] == []
    assert body["messages"][1]["disclosures"] == ["Yatırım tavsiyesi değildir."]


def test_detail_surfaces_the_latest_context_topic(client, mocker):
    """The context panel follows the newest assistant turn that had a subject,
    so switching topics and back does not blank the panel."""
    rows = [
        make_message("assistant", "a", meta={"context_topic": "THYAO"}, offset=0),
        make_message("assistant", "b", meta={"context_topic": "ASELS"}, offset=1),
        make_message("assistant", "c", offset=2),
    ]
    mocker.patch.object(service, "get_conversation", return_value=make_conversation())
    mocker.patch.object(service, "list_messages", return_value=(rows, False))
    with as_user():
        body = client.get("/api/ai_orchestrator/conversations/t-1").json()
    assert body["context_topic"] == "ASELS"


def test_detail_context_topic_is_null_when_no_turn_had_one(client, mocker):
    mocker.patch.object(service, "get_conversation", return_value=make_conversation())
    mocker.patch.object(
        service, "list_messages", return_value=([make_message("user", "soru")], False)
    )
    with as_user():
        body = client.get("/api/ai_orchestrator/conversations/t-1").json()
    assert body["context_topic"] is None


def test_detail_reports_that_older_messages_exist(client, mocker):
    mocker.patch.object(service, "get_conversation", return_value=make_conversation())
    mocker.patch.object(
        service, "list_messages", return_value=([make_message("user", "soru")], True)
    )
    with as_user():
        body = client.get("/api/ai_orchestrator/conversations/t-1").json()
    assert body["has_more"] is True


def test_detail_passes_the_requested_window_through(client, mocker):
    mocker.patch.object(service, "get_conversation", return_value=make_conversation())
    listing = mocker.patch.object(service, "list_messages", return_value=([], False))
    with as_user():
        client.get("/api/ai_orchestrator/conversations/t-1?limit=50")
    assert listing.call_args.args[2] == 50


def test_detail_rejects_an_out_of_range_limit(client):
    with as_user():
        assert (
            client.get("/api/ai_orchestrator/conversations/t-1?limit=501").status_code
            == 422
        )


def test_a_thread_belonging_to_someone_else_is_not_found(client, mocker):
    """Queries are scoped by user_id, so a guessed thread_id resolves to
    nothing — 404, not 403, because the caller should not learn it exists."""
    mocker.patch.object(service, "get_conversation", return_value=None)
    with as_user("user-42"):
        assert client.get("/api/ai_orchestrator/conversations/t-1").status_code == 404


def test_detail_requires_authentication(client):
    assert client.get("/api/ai_orchestrator/conversations/t-1").status_code == 401


# --------------------------------------------------------------------------
# PATCH /conversations/{thread_id}
# --------------------------------------------------------------------------
def test_rename_updates_the_title(client, mocker):
    renamed = make_conversation(title="THYAO araştırması")
    rename = mocker.patch.object(service, "rename_conversation", return_value=renamed)
    with as_user():
        body = client.patch(
            "/api/ai_orchestrator/conversations/t-1",
            json={"title": "THYAO araştırması"},
        ).json()
    assert body["title"] == "THYAO araştırması"
    assert rename.call_args.args[1:] == ("user-1", "t-1", "THYAO araştırması")


def test_rename_of_an_unknown_thread_is_not_found(client, mocker):
    mocker.patch.object(service, "rename_conversation", return_value=None)
    with as_user():
        response = client.patch(
            "/api/ai_orchestrator/conversations/t-1", json={"title": "yeni"}
        )
    assert response.status_code == 404


def test_rename_rejects_an_empty_title(client):
    with as_user():
        response = client.patch(
            "/api/ai_orchestrator/conversations/t-1", json={"title": ""}
        )
    assert response.status_code == 422


def test_rename_requires_authentication(client):
    response = client.patch(
        "/api/ai_orchestrator/conversations/t-1", json={"title": "yeni"}
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------
# DELETE /conversations/{thread_id}
# --------------------------------------------------------------------------
def test_delete_returns_a_body_rather_than_204(client, mocker):
    """The frontend's request() calls response.json() unconditionally, so an
    empty 204 would throw in the client instead of resolving."""
    mocker.patch.object(service, "delete_conversation", return_value=True)
    with as_user():
        response = client.delete("/api/ai_orchestrator/conversations/t-1")
    assert response.status_code == 200
    assert response.json() == {"thread_id": "t-1", "status": "deleted"}


def test_delete_of_an_unknown_thread_is_not_found(client, mocker):
    mocker.patch.object(service, "delete_conversation", return_value=False)
    with as_user():
        assert (
            client.delete("/api/ai_orchestrator/conversations/t-1").status_code == 404
        )


def test_delete_requires_authentication(client):
    assert client.delete("/api/ai_orchestrator/conversations/t-1").status_code == 401
