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
#: 8.000'di ve `SYNTHESIS_PAYLOAD_CHARS`'ın aritmetiğiyle ÇELİŞİYORDU. O
#: hesap geçmiş için ~1.500 token ayırıyor; 8.000 karakter ise ~2.000 token
#: eder. Üç tavan aynı anda dolduğunda toplam 8.475 token çıkıyor ve
#: sağlayıcının tek istek sınırı 8.000.
#:
#: Ölçüldü, uzun bir sohbette: gövde bütçesine SIĞDIĞI hâlde istek 8.871
#: token oldu ve kullanıcı "tek seferde işleyebileceğimden büyük çıktı"
#: cevabı aldı. Tavan yazılı varsayıma çekildi -- 6.000 karakter ≈ 1.500
#: token, ve 4.475 + 1.500 + 2.000 = 7.975.
HISTORY_MAX_CHARS = int(os.getenv("HISTORY_MAX_CHARS", "6000"))

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

#: İstek, modelin tek seferde alabileceğinden BÜYÜK. Sağlayıcı bunu 413 ile
#: ve `rate_limit_exceeded` koduyla döndürüyor, dolayısıyla aşağıdaki kota
#: işaretlerine de takılıyor -- ama ikisi karşıt durumlar: kota beklemekle
#: geçer, bu geçmez. Bir dakika sonra aynı istek yine aynı boyutta.
#:
#: ÖLÇÜLDÜ ve kullanıcı bildirdi: "faizler artarsa portföyüm nasıl etkilenir"
#: her seferinde "yoğunluk sınırına takıldım, birkaç dakika sonra deneyin"
#: cevabı veriyordu; aynı oturumda sorulan başka sorular anında cevaplanıyordu.
#: Beklemek hiçbir zaman işe yaramayacaktı. Sağlayıcı kaydı: 8.393 token
#: istendi, sınır 8.000.
_TOO_LARGE_MARKERS = (
    "request too large", "reduce your message size", "413",
    "context length", "maximum context",
)

#: Substrings that mark a provider quota/rate-limit refusal. Matched on the
#: exception text because the LLM client wraps the provider's 429 rather than
#: raising a typed error.
_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "429", "quota", "too many requests")

#: Boyut hatası kullanıcıya beklemesini SÖYLEMEZ. Beklemek düzeltmiyor ve
#: "birkaç dakika sonra deneyin" demek, kullanıcıyı hiç sonuçlanmayacak bir
#: döngüde tutmak olur -- kullanıcı bunu bizden önce fark etti.
TOO_LARGE_TR = (
    "Bu sorunun yanıtı için toplanan veri tek seferde işleyebileceğimden "
    "büyük çıktı, bu yüzden yanıtı hazırlayamadım. Beklemek bunu değiştirmez; "
    "soruyu daha dar sorarsanız (örneğin tek bir konuya odaklanarak) "
    "yanıtlayabilirim."
)


def _failure_message(exc: Exception) -> str:
    """Sağlayıcı hatasını kullanıcıya doğru cümleyle anlatır.

    Boyut kontrolü kota kontrolünden ÖNCE: Groq'un 413'ü `rate_limit_exceeded`
    kodunu taşıyor ve sıra ters olsaydı kalıcı bir hata geçici diye
    anlatılırdı -- ki tam olarak bu oldu.
    """
    text = str(exc).casefold()
    if any(m in text for m in _TOO_LARGE_MARKERS):
        return TOO_LARGE_TR
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
#: Bu sistemin ölçemediği makro faktörler. Sabit var, seri yok:
#: `TR_POLICY_RATE` tek bir sayı ve enflasyon hiç toplanmıyor. Liste dar
#: tutuldu -- ölçülebilen faktörler (dolar, euro, BIST, altın) BURAYA GİRMEZ,
#: onların yolu zaten doğru çalışıyor.
_UNMEASURABLE_FACTOR = re.compile(
    r"\b(faiz|faizler|faizin|faizi|enflasyon|enflasyonun|tüfe|tufe|ppk)\b",
    re.IGNORECASE,
)

#: Turun kullanıcının KENDİ portföyü hakkında olduğunu gösteren sözcükler.
#: İkisi birden gerekiyor: "faiz nedir" bir tanım sorusu ve EDUCATION_AGENT'ın
#: işi; "faizler artarsa portföyüm ne olur" bir ölçüm talebi.
_OWNERSHIP_WORD = re.compile(
    r"\b(portföy\w*|portfoy\w*|pozisyon\w*|hissem|hisselerim\w*|"
    r"yatırımlarım\w*|yatirimlarim\w*|varlığım\w*|varligim\w*)\b",
    re.IGNORECASE,
)


def _is_unmeasurable_factor_turn(message: str) -> bool:
    """Ölçülemeyen bir makro faktör + kullanıcının KENDİ portföyü.

    İkisi birden gerekiyor: "faiz nedir" bir tanım sorusu, "faizler artarsa
    portföyüm ne olur" bir ölçüm talebi ve ölçüm yapılamaz.
    """
    return bool(
        _UNMEASURABLE_FACTOR.search(message) and _OWNERSHIP_WORD.search(message)
    )


def _forced_agent(message: str) -> Optional[str]:
    """Ölçülemeyen bir makro faktör + kullanıcının kendi portföyü.

    Kodda, çünkü ÖLÇÜLDÜ: "faizler artarsa portföyüm nasıl etkilenir" iki ayrı
    denemede de EDUCATION_AGENT'a gitti -- yönlendirme kuralı prompt'a
    yazıldıktan SONRA da. Bu modülün kendi dersi (`_keep_crisis`,
    `_verify_named_instrument`): prompt tavsiyedir ve zorunlu bir davranışın
    kodda bir karşılığı olmalı.

    Yanlış cevabın iki ayrı zararı vardı: "veriler alınamadı" bir KESİNTİ gibi
    okunuyordu -- oysa faiz serisi yapısal olarak yok, "şu anda" değil hiçbir
    zaman -- ve kullanıcıdan pozisyonlarını YAPIŞTIRMASI isteniyordu, ki bu
    ürün pozisyonları kayıt saklayıcısından okur ve MCP sözleşmesi kullanıcı
    beyanını açıkça yasaklar.

    RISK_STRATEGY_AGENT ölçemediğini biliyor ve sebebini söylüyor. Doğru cevap
    "hesaplayamıyorum" değil, "bu sistemde faiz serisi tutulmuyor".

    Güvenlik kararlarını EZMEZ: çağıran bunu DISTRESS_SIGNAL kontrolünden
    ÖNCE uyguluyor, dolayısıyla güvenlik her zaman üstte kalıyor.
    """
    return "RISK_STRATEGY_AGENT" if _is_unmeasurable_factor_turn(message) else None


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
        # Deterministik kapı BU YOLDA DA geçerli -- hatta asıl burada.
        # Sınıflandırıcı düştüğünde tur EDUCATION_AGENT'a düşüyor ve o ajan
        # hiçbir araç tutmuyor; ölçüldü, sonuç "gerekli veriler alınamadı"
        # oldu ve kullanıcı bunu bir kesinti sandı. Oysa faiz serisi zaten
        # yok ve bunu söylemek için bir model çağrısına ihtiyaç yok.
        #
        # Güvenlik burada da üstte: `flags` pass 1'in deterministik regex'i
        # ve sıkıntı sinyali her şeyi eziyor.
        fallback = "EDUCATION_AGENT"
        if "DISTRESS_SIGNAL" not in flags:
            fallback = _forced_agent(state["user_message"]) or fallback
        return {
            "primary_intent": "OUT_OF_SCOPE",
            "target_agent": "HUMAN_HANDOFF" if "DISTRESS_SIGNAL" in flags else fallback,
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

    # Ölçülemeyen bir makro faktör hakkındaki portföy sorusu, reddi BİLEN
    # ajana gider. Güvenlik kontrolünden ÖNCE, ki DISTRESS_SIGNAL bunu her
    # zaman ezebilsin.
    forced = _forced_agent(state["user_message"])
    if forced is not None and target != forced:
        log.info("routing override: %s -> %s (unmeasurable factor)", target, forced)
        target = forced

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

    # Two tools behind one agent, the same split as MARKET_DATA_AGENT: what
    # the user OWNS, and what was PUBLISHED about it. The intersection lives
    # here rather than in market research because it is not a search --
    # "portföyümdeki hisselerle ilgili haber" names no company, so a document
    # search has nothing to search for, and only this agent can read the
    # holdings that make the question answerable.
    if plan.get("tool") == "get_portfolio_news":
        return await _run_tool(
            state, "get_portfolio_news",
            {key: args[key] for key in ("user_id", "limit", "days") if key in args},
            assumptions=plan.get("assumptions") or [],
            # An empty article list is a COMPLETE answer -- nothing matched in
            # the window -- but it must be reported with the window, so the
            # payload still travels.
            empty_when=lambda p: not p.get("articles"),
        )

    # Üçüncü araç: neye SAHİP olduğu değil, ne KAZANIP ne HARCADIĞI. Aynı
    # ajanda duruyor çünkü köprü burada kuruluyor -- "bu alımı kaldırabilir
    # miyim" sorusu hem pozisyonları hem aylık artanı gerektiriyor ve iki
    # ayrı ajan bunu tek turda birleştiremez.
    # Dördüncü araç: TEK TEK değil, hepsi birden. Diğer üçü bir soruyu
    # cevaplıyor; bu, "portföyümün genel durumu" gibi hiçbirinin tek başına
    # cevaplayamadığı soruyu.
    if plan.get("tool") == "get_portfolio_report":
        return await _run_tool(
            state, "get_portfolio_report", {"user_id": args["user_id"]},
            assumptions=plan.get("assumptions") or [],
            # Bölümü olmayan bir rapor EKSİK değil, üretilememiş demektir --
            # veri yoksa bölüm yine geliyor ve yokluğunu kendisi söylüyor.
            empty_when=lambda p: not p.get("sections"),
        )

    if plan.get("tool") == "get_cash_flow_summary":
        return await _run_tool(
            state, "get_cash_flow_summary",
            {key: args[key] for key in ("user_id", "days") if key in args},
            assumptions=plan.get("assumptions") or [],
            # `has_data: false` EKSİK değil, tam bir cevap: sistemde bu kişiye
            # ait bankacılık kaydı yok. Boş sayılırsa ajan "veriye
            # ulaşamadım" der ve bu, kaydın olmadığını söylemekten farklı.
        )

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
    """Adı geçen bir enstrüman hakkında üç soru, üç araç.

    Fiyat ("ne ediyor"), eğilim ("nasıl gidiyor") ve şirketin işi ("kârlı mı").
    Üçü de aynı ajanın arkasında, çünkü üçü de bu sistemin tuttuğu veriden
    cevaplanıyor ve yönlendiricide üçe bölmek aynı soruyu üç kez sormak olurdu.
    """
    plan = await _llm_json(
        SPECIALIST_PROMPTS["MARKET_DATA_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    assumptions = plan.get("assumptions") or []

    # Two tools behind one agent: what it COSTS and how it is DOING. The
    # split is here rather than in the router because both answer questions
    # about a named instrument from data this system holds -- and sending the
    # open ones ("yorumlar mısın") to the document search is what produced
    # "Akbank hakkında veri bulunamadı" for an instrument with seven hundred
    # bars of history.
    if plan.get("tool") == "get_technical_signals":
        symbol = args.get("symbol") or _first_ticker(state)
        if symbol:
            return await _run_tool(
                state, "get_technical_signals", {"symbol": symbol},
                assumptions=assumptions,
                # `narrative` empty means the history is too short to read.
                # The figures still travel; the agent reports the gap.
                empty_when=lambda p: not p.get("narrative"),
            )
        # No symbol to look up. Falling through to the price path lets the
        # turn be answered from whatever the user did name, rather than
        # calling a one-symbol tool with nothing.

    # Üçüncü araç: şirketin İŞİ nasıl gidiyor. Fiyat "ne ediyor", eğilim
    # "nasıl gidiyor", bu ise "kârlı mı, borçlu mu". Üçü de ADI GEÇEN bir
    # enstrüman hakkında ve üçü de bu sistemin tuttuğu veriden cevaplanıyor;
    # ayrı bir uzman ajan açmak, aynı soruyu yönlendiricide üçe bölmeyi
    # gerektirirdi.
    if plan.get("tool") == "get_company_fundamentals":
        symbols = [
            str(symbol).upper()
            for symbol in (args.get("symbols") or [])
            if str(symbol).strip()
        ] or [t for t in ((state.get("entities") or {}).get("tickers") or [])]
        if symbols:
            return await _run_tool(
                state, "get_company_fundamentals",
                # Sözleşmenin tavanı beş ve aşıldığında REDDEDİYOR. Burada
                # kırpmak, aracın bilerek reddettiği şeyi sessizce yapmak
                # olurdu -- ama turu bir 422'ye çevirmek de kullanıcıya
                # kendi sorusunun cevabı yerine bir hata gösterirdi.
                # Kırpılan sembol `warnings`'e girmiyor çünkü araç onu hiç
                # görmüyor; bu yüzden model beşten fazlasını istediğinde
                # yönlendirici zaten en fazla beş ticker çıkarıyor.
                {"symbols": symbols[:5]},
                assumptions=assumptions,
                empty_when=lambda p: not p.get("instruments"),
            )
        # Sembol yoksa fiyat yoluna düşülüyor: adı geçen bir şey varsa o
        # cevaplanır, tek sembol isteyen bir aracı boşa çağırmaktansa.

    # Dördüncü araç: adı konmuş bir ÇEYREK. Diğer üçünün hiçbirinde seri
    # yok -- fiyat anlık, eğilim türetilmiş, temel veri anlık görüntü. "Son
    # çeyrek kârı" sorusunu cevaplayabilen tek yol bu.
    if plan.get("tool") == "get_quarterly_financials":
        symbol = args.get("symbol") or _first_ticker(state)
        if symbol:
            return await _run_tool(
                state, "get_quarterly_financials", {"symbol": str(symbol).upper()},
                assumptions=assumptions,
                # Boş seri, ölçülmüş bir cevap: 40 hissenin 6'sında hiç
                # çeyreklik veri yok. Hata değil.
                empty_when=lambda p: not p.get("periods"),
            )

    # A turn that named no instrument and no filter would otherwise screen the
    # entire universe and hand the model 50 rows to summarise.
    if not args.get("symbols") and not args.get("filters"):
        tickers = (state.get("entities") or {}).get("tickers") or []
        if tickers:
            args["symbols"] = tickers
    args.pop("symbol", None)
    args.setdefault("top_k", 20)
    return await _run_tool(
        state, "get_market_data", args,
        assumptions=assumptions,
        empty_when=lambda p: not p.get("instruments"),
        repair_prompt=SPECIALIST_PROMPTS["MARKET_DATA_AGENT"],
    )


def _first_ticker(state: MoneyFastState) -> Optional[str]:
    """The instrument the router extracted, when the plan named none."""
    tickers = (state.get("entities") or {}).get("tickers") or []
    return tickers[0] if tickers else None


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
    # run lower, so 0.62 discarded good hits and the assistant reported "no
    # sources found" for news it was holding.
    #
    # 0.35 then overcorrected. Measured over one day of real turns:
    #
    #   "hangi bankalar ile ilgili haberer var"   0.685 .. 0.579   relevant
    #   "halkbank özelinde detaylandırır mısın"   0.577 .. 0.537   relevant
    #   "bana banka haberleri getir"              0.592 .. 0.466   relevant
    #   "hisse senedi analiz"                     0.398 .. 0.365   JUNK
    #
    # The junk band tops out below 0.40 and the worst genuine hit sits at
    # 0.466, so 0.45 separates them with room on both sides. That last query
    # returned a German bank's brothel-loan investigation and it was
    # presented to the user as stock analysis.
    #
    # Overridden here rather than in the tool, because the caller owns this
    # choice and the contract's default has to stay what it says.
    args["min_similarity"] = float(os.getenv("RAG_MIN_SIMILARITY", "0.45"))
    # The retriever scans this reversed and folds in the newest user turn it
    # finds, so the count only affects payload size, not what gets resolved.
    args["conversation_context"] = (state.get("conversation_history") or [])[
        -HISTORY_MAX_TURNS:
    ]
    # Whose uploaded documents this search may reach, on top of the public
    # news corpus. Deliberately NOT the `"unknown"` sentinel the other nodes
    # use: that is a string, and a string that matches no user reads as a
    # narrowing filter rather than as "there is nobody here". None says the
    # second thing, which is what an anonymous turn actually is.
    args["user_id"] = state.get("user_id") or None

    result = await _run_tool(
        state, "rag_semantic_market_search", args,
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("results"),
    )
    return await _fold_in_own_documents(state, args, result)


#: Kullanıcının kendi belgelerine ayrılan sonuç sayısı.
#:
#: Tek bir aramada haberle YARIŞTIRMAK, yüklenen belgeyi pratikte
#: bulunamaz yapıyor. Ölçüldü: bir kullanıcı bilanço tablosu yükledi,
#: "EBITDA marjı ve hasılat" sorgusu belgeyi hiç döndürmedi; belge
#: aslında 0,605 benzerlikle eşleşiyordu ama binlerce haber parçası
#: arasında ilk yirmiye giremiyordu. Kendi yüklediği dosyayı bir daha
#: göremeyen bir yükleme özelliği, çalışmayan bir özelliktir.
OWN_DOCUMENT_SLOTS = 3

#: Yüklenen belgelerin `rag`'daki kategorisi (bkz. backend document_service).
OWN_DOCUMENT_CATEGORY = "USER_UPLOAD"

#: Kullanıcının kendi belgeleri için AYRI ve daha düşük eşik.
#:
#: 0,45 haber için doğru: binlerce parçalık bir derlemde alakasız olanı
#: elemek gerekiyor ve ölçüm o bandı gösterdi. Kişisel belgelerde elenecek
#: bir sel yok -- kullanıcının bir avuç dosyası var ve sorusu onlardan
#: birine değiniyorsa en iyi eşleşmeyi vermek neredeyse her zaman doğru.
#:
#: Ölçüldü, kullanıcının kendi yüklediği bilanço tablosuna karşı:
#:
#:   "bilançoda EBITDA marjı"                    0,390
#:   "EBITDA marjı"                              0,380
#:   "hasılat ne kadar"                          0,314
#:   "Yüklediğim bilançoda EBITDA marjı ne olmuş?" 0,289
#:
#: Sonuncusu kullanıcının GERÇEKTEN yazdığı cümle ve dolgu kelimeleri
#: gömmeyi seyreltiyor. 0,45 hepsini eliyordu: kullanıcı dosyayı yükledi,
#: sordu ve "veri bulunamadı" cevabı aldı. 0,25 dördünü de geçiriyor.
OWN_DOCUMENT_MIN_SIMILARITY = 0.25


async def _fold_in_own_documents(
    state: MoneyFastState, args: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Kullanıcının kendi belgelerine ayrı bir arama ve ayrı yer.

    Haberle aynı sıralamada yarıştırmak yerine ikinci bir arama yapılıyor:
    biri "piyasada ne söyleniyor", diğeri "bu kullanıcı ne yükledi". İki ayrı
    soru ve tek bir benzerlik sıralaması ikincisini her zaman kaybettiriyor.

    Haber sonuçları KIRPILMIYOR, belgeler önlerine ekleniyor: kullanıcının
    kendi dosyası, sorduğu soruya cevap veren kaynakların en olası olanı.

    Bu arama başarısız olursa tur düşmez -- elde olan haber sonuçlarıyla
    devam eder.
    """
    if not args.get("user_id"):
        return result

    # Haber araması hata verdiyse karışılmıyor: "kaynaklara ulaşılamadı"
    # gerçek bir kesintiyi bildiriyor ve onu kullanıcının kendi belgesiyle
    # örtmek, çalışmayan bir kaynağı çalışıyor gibi göstermek olur.
    if (result.get("specialist_output") or {}).get("status") == "ERROR":
        return result

    own_args = {
        **args,
        "top_k": OWN_DOCUMENT_SLOTS,
        "filters": {"categories": [OWN_DOCUMENT_CATEGORY]},
        "min_similarity": float(
            os.getenv("RAG_OWN_DOCUMENT_MIN_SIMILARITY", str(OWN_DOCUMENT_MIN_SIMILARITY))
        ),
    }
    try:
        own = await get_mcp_client().call("rag_semantic_market_search", own_args)
    except (MCPUnavailable, MCPToolError) as exc:
        log.warning("own-document search failed: %s", exc)
        return result

    documents = (own or {}).get("results") or []
    if not documents:
        return result

    payload = result.get("specialist_output") or {}
    existing = (payload.get("data") or {}).get("results") or []
    seen = {row.get("chunk_id") for row in documents}
    merged = documents + [row for row in existing if row.get("chunk_id") not in seen]

    payload.setdefault("data", {})["results"] = merged
    # Boş bir haber araması, kullanıcının belgesi bulunduğunda artık boş
    # değil: "kaynak bulunamadı" demek yanlış olurdu.
    payload["status"] = "OK"
    return {**result, "specialist_output": payload}


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

    # Ölçülemeyen faktör turu, PLAN SORULMADAN kesiliyor.
    #
    # Reddi `_scenario_branch`'e bırakmak yetmiyordu: o yalnızca model
    # `run_portfolio_scenario` seçtiğinde çalışıyor. ÖLÇÜLDÜ -- model bunun
    # yerine `get_portfolio_stress_test`'i seçti, araç düzgün çalıştı ve model
    # döviz ile altın replaylerini FAİZ İÇİN VEKİL olarak kullanıp "faiz
    # artışıyla ilişkili olası TL güçlenmesi..." diye bir okuma kurdu. Araç
    # sözleşmesi bunu açıkça yasaklıyor ve yasak tutmadı.
    #
    # Koşul, yönlendirmeyi zorlayan koşulun AYNISI: tek bir doğru, iki yerde
    # uygulanıyor. Bir LLM çağrısı da tasarruf ediliyor.
    if _is_unmeasurable_factor_turn(state["user_message"]):
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "UNSUPPORTED",
                "user_message_tr": UNSUPPORTED_FACTOR_TR,
                "data": None,
            },
            "tools_used": (state.get("tools_used") or []) + ["get_portfolio_positions"],
        }

    plan = await _llm_json(
        SPECIALIST_PROMPTS["RISK_STRATEGY_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    lookback = args.get("lookback") or "1Y"

    # "Ne olurdu" ailesi: üçü de bu düğümden çıkıyor ve üçü de ÖLÇÜM. Ayrı
    # bir uzman ajan açılmadı, çünkü hepsi aynı portföyü aynı seriden okuyor
    # ve yönlendirmeyi ikiye bölmek, "dolar çıksa ne olur" ile "riskim ne"
    # arasında bir sınır çizmeyi gerektirirdi -- ikisi de risk ölçümü.
    branch = _WHAT_IF_TOOLS.get(plan.get("tool") or "")
    if branch is not None:
        return await branch(state, user_id, args, lookback, plan)

    args["positions"] = positions
    args["lookback"] = lookback
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

    # Aynı sebeple best-effort: teknik görünüm turu zenginleştirir, ayakta
    # tutmaz. Buraya bağlı, MARKET_DATA_AGENT'a değil -- o ajanın holdings
    # erişimi yok ve olmaması bilinçli; portföyün TAMAMINI ölçen tek düğüm bu.
    posture = None
    try:
        posture = await mcp.call("get_portfolio_technicals", {"user_id": user_id})
    except (MCPUnavailable, MCPToolError) as exc:
        log.warning("portfolio technicals unavailable: %s", exc)

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
    if posture and isinstance(data, dict):
        # Ölçümün yanına, içine değil bir kardeş anahtar olarak da değil:
        # synthesis `data`'yı okuyor. Volatilite ve düşüş, portföyün kendi
        # geçmişine göre nerede DURDUĞUNU söylemiyor -- "riskim ne" sorusunun
        # cevabı iki ölçümün ikisini birden istiyor.
        data["technical_posture"] = _slim_posture(posture)
        tools.append("get_portfolio_technicals")
    if summary and isinstance(data, dict):
        # Carried inside the metrics payload rather than beside it: the
        # synthesis step reads `data`, and a sibling key would need every
        # consumer to learn about it.
        data["profile_summary"] = _slim_summary(summary)
        tools.append("get_risk_profile_summary")
    out["tools_used"] = tools
    return out



# ── "Ne olurdu" dalları ──────────────────────────────────────────────────────
#
# Üçü de RISK_STRATEGY_AGENT'ın arkasında, MARKET_DATA_AGENT'ta değil: hepsi
# kullanıcının PORTFÖYÜNÜ ölçüyor ve o ajanın holdings erişimi yok.


async def _scenario_branch(state, user_id, args, lookback, plan):
    """`run_portfolio_scenario`: bir faktör oynasaydı."""
    factor = str(args.get("factor") or "").upper()
    if factor not in SCENARIO_FACTORS:
        # Ölçülemeyen faktörü aracın 422'sine göndermek yerine burada
        # kesiliyor: en sık geleni FAİZ ve sistemde faiz serisi yok. Bir
        # döviz faktörünü vekil olarak koymak, ölçülmemiş bir sayıyı ölçüm
        # diye vermek olurdu.
        # EMPTY DEĞİL. "Boş" bir sonuç, aracın çalışıp bir şey bulamaması
        # demek ve sentez kuralı onu "veri şu anda yok"a çeviriyor -- ölçüldü,
        # kullanıcıya iki kez "tekrar denememi ister misiniz" dendi. Bu ise
        # kalıcı bir sınır ve cümlesi kodda duruyor.
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "UNSUPPORTED",
                "user_message_tr": UNSUPPORTED_FACTOR_TR,
                "data": None,
            },
            "tools_used": state.get("tools_used") or [],
        }
    return await _run_tool(
        state, "run_portfolio_scenario",
        {
            "user_id": user_id,
            "factor": factor,
            # Kullanıcı bir büyüklük söylemediyse %10. Varsayım aracın
            # sözleşmesinde de yazılı ve ajana bunu SÖYLEMESİ talimat verilmiş.
            "shock_pct": float(args.get("shock_pct") or 10),
            "lookback": lookback,
        },
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("statement"),
    )


async def _stress_branch(state, user_id, args, lookback, plan):
    """`get_portfolio_stress_test`: gerçekten olanlar."""
    return await _run_tool(
        state, "get_portfolio_stress_test",
        {"user_id": user_id, "lookback": lookback},
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("worst_days") and not p.get("replays"),
    )


async def _simulate_branch(state, user_id, args, lookback, plan):
    """`simulate_position_change`: bir alım/satım yapılsaydı.

    Değişikliği SUNUCU ÖNERMEZ. Model bir değişiklik üretmediyse tur burada
    biter ve kullanıcıya sorulur -- kendi kendine bir miktar uydurmak, bir
    öneri motoruna dönüşmenin ilk adımı olurdu.
    """
    changes = [
        {"symbol": str(row["symbol"]).upper(),
         "quantity_delta": float(row["quantity_delta"])}
        for row in (args.get("changes") or [])
        if isinstance(row, dict) and row.get("symbol") and row.get("quantity_delta")
    ]
    if not changes:
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["changes"],
                "clarification_request": (
                    "Hangi hisseden ne kadar alıp sattığınızı varsayalım?"
                ),
            },
            "tools_used": state.get("tools_used") or [],
        }
    return await _run_tool(
        state, "simulate_position_change",
        {"user_id": user_id, "changes": changes[:10], "lookback": lookback},
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("current"),
    )


#: Backend'in `scenario.FACTORS`'ıyla ve aracın `FACTORS`'ıyla AYNI liste.
#: Üçü ayrışırsa model geçersiz bir faktör üretir ve kullanıcı "ölçemedim"
#: cevabı alır -- `ALLOWED_SORTS` ile bir kez yaşanmış bir hata.
SCENARIO_FACTORS = ("USDTRY", "EURTRY", "XU100", "XAUUSD")

#: Kullanıcıya gösterilecek adlar. Sembol sızmaz (`prompts.py`'deki NAMING
#: kuralı); backend'in `scenario.FACTORS`'ındaki adların aynısı.
SCENARIO_FACTOR_NAMES = "Dolar/TL, Euro/TL, BIST 100 ve ons altın"

#: Ölçülemeyen bir faktör istendiğinde kullanıcıya gidecek cümle, KODDA.
#: Modelden istenmiyor, çünkü ölçüldü: aynı durum iki kez "veriler şu anda
#: alınamadı, tekrar denememi ister misiniz" diye anlatıldı -- bir KESİNTİ
#: dili. Oysa faiz serisi yapısal olarak yok; tekrar denemek hiçbir zaman
#: işe yaramayacak ve öyle demek kullanıcıya olmayan bir umut vermek.
UNSUPPORTED_FACTOR_TR = (
    "Faiz ve enflasyon için bu sistemde günlük bir seri tutulmuyor, "
    "dolayısıyla portföyünüzün onlara duyarlılığı ölçülemiyor — bu geçici "
    "bir sorun değil, ölçebildiklerimin sınırı. Ölçebildiğim faktörler: "
    f"{SCENARIO_FACTOR_NAMES}."
)

_WHAT_IF_TOOLS = {
    "run_portfolio_scenario": _scenario_branch,
    "get_portfolio_stress_test": _stress_branch,
    "simulate_position_change": _simulate_branch,
}


def _slim_posture(posture: dict[str, Any]) -> dict[str, Any]:
    """Teknik görünümün YAZARA giden hâli: cümleler, ham gösterge blokları değil.

    Pozisyon başına yirmi alanlık `signals` bloğu EKRANIN ihtiyacı -- tablo
    onu çiziyor. Yazarın ihtiyacı `summary.statement` ve satır başına
    `narrative`; araç sözleşmesi zaten "cümleleri olduğu gibi aktar" diyor ve
    göstergeleri alan adlarıyla anmayı YASAKLIYOR. Alan adlarını yazara
    göndermek hem israf hem de o yasağın önüne yem koymak.

    Ölçüldü ve bu bir GERİLEME düzeltmesi: `technical_posture` eklendiğinde
    risk turunun sentez gövdesi 3.269 karakter büyüdü ve toplam, sağlayıcının
    tek istek sınırını aştı (8.393 token istendi, sınır 8.000). Sonuç,
    kullanıcının bildirdiği davranıştı: aynı soru her seferinde "yoğunluk
    sınırına takıldım" cevabı veriyor, aynı oturumdaki başka sorular anında
    cevaplanıyordu. Kırpma bu bloğu 3.269'dan ~1.440'a indiriyor.

    Sayılar kaybolmuyor, YOLU değişiyor: ekran aynı uç noktadan tam hâlini
    okumaya devam ediyor.
    """
    positions = posture.get("positions") or []
    return {
        "summary": posture.get("summary") or {},
        "positions": [
            {
                "symbol": row.get("symbol"),
                "trend": row.get("trend"),
                "narrative": row.get("narrative"),
            }
            for row in positions
        ],
        "unconvertible": posture.get("unconvertible") or [],
    }

def _slim_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Risk özetinin YAZARA giden hâli.

    `_slim_posture` ile aynı gerekçe ve aynı ölçülen sebep. v2.17 ile özete
    iki karşılaştırma daha eklendi -- ürün grubu beyanı ve kullanıcının kendi
    hedefinden sapma -- ve toplam yine sağlayıcının tek istek sınırını aştı:
    kullanıcı "hedef dağılımımdan ne kadar saptım" sorusuna "tek seferde
    işleyebileceğimden büyük çıktı" cevabı aldı.

    İki blokta da YAZARIN ihtiyacı hazır CÜMLELER, satırlar değil. Satırlar
    EKRANIN ihtiyacı: tablo onlardan çiziliyor ve ekran aynı uç noktadan tam
    hâlini okumaya devam ediyor.

    Satırları da göndermek denendi ve yetmedi. Risk turu bu eklemeden ÖNCE de
    tavana yakındı -- ölçüldü: teknik görünüm 7.463, risk özeti 3.557,
    metrikler 1.605 karakter -- ve sekiz pozisyonlu bir portföyde gövde
    9.744'e çıkıp kırpıldı, istek yine 8.128 token ile 8.000'lik sınırı aştı.
    `allocation_drift.statement` en büyük farkı zaten iki sayısıyla birlikte
    adlandırıyor, dolayısıyla cevabın kendisi cümlede duruyor.
    """
    # `metrics` ve `data_quality` bu gövdede İKİ KEZ bulunuyordu: ölçüm
    # aracının kendi çıktısı zaten aynı turda, aynı `data` sözlüğünde
    # duruyor ve istatistiklerin yetkili kaynağı o. Özetin kopyası yalnızca
    # puanın hangi alt kümeden üretildiğini gösteriyor -- ekranın işi, yazarın
    # değil.
    slim = {
        key: value
        for key, value in summary.items()
        if key not in ("metrics", "data_quality")
    }
    exposure = summary.get("group_exposure")
    if isinstance(exposure, dict):
        slim["group_exposure"] = {
            "assessed": exposure.get("assessed"),
            "statements": [
                row.get("statement") for row in exposure.get("groups") or []
            ],
        }
    drift = summary.get("allocation_drift")
    if isinstance(drift, dict):
        slim["allocation_drift"] = {
            "has_target": drift.get("has_target"),
            "statement": drift.get("statement"),
        }
    return slim


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
    # A disclosed condition is not a crisis, a threat, or a budgeting
    # problem. "ben şizofrenim" was answered with the FINANCIAL_DISTRESS
    # text -- a lecture on how borrowed money raises risk -- because this
    # category did not exist and that one was the fallback.
    "MENTAL_HEALTH_DISCLOSURE": (
        "The user has disclosed a mental health condition or difficulty. "
        "This is NOT a crisis and NOT a financial turn. Respond briefly and "
        "warmly in Turkish: acknowledge what they shared without dramatising "
        "it, and make clear they are still welcome here. "
        "Do NOT mention markets, portfolios, debt, budgeting, investing or "
        "risk tolerance. Do NOT diagnose, advise on treatment, or ask about "
        "symptoms. Do NOT offer to connect them to an adviser or specialist "
        "-- this product cannot do that. "
        "You MAY offer to continue with whatever they were asking about. "
        "Do not state phone numbers yourself; they are appended verbatim. "
        "No emoji, no humour, at most three sentences."
    ),
    # The fallback. Distress was detected but not identified, so the reply
    # must be safe under EVERY reading of it -- which means no financial
    # content, because the one thing we know is that we do not know which
    # kind of trouble this is.
    "GENERIC_DISTRESS": (
        "The user is in some form of distress that has not been identified. "
        "Respond briefly and warmly in Turkish: acknowledge it, and ask an "
        "open question about what would help. "
        "Do NOT assume the problem is financial. Do NOT mention markets, "
        "portfolios, debt, budgeting or investing unless the user has "
        "already raised them in this turn. Do NOT offer to connect them to "
        "an adviser -- this product cannot do that. "
        "Do not state phone numbers yourself; they are appended verbatim. "
        "No emoji, no humour, at most three sentences."
    ),
}

#: The vocabulary `handoff_node` selects on.
#:
#: The regex pre-filter emits these names, but the ROUTER MODEL emits its own
#: and `router_node` unions them into the same list without checking. Measured:
#: "i am jumping off a cliff" produced `SELF_HARM` -- one character class away
#: from the canonical name -- and `handoff_node`, which matched exact strings
#: and fell through to FINANCIAL_DISTRESS, answered a suicide statement with
#: budgeting tips and no crisis line.
#:
#: The synonyms are the model's observed and plausible outputs. `primary_intent`
#: is read through the same table: in that turn the intent was already
#: `SELF_HARM` and nothing looked at it.
_FLAG_SYNONYMS = {
    "SELF_HARM": "SELF_HARM_RISK",
    "SELF_HARM_RISK": "SELF_HARM_RISK",
    "SELF_INJURY": "SELF_HARM_RISK",
    "SUICIDE": "SELF_HARM_RISK",
    "SUICIDAL": "SELF_HARM_RISK",
    "SUICIDE_RISK": "SELF_HARM_RISK",
    "SUICIDAL_IDEATION": "SELF_HARM_RISK",
    "COERCION": "COERCION_RISK",
    "COERCION_RISK": "COERCION_RISK",
    "THREAT": "COERCION_RISK",
    "EXTORTION": "COERCION_RISK",
    "BLACKMAIL": "COERCION_RISK",
    "MENTAL_HEALTH": "MENTAL_HEALTH_DISCLOSURE",
    "MENTAL_HEALTH_DISCLOSURE": "MENTAL_HEALTH_DISCLOSURE",
    "PSYCHOLOGICAL_DISTRESS": "MENTAL_HEALTH_DISCLOSURE",
    "FINANCIAL_DISTRESS": "FINANCIAL_DISTRESS",
}

#: Most serious first. A turn carrying several is answered as the worst one.
_CATEGORY_PRECEDENCE = (
    "SELF_HARM_RISK",
    "COERCION_RISK",
    "MENTAL_HEALTH_DISCLOSURE",
    "FINANCIAL_DISTRESS",
)

#: Resources per category. FINANCIAL_DISTRESS carries none deliberately: its
#: answer is budgeting, and a crisis line under a debt question would
#: misread the situation back at the user.
_CATEGORY_NOTICES = {
    "SELF_HARM_RISK": [CRISIS_RESOURCES_TR],
    "COERCION_RISK": [COERCION_RESOURCES_TR],
    "MENTAL_HEALTH_DISCLOSURE": [CRISIS_RESOURCES_TR],
    "FINANCIAL_DISTRESS": [],
    "GENERIC_DISTRESS": [CRISIS_RESOURCES_TR],
}


def handoff_category(flags: list[str], primary_intent: str | None = None) -> str:
    """Which distress response this turn gets.

    Unrecognised signals land on GENERIC_DISTRESS, never on
    FINANCIAL_DISTRESS. The cost of the two mistakes is not symmetric: a
    suicidal user handed a budgeting lecture is a far worse outcome than an
    indebted user handed an unnecessarily gentle one, and the fallback is by
    definition the branch taken when we do not know which we are looking at.
    """
    candidates = {
        _FLAG_SYNONYMS[name]
        for name in list(flags) + ([primary_intent] if primary_intent else [])
        if name in _FLAG_SYNONYMS
    }
    for category in _CATEGORY_PRECEDENCE:
        if category in candidates:
            return category
    return "GENERIC_DISTRESS"


async def handoff_node(state: MoneyFastState) -> dict[str, Any]:
    """Unsafe or distress. No tools, no screens, no instruments."""
    flags = state.get("safety_flags") or []
    category = handoff_category(flags, state.get("primary_intent"))
    notices = _CATEGORY_NOTICES[category]

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



#: Sentez gövdesinin karakter tavanı, TAHMİN DEĞİL ÖLÇÜM.
#:
#: Sağlayıcının istek başına sınırı 8.000 token. Sabit maliyet ölçüldü:
#: sistem prompt'u 15.874 + şablon 2.029 = 17.903 karakter (~4.475 token).
#: Sohbet geçmişi ölçülen turlarda ~1.500 token tutuyor. Geriye kalan
#: ~2.000 token ≈ 8.000 karakter.
#:
#: Önceki değer 12.000'di ve nereden geldiği yazılı değildi; `technical_posture`
#: eklenince toplam sınırı aştı ve kullanıcı bunu üründe gördü.
SYNTHESIS_PAYLOAD_CHARS = 8000


def _fit_payload(payload: dict[str, Any]) -> str:
    """Uzman çıktısını sentez bütçesine sığdırır ve kırptığında SÖYLER.

    Kırpma son çare: JSON'u ortasından kesmek modele bozuk bir gövde vermek
    demek ve bu gövdeden okunan bir sayı yanlış olabilir. Bu yüzden asıl iş
    kırpmak değil, gövdeyi baştan küçük tutmak (`_slim_posture`); burası
    yalnızca öngörülmemiş bir büyümenin turu bir sağlayıcı hatasına
    çevirmesini engelliyor.

    Sessizce kırpmıyor: bir uyarı satırı, gövdenin neden eksik göründüğünü
    log'da aranabilir kılıyor.
    """
    # Girinti YOK. Ölçüldü: aynı risk turu sıkıştırılmış hâlde 6.388,
    # `indent=2` ile 8.707 karakter -- bütçenin üçte biri, modelin hiçbir
    # işine yaramayan boşluğa gidiyordu. Sekiz pozisyonlu bir portföyde tur
    # bu yüzden sığmıyordu ve kullanıcı "tek seferde işleyebileceğimden büyük
    # çıktı" cevabı alıyordu; kırpma da devreye giriyor ama kırpılmış JSON
    # zaten bozuk bir gövde demek.
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= SYNTHESIS_PAYLOAD_CHARS:
        return text
    log.warning(
        "synthesis payload truncated: %d -> %d chars", len(text), SYNTHESIS_PAYLOAD_CHARS
    )
    return text[:SYNTHESIS_PAYLOAD_CHARS]

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
                specialist_json=_fit_payload(state.get("specialist_output") or {}),
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


#: Koşullu bir okumanın ayrılmaz yarısı. Backend'in `scenario.HEDGE_TR`'si ve
#: `technicals.HEDGE_TR`'si ile AYNI cümle -- üç yerde üç farklı çekince
#: yazmak, birinin daha az bağlayıcı olduğu izlenimi verirdi.
SCENARIO_HEDGE_TR = (
    "Bu bir tahmin değil, geçmiş birlikte hareketin ölçümüdür; geçmiş fiyat "
    "hareketi geleceği belirlemez."
)

#: Çekincenin metinde zaten geçtiğini anlamak için aranan parça. Tam cümleyi
#: aramak, modelin küçük bir yeniden ifadesinde ikinci bir kopya eklerdi.
_HEDGE_MARK = "geleceği belirlemez"

#: Çekincenin garanti edildiği araçlar. Üçü de KOŞULLU okuma üretiyor.
HEDGED_TOOLS = frozenset(
    {"run_portfolio_scenario", "get_portfolio_stress_test", "simulate_position_change"}
)


def _keep_hedge(state: MoneyFastState, out: dict[str, Any]) -> dict[str, Any]:
    """Koşullu bir turun çekincesini kapının HER dalından geçirir.

    `_keep_crisis` ile aynı sebep ve aynı ders: prompt tavsiyedir. Araç
    sözleşmesi "`statement`'ı çekincesiyle birlikte olduğu gibi aktar" diyor
    ve ÖLÇÜLDÜ -- model senaryo cümlesini yeniden yazdı ve kapanış çekincesini
    düşürdü. Kalan metin "portföyünüzün değeri yaklaşık %6,8 azalır" idi:
    koşulsuz, çekincesiz, ve ölçümün söylemediği bir kesinlikte.

    Genel uygunluk açıklaması (DISC-GENERAL) bunun yerini tutmuyor: o
    içeriğin yatırım danışmanlığı olmadığını söylüyor, bu ise sayının bir
    tahmin değil bir ölçüm olduğunu.

    Metin çekinceyi zaten taşıyorsa ikinci kez eklenmiyor.
    """
    if not (HEDGED_TOOLS & set(state.get("tools_used") or [])):
        return out
    if _HEDGE_MARK in (out.get("final_output") or ""):
        return out
    existing = out.get("disclosures") or []
    if any(_HEDGE_MARK in item for item in existing):
        return out
    out["disclosures"] = existing + [SCENARIO_HEDGE_TR]
    return out


def _keep_crisis(state: MoneyFastState, out: dict[str, Any]) -> dict[str, Any]:
    """Ensure a distress turn carries its resources out of the gate.

    Applied to every branch, BLOCK included. A blocked crisis turn used to end
    at a generic failure string with nothing actionable in it, which is the
    worst moment to hand someone a dead end.

    Koşullu okumanın çekincesi de buradan geçiyor. Ayrı bir sarmalayıcı,
    kapının yedi dalından birinin unutulması demekti -- bu fonksiyon zaten
    hepsinden geçiyor.
    """
    out = _keep_hedge(state, out)
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
