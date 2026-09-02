"""Unit tests for orchestrator.py.

Strategy, per LangGraph testing practice:

* Nodes are invoked directly with a hand-built state. That is far cheaper and
  far more precise than driving the whole graph and inferring what happened.
* Conditional edges are pure functions and are tested as such, one assertion
  per branch, because they encode the routing policy.
* The compiled graph is exercised end to end only to prove the wiring: that
  every node is reachable and that the compliance revision loop terminates.

Neither Groq nor the MCP server is ever contacted. ``patched_llm`` replaces
``get_llm``; ``fake_mcp`` replaces ``get_mcp_client``; and the autouse socket
blocker in conftest turns any missed patch into a loud failure.
"""

from __future__ import annotations

import asyncio
import json
import runpy
import sys

import pytest
from langgraph.graph import END

import agent_trace
import orchestrator
from mcp_client import MCPToolError, MCPUnavailable


# ==========================================================================
# LLM plumbing
# ==========================================================================
class TestGetLLM:
    def test_uses_the_full_model_by_default(self):
        llm = orchestrator.get_llm()
        assert llm.model_name == "llama-3.3-70b-versatile"
        # ChatGroq coerces an exact 0 to 1e-8, because the Groq API rejects
        # literal zero. Determinism is what matters, so approx is correct here.
        assert llm.temperature == pytest.approx(0.0, abs=1e-6)

    def test_uses_the_fast_model_when_requested(self):
        """Specialist planning only emits argument JSON, so it runs on the 8b."""
        assert orchestrator.get_llm(fast=True).model_name == "llama-3.1-8b-instant"

    def test_is_memoised_per_variant(self):
        assert orchestrator.get_llm(False) is orchestrator.get_llm(False)
        assert orchestrator.get_llm(False) is not orchestrator.get_llm(True)

    def test_missing_api_key_raises_a_clear_error(self, monkeypatch):
        """Edge case: the container starts without GROQ_API_KEY. Failing at
        first use with a named error beats an opaque auth 401 later."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        orchestrator.get_llm.cache_clear()
        with pytest.raises(RuntimeError, match="GROQ_API_KEY is not set"):
            orchestrator.get_llm()

    def test_model_names_fall_back_when_env_is_absent(self, monkeypatch):
        monkeypatch.delenv("GROQ_MODEL", raising=False)
        monkeypatch.delenv("GROQ_FAST_MODEL", raising=False)
        orchestrator.get_llm.cache_clear()
        assert orchestrator.get_llm(False).model_name == "llama-3.3-70b-versatile"
        assert orchestrator.get_llm(True).model_name == "llama-3.1-8b-instant"


class TestLLMHelpers:
    @pytest.mark.asyncio
    async def test_llm_text_strips_and_returns_content(self, patched_llm):
        patched_llm.set_response("  cevap  ")
        assert await orchestrator._llm_text("sys", "user") == "cevap"

    @pytest.mark.asyncio
    async def test_llm_text_handles_none_content(self, patched_llm):
        """Edge case: some providers return None rather than an empty string."""
        patched_llm.set_response(None)
        assert await orchestrator._llm_text("sys", "user") == ""

    @pytest.mark.asyncio
    async def test_llm_text_sends_system_then_human(self, patched_llm):
        await orchestrator._llm_text("SYSTEM", "USER")
        messages = patched_llm.calls[0]
        assert messages[0].content == "SYSTEM"
        assert messages[1].content == "USER"

    @pytest.mark.asyncio
    async def test_llm_json_parses_a_clean_object(self, patched_llm):
        patched_llm.set_response('{"tool": "x", "arguments": {"a": 1}}')
        assert await orchestrator._llm_json("sys", "user") == {
            "tool": "x", "arguments": {"a": 1}
        }


class TestParseJSON:
    """Hallucination tolerance.

    Small models wrap JSON in fences, prepend commentary, or emit prose. Every
    one of those must degrade to {} rather than raise, because a raised
    exception inside a node kills the turn while {} lets the node fall back to
    its defaults.
    """

    def test_plain_object(self):
        assert orchestrator._parse_json('{"a": 1}') == {"a": 1}

    def test_object_with_surrounding_prose(self):
        raw = 'Sure! Here is the JSON you asked for:\n{"a": 1}\nHope that helps.'
        assert orchestrator._parse_json(raw) == {"a": 1}

    def test_fenced_json_block(self):
        assert orchestrator._parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fenced_block_without_a_language_tag(self):
        assert orchestrator._parse_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_fence_opened_but_never_closed(self):
        """Truncated generation: the fence opens and the response is cut off."""
        assert orchestrator._parse_json('```json\n{"a": 1}') == {"a": 1}

    def test_uppercase_language_tag(self):
        assert orchestrator._parse_json('```JSON\n{"a": 1}\n```') == {"a": 1}

    def test_nested_objects_use_the_outermost_braces(self):
        raw = '{"outer": {"inner": {"deep": true}}}'
        assert orchestrator._parse_json(raw) == {"outer": {"inner": {"deep": True}}}

    def test_prose_with_no_object_returns_empty(self, caplog):
        with caplog.at_level("WARNING", logger="moneyfast.graph"):
            assert orchestrator._parse_json("I cannot help with that.") == {}
        assert any("no json object" in r.getMessage() for r in caplog.records)

    def test_empty_string_returns_empty(self):
        assert orchestrator._parse_json("") == {}

    def test_closing_brace_before_opening_returns_empty(self):
        """Edge case: rfind lands before find, so the slice would be reversed."""
        assert orchestrator._parse_json("} not really json {") == {}

    def test_malformed_json_returns_empty(self, caplog):
        with caplog.at_level("WARNING", logger="moneyfast.graph"):
            assert orchestrator._parse_json('{"a": 1,,,}') == {}
        assert any("malformed json" in r.getMessage() for r in caplog.records)

    def test_array_wrapping_an_object_yields_the_inner_object(self):
        """Documents real behaviour rather than wished-for behaviour.

        The parser slices between the first { and the last }, so an array of
        one object degrades to that object. That is benign for the specialist
        envelopes, which are single objects, but it would silently drop
        elements two onward if a node ever expected a list. It does not today.
        """
        assert orchestrator._parse_json('[{"a": 1}]') == {"a": 1}

    def test_array_of_scalars_returns_empty(self):
        """No braces at all, so there is nothing to salvage."""
        assert orchestrator._parse_json("[1, 2, 3]") == {}


# ==========================================================================
# router_node
# ==========================================================================
class TestRouterNode:
    @pytest.mark.asyncio
    async def test_happy_path_populates_routing_state(
        self, route_as, base_state, routing_payload
    ):
        route_as(routing_payload)
        out = await orchestrator.router_node(base_state)
        assert out["primary_intent"] == "PORTFOLIO_INQUIRY"
        assert out["target_agent"] == "PORTFOLIO_AGENT"
        assert out["entities"] == {"tickers": ["THYAO"]}
        assert out["tools_used"] == ["classify_and_route_intent"]
        assert out["revision_count"] == 0
        assert out["errors"] == []

    @pytest.mark.asyncio
    async def test_passes_conversation_summary_and_locale(
        self, route_as, fake_mcp, routing_payload
    ):
        route_as(routing_payload)
        state = {
            "user_message": "onu sat",
            "conversation_history": [{"role": "user", "content": "THYAO aldım"}],
            "user_id": "u_1",
            "locale": "tr-TR",
        }
        await orchestrator.router_node(state)
        _, args = fake_mcp.calls[0]
        assert "THYAO aldım" in args["conversation_summary"]
        assert args["locale"] == "tr-TR"
        assert args["user_context_flags"] == {"has_linked_account": True}

    @pytest.mark.asyncio
    async def test_locale_falls_back_to_the_default(self, route_as, fake_mcp, routing_payload):
        route_as(routing_payload)
        await orchestrator.router_node({"user_message": "x", "user_id": "u_1"})
        assert fake_mcp.calls[0][1]["locale"] == orchestrator.DEFAULT_LOCALE

    @pytest.mark.asyncio
    async def test_anonymous_user_is_flagged_as_unlinked(self, route_as, fake_mcp, routing_payload):
        route_as(routing_payload)
        await orchestrator.router_node({"user_message": "x"})
        assert fake_mcp.calls[0][1]["user_context_flags"] == {"has_linked_account": False}

    @pytest.mark.asyncio
    async def test_distress_from_the_prefilter_is_not_overridable(
        self, route_as, base_state, routing_payload, safety_payload
    ):
        """The deterministic pass decides this one and the model is never
        asked. A safety gate that can be talked out of its verdict by the
        model it guards is not a gate."""
        route_as(
            {**routing_payload, "target_agent": "PORTFOLIO_AGENT"},
            safety={
                **safety_payload,
                "target_agent": "HUMAN_HANDOFF",
                "primary_intent": "DISTRESS",
                "safety_flags": ["DISTRESS_SIGNAL"],
                "is_overridable": False,
            },
        )
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "HUMAN_HANDOFF"
        assert out["safety_flags"] == ["DISTRESS_SIGNAL"]

    @pytest.mark.asyncio
    async def test_distress_reported_only_by_the_model_still_routes_to_handoff(
        self, route_as, base_state, routing_payload
    ):
        """Belt and braces: the regex can miss a phrasing the model catches."""
        route_as({
            **routing_payload,
            "target_agent": "PORTFOLIO_AGENT",
            "safety_flags": ["DISTRESS_SIGNAL"],
        })
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "HUMAN_HANDOFF"

    @pytest.mark.asyncio
    async def test_model_cannot_clear_a_prefilter_flag(
        self, route_as, base_state, routing_payload, safety_payload
    ):
        """Flags are a union, never a replacement. A message that talks the
        model into returning safety_flags: [] must not lose the regex verdict."""
        route_as(
            {**routing_payload, "safety_flags": []},
            safety={**safety_payload, "safety_flags": ["PROMPT_INJECTION_SUSPECTED"]},
        )
        out = await orchestrator.router_node(base_state)
        assert "PROMPT_INJECTION_SUSPECTED" in out["safety_flags"]

    @pytest.mark.asyncio
    async def test_model_may_add_a_flag_the_regex_missed(
        self, route_as, base_state, routing_payload
    ):
        route_as({**routing_payload, "safety_flags": ["SOLICITS_ADVICE"]})
        out = await orchestrator.router_node(base_state)
        assert "SOLICITS_ADVICE" in out["safety_flags"]

    @pytest.mark.asyncio
    async def test_hallucinated_agent_falls_back_instead_of_reaching_a_specialist(
        self, route_as, base_state, routing_payload
    ):
        """An invented agent name must not fall through to a real data tool."""
        route_as({**routing_payload, "target_agent": "SUPER_TRADER_AGENT"})
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "EDUCATION_AGENT"

    @pytest.mark.asyncio
    async def test_low_confidence_forces_clarification(
        self, route_as, base_state, routing_payload
    ):
        route_as({**routing_payload, "confidence": 0.42, "needs_clarification": False})
        out = await orchestrator.router_node(base_state)
        assert out["needs_clarification"] is True

    @pytest.mark.asyncio
    async def test_confidence_exactly_at_the_threshold_routes_normally(
        self, route_as, base_state, routing_payload
    ):
        """Boundary: 0.60 is acceptable, only strictly below it is not."""
        route_as({**routing_payload, "confidence": 0.60})
        out = await orchestrator.router_node(base_state)
        assert out["needs_clarification"] is False

    @pytest.mark.asyncio
    async def test_missing_confidence_is_treated_as_zero(
        self, route_as, base_state, routing_payload
    ):
        """Edge case: a malformed classifier reply must not route confidently."""
        payload = {**routing_payload}
        del payload["confidence"]
        route_as(payload)
        out = await orchestrator.router_node(base_state)
        assert out["needs_clarification"] is True

    @pytest.mark.asyncio
    async def test_missing_target_agent_falls_back_to_education(
        self, route_as, base_state, routing_payload
    ):
        payload = {**routing_payload}
        del payload["target_agent"]
        del payload["primary_intent"]
        route_as(payload)
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "EDUCATION_AGENT"
        assert out["primary_intent"] == "OUT_OF_SCOPE"

    @pytest.mark.asyncio
    async def test_prefilter_outage_is_recorded_but_not_fatal(
        self, fake_mcp, patched_llm, base_state, routing_payload
    ):
        """Losing the deterministic pre-filter degrades safety detection to
        whatever the model notices; it does not drop the turn. The failure is
        recorded so it is visible in the turn record rather than silent."""
        import json

        fake_mcp.responses["classify_and_route_intent"] = MCPUnavailable("no route to host")
        patched_llm.set_responses([json.dumps(routing_payload)])
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "PORTFOLIO_AGENT"
        assert any("safety_prefilter" in e for e in out["errors"])

    @pytest.mark.asyncio
    async def test_tool_error_is_handled_like_unavailable(
        self, fake_mcp, patched_llm, base_state, routing_payload
    ):
        import json

        fake_mcp.responses["classify_and_route_intent"] = MCPToolError("prefilter blew up")
        patched_llm.set_responses([json.dumps(routing_payload)])
        out = await orchestrator.router_node(base_state)
        assert any("safety_prefilter" in e for e in out["errors"])

    @pytest.mark.asyncio
    async def test_llm_outage_does_not_route_at_a_data_agent(
        self, route_as, patched_llm, base_state, routing_payload
    ):
        """Groq 429 or a dropped connection. A rate limit must not become a
        portfolio lookup for whoever happens to be asking."""
        route_as(routing_payload)

        async def _boom(_messages):
            raise RuntimeError("groq 429 rate limited")

        patched_llm.ainvoke = _boom
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "EDUCATION_AGENT"
        assert out["primary_intent"] == "OUT_OF_SCOPE"
        assert any("router" in e for e in out["errors"])

    @pytest.mark.asyncio
    async def test_a_flag_raised_by_both_passes_is_not_duplicated(
        self, route_as, base_state, routing_payload, safety_payload
    ):
        """Both layers can spot the same injection attempt. The turn record
        should say so once."""
        route_as(
            {**routing_payload, "safety_flags": ["PROMPT_INJECTION_SUSPECTED"]},
            safety={**safety_payload, "safety_flags": ["PROMPT_INJECTION_SUSPECTED"]},
        )
        out = await orchestrator.router_node(base_state)
        assert out["safety_flags"] == ["PROMPT_INJECTION_SUSPECTED"]

    @pytest.mark.asyncio
    async def test_both_passes_failing_lands_on_education_not_a_data_agent(
        self, fake_mcp, patched_llm, base_state
    ):
        """Worst case: MCP down and the model returns prose. The turn must not
        be routed at a tool that reads someone's holdings."""
        fake_mcp.responses["classify_and_route_intent"] = MCPUnavailable("down")
        patched_llm.set_response("Bir hata oluştu.")
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "EDUCATION_AGENT"
        assert out["primary_intent"] == "OUT_OF_SCOPE"


# ==========================================================================
# Specialist nodes
# ==========================================================================
class TestPortfolioNode:
    @pytest.mark.asyncio
    async def test_happy_path(self, fake_mcp, patched_llm, base_state, positions_payload):
        patched_llm.set_response('{"arguments": {"account_ids": ["acc_1"]}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        out = await orchestrator.portfolio_node(base_state)
        assert out["specialist_output"]["status"] == "OK"
        assert out["specialist_output"]["data"]["positions"]
        assert out["tools_used"] == ["get_portfolio_positions"]

    @pytest.mark.asyncio
    async def test_user_id_is_taken_from_state_not_from_the_llm(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """Security invariant: the model must not be able to choose whose
        portfolio gets read, even if it emits a user_id in its plan."""
        patched_llm.set_response('{"arguments": {"user_id": "u_someone_else"}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        await orchestrator.portfolio_node(base_state)
        assert fake_mcp.calls[0][1]["user_id"] == "u_123"

    @pytest.mark.asyncio
    async def test_anonymous_user_id_defaults_to_unknown(
        self, fake_mcp, patched_llm, positions_payload
    ):
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        await orchestrator.portfolio_node({"user_message": "x"})
        assert fake_mcp.calls[0][1]["user_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_defaults_are_applied_when_the_plan_is_empty(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response("not json at all")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        await orchestrator.portfolio_node(base_state)
        args = fake_mcp.calls[0][1]
        assert args["base_currency"] == "TRY"
        assert args["valuation_mode"] == "LAST_CLOSE"
        assert args["include_closed"] is False

    @pytest.mark.asyncio
    async def test_empty_positions_is_reported_as_empty_not_ok(
        self, fake_mcp, patched_llm, base_state, empty_positions_payload
    ):
        """The distinction the whole data-integrity rule rests on: EMPTY means
        say so, ERROR means say the data failed, and neither may invent rows."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = empty_positions_payload
        out = await orchestrator.portfolio_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_custodian_failure_is_reported_as_error(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = MCPUnavailable("HTTP 500")
        out = await orchestrator.portfolio_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert out["specialist_output"]["data"] is None


class TestPortfolioNewsBranch:
    """İkinci araç: kullanıcının SAHİP OLDUĞU hisselere dair yayımlananlar.

    Kesişim burada, belge aramasında değil: "portföyümdeki hisselerle ilgili
    haber" hiçbir şirket adı içermiyor, dolayısıyla aramanın arayacağı bir şey
    yok -- cevap, tutulanlarla yayımlananların kesişimi.
    """

    NEWS = {"window_days": 90, "holdings": [{"symbol": "AKBNK", "news_count": 1}],
            "articles": [{"id": "n1", "title": "Akbank...", "held_symbols": ["AKBNK"]}]}

    @pytest.mark.asyncio
    async def test_the_plan_can_choose_the_news_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response('{"tool": "get_portfolio_news", "arguments": {}}')
        fake_mcp.responses["get_portfolio_news"] = self.NEWS
        out = await orchestrator.portfolio_node(base_state)
        assert out["tools_used"] == ["get_portfolio_news"]
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_the_user_still_comes_from_state(self, fake_mcp, patched_llm, base_state):
        """Aynı güvenlik değişmezi: model kimin haberlerinin okunacağını
        seçemez."""
        patched_llm.set_response(
            '{"tool": "get_portfolio_news", "arguments": {"user_id": "u_someone_else"}}'
        )
        fake_mcp.responses["get_portfolio_news"] = self.NEWS
        await orchestrator.portfolio_node(base_state)
        assert fake_mcp.calls[0][1]["user_id"] == "u_123"

    @pytest.mark.asyncio
    async def test_no_currency_or_valuation_argument_leaks_into_a_news_call(
        self, fake_mcp, patched_llm, base_state
    ):
        """`base_currency` ve `valuation_mode` pozisyon aracının alanları; bu
        araç onları tanımıyor ve sözleşme fazladan alanı reddediyor."""
        patched_llm.set_response('{"tool": "get_portfolio_news", "arguments": {"limit": 5}}')
        fake_mcp.responses["get_portfolio_news"] = self.NEWS
        await orchestrator.portfolio_node(base_state)
        assert set(fake_mcp.calls[0][1]) == {"user_id", "limit"}

    @pytest.mark.asyncio
    async def test_a_named_period_is_forwarded(self, fake_mcp, patched_llm, base_state):
        patched_llm.set_response(
            '{"tool": "get_portfolio_news", "arguments": {"days": 7}}'
        )
        fake_mcp.responses["get_portfolio_news"] = self.NEWS
        await orchestrator.portfolio_node(base_state)
        assert fake_mcp.calls[0][1]["days"] == 7

    @pytest.mark.asyncio
    async def test_no_matching_article_is_empty_not_an_error(
        self, fake_mcp, patched_llm, base_state
    ):
        """Pencerede hiçbir şey eşleşmemiş olması TAM bir cevap. Hata demek,
        kullanıcıya bir arıza bildirmek olurdu."""
        patched_llm.set_response('{"tool": "get_portfolio_news", "arguments": {}}')
        fake_mcp.responses["get_portfolio_news"] = {
            "window_days": 90, "holdings": [{"symbol": "AKBNK", "news_count": 0}],
            "articles": [],
        }
        out = await orchestrator.portfolio_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_a_holdings_plan_still_reaches_the_positions_tool(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """İki araç tek ajanın arkasında; varsayılan yol değişmedi."""
        patched_llm.set_response('{"tool": "get_portfolio_positions", "arguments": {}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        out = await orchestrator.portfolio_node(base_state)
        assert out["tools_used"] == ["get_portfolio_positions"]


class TestFundamentalsBranch:
    """Üçüncü araç: şirketin İŞİ nasıl gidiyor.

    Fiyat "ne ediyor", eğilim "nasıl gidiyor", bu ise "kârlı mı, borçlu mu".
    Üçü de adı geçen bir enstrüman hakkında ve aynı ajanın arkasında; ayrı bir
    uzman ajan açmak, aynı soruyu yönlendiricide üçe bölmeyi gerektirirdi.

    Bu araç YENİ VERİ GETİRMEDİ: otuz beş alan zaten toplanıyordu ve
    `/market/fundamentals` hepsini veriyordu, ama hiçbir MCP aracı ona
    ulaşmıyordu -- ajanın bir şirket hakkında görebildiği her şey fiyat,
    değişim, hacim ve dört orandan ibaretti.
    """

    PAYLOAD = {
        "instruments": [
            {"symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
             "fundamentals": {"profit_margin": 0.284, "debt_to_equity": None}},
        ],
        "not_found": [], "missing_data": [],
    }

    @pytest.mark.asyncio
    async def test_a_business_question_reaches_the_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"tool": "get_company_fundamentals", "arguments": {"symbols": ["akbnk"]}}'
        )
        fake_mcp.responses["get_company_fundamentals"] = self.PAYLOAD
        out = await orchestrator.market_data_node(base_state)
        assert out["tools_used"] == ["get_company_fundamentals"]
        assert fake_mcp.calls[0][1]["symbols"] == ["AKBNK"]

    @pytest.mark.asyncio
    async def test_the_router_ticker_is_used_when_the_plan_names_none(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response('{"tool": "get_company_fundamentals", "arguments": {}}')
        fake_mcp.responses["get_company_fundamentals"] = self.PAYLOAD
        out = await orchestrator.market_data_node(
            {**base_state, "entities": {"tickers": ["THYAO"]}}
        )
        assert fake_mcp.calls[0][1]["symbols"] == ["THYAO"]
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_more_than_five_symbols_are_trimmed_before_the_call(
        self, fake_mcp, patched_llm, base_state
    ):
        """Sözleşmenin tavanı beş ve aşıldığında REDDEDİYOR. Turu bir 422'ye
        çevirmek, kullanıcıya kendi sorusunun cevabı yerine hata göstermek
        olurdu."""
        patched_llm.set_response(json.dumps({
            "tool": "get_company_fundamentals",
            "arguments": {"symbols": ["A", "B", "C", "D", "E", "F", "G"]},
        }))
        fake_mcp.responses["get_company_fundamentals"] = self.PAYLOAD
        await orchestrator.market_data_node(base_state)
        assert len(fake_mcp.calls[0][1]["symbols"]) == 5

    @pytest.mark.asyncio
    async def test_blank_symbols_do_not_reach_the_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"tool": "get_company_fundamentals", "arguments": {"symbols": ["", "  ", "AKBNK"]}}'
        )
        fake_mcp.responses["get_company_fundamentals"] = self.PAYLOAD
        await orchestrator.market_data_node(base_state)
        assert fake_mcp.calls[0][1]["symbols"] == ["AKBNK"]

    @pytest.mark.asyncio
    async def test_no_symbol_anywhere_falls_through_to_the_price_path(
        self, fake_mcp, patched_llm, base_state
    ):
        """Tek sembol isteyen bir aracı boşa çağırmaktansa, adı geçen ne
        varsa onunla cevaplamak."""
        patched_llm.set_response('{"tool": "get_company_fundamentals", "arguments": {}}')
        fake_mcp.responses["get_market_data"] = {"instruments": [{"symbol": "THYAO"}]}
        out = await orchestrator.market_data_node({**base_state, "entities": {}})
        assert out["tools_used"] == ["get_market_data"]

    @pytest.mark.asyncio
    async def test_nothing_found_is_empty_not_an_error(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"tool": "get_company_fundamentals", "arguments": {"symbols": ["YOKBU"]}}'
        )
        fake_mcp.responses["get_company_fundamentals"] = {
            "instruments": [], "not_found": ["YOKBU"], "missing_data": [],
        }
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"


class TestCashFlowBranch:
    """Üçüncü araç: neye sahip olduğu değil, ne kazanıp ne harcadığı.

    Köprü bu ajanda kuruluyor -- "bunu kaldırabilir miyim" hem pozisyonları
    hem aylık artanı gerektiriyor ve iki ayrı ajan bunu tek turda
    birleştiremez.
    """

    PAYLOAD = {
        "has_data": True, "period_days": 90, "months_observed": 3.0,
        "currency_code": "TRY", "income_total": 112406.75, "income_events": 4,
        "expense_total": 67452.46, "net_total": 44954.29,
        "monthly_income": 37468.92, "monthly_expense": 22484.15,
        "monthly_net": 14984.76,
        "categories": [{"category": "Kira", "amount": 28000.0,
                        "monthly_amount": 9333.33, "share_percent": 41.5}],
        "first_transaction_at": None, "last_transaction_at": None,
    }

    @pytest.mark.asyncio
    async def test_a_budget_question_reaches_the_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"tool": "get_cash_flow_summary", "arguments": {}}'
        )
        fake_mcp.responses["get_cash_flow_summary"] = self.PAYLOAD
        out = await orchestrator.portfolio_node(base_state)
        assert out["tools_used"] == ["get_cash_flow_summary"]
        assert fake_mcp.calls[0][1]["user_id"] == base_state["user_id"]

    @pytest.mark.asyncio
    async def test_a_named_window_is_forwarded(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"tool": "get_cash_flow_summary", "arguments": {"days": 180}}'
        )
        fake_mcp.responses["get_cash_flow_summary"] = self.PAYLOAD
        await orchestrator.portfolio_node(base_state)
        assert fake_mcp.calls[0][1]["days"] == 180

    @pytest.mark.asyncio
    async def test_the_reporting_currency_is_not_forced_onto_this_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        """`base_currency` ve `valuation_mode` pozisyon aracının alanları.
        Bu araç onları tanımıyor ve gönderilirse sözleşme dışı bir çağrı
        olurdu."""
        patched_llm.set_response('{"tool": "get_cash_flow_summary", "arguments": {}}')
        fake_mcp.responses["get_cash_flow_summary"] = self.PAYLOAD
        await orchestrator.portfolio_node(base_state)
        assert set(fake_mcp.calls[0][1]) <= {"user_id", "days"}

    @pytest.mark.asyncio
    async def test_no_banking_record_is_an_answer_not_an_empty_result(
        self, fake_mcp, patched_llm, base_state
    ):
        """Ölçüldü: 23 kullanıcının 3'ünde bankacılık hareketi var. EMPTY
        sayılırsa ajan "veriye ulaşamadım" der; oysa söylenecek şey sistemde
        bu kişiye ait kayıt olmadığı."""
        patched_llm.set_response('{"tool": "get_cash_flow_summary", "arguments": {}}')
        fake_mcp.responses["get_cash_flow_summary"] = {
            **self.PAYLOAD, "has_data": False, "income_total": None,
            "expense_total": None, "net_total": None, "monthly_net": None,
            "income_events": 0, "categories": [],
        }
        out = await orchestrator.portfolio_node(base_state)
        assert out["specialist_output"]["status"] == "OK"


class TestQuarterlyBranch:
    """Dördüncü araç: adı konmuş bir ÇEYREK.

    Diğer üçünün hiçbirinde seri yok -- fiyat anlık, eğilim türetilmiş, temel
    veri anlık görüntü. "Son çeyrek kârı" sorusunu cevaplayabilen tek yol bu,
    ve dokümandaki örnek senaryonun eksik yarısı tam olarak buydu.
    """

    PAYLOAD = {
        "symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
        "periods": [
            {"period_end": "2026-06-30", "label": "2026Q2", "net_income": 15_198_000_000},
            {"period_end": "2026-03-31", "label": "2026Q1", "net_income": 14_100_000_000},
        ],
        "previous_is_adjacent": True, "year_ago_available": True,
    }

    @pytest.mark.asyncio
    async def test_a_quarter_question_reaches_the_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"tool": "get_quarterly_financials", "arguments": {"symbol": "akbnk"}}'
        )
        fake_mcp.responses["get_quarterly_financials"] = self.PAYLOAD
        out = await orchestrator.market_data_node(base_state)
        assert out["tools_used"] == ["get_quarterly_financials"]
        assert fake_mcp.calls[0][1]["symbol"] == "AKBNK"

    @pytest.mark.asyncio
    async def test_the_router_ticker_is_used_when_the_plan_names_none(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response('{"tool": "get_quarterly_financials", "arguments": {}}')
        fake_mcp.responses["get_quarterly_financials"] = self.PAYLOAD
        await orchestrator.market_data_node(
            {**base_state, "entities": {"tickers": ["THYAO"]}}
        )
        assert fake_mcp.calls[0][1]["symbol"] == "THYAO"

    @pytest.mark.asyncio
    async def test_an_empty_series_is_empty_not_an_error(
        self, fake_mcp, patched_llm, base_state
    ):
        """Ölçüldü: 40 hissenin 6'sında hiç çeyreklik veri yok. Hata değil."""
        patched_llm.set_response(
            '{"tool": "get_quarterly_financials", "arguments": {"symbol": "YENI"}}'
        )
        fake_mcp.responses["get_quarterly_financials"] = {
            "symbol": "YENI", "name": "Yeni", "currency": "TRY", "periods": [],
            "previous_is_adjacent": False, "year_ago_available": False,
        }
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_no_symbol_anywhere_falls_through_to_the_price_path(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response('{"tool": "get_quarterly_financials", "arguments": {}}')
        fake_mcp.responses["get_market_data"] = {"instruments": [{"symbol": "THYAO"}]}
        out = await orchestrator.market_data_node({**base_state, "entities": {}})
        assert out["tools_used"] == ["get_market_data"]


class TestMarketResearchNode:
    @pytest.mark.asyncio
    async def test_happy_path(self, fake_mcp, patched_llm, base_state):
        patched_llm.set_response('{"arguments": {"query": "THY 2Ç26", "top_k": 3}}')
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}
        out = await orchestrator.market_research_node(base_state)
        assert out["specialist_output"]["status"] == "OK"
        assert fake_mcp.calls[0][1]["top_k"] == 3

    @pytest.mark.asyncio
    async def test_query_falls_back_to_the_raw_user_message(
        self, fake_mcp, patched_llm, base_state
    ):
        """Contract: the retriever resolves coreference, so passing the user's
        own phrasing through is correct rather than lazy."""
        patched_llm.set_response("{}")
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}
        await orchestrator.market_research_node(base_state)
        args = fake_mcp.calls[0][1]
        assert args["query"] == base_state["user_message"]
        assert args["top_k"] == 8
        assert args["min_similarity"] == 0.45

    @pytest.mark.asyncio
    async def test_only_the_context_window_is_sent_as_context(
        self, fake_mcp, patched_llm
    ):
        """The retriever folds in the newest user turn it finds, so this bound
        is about payload size rather than about what gets resolved."""
        patched_llm.set_response("{}")
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [1]}
        history = [
            {"role": "user", "content": f"turn {i}"}
            for i in range(orchestrator.HISTORY_MAX_TURNS + 10)
        ]
        await orchestrator.market_research_node(
            {"user_message": "x", "conversation_history": history}
        )
        assert (
            len(fake_mcp.calls[0][1]["conversation_context"])
            == orchestrator.HISTORY_MAX_TURNS
        )

    @pytest.mark.asyncio
    async def test_missing_history_sends_an_empty_context(self, fake_mcp, patched_llm):
        patched_llm.set_response("{}")
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [1]}
        await orchestrator.market_research_node({"user_message": "x"})
        assert fake_mcp.calls[0][1]["conversation_context"] == []

    @pytest.mark.asyncio
    async def test_no_results_is_reported_as_empty(self, fake_mcp, patched_llm, base_state):
        patched_llm.set_response("{}")
        fake_mcp.responses["rag_semantic_market_search"] = {"results": []}
        out = await orchestrator.market_research_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_vector_store_failure_is_reported_as_error(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response("{}")
        fake_mcp.responses["rag_semantic_market_search"] = MCPUnavailable("index down")
        out = await orchestrator.market_research_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"


class TestRiskNode:
    POSTURE = {
        "base_currency": "TRY",
        "positions": [{"symbol": "THYAO", "trend": "DOWNTREND"}],
        "summary": {"below_sma_50": 2, "above_sma_50": 1,
                    "weight_below_sma_50": 0.951,
                    "statement": "3 pozisyonunuzun 2'si 50 günlük ortalamasının altında."},
        "unconvertible": [],
    }

    SCENARIO = {
        "factor": "USDTRY", "factor_name": "Dolar/TL", "shock_pct": 10.0,
        "sensitivity": {"beta": -0.68, "r_squared": 0.001, "observation_count": 222},
        "estimated_impact_pct": -6.8,
        "statement": "Dolar/TL %10,0 yükselseydi ... — ancak geçmiş fiyat "
                     "hareketi geleceği belirlemez.",
        "assumptions": ["Etki doğrusal varsayıldı."], "warnings": [],
    }

    @pytest.mark.asyncio
    async def test_a_factor_question_reaches_the_scenario_tool(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response(
            '{"tool": "run_portfolio_scenario", '
            '"arguments": {"factor": "usdtry", "shock_pct": 10, "lookback": "1Y"}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["run_portfolio_scenario"] = self.SCENARIO
        out = await orchestrator.risk_node(base_state)
        assert out["tools_used"] == ["run_portfolio_scenario"]
        assert fake_mcp.calls[-1][1]["factor"] == "USDTRY"
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_an_unmeasurable_factor_turn_never_reaches_a_plan(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """ÖLÇÜLDÜ: reddi yalnızca senaryo dalına bağlamak yetmedi. Model
        bunun yerine `get_portfolio_stress_test`'i seçti, araç düzgün çalıştı,
        ve model döviz ile altın replaylerini FAİZ İÇİN VEKİL kullanıp "faiz
        artışıyla ilişkili olası TL güçlenmesi..." diye bir okuma kurdu. Araç
        sözleşmesi bunu yasaklıyordu ve yasak tutmadı."""
        patched_llm.set_response(
            '{"tool": "get_portfolio_stress_test", "arguments": {}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_portfolio_stress_test"] = {
            "worst_days": [{"date": "2026-03-01", "return_pct": -7.5}],
            "replays": {"USDTRY": {"factor_move_pct": 0.89}},
        }
        out = await orchestrator.risk_node(
            {**base_state, "user_message": "faizler artarsa portföyüm nasıl etkilenir"}
        )
        assert out["specialist_output"]["status"] == "UNSUPPORTED"
        assert out["specialist_output"]["data"] is None
        # Stres testi HİÇ çağrılmadı: çağrılsaydı verisi modele ulaşırdı.
        assert "get_portfolio_stress_test" not in [n for n, _ in fake_mcp.calls]

    @pytest.mark.asyncio
    async def test_an_ordinary_risk_question_is_not_short_circuited(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """"Portföyüm ne kadar riskli" bir faktör sorusu değil; kesilseydi
        çalışan bir yol kaybolurdu."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(
            {**base_state, "user_message": "portföyüm ne kadar riskli"}
        )
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_an_unmeasurable_factor_is_refused_before_the_call(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """En sık geleni FAİZ ve sistemde faiz serisi yok. Bir döviz
        faktörünü vekil koymak, ölçülmemiş bir sayıyı ölçüm diye vermek
        olurdu -- o yüzden çağrı hiç yapılmıyor."""
        patched_llm.set_response(
            '{"tool": "run_portfolio_scenario", "arguments": {"factor": "FAIZ"}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "UNSUPPORTED"
        assert [name for name, _ in fake_mcp.calls] == ["get_portfolio_positions"]

    def test_the_limit_is_not_described_as_an_outage(self):
        """ÖLÇÜLDÜ: aynı durum iki kez "veriler şu anda alınamadı, tekrar
        denememi ister misiniz" diye anlatıldı. Tekrar denemek hiçbir zaman
        işe yaramayacak ve öyle demek olmayan bir umut vermek."""
        text = orchestrator.UNSUPPORTED_FACTOR_TR
        assert "şu anda" not in text
        assert "tekrar" not in text
        assert "geçici bir sorun değil" in text

    def test_the_limit_names_what_can_be_measured_instead(self):
        assert "Dolar/TL" in orchestrator.UNSUPPORTED_FACTOR_TR
        assert "BIST 100" in orchestrator.UNSUPPORTED_FACTOR_TR

    def test_the_limit_uses_names_not_symbols(self):
        """Sembol kullanıcıya sızmaz; `prompts.py`'deki NAMING kuralı."""
        for symbol in orchestrator.SCENARIO_FACTORS:
            assert symbol not in orchestrator.UNSUPPORTED_FACTOR_TR

    @pytest.mark.asyncio
    async def test_a_missing_factor_is_refused_the_same_way(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response('{"tool": "run_portfolio_scenario", "arguments": {}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "UNSUPPORTED"
        assert out["specialist_output"]["user_message_tr"] == \
            orchestrator.UNSUPPORTED_FACTOR_TR

    @pytest.mark.asyncio
    async def test_an_unnamed_shock_size_defaults_and_is_declared(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response(
            '{"tool": "run_portfolio_scenario", "arguments": {"factor": "XU100"}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["run_portfolio_scenario"] = self.SCENARIO
        await orchestrator.risk_node(base_state)
        assert fake_mcp.calls[-1][1]["shock_pct"] == 10.0

    @pytest.mark.asyncio
    async def test_a_stress_question_reaches_the_stress_tool(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response('{"tool": "get_portfolio_stress_test", "arguments": {}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_portfolio_stress_test"] = {
            "worst_days": [{"date": "2026-03-01", "return_pct": -7.5}], "replays": {},
        }
        out = await orchestrator.risk_node(base_state)
        assert out["tools_used"] == ["get_portfolio_stress_test"]
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_a_stress_test_with_nothing_measured_is_empty(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response('{"tool": "get_portfolio_stress_test", "arguments": {}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_portfolio_stress_test"] = {"worst_days": [], "replays": {}}
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_a_trade_question_reaches_the_simulation(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response(
            '{"tool": "simulate_position_change", "arguments": {"changes": '
            '[{"symbol": "thyao", "quantity_delta": 100}]}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["simulate_position_change"] = {
            "current": {"score": 35.5}, "hypothetical": {"score": 26.8},
        }
        out = await orchestrator.risk_node(base_state)
        assert fake_mcp.calls[-1][1]["changes"] == [
            {"symbol": "THYAO", "quantity_delta": 100.0}
        ]
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_a_simulation_without_a_change_asks_rather_than_inventing_one(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """Değişikliği SUNUCU ÖNERMEZ. Kendi kendine bir miktar uydurmak, bir
        öneri motoruna dönüşmenin ilk adımı olurdu."""
        patched_llm.set_response(
            '{"tool": "simulate_position_change", "arguments": {"changes": []}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert out["specialist_output"]["missing_fields"] == ["changes"]
        assert [name for name, _ in fake_mcp.calls] == ["get_portfolio_positions"]

    @pytest.mark.asyncio
    async def test_a_malformed_change_row_is_dropped_not_guessed(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response(
            '{"tool": "simulate_position_change", "arguments": {"changes": '
            '["THYAO", {"symbol": "AKBNK"}, {"quantity_delta": 5}, '
            '{"symbol": "DOAS", "quantity_delta": -3}]}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["simulate_position_change"] = {
            "current": {"score": 1}, "hypothetical": {"score": 2},
        }
        await orchestrator.risk_node(base_state)
        assert fake_mcp.calls[-1][1]["changes"] == [
            {"symbol": "DOAS", "quantity_delta": -3.0}
        ]

    @pytest.mark.asyncio
    async def test_at_most_ten_changes_are_forwarded(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """Sözleşmenin sınırı on; on birinciyi göndermek 422 döndürürdü."""
        rows = [{"symbol": f"S{i}", "quantity_delta": 1} for i in range(15)]
        patched_llm.set_response(json.dumps(
            {"tool": "simulate_position_change", "arguments": {"changes": rows}}
        ))
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["simulate_position_change"] = {
            "current": {"score": 1}, "hypothetical": {"score": 2},
        }
        await orchestrator.risk_node(base_state)
        assert len(fake_mcp.calls[-1][1]["changes"]) == 10

    @pytest.mark.asyncio
    async def test_an_empty_portfolio_short_circuits_before_any_what_if(
        self, fake_mcp, patched_llm, base_state, empty_positions_payload
    ):
        """Ölçülecek pozisyon yoksa senaryo da yok; üç dal da bu kapının
        arkasında."""
        patched_llm.set_response(
            '{"tool": "run_portfolio_scenario", "arguments": {"factor": "XU100"}}'
        )
        fake_mcp.responses["get_portfolio_positions"] = empty_positions_payload
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_the_technical_posture_travels_inside_the_metrics_payload(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """Kardeş anahtar değil, `data`'nın içinde: synthesis `data`'yı
        okuyor ve yanına konan bir anahtarı her tüketicinin ayrıca öğrenmesi
        gerekirdi."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_portfolio_technicals"] = self.POSTURE
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(base_state)
        data = out["specialist_output"]["data"]
        assert data["technical_posture"]["summary"]["weight_below_sma_50"] == 0.951
        assert "get_portfolio_technicals" in out["tools_used"]

    @pytest.mark.asyncio
    async def test_a_missing_posture_costs_the_turn_nothing_else(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """Best-effort: teknik görünüm turu zenginleştirir, ayakta tutmaz.
        Onun yüzünden turu düşürmek, kısmi bir cevabı hiç cevaba çevirirdi."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_portfolio_technicals"] = MCPUnavailable("down")
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "OK"
        assert "technical_posture" not in out["specialist_output"]["data"]
        assert "get_portfolio_technicals" not in out["tools_used"]

    @pytest.mark.asyncio
    async def test_fetches_positions_before_computing_metrics(
        self, fake_mcp, patched_llm, base_state, positions_payload, risk_summary_payload
    ):
        """The risk tool has no position access by design, so the graph makes
        four calls in a fixed order: holdings, the profile summary, the
        technical posture, then the statistics. The middle two are
        best-effort; only the first and the last can fail the turn."""
        patched_llm.set_response('{"arguments": {"lookback": "3Y"}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_risk_profile_summary"] = risk_summary_payload
        fake_mcp.responses["get_portfolio_technicals"] = self.POSTURE
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(base_state)
        assert [name for name, _ in fake_mcp.calls] == [
            "get_portfolio_positions",
            "get_risk_profile_summary",
            "get_portfolio_technicals",
            "calculate_portfolio_risk_metrics",
        ]
        assert out["tools_used"] == [
            "get_portfolio_positions",
            "calculate_portfolio_risk_metrics",
            "get_portfolio_technicals",
            "get_risk_profile_summary",
        ]
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_positions_are_passed_into_the_risk_tool(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {}}
        await orchestrator.risk_node(base_state)
        risk_args = dict(fake_mcp.calls)["calculate_portfolio_risk_metrics"]
        assert risk_args["positions"] == positions_payload["positions"]
        assert risk_args["lookback"] == "1Y"
        assert risk_args["confidence_level"] == 0.95
        assert risk_args["rebalance_assumption"] == "BUY_AND_HOLD"


class TestRiskProfileSummary:
    """The score and the band exist only behind the summary tool.

    Without it the assistant answered "portföyüm ne kadar riskli" with an
    annualised volatility percentage while the risk page answered "83 puan,
    Düşük" for the same portfolio. One system, one question, two answers, and
    no way for the user to tell which was the answer.
    """

    @pytest.mark.asyncio
    async def test_the_summary_rides_along_with_the_metrics(
        self, fake_mcp, patched_llm, base_state, positions_payload, risk_summary_payload
    ):
        """Inside `data`, not beside it: synthesis reads `data`, and a sibling
        key would need every consumer to learn about it."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_risk_profile_summary"] = risk_summary_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(base_state)
        data = out["specialist_output"]["data"]
        assert data["metrics"] == {"beta": 1.1}
        assert data["profile_summary"]["score"] == 83.4
        assert data["profile_summary"]["suitability"]["alignment"] == "PORTFOLIO_CALMER"

    @pytest.mark.asyncio
    async def test_it_asks_for_the_same_window_as_the_metrics(
        self, fake_mcp, patched_llm, base_state, positions_payload, risk_summary_payload
    ):
        """A score measured over 1Y beside statistics measured over 3Y would
        be two answers about two different portfolios-in-time."""
        patched_llm.set_response('{"arguments": {"lookback": "3Y"}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_risk_profile_summary"] = risk_summary_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {}}
        await orchestrator.risk_node(base_state)
        summary_args = dict(fake_mcp.calls)["get_risk_profile_summary"]
        assert summary_args["lookback"] == "3Y"
        assert summary_args["user_id"] == base_state["user_id"]

    @pytest.mark.asyncio
    async def test_a_failed_summary_does_not_cost_the_turn_its_statistics(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """Best-effort on purpose. Failing the whole turn over the summary
        would trade a partial answer for none."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_risk_profile_summary"] = MCPUnavailable("profile down")
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "OK"
        assert "profile_summary" not in out["specialist_output"]["data"]
        assert "get_risk_profile_summary" not in out["tools_used"]

    @pytest.mark.asyncio
    async def test_an_empty_summary_is_not_attached(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """An empty block would give the model a score-shaped hole to narrate.
        Absent says "no score this turn", which is the truth."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_risk_profile_summary"] = {}
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {}}
        out = await orchestrator.risk_node(base_state)
        assert "profile_summary" not in out["specialist_output"]["data"]

    @pytest.mark.asyncio
    async def test_a_rejected_argument_gets_one_correction_attempt(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """The market-data node has had this since a bad enum became
        "Verilere ulaşamadım"; the risk node reproduced the same failure with
        a lookback of "365"."""
        patched_llm.set_responses([
            '{"arguments": {"lookback": "son 3 ay"}}',
            '{"arguments": {"lookback": "3M"}}',
        ])
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = [
            MCPToolError("lookback 'son 3 ay' is not one of 1M, 3M, 6M, 1Y."),
            {"metrics": {"beta": 1.1}},
        ]
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_a_failed_metric_call_still_reports_the_error(
        self, fake_mcp, patched_llm, base_state, positions_payload, risk_summary_payload
    ):
        """The summary cannot rescue a turn whose statistics failed: `data` is
        None on the error path and there is nowhere honest to put it."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_risk_profile_summary"] = risk_summary_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = MCPToolError("no history")
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert out["specialist_output"]["data"] is None

    @pytest.mark.asyncio
    async def test_an_empty_portfolio_never_asks_for_a_score(
        self, fake_mcp, patched_llm, base_state, empty_positions_payload
    ):
        """Nothing to measure means nothing to score."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = empty_positions_payload
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"
        assert [name for name, _ in fake_mcp.calls] == ["get_portfolio_positions"]

    @pytest.mark.asyncio
    async def test_empty_portfolio_short_circuits_before_the_risk_call(
        self, fake_mcp, patched_llm, base_state, empty_positions_payload
    ):
        """Nothing to measure. Calling the risk tool with [] would waste a
        round trip and invite a divide-by-zero downstream."""
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = empty_positions_payload
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"
        assert [name for name, _ in fake_mcp.calls] == ["get_portfolio_positions"]

    @pytest.mark.asyncio
    async def test_custodian_failure_stops_before_the_risk_call(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["get_portfolio_positions"] = MCPUnavailable("custodian down")
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert len(fake_mcp.calls) == 1

    @pytest.mark.asyncio
    async def test_risk_tool_failure_is_reported_as_error(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = MCPToolError("no history")
        out = await orchestrator.risk_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"


class TestTransactionNode:
    @pytest.mark.asyncio
    async def test_stages_a_complete_request(
        self, fake_mcp, patched_llm, base_state, proposal_payload
    ):
        patched_llm.set_response(json.dumps({
            "status": "READY",
            "arguments": {
                "transaction_type": "BUY",
                "source_account_id": "acc_998877",
                "instrument": {"symbol": "THYAO", "exchange": "XIST"},
                "quantity": 100.0,
            },
            "assumptions": ["Market order assumed."],
        }))
        fake_mcp.responses["prepare_transaction_proposal"] = proposal_payload
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "OK"
        args = fake_mcp.calls[0][1]
        assert args["user_id"] == "u_123"
        assert args["idempotency_key"].startswith("idem_")
        assert args["assumptions"] == ["Market order assumed."]

    @pytest.mark.asyncio
    async def test_needs_input_never_reaches_the_tool(self, fake_mcp, patched_llm, base_state):
        """A missing mandatory value is a question, never a value to invent."""
        patched_llm.set_response(json.dumps({
            "status": "NEEDS_INPUT",
            "missing_fields": ["quantity"],
            "clarification_request": "How many lots?",
        }))
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert out["specialist_output"]["missing_fields"] == ["quantity"]
        assert fake_mcp.calls == []

    @pytest.mark.asyncio
    async def test_missing_arguments_block_is_treated_as_needs_input(
        self, fake_mcp, patched_llm, base_state
    ):
        """Hallucinated reply with status READY but no arguments. Staging on
        that would mean inventing every field."""
        patched_llm.set_response('{"status": "READY"}')
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert fake_mcp.calls == []

    @pytest.mark.asyncio
    async def test_unparseable_plan_is_treated_as_needs_input(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response("I'd be happy to help you buy some shares!")
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert out["specialist_output"]["missing_fields"] == ["unspecified"]
        assert out["specialist_output"]["clarification_request"]

    @pytest.mark.asyncio
    async def test_idempotency_key_is_stable_for_the_same_turn(
        self, fake_mcp, patched_llm, base_state, proposal_payload
    ):
        """Same user, same message, same history length: one proposal, not two."""
        plan = '{"status": "READY", "arguments": {"transaction_type": "BUY"}}'
        patched_llm.set_responses([plan, plan])
        fake_mcp.responses["prepare_transaction_proposal"] = proposal_payload
        await orchestrator.transaction_node(base_state)
        await orchestrator.transaction_node(base_state)
        assert fake_mcp.calls[0][1]["idempotency_key"] == fake_mcp.calls[1][1]["idempotency_key"]

    @pytest.mark.asyncio
    async def test_idempotency_key_differs_across_turns(
        self, fake_mcp, patched_llm, proposal_payload
    ):
        plan = '{"status": "READY", "arguments": {"transaction_type": "BUY"}}'
        patched_llm.set_responses([plan, plan])
        fake_mcp.responses["prepare_transaction_proposal"] = proposal_payload
        await orchestrator.transaction_node({"user_message": "100 lot al", "user_id": "u_1"})
        await orchestrator.transaction_node({"user_message": "200 lot al", "user_id": "u_1"})
        assert fake_mcp.calls[0][1]["idempotency_key"] != fake_mcp.calls[1][1]["idempotency_key"]

    @pytest.mark.asyncio
    async def test_confirmation_required_false_is_treated_as_a_system_fault(
        self, fake_mcp, patched_llm, base_state, proposal_payload, caplog
    ):
        """The single most important assertion in this file.

        If the staging service ever returns confirmation_required=False, the
        graph must refuse to present the proposal at all rather than render
        something the user could mistake for a completed order.
        """
        patched_llm.set_response('{"status": "READY", "arguments": {"transaction_type": "BUY"}}')
        fake_mcp.responses["prepare_transaction_proposal"] = {
            **proposal_payload, "confirmation_required": False
        }
        with caplog.at_level("ERROR", logger="moneyfast.graph"):
            out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert any("confirmation_required" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_staging_failure_is_reported_as_error(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response('{"status": "READY", "arguments": {"transaction_type": "BUY"}}')
        fake_mcp.responses["prepare_transaction_proposal"] = MCPUnavailable("staging down")
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"

    @pytest.mark.asyncio
    async def test_empty_payload_skips_the_confirmation_check(
        self, fake_mcp, patched_llm, base_state
    ):
        """Edge case: an empty dict has no confirmation_required key, and the
        guard must not misread that as False."""
        patched_llm.set_response('{"status": "READY", "arguments": {"transaction_type": "BUY"}}')
        fake_mcp.responses["prepare_transaction_proposal"] = {}
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "OK"


class TestHandoffNode:
    @pytest.mark.asyncio
    async def test_returns_an_instruction_and_calls_no_tool(self, fake_mcp, base_state):
        """`DISTRESS_SIGNAL` alone says a turn is in trouble, not WHICH
        trouble -- so it lands on the generic branch, not the budgeting one.
        """
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["DISTRESS_SIGNAL"]}
        )
        payload = out["specialist_output"]
        assert payload["status"] == "HANDOFF"
        assert payload["safety_flags"] == ["DISTRESS_SIGNAL"]
        assert payload["handoff_category"] == "GENERIC_DISTRESS"
        assert "Do NOT assume the problem is financial" in payload["instruction"]
        assert fake_mcp.calls == []

    @pytest.mark.asyncio
    async def test_missing_safety_flags_defaults_to_empty(self, fake_mcp, base_state):
        out = await orchestrator.handoff_node(base_state)
        assert out["specialist_output"]["safety_flags"] == []

    @pytest.mark.asyncio
    async def test_self_harm_gets_crisis_resources_and_no_money_talk(
        self, fake_mcp, base_state
    ):
        """The log's worst turn: "ölmek istiyorum" was answered with a lecture
        on how borrowed money raises risk, because one instruction served both
        categories."""
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["DISTRESS_SIGNAL", "SELF_HARM_RISK"]}
        )
        assert out["crisis_notices"] == [orchestrator.CRISIS_RESOURCES_TR]
        instruction = out["specialist_output"]["instruction"]
        assert out["specialist_output"]["handoff_category"] == "SELF_HARM_RISK"
        assert "not a financial turn" in instruction
        for banned in ("budgeting", "portfolios", "debt"):
            assert banned in instruction  # named only to be forbidden
        assert "Do NOT offer to connect" in instruction

    @pytest.mark.asyncio
    async def test_coercion_points_at_law_enforcement_not_a_budget(
        self, fake_mcp, base_state
    ):
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["DISTRESS_SIGNAL", "COERCION_RISK"]}
        )
        assert out["crisis_notices"] == [orchestrator.COERCION_RESOURCES_TR]
        assert "155" in orchestrator.COERCION_RESOURCES_TR
        assert out["specialist_output"]["handoff_category"] == "COERCION_RISK"

    @pytest.mark.asyncio
    async def test_financial_distress_keeps_the_budgeting_answer(
        self, fake_mcp, base_state
    ):
        """Unchanged behaviour for the case the original instruction was
        actually written for -- and no crisis line, which would be noise."""
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["DISTRESS_SIGNAL", "FINANCIAL_DISTRESS"]}
        )
        assert out["crisis_notices"] == []
        assert "Do not screen" in out["specialist_output"]["instruction"]

    @pytest.mark.asyncio
    async def test_a_suicide_statement_the_regex_missed_is_still_not_budgeting(
        self, fake_mcp, base_state
    ):
        """Measured, 31 Aug: "ok i get it i am jumping off a cliff".

        The regex held `jump off`, which does not match "jumping off", so the
        only signal was the router model's -- and it spells the flag
        `SELF_HARM`, one character class from the canonical name. The exact
        match in `handoff_node` missed it, the `else` branch was
        FINANCIAL_DISTRESS, and the user was told that borrowed money raises
        risk, with no crisis line.
        """
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["SELF_HARM"], "primary_intent": "SELF_HARM"}
        )
        assert out["specialist_output"]["handoff_category"] == "SELF_HARM_RISK"
        assert out["crisis_notices"] == [orchestrator.CRISIS_RESOURCES_TR]
        assert "Do not screen" not in out["specialist_output"]["instruction"]

    @pytest.mark.asyncio
    async def test_the_intent_alone_is_enough(self, fake_mcp, base_state):
        """In that turn `primary_intent` was already SELF_HARM and nothing
        read it."""
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": [], "primary_intent": "SUICIDE"}
        )
        assert out["specialist_output"]["handoff_category"] == "SELF_HARM_RISK"

    @pytest.mark.asyncio
    async def test_a_disclosed_condition_is_not_a_budgeting_problem(
        self, fake_mcp, base_state
    ):
        """Measured, 31 Aug: "ben şizofrenim" was answered with the
        borrowed-money lecture, because no category existed for it and
        FINANCIAL_DISTRESS was the fallback."""
        out = await orchestrator.handoff_node(
            {
                **base_state,
                "safety_flags": ["DISTRESS_SIGNAL"],
                "primary_intent": "MENTAL_HEALTH",
            }
        )
        payload = out["specialist_output"]
        assert payload["handoff_category"] == "MENTAL_HEALTH_DISCLOSURE"
        assert out["crisis_notices"] == [orchestrator.CRISIS_RESOURCES_TR]
        assert "Do not screen" not in payload["instruction"]
        assert "Do NOT diagnose" in payload["instruction"]

    @pytest.mark.asyncio
    async def test_the_worst_signal_wins(self, fake_mcp, base_state):
        out = await orchestrator.handoff_node(
            {
                **base_state,
                "safety_flags": ["FINANCIAL_DISTRESS", "MENTAL_HEALTH", "SUICIDAL"],
            }
        )
        assert out["specialist_output"]["handoff_category"] == "SELF_HARM_RISK"

    @pytest.mark.asyncio
    async def test_an_unknown_flag_never_reaches_the_budgeting_answer(
        self, fake_mcp, base_state
    ):
        """The whole point of the fallback change: a name nobody anticipated
        must not select a content category."""
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["DISTRESS_SIGNAL", "SOMETHING_NEW"]}
        )
        assert out["specialist_output"]["handoff_category"] == "GENERIC_DISTRESS"
        assert out["crisis_notices"] == [orchestrator.CRISIS_RESOURCES_TR]

    @pytest.mark.asyncio
    async def test_an_unknown_flag_is_carried_not_dropped(self, fake_mcp, base_state):
        """It cannot pick the category, but it stays visible in the trace."""
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["DISTRESS_SIGNAL", "SOMETHING_NEW"]}
        )
        assert out["specialist_output"]["safety_flags"] == [
            "DISTRESS_SIGNAL",
            "SOMETHING_NEW",
        ]

    def test_crisis_resources_name_real_lines(self):
        """A hallucinated helpline is worse than none: the model once offered
        ALO 182, the health-appointment line."""
        assert "112" in orchestrator.CRISIS_RESOURCES_TR
        assert "183" in orchestrator.CRISIS_RESOURCES_TR
        assert "182" not in orchestrator.CRISIS_RESOURCES_TR


class TestKeepCrisis:
    """Crisis resources must leave the compliance gate on every branch."""

    def test_notices_are_appended_to_disclosures(self):
        out = orchestrator._keep_crisis(
            {"crisis_notices": ["ACIL"]}, {"disclosures": ["yasal"]}
        )
        assert out["disclosures"] == ["yasal", "ACIL"]

    def test_block_branch_still_carries_them(self):
        """The worst moment to hand someone a dead end is a blocked crisis
        turn, which previously ended at a generic failure string."""
        out = orchestrator._keep_crisis(
            {"crisis_notices": ["ACIL"]}, {"final_output": "engellendi"}
        )
        assert out["disclosures"] == ["ACIL"]

    def test_not_duplicated_when_already_present(self):
        out = orchestrator._keep_crisis(
            {"crisis_notices": ["ACIL"]}, {"disclosures": ["ACIL"]}
        )
        assert out["disclosures"] == ["ACIL"]

    def test_ordinary_turn_is_untouched(self):
        payload = {"disclosures": ["yasal"]}
        assert orchestrator._keep_crisis({}, payload) is payload


# ==========================================================================
# synthesis_node
# ==========================================================================
class TestSynthesisNode:
    @pytest.mark.asyncio
    async def test_produces_a_draft_from_specialist_output(self, patched_llm, base_state):
        patched_llm.set_response("BIST 100 içinden baktım.\n\nPortföyünüzde 500 lot THYAO var.")
        out = await orchestrator.synthesis_node(
            {**base_state, "specialist_output": {"status": "OK", "data": {}}}
        )
        assert "THYAO" in out["draft_response"]

    @pytest.mark.asyncio
    async def test_uses_the_orchestrator_system_prompt(self, patched_llm, base_state):
        await orchestrator.synthesis_node({**base_state, "specialist_output": {}})
        system = patched_llm.calls[0][0].content
        assert "MONEYFAST FRONT-FACING AGENT" in system
        assert "Reply ENTIRELY IN TURKISH" in system

    @pytest.mark.asyncio
    async def test_specialist_payload_is_embedded_as_json(self, patched_llm, base_state):
        await orchestrator.synthesis_node(
            {**base_state, "specialist_output": {"status": "EMPTY", "tool": "x"}}
        )
        user = patched_llm.calls[0][1].content
        assert '"status": "EMPTY"' in user

    @pytest.mark.asyncio
    async def test_oversized_payload_is_truncated(self, patched_llm, base_state):
        """Guards the context window: a 10k-row payload must not blow the turn.

        Asserted on the specialist slice rather than on the whole prompt,
        which now also carries the conversation and would make this pass or
        fail for the wrong reason."""
        huge = {"data": {"rows": ["x" * 100 for _ in range(500)]}}
        await orchestrator.synthesis_node({**base_state, "specialist_output": huge})
        user = patched_llm.calls[0][1].content
        embedded = user.split("Specialist output", 1)[1]
        # JSON dilimi + şablonun kendi bağlayıcı kuralları. Sınırlanan şey
        # JSON; şablon bir kural eklendiğinde büyüyor ve payı burada açıkça
        # ayrılmış -- testin ölçtüğü, gövdenin kırpıldığı.
        assert len(embedded) < orchestrator.SYNTHESIS_PAYLOAD_CHARS + 2000

    @pytest.mark.asyncio
    async def test_the_writer_is_given_the_conversation(self, patched_llm, base_state):
        """The final writer used to be blind to earlier turns, so "peki ya onu
        satsam?" was rendered by a model that did not know what "onu" was."""
        history = [
            {"role": "user", "content": "THYAO hakkında ne biliyorsun?"},
            {"role": "assistant", "content": "THYAO bir havayolu şirketi."},
        ]
        await orchestrator.synthesis_node(
            {**base_state, "conversation_history": history, "specialist_output": {}}
        )
        user = patched_llm.calls[0][1].content
        assert "THYAO hakkında ne biliyorsun?" in user

    @pytest.mark.asyncio
    async def test_an_empty_conversation_renders_as_none(self, patched_llm, base_state):
        """Same idiom the router already uses. An empty placeholder would
        leave a bare heading the model reads as a truncated instruction."""
        await orchestrator.synthesis_node(
            {**base_state, "conversation_history": [], "specialist_output": {}}
        )
        user = patched_llm.calls[0][1].content
        assert "(none)" in user

    @pytest.mark.asyncio
    async def test_the_revision_pass_is_not_given_the_conversation(
        self, patched_llm, base_state
    ):
        """The revision path sees only the rejected draft and the reason.
        History there would widen the surface for reintroducing exactly what
        the compliance gate just blocked."""
        await orchestrator.synthesis_node(
            {
                **base_state,
                "revision_count": 1,
                "draft_response": "önceki taslak",
                "blocked_reason": "tavsiye içeriyor",
                "conversation_history": [
                    {"role": "user", "content": "gizli önceki mesaj"}
                ],
            }
        )
        user = patched_llm.calls[0][1].content
        assert "gizli önceki mesaj" not in user

    @pytest.mark.asyncio
    async def test_missing_specialist_output_is_rendered_as_empty_object(
        self, patched_llm, base_state
    ):
        await orchestrator.synthesis_node(base_state)
        assert "{}" in patched_llm.calls[0][1].content

    @pytest.mark.asyncio
    async def test_revision_uses_the_revision_template(self, patched_llm, base_state):
        state = {
            **base_state,
            "revision_count": 1,
            "draft_response": "Bu hisseyi almanızı öneririm.",
            "blocked_reason": "Tavsiye içeriyor.",
        }
        await orchestrator.synthesis_node(state)
        user = patched_llm.calls[0][1].content
        assert "rejected by compliance" in user
        assert "Bu hisseyi almanızı öneririm." in user
        assert "Tavsiye içeriyor." in user

    @pytest.mark.asyncio
    async def test_revision_without_a_previous_draft_falls_back_to_synthesis(
        self, patched_llm, base_state
    ):
        """Edge case: revision_count is set but no draft exists, so there is
        nothing to rewrite and the node must start over."""
        await orchestrator.synthesis_node(
            {**base_state, "revision_count": 1, "draft_response": "", "specialist_output": {}}
        )
        assert "Detected intent" in patched_llm.calls[0][1].content

    @pytest.mark.asyncio
    async def test_revision_without_a_blocked_reason_uses_a_default(
        self, patched_llm, base_state
    ):
        await orchestrator.synthesis_node(
            {**base_state, "revision_count": 1, "draft_response": "önceki"}
        )
        assert "Compliance rejection." in patched_llm.calls[0][1].content

    @pytest.mark.asyncio
    async def test_llm_outage_yields_a_turkish_failure_message(
        self, mocker, base_state, caplog
    ):
        """A network drop. The user gets a plain Turkish apology, never a
        stack trace and never a fabricated answer. Rate limiting has its own
        message and its own test below."""
        mocker.patch.object(
            orchestrator, "_llm_text", side_effect=RuntimeError("connection reset by peer")
        )
        with caplog.at_level("ERROR", logger="moneyfast.graph"):
            out = await orchestrator.synthesis_node(base_state)
        assert out["draft_response"] == ""
        assert out["final_output"] == orchestrator.GENERIC_FAILURE_TR
        assert "synthesis" in out["errors"][0]

    @pytest.mark.asyncio
    async def test_a_rate_limit_says_so_instead_of_the_generic_apology(
        self, mocker, base_state
    ):
        """Under one message a quota exhaustion looked identical to a broken
        application: four turns in a row, including "selam", answered "Şu anda
        yanıtı hazırlayamadım" with nothing saying that waiting is the fix."""
        mocker.patch.object(
            orchestrator, "_llm_text",
            side_effect=RuntimeError("Error code: 429 - rate_limit_exceeded"),
        )
        out = await orchestrator.synthesis_node(base_state)
        assert out["final_output"] == orchestrator.RATE_LIMITED_TR
        assert "yoğunluk sınırına" in out["final_output"]

    @pytest.mark.asyncio
    async def test_an_ordinary_outage_keeps_the_generic_apology(
        self, mocker, base_state
    ):
        mocker.patch.object(
            orchestrator, "_llm_text", side_effect=RuntimeError("connection reset")
        )
        out = await orchestrator.synthesis_node(base_state)
        assert out["final_output"] == orchestrator.GENERIC_FAILURE_TR

    @pytest.mark.asyncio
    async def test_missing_intent_and_agent_use_placeholders(self, patched_llm):
        await orchestrator.synthesis_node({"user_message": "merhaba"})
        user = patched_llm.calls[0][1].content
        assert "UNKNOWN" in user
        assert "EDUCATION_AGENT" in user


# ==========================================================================
# compliance_gate_node
# ==========================================================================
class TestComplianceGate:
    @pytest.mark.asyncio
    async def test_pass_emits_the_draft_unchanged(
        self, fake_mcp, base_state, pass_verdict
    ):
        fake_mcp.responses["validate_compliance_rules"] = pass_verdict
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "Nötr bir cevap."}
        )
        assert out["compliance_verdict"] == "PASS"
        assert out["final_output"] == "Nötr bir cevap."

    @pytest.mark.asyncio
    async def test_revise_emits_the_remediated_text_not_the_original(
        self, fake_mcp, base_state, pass_verdict
    ):
        """Contract: on REVISE the original draft must never be emitted."""
        fake_mcp.responses["validate_compliance_rules"] = {
            **pass_verdict,
            "verdict": "REVISE",
            "remediated_response": "Düzeltilmiş cevap.",
        }
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "Almanızı öneririm."}
        )
        assert out["compliance_verdict"] == "REVISE"
        assert out["final_output"] == "Düzeltilmiş cevap."
        assert "öneririm" not in out["final_output"]

    @pytest.mark.asyncio
    async def test_revise_without_remediated_text_becomes_a_block(
        self, fake_mcp, base_state, pass_verdict
    ):
        """Fail closed: REVISE with nothing to emit is not a licence to emit
        the original."""
        fake_mcp.responses["validate_compliance_rules"] = {
            **pass_verdict, "verdict": "REVISE", "remediated_response": None
        }
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "Almanızı öneririm."}
        )
        assert out["compliance_verdict"] == "BLOCK"
        assert out["final_output"] == orchestrator.GENERIC_FAILURE_TR

    @pytest.mark.asyncio
    async def test_block_emits_the_user_facing_reason(
        self, fake_mcp, base_state, pass_verdict
    ):
        fake_mcp.responses["validate_compliance_rules"] = {
            **pass_verdict,
            "verdict": "BLOCK",
            "blocked_reason_user_facing": "Getiri garantisi veremem.",
        }
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "Kesin kazandırır."}
        )
        assert out["compliance_verdict"] == "BLOCK"
        assert out["final_output"] == "Getiri garantisi veremem."
        assert out["revision_count"] == 1

    @pytest.mark.asyncio
    async def test_block_without_a_reason_uses_the_generic_message(
        self, fake_mcp, base_state, pass_verdict
    ):
        fake_mcp.responses["validate_compliance_rules"] = {
            **pass_verdict, "verdict": "BLOCK", "blocked_reason_user_facing": None
        }
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "taslak"}
        )
        assert out["final_output"] == orchestrator.GENERIC_FAILURE_TR

    @pytest.mark.asyncio
    async def test_missing_verdict_field_fails_closed(
        self, fake_mcp, base_state, pass_verdict
    ):
        """A malformed rule-engine reply must block, never default to PASS."""
        payload = {**pass_verdict}
        del payload["verdict"]
        fake_mcp.responses["validate_compliance_rules"] = payload
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "taslak"}
        )
        assert out["compliance_verdict"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_lowercase_verdict_is_normalised(
        self, fake_mcp, base_state, pass_verdict
    ):
        fake_mcp.responses["validate_compliance_rules"] = {**pass_verdict, "verdict": "pass"}
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "taslak"}
        )
        assert out["compliance_verdict"] == "PASS"

    @pytest.mark.asyncio
    async def test_gate_unreachable_fails_closed(self, fake_mcp, base_state, caplog):
        """The invariant that matters most: no verdict means no emission."""
        fake_mcp.responses["validate_compliance_rules"] = MCPUnavailable("rule engine down")
        with caplog.at_level("ERROR", logger="moneyfast.graph"):
            out = await orchestrator.compliance_gate_node(
                {**base_state, "draft_response": "Kesin kazandırır."}
            )
        assert out["compliance_verdict"] == "BLOCK"
        assert out["final_output"] == orchestrator.GENERIC_FAILURE_TR
        assert "Kesin kazandırır." != out["final_output"]

    @pytest.mark.asyncio
    async def test_tool_error_also_fails_closed(self, fake_mcp, base_state):
        fake_mcp.responses["validate_compliance_rules"] = MCPToolError("bad jurisdiction")
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "taslak"}
        )
        assert out["compliance_verdict"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_empty_draft_blocks_without_calling_the_gate(self, fake_mcp, base_state):
        out = await orchestrator.compliance_gate_node({**base_state, "draft_response": ""})
        assert out["compliance_verdict"] == "BLOCK"
        assert out["final_output"] == orchestrator.GENERIC_FAILURE_TR
        assert fake_mcp.calls == []

    @pytest.mark.asyncio
    async def test_empty_draft_preserves_an_existing_final_output(
        self, fake_mcp, base_state
    ):
        """Synthesis already failed and wrote its own message; keep it."""
        out = await orchestrator.compliance_gate_node(
            {**base_state, "draft_response": "", "final_output": "Özel hata mesajı."}
        )
        assert out["final_output"] == "Özel hata mesajı."

    @pytest.mark.asyncio
    async def test_personal_data_flag_is_derived_from_the_payload(
        self, fake_mcp, base_state, pass_verdict, positions_payload
    ):
        fake_mcp.responses["validate_compliance_rules"] = pass_verdict
        await orchestrator.compliance_gate_node({
            **base_state,
            "draft_response": "taslak",
            "specialist_output": {"data": positions_payload},
            "tools_used": ["get_portfolio_positions"],
        })
        args = fake_mcp.calls[0][1]
        assert args["contains_personal_data"] is True
        assert args["contains_transaction_proposal"] is False
        assert args["tools_used"] == ["get_portfolio_positions"]
        assert args["jurisdiction"] == orchestrator.JURISDICTION

    @pytest.mark.asyncio
    async def test_proposal_flag_is_derived_from_the_payload(
        self, fake_mcp, base_state, pass_verdict, proposal_payload
    ):
        fake_mcp.responses["validate_compliance_rules"] = pass_verdict
        await orchestrator.compliance_gate_node({
            **base_state,
            "draft_response": "taslak",
            "specialist_output": {"data": proposal_payload},
        })
        assert fake_mcp.calls[0][1]["contains_transaction_proposal"] is True

    @pytest.mark.asyncio
    async def test_null_data_does_not_crash_the_flag_derivation(
        self, fake_mcp, base_state, pass_verdict
    ):
        """Edge case: an ERROR envelope carries data=None."""
        fake_mcp.responses["validate_compliance_rules"] = pass_verdict
        await orchestrator.compliance_gate_node({
            **base_state, "draft_response": "taslak",
            "specialist_output": {"status": "ERROR", "data": None},
        })
        assert fake_mcp.calls[0][1]["contains_personal_data"] is False


# ==========================================================================
# Required disclosures
# ==========================================================================
class TestWithDisclosures:
    def test_append_placement(self):
        verdict = {"required_disclosures": [
            {"text": "Yatırım danışmanlığı değildir.", "placement": "APPEND"}
        ]}
        out = orchestrator._with_disclosures("Cevap.", verdict)
        assert out.startswith("Cevap.")
        assert out.endswith("Yatırım danışmanlığı değildir.")

    def test_prepend_placement(self):
        verdict = {"required_disclosures": [
            {"text": "Uyarı.", "placement": "PREPEND"}
        ]}
        assert orchestrator._with_disclosures("Cevap.", verdict).startswith("Uyarı.")

    def test_inline_placement_is_appended(self):
        """INLINE has no insertion point here, so it lands at the end. Pinned
        so the behaviour is a decision rather than an accident."""
        verdict = {"required_disclosures": [{"text": "Not.", "placement": "INLINE"}]}
        assert orchestrator._with_disclosures("Cevap.", verdict).endswith("Not.")

    def test_disclosure_already_present_is_not_duplicated(self):
        verdict = {"required_disclosures": [{"text": "Uyarı.", "placement": "APPEND"}]}
        out = orchestrator._with_disclosures("Cevap. Uyarı.", verdict)
        assert out.count("Uyarı.") == 1

    def test_blank_disclosure_is_skipped(self):
        verdict = {"required_disclosures": [{"text": "   ", "placement": "APPEND"}]}
        assert orchestrator._with_disclosures("Cevap.", verdict) == "Cevap."

    def test_disclosure_without_text_is_skipped(self):
        verdict = {"required_disclosures": [{"placement": "APPEND"}]}
        assert orchestrator._with_disclosures("Cevap.", verdict) == "Cevap."

    def test_no_disclosures_returns_the_text_unchanged(self):
        assert orchestrator._with_disclosures("Cevap.", {}) == "Cevap."

    def test_multiple_placements_are_ordered(self):
        verdict = {"required_disclosures": [
            {"text": "Başlık.", "placement": "PREPEND"},
            {"text": "Dipnot.", "placement": "APPEND"},
        ]}
        out = orchestrator._with_disclosures("Gövde.", verdict)
        assert out.index("Başlık.") < out.index("Gövde.") < out.index("Dipnot.")

    def test_disclosure_text_is_inserted_verbatim(self):
        """Contract: never paraphrase, shorten or translate a disclosure."""
        text = "Burada yer alan bilgiler yatırım danışmanlığı kapsamında değildir."
        verdict = {"required_disclosures": [{"text": text, "placement": "APPEND"}]}
        assert text in orchestrator._with_disclosures("Cevap.", verdict)


# ==========================================================================
# Conditional edges
# ==========================================================================
class TestRouteAfterRouter:
    @pytest.mark.parametrize(
        "agent,expected",
        [
            ("PORTFOLIO_AGENT", "portfolio"),
            ("MARKET_RESEARCH_AGENT", "market_research"),
            ("RISK_STRATEGY_AGENT", "risk"),
            ("TRANSACTION_AGENT", "transaction"),
            ("HUMAN_HANDOFF", "handoff"),
            ("EDUCATION_AGENT", "synthesis"),
            ("SMALLTALK_AGENT", "synthesis"),
        ],
    )
    def test_every_agent_maps_to_its_node(self, agent, expected):
        state = {"target_agent": agent, "primary_intent": "PORTFOLIO_INQUIRY", "safety_flags": []}
        assert orchestrator.route_after_router(state) == expected

    def test_unknown_agent_falls_through_to_synthesis(self):
        """A classifier that invents an agent must not deadlock the graph."""
        state = {"target_agent": "MYSTERY_AGENT", "primary_intent": "X", "safety_flags": []}
        assert orchestrator.route_after_router(state) == "synthesis"

    def test_missing_agent_falls_through_to_synthesis(self):
        assert orchestrator.route_after_router({"safety_flags": []}) == "synthesis"

    def test_uncertainty_no_longer_skips_the_specialist(self):
        """`needs_clarification` used to short-circuit to synthesis, so the
        tool was never called and the user was told the data could not be
        retrieved -- when nothing had tried. Measured: "onun son fiyatı ne
        kadar" routed correctly to MARKET_DATA_AGENT, was flagged uncertain,
        skipped the tool, and answered "fiyat alınamadı" with the quote one
        call away."""
        state = {
            "needs_clarification": True,
            "target_agent": "PORTFOLIO_AGENT",
            "primary_intent": "PORTFOLIO_INQUIRY",
            "safety_flags": [],
        }
        assert orchestrator.route_after_router(state) == "portfolio"

    def test_unsafe_intent_routes_to_handoff(self):
        state = {"target_agent": "PORTFOLIO_AGENT", "primary_intent": "UNSAFE", "safety_flags": []}
        assert orchestrator.route_after_router(state) == "handoff"

    def test_distress_flag_routes_to_handoff_whatever_the_agent(self):
        state = {
            "target_agent": "TRANSACTION_AGENT",
            "primary_intent": "TRANSACTION_REQUEST",
            "safety_flags": ["DISTRESS_SIGNAL"],
        }
        assert orchestrator.route_after_router(state) == "handoff"

    def test_safety_decides_before_anything_else(self):
        """Precedence, pinned. The old order let `needs_clarification` win
        over the distress check, so an uncertain distress turn went to
        synthesis instead of handoff -- a safety gate disabled by a
        confidence score."""
        state = {
            "needs_clarification": True,
            "primary_intent": "UNSAFE",
            "safety_flags": ["DISTRESS_SIGNAL"],
            "target_agent": "PORTFOLIO_AGENT",
        }
        assert orchestrator.route_after_router(state) == "handoff"

    def test_missing_safety_flags_key_is_tolerated(self):
        assert orchestrator.route_after_router({"target_agent": "PORTFOLIO_AGENT"}) == "portfolio"


class TestRouteAfterCompliance:
    def test_pass_ends_the_turn(self):
        assert orchestrator.route_after_compliance({"compliance_verdict": "PASS"}) == END

    def test_revise_ends_the_turn(self):
        assert orchestrator.route_after_compliance({"compliance_verdict": "REVISE"}) == END

    def test_block_with_budget_loops_back_to_synthesis(self, caplog):
        state = {"compliance_verdict": "BLOCK", "revision_count": 1, "draft_response": "d"}
        with caplog.at_level("INFO", logger="moneyfast.graph"):
            assert orchestrator.route_after_compliance(state) == "synthesis"

    def test_block_with_the_budget_exhausted_ends_the_turn(self):
        """Termination guarantee. Without this the graph loops until the
        recursion limit and the user waits for nothing."""
        state = {"compliance_verdict": "BLOCK", "revision_count": 99, "draft_response": "d"}
        assert orchestrator.route_after_compliance(state) == END

    def test_block_without_a_draft_ends_the_turn(self):
        """Nothing to rewrite, so looping would just repeat the failure."""
        state = {"compliance_verdict": "BLOCK", "revision_count": 1, "draft_response": ""}
        assert orchestrator.route_after_compliance(state) == END

    def test_missing_revision_count_is_treated_as_zero(self):
        state = {"compliance_verdict": "BLOCK", "draft_response": "d"}
        assert orchestrator.route_after_compliance(state) == "synthesis"


# ==========================================================================
# Helpers
# ==========================================================================
class TestHelpers:
    def test_history_summary_is_none_when_there_is_no_history(self):
        assert orchestrator._history_summary({}) is None
        assert orchestrator._history_summary({"conversation_history": []}) is None

    def test_history_summary_keeps_the_newest_turns(self):
        total = orchestrator.HISTORY_MAX_TURNS + 4
        history = [{"role": "user", "content": f"turn {i}"} for i in range(total)]
        summary = orchestrator._history_summary({"conversation_history": history})
        assert f"turn {total - 1}" in summary
        assert "turn 0" not in summary

    def test_history_summary_defaults_a_missing_role(self):
        summary = orchestrator._history_summary({"conversation_history": [{"content": "x"}]})
        assert summary == "kullanıcı: x"

    def test_previous_answers_are_excerpted_not_reproduced(self):
        """A whole previous answer in the prompt is a template, and synthesis
        copied one: handed a valid THYAO payload it reproduced the earlier
        turn's "ASELS verisi alınamadı" word for word. Coreference needs the
        subject of the last answer, never its body."""
        long_answer = "ASELS fiyatı 399,75 TL. " + "ayrıntı " * 300
        summary = orchestrator._history_summary(
            {"conversation_history": [{"role": "assistant", "content": long_answer}]}
        )
        assert "ASELS" in summary
        assert len(summary) < 400
        assert summary.endswith("…")

    def test_user_turns_are_kept_whole(self):
        """The user's own words are short and are what the referent points at."""
        summary = orchestrator._history_summary(
            {"conversation_history": [{"role": "user", "content": "ASELS ne durumda?"}]}
        )
        assert summary == "kullanıcı: ASELS ne durumda?"

    def test_history_summary_is_capped_in_length(self):
        """Long histories must not blow the classifier's context window."""
        history = [{"role": "user", "content": "x" * 5000} for _ in range(6)]
        summary = orchestrator._history_summary({"conversation_history": history})
        assert len(summary) <= orchestrator.HISTORY_MAX_CHARS

    def test_history_summary_cap_keeps_the_newest_content(self):
        """The cap slices the tail, so when it bites it is the oldest turn
        that loses its opening rather than the newest losing its end."""
        history = [
            {"role": "user", "content": "eski " * 3000},
            {"role": "user", "content": "en yeni soru"},
        ]
        summary = orchestrator._history_summary({"conversation_history": history})
        assert summary.endswith("en yeni soru")

    def test_specialist_task_is_valid_json(self, base_state):
        task = json.loads(orchestrator._specialist_task(base_state))
        assert task["task"] == base_state["user_message"]
        assert task["user_id"] == "u_123"

    def test_specialist_task_preserves_turkish_characters(self):
        """ensure_ascii=False matters: escaped Turkish would degrade the plan."""
        task = orchestrator._specialist_task({"user_message": "portföyüm nasıl?"})
        assert "portföyüm" in task

    def test_idempotency_key_is_deterministic(self, base_state):
        assert orchestrator._idempotency_key(base_state) == orchestrator._idempotency_key(base_state)

    def test_idempotency_key_varies_with_the_user(self, base_state):
        other = {**base_state, "user_id": "u_999"}
        assert orchestrator._idempotency_key(base_state) != orchestrator._idempotency_key(other)

    def test_idempotency_key_varies_between_turns(self, base_state):
        """Seeded on the turn's trace id. It used to be seeded on the history
        LENGTH, which stops changing once the window saturates -- so asking
        the same thing twice produced the same key and the second, legitimate
        staging request could be deduplicated into the first proposal."""
        agent_trace.new_turn("t-1")
        first = orchestrator._idempotency_key(base_state)
        agent_trace.new_turn("t-1")
        second = orchestrator._idempotency_key(base_state)
        assert first != second

    def test_idempotency_key_is_stable_within_one_turn(self, base_state):
        """The graph repairs bad specialist arguments and calls again; that
        retry is exactly what idempotency exists to collapse."""
        agent_trace.new_turn("t-1")
        assert orchestrator._idempotency_key(base_state) == orchestrator._idempotency_key(
            base_state
        )

    def test_idempotency_key_is_prefixed_and_bounded(self, base_state):
        key = orchestrator._idempotency_key(base_state)
        assert key.startswith("idem_")
        assert len(key) == len("idem_") + 24

    @pytest.mark.asyncio
    async def test_run_tool_reports_ok_without_an_empty_predicate(self, fake_mcp, base_state):
        fake_mcp.responses["some_tool"] = {"data": 1}
        out = await orchestrator._run_tool(base_state, "some_tool", {})
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_run_tool_appends_to_existing_tools_used(self, fake_mcp, base_state):
        fake_mcp.responses["some_tool"] = {"data": 1}
        out = await orchestrator._run_tool(
            {**base_state, "tools_used": ["classify_and_route_intent"]}, "some_tool", {}
        )
        assert out["tools_used"] == ["classify_and_route_intent", "some_tool"]

    def test_tool_error_envelope_carries_a_turkish_instruction(self, base_state):
        out = orchestrator._tool_error(base_state, "some_tool", RuntimeError("boom"))
        assert out["specialist_output"]["status"] == "ERROR"
        assert out["specialist_output"]["instruction"] == orchestrator.DATA_FAILURE_TR
        assert "some_tool: boom" in out["errors"][0]

    def test_failure_messages_are_turkish(self):
        """They reach the user directly, bypassing the LLM, so they cannot be
        English placeholders."""
        for message in (orchestrator.GENERIC_FAILURE_TR, orchestrator.DATA_FAILURE_TR):
            assert any(ch in message for ch in "ıİşğüöç")


# ==========================================================================
# Graph assembly
# ==========================================================================
class TestGraph:
    def test_all_nodes_are_registered(self):
        nodes = set(orchestrator.build_graph().get_graph().nodes)
        assert {
            "router", "portfolio", "market_research", "risk",
            "transaction", "handoff", "synthesis", "compliance",
        } <= nodes

    def test_every_specialist_leads_to_synthesis(self):
        edges = {(e.source, e.target) for e in orchestrator.build_graph().get_graph().edges}
        for node in ("portfolio", "market_research", "risk", "transaction", "handoff"):
            assert (node, "synthesis") in edges

    def test_synthesis_leads_to_the_compliance_gate(self):
        """Structural guarantee that no draft can reach the user unvalidated."""
        edges = {(e.source, e.target) for e in orchestrator.build_graph().get_graph().edges}
        assert ("synthesis", "compliance") in edges

    def test_compliance_is_the_only_terminal_node(self):
        graph = orchestrator.build_graph().get_graph()
        terminals = {e.source for e in graph.edges if e.target == END}
        assert terminals == {"compliance"}

    def test_entry_point_is_the_router(self):
        edges = {(e.source, e.target) for e in orchestrator.build_graph().get_graph().edges}
        assert ("__start__", "router") in edges

    def test_graph_is_memoised(self):
        assert orchestrator.get_graph() is orchestrator.get_graph()

    def test_compiles_without_a_checkpointer_when_unavailable(self, mocker, caplog):
        """Optional dependency path: langgraph.checkpoint may be absent in a
        slimmed image, and the graph must still compile."""
        mocker.patch.dict(sys.modules, {"langgraph.checkpoint.memory": None})
        with caplog.at_level("INFO", logger="moneyfast.graph"):
            assert orchestrator.build_graph() is not None
        assert any("no checkpointer" in r.getMessage() for r in caplog.records)


class TestRunTurnStreaming:
    """Progress streams; the answer does not.

    The graph is fail-closed -- a draft the compliance gate blocks must never
    be shown -- so synthesis tokens cannot be emitted as they are produced.
    The stages are real node transitions, which is the point: the captions
    they replace were a fixed 800ms client-side loop that announced "Risk
    modeli güncelleniyor..." even for "what is the capital of Turkey".
    """

    @pytest.mark.asyncio
    async def test_stages_name_the_nodes_actually_entered(
        self, route_as, fake_mcp, patched_llm, routing_payload, positions_payload, pass_verdict
    ):
        fake_mcp.responses.update({
            "get_portfolio_positions": positions_payload,
            "validate_compliance_rules": pass_verdict,
        })
        route_as(routing_payload)
        patched_llm.set_responses(["{}", "Portföyünüzde 500 lot THYAO var."])

        events = [
            item
            async for item in orchestrator.run_turn_streaming(
                "portföyüm ne durumda?", user_id="u_123"
            )
        ]

        stages = [value for kind, value in events if kind == "stage"]
        assert orchestrator.STAGE_LABELS_TR["portfolio"] in stages
        # The risk node never ran, so its caption must not appear.
        assert orchestrator.STAGE_LABELS_TR["risk"] not in stages

    @pytest.mark.asyncio
    async def test_the_last_event_carries_the_finished_state(
        self, route_as, fake_mcp, patched_llm, routing_payload, positions_payload, pass_verdict
    ):
        fake_mcp.responses.update({
            "get_portfolio_positions": positions_payload,
            "validate_compliance_rules": pass_verdict,
        })
        route_as(routing_payload)
        patched_llm.set_responses(["{}", "Portföyünüzde 500 lot THYAO var."])

        events = [
            item
            async for item in orchestrator.run_turn_streaming("portföyüm?", user_id="u_1")
        ]

        kind, final = events[-1]
        assert kind == "state"
        assert "THYAO" in final["final_output"]
        assert final["compliance_verdict"] == "PASS"
        # Seeded from the initial state: `updates` mode yields only the keys a
        # node returned, so this would be missing if the accumulator started
        # empty -- and widgets.build() reads it.
        assert final["user_message"] == "portföyüm?"

    @pytest.mark.asyncio
    async def test_a_node_yielding_no_patch_is_survived(self, mocker):
        """LangGraph yields a dict per node today. A None would otherwise
        crash the turn at the accumulator rather than degrade."""

        class _FakeGraph:
            async def astream(self, *_args, **_kwargs):
                yield {"router": None}
                yield {"synthesis": {"final_output": "Merhaba"}}

        mocker.patch.object(orchestrator, "get_graph", return_value=_FakeGraph())

        events = [item async for item in orchestrator.run_turn_streaming("selam")]

        assert ("stage", orchestrator.STAGE_LABELS_TR["router"]) in events
        assert events[-1][1]["final_output"] == "Merhaba"

    @pytest.mark.asyncio
    async def test_streaming_and_buffered_runs_agree(
        self, route_as, fake_mcp, patched_llm, routing_payload, positions_payload, pass_verdict
    ):
        """Two entry points, one graph. If they diverged, the streamed answer
        and the fallback answer would differ for the same question."""
        def _setup():
            fake_mcp.responses.update({
                "get_portfolio_positions": positions_payload,
                "validate_compliance_rules": pass_verdict,
            })
            route_as(routing_payload)
            patched_llm.set_responses(["{}", "Portföyünüzde 500 lot THYAO var."])

        _setup()
        buffered = await orchestrator.run_turn("portföyüm?", user_id="u_1", thread_id="a")
        _setup()
        streamed = [
            item
            async for item in orchestrator.run_turn_streaming(
                "portföyüm?", user_id="u_1", thread_id="b"
            )
        ][-1][1]

        assert streamed["final_output"] == buffered["final_output"]
        assert streamed["target_agent"] == buffered["target_agent"]


class TestRunTurn:
    @pytest.mark.asyncio
    async def test_portfolio_turn_end_to_end(
        self, route_as, fake_mcp, patched_llm, routing_payload, positions_payload, pass_verdict
    ):
        """Full traversal: router, specialist, synthesis, gate."""
        fake_mcp.responses.update({
            "get_portfolio_positions": positions_payload,
            "validate_compliance_rules": pass_verdict,
        })
        route_as(routing_payload)
        patched_llm.set_responses(["{}", "Portföyünüzde 500 lot THYAO var."])
        state = await orchestrator.run_turn("portföyüm ne durumda?", user_id="u_123")
        assert state["compliance_verdict"] == "PASS"
        assert "THYAO" in state["final_output"]
        assert state["target_agent"] == "PORTFOLIO_AGENT"

    @pytest.mark.asyncio
    async def test_unsafe_turn_reaches_handoff_without_touching_a_data_tool(
        self, route_as, fake_mcp, patched_llm, routing_payload, pass_verdict
    ):
        fake_mcp.responses["validate_compliance_rules"] = pass_verdict
        route_as({
            **routing_payload, "primary_intent": "UNSAFE", "target_agent": "PORTFOLIO_AGENT"
        })
        patched_llm.set_response("Bu konuda yardımcı olamam.")
        state = await orchestrator.run_turn("piyasayı nasıl manipüle ederim?")
        assert state["specialist_output"]["status"] == "HANDOFF"
        called = [name for name, _ in fake_mcp.calls]
        assert "get_portfolio_positions" not in called

    @pytest.mark.asyncio
    async def test_blocked_turn_revises_once_then_terminates(
        self, route_as, fake_mcp, patched_llm, routing_payload, pass_verdict
    ):
        """The revision loop must converge. Two BLOCKs in a row exhaust the
        budget and the turn ends with the compliance-supplied refusal."""
        route_as(routing_payload)
        fake_mcp.responses.update({
            "get_portfolio_positions": {"positions": [{"symbol": "THYAO"}]},
            "validate_compliance_rules": {
                **pass_verdict,
                "verdict": "BLOCK",
                "blocked_reason_user_facing": "Getiri garantisi veremem.",
            },
        })
        patched_llm.set_response("Kesin kazandırır.")
        state = await orchestrator.run_turn("kazandırır mı?", user_id="u_1")
        assert state["compliance_verdict"] == "BLOCK"
        assert state["final_output"] == "Getiri garantisi veremem."
        assert state["revision_count"] >= 2, "the gate ran at least twice"

    @pytest.mark.asyncio
    async def test_history_and_thread_id_are_accepted(
        self, route_as, fake_mcp, patched_llm, routing_payload, positions_payload, pass_verdict
    ):
        fake_mcp.responses.update({
            "get_portfolio_positions": positions_payload,
            "validate_compliance_rules": pass_verdict,
        })
        route_as(routing_payload)
        patched_llm.set_response("Cevap.")
        state = await orchestrator.run_turn(
            "peki ya riski?",
            user_id="u_1",
            conversation_history=[{"role": "user", "content": "portföyüm"}],
            thread_id="t-42",
        )
        assert state["final_output"] == "Cevap."

    @pytest.mark.asyncio
    async def test_per_turn_state_does_not_leak_between_turns(
        self, route_as, fake_mcp, patched_llm, routing_payload, positions_payload, pass_verdict
    ):
        """The checkpointer keys state on thread_id and MERGES the input into
        whatever the previous turn left. A second turn on the same thread that
        runs no tool must not inherit the first turn's specialist_output --
        synthesis reads that as its source of figures, so an unrelated answer
        could quote an earlier question's holdings."""
        import json

        fake_mcp.responses.update({
            "get_portfolio_positions": positions_payload,
            "validate_compliance_rules": pass_verdict,
        })
        route_as(routing_payload)
        patched_llm.set_responses(["{}", "Portföyünüzde THYAO var."])
        first = await orchestrator.run_turn("portföyüm?", user_id="u_1", thread_id="shared")
        assert first["specialist_output"]["status"] == "OK"

        # Second turn: routed to an agent that runs no tool.
        route_as({**routing_payload, "target_agent": "EDUCATION_AGENT",
                  "primary_intent": "FINANCIAL_EDUCATION"})
        patched_llm.set_responses(["F/K oranı şudur."])
        second = await orchestrator.run_turn("F/K nedir?", user_id="u_1", thread_id="shared")

        assert not second.get("specialist_output"), "stale tool payload leaked into a new turn"
        assert second["target_agent"] == "EDUCATION_AGENT"

    @pytest.mark.asyncio
    async def test_router_outage_still_produces_a_reply(
        self, fake_mcp, patched_llm, pass_verdict
    ):
        """Degraded mode: the classifier is down but the user still gets a
        coherent Turkish answer rather than a traceback."""
        fake_mcp.responses["classify_and_route_intent"] = MCPUnavailable("down")
        fake_mcp.responses["validate_compliance_rules"] = pass_verdict
        patched_llm.set_response("Şu anda verilere ulaşamıyorum.")
        state = await orchestrator.run_turn("portföyüm?", user_id="u_1")
        assert state["final_output"]
        assert state["errors"]


# ==========================================================================
# CLI entrypoint
# ==========================================================================
class TestCLI:
    @pytest.mark.asyncio
    async def test_repl_prints_the_reply_and_accumulates_history(
        self, mocker, capsys
    ):
        mocker.patch("builtins.input", side_effect=["merhaba", ""])
        run_turn = mocker.patch.object(
            orchestrator, "run_turn", return_value={"final_output": "Merhaba!"}
        )
        await orchestrator._repl()
        assert "Merhaba!" in capsys.readouterr().out
        assert run_turn.call_count == 1

    @pytest.mark.asyncio
    async def test_repl_carries_history_between_turns(self, mocker):
        """Two turns append four entries: user, assistant, user, assistant.

        Note the aliasing: _repl passes the same list object on every call, so
        call_args holds a reference rather than a snapshot. Asserting on the
        final state is therefore the only honest check; asserting the length
        seen by call two would just re-read the list after both turns.
        """
        mocker.patch("builtins.input", side_effect=["ilk", "ikinci", ""])
        run_turn = mocker.patch.object(
            orchestrator, "run_turn", return_value={"final_output": "cevap"}
        )
        await orchestrator._repl()
        assert run_turn.call_count == 2
        history = run_turn.call_args_list[1].kwargs["conversation_history"]
        assert [t["content"] for t in history] == ["ilk", "cevap", "ikinci", "cevap"]

    @pytest.mark.asyncio
    async def test_repl_falls_back_when_final_output_is_missing(self, mocker, capsys):
        mocker.patch("builtins.input", side_effect=["merhaba", ""])
        mocker.patch.object(orchestrator, "run_turn", return_value={})
        await orchestrator._repl()
        assert orchestrator.GENERIC_FAILURE_TR in capsys.readouterr().out

    @pytest.mark.asyncio
    @pytest.mark.parametrize("signal", [EOFError, KeyboardInterrupt])
    async def test_repl_exits_cleanly_on_interrupt(self, mocker, signal):
        """Ctrl-C and Ctrl-D must not print a traceback."""
        mocker.patch("builtins.input", side_effect=signal)
        run_turn = mocker.patch.object(orchestrator, "run_turn")
        await orchestrator._repl()
        run_turn.assert_not_called()

    @pytest.mark.asyncio
    async def test_repl_exits_on_a_blank_line(self, mocker):
        mocker.patch("builtins.input", return_value="   ")
        run_turn = mocker.patch.object(orchestrator, "run_turn")
        await orchestrator._repl()
        run_turn.assert_not_called()

    def test_main_with_arguments_runs_a_single_turn(self, mocker, capsys):
        """Executes the module as __main__ with asyncio.run patched, so the
        coroutine is closed rather than awaited and no event loop is started."""
        captured = {}

        def _fake_run(coro):
            captured["coro"] = coro
            coro.close()
            return {"final_output": "Tek seferlik cevap."}

        mocker.patch.object(asyncio, "run", _fake_run)
        mocker.patch.object(sys, "argv", ["orchestrator.py", "portföyüm", "nasıl?"])
        runpy.run_path(orchestrator.__file__, run_name="__main__")
        assert "Tek seferlik cevap." in capsys.readouterr().out

    def test_main_without_arguments_starts_the_repl(self, mocker):
        captured = {}

        def _fake_run(coro):
            captured["name"] = coro.__qualname__
            coro.close()
            return None

        mocker.patch.object(asyncio, "run", _fake_run)
        mocker.patch.object(sys, "argv", ["orchestrator.py"])
        runpy.run_path(orchestrator.__file__, run_name="__main__")
        assert captured["name"].endswith("_repl")

    def test_main_falls_back_when_the_turn_returns_nothing(self, mocker, capsys):
        def _fake_run(coro):
            coro.close()
            return {}

        mocker.patch.object(asyncio, "run", _fake_run)
        mocker.patch.object(sys, "argv", ["orchestrator.py", "merhaba"])
        runpy.run_path(orchestrator.__file__, run_name="__main__")
        assert orchestrator.GENERIC_FAILURE_TR in capsys.readouterr().out


# ==========================================================================
# Module configuration
# ==========================================================================
def test_state_schema_exposes_every_contract_field():
    """The eight fields the architecture spec names must all exist."""
    annotations = set(orchestrator.MoneyFastState.__annotations__)
    assert {
        "user_message", "conversation_history", "primary_intent", "target_agent",
        "specialist_output", "draft_response", "compliance_verdict", "final_output",
    } <= annotations


def test_agent_roster_matches_the_routing_contract():
    assert orchestrator.AGENTS == [
        "PORTFOLIO_AGENT", "MARKET_DATA_AGENT", "MARKET_RESEARCH_AGENT",
        "RISK_STRATEGY_AGENT", "TRANSACTION_AGENT", "EDUCATION_AGENT",
        "SMALLTALK_AGENT", "HUMAN_HANDOFF",
    ]


def test_configuration_defaults():
    assert orchestrator.JURISDICTION == "TR"
    assert orchestrator.DEFAULT_LOCALE == "tr-TR"
    assert orchestrator.MAX_COMPLIANCE_REVISIONS >= 1


class TestSimilarityThresholdCalibration:
    """The threshold belongs to the embedding model, not to the product.

    The tool contract documents 0.62, calibrated for E5. This corpus uses
    paraphrase-multilingual-MiniLM, whose cosine scores run lower — measured
    against the live corpus, a clearly relevant article scores 0.43-0.72. The
    contract default silently discarded good hits and the assistant reported
    "no sources found" for news it was holding.
    """

    @pytest.mark.asyncio
    async def test_caller_overrides_whatever_the_model_proposed(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}
        patched_llm.set_response('{"arguments": {"min_similarity": 0.9}}')
        await orchestrator.market_research_node(base_state)
        _, args = fake_mcp.calls[0]
        assert args["min_similarity"] == 0.45

    @pytest.mark.asyncio
    async def test_threshold_is_tunable_without_a_rebuild(
        self, fake_mcp, patched_llm, base_state, monkeypatch
    ):
        """Retrieval evaluation should be able to move this without a code
        change; VECTOR_DB_ARCHITECTURE.md requires it be chosen by measurement."""
        monkeypatch.setenv("RAG_MIN_SIMILARITY", "0.5")
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}
        patched_llm.set_response("{}")
        await orchestrator.market_research_node(base_state)
        assert fake_mcp.calls[0][1]["min_similarity"] == 0.5


class TestMarketDataNode:
    """Added in v2.2. This is the node that answers "THYAO kaç lira?" — the
    question the six-tool system structurally could not reach."""

    @pytest.mark.asyncio
    async def test_named_symbols_are_passed_through(self, fake_mcp, patched_llm, base_state):
        fake_mcp.responses["get_market_data"] = {"instruments": [{"symbol": "THYAO"}]}
        patched_llm.set_response('{"arguments": {"symbols": ["THYAO"]}}')
        out = await orchestrator.market_data_node(base_state)
        assert fake_mcp.calls[0][1]["symbols"] == ["THYAO"]
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_an_open_question_reaches_the_trend_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        """Measured, 31 Aug: "akbankı yorumlar mısın" went to the document
        search, found no article, and the user was told "Akbank hakkında veri
        bulunamadı" -- about an instrument with a live price, published
        fundamentals and roughly seven hundred daily bars."""
        fake_mcp.responses["get_technical_signals"] = {
            "symbol": "AKBNK", "narrative": "AKBNK yükseliş eğiliminde.",
            "signals": {"trend": "UPTREND"},
        }
        patched_llm.set_response(
            '{"tool": "get_technical_signals", "arguments": {"symbol": "AKBNK"}}'
        )

        out = await orchestrator.market_data_node(base_state)

        assert fake_mcp.calls[0][0] == "get_technical_signals"
        assert fake_mcp.calls[0][1] == {"symbol": "AKBNK"}
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_the_trend_tool_falls_back_to_the_routers_ticker(
        self, fake_mcp, patched_llm, base_state
    ):
        """The plan chose the tool but named no symbol; the router already
        extracted one."""
        fake_mcp.responses["get_technical_signals"] = {
            "symbol": "THYAO", "narrative": "THYAO yatay seyrediyor.",
            "signals": {"trend": "SIDEWAYS"},
        }
        patched_llm.set_response('{"tool": "get_technical_signals", "arguments": {}}')

        await orchestrator.market_data_node(
            {**base_state, "entities": {"tickers": ["THYAO"]}}
        )

        assert fake_mcp.calls[0][1] == {"symbol": "THYAO"}

    @pytest.mark.asyncio
    async def test_no_symbol_anywhere_falls_through_to_the_price_path(
        self, fake_mcp, patched_llm, base_state
    ):
        """A one-symbol tool called with no symbol answers nothing. The price
        path can still work from whatever the turn did name."""
        fake_mcp.responses["get_market_data"] = {"instruments": []}
        patched_llm.set_response(
            '{"tool": "get_technical_signals", "arguments": {"filters": {"max_pe": 10}}}'
        )

        await orchestrator.market_data_node(base_state)

        assert fake_mcp.calls[0][0] == "get_market_data"

    @pytest.mark.asyncio
    async def test_a_stray_symbol_argument_never_reaches_the_screen(
        self, fake_mcp, patched_llm, base_state
    ):
        """`symbol` belongs to the trend tool. get_market_data rejects an
        unknown key rather than ignoring it, which would fail the turn."""
        fake_mcp.responses["get_market_data"] = {"instruments": []}
        patched_llm.set_response('{"arguments": {"symbol": "THYAO", "filters": {}}}')

        await orchestrator.market_data_node(base_state)

        assert "symbol" not in fake_mcp.calls[0][1]

    @pytest.mark.asyncio
    async def test_no_narrative_is_reported_as_an_empty_reading(
        self, fake_mcp, patched_llm, base_state
    ):
        """Too little history to read. The agent must say so rather than
        assembling a trend out of the raw figures."""
        fake_mcp.responses["get_technical_signals"] = {
            "symbol": "YENI", "narrative": None, "signals": {"trend": "UNKNOWN"},
        }
        patched_llm.set_response(
            '{"tool": "get_technical_signals", "arguments": {"symbol": "YENI"}}'
        )

        out = await orchestrator.market_data_node(base_state)

        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_filters_reach_the_tool(self, fake_mcp, patched_llm, base_state):
        fake_mcp.responses["get_market_data"] = {"instruments": []}
        patched_llm.set_response('{"arguments": {"filters": {"max_pe": 10}}}')
        await orchestrator.market_data_node(base_state)
        assert fake_mcp.calls[0][1]["filters"] == {"max_pe": 10}

    @pytest.mark.asyncio
    async def test_falls_back_to_router_entities_rather_than_screening_everything(
        self, fake_mcp, patched_llm, base_state
    ):
        """A plan with neither symbols nor filters would otherwise screen the
        whole universe and hand the model fifty rows to summarise."""
        fake_mcp.responses["get_market_data"] = {"instruments": []}
        patched_llm.set_response("{}")
        state = {**base_state, "entities": {"tickers": ["ASELS"]}}
        await orchestrator.market_data_node(state)
        assert fake_mcp.calls[0][1]["symbols"] == ["ASELS"]

    @pytest.mark.asyncio
    async def test_empty_result_is_reported_as_empty_not_as_an_error(
        self, fake_mcp, patched_llm, base_state
    ):
        """No instrument matching a screen is a complete answer."""
        fake_mcp.responses["get_market_data"] = {"instruments": []}
        patched_llm.set_response('{"arguments": {"filters": {"max_pe": 1}}}')
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "EMPTY"

    @pytest.mark.asyncio
    async def test_tool_failure_does_not_become_a_remembered_price(
        self, fake_mcp, patched_llm, base_state
    ):
        """A stale price presented as current is indistinguishable from a
        wrong one."""
        fake_mcp.responses["get_market_data"] = MCPUnavailable("market data down")
        patched_llm.set_response("{}")
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert out["specialist_output"]["data"] is None

    @pytest.mark.asyncio
    async def test_price_questions_route_here(self, route_as, base_state, routing_payload):
        route_as({**routing_payload, "target_agent": "MARKET_DATA_AGENT",
                  "primary_intent": "MARKET_DATA"})
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "MARKET_DATA_AGENT"
        assert orchestrator.route_after_router(out) == "market_data"


class TestArgumentRepair:
    """One correction attempt when the tool rejects an argument the caller can fix.

    This is the failure the user actually hit: asking for "BIST 100'de en çok
    kazandıranlar" produced "Verilere ulaşamadım", and typing "tekrar dene"
    worked — because the retry re-rolled the planner onto a legal enum value.
    The fix makes that correction happen inside one turn, using the tool's own
    error, which names the permitted values.
    """

    def _failing_then_ok(self, fake_mcp, error, payload):
        """First call raises, second succeeds."""
        outcomes = [error, payload]

        async def _call(name, arguments):
            fake_mcp.calls.append((name, arguments))
            outcome = outcomes.pop(0) if outcomes else payload
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        fake_mcp.call = _call

    @pytest.mark.asyncio
    async def test_a_rejected_sort_is_corrected_within_the_same_turn(
        self, fake_mcp, patched_llm, base_state
    ):
        self._failing_then_ok(
            fake_mcp,
            MCPToolError("get_market_data: unrecognised sort_by 'gainers'; allowed: change_percent, symbol."),
            {"instruments": [{"symbol": "THYAO"}]},
        )
        patched_llm.set_responses([
            '{"arguments": {"filters": {"market": "BIST"}, "sort_by": "gainers"}}',
            '{"arguments": {"filters": {"market": "BIST"}, "sort_by": "change_percent"}}',
        ])
        out = await orchestrator.market_data_node(base_state)

        assert out["specialist_output"]["status"] == "OK", "the user should not see a failure"
        assert len(fake_mcp.calls) == 2
        assert fake_mcp.calls[1][1]["sort_by"] == "change_percent"

    @pytest.mark.asyncio
    async def test_the_repair_prompt_carries_the_tool_error(
        self, fake_mcp, patched_llm, base_state
    ):
        """The model is corrected with the authoritative list, not asked to
        guess a second time."""
        self._failing_then_ok(
            fake_mcp,
            MCPToolError("unrecognised sort_by 'losers'; allowed: change_percent_asc."),
            {"instruments": []},
        )
        patched_llm.set_responses([
            '{"arguments": {"sort_by": "losers"}}',
            '{"arguments": {"sort_by": "change_percent_asc"}}',
        ])
        await orchestrator.market_data_node(base_state)
        repair_call = patched_llm.calls[-1]
        assert "change_percent_asc" in str(repair_call)
        assert "losers" in str(repair_call)

    @pytest.mark.asyncio
    async def test_only_one_retry_is_attempted(self, fake_mcp, patched_llm, base_state):
        """A model that keeps producing bad arguments must not loop."""
        error = MCPToolError("get_market_data: unrecognised sort_by 'nope'; allowed: symbol.")
        fake_mcp.responses["get_market_data"] = error
        patched_llm.set_responses([
            '{"arguments": {"sort_by": "nope"}}',
            '{"arguments": {"sort_by": "still_nope"}}',
        ])
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert len(fake_mcp.calls) == 2, "one original call plus exactly one retry"

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_is_not_retried(
        self, fake_mcp, patched_llm, base_state
    ):
        """Rewriting arguments cannot fix a service that is down; retrying only
        doubles the wait before the user is told."""
        fake_mcp.responses["get_market_data"] = MCPUnavailable("connection refused")
        patched_llm.set_response('{"arguments": {"symbols": ["THYAO"]}}')
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert len(fake_mcp.calls) == 1

    @pytest.mark.asyncio
    async def test_an_unchanged_repair_is_not_re_sent(
        self, fake_mcp, patched_llm, base_state
    ):
        """If the model returns the same arguments, calling again would fail
        identically — so it is reported rather than repeated."""
        fake_mcp.responses["get_market_data"] = MCPToolError("unrecognised sort_by 'x'; allowed: symbol.")
        patched_llm.set_responses([
            '{"arguments": {"sort_by": "x"}}',
            '{"arguments": {"sort_by": "x"}}',
        ])
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"
        assert len(fake_mcp.calls) == 1

    @pytest.mark.asyncio
    async def test_a_repair_that_returns_nothing_reports_the_original_error(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["get_market_data"] = MCPToolError("unrecognised sort_by 'x'; allowed: symbol.")
        patched_llm.set_responses([
            '{"arguments": {"sort_by": "x"}}',
            "not json at all",
        ])
        out = await orchestrator.market_data_node(base_state)
        assert out["specialist_output"]["status"] == "ERROR"


class TestDisclosurePlacement:
    """Required notices travel as data, not as three sentences appended to
    every answer. The words are unchanged and still mandatory; only where they
    are rendered moves."""

    def _verdict(self, texts, remediated=None):
        return {
            "verdict": "REVISE",
            "required_disclosures": [{"text": t, "placement": "APPEND"} for t in texts],
            "remediated_response": remediated,
        }

    def test_disclosure_texts_are_extracted_verbatim(self):
        verdict = self._verdict(["Bu içerik yatırım danışmanlığı değildir.", "Veriler gecikmelidir."])
        assert orchestrator._disclosure_texts(verdict) == [
            "Bu içerik yatırım danışmanlığı değildir.",
            "Veriler gecikmelidir.",
        ]

    def test_a_duplicate_notice_is_listed_once(self):
        verdict = self._verdict(["Aynı metin.", "Aynı metin."])
        assert orchestrator._disclosure_texts(verdict) == ["Aynı metin."]

    def test_no_disclosures_yields_an_empty_list(self):
        assert orchestrator._disclosure_texts({"verdict": "PASS"}) == []

    def test_the_inlined_copy_is_stripped_from_the_prose(self):
        """The compliance layer returns the notice already appended. Leaving
        that copy in place would show it twice — once inline, once as the
        footnote."""
        notice = "Bu içerik yatırım danışmanlığı değildir."
        verdict = self._verdict([notice])
        cleaned = orchestrator._without_disclosures(f"THYAO 301,25 TL.\n\n{notice}", verdict)
        assert cleaned == "THYAO 301,25 TL."

    def test_stripping_collapses_the_blank_lines_it_leaves(self):
        notice = "Uyarı."
        verdict = self._verdict([notice])
        cleaned = orchestrator._without_disclosures(f"Cevap.\n\n{notice}\n\n{notice}", verdict)
        assert cleaned == "Cevap."

    def test_an_answer_without_the_notice_is_unchanged(self):
        verdict = self._verdict(["Uyarı."])
        assert orchestrator._without_disclosures("Cevap.", verdict) == "Cevap."


class TestTransferStaging:
    """Transfers are staged like trades and confirmed by the user.

    They used to be refused outright; before that, they were routed through
    the SECURITIES path — costed with brokerage commission and BSMV, and
    rendered as a "Satım" with a blank ticker. Now they settle against the
    banking ledger.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["TRANSFER", "EFT", "HAVALE"])
    async def test_a_transfer_is_staged_for_confirmation(
        self, fake_mcp, patched_llm, base_state, kind
    ):
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "%s",'
            ' "notional_amount": {"amount": 200, "currency": "TRY"},'
            ' "destination_account_id": "1000000000002"}}' % kind
        )
        state = {**base_state, "user_message": "1000000000002 hesabına 200 lira gönder"}
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"
        assert fake_mcp.calls[0][1]["transaction_type"] == kind

    @pytest.mark.asyncio
    async def test_a_transfer_still_requires_confirmation(
        self, fake_mcp, patched_llm, base_state
    ):
        """The agent prepares; the user confirms. Same discipline as a trade —
        conversational assent is never confirmation."""
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": False,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "TRANSFER",'
            ' "notional_amount": {"amount": 200, "currency": "TRY"},'
            ' "destination_account_id": "1000000000002"}}'
        )
        state = {**base_state, "user_message": "200 lira gönder"}
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "ERROR"


class TestRefusedSymbol:
    """The user says "not that one" and the planner stages it anyway.

    Observed: asked for "thyao değil diğer bahsettiğim hisseyi satın
    alacağım", a THYAO proposal was produced. The prompt already forbade it;
    a rule that decides where money goes belongs in code.
    """

    def _state(self, base_state, message, history=()):
        return {
            **base_state,
            "user_message": message,
            "conversation_history": [{"role": "user", "content": h} for h in history],
        }

    def test_a_negated_ticker_is_caught(self, base_state):
        args = {"instrument": {"symbol": "THYAO"}}
        state = self._state(base_state, "thyao değil diğer bahsettiğim hisseyi al")
        assert orchestrator._symbol_refused_in_message(state, args) == "THYAO"

    def test_istemiyorum_counts_as_a_refusal(self, base_state):
        args = {"instrument": {"symbol": "THYAO"}}
        state = self._state(base_state, "thyao istemiyorum, aselsan alacağım")
        assert orchestrator._symbol_refused_in_message(state, args) == "THYAO"

    def test_the_company_name_refuses_its_ticker(self, base_state):
        """"aselsan istemiyorum" must block ASELS, not just the literal word."""
        args = {"instrument": {"symbol": "ASELS"}}
        state = self._state(base_state, "aselsan istemiyorum")
        assert orchestrator._symbol_refused_in_message(state, args) == "ASELS"

    def test_the_instrument_that_was_asked_for_passes(self, base_state):
        """"ASELS al, THYAO değil" refuses THYAO and leaves ASELS alone."""
        args = {"instrument": {"symbol": "ASELS"}}
        state = self._state(base_state, "asels al, thyao değil")
        assert orchestrator._symbol_refused_in_message(state, args) is None

    def test_a_plain_request_is_not_a_refusal(self, base_state):
        args = {"instrument": {"symbol": "THYAO"}}
        state = self._state(base_state, "thyao 5 adet almak istiyorum")
        assert orchestrator._symbol_refused_in_message(state, args) is None

    def test_a_distant_refusal_word_does_not_reach_back(self, base_state):
        """Narrow on purpose: the marker has to follow the symbol closely."""
        args = {"instrument": {"symbol": "THYAO"}}
        state = self._state(
            base_state, "thyao almak istiyorum ama bu fiyattan olmasın diyorum"
        )
        assert orchestrator._symbol_refused_in_message(state, args) is None

    def test_a_missing_symbol_is_not_a_refusal(self, base_state):
        assert orchestrator._symbol_refused_in_message(self._state(base_state, "al"), {}) is None
        assert (
            orchestrator._symbol_refused_in_message(
                self._state(base_state, "al"), {"instrument": {"symbol": ""}}
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_staging_is_refused_end_to_end(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 10,'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        state = self._state(base_state, "thyao değil diğer bahsettiğim hisseyi alacağım")
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert out["specialist_output"]["missing_fields"] == ["instrument.symbol"]
        assert "THYAO" in out["specialist_output"]["clarification_request"]
        assert not fake_mcp.calls, "the symbol the user refused must not be staged"


class TestCurrentTurnAmount:
    """The 250/200 bug: the planner sees the last six turns verbatim, and with
    no precedence rule it staged an amount from the PREVIOUS message while the
    user had just named a different one."""

    def _state(self, base_state, message, history):
        return {
            **base_state,
            "user_message": message,
            "conversation_history": [{"role": "user", "content": h} for h in history],
        }

    @pytest.mark.asyncio
    async def test_an_amount_only_in_the_history_is_refused(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 250,'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        state = self._state(base_state, "200 adet al", ["250 adet alacaktım"])
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert not fake_mcp.calls, "a figure the user did not just say must not be staged"

    @pytest.mark.asyncio
    async def test_the_guard_reaches_the_whole_widened_window(
        self, fake_mcp, patched_llm, base_state
    ):
        """The guard still reaches back across the widened window, but only
        when THIS turn states a competing figure."""
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 250,'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        history = ["250 adet alacaktım"] + [f"başka konu {i}" for i in range(18)]
        state = self._state(base_state, "200 adet al", history)
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert not fake_mcp.calls

    @pytest.mark.asyncio
    async def test_a_figure_the_user_asked_to_reuse_is_allowed(
        self, fake_mcp, patched_llm, base_state
    ):
        """"son söylediğim adet kadar al" delegates to the history on purpose.
        Refusing it produced a loop with no exit: the planner resolved
        quantity=2 correctly, the guard rejected it, the assistant asked
        again, and the user answered "birkaç mesaj önce söyledim" four times
        before giving up."""
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "p1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 2,'
            ' "instrument": {"symbol": "ASELS"}, "source_account_id": "1"}}'
        )
        state = self._state(
            base_state, "son söylediğim adet kadar al", ["ASELS 2 adet almak istiyorum"]
        )
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"
        assert fake_mcp.calls, "the staging call must actually happen"

    @pytest.mark.asyncio
    async def test_the_clarification_never_names_an_internal_field(
        self, fake_mcp, patched_llm, base_state
    ):
        """It read "Tutarı bu mesajda göremedim (quantity=250)". The NAMING
        rule keeps internal keys off the screen."""
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 250,'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        state = self._state(base_state, "200 adet al", ["250 adet alacaktım"])
        out = await orchestrator.transaction_node(state)
        request = out["specialist_output"]["clarification_request"]
        assert "quantity" not in request
        assert "notional_amount" not in request

    @pytest.mark.asyncio
    async def test_the_amount_from_the_current_turn_is_staged(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 200,'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        state = self._state(base_state, "200 adet al", ["250 adet alacaktım"])
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"
        assert fake_mcp.calls[0][1]["quantity"] == 200

    @pytest.mark.asyncio
    async def test_a_thousands_separator_still_matches(
        self, fake_mcp, patched_llm, base_state
    ):
        """The user writes "10.000", the planner emits 10000."""
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY",'
            ' "notional_amount": {"amount": 10000, "currency": "TRY"},'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        state = self._state(base_state, "10.000 TL'lik al", ["5.000 TL demiştim"])
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_an_inferred_amount_in_neither_place_is_left_alone(
        self, fake_mcp, patched_llm, base_state
    ):
        """"hepsini sat" has no number anywhere. That is a different question
        and the tool validates it; blocking here would break the phrasing."""
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "SELL", "quantity": 120,'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        state = self._state(base_state, "THYAO'nun hepsini sat", ["portföyümü göster"])
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"


class TestDirectionGuard:
    """"10 tane aselsan satsana" was staged as a BUY and settled.

    The inversion is worse than it looks: a SELL mislabelled as BUY skips the
    backend's sell-side inventory check and lands in the cash check instead, so
    it surfaces as a successful purchase rather than an error.
    """

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("10 tane aselsan satsana", "SELL"),
            ("ASELS satmak istiyorum", "SELL"),
            ("hepsini bozdur", "SELL"),
            ("pozisyonu nakde çevir", "SELL"),
            # "altın" starts with the buy stem "al" — a prefix match would read
            # every gold price question as a purchase order.
            ("altın fiyatı ne kadar", None),
            ("altın alsana", "BUY"),
            ("10 tane aselsan al", "BUY"),
            ("10 tane aselsan satın al", "BUY"),
            ("100 lotluk THYAO alsana", "BUY"),
            ("THYAO almak istiyorum", "BUY"),
            ("portföyümü göster", None),
        ],
    )
    def test_the_users_verb_decides_the_direction(self, message, expected):
        assert orchestrator._stated_direction(message) == expected

    def test_satin_al_is_a_buy_despite_containing_sat(self):
        """The single most dangerous collision: every purchase phrased this way
        would otherwise read as a sale."""
        assert orchestrator._stated_direction("ASELS satın alıcam") == "BUY"
        assert orchestrator._stated_direction("ASELS satin alicam") == "BUY"

    @pytest.mark.parametrize("message", ["ASELS SATSANA", "ASELS Satsana"])
    def test_case_and_turkish_i_do_not_change_the_reading(self, message):
        assert orchestrator._stated_direction(message) == "SELL"

    @pytest.mark.asyncio
    async def test_a_buy_emitted_for_a_sell_request_is_refused(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 10,'
            ' "instrument": {"symbol": "ASELS"}, "source_account_id": "1"}}'
        )
        state = {**base_state, "user_message": "10 tane aselsan satsana"}
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "NEEDS_INPUT"
        assert "transaction_type" in out["specialist_output"]["missing_fields"]
        assert not fake_mcp.calls, "nothing may be staged in the wrong direction"

    @pytest.mark.asyncio
    async def test_a_matching_sell_is_staged(self, fake_mcp, patched_llm, base_state):
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "SELL", "quantity": 10,'
            ' "instrument": {"symbol": "ASELS"}, "source_account_id": "1"}}'
        )
        state = {**base_state, "user_message": "10 tane aselsan satsana"}
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"
        assert fake_mcp.calls[0][1]["transaction_type"] == "SELL"

    @pytest.mark.asyncio
    async def test_an_unstated_direction_is_left_to_the_tool(
        self, fake_mcp, patched_llm, base_state
    ):
        """Inferring a direction from history is the failure being prevented,
        so silence here must not be turned into a guess either."""
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 10,'
            ' "instrument": {"symbol": "ASELS"}, "source_account_id": "1"}}'
        )
        state = {**base_state, "user_message": "ASELS 10 adet"}
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_an_unreadable_transaction_type_is_not_second_guessed(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True,
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "SUBSCRIBE", "quantity": 1,'
            ' "instrument": {"symbol": "ASELS"}, "source_account_id": "1"}}'
        )
        state = {**base_state, "user_message": "ASELS satsana"}
        out = await orchestrator.transaction_node(state)
        assert out["specialist_output"]["status"] == "OK"


class TestInstrumentIsVerifiedBeforeAsking:
    """The measured bug: `get_market_data` was never called.

    Three consecutive turns -- "nvvvvdi hissesi almak", "aple alcam" and
    "ndivia nasıl" -- all reached an answer with no market lookup in the
    trace. The model recognised "aple" as Apple from its own knowledge,
    declared NVVVVDI non-existent from the same place, and told the user data
    for "ndivia" could not be retrieved while the backend resolves it to NVDA.

    The prompt already said to check first. This module has been here before:
    `_keep_crisis` exists because a mandatory instruction was followed about
    half the time. So on the one path where being wrong costs money, the check
    runs in code.
    """

    NEEDS_QUANTITY = json.dumps({
        "status": "NEEDS_INPUT",
        "missing_fields": ["quantity"],
        "clarification_request": "Kaç adet almak istersiniz?",
        "arguments": {"instrument": {"symbol": "NVVVVDI"}},
    })

    @pytest.mark.asyncio
    async def test_a_missing_instrument_is_reported_instead_of_a_quantity_question(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(self.NEEDS_QUANTITY)
        fake_mcp.responses["get_market_data"] = {
            "instruments": [],
            "warnings": ["Şu semboller bulunamadı veya fiyatı yok: NVVVVDI"],
        }
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["missing_fields"] == ["instrument"]
        assert "Kaç adet" not in out["specialist_output"]["clarification_request"]

    @pytest.mark.asyncio
    async def test_the_lookup_actually_happens(self, fake_mcp, patched_llm, base_state):
        """The whole point: a tool call, not the model's recollection."""
        patched_llm.set_response(self.NEEDS_QUANTITY)
        fake_mcp.responses["get_market_data"] = {"instruments": []}
        await orchestrator.transaction_node(base_state)
        assert any(name == "get_market_data" for name, _ in fake_mcp.calls)

    @pytest.mark.asyncio
    async def test_the_resolvers_own_suggestion_is_passed_through(
        self, fake_mcp, patched_llm, base_state
    ):
        """Rather than writing a second, differently worded version of the
        same sentence."""
        patched_llm.set_response(self.NEEDS_QUANTITY)
        fake_mcp.responses["get_market_data"] = {
            "instruments": [],
            "warnings": ["«ndivia» için tam eşleşme yok. Bunlardan biri mi: NVDA?"],
        }
        out = await orchestrator.transaction_node(base_state)
        assert "NVDA" in out["specialist_output"]["clarification_request"]

    @pytest.mark.asyncio
    async def test_an_instrument_that_exists_lets_the_question_through(
        self, fake_mcp, patched_llm, base_state
    ):
        """Verification must not turn every clarification into a refusal."""
        patched_llm.set_response(self.NEEDS_QUANTITY)
        fake_mcp.responses["get_market_data"] = {"instruments": [{"symbol": "NVDA"}]}
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["missing_fields"] == ["quantity"]

    @pytest.mark.asyncio
    async def test_a_lookup_failure_does_not_become_a_denial(
        self, fake_mcp, patched_llm, base_state
    ):
        """An unreachable tool is not proof the instrument is missing. The
        turn continues; staging resolves strictly and refuses on its own."""
        patched_llm.set_response(self.NEEDS_QUANTITY)
        fake_mcp.responses["get_market_data"] = MCPUnavailable("mcp down")
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["missing_fields"] == ["quantity"]

    @pytest.mark.asyncio
    async def test_a_turn_naming_no_instrument_is_left_alone(
        self, fake_mcp, patched_llm, base_state
    ):
        patched_llm.set_response(json.dumps({
            "status": "NEEDS_INPUT",
            "missing_fields": ["instrument"],
            "clarification_request": "Hangi hisseyi almak istersiniz?",
            "arguments": {},
        }))
        out = await orchestrator.transaction_node(base_state)
        assert not any(name == "get_market_data" for name, _ in fake_mcp.calls)

    def test_the_symbol_is_found_however_the_model_expressed_it(self):
        state = {"entities": {"tickers": ["THYAO"]}}
        assert orchestrator._named_symbol(
            {"arguments": {"instrument": {"symbol": "ASELS"}}}, state) == "ASELS"
        assert orchestrator._named_symbol({"arguments": {"symbol": "GARAN"}}, state) == "GARAN"
        # Falls back to whatever the router extracted.
        assert orchestrator._named_symbol({"arguments": {}}, state) == "THYAO"
        assert orchestrator._named_symbol({"arguments": {}}, {"entities": {}}) is None


class TestHandoffCategoryVocabulary:
    """The names a distress signal can arrive under.

    The regex pre-filter emits a fixed vocabulary, but `router_node` unions
    the ROUTER MODEL's own flags into the same list without checking them,
    and the model does not use those names. Pinning the table is what stops
    a synonym from silently selecting the wrong response.
    """

    def test_every_self_harm_synonym_lands_on_the_same_category(self):
        for name in ("SELF_HARM", "SELF_HARM_RISK", "SUICIDE", "SUICIDAL",
                     "SUICIDE_RISK", "SUICIDAL_IDEATION", "SELF_INJURY"):
            assert orchestrator.handoff_category([name]) == "SELF_HARM_RISK", name

    def test_coercion_synonyms(self):
        for name in ("COERCION", "COERCION_RISK", "THREAT", "BLACKMAIL", "EXTORTION"):
            assert orchestrator.handoff_category([name]) == "COERCION_RISK", name

    def test_financial_distress_is_only_chosen_when_actually_flagged(self):
        """It stopped being the fallback. It is still the answer for the case
        it was written for."""
        assert orchestrator.handoff_category(["FINANCIAL_DISTRESS"]) == "FINANCIAL_DISTRESS"

    def test_nothing_at_all_is_still_safe(self):
        assert orchestrator.handoff_category([]) == "GENERIC_DISTRESS"
        assert orchestrator.handoff_category([], None) == "GENERIC_DISTRESS"

    def test_an_intent_that_means_nothing_here_is_ignored(self):
        assert orchestrator.handoff_category([], "PORTFOLIO_QUERY") == "GENERIC_DISTRESS"

    def test_precedence_is_worst_first(self):
        assert orchestrator.handoff_category(
            ["FINANCIAL_DISTRESS", "COERCION"]
        ) == "COERCION_RISK"
        assert orchestrator.handoff_category(
            ["MENTAL_HEALTH", "FINANCIAL_DISTRESS"]
        ) == "MENTAL_HEALTH_DISCLOSURE"

    def test_every_category_has_an_instruction_and_a_notice_entry(self):
        """A category reachable from the table but missing from either dict
        would raise KeyError inside the handoff -- on a distress turn."""
        for category in set(orchestrator._FLAG_SYNONYMS.values()) | {"GENERIC_DISTRESS"}:
            assert category in orchestrator._HANDOFF_INSTRUCTIONS, category
            assert category in orchestrator._CATEGORY_NOTICES, category


class TestResearchCarriesTheCaller:
    """The uploaded-document half of retrieval.

    `market_research_node` is the only place a search is issued, so it is the
    only place the caller's identity can be attached. Without it every search
    is anonymous and a user's own uploads are invisible to them.
    """

    @pytest.mark.asyncio
    async def test_a_signed_in_turn_forwards_the_user(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}
        patched_llm.set_response("{}")

        await orchestrator.market_research_node(
            {**base_state, "user_id": "11111111-1111-1111-1111-111111111111"}
        )

        assert fake_mcp.calls[0][1]["user_id"] == (
            "11111111-1111-1111-1111-111111111111"
        )

    @pytest.mark.asyncio
    async def test_an_anonymous_turn_sends_none_not_the_unknown_sentinel(
        self, fake_mcp, patched_llm, base_state
    ):
        """The other nodes fall back to the string "unknown". Here that would
        be a user id that matches nobody -- which reads as a narrowing filter
        rather than as "there is no one here", and hides the difference
        between the two from anything downstream."""
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}
        patched_llm.set_response("{}")

        await orchestrator.market_research_node({**base_state, "user_id": None})

        assert fake_mcp.calls[0][1]["user_id"] is None


class TestOwnDocumentsGetTheirOwnSlots:
    """Kullanıcının yüklediği belge, haberle aynı sıralamada yarışmaz.

    Ölçüldü: bir kullanıcı bilanço tablosu yükledi ve "EBITDA marjı ve
    hasılat" sorgusu belgeyi HİÇ döndürmedi. Belge 0,605 benzerlikle
    eşleşiyordu; binlerce haber parçası arasında ilk yirmiye giremiyordu.
    Kendi yüklediği dosyayı bir daha göremeyen bir yükleme özelliği,
    çalışmayan bir özelliktir.
    """

    def _plan(self, patched_llm):
        patched_llm.set_response("{}")

    @pytest.mark.asyncio
    async def test_a_second_search_is_scoped_to_the_users_uploads(
        self, fake_mcp, patched_llm, base_state
    ):
        self._plan(patched_llm)
        fake_mcp.responses["rag_semantic_market_search"] = {
            "results": [{"chunk_id": "news-1"}]
        }

        await orchestrator.market_research_node({**base_state, "user_id": "u-1"})

        assert len(fake_mcp.calls) == 2
        _, second = fake_mcp.calls[1]
        assert second["filters"] == {
            "categories": [orchestrator.OWN_DOCUMENT_CATEGORY]
        }
        assert second["top_k"] == orchestrator.OWN_DOCUMENT_SLOTS

    @pytest.mark.asyncio
    async def test_own_documents_come_first_and_news_is_not_dropped(
        self, fake_mcp, patched_llm, base_state
    ):
        """Kullanıcının kendi dosyası, sorduğu soruya cevap veren kaynakların
        en olası olanı -- ama haberin yerini almıyor, önüne ekleniyor."""
        self._plan(patched_llm)
        fake_mcp.responses["rag_semantic_market_search"] = [
            {"results": [{"chunk_id": "news-1"}, {"chunk_id": "news-2"}]},
            {"results": [{"chunk_id": "doc-1"}]},
        ]

        out = await orchestrator.market_research_node(
            {**base_state, "user_id": "u-1"}
        )

        ids = [r["chunk_id"] for r in out["specialist_output"]["data"]["results"]]
        assert ids == ["doc-1", "news-1", "news-2"]

    @pytest.mark.asyncio
    async def test_a_chunk_found_by_both_searches_appears_once(
        self, fake_mcp, patched_llm, base_state
    ):
        self._plan(patched_llm)
        fake_mcp.responses["rag_semantic_market_search"] = [
            {"results": [{"chunk_id": "doc-1"}, {"chunk_id": "news-1"}]},
            {"results": [{"chunk_id": "doc-1"}]},
        ]

        out = await orchestrator.market_research_node(
            {**base_state, "user_id": "u-1"}
        )

        ids = [r["chunk_id"] for r in out["specialist_output"]["data"]["results"]]
        assert ids == ["doc-1", "news-1"]

    @pytest.mark.asyncio
    async def test_an_empty_news_search_is_no_longer_empty(
        self, fake_mcp, patched_llm, base_state
    ):
        """Haberde bir şey çıkmadı ama kullanıcının belgesi cevap veriyor.
        "Kaynak bulunamadı" demek yanlış olurdu."""
        self._plan(patched_llm)
        fake_mcp.responses["rag_semantic_market_search"] = [
            {"results": []},
            {"results": [{"chunk_id": "doc-1"}]},
        ]

        out = await orchestrator.market_research_node(
            {**base_state, "user_id": "u-1"}
        )

        assert out["specialist_output"]["status"] == "OK"

    @pytest.mark.asyncio
    async def test_an_anonymous_turn_makes_only_one_search(
        self, fake_mcp, patched_llm, base_state
    ):
        self._plan(patched_llm)
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}

        await orchestrator.market_research_node({**base_state, "user_id": None})

        assert len(fake_mcp.calls) == 1

    @pytest.mark.asyncio
    async def test_no_uploaded_documents_leaves_the_result_alone(
        self, fake_mcp, patched_llm, base_state
    ):
        self._plan(patched_llm)
        fake_mcp.responses["rag_semantic_market_search"] = [
            {"results": [{"chunk_id": "news-1"}]},
            {"results": []},
        ]

        out = await orchestrator.market_research_node(
            {**base_state, "user_id": "u-1"}
        )

        ids = [r["chunk_id"] for r in out["specialist_output"]["data"]["results"]]
        assert ids == ["news-1"]

    @pytest.mark.asyncio
    async def test_a_failed_news_search_is_not_papered_over(
        self, fake_mcp, patched_llm, base_state
    ):
        """"Kaynaklara ulaşılamadı" gerçek bir kesintiyi bildiriyor; onu
        kullanıcının kendi belgesiyle örtmek, çalışmayan bir kaynağı
        çalışıyor gibi göstermek olur."""
        self._plan(patched_llm)
        fake_mcp.responses["rag_semantic_market_search"] = MCPUnavailable("down")

        out = await orchestrator.market_research_node(
            {**base_state, "user_id": "u-1"}
        )

        assert out["specialist_output"]["status"] == "ERROR"
        # İkinci arama hiç denenmedi.
        assert len(fake_mcp.calls) == 1

    @pytest.mark.asyncio
    async def test_a_failed_own_document_search_keeps_the_news(
        self, fake_mcp, patched_llm, base_state
    ):
        """İkincil bir arama turu düşürmemeli: haber sonucu elde."""
        self._plan(patched_llm)
        # Kuyruk: birinci çağrı haberi döner, ikincisi patlar.
        fake_mcp.responses["rag_semantic_market_search"] = [
            {"results": [{"chunk_id": "news-1"}]},
            MCPUnavailable("gone"),
        ]

        out = await orchestrator.market_research_node(
            {**base_state, "user_id": "u-1"}
        )

        ids = [r["chunk_id"] for r in out["specialist_output"]["data"]["results"]]
        assert ids == ["news-1"]

    @pytest.mark.asyncio
    async def test_personal_documents_use_their_own_threshold(
        self, fake_mcp, patched_llm, base_state
    ):
        """0,45 haber için doğru: binlerce parçada alakasızı elemek gerekiyor.
        Kişisel belgelerde elenecek bir sel yok -- ve o eşik, kullanıcının
        kendi yüklediği dosyayı kendi cümlesiyle sorduğunda (ölçülen: 0,289)
        eliyordu."""
        patched_llm.set_response("{}")
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [{"chunk_id": "c1"}]}

        await orchestrator.market_research_node({**base_state, "user_id": "u-1"})

        _, news = fake_mcp.calls[0]
        _, own = fake_mcp.calls[1]
        assert own["min_similarity"] < news["min_similarity"]
        assert own["min_similarity"] == orchestrator.OWN_DOCUMENT_MIN_SIMILARITY


class TestConditionalHedgeSurvivesTheGate:
    """Koşullu bir turun çekincesi kapının HER dalından çıkmalı.

    `_keep_crisis` ile aynı ders: prompt tavsiyedir. Araç sözleşmesi
    "`statement`'ı çekincesiyle birlikte olduğu gibi aktar" diyor ve ÖLÇÜLDÜ --
    canlı bir turda model cümleyi yeniden yazdı ve kapanış çekincesini
    düşürdü. Geriye kalan "portföyünüzün değeri yaklaşık %6,8 azalır" idi:
    koşulsuz, çekincesiz, ve ölçümün söylemediği bir kesinlikte.
    """

    def _state(self, tool="run_portfolio_scenario", **extra):
        return {"user_message": "dolar yükselirse", "tools_used": [tool], **extra}

    def test_the_hedge_is_added_when_the_model_drops_it(self):
        out = orchestrator._keep_crisis(
            self._state(), {"final_output": "Portföyünüz yaklaşık %6,8 azalır."}
        )
        assert orchestrator.SCENARIO_HEDGE_TR in out["disclosures"]

    def test_it_is_not_repeated_when_the_answer_already_carries_it(self):
        out = orchestrator._keep_crisis(
            self._state(),
            {"final_output": "... — ancak geçmiş fiyat hareketi geleceği belirlemez."},
        )
        assert out.get("disclosures") in (None, [])

    def test_it_is_not_repeated_when_a_disclosure_already_carries_it(self):
        out = orchestrator._keep_crisis(
            self._state(),
            {"final_output": "x", "disclosures": ["Geçmiş fiyat hareketi geleceği belirlemez."]},
        )
        assert len(out["disclosures"]) == 1

    @pytest.mark.parametrize("tool", sorted(orchestrator.HEDGED_TOOLS))
    def test_every_conditional_tool_is_covered(self, tool):
        out = orchestrator._keep_crisis(self._state(tool), {"final_output": "x"})
        assert orchestrator.SCENARIO_HEDGE_TR in out["disclosures"]

    def test_a_turn_that_used_no_conditional_tool_gets_nothing(self):
        """Fiyat sorusuna koşullu bir çekince eklemek, orada olmayan bir
        koşulluluk vaat ederdi."""
        out = orchestrator._keep_crisis(
            self._state("get_market_data"), {"final_output": "THYAO 291,75 TL."}
        )
        assert out.get("disclosures") in (None, [])

    def test_a_blocked_turn_still_carries_it(self):
        """Kapının BLOCK dalı dahil: engellenmiş bir turda da kullanıcı
        sayının ne olduğunu bilmeli."""
        out = orchestrator._keep_crisis(
            self._state(), {"compliance_verdict": "BLOCK", "final_output": "..."}
        )
        assert orchestrator.SCENARIO_HEDGE_TR in out["disclosures"]

    def test_it_sits_beside_the_crisis_notices_not_instead_of_them(self):
        out = orchestrator._keep_crisis(
            self._state(crisis_notices=["ALO 183"]), {"final_output": "x"}
        )
        assert "ALO 183" in out["disclosures"]
        assert orchestrator.SCENARIO_HEDGE_TR in out["disclosures"]

    def test_the_hedge_says_the_number_is_a_measurement(self):
        """Genel uygunluk açıklaması bunun yerini tutmuyor: o içeriğin
        danışmanlık olmadığını söylüyor, bu sayının tahmin olmadığını."""
        assert "tahmin değil" in orchestrator.SCENARIO_HEDGE_TR
        assert "geleceği belirlemez" in orchestrator.SCENARIO_HEDGE_TR


class TestUnmeasurableFactorRouting:
    """Ölçülemeyen makro faktör + kullanıcının kendi portföyü -> risk ajanı.

    Kodda, çünkü ÖLÇÜLDÜ: "faizler artarsa portföyüm nasıl etkilenir" İKİ ayrı
    denemede de EDUCATION_AGENT'a gitti -- yönlendirme kuralı prompt'a
    yazıldıktan sonra da. Bu modülün kendi dersi: prompt tavsiyedir.

    Yanlış cevabın iki zararı vardı. "Veriler alınamadı" bir KESİNTİ gibi
    okunuyordu, oysa faiz serisi yapısal olarak yok; ve kullanıcıdan
    pozisyonlarını YAPIŞTIRMASI isteniyordu, ki MCP sözleşmesi pozisyon
    verisini kullanıcı beyanından almayı açıkça yasaklıyor.
    """

    @pytest.mark.parametrize("message", [
        "faizler artarsa portföyüm nasıl etkilenir",
        "faiz artışı pozisyonlarımı nasıl etkiler",
        "enflasyon yükselirse portföyüm ne olur",
        "TÜFE çıkarsa yatırımlarım etkilenir mi",
    ])
    def test_it_forces_the_agent_that_knows_the_limit(self, message):
        assert orchestrator._forced_agent(message) == "RISK_STRATEGY_AGENT"

    @pytest.mark.parametrize("message", [
        "faiz nedir",
        "enflasyon nasıl hesaplanır",
        "merkez bankası faizi artırdı mı",
    ])
    def test_a_definition_question_is_left_alone(self, message):
        """"Faiz nedir" bir tanım sorusu ve EDUCATION_AGENT'ın işi. Onu da
        çekmek, tool'suz bir soruyu tool'lu bir ajana yollamak olurdu."""
        assert orchestrator._forced_agent(message) is None

    @pytest.mark.parametrize("message", [
        "dolar yükselirse portföyüm ne olur",
        "borsa düşerse pozisyonlarım ne kaybeder",
        "altın çıkarsa portföyüm etkilenir mi",
    ])
    def test_a_measurable_factor_is_not_touched(self, message):
        """Ölçülebilen faktörlerin yolu zaten doğru çalışıyor; onları da
        zorlamak, çalışan bir yolun üstüne ikinci bir karar koymak olurdu."""
        assert orchestrator._forced_agent(message) is None

    def test_a_turn_about_nothing_financial_is_not_touched(self):
        assert orchestrator._forced_agent("merhaba nasılsın") is None

    @pytest.mark.asyncio
    async def test_the_override_applies_in_the_router(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["classify_and_route_intent"] = {
            "target_agent": "EDUCATION_AGENT", "confidence": 0.9, "safety_flags": [],
        }
        patched_llm.set_response('{"target_agent": "EDUCATION_AGENT", "confidence": 0.9}')
        out = await orchestrator.router_node(
            {**base_state, "user_message": "faizler artarsa portföyüm nasıl etkilenir"}
        )
        assert out["target_agent"] == "RISK_STRATEGY_AGENT"

    @pytest.mark.asyncio
    async def test_the_override_does_not_fire_when_the_router_already_agrees(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["classify_and_route_intent"] = {
            "target_agent": "RISK_STRATEGY_AGENT", "confidence": 0.9, "safety_flags": [],
        }
        patched_llm.set_response('{"target_agent": "RISK_STRATEGY_AGENT", "confidence": 0.9}')
        out = await orchestrator.router_node(
            {**base_state, "user_message": "faizler artarsa portföyüm ne olur"}
        )
        assert out["target_agent"] == "RISK_STRATEGY_AGENT"

    @pytest.mark.asyncio
    async def test_the_override_survives_a_classifier_outage(
        self, fake_mcp, patched_llm, base_state
    ):
        """ASIL burada gerekiyor. Sınıflandırıcı düştüğünde tur
        EDUCATION_AGENT'a düşüyor ve o ajan hiçbir araç tutmuyor; ölçüldü,
        sonuç "gerekli veriler alınamadı" oldu ve kullanıcı bunu bir kesinti
        sandı. Oysa faiz serisinin yokluğunu söylemek için model gerekmiyor."""
        fake_mcp.responses["classify_and_route_intent"] = {
            "target_agent": "EDUCATION_AGENT", "confidence": 0.9, "safety_flags": [],
        }
        async def _down(_messages):
            raise RuntimeError("rate limit")

        patched_llm.ainvoke = _down
        out = await orchestrator.router_node(
            {**base_state, "user_message": "faizler artarsa portföyüm nasıl etkilenir"}
        )
        assert out["target_agent"] == "RISK_STRATEGY_AGENT"
        assert any("router:" in e for e in out["errors"])

    @pytest.mark.asyncio
    async def test_an_ordinary_turn_still_degrades_to_education_on_outage(
        self, fake_mcp, patched_llm, base_state
    ):
        """Sınıflandırılmamış bir turu araçlı bir ajana yollamak, birinin
        pozisyonlarını okuyan bir araca kör bir tur göndermek olurdu."""
        fake_mcp.responses["classify_and_route_intent"] = {
            "target_agent": "PORTFOLIO_AGENT", "confidence": 0.9, "safety_flags": [],
        }
        async def _down(_messages):
            raise RuntimeError("rate limit")

        patched_llm.ainvoke = _down
        out = await orchestrator.router_node(base_state)
        assert out["target_agent"] == "EDUCATION_AGENT"

    @pytest.mark.asyncio
    async def test_distress_reaches_a_human_even_when_the_classifier_fails(
        self, fake_mcp, patched_llm, base_state
    ):
        """Ana yolda `DISTRESS_SIGNAL` -> HUMAN_HANDOFF kontrolü vardı, hata
        yolunda YOKTU: ön süzgecin ezilebilir olarak işaretlediği bir sıkıntı
        sinyali, sınıflandırıcı düştüğünde EDUCATION_AGENT'a iniyordu."""
        fake_mcp.responses["classify_and_route_intent"] = {
            "target_agent": "EDUCATION_AGENT", "confidence": 0.9,
            "safety_flags": ["DISTRESS_SIGNAL"],
        }
        async def _down(_messages):
            raise RuntimeError("rate limit")

        patched_llm.ainvoke = _down
        out = await orchestrator.router_node(
            {**base_state, "user_message": "her şeyi kaybettim, yaşamak istemiyorum"}
        )
        assert out["target_agent"] == "HUMAN_HANDOFF"

    @pytest.mark.asyncio
    async def test_distress_beats_the_override_on_the_outage_path_too(
        self, fake_mcp, patched_llm, base_state
    ):
        fake_mcp.responses["classify_and_route_intent"] = {
            "target_agent": "EDUCATION_AGENT", "confidence": 0.9,
            "safety_flags": ["DISTRESS_SIGNAL"],
        }
        async def _down(_messages):
            raise RuntimeError("rate limit")

        patched_llm.ainvoke = _down
        out = await orchestrator.router_node({
            **base_state,
            "user_message": "faizler yüzünden portföyüm bitti, yaşamak istemiyorum",
        })
        assert out["target_agent"] == "HUMAN_HANDOFF"

    @pytest.mark.asyncio
    async def test_safety_still_wins_over_the_override(
        self, fake_mcp, patched_llm, base_state
    ):
        """Güvenlik devredilemez. Sıkıntı sinyali taşıyan bir tur, içinde
        "faiz" ve "portföyüm" geçse bile insana gider."""
        fake_mcp.responses["classify_and_route_intent"] = {
            "target_agent": "EDUCATION_AGENT", "confidence": 0.9,
            "safety_flags": ["DISTRESS_SIGNAL"],
        }
        patched_llm.set_response('{"target_agent": "EDUCATION_AGENT", "confidence": 0.9}')
        out = await orchestrator.router_node({
            **base_state,
            "user_message": "faizler yüzünden portföyüm bitti, yaşamak istemiyorum",
        })
        assert out["target_agent"] == "HUMAN_HANDOFF"


class TestProviderErrorsAreNamedCorrectly:
    """Kalıcı bir hatayı geçici diye anlatmak, kullanıcıyı hiç sonuçlanmayacak
    bir döngüde tutar.

    Kullanıcı bunu bizden önce fark etti: "faizler artarsa portföyüm nasıl
    etkilenir" her seferinde "yoğunluk sınırına takıldım, birkaç dakika sonra
    deneyin" cevabı veriyordu, ama aynı oturumda sorulan başka sorular ANINDA
    cevaplanıyordu. Sağlayıcı kaydı sebebi söylüyordu: 413, 8.393 token
    istendi, sınır 8.000 -- yani beklemek hiçbir zaman işe yaramayacaktı.
    """

    def test_a_too_large_request_is_not_called_a_quota_problem(self):
        exc = Exception(
            "Error code: 413 - {'error': {'message': 'Request too large for model "
            "`openai/gpt-oss-120b` ... on tokens per minute (TPM): Limit 8000, "
            "Requested 8393, please reduce your message size and try again', "
            "'code': 'rate_limit_exceeded'}}"
        )
        message = orchestrator._failure_message(exc)
        assert message == orchestrator.TOO_LARGE_TR
        assert message != orchestrator.RATE_LIMITED_TR

    def test_the_size_message_does_not_tell_the_user_to_wait(self):
        """Beklemek düzeltmiyor; "birkaç dakika sonra deneyin" demek yanlış."""
        assert "Beklemek bunu değiştirmez" in orchestrator.TOO_LARGE_TR
        assert "birkaç dakika" not in orchestrator.TOO_LARGE_TR

    def test_a_real_quota_refusal_still_says_waiting_helps(self):
        """Gerçek kota gerçekten geçici; o cümle kaybolmamalı."""
        exc = Exception("Error code: 429 - rate limit reached, please try again")
        assert orchestrator._failure_message(exc) == orchestrator.RATE_LIMITED_TR

    def test_an_unrelated_failure_stays_generic(self):
        assert orchestrator._failure_message(
            Exception("connection reset by peer")
        ) == orchestrator.GENERIC_FAILURE_TR

    @pytest.mark.parametrize("text", [
        "context length exceeded", "maximum context length is 8192",
        "Request too large", "please reduce your message size",
    ])
    def test_every_size_wording_is_recognised(self, text):
        assert orchestrator._failure_message(Exception(text)) == orchestrator.TOO_LARGE_TR


class TestSynthesisPayloadFits:
    """Gövde, sağlayıcının tek istek bütçesine sığmak zorunda.

    `technical_posture` eklendiğinde risk turunun gövdesi 3.269 karakter
    büyüdü ve toplam sınırı aştı. Bu bir GERİLEME düzeltmesi.
    """

    POSTURE = {
        "base_currency": "TRY",
        "summary": {"below_sma_50": 2, "statement": "3 pozisyonunuzun 2'si..."},
        "positions": [
            {"symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
             "trend": "UPTREND", "narrative": "AKBNK, 50 günlük...",
             "signals": {f"f{i}": i for i in range(20)}},
        ],
        "unconvertible": ["AAPL"],
    }

    def test_the_writer_gets_the_sentences_not_the_indicator_block(self):
        """Yirmi alanlık `signals` bloğu EKRANIN ihtiyacı. Yazara alan
        adlarını göndermek, onları anmayı yasaklayan kuralın önüne yem
        koymak."""
        slim = orchestrator._slim_posture(self.POSTURE)
        assert "signals" not in slim["positions"][0]
        assert slim["positions"][0]["narrative"] == "AKBNK, 50 günlük..."
        assert slim["summary"]["statement"] == "3 pozisyonunuzun 2'si..."

    def test_the_trim_actually_shrinks_the_payload(self):
        import json as _json
        full = len(_json.dumps(self.POSTURE, ensure_ascii=False))
        slim = len(_json.dumps(orchestrator._slim_posture(self.POSTURE), ensure_ascii=False))
        assert slim < full

    def test_holdings_left_out_of_the_weight_survive_the_trim(self):
        """Kırpma, portföyün bir kısmını yok saymamalı."""
        assert orchestrator._slim_posture(self.POSTURE)["unconvertible"] == ["AAPL"]

    def test_an_empty_posture_does_not_crash_the_trim(self):
        assert orchestrator._slim_posture({}) == {
            "summary": {}, "positions": [], "unconvertible": [],
        }

    def test_a_payload_within_budget_is_untouched(self):
        import json as _json
        payload = {"status": "OK", "data": {"x": 1}}
        assert orchestrator._fit_payload(payload) == _json.dumps(
            payload, ensure_ascii=False, indent=2
        )

    def test_an_oversized_payload_is_cut_and_the_cut_is_logged(self, caplog):
        """Sessiz kırpma, modele bozuk bir gövde verip sebebini gizlemek
        olurdu."""
        payload = {"rows": ["x" * 200 for _ in range(200)]}
        with caplog.at_level("WARNING"):
            out = orchestrator._fit_payload(payload)
        assert len(out) == orchestrator.SYNTHESIS_PAYLOAD_CHARS
        assert any("truncated" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_the_risk_turn_carries_the_slim_posture(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        patched_llm.set_response("{}")
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["get_portfolio_technicals"] = self.POSTURE
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(base_state)
        posture = out["specialist_output"]["data"]["technical_posture"]
        assert "signals" not in posture["positions"][0]
        assert posture["summary"]["statement"] == "3 pozisyonunuzun 2'si..."
