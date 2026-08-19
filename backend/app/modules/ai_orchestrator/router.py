import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from .schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["AI Orchestrator"])


@router.post("/chat", response_model=ChatResponse)
async def chat_with_orchestrator(request: ChatRequest) -> ChatResponse:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.AI_ORCHESTRATOR_URL}/chat",
                json=request.model_dump(),
            )
            response.raise_for_status()
            return ChatResponse(**response.json())
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503, detail=f"AI orchestrator unreachable: {exc}"
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI orchestrator returned an error: {exc.response.status_code}",
        )


@router.get("/health")
async def health_check():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.AI_ORCHESTRATOR_URL}/readyz")
            return {"status": "ok", "orchestrator": response.json()}
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503, detail=f"AI orchestrator unreachable: {exc}"
        )
