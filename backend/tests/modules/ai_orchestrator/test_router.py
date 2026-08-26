"""Unit tests for app/modules/ai_orchestrator/router.py.

Bu, backend'deki TEK dış HTTP çağrısı (`httpx.AsyncClient` ile
AI-Services/moneyfast-orchestrator'a giden istek). `block_network`
(conftest.py, autouse) gerçek bir soket açılmasını engelliyor; bu dosyada
`httpx.AsyncClient`'ın kendisini mock'layarak dört senaryoyu test ediyoruz:
başarı, bağlantı reddi, zaman aşımı, orchestrator'ın hata durumu döndürmesi.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx

CHAT_PAYLOAD = {"user_message": "Portföyümü değerlendirir misin?"}


def _install_async_client(
    mocker, *, post_result=None, post_exception=None, get_result=None, get_exception=None
):
    """`async with httpx.AsyncClient(...) as client:` bloğunu tamamen mock'lar.

    `AsyncMock` yerine dunder'ları (__aenter__/__aexit__) elle AsyncMock
    olarak atıyoruz — bare `AsyncMock()` üzerinde çocuk attribute'lar
    otomatik olarak async olmayabiliyor, bu yüzden açık ve garantili yol bu.
    """
    client_instance = MagicMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)

    post_mock = AsyncMock()
    if post_exception is not None:
        post_mock.side_effect = post_exception
    elif post_result is not None:
        post_mock.return_value = post_result
    client_instance.post = post_mock

    get_mock = AsyncMock()
    if get_exception is not None:
        get_mock.side_effect = get_exception
    elif get_result is not None:
        get_mock.return_value = get_result
    client_instance.get = get_mock

    mocker.patch("httpx.AsyncClient", return_value=client_instance)
    return client_instance


def _fake_response(json_body, raise_error=None):
    response = MagicMock()
    response.json.return_value = json_body
    response.raise_for_status.side_effect = raise_error
    return response


# --------------------------------------------------------------------------
# POST /chat
# --------------------------------------------------------------------------
def test_chat_happy_path_forwards_orchestrator_response(client, mocker):
    orchestrator_body = {
        "final_output": "Portföyünüz dengeli görünüyor.",
        "primary_intent": "portfolio_review",
        "target_agent": "portfolio",
        "compliance_verdict": "approved",
    }
    _install_async_client(mocker, post_result=_fake_response(orchestrator_body))

    response = client.post("/api/ai_orchestrator/chat", json=CHAT_PAYLOAD)

    assert response.status_code == 200
    # The response model gained widget/context_topic/conversation_id, so a
    # whole-body equality check would now assert the absence of features
    # rather than the forwarding behaviour under test.
    assert response.json() | orchestrator_body == response.json()
    assert response.json()["widget"] is None


def test_chat_returns_503_when_orchestrator_connection_refused(client, mocker):
    _install_async_client(mocker, post_exception=httpx.ConnectError("refused"))

    response = client.post("/api/ai_orchestrator/chat", json=CHAT_PAYLOAD)

    assert response.status_code == 503
    assert "unreachable" in response.json()["detail"]


def test_chat_returns_504_when_orchestrator_times_out(client, mocker):
    """A timeout is not an outage. 503 sent the user looking for a service
    that is up and simply slow -- usually a Groq 429 whose retry-after
    exceeded our budget."""
    _install_async_client(mocker, post_exception=httpx.TimeoutException("timed out"))

    response = client.post("/api/ai_orchestrator/chat", json=CHAT_PAYLOAD)

    assert response.status_code == 504
    assert "yoğunluk" in response.json()["detail"]


def test_chat_returns_502_when_orchestrator_returns_error_status(client, mocker):
    error_response = MagicMock(status_code=500)
    error = httpx.HTTPStatusError("boom", request=MagicMock(), response=error_response)
    _install_async_client(mocker, post_result=_fake_response({}, raise_error=error))

    response = client.post("/api/ai_orchestrator/chat", json=CHAT_PAYLOAD)

    assert response.status_code == 502
    assert "500" in response.json()["detail"]


def test_chat_missing_user_message_returns_422(client):
    response = client.post("/api/ai_orchestrator/chat", json={})

    assert response.status_code == 422


# --------------------------------------------------------------------------
# GET /health
# --------------------------------------------------------------------------
def test_orchestrator_health_happy_path_passes_through_readyz_body(client, mocker):
    _install_async_client(mocker, get_result=_fake_response({"status": "ready"}))

    response = client.get("/api/ai_orchestrator/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "orchestrator": {"status": "ready"}}


def test_orchestrator_health_returns_503_when_unreachable(client, mocker):
    _install_async_client(mocker, get_exception=httpx.ConnectError("refused"))

    response = client.get("/api/ai_orchestrator/health")

    assert response.status_code == 503


def test_orchestrator_health_returns_503_on_timeout(client, mocker):
    _install_async_client(mocker, get_exception=httpx.TimeoutException("timed out"))

    response = client.get("/api/ai_orchestrator/health")

    assert response.status_code == 503


# --------------------------------------------------------------------------
# POST /chat/stream
#
# The streaming variant exists so the client can show what the graph is
# ACTUALLY doing. The captions it replaces were a hardcoded 800ms loop that
# announced "Risk modeli güncelleniyor..." for any question at all.
#
# The answer itself is not streamed token by token: the compliance gate is
# fail-closed, and text already painted on screen cannot be un-shown.
# --------------------------------------------------------------------------
def _install_stream(mocker, lines, raise_error=None):
    """Mock `async with client.stream(...) as upstream:` yielding `lines`."""
    upstream = MagicMock()
    upstream.raise_for_status.side_effect = raise_error

    async def _aiter_lines():
        for line in lines:
            yield line

    upstream.aiter_lines = _aiter_lines

    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=upstream)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)

    client_instance = MagicMock()
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=False)
    client_instance.stream = MagicMock(return_value=stream_ctx)

    mocker.patch("httpx.AsyncClient", return_value=client_instance)
    return client_instance


DONE_LINE = 'data: {"final_output": "Merhaba", "primary_intent": "SMALLTALK"}'


def test_stream_relays_stage_events_and_the_answer(client, mocker):
    _install_stream(
        mocker,
        ['event: stage', 'data: {"stage": "Yanıt yazılıyor..."}', '', 'event: done', DONE_LINE, ''],
    )
    response = client.post(
        "/api/ai_orchestrator/chat/stream",
        json={"user_message": "selam", "thread_id": "t1", "conversation_history": []},
    )
    assert response.status_code == 200
    assert "Yanıt yazılıyor" in response.text
    assert "Merhaba" in response.text


def test_stream_records_the_turn_once_the_answer_arrives(client, mocker):
    """The buffered endpoint persists the turn; the streaming one must too, or
    a streamed conversation would vanish from history."""
    from app.modules.ai_orchestrator import service

    recorded = mocker.patch.object(service, "record_turn", return_value="conv-1")
    mocker.patch.object(service, "load_history", return_value=[])
    _install_stream(mocker, ['event: done', DONE_LINE, ''])

    response = client.post(
        "/api/ai_orchestrator/chat/stream",
        json={"user_message": "selam", "thread_id": "t1", "conversation_history": []},
    )

    assert recorded.call_count == 1
    assert recorded.call_args.kwargs["assistant_message"] == "Merhaba"
    assert "conv-1" in response.text


def test_stream_reports_an_upstream_failure_in_band(client, mocker):
    """The response is already 200 by the time the graph fails, so the error
    cannot be an HTTP status. The client falls back to the buffered path."""
    _install_stream(mocker, [], raise_error=httpx.ConnectError("refused"))
    response = client.post(
        "/api/ai_orchestrator/chat/stream",
        json={"user_message": "selam", "thread_id": "t1", "conversation_history": []},
    )
    assert response.status_code == 200
    assert "event: error" in response.text


def test_stream_ignores_a_malformed_frame(client, mocker):
    from app.modules.ai_orchestrator import service

    recorded = mocker.patch.object(service, "record_turn", return_value="conv-2")
    mocker.patch.object(service, "load_history", return_value=[])
    _install_stream(mocker, ['data: not-json', '', 'event: done', DONE_LINE, ''])

    response = client.post(
        "/api/ai_orchestrator/chat/stream",
        json={"user_message": "selam", "thread_id": "t1", "conversation_history": []},
    )

    assert response.status_code == 200
    assert recorded.call_count == 1


def test_stream_without_an_answer_records_nothing(client, mocker):
    """A turn that died mid-graph must not be persisted as an empty reply."""
    from app.modules.ai_orchestrator import service

    recorded = mocker.patch.object(service, "record_turn", return_value="conv-3")
    mocker.patch.object(service, "load_history", return_value=[])
    _install_stream(mocker, ['event: stage', 'data: {"stage": "..."}', ''])

    client.post(
        "/api/ai_orchestrator/chat/stream",
        json={"user_message": "selam", "thread_id": "t1", "conversation_history": []},
    )

    assert recorded.call_count == 0


def test_stream_falls_back_to_the_client_history_when_nothing_is_stored(client, mocker):
    from app.modules.ai_orchestrator import service

    mocker.patch.object(service, "record_turn", return_value="conv-4")
    mocker.patch.object(service, "load_history", return_value=[])
    instance = _install_stream(mocker, ['event: done', DONE_LINE, ''])

    client.post(
        "/api/ai_orchestrator/chat/stream",
        json={
            "user_message": "peki ya o?",
            "thread_id": "t1",
            "conversation_history": [{"role": "user", "content": "THYAO"}],
        },
    )

    sent = instance.stream.call_args.kwargs["json"]
    assert sent["conversation_history"] == [{"role": "user", "content": "THYAO"}]


class TestChatHistoryEndpoints:
    """The read path for stored conversations.

    Turns were persisted from day one and no endpoint returned them; the chat
    UI restored its sessions from `localStorage`, so history lived in a single
    browser. Anyone else with the same database — a teammate who loaded the
    seeds, or the same person in a private window — saw an empty sidebar.
    """

    def _as_user(self, user_id="user-1"):
        from app.core.database import get_db
        from app.core.deps import get_current_user_id
        from app.main import app

        app.dependency_overrides[get_current_user_id] = lambda: user_id
        app.dependency_overrides[get_db] = lambda: MagicMock()

    def _clear(self):
        from app.core.database import get_db
        from app.core.deps import get_current_user_id
        from app.main import app

        app.dependency_overrides.pop(get_current_user_id, None)
        app.dependency_overrides.pop(get_db, None)

    def test_listing_requires_a_signed_in_user(self, client):
        """user_id comes from the bearer token, never a query parameter —
        the same rule /chat follows."""
        assert client.get("/api/ai_orchestrator/conversations").status_code == 401

    def test_listing_returns_the_stored_conversations(self, client, mocker):
        from app.modules.ai_orchestrator import service

        mocker.patch.object(service, "list_conversations", return_value=[
            {"thread_id": "t-1", "title": "aselsan hissesi var mı",
             "updated_at": datetime(2026, 8, 25, 12, 51, tzinfo=timezone.utc),
             "message_count": 18},
        ])
        self._as_user()
        try:
            response = client.get("/api/ai_orchestrator/conversations")
        finally:
            self._clear()

        assert response.status_code == 200
        body = response.json()
        assert body[0]["thread_id"] == "t-1"
        assert body[0]["message_count"] == 18
        assert "meta" not in body[0]

    def test_messages_are_returned_for_your_own_thread(self, client, mocker):
        from app.modules.ai_orchestrator import service

        mocker.patch.object(service, "conversation_messages", return_value=[
            {"id": "m-1", "role": "user", "content": "merhaba",
             "created_at": datetime(2026, 8, 25, 12, 51, tzinfo=timezone.utc)},
        ])
        self._as_user()
        try:
            response = client.get("/api/ai_orchestrator/conversations/t-1/messages")
        finally:
            self._clear()

        assert response.status_code == 200
        assert response.json()[0]["content"] == "merhaba"
        assert "meta" not in response.json()[0]

    def test_someone_elses_thread_is_a_404(self, client, mocker):
        """A thread id is guessable. Without the ownership filter this would
        hand one user another user's conversation."""
        from app.modules.ai_orchestrator import service

        mocker.patch.object(service, "conversation_messages", return_value=None)
        self._as_user()
        try:
            response = client.get("/api/ai_orchestrator/conversations/theirs/messages")
        finally:
            self._clear()

        assert response.status_code == 404

    def test_deleting_your_conversation_succeeds(self, client, mocker):
        from app.modules.ai_orchestrator import service

        mocker.patch.object(service, "delete_conversation", return_value=True)
        self._as_user()
        try:
            response = client.delete("/api/ai_orchestrator/conversations/t-1")
        finally:
            self._clear()

        assert response.status_code == 204

    def test_deleting_a_conversation_that_is_not_yours_is_a_404(self, client, mocker):
        from app.modules.ai_orchestrator import service

        mocker.patch.object(service, "delete_conversation", return_value=False)
        self._as_user()
        try:
            response = client.delete("/api/ai_orchestrator/conversations/theirs")
        finally:
            self._clear()

        assert response.status_code == 404
