"""MoneyFast LangGraph orchestrator.

Graph shape:

    START
      -> router_node                 (safety pre-filter, then Groq routing)
      -> one of:
           portfolio_node            (get_portfolio_positions)
           market_data_node          (get_market_data)
           market_research_node      (rag_semantic_market_search)
           risk_node                 (positions, then risk metrics)
           transaction_node          (prepare_transaction_proposal, staging)
           handoff_node              (unsafe / distress, no tools)
           synthesis_node            (education, smalltalk, clarification)
      -> synthesis_node              (Turkish markdown draft)
      -> compliance_gate_node        (validate_compliance_rules)
      -> synthesis_node on BLOCK, up to MAX_COMPLIANCE_REVISIONS
      -> END

Fail-closed is the invariant: if compliance cannot run, or still blocks after
the revision budget, the user gets the compliance-supplied refusal text and
never the draft.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from functools import lru_cache
from typing import Any, Literal, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from mcp_client import MCPToolError, MCPUnavailable, get_mcp_client
from prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    REVISION_TASK_TEMPLATE,
    ROUTER_PROMPT,
    ROUTER_TASK_TEMPLATE,
    SPECIALIST_PROMPTS,
    SYNTHESIS_TASK_TEMPLATE,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("moneyfast.graph")

JURISDICTION = os.getenv("JURISDICTION", "TR")
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "tr-TR")
MAX_COMPLIANCE_REVISIONS = int(os.getenv("MAX_COMPLIANCE_REVISIONS", "1"))

GENERIC_FAILURE_TR = (
    "Şu anda yanıtı hazırlayamadım. Kısa bir süre sonra tekrar deneyebilir "
    "misiniz?"
)
#: Transaction types the backend recognises as money transfers.
TRANSFER_TYPES = frozenset({"TRANSFER", "EFT", "HAVALE", "TRANSFER_INTERNAL", "TRANSFER_EXTERNAL"})

TRANSFER_UNSUPPORTED_TR = (
    "Para transferi şu anda desteklenmiyor; bu asistan yalnızca yatırım "
    "işlemlerini hazırlayabiliyor. Transferi bankacılık ekranından "
    "yapmanız gerekiyor."
)

DATA_FAILURE_TR = (
    "Verilere şu anda ulaşamadım, bu yüzden sayı paylaşmayacağım. "
    "Birazdan tekrar denememi ister misiniz?"
)

AGENTS = [
    "PORTFOLIO_AGENT",
    "MARKET_DATA_AGENT",
    "MARKET_RESEARCH_AGENT",
    "RISK_STRATEGY_AGENT",
    "TRANSACTION_AGENT",
    "EDUCATION_AGENT",
    "SMALLTALK_AGENT",
    "HUMAN_HANDOFF",
]


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class MoneyFastState(TypedDict, total=False):
    # Required by the architecture spec
    user_message: str
    conversation_history: list[dict[str, str]]
    primary_intent: str
    target_agent: str
    specialist_output: dict[str, Any]
    draft_response: str
    compliance_verdict: str
    final_output: str
    #: Required notices, carried separately so the UI can place them.
    disclosures: list[str]
    # Operational
    user_id: str
    locale: str
    entities: dict[str, Any]
    safety_flags: list[str]
    needs_clarification: bool
    clarifying_question: Optional[str]
    tools_used: list[str]
    compliance: dict[str, Any]
    blocked_reason: Optional[str]
    revision_count: int
    errors: list[str]


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
@lru_cache(maxsize=2)
def get_llm(fast: bool = False):
    """Lazy so importing this module never requires a key."""
    from langchain_groq import ChatGroq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    model = (
        os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
        if fast
        else os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    )
    return ChatGroq(model=model, temperature=0, api_key=api_key)


async def _llm_text(system: str, user: str, fast: bool = False) -> str:
    llm = get_llm(fast)
    reply = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    return (reply.content or "").strip()


async def _llm_json(system: str, user: str, fast: bool = False) -> dict[str, Any]:
    raw = await _llm_text(system, user, fast=fast)
    return _parse_json(raw)


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        log.warning("llm returned no json object: %.160s", raw)
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        log.warning("llm returned malformed json: %.160s", raw)
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
async def router_node(state: MoneyFastState) -> dict[str, Any]:
    """Classify the turn, in two passes with different trust levels.

    Pass 1 is the MCP safety pre-filter: deterministic regex, no model. It
    decides distress routing on its own, because a safety gate that depends on
    the model it is guarding fails open exactly when the model misbehaves.

    Pass 2 asks the model for the topic. Its answer is accepted for routing
    only; it can add safety flags but never clear one, and it cannot override a
    non-overridable decision from pass 1.

    Failure is not fatal: an unreachable MCP server or an unparseable model
    reply both degrade to EDUCATION_AGENT, which holds no user data and can
    emit no figures. Guessing a specialist here would send an unclassified
    turn at a tool that reads someone's holdings.
    """
    safety: dict[str, Any] = {}
    errors: list[str] = []
    try:
        safety = await get_mcp_client().call(
            "classify_and_route_intent",
            {
                "user_message": state["user_message"],
                "conversation_summary": _history_summary(state),
                "available_agents": AGENTS,
                "locale": state.get("locale") or DEFAULT_LOCALE,
                "user_context_flags": {"has_linked_account": bool(state.get("user_id"))},
            },
        )
    except (MCPUnavailable, MCPToolError) as exc:
        # Losing the pre-filter is serious but not a reason to drop the turn:
        # the model is still asked, and its own safety_flags still apply.
        log.error("safety pre-filter unavailable: %s", exc)
        errors.append(f"safety_prefilter: {exc}")

    flags = list(safety.get("safety_flags") or [])

    if safety.get("is_overridable") is False:
        target = safety.get("target_agent") or "HUMAN_HANDOFF"
        log.warning("routing fixed by safety pre-filter: agent=%s flags=%s", target, flags)
        return {
            "primary_intent": safety.get("primary_intent") or "DISTRESS",
            "target_agent": target,
            "entities": {},
            "safety_flags": flags,
            "needs_clarification": False,
            "clarifying_question": None,
            "tools_used": ["classify_and_route_intent"],
            "revision_count": 0,
            "errors": errors,
        }

    try:
        result = await _llm_json(
            ROUTER_PROMPT,
            ROUTER_TASK_TEMPLATE.format(
                user_message=state["user_message"],
                conversation_summary=_history_summary(state) or "(none)",
                available_agents=", ".join(AGENTS),
                safety_flags=", ".join(flags) or "(none)",
            ),
            fast=True,
        )
    except Exception as exc:  # network, rate limit, malformed JSON
        log.error("router classification failed: %s", exc)
        return {
            "primary_intent": "OUT_OF_SCOPE",
            "target_agent": "EDUCATION_AGENT",
            "entities": {},
            "safety_flags": flags,
            "needs_clarification": False,
            "clarifying_question": None,
            "tools_used": ["classify_and_route_intent"],
            "revision_count": 0,
            "errors": errors + [f"router: {exc}"],
        }

    target = result.get("target_agent")
    if target not in AGENTS:
        # A hallucinated agent name must not fall through to a real specialist.
        log.warning("router returned unknown agent %r, falling back", target)
        target = "EDUCATION_AGENT"

    # Union, never replacement: the model may notice an injection attempt the
    # regex missed, but it may not clear a flag the regex raised.
    for flag in result.get("safety_flags") or []:
        if flag not in flags:
            flags.append(flag)
    if "DISTRESS_SIGNAL" in flags:
        target = "HUMAN_HANDOFF"

    needs_clarification = bool(result.get("needs_clarification"))
    if float(result.get("confidence") or 0) < 0.60:
        needs_clarification = True

    log.info(
        "routed intent=%s agent=%s confidence=%s flags=%s",
        result.get("primary_intent"), target, result.get("confidence"), flags,
    )
    return {
        "primary_intent": result.get("primary_intent") or "OUT_OF_SCOPE",
        "target_agent": target,
        "entities": result.get("entities") or {},
        "safety_flags": flags,
        "needs_clarification": needs_clarification,
        "clarifying_question": result.get("clarifying_question"),
        "tools_used": ["classify_and_route_intent"],
        "revision_count": 0,
        "errors": errors,
    }


async def portfolio_node(state: MoneyFastState) -> dict[str, Any]:
    plan = await _llm_json(
        SPECIALIST_PROMPTS["PORTFOLIO_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    args["user_id"] = state.get("user_id") or "unknown"
    # Reporting currency follows the session locale, not the model. It is a
    # presentation choice, and letting the model pick means a Turkish user can
    # be shown their portfolio in USD because the plan happened to say so.
    args["base_currency"] = "USD" if (state.get("locale") or DEFAULT_LOCALE).endswith("US") else "TRY"
    args.setdefault("valuation_mode", "LAST_CLOSE")
    args.setdefault("include_closed", False)
    return await _run_tool(
        state, "get_portfolio_positions", args,
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("positions"),
    )


async def market_data_node(state: MoneyFastState) -> dict[str, Any]:
    """Current prices and valuation ratios, for any instrument."""
    plan = await _llm_json(
        SPECIALIST_PROMPTS["MARKET_DATA_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    # A turn that named no instrument and no filter would otherwise screen the
    # entire universe and hand the model 50 rows to summarise.
    if not args.get("symbols") and not args.get("filters"):
        entities = state.get("entities") or {}
        tickers = entities.get("tickers") or []
        if tickers:
            args["symbols"] = tickers
    args.setdefault("top_k", 20)
    return await _run_tool(
        state, "get_market_data", args,
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("instruments"),
        repair_prompt=SPECIALIST_PROMPTS["MARKET_DATA_AGENT"],
    )


async def market_research_node(state: MoneyFastState) -> dict[str, Any]:
    plan = await _llm_json(
        SPECIALIST_PROMPTS["MARKET_RESEARCH_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    args.setdefault("query", state["user_message"])
    args.setdefault("top_k", 8)
    # Cosine thresholds are a property of the embedding model, not a product
    # constant. The tool contract documents 0.62, which is calibrated for E5;
    # the corpus is embedded with paraphrase-multilingual-MiniLM, whose scores
    # run lower. Measured against the live corpus: a clearly relevant article
    # scores 0.43-0.72 and off-topic ones sit below 0.35, so 0.62 silently
    # discarded good hits and the assistant reported "no sources found" for
    # news it was holding.
    #
    # Overridden here rather than in the tool, because the caller owns this
    # choice and the contract's default has to stay what it says.
    args["min_similarity"] = float(os.getenv("RAG_MIN_SIMILARITY", "0.35"))
    args["conversation_context"] = (state.get("conversation_history") or [])[-6:]
    return await _run_tool(
        state, "rag_semantic_market_search", args,
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("results"),
    )


async def risk_node(state: MoneyFastState) -> dict[str, Any]:
    """Two calls: the risk tool has no position access by design."""
    mcp = get_mcp_client()
    try:
        holdings = await mcp.call(
            "get_portfolio_positions",
            {"user_id": state.get("user_id") or "unknown", "base_currency": "TRY"},
        )
    except (MCPUnavailable, MCPToolError) as exc:
        return _tool_error(state, "get_portfolio_positions", exc)

    positions = holdings.get("positions") or []
    if not positions:
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "EMPTY",
                "reason": "No positions to measure.",
                "data": None,
            },
            "tools_used": (state.get("tools_used") or []) + ["get_portfolio_positions"],
        }

    plan = await _llm_json(
        SPECIALIST_PROMPTS["RISK_STRATEGY_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    args["positions"] = positions
    args.setdefault("lookback", "1Y")
    args.setdefault("confidence_level", 0.95)
    args.setdefault("rebalance_assumption", "BUY_AND_HOLD")
    out = await _run_tool(
        state, "calculate_portfolio_risk_metrics", args,
        assumptions=plan.get("assumptions") or [],
    )
    out["tools_used"] = ["get_portfolio_positions"] + (out.get("tools_used") or [])
    return out


async def transaction_node(state: MoneyFastState) -> dict[str, Any]:
    plan = await _llm_json(SPECIALIST_PROMPTS["TRANSACTION_AGENT"], _specialist_task(state))
    if plan.get("status") == "NEEDS_INPUT" or not plan.get("arguments"):
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": plan.get("missing_fields") or ["unspecified"],
                "clarification_request": plan.get("clarification_request")
                or "Which instrument, how much, and from which account?",
            }
        }
    args = dict(plan["arguments"])

    # Money transfers are not supported. Banking is unimplemented, so a
    # transfer staged here would be routed through the SECURITIES path: costed
    # with brokerage commission and BSMV, rendered by the widget as a "Satım"
    # with a blank ticker, and confirmed into a proposal that moves nothing.
    # Declining is the honest answer; the previous behaviour looked like it
    # worked, which is worse than a refusal.
    if str(args.get("transaction_type", "")).upper() in TRANSFER_TYPES:
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "UNSUPPORTED",
                "tool": None,
                "data": None,
                "instruction": TRANSFER_UNSUPPORTED_TR,
            }
        }

    # The amount must come from THIS turn. The planner sees the last six turns
    # verbatim, and with no precedence rule it read "250 lira" from the
    # previous message while the user had just said "200 lira at" -- staging a
    # figure the user never asked for in the turn they were answering.
    mismatch = _amount_not_in_current_turn(state, args)
    if mismatch is not None:
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["quantity" if "quantity" in mismatch else "notional_amount"],
                "clarification_request": (
                    f"Tutarı bu mesajda göremedim ({mismatch}). Kaç adet ya da kaç TL "
                    f"olduğunu tekrar yazar mısınız?"
                ),
            }
        }

    args["user_id"] = state.get("user_id") or "unknown"
    args["idempotency_key"] = _idempotency_key(state)
    args["assumptions"] = plan.get("assumptions") or []
    out = await _run_tool(state, "prepare_transaction_proposal", args)
    payload = (out.get("specialist_output") or {}).get("data") or {}
    if payload and payload.get("confirmation_required") is not True:
        # Contract violation upstream. Refuse rather than present it.
        log.error("staging returned confirmation_required != true")
        return _tool_error(
            state, "prepare_transaction_proposal",
            RuntimeError("confirmation_required was not true"),
        )
    return out


async def handoff_node(state: MoneyFastState) -> dict[str, Any]:
    """Unsafe or distress. No tools, no screens, no instruments."""
    return {
        "specialist_output": {
            "agent": "HUMAN_HANDOFF",
            "status": "HANDOFF",
            "safety_flags": state.get("safety_flags") or [],
            "instruction": (
                "Do not screen, list instruments, or give a strategy. State "
                "plainly that borrowed money and recovery pressure make risk "
                "materially worse. Offer budgeting basics or a human handoff. "
                "No emoji, no humour."
            ),
        }
    }


async def synthesis_node(state: MoneyFastState) -> dict[str, Any]:
    """Turn the internal envelope into the Turkish user-facing draft."""
    revision = int(state.get("revision_count") or 0)
    try:
        if revision > 0 and state.get("draft_response"):
            task = REVISION_TASK_TEMPLATE.format(
                previous_draft=state["draft_response"],
                blocked_reason=state.get("blocked_reason") or "Compliance rejection.",
            )
        else:
            task = SYNTHESIS_TASK_TEMPLATE.format(
                user_message=state["user_message"],
                primary_intent=state.get("primary_intent") or "UNKNOWN",
                target_agent=state.get("target_agent") or "EDUCATION_AGENT",
                specialist_json=json.dumps(
                    state.get("specialist_output") or {}, ensure_ascii=False, indent=2
                )[:12000],
            )
        draft = await _llm_text(ORCHESTRATOR_SYSTEM_PROMPT, task)
    except Exception as exc:  # LLM outage
        log.error("synthesis failed: %s", exc)
        return {
            "draft_response": "",
            "final_output": GENERIC_FAILURE_TR,
            "errors": (state.get("errors") or []) + [f"synthesis: {exc}"],
        }
    return {"draft_response": draft}


async def compliance_gate_node(state: MoneyFastState) -> dict[str, Any]:
    """Deterministic gate. Fail closed on any error."""
    draft = state.get("draft_response") or ""
    if not draft:
        return {
            "compliance_verdict": "BLOCK",
            "final_output": state.get("final_output") or GENERIC_FAILURE_TR,
        }

    specialist = state.get("specialist_output") or {}
    try:
        verdict = await get_mcp_client().call(
            "validate_compliance_rules",
            {
                "draft_response": draft,
                "user_query": state["user_message"],
                "jurisdiction": JURISDICTION,
                "tools_used": state.get("tools_used") or [],
                "contains_personal_data": bool(
                    (specialist.get("data") or {}).get("positions")
                ),
                "contains_transaction_proposal": bool(
                    (specialist.get("data") or {}).get("proposal_id")
                ),
                "strictness": "STANDARD",
            },
        )
    except (MCPUnavailable, MCPToolError) as exc:
        log.error("compliance unavailable, failing closed: %s", exc)
        return {
            "compliance_verdict": "BLOCK",
            "final_output": GENERIC_FAILURE_TR,
            "errors": (state.get("errors") or []) + [f"compliance: {exc}"],
        }

    decision = (verdict.get("verdict") or "BLOCK").upper()
    log.info(
        "compliance verdict=%s severity=%s audit=%s",
        decision, verdict.get("max_severity"), verdict.get("audit_id"),
    )

    if decision == "PASS":
        return {
            "compliance_verdict": "PASS",
            "compliance": verdict,
            "final_output": _without_disclosures(draft, verdict),
            "disclosures": _disclosure_texts(verdict),
        }
    if decision == "REVISE":
        remediated = verdict.get("remediated_response") or ""
        if not remediated:
            return {
                "compliance_verdict": "BLOCK",
                "compliance": verdict,
                "final_output": GENERIC_FAILURE_TR,
            }
        return {
            "compliance_verdict": "REVISE",
            "compliance": verdict,
            "final_output": _without_disclosures(remediated, verdict),
            "disclosures": _disclosure_texts(verdict),
        }

    # BLOCK
    reason = verdict.get("blocked_reason_user_facing") or GENERIC_FAILURE_TR
    return {
        "compliance_verdict": "BLOCK",
        "compliance": verdict,
        "blocked_reason": reason,
        "final_output": reason,
        "revision_count": int(state.get("revision_count") or 0) + 1,
    }


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------
SpecialistRoute = Literal[
    "portfolio", "market_data",
    "market_research", "risk", "transaction", "handoff", "synthesis"
]


def route_after_router(state: MoneyFastState) -> SpecialistRoute:
    if state.get("needs_clarification"):
        return "synthesis"
    intent = state.get("primary_intent")
    if intent == "UNSAFE" or "DISTRESS_SIGNAL" in (state.get("safety_flags") or []):
        return "handoff"
    return {
        "PORTFOLIO_AGENT": "portfolio",
        "MARKET_DATA_AGENT": "market_data",
        "MARKET_RESEARCH_AGENT": "market_research",
        "RISK_STRATEGY_AGENT": "risk",
        "TRANSACTION_AGENT": "transaction",
        "HUMAN_HANDOFF": "handoff",
    }.get(state.get("target_agent") or "", "synthesis")


def route_after_compliance(state: MoneyFastState) -> Literal["synthesis", "__end__"]:
    if state.get("compliance_verdict") == "BLOCK":
        used = int(state.get("revision_count") or 0)
        if used <= MAX_COMPLIANCE_REVISIONS and state.get("draft_response"):
            log.info("compliance blocked, revision attempt %d", used)
            return "synthesis"
    return END


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
def build_graph():
    g = StateGraph(MoneyFastState)
    g.add_node("router", router_node)
    g.add_node("portfolio", portfolio_node)
    g.add_node("market_data", market_data_node)
    g.add_node("market_research", market_research_node)
    g.add_node("risk", risk_node)
    g.add_node("transaction", transaction_node)
    g.add_node("handoff", handoff_node)
    g.add_node("synthesis", synthesis_node)
    g.add_node("compliance", compliance_gate_node)

    g.add_edge(START, "router")
    g.add_conditional_edges(
        "router",
        route_after_router,
        {
            "portfolio": "portfolio",
            "market_data": "market_data",
            "market_research": "market_research",
            "risk": "risk",
            "transaction": "transaction",
            "handoff": "handoff",
            "synthesis": "synthesis",
        },
    )
    for node in ("portfolio", "market_data", "market_research", "risk", "transaction", "handoff"):
        g.add_edge(node, "synthesis")
    g.add_edge("synthesis", "compliance")
    g.add_conditional_edges(
        "compliance", route_after_compliance, {"synthesis": "synthesis", END: END}
    )

    checkpointer = None
    try:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
    except ImportError:  # optional
        log.info("no checkpointer available, running stateless")
    return g.compile(checkpointer=checkpointer) if checkpointer else g.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


async def run_turn(
    user_message: str,
    user_id: str = "anonymous",
    conversation_history: Optional[list[dict[str, str]]] = None,
    thread_id: str = "default",
) -> dict[str, Any]:
    state: MoneyFastState = {
        "user_message": user_message,
        "conversation_history": conversation_history or [],
        "user_id": user_id,
        "locale": DEFAULT_LOCALE,
        # Everything below is reset explicitly because the checkpointer keys
        # state on thread_id and MERGES this input into whatever the previous
        # turn left behind. Without the reset, a turn that runs no tool
        # inherits the last one's specialist_output -- and synthesis reads
        # that as its source of figures, so an unrelated later answer can
        # quote an earlier question's holdings. The observed symptom was
        # milder and just as wrong: a refusal rendered with the previous
        # turn's transaction confirm button attached.
        "primary_intent": "",
        "target_agent": "",
        "specialist_output": {},
        "draft_response": "",
        "final_output": "",
        "compliance_verdict": "",
        "compliance": {},
        "blocked_reason": None,
        "entities": {},
        "safety_flags": [],
        "needs_clarification": False,
        "clarifying_question": None,
        "tools_used": [],
        "revision_count": 0,
        "errors": [],
    }
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
    return await get_graph().ainvoke(state, config=config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _history_summary(state: MoneyFastState) -> Optional[str]:
    history = state.get("conversation_history") or []
    if not history:
        return None
    lines = [f"{t.get('role', 'user')}: {t.get('content', '')}" for t in history[-6:]]
    return "\n".join(lines)[-2000:]


def _specialist_task(state: MoneyFastState) -> str:
    return json.dumps(
        {
            "task": state["user_message"],
            "primary_intent": state.get("primary_intent"),
            "entities": state.get("entities") or {},
            "user_id": state.get("user_id"),
            "conversation_summary": _history_summary(state),
        },
        ensure_ascii=False,
    )


#: Substrings identifying an error the CALLER can fix by rewriting its
#: arguments, as opposed to one the caller can do nothing about (backend down,
#: timeout). Only the former is worth a second attempt.
_REPAIRABLE_MARKERS = ("unrecognised", "unrecognized", "invalid", "allowed:")


def _is_repairable(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _REPAIRABLE_MARKERS)


async def _repair_args(
    state: MoneyFastState, prompt: str, args: dict[str, Any], error: str
) -> Optional[dict[str, Any]]:
    """Ask the planner to fix arguments the tool rejected.

    The tool's own error names the permitted values, so the model is being
    corrected with the authoritative list rather than asked to guess again.
    Returns None if the retry produced nothing usable.
    """
    task = json.dumps(
        {
            "task": state["user_message"],
            "rejected_arguments": args,
            "tool_error": error,
            "instruction": (
                "The tool rejected these arguments. Re-emit the SAME envelope with "
                "only the offending value corrected to one the error permits. Do not "
                "change the user's intent and do not drop a filter to make it pass."
            ),
        },
        ensure_ascii=False,
    )
    try:
        plan = await _llm_json(prompt, task, fast=True)
    except Exception as exc:  # pragma: no cover - defensive, retry is best-effort
        log.warning("argument repair failed: %s", exc)
        return None
    repaired = plan.get("arguments") or None
    if not repaired:
        return None
    # Compare on the merged form: the node adds defaults (top_k) after the
    # planner runs, so a repair that changed nothing still looks different
    # from the arguments actually sent. Re-sending those would fail
    # identically and cost another round trip.
    merged = {**args, **repaired}
    return merged if merged != args else None


def _amount_not_in_current_turn(
    state: MoneyFastState, args: dict[str, Any]
) -> Optional[str]:
    """Return the offending figure when it appears only in the history.

    Deliberately narrow: it fires only when the number is absent from the
    current message AND present in an earlier one. A figure the user did not
    write anywhere (a quantity the model inferred from "hepsini sat") is left
    alone, because that is a different question and the tool validates it.
    """
    message = (state.get("user_message") or "").replace(".", "").replace(",", "")
    history = " ".join(
        str(turn.get("content", "")) for turn in (state.get("conversation_history") or [])
    ).replace(".", "").replace(",", "")

    candidates: list[tuple[str, float]] = []
    quantity = args.get("quantity")
    if isinstance(quantity, (int, float)):
        candidates.append(("quantity", float(quantity)))
    notional = args.get("notional_amount")
    if isinstance(notional, dict) and isinstance(notional.get("amount"), (int, float)):
        candidates.append(("notional_amount", float(notional["amount"])))

    for field, value in candidates:
        # Compare as the user would have typed it: "250" not "250.0".
        written = str(int(value)) if float(value).is_integer() else str(value)
        if written not in message and written in history:
            return f"{field}={written}"
    return None


async def _run_tool(
    state: MoneyFastState,
    tool: str,
    args: dict[str, Any],
    assumptions: Optional[list[str]] = None,
    empty_when=None,
    repair_prompt: Optional[str] = None,
) -> dict[str, Any]:
    try:
        payload = await get_mcp_client().call(tool, args)
    except (MCPUnavailable, MCPToolError) as exc:
        # One correction attempt, and only for an error the arguments can fix.
        # Without it a single unrecognised enum value became "Verilere
        # ulaşamadım" and the user had to type "tekrar dene" to re-roll the
        # planner into a legal value.
        if repair_prompt and _is_repairable(exc):
            repaired = await _repair_args(state, repair_prompt, args, str(exc))
            if repaired is not None:
                log.info("retrying %s with repaired arguments", tool)
                try:
                    payload = await get_mcp_client().call(tool, repaired)
                except (MCPUnavailable, MCPToolError) as retry_exc:
                    return _tool_error(state, tool, retry_exc)
                else:
                    return _tool_success(state, tool, payload, assumptions, empty_when)
        return _tool_error(state, tool, exc)

    return _tool_success(state, tool, payload, assumptions, empty_when)


def _tool_success(
    state: MoneyFastState,
    tool: str,
    payload: Any,
    assumptions: Optional[list[str]],
    empty_when,
) -> dict[str, Any]:
    status = "EMPTY" if (empty_when and empty_when(payload)) else "OK"
    return {
        "specialist_output": {
            "agent": state.get("target_agent"),
            "status": status,
            "tool": tool,
            "data": payload,
            "assumptions": assumptions or [],
        },
        "tools_used": (state.get("tools_used") or []) + [tool],
    }


def _tool_error(state: MoneyFastState, tool: str, exc: Exception) -> dict[str, Any]:
    log.error("tool %s failed: %s", tool, exc)
    return {
        "specialist_output": {
            "agent": state.get("target_agent"),
            "status": "ERROR",
            "tool": tool,
            "data": None,
            "error": str(exc),
            "instruction": DATA_FAILURE_TR,
        },
        "errors": (state.get("errors") or []) + [f"{tool}: {exc}"],
    }


def _disclosure_texts(verdict: dict[str, Any]) -> list[str]:
    """The disclosures this turn requires, as separate strings.

    Returned alongside the answer rather than concatenated into it. The words
    are unchanged and still mandatory; only their placement moves, so the chat
    can render them as a footnote instead of three sentences of boilerplate
    glued to a one-line reply.
    """
    out: list[str] = []
    for item in verdict.get("required_disclosures") or []:
        body = (item.get("text") or "").strip()
        if body and body not in out:
            out.append(body)
    return out


def _without_disclosures(text: str, verdict: dict[str, Any]) -> str:
    """Remove disclosure sentences the compliance layer appended to the draft.

    The backend's `remediated_response` arrives with them already inlined. They
    are carried structurally instead, so leaving the copies in the prose would
    show each notice twice.
    """
    cleaned = text
    for body in _disclosure_texts(verdict):
        cleaned = cleaned.replace(body, "")
    # Collapse the blank lines the removals leave behind.
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _with_disclosures(text: str, verdict: dict[str, Any]) -> str:
    """Insert required disclosures verbatim. Never paraphrase them."""
    prepend, append = [], []
    for item in verdict.get("required_disclosures") or []:
        body = (item.get("text") or "").strip()
        if not body or body in text:
            continue
        (prepend if item.get("placement") == "PREPEND" else append).append(body)
    return "\n\n".join([*prepend, text, *append]).strip()


def _idempotency_key(state: MoneyFastState) -> str:
    import hashlib

    seed = f"{state.get('user_id')}|{state['user_message']}|{len(state.get('conversation_history') or [])}"
    return "idem_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def _repl() -> None:
    print("MoneyFast orchestrator. Boş satır ile çıkın.\n")
    history: list[dict[str, str]] = []
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            break
        result = await run_turn(message, user_id="u_local", conversation_history=history)
        print("\n" + (result.get("final_output") or GENERIC_FAILURE_TR) + "\n")
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": result.get("final_output") or ""})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = asyncio.run(run_turn(" ".join(sys.argv[1:]), user_id="u_local"))
        print(out.get("final_output") or GENERIC_FAILURE_TR)
    else:
        asyncio.run(_repl())
