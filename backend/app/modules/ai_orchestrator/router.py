import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user_id
from . import service
from .deps import ChatIdentity, resolve_chat_identity
from . import document_service, documents
from .schemas import (
    ChatDocumentListOut,
    ChatDocumentOut,
    ChatRequest,
    ChatResponse,
    ConversationDetailOut,
    ConversationListOut,
    ConversationSummary,
    DeletedConversationOut,
    MessageOut,
    RenameConversationRequest,
)

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


def _history_for(
    db: Session, identity: ChatIdentity, request: ChatRequest
) -> list[dict]:
    """The conversation the orchestrator is allowed to see.

    Stored history wins over the client's copy for a signed-in user: it is
    what resolves "peki ya o?" to an instrument, so a client able to rewrite
    it could steer a tool call at a different holding. An anonymous caller has
    nothing stored and falls back to what they sent, which can only mislead
    them about their own conversation.

    Both branches go through `trim_history`. The fallback used to be passed
    through untouched, which left the only bound on an anonymous caller's
    payload in a different container.
    """
    return service.load_history(db, identity.user_id, request.thread_id) or (
        service.trim_history([turn.model_dump() for turn in request.conversation_history])
    )


def _turn_meta(answer: dict) -> dict:
    """What gets stored alongside the assistant message.

    `context_topic` and `disclosures` are here so a reopened conversation can
    render its bubbles the way they were first shown. Widgets deliberately are
    not: a restored portfolio widget would display an earlier turn's prices,
    and a restored action widget would offer an "Onayla" button for a proposal
    that has since expired.
    """
    return {
        "primary_intent": answer.get("primary_intent"),
        "target_agent": answer.get("target_agent"),
        "compliance_verdict": answer.get("compliance_verdict"),
        "context_topic": answer.get("context_topic"),
        "disclosures": answer.get("disclosures") or [],
    }


@router.post("/chat", response_model=ChatResponse)
async def chat_with_orchestrator(
    request: ChatRequest,
    identity: ChatIdentity = Depends(resolve_chat_identity),
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
    history = _history_for(db, identity, request)

    payload = {
        "user_message": request.user_message,
        "user_id": identity.user_id,
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
        user_id=identity.user_id,
        thread_id=request.thread_id,
        user_message=request.user_message,
        assistant_message=answer.final_output,
        meta=_turn_meta(answer.model_dump()),
    )
    answer.persistence = service.persistence_status(
        identity.user_id, identity.token_present, answer.conversation_id
    )
    return answer


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    identity: ChatIdentity = Depends(resolve_chat_identity),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Sohbetin akış (SSE) sürümü. Kimlik çözümü `/chat` ile birebir aynı.

    Yanıt tek parça değil: graf düğümleri ilerledikçe `stage` olayları,
    sonunda tek bir `done` olayı gönderilir. Model çıktısı token token
    akmaz — uygunluk kapısı fail-closed çalışıyor ve engellediği bir taslak
    kullanıcıya ulaşmamalı; ekrana yazılmış bir metni geri almak bu güvenceyi
    anlamsız kılardı.

    Tur, tıpkı `/chat`'te olduğu gibi bitiminde kaydedilir; akış sürümünde
    kayıt `done` olayı üretildikten sonra yapılır.
    """
    history = _history_for(db, identity, request)
    payload = {
        "user_message": request.user_message,
        "user_id": identity.user_id,
        "thread_id": request.thread_id,
        "conversation_history": history,
    }

    async def relay():
        try:
            async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
                async with client.stream(
                    "POST", f"{settings.AI_ORCHESTRATOR_URL}/chat/stream", json=payload
                ) as upstream:
                    upstream.raise_for_status()
                    answer: Optional[dict] = None
                    async for line in upstream.aiter_lines():
                        # Olayı olduğu gibi geçiriyoruz; `done` gövdesini
                        # ayrıca yakalıyoruz çünkü tur kaydı burada yapılıyor.
                        if line.startswith("data: "):
                            try:
                                body = json.loads(line[6:])
                            except json.JSONDecodeError:
                                body = None
                            if isinstance(body, dict) and "final_output" in body:
                                answer = body
                        yield f"{line}\n"
                    if answer is not None:
                        conversation_id = service.record_turn(
                            db,
                            user_id=identity.user_id,
                            thread_id=request.thread_id,
                            user_message=request.user_message,
                            assistant_message=answer.get("final_output") or "",
                            meta=_turn_meta(answer),
                        )
                        # `persistence` rides along with the id so the client
                        # can tell "not saved because you were never signed
                        # in" from "not saved because your session expired"
                        # without decoding its own token.
                        tail = json.dumps(
                            {
                                "conversation_id": conversation_id,
                                "persistence": service.persistence_status(
                                    identity.user_id,
                                    identity.token_present,
                                    conversation_id,
                                ),
                            },
                            ensure_ascii=False,
                        )
                        yield f"event: saved\ndata: {tail}\n\n"
        except (httpx.HTTPError, httpx.StreamError) as exc:
            # Akış zaten 200 döndü; hata ancak gövdenin içinde bildirilebilir.
            # İstemci bunu görünce tamponlu `/chat` uç noktasına düşer.
            log.warning("streaming chat failed: %s", exc)
            body = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {body}\n\n"

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


# ---------------------------------------------------------------------------
# Conversations
#
# The counterpart to the writes above. Rows were being written since the `ai`
# schema landed but nothing could read them back, so the session list in the
# UI came entirely from localStorage -- which meant history died with the
# browser profile and could be read by the next person to use the machine.
#
# These use `get_current_user_id`, not the optional resolver. An anonymous
# caller has nothing stored, and answering with an empty list would make
# "your session expired" indistinguishable from "you have no conversations".
# ---------------------------------------------------------------------------
@router.get("/conversations", response_model=ConversationListOut)
def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ConversationListOut:
    rows, total = service.list_conversations(db, user_id, limit, offset)
    return ConversationListOut(
        items=[ConversationSummary.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{thread_id}", response_model=ConversationDetailOut)
def get_conversation(
    thread_id: str,
    limit: int = Query(200, ge=1, le=500),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ConversationDetailOut:
    """One conversation with its transcript, oldest message first.

    `limit` is a UI read and unrelated to the model's context budget: the
    screen shows the whole conversation, the model sees `trim_history`.
    """
    conversation = service.get_conversation(db, user_id, thread_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı.")

    rows, has_more = service.list_messages(db, conversation.id, limit)
    context_topic = next(
        (
            row.meta.get("context_topic")
            for row in reversed(rows)
            if row.role == "assistant" and (row.meta or {}).get("context_topic")
        ),
        None,
    )
    return ConversationDetailOut(
        **ConversationSummary.model_validate(conversation).model_dump(),
        messages=[
            MessageOut(
                id=row.id,
                role=row.role,
                content=row.content,
                created_at=row.created_at,
                disclosures=(row.meta or {}).get("disclosures") or [],
            )
            for row in rows
        ],
        has_more=has_more,
        context_topic=context_topic,
    )


@router.patch("/conversations/{thread_id}", response_model=ConversationSummary)
def rename_conversation(
    thread_id: str,
    payload: RenameConversationRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ConversationSummary:
    conversation = service.rename_conversation(db, user_id, thread_id, payload.title)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı.")
    return ConversationSummary.model_validate(conversation)


@router.delete("/conversations/{thread_id}", response_model=DeletedConversationOut)
def delete_conversation(
    thread_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> DeletedConversationOut:
    """Hard delete; the messages cascade.

    Returns a body rather than 204 because the frontend's `request()` calls
    `response.json()` unconditionally, so an empty response would throw in the
    client rather than resolve.
    """
    if not service.delete_conversation(db, user_id, thread_id):
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı.")
    return DeletedConversationOut(thread_id=thread_id)


# ---------------------------------------------------------------------------
# Yüklenen belgeler
# ---------------------------------------------------------------------------
#
# Sohbete eklenen dosya: metni çıkarılır, KULLANICI SAHİPLİĞİYLE gömülür ve
# burada kaydedilir. Gömülü kopya yalnızca yükleyenin aramalarında çıkar
# (vector-migrations 0004); paylaşılan haber derlemine karışmaz.


@router.post(
    "/documents",
    response_model=ChatDocumentOut,
    status_code=201,
    summary="Sohbete belge yükle",
)
def upload_document(
    file: UploadFile = File(...),
    thread_id: Optional[str] = Form(None),
    identity: ChatIdentity = Depends(resolve_chat_identity),
    db: Session = Depends(get_db),
):
    """PDF, Excel, CSV, PowerPoint ya da düz metin.

    Anonim yükleme YOK. Belgenin bir sahibi olmadan gömülmesi, onu paylaşılan
    derleme koymak demek; sahibi olmayan bir belge de silinemez.
    """
    if not identity.user_id:
        raise HTTPException(
            status_code=401,
            detail="Belge yüklemek için oturum açmanız gerekiyor.",
        )

    record = document_service.store(
        db,
        user_id=identity.user_id,
        thread_id=thread_id,
        filename=file.filename or "belge",
        payload=file.file.read(),
    )
    return document_service.as_dict(record)


@router.get(
    "/documents",
    response_model=ChatDocumentListOut,
    summary="Yüklediğim belgeler",
)
def list_documents(
    identity: ChatIdentity = Depends(resolve_chat_identity),
    db: Session = Depends(get_db),
):
    """Yalnızca çağıranın kendi belgeleri.

    Anonim çağıran boş liste alır, 401 değil: yüklediği bir şey yoktur ve
    "belgeniz yok" doğru cevaptır.
    """
    records = (
        document_service.listing(db, identity.user_id) if identity.user_id else []
    )
    return {
        "documents": [document_service.as_dict(record) for record in records],
        "accepted": sorted(documents.SUPPORTED),
        "max_bytes": documents.MAX_UPLOAD_BYTES,
    }


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    summary="Yüklediğim bir belgeyi sil",
)
def delete_document(
    document_id: str,
    identity: ChatIdentity = Depends(resolve_chat_identity),
    db: Session = Depends(get_db),
):
    """Belgeyi hem listeden hem aramadan kaldırır.

    Yalnızca birini silmek, kullanıcının sildiğini sandığı ve hâlâ okunan
    bir dosya bırakırdı.
    """
    if not identity.user_id:
        raise HTTPException(status_code=401, detail="Oturum açmanız gerekiyor.")
    document_service.delete(db, identity.user_id, document_id)
