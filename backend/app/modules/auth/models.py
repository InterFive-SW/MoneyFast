import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


from sqlalchemy.dialects.postgresql import JSONB

DEFAULT_NOTIFICATIONS = {
    "security": {"email": True, "push": True, "sms": True},
    "transactions": {"email": True, "push": True, "sms": False},
    "market": {"email": False, "push": True, "sms": False},
    "reports": {"email": True, "push": False, "sms": False},
    "marketing": {"email": False, "push": False, "sms": False},
}

DEFAULT_USER_PREFERENCES = {
    "currency": "TRY",
    "language": "tr",
    "default_template": "balanced",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tc_no: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # JSONB formatında bildirim tercihleri matrisi (Kategori -> Kanal -> Durum)
    notification_preferences: Mapped[dict] = mapped_column(
        JSONB, 
        default=lambda: DEFAULT_NOTIFICATIONS, 
        server_default='{}',
        nullable=False
    )

    # Kullanıcının ek doğrulama istemeden önce yapabileceği maksimum transfer
    # tutarı (₺). Bu eşik aşıldığında işlem SMS veya 2FA ile doğrulanır.
    # Varsayılan 50.000₺ olarak belirlenmiştir; Güvenlik Merkezi → İşlem
    # Onay Limiti slider'ından değiştirilebilir.
    transaction_limit: Mapped[int] = mapped_column(
        Integer,
        default=50000,
        server_default='50000',
        nullable=False
    )

    # Kullanıcıya özgü görünüm ve bölgesel tercihler (dil, para birimi,
    # varsayılan dashboard şablonu vb.). Esneklik için PostgreSQL JSONB
    # formatında saklanır — yeni bir tercih eklemek şema değişikliği
    # gerektirmez; sadece JSON anahtarı eklenir.
    user_preferences: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: DEFAULT_USER_PREFERENCES,
        server_default='{}',
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
