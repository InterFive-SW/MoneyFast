import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Notification(Base):
    """
    Kullanıcıya özel uygulama içi bildirimlerin (in-app notifications) kalıcı depolama modelidir.
    REST tabanlı polling mimarisi üzerinden istemciye (client) periyodik olarak sunulur.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Kullanıcıyla ilişkilendirilen foreign key (Hızlı sorgulama için indekslenmiştir)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Bildirimin ana başlığı ve detaylı içeriği
    title = Column(String(100), nullable=False)
    description = Column(String(255), nullable=False)
    
    # Bildirimin önem derecesi veya türü (SUCCESS, INFO, WARNING, ERROR)
    type = Column(String(20), nullable=False, default="INFO")
    
    # Kullanıcı bildirime tıkladığında yönlendirilecek hedef URL (Opsiyonel)
    link_url = Column(String(255), nullable=True)
    
    # Kullanıcının bildirimi okuyup okumadığını takip eden bayrak (flag)
    is_read = Column(Boolean, nullable=False, default=False)
    
    # Kaydın veritabanına eklendiği UTC zaman damgası
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

