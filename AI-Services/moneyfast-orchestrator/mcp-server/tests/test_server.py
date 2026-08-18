"""Unit tests for server.py.

Covers registration wiring plus the async MCP dispatch path. These are the
only async tests in the suite, because ``FastMCP.list_tools`` and
``call_tool`` are coroutines. No transport is opened: dispatch happens
in-process, and ``block_network`` in conftest guarantees it.

The ``__main__`` block is exercised with ``runpy`` under a patched FastMCP,
so the ``mcp.run(transport="sse")`` line is covered without ever binding a
port.
"""

from __future__ import annotations

import importlib
import runpy

import pytest

import server

EXPECTED_TOOLS = {
    "get_portfolio_positions",
    "rag_semantic_market_search",
    "calculate_portfolio_risk_metrics",
    "validate_compliance_rules",
    "classify_and_route_intent",
    "prepare_transaction_proposal",
}


# --------------------------------------------------------------------------
# Module constants and wiring
# --------------------------------------------------------------------------
def test_server_identity_constants():
    assert server.SERVER_NAME == "moneyfast"
    assert server.CONTRACT_VERSION == "v2.1"


def test_instructions_state_the_four_load_bearing_rules():
    """The instructions block is the only guidance a client sees before it
    reads a docstring, so the invariants have to be in it."""
    instructions = server.SERVER_INSTRUCTIONS
    assert "classify_and_route_intent first" in instructions
    assert "empty list is a valid" in instructions
    assert "Fail closed" in instructions
    assert "stages only" in instructions


def test_domain_modules_cover_all_six_domains():
    domains = {name for name, _ in server.DOMAIN_MODULES}
    assert domains == {
        "orchestrator", "portfolio", "market_research",
        "risk_strategy", "compliance", "transaction",
    }


def test_every_domain_module_exposes_register():
    for _, module in server.DOMAIN_MODULES:
        assert callable(getattr(module, "register", None)), module.__name__


def test_routing_is_registered_first():
    """Ordering is cosmetic for correctness but documents the call sequence."""
    assert server.DOMAIN_MODULES[0][0] == "orchestrator"


def test_bound_to_all_interfaces_for_container_networking():
    """0.0.0.0, not 127.0.0.1. Binding to loopback inside a container makes the
    port unreachable from the orchestrator container on the same network."""
    assert server.mcp.settings.host == "0.0.0.0"
    assert server.mcp.settings.port == 8000


# --------------------------------------------------------------------------
# build_server
# --------------------------------------------------------------------------
def test_build_server_returns_the_shared_instance():
    assert server.build_server() is server.mcp


def test_build_server_registers_every_domain(mocker):
    """Isolated: each module's register is replaced with a spy, so nothing is
    attached to the real FastMCP instance during this test."""
    spies = []
    for _, module in server.DOMAIN_MODULES:
        spies.append(mocker.patch.object(module, "register"))
    server.build_server()
    for spy in spies:
        spy.assert_called_once_with(server.mcp)


def test_build_server_logs_readiness(mocker, caplog):
    for _, module in server.DOMAIN_MODULES:
        mocker.patch.object(module, "register")
    with caplog.at_level("INFO", logger="moneyfast.mcp"):
        server.build_server()
    assert any("MOCK DATA ONLY" in record.getMessage() for record in caplog.records)


# --------------------------------------------------------------------------
# Async dispatch through FastMCP
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_six_tools_are_discoverable():
    tools = await server.mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_no_duplicate_registrations():
    """build_server runs at import; a second call must not double-register."""
    tools = await server.mcp.list_tools()
    names = [t.name for t in tools]
    assert len(names) == len(set(names))


@pytest.mark.asyncio
async def test_full_docstrings_are_published_as_tool_descriptions():
    """The interface contract only helps the model if it actually ships. A
    truncated description means the docstring was shortened somewhere."""
    tools = await server.mcp.list_tools()
    for tool in tools:
        assert tool.description and len(tool.description) > 3000, tool.name
        assert "WHEN TO USE" in tool.description
        assert "Constraints:" in tool.description


@pytest.mark.asyncio
async def test_required_arguments_are_advertised_in_the_schema():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert "user_id" in tools["get_portfolio_positions"].inputSchema["required"]
    assert "query" in tools["rag_semantic_market_search"].inputSchema["required"]
    assert "positions" in tools["calculate_portfolio_risk_metrics"].inputSchema["required"]
    assert "idempotency_key" in tools["prepare_transaction_proposal"].inputSchema["required"]


@pytest.mark.asyncio
async def test_optional_arguments_are_not_marked_required():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    required = set(tools["get_portfolio_positions"].inputSchema.get("required", []))
    assert "account_ids" not in required
    assert "base_currency" not in required


@pytest.mark.asyncio
async def test_dispatch_reaches_the_portfolio_tool():
    result = await server.mcp.call_tool("get_portfolio_positions", {"user_id": "u_1"})
    payload = result[1] if isinstance(result, tuple) else result
    assert isinstance(payload, dict)


@pytest.mark.asyncio
async def test_dispatch_reaches_the_transaction_tool():
    result = await server.mcp.call_tool(
        "prepare_transaction_proposal",
        {
            "user_id": "u_1",
            "transaction_type": "BUY",
            "source_account_id": "acc_998877",
            "idempotency_key": "idem_1",
        },
    )
    payload = result[1] if isinstance(result, tuple) else result
    assert isinstance(payload, dict)


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected():
    with pytest.raises(Exception):
        await server.mcp.call_tool("get_stock_tips", {})


@pytest.mark.asyncio
async def test_missing_required_argument_is_rejected():
    """Schema validation must catch this before the function body runs."""
    with pytest.raises(Exception):
        await server.mcp.call_tool("get_portfolio_positions", {})


@pytest.mark.asyncio
async def test_tool_exception_surfaces_through_dispatch(mocker):
    """The seam that stays valid after the mocks become real HTTP calls.

    A failing custodian must reach the caller, never be swallowed into a
    partial or empty payload, because the orchestrator distinguishes ERROR
    from EMPTY and is only allowed to say "no holdings found" for the latter.

    A real replacement function is used rather than a MagicMock: FastMCP reads
    ``__name__`` and the signature at registration time, so a bare mock cannot
    be registered as a tool.
    """

    def get_portfolio_positions(user_id: str) -> dict:
        """Failing stand-in for the custodian client."""
        raise RuntimeError("UpstreamUnavailableError: HTTP 500")

    mocker.patch.object(
        server.portfolio_tools, "get_portfolio_positions", get_portfolio_positions
    )
    fresh = server.FastMCP("moneyfast-test")
    server.portfolio_tools.register(fresh)
    with pytest.raises(Exception, match="HTTP 500"):
        await fresh.call_tool("get_portfolio_positions", {"user_id": "u_1"})


# --------------------------------------------------------------------------
# The __main__ entrypoint
# --------------------------------------------------------------------------
def test_main_block_starts_sse_transport(mocker):
    """Runs server.py as __main__ with FastMCP replaced, so run() is asserted
    rather than executed. Nothing binds a port and no transport is created."""
    fake_mcp = mocker.MagicMock(name="FastMCP_instance")
    mocker.patch("mcp.server.fastmcp.FastMCP", return_value=fake_mcp)
    runpy.run_path(str(server.__file__), run_name="__main__")
    fake_mcp.run.assert_called_once_with(transport="sse")


def test_main_block_binds_all_interfaces_and_port_8000(mocker):
    factory = mocker.patch("mcp.server.fastmcp.FastMCP")
    runpy.run_path(str(server.__file__), run_name="__main__")
    _, kwargs = factory.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8000


def test_module_is_importable_without_side_effects_beyond_registration():
    """Re-importing must not start a server; only __main__ does that."""
    reloaded = importlib.reload(server)
    assert reloaded.mcp is not None
