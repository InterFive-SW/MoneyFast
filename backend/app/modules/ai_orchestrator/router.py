import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_optional_user_id
from . import service
from .schemas import ChatRequest, ChatResponse

log = logging.getLogger("moneyfast.ai_orchestrator")

router = APIRouter(tags=["AI Orchestrator"])

#: One turn can legitimately take a while: routing, a specialist plan, a tool
#: round trip, synthesis, and the compliance gate are separate model calls,
#: and Groq's free tier answers a 429 with a retry-after in the tens of
#: seconds. The previous 30s budget turned an ordinary rate limit into a 503
#: with no explanation, which reads to the user as an outage.
CHAT_TIMEOUT_SECONDS = 180.0
HEALTH_TIMEOUT_SECONDS = 5.0

BUSY_MESSAGE = (
    "Şu anda yoğunluk var ve yanıtı zamanında hazırlayamadım. "
    "Birkaç saniye sonra tekrar dener misiniz?"
)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_orchestrator(
    request: ChatRequest,
    user_id: Optional[str] = Depends(get_optional_user_id),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """
    Kullanıcı mesajını orchestrator'a iletir ve tek turluk yanıtı döner.

    `user_id` gövdeden DEĞİL, bearer token'dan çözülür. MCP sözleşmesi bu
    değerin yalnızca doğrulanmış oturumdan gelmesini şart koşuyor; gövdede
    olsaydı herkes tek bir JSON alanını değiştirerek başkasının portföyünü
    okuyabilirdi. Token yoksa `None` gider ve ajanlar bunu "okunacak portföy
    yok" olarak ele alır.
    """
    # Stored history wins over the client's copy for a signed-in user: it is
    # what resolves "peki ya o?" to an instrument, so a client able to rewrite
    # it could steer a tool call at a different holding. An anonymous caller
    # has nothing stored and falls back to what they sent, which can only
    # mislead them about their own conversation.
    history = service.load_history(db, user_id, request.thread_id) or [
        turn.model_dump() for turn in request.conversation_history
    ]

    payload = {
        "user_message": request.user_message,
        "user_id": user_id,
        "thread_id": request.thread_id,
        "conversation_history": history,
    }

    try:
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.AI_ORCHESTRATOR_URL}/chat", json=payload
            )
            response.raise_for_status()
            answer = ChatResponse(**response.json())
    except httpx.TimeoutException as exc:
        # Distinguished from a connect error on purpose: the orchestrator is
        # up, it just did not finish. Telling the user "unreachable" would
        # send them looking for an outage that is not there.
        log.warning("orchestrator timed out after %ss: %s", CHAT_TIMEOUT_SECONDS, exc)
        raise HTTPException(status_code=504, detail=BUSY_MESSAGE)
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503, detail=f"AI orchestrator unreachable: {exc}"
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI orchestrator returned an error: {exc.response.status_code}",
        )

    answer.conversation_id = service.record_turn(
        db,
        user_id=user_id,
        thread_id=request.thread_id,
        user_message=request.user_message,
        assistant_message=answer.final_output,
        meta={
            "primary_intent": answer.primary_intent,
            "target_agent": answer.target_agent,
            "compliance_verdict": answer.compliance_verdict,
        },
    )
    return answer


@router.get("/health")
async def health_check():
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{settings.AI_ORCHESTRATOR_URL}/readyz")
            return {"status": "ok", "orchestrator": response.json()}
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise HTTPException(
            status_code=503, detail=f"AI orchestrator unreachable: {exc}"
        )
