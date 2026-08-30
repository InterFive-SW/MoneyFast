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

import agent_trace
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

#: The context window's safety net, NOT its authority.
#:
#: The backend decides how much conversation the model sees
#: (`ai_orchestrator.service.trim_history`, 20 messages / 7500 characters) and
#: applies it to both the stored and the client-supplied path. These numbers
#: are deliberately LOOSER, which makes them provably inert behind the
#: backend -- 8000 clears 7500 plus the role prefixes -- while still bounding
#: the CLI and anyone calling this service directly.
#:
#: Do not "fix the inconsistency" by making them equal. Equal numbers put two
#: live trimmers in the path and the next person to widen the window would
#: have to find both.
HISTORY_MAX_TURNS = int(os.getenv("HISTORY_MAX_TURNS", "20"))
HISTORY_MAX_CHARS = int(os.getenv("HISTORY_MAX_CHARS", "8000"))

#: How much of a PREVIOUS ANSWER survives into the prompt. Only the subject
#: is needed to resolve "ondan 2 adet"; the body is what a model copies when
#: it should be reading this turn's tool payload instead.
HISTORY_ANSWER_EXCERPT_CHARS = int(os.getenv("HISTORY_ANSWER_EXCERPT_CHARS", "220"))

GENERIC_FAILURE_TR = (
    "Şu anda yanıtı hazırlayamadım. Kısa bir süre sonra tekrar deneyebilir "
    "misiniz?"
)

#: Rate limiting deserves its own sentence. Under the generic message a
#: quota exhaustion looked identical to a broken application: four turns in a
#: row, including "selam", answered "Şu anda yanıtı hazırlayamadım" with
#: nothing telling the user that waiting is the fix.
RATE_LIMITED_TR = (
    "Şu anda yoğunluk sınırına takıldım ve yanıt üretemiyorum. Bu geçici bir "
    "durum — birkaç dakika sonra tekrar denerseniz kaldığımız yerden devam "
    "ederiz."
)

#: Substrings that mark a provider quota/rate-limit refusal. Matched on the
#: exception text because the LLM client wraps the provider's 429 rather than
#: raising a typed error.
_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "429", "quota", "too many requests")


def _failure_message(exc: Exception) -> str:
    text = str(exc).casefold()
    return RATE_LIMITED_TR if any(m in text for m in _RATE_LIMIT_MARKERS) else GENERIC_FAILURE_TR


#: Transaction types the backend recognises as money transfers. The tool
#: docstring once documented TRANSFER_INTERNAL/EXTERNAL, which the backend
#: rejects — the three the backend accepts are the contract.
TRANSFER_TYPES = frozenset({"TRANSFER", "EFT", "HAVALE"})

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
    #: Crisis resources for a distress turn. Set by the handoff node and
    #: merged into `disclosures` on EVERY compliance branch, including BLOCK.
    #: Left to the model these appeared about half the time; a safety control
    #: that depends on a sampled token is not a control.
    crisis_notices: list[str]
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
    # The retriever scans this reversed and folds in the newest user turn it
    # finds, so the count only affects payload size, not what gets resolved.
    args["conversation_context"] = (state.get("conversation_history") or [])[
        -HISTORY_MAX_TURNS:
    ]
    return await _run_tool(
        state, "rag_semantic_market_search", args,
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("results"),
    )


async def risk_node(state: MoneyFastState) -> dict[str, Any]:
    """Three calls: positions, the profile summary, then the raw statistics.

    The risk tool has no position access by design, hence the first call. The
    second exists because `calculate_portfolio_risk_metrics` returns no score
    and no band -- those are produced by the backend's profile layer, which
    the agent could not reach. Asked "how risky is my portfolio", the risk
    page answered "83 puan, Düşük" and the assistant answered with an
    annualised volatility percentage: one system, one question, two answers,
    and no way for the user to tell which one was the answer.
    """
    mcp = get_mcp_client()
    user_id = state.get("user_id") or "unknown"
    try:
        holdings = await mcp.call(
            "get_portfolio_positions",
            {"user_id": user_id, "base_currency": "TRY"},
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

    # Best-effort, and deliberately so. A missing summary costs the turn its
    # score and its declared-tolerance comparison; the statistics below still
    # answer the question. Failing the whole turn over it would trade a
    # partial answer for none.
    summary = None
    try:
        summary = await mcp.call(
            "get_risk_profile_summary",
            {"user_id": user_id, "lookback": args["lookback"]},
        )
    except (MCPUnavailable, MCPToolError) as exc:
        log.warning("risk profile summary unavailable: %s", exc)

    out = await _run_tool(
        state, "calculate_portfolio_risk_metrics", args,
        assumptions=plan.get("assumptions") or [],
        # One correction attempt, as the market-data node has. Measured on the
        # live path: the planner emitted lookback "1y" on one turn and "365"
        # on the next, and a rejected argument became "Verilere ulaşamadım"
        # for a portfolio whose data was entirely present.
        repair_prompt=SPECIALIST_PROMPTS["RISK_STRATEGY_AGENT"],
    )
    tools = ["get_portfolio_positions"] + (out.get("tools_used") or [])
    data = (out.get("specialist_output") or {}).get("data")
    if summary and isinstance(data, dict):
        # Carried inside the metrics payload rather than beside it: the
        # synthesis step reads `data`, and a sibling key would need every
        # consumer to learn about it.
        data["profile_summary"] = summary
        tools.append("get_risk_profile_summary")
    out["tools_used"] = tools
    return out


async def _verify_named_instrument(
    state: MoneyFastState, plan: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Look the named instrument up BEFORE anything is asked about it.

    Measured, from three consecutive turns: "nvvvvdi hissesi almak", "aple
    alcam" and "ndivia nasıl" all reached an answer with `get_market_data`
    NEVER CALLED. The model recognised "aple" as Apple from its own knowledge,
    invented that NVVVVDI does not exist, and told the user data for "ndivia"
    could not be retrieved -- while the backend resolves ndivia to NVDA
    perfectly well.

    The prompt already tells the specialist to check first. A prompt is
    advisory: this module already learned that with `_keep_crisis`, where a
    mandatory instruction was followed about half the time. So the check runs
    in code, on the one path where being wrong costs money.

    Returns a NEEDS_INPUT specialist output when the name does not resolve,
    or None to let the turn continue.
    """
    named = _named_symbol(plan, state)
    if not named:
        return None

    try:
        payload = await get_mcp_client().call("get_market_data", {"symbols": [named]})
    except (MCPUnavailable, MCPToolError):
        # A lookup failure is not proof the instrument is missing. Let the turn
        # continue; staging resolves strictly and refuses on its own.
        return None

    if payload.get("instruments"):
        return None

    # Not found. The tool's warning already carries the candidates the resolver
    # produced, phrased for a person -- pass that through rather than writing a
    # second, differently worded version of the same sentence.
    suggestion = next(
        (w for w in (payload.get("warnings") or []) if "biri mi" in w), None
    )
    return {
        "specialist_output": {
            "agent": "TRANSACTION_AGENT",
            "status": "NEEDS_INPUT",
            "missing_fields": ["instrument"],
            "clarification_request": suggestion or (
                f"«{named}» diye bir enstrüman bulamadım. "
                f"Sembolü ya da tam adını yazar mısınız?"
            ),
        }
    }


def _named_symbol(plan: dict[str, Any], state: MoneyFastState) -> Optional[str]:
    """Whatever instrument this turn is about, however the model expressed it."""
    args = plan.get("arguments") or {}
    instrument = args.get("instrument") or {}
    candidates = [
        instrument.get("symbol") if isinstance(instrument, dict) else None,
        args.get("symbol"),
    ]
    tickers = (state.get("entities") or {}).get("tickers") or []
    candidates.extend(tickers[:1])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def transaction_node(state: MoneyFastState) -> dict[str, Any]:
    plan = await _llm_json(SPECIALIST_PROMPTS["TRANSACTION_AGENT"], _specialist_task(state))

    if plan.get("status") == "NEEDS_INPUT" or not plan.get("arguments"):
        # About to ask for something more -- usually a quantity. Confirm the
        # instrument EXISTS first. Asking "how many NVVVVDI?" and finding out
        # only at staging that there is no such thing is a question that
        # should never have been put.
        #
        # Only on this path: a complete request goes to staging, which already
        # resolves strictly and refuses with suggestions. The measured failures
        # were all of the "asked for a quantity" kind.
        unknown = await _verify_named_instrument(state, plan)
        if unknown is not None:
            return unknown

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

    # Transfers are staged like trades and confirmed by the user. They settle
    # against the banking ledger, not the investment account — routing them
    # through securities settlement is what produced a "Satım" with a blank
    # ticker, priced with brokerage commission.

    # Direction before amount: staging the wrong side of a trade is worse than
    # staging the wrong size of one.
    inverted = _direction_contradicts_message(state, args)
    if inverted is not None:
        emitted, stated = inverted.split("!=")
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["transaction_type"],
                "clarification_request": (
                    "İşlemin yönünden emin olamadım: mesajınızı "
                    f"{'satış' if stated == 'SELL' else 'alış'} olarak okudum ama "
                    "hazırlanan öneri "
                    f"{'alış' if emitted == 'BUY' else 'satış'} yönündeydi. "
                    "Alım mı satım mı yapmak istiyorsunuz?"
                ),
            }
        }

    mismatch = _amount_not_in_current_turn(state, args)
    if mismatch is not None:
        log.warning("staging refused, figure overruled by this turn: %s", mismatch)
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["quantity" if "quantity" in mismatch else "notional_amount"],
                # The field name stays out of the user's sentence: `mismatch`
                # reads "quantity=250", and the NAMING rule keeps internal
                # keys off the screen. It is logged instead, where it helps.
                "clarification_request": (
                    "Bu mesajda yazdığınız adet ile daha önce konuştuğumuz adet "
                    "farklı görünüyor. Hangisini kullanayım?"
                ),
            }
        }

    refused = _symbol_refused_in_message(state, args)
    if refused is not None:
        log.warning("staging refused, user rejected this symbol: %s", refused)
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["instrument.symbol"],
                "clarification_request": (
                    f"{refused} istemediğinizi söylediniz. Hangi hisseyi almak "
                    "veya satmak istediğinizi yazar mısınız?"
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


#: Verbatim crisis resources. Hardcoded rather than generated: asked to
#: produce them the model once offered "ALO 182", which is the MHRS health
#: APPOINTMENT line, not a crisis line. A hallucinated resource is worse than
#: none, because someone may actually dial it.
CRISIS_RESOURCES_TR = (
    "Acil bir tehlike varsa 112'yi arayın. "
    "Sosyal Destek Hattı 183, 7/24 ücretsizdir ve psikososyal destek sağlar."
)

#: Being threatened by someone else is a police matter, not a budgeting one.
COERCION_RESOURCES_TR = (
    "Can güvenliğiniz tehlikedeyse 112'yi arayın. "
    "Kolluk ihbarı için 155 (Polis) veya 156 (Jandarma) aranabilir."
)

#: What the assistant may say once distress is detected. Split by category:
#: these were ONE instruction written for the financial case, so "ölmek
#: istiyorum" was answered with a lecture about how borrowed money raises
#: risk. Self-harm now gets no financial content at all.
_HANDOFF_INSTRUCTIONS = {
    "SELF_HARM_RISK": (
        "The user may be at risk of self-harm. This is not a financial turn. "
        "Respond briefly and warmly in Turkish: acknowledge what they said, "
        "say they do not have to face it alone, and encourage contacting "
        "someone they trust or a professional. "
        "Do NOT mention markets, portfolios, debt, budgeting, investing or "
        "risk tolerance. Do NOT analyse their finances. "
        "Do NOT offer to connect them to an adviser or specialist -- this "
        "product cannot do that, and the offer was previously made and then "
        "refused when accepted. "
        "Do not state phone numbers yourself; they are appended verbatim. "
        "No emoji, no humour, at most four sentences."
    ),
    "COERCION_RISK": (
        "The user reports being threatened or coerced by another person. "
        "This is a safety matter, not an investment one. Respond briefly in "
        "Turkish, take it seriously, and encourage contacting the "
        "authorities or someone they trust. "
        "Do NOT suggest trades, instruments or ways to raise money quickly -- "
        "urgency plus threat is exactly how people are pushed into ruinous "
        "positions. Do not state phone numbers yourself; they are appended. "
        "No emoji, no humour, at most four sentences."
    ),
    "FINANCIAL_DISTRESS": (
        "Do not screen, list instruments, or give a strategy. State "
        "plainly that borrowed money and recovery pressure make risk "
        "materially worse. Offer budgeting basics. Do NOT offer to connect "
        "them to a human adviser -- this product cannot do that. "
        "No emoji, no humour."
    ),
}


async def handoff_node(state: MoneyFastState) -> dict[str, Any]:
    """Unsafe or distress. No tools, no screens, no instruments."""
    flags = state.get("safety_flags") or []
    # Self-harm outranks the others: a turn carrying both is answered as the
    # more serious one.
    if "SELF_HARM_RISK" in flags:
        category, notices = "SELF_HARM_RISK", [CRISIS_RESOURCES_TR]
    elif "COERCION_RISK" in flags:
        category, notices = "COERCION_RISK", [COERCION_RESOURCES_TR]
    else:
        category, notices = "FINANCIAL_DISTRESS", []

    return {
        "crisis_notices": notices,
        "specialist_output": {
            "agent": "HUMAN_HANDOFF",
            "status": "HANDOFF",
            "safety_flags": flags,
            "handoff_category": category,
            "instruction": _HANDOFF_INSTRUCTIONS[category],
        },
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
                # The writer used to be blind to earlier turns, so a
                # follow-up like "peki ya onu satsam?" was rendered by a
                # model that did not know what "onu" referred to. The
                # template's own rules keep this to coreference and tone:
                # figures still come only from the specialist output below.
                conversation_summary=_history_summary(state) or "(none)",
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
            "final_output": _failure_message(exc),
            "errors": (state.get("errors") or []) + [f"synthesis: {exc}"],
        }
    return {"draft_response": draft}


def _keep_crisis(state: MoneyFastState, out: dict[str, Any]) -> dict[str, Any]:
    """Ensure a distress turn carries its resources out of the gate.

    Applied to every branch, BLOCK included. A blocked crisis turn used to end
    at a generic failure string with nothing actionable in it, which is the
    worst moment to hand someone a dead end.
    """
    notices = state.get("crisis_notices") or []
    if not notices:
        return out
    existing = out.get("disclosures") or []
    out["disclosures"] = existing + [n for n in notices if n not in existing]
    return out


async def compliance_gate_node(state: MoneyFastState) -> dict[str, Any]:
    """Deterministic gate. Fail closed on any error."""
    draft = state.get("draft_response") or ""
    if not draft:
        return _keep_crisis(state, {
            "compliance_verdict": "BLOCK",
            "final_output": state.get("final_output") or GENERIC_FAILURE_TR,
        })

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
        return _keep_crisis(state, {
            "compliance_verdict": "BLOCK",
            "final_output": GENERIC_FAILURE_TR,
            "errors": (state.get("errors") or []) + [f"compliance: {exc}"],
        })

    decision = (verdict.get("verdict") or "BLOCK").upper()
    log.info(
        "compliance verdict=%s severity=%s audit=%s",
        decision, verdict.get("max_severity"), verdict.get("audit_id"),
    )

    if decision == "PASS":
        return _keep_crisis(state, {
            "compliance_verdict": "PASS",
            "compliance": verdict,
            "final_output": _without_disclosures(draft, verdict),
            "disclosures": _disclosure_texts(verdict),
        })
    if decision == "REVISE":
        remediated = verdict.get("remediated_response") or ""
        if not remediated:
            return _keep_crisis(state, {
                "compliance_verdict": "BLOCK",
                "compliance": verdict,
                "final_output": GENERIC_FAILURE_TR,
            })
        return _keep_crisis(state, {
            "compliance_verdict": "REVISE",
            "compliance": verdict,
            "final_output": _without_disclosures(remediated, verdict),
            "disclosures": _disclosure_texts(verdict),
        })

    # BLOCK
    reason = verdict.get("blocked_reason_user_facing") or GENERIC_FAILURE_TR
    return _keep_crisis(state, {
        "compliance_verdict": "BLOCK",
        "compliance": verdict,
        "blocked_reason": reason,
        "final_output": reason,
        "revision_count": int(state.get("revision_count") or 0) + 1,
    })


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------
SpecialistRoute = Literal[
    "portfolio", "market_data",
    "market_research", "risk", "transaction", "handoff", "synthesis"
]


def route_after_router(state: MoneyFastState) -> SpecialistRoute:
    """Pick the specialist. Safety decides first; uncertainty does not decide.

    `needs_clarification` used to short-circuit straight to synthesis, which
    meant the tool was never called and the user was told the data could not
    be retrieved -- when nothing had tried to retrieve it. Measured over one
    session: "onun son fiyatı ne kadar" routed correctly to MARKET_DATA_AGENT,
    was flagged uncertain, skipped the tool, and answered "fiyat alınamadı"
    while the quote sat one call away.

    The flag is not ignored, it is demoted. The specialist runs, and it is the
    specialist that reports NEEDS_INPUT when a field really is missing -- an
    answer grounded in what the tools could actually resolve, rather than a
    guess made before asking. Every specialist here is read-only except
    TRANSACTION, and that one only ever STAGES: nothing reaches the user's
    money without the on-screen confirmation step.
    """
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
def _traced(name: str, fn):
    """Record one node's input, output and duration.

    Wrapped here rather than inside each node: registration is the one place
    that already names every stage, so both `run_turn` and
    `run_turn_streaming` are covered without either knowing tracing exists.
    """
    async def wrapper(state: MoneyFastState) -> dict[str, Any]:
        with agent_trace.span("node", name, input=dict(state)) as sp:
            out = await fn(state)
            sp.set(output=out)
            return out

    wrapper.__name__ = getattr(fn, "__name__", name)
    return wrapper


def build_graph():
    g = StateGraph(MoneyFastState)
    g.add_node("router", _traced("router", router_node))
    g.add_node("portfolio", _traced("portfolio", portfolio_node))
    g.add_node("market_data", _traced("market_data", market_data_node))
    g.add_node("market_research", _traced("market_research", market_research_node))
    g.add_node("risk", _traced("risk", risk_node))
    g.add_node("transaction", _traced("transaction", transaction_node))
    g.add_node("handoff", _traced("handoff", handoff_node))
    g.add_node("synthesis", _traced("synthesis", synthesis_node))
    g.add_node("compliance", _traced("compliance", compliance_gate_node))

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


def _initial_state(
    user_message: str,
    user_id: str,
    conversation_history: Optional[list[dict[str, str]]],
) -> MoneyFastState:
    """The turn's starting state. Shared by the buffered and streaming runs so
    the two can never drift on what gets reset."""
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
        # Both were missing from this reset. The BLOCK branch does not set
        # `disclosures`, so a blocked turn rendered the PREVIOUS turn's
        # notices; and crisis resources would otherwise follow a distress
        # turn into the next unrelated question about a share price.
        "disclosures": [],
        "crisis_notices": [],
        "blocked_reason": None,
        "entities": {},
        "safety_flags": [],
        "needs_clarification": False,
        "clarifying_question": None,
        "tools_used": [],
        "revision_count": 0,
        "errors": [],
    }
    return state


def _graph_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}


async def run_turn(
    user_message: str,
    user_id: str = "anonymous",
    conversation_history: Optional[list[dict[str, str]]] = None,
    thread_id: str = "default",
) -> dict[str, Any]:
    agent_trace.new_turn(thread_id)
    state = _initial_state(user_message, user_id, conversation_history)
    return await get_graph().ainvoke(state, config=_graph_config(thread_id))


#: What each graph node is doing, in the user's language.
#:
#: These replace a hardcoded 800ms ticker on the client that cycled four
#: captions regardless of what ran -- it announced "Risk modeli
#: güncelleniyor..." for "what is the capital of Turkey". Naming a stage the
#: system did not enter is the same class of error as showing a price the
#: system did not fetch.
STAGE_LABELS_TR = {
    "router": "Talebiniz sınıflandırılıyor...",
    "portfolio": "Portföyünüz okunuyor...",
    "market_data": "Piyasa verileri çekiliyor...",
    "market_research": "Kaynaklar taranıyor...",
    "risk": "Risk ölçütleri hesaplanıyor...",
    "transaction": "İşlem önerisi hazırlanıyor...",
    "handoff": "Yanıt hazırlanıyor...",
    "synthesis": "Yanıt yazılıyor...",
    "compliance_gate": "Uygunluk kontrolü yapılıyor...",
}


async def run_turn_streaming(
    user_message: str,
    user_id: str = "anonymous",
    conversation_history: Optional[list[dict[str, str]]] = None,
    thread_id: str = "default",
):
    """Yield ("stage", label) as each node completes, then ("state", final).

    Only the STAGES stream. The answer itself is emitted once, after the
    compliance gate has passed it.

    That ordering is the whole point. The graph is
    router -> specialist -> synthesis -> compliance_gate, and it is
    fail-closed: a draft that compliance BLOCKs must never reach the user.
    Streaming synthesis tokens as they were generated would put text on screen
    that the gate might then retract, so the guarantee would hold only until
    the first block. The client gets real progress while the turn runs and
    types out the APPROVED text afterwards.
    """
    agent_trace.new_turn(thread_id)
    state = _initial_state(user_message, user_id, conversation_history)
    # Seeded from the initial state, not empty: `updates` mode yields only the
    # keys a node returned, so `user_message` and friends would be missing
    # from the accumulated result that widgets.build() reads.
    final: dict[str, Any] = dict(state)
    async for update in get_graph().astream(
        state, config=_graph_config(thread_id), stream_mode="updates"
    ):
        for node, patch in (update or {}).items():
            if isinstance(patch, dict):
                final.update(patch)
            label = STAGE_LABELS_TR.get(node)
            if label:
                yield "stage", label
    yield "state", final


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _history_summary(state: MoneyFastState) -> Optional[str]:
    """The conversation as a flat transcript.

    Not a summary despite the name: no model is asked to condense anything,
    which is deliberate -- a generated summary is one more surface that can
    invent a figure, and this text feeds the router's coreference resolution.

    The character cap slices the TAIL, so when it bites it is the oldest turn
    that loses its opening rather than the newest turn losing its end.
    """
    history = state.get("conversation_history") or []
    if not history:
        return None
    lines = []
    for turn in history[-HISTORY_MAX_TURNS:]:
        role = turn.get("role", "user")
        content = str(turn.get("content", ""))
        if role == "assistant":
            # Excerpt, not transcript. A whole previous answer sitting in the
            # prompt is a template, and synthesis copied one: asked for
            # THYAO's price with a valid THYAO payload in hand, it reproduced
            # the previous turn's "ASELS verisi alınamadı" word for word.
            # Coreference needs the SUBJECT of the last answer, never its
            # body, so the body is the part that goes.
            content = _excerpt(content)
            lines.append(f"[önceki yanıt özeti] {content}")
        else:
            lines.append(f"kullanıcı: {content}")
    return "\n".join(lines)[-HISTORY_MAX_CHARS:]


def _excerpt(content: str) -> str:
    """First sentence-ish of an assistant turn, enough to name its subject."""
    flat = " ".join(content.split())
    if len(flat) <= HISTORY_ANSWER_EXCERPT_CHARS:
        return flat
    return flat[:HISTORY_ANSWER_EXCERPT_CHARS].rstrip() + "…"


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
#: "is not one of" is how the risk tools word a rejected lookback, and like
#: the others it is followed by the permitted values -- which is the whole
#: reason a repair attempt is worth making rather than a re-roll.
_REPAIRABLE_MARKERS = (
    "unrecognised", "unrecognized", "invalid", "allowed:", "is not one of",
)


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


#: Verb forms that state a direction, matched on whole words.
#:
#: Curated forms rather than a prefix like `al*`, because in this domain `al*`
#: also matches **altın** (gold) — "altın fiyatı ne kadar" would read as a buy
#: order. `sat*` is safer but still needs `satın` carved out, since "satın al"
#: is a purchase that contains the sell stem.
_SELL_FORMS = (
    "satsana", "satsanıza", "satalım", "satayım", "satacağım", "satacagim",
    "satıcam", "saticam", "satmak", "satıyorum", "satiyorum", "satabilir",
    "satar", "satış", "satis", "satın", "sat", "bozdur", "bozdurayım",
)
_BUY_FORMS = (
    "alsana", "alsanıza", "alayım", "alalım", "alacağım", "alacagim",
    "alıcam", "alicam", "almak", "alıyorum", "aliyorum", "alabilir",
    "alırım", "alirim", "alım", "alim", "al",
)
_SELL_PHRASES = ("elden çıkar", "elden cikar", "nakde çevir", "nakde cevir")
_BUY_PHRASES = ("satın al", "satin al")


def _fold(text: str) -> str:
    """Lowercase with Turkish dotted/dotless i folded together.

    `str.lower()` leaves "İ" intact on some inputs and maps "I" to "i" rather
    than "ı", and users type both. Folding here keeps the verb match from
    depending on which keyboard produced the message.
    """
    table = str.maketrans({"İ": "i", "I": "ı", "Î": "i"})
    return text.translate(table).lower()


def _has_word(folded: str, forms: tuple[str, ...]) -> bool:
    """Whole-word match, so "al" does not fire inside "altın" or "alan"."""
    return any(re.search(rf"(?<!\w){re.escape(form)}(?!\w)", folded) for form in forms)


def _stated_direction(message: str) -> Optional[str]:
    """BUY / SELL when the user's own words say so, else None.

    "satın al" is checked first because it contains "sat": without that, every
    purchase phrased that way would read as a sale.
    """
    folded = _fold(message or "")
    if any(phrase in folded for phrase in _BUY_PHRASES):
        return "BUY"
    if any(phrase in folded for phrase in _SELL_PHRASES):
        return "SELL"
    if _has_word(folded, _SELL_FORMS):
        return "SELL"
    if _has_word(folded, _BUY_FORMS):
        return "BUY"
    return None


#: Turkish ways of saying "not that one", as they appear right after the
#: instrument: "THYAO değil", "thyao istemiyorum", "onu yerine".
_REFUSAL_MARKERS = (
    "değil", "degil", "istemiyorum", "istemem", "olmasın", "olmasin",
    "vazgeçtim", "vazgectim", "yerine",
)


def _same_instrument(token: str, symbol: str) -> bool:
    """Ticker and company name for one instrument: ASELS / aselsan."""
    if token == symbol:
        return True
    if len(token) >= 4 and len(symbol) >= 4:
        return token.startswith(symbol) or symbol.startswith(token)
    return False


def _symbol_refused_in_message(
    state: MoneyFastState, args: dict[str, Any]
) -> Optional[str]:
    """Return the symbol when THIS turn rejected the one being staged.

    The prompt already forbids it, and the prompt was not enough: asked for
    "thyao değil diğer bahsettiğim hisseyi satın alacağım", the planner staged
    THYAO. A rule that decides where money goes belongs in code, the same way
    the direction check and the crisis resources do -- a sampled token is not
    a control.

    Narrow on purpose: it fires only when the refusal word follows the symbol
    closely, so "ASELS al, THYAO değil" blocks THYAO and leaves ASELS alone.
    """
    symbol = ((args.get("instrument") or {}).get("symbol") or "").strip().casefold()
    if not symbol:
        return None

    tokens = re.findall(r"[0-9a-zçğıöşü]+", (state.get("user_message") or "").casefold())
    for index, token in enumerate(tokens):
        if not _same_instrument(token, symbol):
            continue
        # Two tokens, not more. At three, "asels al, thyao değil" reached the
        # "değil" belonging to THYAO and refused the instrument the user had
        # just asked for.
        for follower in tokens[index + 1 : index + 3]:
            if any(follower.startswith(marker) for marker in _REFUSAL_MARKERS):
                return (args.get("instrument") or {}).get("symbol")
    return None


def _direction_contradicts_message(
    state: MoneyFastState, args: dict[str, Any]
) -> Optional[str]:
    """The planner's direction against the user's verb.

    "10 tane aselsan satsana" was staged as a BUY and settled. The prompt now
    names the verbs, but a prompt is guidance; this is the check. It also
    matters that a flipped direction SKIPS the sell-side inventory guard in the
    backend and lands in the cash check instead, so the mistake surfaces as a
    successful purchase rather than an error.

    Returns None when the user stated no direction — inferring one from history
    is exactly the failure being prevented, so an unstated direction is left to
    the tool's own validation.
    """
    stated = _stated_direction(state.get("user_message") or "")
    if stated is None:
        return None
    emitted = str(args.get("transaction_type") or "").upper()
    if emitted in ("BUY", "ALIS", "ALIŞ"):
        emitted = "BUY"
    elif emitted in ("SELL", "SATIS", "SATIŞ"):
        emitted = "SELL"
    else:
        return None
    return None if emitted == stated else f"{emitted}!={stated}"


def _amount_not_in_current_turn(
    state: MoneyFastState, args: dict[str, Any]
) -> Optional[str]:
    """Return the offending figure when this turn's own number was overruled.

    Guards the 250/200 bug: the user said "250 adet alacaktım" earlier, says
    "200 adet al" now, and the planner stages 250 -- a figure the user has
    just replaced. That is the case worth blocking, and the signal for it is
    specific: THIS message states a number, and the planner used a different
    one that it found in the history.

    It deliberately does NOT fire when this message names no figure at all.
    "son söylediğim adet kadar al" is the user explicitly delegating to the
    history, and refusing it produced a loop with no exit: the planner
    resolved quantity=2 correctly, the guard rejected it, the assistant asked
    again, and the user answered "birkaç mesaj önce söyledim" four times
    before giving up. Carrying the figure forward there is what was asked
    for, it is surfaced as an assumption, and it still cannot move money
    without the on-screen confirmation.
    """
    message = (state.get("user_message") or "").replace(".", "").replace(",", "")
    stated_here = set(re.findall(r"\d+(?:\.\d+)?", message))
    if not stated_here:
        # No competing figure in this turn: nothing was overruled.
        return None

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
        if written not in stated_here and written in history:
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
    """One key per turn.

    The seed used to include `len(conversation_history)`, which is bounded by
    the window. Once the window saturates the length stops changing, so asking
    the same thing twice produced the SAME key and the second, legitimate
    staging request could be deduplicated into the first proposal.

    The turn's trace id is unique per turn and stable across the graph's own
    argument-repair retry -- which is the retry idempotency exists for.
    """
    import hashlib

    trace_id = agent_trace.current_trace_id() or ""
    seed = f"{state.get('user_id')}|{state['user_message']}|{trace_id}"
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
