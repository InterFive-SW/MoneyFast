import asyncio
import uuid
import time
from fastapi import APIRouter
from .schemas import ChatRequest, ChatResponse, WidgetData

router = APIRouter(tags=["AI Assistant"])

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest):
    """
    Kullanıcıdan gelen mesajı LangGraph orkestratörüne iletir.
    Durumsuz (stateless) çalışır, gelen JSON kontratlarını ayrıştırarak widget olarak döner.
    """
    import os
    import re
    import json
    import httpx

    orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://localhost:8080")
    
    # 1. Orkestratöre HTTP İsteği
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{orchestrator_url}/chat",
                json={
                    "user_message": request.text,
                    "user_id": "anonymous",
                    "thread_id": "default",
                    "conversation_history": request.history if request.history else []
                },
                timeout=45.0
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        # Orkestratör bağlantı hatası durumunda fail-safe
        return ChatResponse(
            id=str(uuid.uuid4()),
            text="Şu anda AI asistanına bağlanılamıyor. Lütfen daha sonra tekrar deneyin.",
            thoughts=[f"Hata: {str(e)}"]
        )

    final_output = data.get("final_output", "")
    target_agent = data.get("target_agent")
    
    # 2. Markdown Temizleyici (Sanitizer)
    def sanitize_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return text.strip()

    sanitized_output = sanitize_json(final_output)
    
    widget = None
    response_text = final_output
    
    # 3. JSON Kontratını Ayrıştırma (Parsing)
    if sanitized_output.startswith("{") and sanitized_output.endswith("}"):
        try:
            parsed_json = json.loads(sanitized_output)
            # Eğer bir widget ise
            if "widget_type" in parsed_json:
                widget_type = parsed_json.pop("widget_type")
                widget = WidgetData(
                    type=widget_type,
                    payload=parsed_json
                )
                # JSON olduğunda doğal dil mesajını temizle
                response_text = ""
        except json.JSONDecodeError:
            # Geçerli bir JSON değilse normal metin olarak kalır
            pass

    return ChatResponse(
        id=str(uuid.uuid4()),
        text=response_text,
        context_topic=target_agent,
        widget=widget,
        thoughts=["İstek LangGraph'a iletildi.", f"Hedef ajan: {target_agent}"]
    )


@router.get(
    "/health",
    summary="Ai_assistant modülü sağlık durumu"
)
async def health_check():
    """
    Ai_assistant modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "ai_assistant"}
