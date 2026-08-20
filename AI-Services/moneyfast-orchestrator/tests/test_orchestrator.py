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
        assert args["min_similarity"] == 0.35

    @pytest.mark.asyncio
    async def test_only_the_last_six_turns_are_sent_as_context(
        self, fake_mcp, patched_llm
    ):
        patched_llm.set_response("{}")
        fake_mcp.responses["rag_semantic_market_search"] = {"results": [1]}
        history = [{"role": "user", "content": f"turn {i}"} for i in range(20)]
        await orchestrator.market_research_node(
            {"user_message": "x", "conversation_history": history}
        )
        assert len(fake_mcp.calls[0][1]["conversation_context"]) == 6

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
    @pytest.mark.asyncio
    async def test_fetches_positions_before_computing_metrics(
        self, fake_mcp, patched_llm, base_state, positions_payload
    ):
        """The risk tool has no position access by design, so the graph makes
        two calls in a fixed order."""
        patched_llm.set_response('{"arguments": {"lookback": "3Y"}}')
        fake_mcp.responses["get_portfolio_positions"] = positions_payload
        fake_mcp.responses["calculate_portfolio_risk_metrics"] = {"metrics": {"beta": 1.1}}
        out = await orchestrator.risk_node(base_state)
        assert [name for name, _ in fake_mcp.calls] == [
            "get_portfolio_positions", "calculate_portfolio_risk_metrics"
        ]
        assert out["tools_used"] == [
            "get_portfolio_positions", "calculate_portfolio_risk_metrics"
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
        risk_args = fake_mcp.calls[1][1]
        assert risk_args["positions"] == positions_payload["positions"]
        assert risk_args["lookback"] == "1Y"
        assert risk_args["confidence_level"] == 0.95
        assert risk_args["rebalance_assumption"] == "BUY_AND_HOLD"

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
        out = await orchestrator.handoff_node(
            {**base_state, "safety_flags": ["DISTRESS_SIGNAL"]}
        )
        payload = out["specialist_output"]
        assert payload["status"] == "HANDOFF"
        assert payload["safety_flags"] == ["DISTRESS_SIGNAL"]
        assert "Do not screen" in payload["instruction"]
        assert fake_mcp.calls == []

    @pytest.mark.asyncio
    async def test_missing_safety_flags_defaults_to_empty(self, fake_mcp, base_state):
        out = await orchestrator.handoff_node(base_state)
        assert out["specialist_output"]["safety_flags"] == []


# ==========================================================================
# synthesis_node
# ==========================================================================
class TestSynthesisNode:
    @pytest.mark.asyncio
    async def test_produces_a_draft_from_specialist_output(self, patched_llm, base_state):
        patched_llm.set_response("**Kullandığım filtreler:** ...\n\nPortföyünüzde 500 lot THYAO var.")
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
        """Guards the context window: a 10k-row payload must not blow the turn."""
        huge = {"data": {"rows": ["x" * 100 for _ in range(500)]}}
        await orchestrator.synthesis_node({**base_state, "specialist_output": huge})
        user = patched_llm.calls[0][1].content
        assert len(user) < 13000

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
        """Groq 429 or a network drop. The user gets a plain Turkish apology,
        never a stack trace and never a fabricated answer."""
        mocker.patch.object(
            orchestrator, "_llm_text", side_effect=RuntimeError("groq 429 rate limited")
        )
        with caplog.at_level("ERROR", logger="moneyfast.graph"):
            out = await orchestrator.synthesis_node(base_state)
        assert out["draft_response"] == ""
        assert out["final_output"] == orchestrator.GENERIC_FAILURE_TR
        assert "synthesis" in out["errors"][0]

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

    def test_clarification_short_circuits_before_any_specialist(self):
        """Asking a question needs no tool call, so skip straight to synthesis."""
        state = {
            "needs_clarification": True,
            "target_agent": "PORTFOLIO_AGENT",
            "primary_intent": "PORTFOLIO_INQUIRY",
            "safety_flags": [],
        }
        assert orchestrator.route_after_router(state) == "synthesis"

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

    def test_clarification_takes_precedence_over_the_safety_check(self):
        """Documents the precedence order as it actually is, so a change to it
        is a deliberate edit rather than a silent regression."""
        state = {
            "needs_clarification": True,
            "primary_intent": "UNSAFE",
            "safety_flags": ["DISTRESS_SIGNAL"],
            "target_agent": "PORTFOLIO_AGENT",
        }
        assert orchestrator.route_after_router(state) == "synthesis"

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

    def test_history_summary_keeps_the_last_six_turns(self):
        history = [{"role": "user", "content": f"turn {i}"} for i in range(10)]
        summary = orchestrator._history_summary({"conversation_history": history})
        assert "turn 9" in summary
        assert "turn 3" not in summary

    def test_history_summary_defaults_a_missing_role(self):
        summary = orchestrator._history_summary({"conversation_history": [{"content": "x"}]})
        assert summary == "user: x"

    def test_history_summary_is_capped_in_length(self):
        """Long histories must not blow the classifier's context window."""
        history = [{"role": "user", "content": "x" * 5000} for _ in range(6)]
        assert len(orchestrator._history_summary({"conversation_history": history})) <= 2000

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

    def test_idempotency_key_varies_with_history_length(self, base_state):
        later = {**base_state, "conversation_history": [{"role": "user", "content": "x"}]}
        assert orchestrator._idempotency_key(base_state) != orchestrator._idempotency_key(later)

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
        assert args["min_similarity"] == 0.35

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


class TestTransferRefusal:
    """Banking is unimplemented. A transfer staged through the securities path
    was costed with brokerage commission and BSMV, rendered by the widget as a
    "Satım" with a blank ticker, and confirmed into a proposal that moved
    nothing. It looked like it worked, which is worse than a refusal."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["TRANSFER", "EFT", "HAVALE", "TRANSFER_INTERNAL"])
    async def test_a_transfer_is_declined_rather_than_staged(
        self, fake_mcp, patched_llm, base_state, kind
    ):
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "%s", "notional_amount": {"amount": 200, "currency": "TRY"},'
            ' "source_account_id": "1", "destination_account_id": "2"}}' % kind
        )
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "UNSUPPORTED"
        assert not fake_mcp.calls, "nothing may be staged"

    @pytest.mark.asyncio
    async def test_a_securities_order_is_unaffected(self, fake_mcp, patched_llm, base_state):
        fake_mcp.responses["prepare_transaction_proposal"] = {
            "proposal_id": "PROP-1", "confirmation_required": True, "status": "PENDING_USER_CONFIRMATION",
        }
        patched_llm.set_response(
            '{"arguments": {"transaction_type": "BUY", "quantity": 10,'
            ' "instrument": {"symbol": "THYAO"}, "source_account_id": "1"}}'
        )
        out = await orchestrator.transaction_node(base_state)
        assert out["specialist_output"]["status"] == "OK"


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
