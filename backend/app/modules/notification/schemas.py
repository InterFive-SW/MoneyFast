from datetime import datetime
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import List, Optional

class NotificationResponse(BaseModel):
    """
    İstemciye dönülecek tekil bildirim nesnesinin veri transfer objesidir (DTO).
    Güvenlik sebebiyle veritabanı modelinden sadece ilgili alanlar dışa aktarılır.
    """
    id: UUID
    title: str
    description: str
    type: str
    link_url: Optional[str] = None
    is_read: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class NotificationListResponse(BaseModel):
    """
    Sayfalandırılmış veya kısıtlı bildirim listesini ve okunmamış bildirim sayısını
    barındıran DTO nesnesidir. İstemcideki sayaç (badge) güncellemeleri için kullanılır.
    """
    unread_count: int
    items: List[NotificationResponse]
