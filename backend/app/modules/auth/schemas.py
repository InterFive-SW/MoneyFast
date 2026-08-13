"""
Kimlik Doğrulama Şemaları

Kimlik doğrulama ve kullanıcı yönetimi için Veri Transfer Nesneleri (DTO'lar).
Pydantic V2 kullanarak girdi verilerini sıkı bir şekilde doğrular.
"""

from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator


class UserBase(BaseModel):
    """Birden fazla kullanıcı şeması arasında paylaşılan temel alanlar."""

    first_name: str = Field(..., description="Kullanıcının adı")
    last_name: str = Field(..., description="Kullanıcının soyadı")


class UserCreate(UserBase):
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


class UserLogin(BaseModel):
    """Kullanıcı giriş bilgileri için şema."""

    tc_no: str = Field(
        ..., pattern=r"^\d{11}$", description="11 haneli T.C. Kimlik Numarası"
    )
    password: str = Field(..., description="Kullanıcının şifresi")


class UserResponse(UserBase):
    """Kullanıcı verilerini güvenli bir şekilde (şifresiz) döndürmek için şema."""

    id: UUID
    tc_no: str
    email: EmailStr
    phone_number: str

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """JWT token yanıtı için şema."""

    access_token: str
    token_type: str
