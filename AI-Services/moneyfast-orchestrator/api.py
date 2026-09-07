"""FastAPI surface for the orchestrator container.

/healthz  liveness, no dependencies
/readyz   readiness, pings the MCP server over the Docker network
/chat     one turn through the graph
/chat/stream  the same turn, emitting real progress stages over SSE
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import agent_trace
import sanitize
import sources
import widgets
from mcp_client import get_mcp_client
import orchestrator
from orchestrator import run_turn, run_turn_streaming
from prompts import NEWS_IMPACT_JUDGE_PROMPT, NEWS_IMPACT_TASK_TEMPLATE

log = logging.getLogger("moneyfast.api")
app = FastAPI(title="MoneyFast Orchestrator", version="1.0.0")


class Turn(BaseModel):
    #: A closed set. `_history_summary` flattens each turn to
    #: "{role}: {content}" before it reaches the router prompt, so a free-form
    #: role arrives there looking exactly like an instruction. The backend
    #: enforces the same constraint; this one guards direct callers.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)
    #: Bu turda gösterilmiş kaynaklar. Modele HİÇ gitmiyor --
    #: `_history_summary` yalnızca `role` ve `content` okuyor. Yalnızca
    #: "bana kaynakça verir misin" turunun okuduğu şey; onlar olmadan o soru
    #: bir aramaya dönüşüyor ve kota hatasına açık kalıyor.
    sources: list[dict[str, Any]] = Field(default_factory=list, max_length=16)


class ChatRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=4000)
    # Resolved from the bearer token by the backend before it reaches here;
    # see backend/app/modules/ai_orchestrator/deps.py. None means anonymous,
    # which the portfolio tools correctly treat as "no holdings to read".
    user_id: Optional[str] = None
    #: Matches the width of `ai.conversations.thread_id` in the backend.
    thread_id: str = Field("default", min_length=1, max_length=64)
    conversation_history: list[Turn] = []


class ChatResponse(BaseModel):
    final_output: str
    #: Mandatory notices for this turn, verbatim. Sent as a list rather than
    #: appended to `final_output` so the chat renders them as a footnote.
    disclosures: list[str] = []
    primary_intent: Optional[str] = None
    target_agent: Optional[str] = None
    compliance_verdict: Optional[str] = None
    # Built deterministically from the specialist's tool payload, never asked
    # of the model. See widgets.py.
    widget: Optional[dict[str, Any]] = None
    context_topic: Optional[str] = None
    #: Bu cevabın dayandığı kaynaklar. Widget'la aynı kural: modelden
    #: istenmez, aracın döndürdüğünden kurulur. `sanitize` bunlara
    #: dokunmuyor -- yalnızca `final_output` üzerinde çalışıyor -- o yüzden
    #: buradaki her etiket Türkçe olarak KODDA kuruluyor, hiçbiri bir
    #: yük anahtarından alınmıyor.
    sources: list[dict[str, Any]] = []


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    try:
        tools = await get_mcp_client().list_tools()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"mcp unreachable: {exc}") from exc
    # Sağlayıcı ve model yankılanıyor: "bu container aslında hangi
    # sağlayıcıyla konuşuyor" sorusu, container'a girmeden cevaplanabilmeli.
    # `rag`'in `/readyz`'i model ve boyutu aynı sebeple döndürüyor.
    #
    # `model_name()` istemci KURMUYOR: kursaydı hazırlık yoklaması anahtarın
    # varlığına bağlanır ve eksik bir anahtar, MCP erişilebilirliğini
    # raporlamak için yazılmış bir ucu 503'e çevirirdi. Anahtar yankılanmıyor.
    return {
        "status": "ready",
        "mcp_tools": tools,
        "llm_provider": orchestrator.provider_name(),
        "llm_model": orchestrator.model_name(fast=False),
    }


class NewsItemIn(BaseModel):
    """Yargılanacak tek haber."""

    news_id: str
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=4000)
    source: str = Field(default="", max_length=120)


class NewsImpactRequest(BaseModel):
    """Bir toplu iş: haberler ve içinden seçilebilecek enstrüman evreni.

    Evren isteğin İÇİNDE geliyor, burada tutulmuyor: bu servisin veritabanı
    yok ve olmamalı. Model yalnızca bu listeden seçebiliyor; dışındaki bir ad
    aşağıda düşürülüyor.
    """

    items: list[NewsItemIn] = Field(default_factory=list, max_length=100)
    universe: list[str] = Field(default_factory=list, max_length=2000)


@app.post("/analyze/news-impact")
async def analyze_news_impact(request: NewsImpactRequest) -> dict[str, Any]:
    """Haberleri yargılar; her biri için yapılandırılmış etki satırları döner.

    Kullanıcıyla konuşmuyor, grafiğe girmiyor: bir toplu iş. Backend
    zamanlıyor ve sonucu saklıyor, LLM çıkışı burada kalıyor -- CLAUDE.md'nin
    "LLM çıkışı yalnızca `agents` servisinde" kuralı.

    **Tek bir haberin hatası turu düşürmez.** Yüz haberin birinde bozuk bir
    JSON, tüm partinin kaybı olmamalı -- ingestor'ın parçalı itme
    gerekçesiyle aynı.
    """
    universe = {code.strip().upper() for code in request.universe if code.strip()}
    results: list[dict[str, Any]] = []
    failed = 0

    for item in request.items:
        try:
            plan = await orchestrator._llm_json(
                NEWS_IMPACT_JUDGE_PROMPT,
                NEWS_IMPACT_TASK_TEMPLATE.format(
                    source=item.source or "bilinmiyor",
                    title=item.title,
                    summary=item.summary or "(özet yok)",
                    universe=", ".join(sorted(universe)) or "(boş)",
                ),
                fast=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("news impact judge failed for %s: %s", item.news_id, exc)
            failed += 1
            continue
        results.append({
            "news_id": item.news_id,
            "impacts": _clean_impacts(plan.get("impacts"), universe),
        })

    return {
        "analyzed": len(results),
        "failed": failed,
        "model": orchestrator.model_name(fast=True),
        "results": results,
    }


#: Modelin üretebileceği değerler. Tanınmayan bir değer satırı DÜŞÜRÜYOR,
#: varsayılana çevirmiyor: "UP" yerine "BULLISH" yazan bir model, sessizce
#: nötre çevrildiğinde yanlış bir yargıyı doğru gibi saklardı.
_DIRECTIONS = {"UP", "DOWN", "NEUTRAL"}
_SCOPES = {"DIRECT", "SPILLOVER"}
_MAGNITUDES = {"LOW", "MEDIUM", "HIGH"}

#: Bir haber için en fazla satır. Prompt da altıyı söylüyor; burası onu
#: ZORLUYOR, çünkü prompt tavsiyedir.
MAX_IMPACTS_PER_ITEM = 6

#: Mekanizma cümlesinin üst sınırı. Uzun bir metin, "tek cümle" kuralının
#: tutulmadığı anlamına gelir ve ekranda satır olarak okunmaz.
MAX_MECHANISM_CHARS = 400


def _clean_impacts(raw: Any, universe: set[str]) -> list[dict[str, Any]]:
    """Modelin çıktısını saklanabilir satırlara indirger.

    Evren dışı sembol, tanınmayan yön ve mekanizmasız satır DÜŞÜYOR.
    Uydurmaya karşı asıl kilit burası: prompt "listeden seç" diyor ama prompt
    tavsiyedir, ve olmayan bir sembol için etki saklamak ekranda bulunamayan
    bir satır demek.
    """
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        mechanism = str(row.get("mechanism") or "").strip()
        direction = str(row.get("direction") or "").strip().upper()
        if symbol not in universe or symbol in seen or not mechanism:
            continue
        if direction not in _DIRECTIONS:
            continue
        scope = str(row.get("scope") or "DIRECT").strip().upper()
        magnitude = str(row.get("magnitude") or "LOW").strip().upper()
        try:
            confidence = float(row.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        seen.add(symbol)
        rows.append({
            "symbol": symbol,
            "direction": direction,
            "scope": scope if scope in _SCOPES else "DIRECT",
            "magnitude": magnitude if magnitude in _MAGNITUDES else "LOW",
            # Aralığın dışına taşan bir güven, modelin ölçeği anlamadığını
            # gösteriyor; kırpmak onu sessizce doğru saymak olurdu ama satırı
            # düşürmek de tek bir alan yüzünden yargıyı atmak olurdu.
            "confidence": min(1.0, max(0.0, confidence)),
            "mechanism": mechanism[:MAX_MECHANISM_CHARS],
        })
        if len(rows) >= MAX_IMPACTS_PER_ITEM:
            break
    return rows


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    state = await run_turn(
        req.user_message,
        user_id=req.user_id or "anonymous",
        conversation_history=[t.model_dump() for t in req.conversation_history],
        thread_id=req.thread_id,
    )
    return _response_payload(state)


def _response_payload(state: dict[str, Any]) -> ChatResponse:
    """Project graph state onto what the client may see.

    Internal fields (specialist_output, draft_response, tools_used) stay server
    side; the widget is built here rather than shipping specialist_output
    across the boundary for the backend to interpret.
    """
    widget, context_topic = widgets.build(state)
    # The last gate before the user sees anything. Both /chat and /chat/stream
    # come through here, so a naming leak has exactly one place to escape.
    return ChatResponse(
        final_output=sanitize.sanitized(
            state.get("final_output") or "", agent_trace.current_trace_id()
        ),
        primary_intent=state.get("primary_intent"),
        target_agent=state.get("target_agent"),
        compliance_verdict=state.get("compliance_verdict"),
        disclosures=state.get("disclosures") or [],
        widget=widget,
        context_topic=context_topic,
        sources=sources.build(state),
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Server-sent events: `stage` while the graph runs, then one `done`.

    The ANSWER is not streamed token by token, and that is deliberate. The
    graph is fail-closed -- a draft the compliance gate blocks must never
    reach the user -- so emitting synthesis tokens as they are produced would
    show text the gate might then retract. Progress is honest and streamable;
    the answer is sent once, after it has been approved.
    """

    async def events():
        try:
            async for kind, value in run_turn_streaming(
                req.user_message,
                user_id=req.user_id or "anonymous",
                conversation_history=[t.model_dump() for t in req.conversation_history],
                thread_id=req.thread_id,
            ):
                if kind == "stage":
                    payload = json.dumps({"stage": value}, ensure_ascii=False)
                    yield f"event: stage\ndata: {payload}\n\n"
                else:
                    body = _response_payload(value).model_dump()
                    payload = json.dumps(body, ensure_ascii=False)
                    yield f"event: done\ndata: {payload}\n\n"
        except Exception as exc:  # noqa: BLE001
            # The stream has already returned 200, so a failure cannot become
            # an HTTP error code. It is reported in-band and the client falls
            # back to the buffered endpoint.
            log.exception("streaming turn failed: %s", exc)
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
