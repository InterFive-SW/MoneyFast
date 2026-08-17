from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class ChartDataPoint(BaseModel):
    name: str
    value: float

class ChartWidgetPayload(BaseModel):
    title: str
    data: List[ChartDataPoint]
    color: Optional[str] = None

class ActionWidgetPayload(BaseModel):
    message: str
    confirmLabel: str
    cancelLabel: str
    actionId: str

class WidgetData(BaseModel):
    type: str
    payload: Dict[str, Any]

class ChatRequest(BaseModel):
    text: str
    context: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = Field(default_factory=list)

class ChatResponse(BaseModel):
    id: str
    text: str
    context_topic: Optional[str] = None
    widget: Optional[WidgetData] = None
    thoughts: List[str] = Field(default_factory=list)
