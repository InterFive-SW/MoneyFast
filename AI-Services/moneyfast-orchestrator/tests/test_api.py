"""Unit tests for api.py.

The ASGI app is exercised through Starlette's TestClient, which dispatches
in-process over ASGITransport and opens no socket. ``run_turn`` and
``get_mcp_client`` are patched at the ``api`` module level, since that is
where the names are bound.

The security assertion in this file is the response-shape one: the graph state
carries ``specialist_output``, ``draft_response`` and ``tools_used``, and none
of those may cross to the client. ``draft_response`` in particular can be the
text compliance just refused to emit.
"""

from __future__ import annotations

import pytest

import api


@pytest.fixture()
def patched_run_turn(mocker):
    """Replace the graph with a controllable coroutine."""
    return mocker.patch.object(
        api,
        "run_turn",
        return_value={
            "final_output": "Portföyünüzde 500 lot THYAO var.",
            "primary_intent": "PORTFOLIO_INQUIRY",
            "target_agent": "PORTFOLIO_AGENT",
            "compliance_verdict": "PASS",
            "draft_response": "iç taslak, sızmamalı",
            "specialist_output": {"data": {"positions": [{"symbol": "THYAO"}]}},
            "tools_used": ["get_portfolio_positions"],
        },
    )


# --------------------------------------------------------------------------
# Liveness
# --------------------------------------------------------------------------
def test_healthz_is_dependency_free(api_client):
    """Liveness must not touch the MCP server: a dependent liveness probe
    makes Docker restart a healthy container when a neighbour is down."""
    response = api_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------
def test_readyz_lists_the_tools_when_the_server_answers(api_client, mocker):
    client = mocker.MagicMock()

    async def _list_tools():
        return ["get_portfolio_positions", "validate_compliance_rules"]

    client.list_tools = _list_tools
    mocker.patch.object(api, "get_mcp_client", return_value=client)

    response = api_client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert "validate_compliance_rules" in body["mcp_tools"]


def test_readyz_returns_503_when_the_mcp_server_is_unreachable(api_client, mocker):
    """503, not 500. The container is alive but not ready to serve, which is
    what orchestration needs in order to hold traffic rather than restart."""
    client = mocker.MagicMock()

    async def _list_tools():
        raise ConnectionError("no route to host mcp-market-data")

    client.list_tools = _list_tools
    mocker.patch.object(api, "get_mcp_client", return_value=client)

    response = api_client.get("/readyz")
    assert response.status_code == 503
    assert "mcp unreachable" in response.json()["detail"]


def test_readyz_surfaces_a_timeout_as_503(api_client, mocker):
    client = mocker.MagicMock()

    async def _list_tools():
        raise TimeoutError("timed out after 30s")

    client.list_tools = _list_tools
    mocker.patch.object(api, "get_mcp_client", return_value=client)
    assert api_client.get("/readyz").status_code == 503


# --------------------------------------------------------------------------
# /chat happy path
# --------------------------------------------------------------------------
def test_chat_returns_the_final_output(api_client, patched_run_turn):
    response = api_client.post("/chat", json={"user_message": "portföyüm ne durumda?"})
    assert response.status_code == 200
    assert response.json()["final_output"] == "Portföyünüzde 500 lot THYAO var."


def test_chat_exposes_only_the_four_public_fields(api_client, patched_run_turn):
    """Internal graph state must not cross the wire. draft_response can hold
    text the compliance gate refused to emit."""
    body = api_client.post("/chat", json={"user_message": "x"}).json()
    assert set(body) == {
        "final_output", "primary_intent", "target_agent", "compliance_verdict"
    }
    assert "iç taslak" not in response_text(body)


def response_text(body: dict) -> str:
    return " ".join(str(v) for v in body.values())


def test_chat_forwards_defaults_to_the_graph(api_client, patched_run_turn):
    api_client.post("/chat", json={"user_message": "merhaba"})
    kwargs = patched_run_turn.call_args.kwargs
    assert patched_run_turn.call_args.args[0] == "merhaba"
    assert kwargs["user_id"] == "anonymous"
    assert kwargs["thread_id"] == "default"
    assert kwargs["conversation_history"] == []


def test_chat_forwards_identity_and_history(api_client, patched_run_turn):
    api_client.post(
        "/chat",
        json={
            "user_message": "peki ya riski?",
            "user_id": "u_123",
            "thread_id": "t-42",
            "conversation_history": [
                {"role": "user", "content": "portföyüm"},
                {"role": "assistant", "content": "500 lot THYAO"},
            ],
        },
    )
    kwargs = patched_run_turn.call_args.kwargs
    assert kwargs["user_id"] == "u_123"
    assert kwargs["thread_id"] == "t-42"
    assert kwargs["conversation_history"] == [
        {"role": "user", "content": "portföyüm"},
        {"role": "assistant", "content": "500 lot THYAO"},
    ]


def test_chat_history_is_serialised_to_plain_dicts(api_client, patched_run_turn):
    """The graph expects dicts, not pydantic models, so model_dump has to run."""
    api_client.post(
        "/chat",
        json={
            "user_message": "x",
            "conversation_history": [{"role": "user", "content": "y"}],
        },
    )
    history = patched_run_turn.call_args.kwargs["conversation_history"]
    assert all(isinstance(turn, dict) for turn in history)


def test_chat_tolerates_a_missing_final_output(api_client, mocker):
    """Edge case: a graph path that ends without writing final_output must
    still yield a valid response body rather than a 500."""
    mocker.patch.object(api, "run_turn", return_value={"primary_intent": "SMALLTALK"})
    response = api_client.post("/chat", json={"user_message": "merhaba"})
    assert response.status_code == 200
    assert response.json()["final_output"] == ""


def test_chat_optional_fields_default_to_null(api_client, mocker):
    mocker.patch.object(api, "run_turn", return_value={"final_output": "ok"})
    body = api_client.post("/chat", json={"user_message": "x"}).json()
    assert body["primary_intent"] is None
    assert body["target_agent"] is None
    assert body["compliance_verdict"] is None


# --------------------------------------------------------------------------
# /chat validation
# --------------------------------------------------------------------------
def test_empty_message_is_rejected_with_422(api_client, patched_run_turn):
    """min_length=1. Rejecting at the edge saves a pointless graph traversal."""
    response = api_client.post("/chat", json={"user_message": ""})
    assert response.status_code == 422
    patched_run_turn.assert_not_called()


def test_missing_message_field_is_rejected_with_422(api_client, patched_run_turn):
    assert api_client.post("/chat", json={}).status_code == 422
    patched_run_turn.assert_not_called()


def test_oversized_message_is_rejected_with_422(api_client, patched_run_turn):
    """max_length=4000 caps the prompt-injection surface and the token bill."""
    response = api_client.post("/chat", json={"user_message": "x" * 4001})
    assert response.status_code == 422
    patched_run_turn.assert_not_called()


def test_message_at_the_length_boundary_is_accepted(api_client, patched_run_turn):
    assert api_client.post("/chat", json={"user_message": "x" * 4000}).status_code == 200


def test_malformed_history_entry_is_rejected(api_client, patched_run_turn):
    response = api_client.post(
        "/chat",
        json={"user_message": "x", "conversation_history": [{"role": "user"}]},
    )
    assert response.status_code == 422


def test_wrong_type_for_message_is_rejected(api_client, patched_run_turn):
    assert api_client.post("/chat", json={"user_message": 42}).status_code == 422


def test_turkish_characters_survive_the_round_trip(api_client, mocker):
    """UTF-8 handling: a mangled ı or ğ would reach the user verbatim."""
    mocker.patch.object(
        api, "run_turn", return_value={"final_output": "Öğrenmek için: ığüşçö"}
    )
    body = api_client.post("/chat", json={"user_message": "portföyüm"}).json()
    assert body["final_output"] == "Öğrenmek için: ığüşçö"


# --------------------------------------------------------------------------
# /chat failure modes
# --------------------------------------------------------------------------
def test_graph_exception_surfaces_as_500(api_client, mocker):
    """An unhandled graph error must not be masked as a 200 with empty text:
    the client cannot distinguish that from a legitimate empty answer."""
    mocker.patch.object(api, "run_turn", side_effect=RuntimeError("graph exploded"))
    with pytest.raises(RuntimeError, match="graph exploded"):
        api_client.post("/chat", json={"user_message": "x"})


def test_graph_exception_returns_500_to_a_real_client(mocker):
    """Same case with exception propagation off, which is how uvicorn behaves
    in production: the client sees a 500, not a traceback."""
    from fastapi.testclient import TestClient

    mocker.patch.object(api, "run_turn", side_effect=RuntimeError("graph exploded"))
    client = TestClient(api.app, raise_server_exceptions=False)
    assert client.post("/chat", json={"user_message": "x"}).status_code == 500


def test_llm_outage_inside_the_graph_still_returns_200(api_client, mocker):
    """The graph is meant to degrade internally rather than raise. This pins
    that contract at the HTTP boundary."""
    mocker.patch.object(
        api,
        "run_turn",
        return_value={
            "final_output": "Şu anda yanıtı hazırlayamadım.",
            "compliance_verdict": "BLOCK",
        },
    )
    response = api_client.post("/chat", json={"user_message": "x"})
    assert response.status_code == 200
    assert response.json()["compliance_verdict"] == "BLOCK"


# --------------------------------------------------------------------------
# App metadata and routing
# --------------------------------------------------------------------------
def test_app_metadata():
    assert api.app.title == "MoneyFast Orchestrator"
    assert api.app.version == "1.0.0"


def test_only_the_three_documented_routes_exist():
    """A stray debug route is how internal state leaks in practice."""
    paths = {r.path for r in api.app.routes if hasattr(r, "path")}
    assert {"/healthz", "/readyz", "/chat"} <= paths
    assert not {p for p in paths if p.startswith("/debug")}


def test_unknown_path_returns_404(api_client):
    assert api_client.get("/does-not-exist").status_code == 404


def test_wrong_method_returns_405(api_client):
    assert api_client.get("/chat").status_code == 405


def test_response_model_declares_the_public_contract():
    assert set(api.ChatResponse.model_fields) == {
        "final_output", "primary_intent", "target_agent", "compliance_verdict"
    }


def test_request_model_defaults():
    request = api.ChatRequest(user_message="x")
    assert request.user_id == "anonymous"
    assert request.thread_id == "default"
    assert request.conversation_history == []
