"""
Kimlik Doğrulama Şemaları

Kimlik doğrulama ve kullanıcı yönetimi için Veri Transfer Nesneleri (DTO'lar).
Pydantic V2 kullanarak girdi verilerini sıkı bir şekilde doğrular.
"""

from typing import Optional, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator


class UserBase(BaseModel):
    """Birden fazla kullanıcı şeması arasında paylaşılan temel alanlar."""

    first_name: str = Field(..., description="Kullanıcının adı")
    last_name: str = Field(..., description="Kullanıcının soyadı")


class RegisterRequest(UserBase):
    """Sıkı doğrulamalarla yeni bir kullanıcı kaydetmek için şema."""

    tc_no: str = Field(
        ..., pattern=r"^\d{11}$", description="11 haneli T.C. Kimlik Numarası"
    )
    email: EmailStr = Field(..., description="Geçerli e-posta adresi")
    phone_number: str = Field(
        ...,
        pattern=r"^\+?[0-9]{10,15}$",
        description="İsteğe bağlı ülke koduyla telefon numarası",
    )
    password: str = Field(
        ...,
        min_length=8,
        description="Şifre en az 8 karakter olmalı, 1 büyük harf ve 1 rakam içermelidir",
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(char.isupper() for char in v):
            raise ValueError("Şifre en az bir büyük harf içermelidir")
        if not any(char.isdigit() for char in v):
            raise ValueError("Şifre en az bir rakam içermelidir")
        return v


class LoginRequest(BaseModel):
    """Kullanıcı giriş bilgileri için şema."""

    tc_no: str = Field(
        ..., pattern=r"^\d{11}$", description="11 haneli T.C. Kimlik Numarası"
    )
    password: str = Field(..., description="Kullanıcının şifresi")


class UserResponse(UserBase):
    """Kullanıcı verilerini güvenli bir şekilde (şifresiz) döndürmek için şema."""

    id: str
    tc_no: str
    email: EmailStr
    phone_number: str
    is_active: bool
    
    # JSONB mimarisine uygun olarak, kategori ve kanala göre bildirim tercihlerini tutar.
    notification_preferences: Dict[str, Dict[str, bool]] = Field(..., description="Kullanıcının detaylı bildirim tercihleri matrisi")

    # Güvenlik Merkezi → İşlem Onay Limiti slider'ından ayarlanan eşik değeri.
    # Bu değerin üzerindeki para transferlerinde ek doğrulama (SMS/2FA) istenir.
    transaction_limit: int = Field(..., description="Ek doğrulama gerektiren transfer eşiği (₺)")

    # Görünüm & Format sekmesinden ayarlanan kullanıcı tercihleri (dil, para
    # birimi, varsayılan dashboard şablonu). JSONB olarak saklandığı için
    # şema genişletmeye gerek kalmadan yeni tercih anahtarları eklenebilir.
    user_preferences: Dict[str, str] = Field(..., description="Kullanıcıya özgü görünüm ve bölgesel tercihler")
    
    created_at: datetime

    #: Ekranlarda gösterilen müşteri numarası. Saklanmıyor, kullanıcı
    #: kimliğinden türetiliyor -- hesap numaralarının ve IBAN'ların zaten
    #: üretildiği yöntemin aynısı. Arayüzde bir dönem HERKES için aynı sabit
    #: (`84938201`) yazılıydı, yani müşteriyi ayırt etmeyen bir "müşteri no".
    customer_no: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """JWT token yanıtı için şema."""

    access_token: str
    token_type: str = "bearer"
    #: Kısa ömürlü access token'ı yenilemek için kullanılır. Yalnızca
    #: `/auth/refresh` kabul eder. Optional: yenileme uç noktası yalnızca
    #: access token döndürür, yeni bir refresh token üretmez.
    refresh_token: Optional[str] = None


class RefreshRequest(BaseModel):
    """`/auth/refresh` gövdesi."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """Şifre sıfırlama isteği için şema.
    GÜVENLİK: Hem T.C. Kimlik hem de e-posta adresinin eşleşmesi gerekir.
    """
    tc_no: str = Field(..., pattern=r"^\d{11}$")
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Şifreyi sıfırlamak için şema."""
    token: str = Field(..., description="E-postadaki JWT sıfırlama token'ı")
    new_password: str = Field(
        ...,
        min_length=8,
        description="Şifre en az 8 karakter olmalı, 1 büyük harf ve 1 rakam içermelidir",
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(char.isupper() for char in v):
            raise ValueError("Şifre en az bir büyük harf içermelidir")
        if not any(char.isdigit() for char in v):
            raise ValueError("Şifre en az bir rakam içermelidir")
        return v


class VerifyEmailRequest(BaseModel):
    """E-posta doğrulama için şema."""
    token: str = Field(..., description="E-postadaki JWT doğrulama token'ı")


class UserUpdateRequest(BaseModel):
    """Kullanıcı profil güncelleme isteği için şema.
    GÜVENLİK: TC ve Ad-Soyad gibi kritik bilgiler değiştirilemez. 
    Yalnızca iletişim ve tercih ayarları güncellenebilir.
    """
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, pattern=r"^\+?[0-9]{10,15}$")
    
    # JSONB yapısına uygun opsiyonel bildirim tercihleri
    notification_preferences: Optional[Dict[str, Dict[str, bool]]] = Field(None, description="Opsiyonel olarak güncellenecek detaylı bildirim matrisi")

    # Güvenlik → İşlem Onay Limiti (₺). Pydantic seviyesinde 0 ile 250.000₺
    # arasına kısıtlanmıştır; frontend slider aynı aralığı yansıtır.
    transaction_limit: Optional[int] = Field(None, ge=0, le=250000, description="Ek doğrulama gerektiren transfer eşiği (₺)")

    # Görünüm & Format tercihleri. Anahtar-değer çiftleri olarak
    # saklandığı için frontend hangi anahtarları gönderirse backend
    # doğrudan JSONB kolonuna yazar.
    user_preferences: Optional[Dict[str, str]] = Field(None, description="Kullanıcıya özgü görünüm ve bölgesel tercihler")


class ChangePasswordRequest(BaseModel):
    """Aktif oturumda şifre değiştirme isteği için şema.
    GÜVENLİK: Hesabın ele geçirilmesini önlemek amacıyla mevcut şifrenin doğrulanması zorunludur.
    """
    current_password: str = Field(..., description="Kullanıcının mevcut şifresi")
    new_password: str = Field(
        ...,
        min_length=8,
        description="Yeni şifre en az 8 karakter olmalı, 1 büyük harf ve 1 rakam içermelidir",
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(char.isupper() for char in v):
            raise ValueError("Şifre en az bir büyük harf içermelidir")
        if not any(char.isdigit() for char in v):
            raise ValueError("Şifre en az bir rakam içermelidir")
        return v


class DeleteAccountRequest(BaseModel):
    """Hesap kapatma (soft delete) isteği için şema.

    KVKK/GDPR UYUM NOTU:
    Hesap kapatma geri dönüşü olmayan (irreversible) kritik bir aksiyondur.
    Frontend'de çok adımlı onay modalı ("KAPAT" yazma zorunluluğu) ile
    korunduğu için bu şemada yalnızca opsiyonel ayrılma nedeni istenir.
    Gerçek silme yerine soft-delete (is_active=False) uygulanır; yasal
    saklama yükümlülükleri gereği kullanıcı kaydı veritabanında kalır.
    """
    reason: Optional[str] = Field(None, max_length=500, description="Kullanıcının opsiyonel ayrılma nedeni")

