from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    """What the frontend sends.

    There is deliberately no `user_id` field. "MCP Tools Interface Definitions
    v2.1" requires it to come from the authenticated session envelope and
    never from user-typed input; leaving it in the schema would mean anyone
    could read anyone's holdings by editing one JSON key. The router resolves
    it from the bearer token instead (see app/core/deps.py).
    """

    user_message: str = Field(..., min_length=1, max_length=4000)
    thread_id: str = "default"
    conversation_history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    final_output: str

    #: Zorunlu bildirimler, kelimesi kelimesine. `final_output`'a eklenmek
    #: yerine ayrı taşınıyor: metin aynı kalıyor, yalnızca yeri değişiyor —
    #: sohbet bunları balonun altında dipnot olarak gösteriyor. Her yanıtın
    #: sonuna yapıştırılan üç cümlelik kalıp, okuyucuya bildirimi gerçekten
    #: gerektiği yerde de atlatıyordu.
    disclosures: list[str] = Field(default_factory=list)
    primary_intent: Optional[str] = None
    target_agent: Optional[str] = None
    compliance_verdict: Optional[str] = None

    # Rendered by the chat UI. Built deterministically in the router from the
    # specialist's tool payload -- never asked of the model, because a model
    # that can emit widget JSON can emit a fabricated transaction proposal.
    widget: Optional[Dict[str, Any]] = None
    context_topic: Optional[str] = None
    conversation_id: Optional[str] = None
