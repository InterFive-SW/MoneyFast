"""Unit tests for server.py.

Registration wiring plus the MCP dispatch path. Five of the six tools are now
coroutines that speak HTTP, so dispatch tests run through the ``fake_backend``
transport from conftest: FastMCP awaits the tool, the tool calls
``backend_client``, and the MockTransport answers. No socket is opened at any
point, and ``block_network`` proves it.

The ``__main__`` block is exercised with ``runpy`` under a patched FastMCP, so
``mcp.run(transport="sse")`` is covered without binding a port.
"""

from __future__ import annotations

import importlib
import inspect
import runpy

import pytest

import server

EXPECTED_TOOLS = {
    # v2.21: ölçülen kanıtların hangi yöne meylettiği, gerekçesiyle.
    "get_direction_signal",
    # v2.22: ekranda duran dengeleme listesi. Araç onu ÜRETMİYOR, okuyor.
    "get_rebalance_plan",
    "get_portfolio_positions",
    "get_market_data",
    "rag_semantic_market_search",
    "calculate_portfolio_risk_metrics",
    "get_risk_profile_summary",
    "validate_compliance_rules",
    "classify_and_route_intent",
    "prepare_transaction_proposal",
    # v2.8: banking. Both stop at a proposal -- there is no execute tool.
    "lookup_bill",
    "prepare_payment_proposal",
    # v2.10: trend state for one instrument. Separate from get_market_data
    # because it needs price HISTORY, and the history can be too short to
    # answer -- a failure mode a current quote does not have.
    "get_technical_signals",
    # v2.11: haberin kullanıcının SAHİP OLDUĞU hisselerle kesişimi. Belge
    # aramasından ayrı, çünkü bu bir sorgu değil bir kesişim: eşleşme sembol
    # eşitliğiyle kesin, semantik yakınlıkla değil.
    "get_portfolio_news",
    # v2.12: aynı okuma, her POZİSYON için, artı tek bir toplam cümlesi.
    # Tek-sembol aracının n kez çağrılmasıyla aynı şey değil: sayı ile değer
    # ayrışıyor ve toplamı modele hesaplatmak her turda başka bir sayı
    # üretirdi.
    "get_portfolio_technicals",
    # v2.13: "ne olurdu" ailesi. Üçü de ölçüm; ikisi geçmiş getirilerin
    # aritmetiği, biri gerçekten olan günler.
    "run_portfolio_scenario",
    "get_portfolio_stress_test",
    "simulate_position_change",
    # v2.14: şirketin işi nasıl gidiyor. Yeni veri değil -- zaten toplanan
    # otuz beş alan, ajana ilk kez ulaşıyor.
    "get_company_fundamentals",
    # v2.15: tek SERİ taşıyan araç. Anlık görüntünün cevaplayamadığı soru.
    "get_quarterly_financials",
    # v2.16: neye SAHİP olduğu değil, ne kazanıp ne harcadığı. Portföyle
    # bütçe arasındaki köprü; hesaplama zaten vardı, ajan göremiyordu.
    "get_cash_flow_summary",
    # v2.18: hepsi birden. Diğerleri birer soruyu cevaplıyor; bu, hiçbirinin
    # tek başına cevaplayamadığı "genel durum" sorusunu.
    "get_portfolio_report",
    # v2.19: şirket ADINDAN sembole. Belge aramasından ayrı, çünkü bu bir
    # benzerlik değil bir sözlük araması: "türk hava yolları" ile THYAO
    # arasındaki bağ kayıtlı bir gerçek. Bu araç olmadan yönlendiricinin
    # çıkardığı `company_names` hiçbir yerde okunmuyordu ve adla sorulan her
    # soru süzgeçsiz aramaya düşüyordu.
    "resolve_instruments",
    # v2.20: bekleyen emirler. Emir akışının karşılığı -- bir alım artık
    # onaylandığı anda gerçekleşmiyor, fiyatı gelene kadar bekliyor ve
    # parası bloke duruyor. Bunu göremeyen bir sohbet "aldım mı almadım mı"
    # ve "bakiyem neden azaldı" sorularının ikisini de cevapsız bırakıyordu.
    "get_open_orders",
    "cancel_order",
}

#: Every tool that reaches the backend. classify_and_route_intent is
#: deliberately excluded: it stayed local, which is why it stayed sync.
HTTP_TOOLS = EXPECTED_TOOLS - {"classify_and_route_intent"}


# ==========================================================================
# Module constants and wiring
# ==========================================================================
class TestWiring:
    def test_server_identity_constants(self):
        assert server.SERVER_NAME == "moneyfast"
        # v2.10: `get_technical_signals` eklendi. Bilerek yapılan bir
        # sözleşme değişikliği, dolayısıyla iddia gevşetilmiyor, onunla
        # birlikte taşınıyor.
        # v2.19: `resolve_instruments`.
        # v2.20: `get_open_orders` + `cancel_order`.
        # v2.21: `get_direction_signal`.
        # v2.22: `get_rebalance_plan` (salt okuma).
        assert server.CONTRACT_VERSION == "v2.22"

    def test_instructions_state_the_load_bearing_rules(self):
        """The instructions block is the only guidance a client sees before it
        reads a docstring, so the invariants have to be in it."""
        instructions = server.SERVER_INSTRUCTIONS
        assert "classify_and_route_intent first" in instructions
        assert "empty list is a valid" in instructions
        assert "Fail closed" in instructions
        assert "stages only" in instructions

    def test_domain_modules_cover_every_domain(self):
        domains = {name for name, _ in server.DOMAIN_MODULES}
        assert domains == {
            "orchestrator", "portfolio", "market_data", "market_research",
            "risk_strategy", "compliance", "transaction", "banking",
            "technical", "news", "scenario", "fundamentals", "cash_flow",
            "report", "instrument", "order",
        }

    def test_every_domain_module_exposes_register(self):
        for _, module in server.DOMAIN_MODULES:
            assert callable(getattr(module, "register", None)), module.__name__

    def test_routing_is_registered_first(self):
        assert server.DOMAIN_MODULES[0][0] == "orchestrator"

    def test_bound_to_all_interfaces_for_container_networking(self):
        """0.0.0.0, not 127.0.0.1. Loopback inside a container makes the port
        unreachable from the orchestrator container on the same network."""
        assert server.mcp.settings.host == "0.0.0.0"
        assert server.mcp.settings.port == 8000

    def test_build_server_returns_the_shared_instance(self):
        assert server.build_server() is server.mcp

    def test_build_server_registers_every_domain(self, mocker):
        """Isolated: each register is replaced with a spy, so nothing attaches
        to the real FastMCP instance during this test."""
        spies = [mocker.patch.object(module, "register") for _, module in server.DOMAIN_MODULES]
        server.build_server()
        for spy in spies:
            spy.assert_called_once_with(server.mcp)

    def test_build_server_logs_readiness(self, mocker, caplog):
        for _, module in server.DOMAIN_MODULES:
            mocker.patch.object(module, "register")
        with caplog.at_level("INFO", logger="moneyfast.mcp"):
            server.build_server()
        assert any("moneyfast mcp ready" in r.getMessage() for r in caplog.records)


# ==========================================================================
# Discovery
# ==========================================================================
class TestDiscovery:
    @pytest.mark.asyncio
    async def test_every_tool_is_discoverable(self):
        tools = await server.mcp.list_tools()
        assert {t.name for t in tools} == EXPECTED_TOOLS

    @pytest.mark.asyncio
    async def test_no_duplicate_registrations(self):
        """build_server runs at import; a second call must not double-register."""
        names = [t.name for t in await server.mcp.list_tools()]
        assert len(names) == len(set(names))

    @pytest.mark.asyncio
    async def test_full_docstrings_are_published_as_tool_descriptions(self):
        """The interface contract only helps the model if it actually ships.
        The HTTP refactor must not have shortened any of them."""
        for tool in await server.mcp.list_tools():
            assert tool.description and len(tool.description) > 3000, tool.name
            assert "WHEN TO USE" in tool.description
            assert "Constraints:" in tool.description

    @pytest.mark.asyncio
    async def test_required_arguments_are_advertised(self):
        tools = {t.name: t for t in await server.mcp.list_tools()}
        assert "user_id" in tools["get_portfolio_positions"].inputSchema["required"]
        assert "query" in tools["rag_semantic_market_search"].inputSchema["required"]
        assert "positions" in tools["calculate_portfolio_risk_metrics"].inputSchema["required"]
        assert "idempotency_key" in tools["prepare_transaction_proposal"].inputSchema["required"]

    @pytest.mark.asyncio
    async def test_optional_arguments_are_not_marked_required(self):
        tools = {t.name: t for t in await server.mcp.list_tools()}
        required = set(tools["get_portfolio_positions"].inputSchema.get("required", []))
        assert "account_ids" not in required
        assert "base_currency" not in required

    @pytest.mark.asyncio
    async def test_async_signatures_survive_registration(self):
        """FastMCP awaits a coroutine tool. If one of these silently reverted
        to sync, it would block the event loop for the whole backend round
        trip and the failure would look like unrelated latency."""
        import compliance_tools
        import market_research_tools
        import portfolio_tools
        import risk_strategy_tools
        import transaction_tools

        for fn in (
            portfolio_tools.get_portfolio_positions,
            market_research_tools.rag_semantic_market_search,
            risk_strategy_tools.calculate_portfolio_risk_metrics,
            compliance_tools.validate_compliance_rules,
            transaction_tools.prepare_transaction_proposal,
        ):
            assert inspect.iscoroutinefunction(fn), fn.__name__

    @pytest.mark.asyncio
    async def test_the_routing_tool_stayed_synchronous(self):
        """It never calls the backend, so it has no reason to be async."""
        import orchestrator_tools

        assert not inspect.iscoroutinefunction(
            orchestrator_tools.classify_and_route_intent
        )


# ==========================================================================
# Dispatch
# ==========================================================================
class TestDispatch:
    @staticmethod
    def unwrap(result):
        return result[1] if isinstance(result, tuple) else result

    @pytest.mark.asyncio
    async def test_portfolio_dispatch_reaches_the_backend(self, fake_backend):
        result = await server.mcp.call_tool("get_portfolio_positions", {"user_id": "u_1"})
        assert isinstance(self.unwrap(result), dict)
        assert fake_backend.attempts == 1
        assert "/investment/portfolio/u_1/positions" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_search_dispatch_reaches_the_backend(self, fake_backend):
        await server.mcp.call_tool("rag_semantic_market_search", {"query": "THY"})
        assert "/search" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_risk_dispatch_reaches_the_backend(self, fake_backend, sample_positions):
        await server.mcp.call_tool(
            "calculate_portfolio_risk_metrics", {"positions": sample_positions}
        )
        assert "/risk/calculate" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_compliance_dispatch_reaches_the_backend(self, fake_backend):
        await server.mcp.call_tool(
            "validate_compliance_rules", {"draft_response": "d", "user_query": "q"}
        )
        assert "/compliance/validate" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_transaction_dispatch_reaches_the_backend(self, fake_backend, stage_args):
        await server.mcp.call_tool("prepare_transaction_proposal", stage_args)
        assert "/investment/transactions/stage" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_routing_dispatch_makes_no_http_call(self, fake_backend):
        """The one tool that stayed local must stay local."""
        await server.mcp.call_tool("classify_and_route_intent", {"user_message": "merhaba"})
        assert fake_backend.attempts == 0

    @pytest.mark.asyncio
    async def test_unknown_tool_is_rejected(self):
        with pytest.raises(Exception):
            await server.mcp.call_tool("get_stock_tips", {})

    @pytest.mark.asyncio
    async def test_missing_required_argument_is_rejected(self, fake_backend):
        """Schema validation must catch this before the function body runs, so
        no request should leave."""
        with pytest.raises(Exception):
            await server.mcp.call_tool("get_portfolio_positions", {})
        assert fake_backend.attempts == 0


# ==========================================================================
# Failures surface through dispatch
# ==========================================================================
class TestFailuresSurface:
    @pytest.mark.asyncio
    async def test_backend_outage_surfaces_as_a_tool_error(self, fake_backend):
        """The orchestrator distinguishes ERROR from EMPTY and is only allowed
        to say "no holdings found" for the latter. A swallowed failure would
        collapse that distinction into a lie."""
        fake_backend.status("portfolio", 503)
        with pytest.raises(Exception):
            await server.mcp.call_tool("get_portfolio_positions", {"user_id": "u_1"})

    @pytest.mark.asyncio
    async def test_compliance_failure_surfaces_so_the_graph_can_fail_closed(
        self, fake_backend
    ):
        """If this ever returned a payload instead of raising, the gate would
        silently become optional."""
        fake_backend.status("compliance", 500)
        with pytest.raises(Exception):
            await server.mcp.call_tool(
                "validate_compliance_rules", {"draft_response": "d", "user_query": "q"}
            )

    @pytest.mark.asyncio
    async def test_contract_violation_surfaces(self, fake_backend, stage_payload):
        fake_backend.json(
            "stage", {**stage_payload, "confirmation_required": False}
        )
        with pytest.raises(Exception):
            await server.mcp.call_tool(
                "prepare_transaction_proposal",
                {
                    "user_id": "u_1", "transaction_type": "BUY",
                    "source_account_id": "acc_1", "idempotency_key": "idem_1",
                },
            )

    @pytest.mark.asyncio
    async def test_empty_result_is_not_an_error(self, fake_backend, portfolio_payload):
        """The counterpart to the tests above: an empty portfolio dispatches
        successfully and returns a payload."""
        portfolio_payload["positions"] = []
        fake_backend.json("portfolio", portfolio_payload)
        result = await server.mcp.call_tool("get_portfolio_positions", {"user_id": "u_new"})
        payload = result[1] if isinstance(result, tuple) else result
        assert isinstance(payload, dict)


# ==========================================================================
# The __main__ entrypoint
# ==========================================================================
class TestMainEntrypoint:
    def test_main_block_starts_sse_transport(self, mocker):
        """Runs server.py as __main__ with FastMCP replaced, so run() is
        asserted rather than executed. Nothing binds a port."""
        fake_mcp = mocker.MagicMock(name="FastMCP_instance")
        mocker.patch("mcp.server.fastmcp.FastMCP", return_value=fake_mcp)
        runpy.run_path(str(server.__file__), run_name="__main__")
        fake_mcp.run.assert_called_once_with(transport="sse")

    def test_main_block_binds_all_interfaces_and_port_8000(self, mocker):
        factory = mocker.patch("mcp.server.fastmcp.FastMCP")
        runpy.run_path(str(server.__file__), run_name="__main__")
        _, kwargs = factory.call_args
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 8000

    def test_module_is_importable_without_starting_a_server(self):
        reloaded = importlib.reload(server)
        assert reloaded.mcp is not None
