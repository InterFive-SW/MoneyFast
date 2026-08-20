"""FastAPI surface for the orchestrator container.

/healthz  liveness, no dependencies
/readyz   readiness, pings the MCP server over the Docker network
/chat     one turn through the graph
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import widgets
from mcp_client import get_mcp_client
from orchestrator import run_turn

log = logging.getLogger("moneyfast.api")
app = FastAPI(title="MoneyFast Orchestrator", version="1.0.0")


class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=4000)
    # Resolved from the bearer token by the backend before it reaches here;
    # see backend/app/core/deps.py. None means anonymous, which the portfolio
    # tools correctly treat as "no holdings to read".
    user_id: Optional[str] = None
    thread_id: str = "default"
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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    try:
        tools = await get_mcp_client().list_tools()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"mcp unreachable: {exc}") from exc
    return {"status": "ready", "mcp_tools": tools}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    state = await run_turn(
        req.user_message,
        user_id=req.user_id or "anonymous",
        conversation_history=[t.model_dump() for t in req.conversation_history],
        thread_id=req.thread_id,
    )
    # Internal fields (specialist_output, draft_response, tools_used) stay
    # server side. The client sees only what the user may see -- which is why
    # the widget is projected here rather than by shipping specialist_output
    # across the boundary for the backend to interpret.
    widget, context_topic = widgets.build(state)
    return ChatResponse(
        final_output=state.get("final_output") or "",
        primary_intent=state.get("primary_intent"),
        target_agent=state.get("target_agent"),
        compliance_verdict=state.get("compliance_verdict"),
        disclosures=state.get("disclosures") or [],
        widget=widget,
        context_topic=context_topic,
    )
