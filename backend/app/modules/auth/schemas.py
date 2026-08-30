"""
Kimlik Doğrulama Şemaları

Kimlik doğrulama ve kullanıcı yönetimi için Veri Transfer Nesneleri (DTO'lar).
Pydantic V2 kullanarak girdi verilerini sıkı bir şekilde doğrular.
"""

from typing import Optional
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
