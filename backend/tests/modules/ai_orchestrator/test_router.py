"""Unit tests for app/modules/ai_orchestrator/router.py.

Bu, backend'deki TEK dış HTTP çağrısı (`httpx.AsyncClient` ile
AI-Services/moneyfast-orchestrator'a giden istek). `block_network`
(conftest.py, autouse) gerçek bir soket açılmasını engelliyor; bu dosyada
`httpx.AsyncClient`'ın kendisini mock'layarak dört senaryoyu test ediyoruz:
başarı, bağlantı reddi, zaman aşımı, orchestrator'ın hata durumu döndürmesi.
"""

from __future__ import annotations

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
