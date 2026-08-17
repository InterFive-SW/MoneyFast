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

from mcp_client import get_mcp_client
from orchestrator import run_turn

log = logging.getLogger("moneyfast.api")
app = FastAPI(title="MoneyFast Orchestrator", version="1.0.0")


class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=4000)
    user_id: str = "anonymous"
    thread_id: str = "default"
    conversation_history: list[Turn] = []


class ChatResponse(BaseModel):
    final_output: str
    primary_intent: Optional[str] = None
    target_agent: Optional[str] = None
    compliance_verdict: Optional[str] = None


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
        user_id=req.user_id,
        conversation_history=[t.model_dump() for t in req.conversation_history],
        thread_id=req.thread_id,
    )
    # Internal fields (specialist_output, draft_response, tools_used) stay
    # server side. The client sees only what the user may see.
    return ChatResponse(
        final_output=state.get("final_output") or "",
        primary_intent=state.get("primary_intent"),
        target_agent=state.get("target_agent"),
        compliance_verdict=state.get("compliance_verdict"),
    )
