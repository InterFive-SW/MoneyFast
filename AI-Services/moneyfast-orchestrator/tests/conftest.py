"""Shared fixtures for the MoneyFast orchestrator test suite.

Design notes:

* ``block_network`` is autouse and patches the socket layer itself. Mocking
  ``get_mcp_client`` or ``get_llm`` in each test is necessary but not
  sufficient: one forgotten patch and CI quietly dials Groq. Blocking at the
  socket means a missed mock fails loudly and locally.
* ``reset_module_state`` is autouse because ``orchestrator`` memoises the LLM
  and the compiled graph with ``lru_cache``, and ``mcp_client`` holds a module
  level singleton. Without a reset, test order changes results.
* ``GROQ_API_KEY`` is set for the whole session so that importing the app does
  not depend on the developer's shell. The missing-key path is tested
  explicitly by deleting it inside that one test.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any

import pytest

# The app modules sit one level above tests/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mcp_client  # noqa: E402
import orchestrator  # noqa: E402


class NetworkAccessAttempted(RuntimeError):
    """Raised when a unit test tries to open a real socket."""


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that attempts real network I/O.

    Covers Groq, the MCP server and anything else. ASGI transport used by
    TestClient is in-process and does not touch sockets, so FastAPI tests are
    unaffected.
    """

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise NetworkAccessAttempted(
            "Real network access attempted in a unit test. Patch "
            "orchestrator.get_llm or orchestrator.get_mcp_client instead."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic environment for every test."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_not_real")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")


@pytest.fixture(autouse=True)
def reset_module_state() -> None:
    """Clear memoised state so tests cannot leak into one another."""
    orchestrator.get_llm.cache_clear()
    orchestrator.get_graph.cache_clear()
    mcp_client._client = None
    yield
    orchestrator.get_llm.cache_clear()
    orchestrator.get_graph.cache_clear()
    mcp_client._client = None


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------
class FakeMessage:
    """Stand-in for a LangChain AIMessage."""

    def __init__(self, content: str | None) -> None:
        self.content = content


@pytest.fixture()
def fake_llm(mocker):
    """A ChatGroq double whose ``ainvoke`` returns whatever the test sets.

    Usage::

        fake_llm.set_response('{"arguments": {}}')
        fake_llm.set_responses(["first", "second"])   # one per call
    """
    llm = mocker.MagicMock(name="ChatGroq")
    llm._queue = []

    async def _ainvoke(messages):
        llm.calls.append(messages)
        if llm._queue:
            return FakeMessage(llm._queue.pop(0))
        return FakeMessage(llm._default)

    llm.calls = []
    llm._default = "Taslak yanıt."
    llm.ainvoke = _ainvoke
    llm.set_response = lambda text: setattr(llm, "_default", text)
    llm.set_responses = lambda texts: llm._queue.extend(texts)
    return llm


@pytest.fixture()
def patched_llm(mocker, fake_llm):
    """Bind the fake LLM into the orchestrator, bypassing get_llm entirely."""
    mocker.patch.object(orchestrator, "get_llm", return_value=fake_llm)
    return fake_llm


@pytest.fixture()
def fake_mcp(mocker):
    """An MCPToolClient double with a per-tool response registry.

    ``responses`` maps a tool name to either a payload dict or an exception
    instance, which lets a single fixture drive both happy and failure paths.
    """
    client = mocker.MagicMock(name="MCPToolClient")
    client.responses = {}
    client.calls = []

    async def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        client.calls.append((name, arguments))
        outcome = client.responses.get(name, {})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def _list_tools() -> list[str]:
        return sorted(client.responses) or ["get_portfolio_positions"]

    client.call = _call
    client.list_tools = _list_tools
    mocker.patch.object(orchestrator, "get_mcp_client", return_value=client)
    return client


# --------------------------------------------------------------------------
# Payload fixtures mirroring the v2.1 tool contracts
# --------------------------------------------------------------------------
@pytest.fixture()
def routing_payload() -> dict[str, Any]:
    return {
        "primary_intent": "PORTFOLIO_INQUIRY",
        "confidence": 0.93,
        "target_agent": "PORTFOLIO_AGENT",
        "secondary_intents": [],
        "is_compound": False,
        "sub_requests": [],
        "entities": {"tickers": ["THYAO"]},
        "required_tools": ["get_portfolio_positions"],
        "needs_clarification": False,
        "clarifying_question": None,
        "routing_rationale": "Ownership reference.",
        "safety_flags": [],
    }


@pytest.fixture()
def positions_payload() -> dict[str, Any]:
    return {
        "as_of": "2026-08-13T15:10:00Z",
        "source": "CUSTODIAN_OF_RECORD",
        "is_delayed": True,
        "delay_minutes": 15,
        "base_currency": "TRY",
        "positions": [
            {
                "symbol": "THYAO",
                "quantity": 500.0,
                "market_value": 145875.0,
                "asset_class": "EQUITY",
                "available_quantity": 500.0,
            }
        ],
        "totals": {"total_market_value": 145875.0, "position_count": 1},
        "warnings": [],
    }


@pytest.fixture()
def empty_positions_payload(positions_payload) -> dict[str, Any]:
    return {**positions_payload, "positions": [], "totals": {"position_count": 0}}


@pytest.fixture()
def proposal_payload() -> dict[str, Any]:
    return {
        "proposal_id": "prp_8d31f04c",
        "status": "PENDING_USER_CONFIRMATION",
        "expires_at": "2026-08-13T15:25:00Z",
        "confirmation_required": True,
        "summary": {"transaction_type": "BUY"},
        "estimate": {"total_cost": 29205.64, "price_certainty": "INDICATIVE"},
        "impact": None,
        "blockers": [],
        "warnings": [],
        "missing_fields": [],
        "disclosures": [],
        "audit_id": "aud_7a20be31",
    }


@pytest.fixture()
def pass_verdict() -> dict[str, Any]:
    return {
        "verdict": "PASS",
        "rule_pack_version": "TR_RETAIL_2026.07",
        "violations": [],
        "required_disclosures": [],
        "remediated_response": None,
        "blocked_reason_user_facing": None,
        "audit_id": "aud_1",
    }


@pytest.fixture()
def base_state() -> dict[str, Any]:
    """Minimal state accepted by any node."""
    return {
        "user_message": "portföyüm ne durumda?",
        "conversation_history": [],
        "user_id": "u_123",
        "locale": "tr-TR",
        "target_agent": "PORTFOLIO_AGENT",
        "primary_intent": "PORTFOLIO_INQUIRY",
    }


# --------------------------------------------------------------------------
# FastAPI client
# --------------------------------------------------------------------------
@pytest.fixture()
def api_client():
    """Starlette TestClient over the ASGI app. No socket is opened."""
    from fastapi.testclient import TestClient

    import api

    with TestClient(api.app) as client:
        yield client
