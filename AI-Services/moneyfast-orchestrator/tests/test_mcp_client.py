"""Unit tests for mcp_client.py.

No SSE stream is ever opened: ``sse_client`` and ``ClientSession`` are both
replaced with async context managers, so the retry loop, the payload decoder
and the error taxonomy are exercised in-process.

The distinction the tests protect is the one the graph depends on:
MCPToolError means the tool ran and failed, MCPUnavailable means we never got
an answer. The graph renders those differently, so collapsing them would be a
user-visible bug.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest

import mcp_client
from mcp_client import MCPToolClient, MCPToolError, MCPUnavailable


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------
class FakeBlock:
    def __init__(self, text=None):
        if text is not None:
            self.text = text


class FakeResult:
    """Mimics mcp.types.CallToolResult closely enough for the decoder."""

    def __init__(self, content=None, structured=None, is_error=False):
        self.content = content
        self.isError = is_error
        if structured is not None:
            self.structuredContent = structured


class FakeTool:
    def __init__(self, name):
        self.name = name


class FakeToolList:
    def __init__(self, names):
        self.tools = [FakeTool(n) for n in names]


class FakeSession:
    """Stands in for mcp.ClientSession."""

    def __init__(self, result=None, tools=(), call_error=None):
        self._result = result
        self._tools = tools
        self._call_error = call_error
        self.initialized = False
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def initialize(self):
        self.initialized = True

    async def list_tools(self):
        return FakeToolList(self._tools)

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments))
        if self._call_error is not None:
            raise self._call_error
        return self._result


def patch_transport(mocker, session=None, connect_error=None, sessions=None):
    """Replace sse_client and ClientSession with in-process doubles.

    ``connect_error`` simulates a transport failure at connect time;
    ``sessions`` supplies a different session per attempt so retry behaviour
    can be observed.
    """
    state = {"attempts": 0}

    @asynccontextmanager
    async def _sse_client(url, timeout=None):
        state["attempts"] += 1
        if connect_error is not None and (
            sessions is None or state["attempts"] <= len(connect_error)
        ):
            raise connect_error[state["attempts"] - 1] if isinstance(
                connect_error, list
            ) else connect_error
        yield ("read", "write")

    def _client_session(read, write):
        if sessions is not None:
            return sessions[min(state["attempts"] - 1, len(sessions) - 1)]
        return session

    mocker.patch.object(mcp_client, "sse_client", _sse_client)
    mocker.patch.object(mcp_client, "ClientSession", _client_session)
    return state


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------
def test_defaults_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://mcp-market-data:8000/sse")
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("MCP_MAX_RETRIES", "3")
    client = MCPToolClient()
    assert client.url == "http://mcp-market-data:8000/sse"
    assert client.timeout == 12.5
    assert client.max_retries == 3


def test_falls_back_to_the_container_service_name(monkeypatch):
    """Edge case: no env at all. The default must be the Docker service name,
    never localhost, which inside a container resolves to the container."""
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    monkeypatch.delenv("MCP_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MCP_MAX_RETRIES", raising=False)
    client = MCPToolClient()
    assert client.url == "http://mcp-market-data:8000/sse"
    assert "localhost" not in client.url
    assert client.timeout == 30.0
    assert client.max_retries == 1


def test_explicit_arguments_override_the_environment(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://from-env:8000/sse")
    client = MCPToolClient(url="http://explicit:9000/sse", timeout=1.0, max_retries=0)
    assert client.url == "http://explicit:9000/sse"
    assert client.timeout == 1.0
    assert client.max_retries == 0


def test_zero_values_are_honoured_not_treated_as_missing(monkeypatch):
    """timeout=0.0 and max_retries=0 are falsy. ``is not None`` is required;
    an ``or`` here would silently restore the 30 second default."""
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "30")
    client = MCPToolClient(timeout=0.0, max_retries=0)
    assert client.timeout == 0.0
    assert client.max_retries == 0


# --------------------------------------------------------------------------
# list_tools
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_tools_returns_names_and_initialises_the_session(mocker):
    session = FakeSession(tools=["get_portfolio_positions", "validate_compliance_rules"])
    patch_transport(mocker, session=session)
    names = await MCPToolClient(url="http://x/sse").list_tools()
    assert names == ["get_portfolio_positions", "validate_compliance_rules"]
    assert session.initialized, "initialize() must run before any RPC"


@pytest.mark.asyncio
async def test_list_tools_on_an_empty_server(mocker):
    patch_transport(mocker, session=FakeSession(tools=[]))
    assert await MCPToolClient(url="http://x/sse").list_tools() == []


# --------------------------------------------------------------------------
# call: happy path
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_returns_the_decoded_payload(mocker):
    result = FakeResult(structured={"as_of": "2026-08-13T15:10:00Z", "positions": []})
    session = FakeSession(result=result)
    patch_transport(mocker, session=session)
    payload = await MCPToolClient(url="http://x/sse").call("get_portfolio_positions", {"user_id": "u_1"})
    assert payload["positions"] == []
    assert session.calls == [("get_portfolio_positions", {"user_id": "u_1"})]


@pytest.mark.asyncio
async def test_call_passes_arguments_through_unchanged(mocker):
    session = FakeSession(result=FakeResult(structured={"ok": True}))
    patch_transport(mocker, session=session)
    args = {"query": "THY", "top_k": 3, "filters": None}
    await MCPToolClient(url="http://x/sse").call("rag_semantic_market_search", args)
    assert session.calls[0][1] == args


# --------------------------------------------------------------------------
# call: tool-level error vs transport error
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_is_error_flag_raises_mcp_tool_error(mocker):
    """The tool ran and reported failure. This must not be retried: retrying a
    deterministic tool failure just burns latency."""
    result = FakeResult(content=[FakeBlock("InsufficientHistoryError")], is_error=True)
    state = patch_transport(mocker, session=FakeSession(result=result))
    with pytest.raises(MCPToolError, match="InsufficientHistoryError"):
        await MCPToolClient(url="http://x/sse", max_retries=3).call("t", {})
    assert state["attempts"] == 1, "tool errors must not be retried"


@pytest.mark.asyncio
async def test_transport_failure_is_retried_then_raises_unavailable(mocker):
    state = patch_transport(mocker, connect_error=ConnectionError("refused"))
    mocker.patch.object(mcp_client.asyncio, "sleep", new=_instant_sleep())
    with pytest.raises(MCPUnavailable, match="unreachable at"):
        await MCPToolClient(url="http://x/sse", max_retries=2).call("t", {})
    assert state["attempts"] == 3, "initial attempt plus two retries"


@pytest.mark.asyncio
async def test_zero_retries_fails_on_the_first_attempt(mocker):
    state = patch_transport(mocker, connect_error=TimeoutError("timed out"))
    with pytest.raises(MCPUnavailable):
        await MCPToolClient(url="http://x/sse", max_retries=0).call("t", {})
    assert state["attempts"] == 1


@pytest.mark.asyncio
async def test_negative_retry_budget_never_attempts_the_call(mocker):
    """Misconfiguration guard: MCP_MAX_RETRIES=-1.

    The retry loop is ``while attempt <= max_retries``, so a negative budget
    skips the body entirely and falls through to the raise. This is the only
    path on which the loop exits by condition rather than by break, and the
    behaviour it produces is the right one: fail fast and loudly, rather than
    hang or return a fabricated empty payload.
    """
    monkey = patch_transport(mocker, session=FakeSession(result=FakeResult(structured={"ok": 1})))
    with pytest.raises(MCPUnavailable) as info:
        await MCPToolClient(url="http://x/sse", max_retries=-1).call("t", {})
    assert monkey["attempts"] == 0, "no transport connection should be opened"
    assert info.value.__cause__ is None


@pytest.mark.asyncio
async def test_negative_retry_budget_from_the_environment(monkeypatch, mocker):
    monkeypatch.setenv("MCP_MAX_RETRIES", "-1")
    patch_transport(mocker, session=FakeSession(result=FakeResult(structured={"ok": 1})))
    with pytest.raises(MCPUnavailable):
        await MCPToolClient(url="http://x/sse").call("t", {})


@pytest.mark.asyncio
async def test_transient_failure_then_success(mocker):
    """The retry actually has to work, not just be counted."""
    sleeps = []

    @asynccontextmanager
    async def _flaky(url, timeout=None):
        _flaky.attempts += 1
        if _flaky.attempts == 1:
            raise ConnectionError("first attempt dies")
        yield ("read", "write")

    _flaky.attempts = 0
    mocker.patch.object(mcp_client, "sse_client", _flaky)
    mocker.patch.object(
        mcp_client, "ClientSession", lambda r, w: FakeSession(result=FakeResult(structured={"ok": 1}))
    )
    mocker.patch.object(mcp_client.asyncio, "sleep", new=_instant_sleep(sleeps))
    payload = await MCPToolClient(url="http://x/sse", max_retries=2).call("t", {})
    assert payload == {"ok": 1}
    assert _flaky.attempts == 2
    assert sleeps == [0.5], "first backoff is 0.5s"


@pytest.mark.asyncio
async def test_backoff_is_exponential(mocker):
    sleeps = []
    patch_transport(mocker, connect_error=ConnectionError("down"))
    mocker.patch.object(mcp_client.asyncio, "sleep", new=_instant_sleep(sleeps))
    with pytest.raises(MCPUnavailable):
        await MCPToolClient(url="http://x/sse", max_retries=3).call("t", {})
    assert sleeps == [0.5, 1.0, 2.0]


@pytest.mark.asyncio
async def test_unavailable_error_names_the_url_and_chains_the_cause(mocker):
    """Operators need the URL to diagnose a Docker networking mistake."""
    patch_transport(mocker, connect_error=ConnectionError("name resolution failed"))
    mocker.patch.object(mcp_client.asyncio, "sleep", new=_instant_sleep())
    with pytest.raises(MCPUnavailable) as info:
        await MCPToolClient(url="http://mcp-market-data:8000/sse", max_retries=1).call("t", {})
    assert "mcp-market-data:8000" in str(info.value)
    assert isinstance(info.value.__cause__, ConnectionError)


@pytest.mark.asyncio
async def test_error_inside_call_tool_is_treated_as_transport_failure(mocker):
    """A protocol-level exception is retried like any other transport fault."""
    session = FakeSession(call_error=RuntimeError("protocol desync"))
    patch_transport(mocker, session=session)
    mocker.patch.object(mcp_client.asyncio, "sleep", new=_instant_sleep())
    with pytest.raises(MCPUnavailable, match="protocol desync"):
        await MCPToolClient(url="http://x/sse", max_retries=1).call("t", {})


def _instant_sleep(recorder=None):
    async def _sleep(seconds):
        if recorder is not None:
            recorder.append(seconds)

    return _sleep


# --------------------------------------------------------------------------
# Payload decoding
# --------------------------------------------------------------------------
def test_payload_unwraps_the_fastmcp_result_envelope():
    """FastMCP wraps a plain dict return under a single "result" key."""
    inner = {"as_of": "2026-08-13T15:10:00Z", "positions": []}
    assert mcp_client._payload(FakeResult(structured={"result": inner})) == inner


def test_payload_keeps_a_structured_dict_that_is_not_an_envelope():
    structured = {"verdict": "PASS", "audit_id": "aud_1"}
    assert mcp_client._payload(FakeResult(structured=structured)) == structured


def test_payload_keeps_a_result_key_that_is_not_a_dict():
    """{"result": [...]} is real content, not an envelope, so it stays wrapped."""
    structured = {"result": [1, 2, 3]}
    assert mcp_client._payload(FakeResult(structured=structured)) == structured


def test_payload_ignores_non_dict_structured_content():
    assert mcp_client._payload(FakeResult(structured=["not", "a", "dict"], content=None)) == {}


def test_payload_parses_json_from_text_blocks():
    payload = {"verdict": "BLOCK"}
    result = FakeResult(content=[FakeBlock(json.dumps(payload))])
    assert mcp_client._payload(result) == payload


def test_payload_wraps_a_json_array_under_result():
    result = FakeResult(content=[FakeBlock(json.dumps([1, 2]))])
    assert mcp_client._payload(result) == {"result": [1, 2]}


def test_payload_returns_raw_on_malformed_json():
    """A tool that returns prose must not crash the graph; the raw text is
    surfaced so the failure is visible in logs."""
    result = FakeResult(content=[FakeBlock("not json at all")])
    assert mcp_client._payload(result) == {"raw": "not json at all"}


def test_payload_of_an_empty_result_is_an_empty_dict():
    assert mcp_client._payload(FakeResult(content=[])) == {}


def test_payload_with_no_content_attribute_at_all():
    assert mcp_client._payload(object()) == {}


def test_as_text_joins_multiple_blocks():
    result = FakeResult(content=[FakeBlock("line one"), FakeBlock("line two")])
    assert mcp_client._as_text(result) == "line one\nline two"


def test_as_text_skips_blocks_without_text():
    """Image and resource blocks have no .text and must be stepped over."""
    result = FakeResult(content=[FakeBlock(), FakeBlock("kept"), FakeBlock("")])
    assert mcp_client._as_text(result) == "kept"


def test_as_text_handles_none_content():
    assert mcp_client._as_text(FakeResult(content=None)) == ""


# --------------------------------------------------------------------------
# Singleton
# --------------------------------------------------------------------------
def test_get_mcp_client_is_a_singleton():
    first = mcp_client.get_mcp_client()
    second = mcp_client.get_mcp_client()
    assert first is second


def test_get_mcp_client_logs_the_bound_url_once(caplog, monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://mcp-market-data:8000/sse")
    with caplog.at_level("INFO", logger="moneyfast.mcp"):
        mcp_client.get_mcp_client()
        mcp_client.get_mcp_client()
    bindings = [r for r in caplog.records if "bound to" in r.getMessage()]
    assert len(bindings) == 1


def test_error_types_are_distinct_so_the_graph_can_branch():
    """MCPToolError: the tool answered and failed. MCPUnavailable: no answer.
    The graph renders these differently, so they must not share a class."""
    assert issubclass(MCPToolError, RuntimeError)
    assert issubclass(MCPUnavailable, RuntimeError)
    assert not issubclass(MCPToolError, MCPUnavailable)
    assert not issubclass(MCPUnavailable, MCPToolError)
