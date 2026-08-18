from typing import Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    user_message: str = Field(..., min_length=1, max_length=4000)
    user_id: str = "anonymous"
    thread_id: str = "default"
    conversation_history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    final_output: str
    primary_intent: Optional[str] = None
    target_agent: Optional[str] = None
    compliance_verdict: Optional[str] = None
