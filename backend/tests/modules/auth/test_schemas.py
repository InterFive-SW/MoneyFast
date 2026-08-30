"""Unit tests for app/modules/auth/schemas.py — özellikle şifre validator'ı."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

VALID_REGISTER_KWARGS = dict(
    first_name="Ada",
    last_name="Lovelace",
    tc_no="12345678901",
    email="ada@example.com",
    phone_number="+905551112233",
    password="Password123",
)


def test_register_request_accepts_a_valid_password():
    req = RegisterRequest(**VALID_REGISTER_KWARGS)
    assert req.password == "Password123"


def test_register_request_rejects_password_without_uppercase():
    kwargs = {**VALID_REGISTER_KWARGS, "password": "password123"}

    with pytest.raises(ValidationError, match="büyük harf"):
        RegisterRequest(**kwargs)


def test_register_request_rejects_password_without_digit():
    kwargs = {**VALID_REGISTER_KWARGS, "password": "Passwordonly"}

    with pytest.raises(ValidationError, match="rakam"):
        RegisterRequest(**kwargs)


def test_register_request_rejects_tc_no_with_wrong_length():
    kwargs = {**VALID_REGISTER_KWARGS, "tc_no": "123"}

    with pytest.raises(ValidationError):
        RegisterRequest(**kwargs)


def test_login_request_requires_11_digit_tc_no():
    with pytest.raises(ValidationError):
        LoginRequest(tc_no="abc", password="whatever")


def test_token_response_defaults_to_bearer_type():
    token = TokenResponse(access_token="abc.def.ghi")
    assert token.token_type == "bearer"


def test_user_response_builds_from_orm_style_attributes():
    fake_user = user_stub(
        id="u1",
        first_name="Ada",
        last_name="Lovelace",
        tc_no="12345678901",
        email="ada@example.com",
        phone_number="+905551112233",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    response = UserResponse.model_validate(fake_user)

    assert response.tc_no == "12345678901"


def user_stub(**overrides):
    """Bir kullanıcı satırı taklidi, ŞU ANKİ şemanın gerektirdiği alanlarla.

    Testler bunları tek tek `SimpleNamespace(tc_no=..., hashed_password=...)`
    diye kuruyordu. Şema büyüdükçe -- main `is_verified` ekledi, #42
    `notification_preferences` ve `transaction_limit` ekledi -- her ekleme aynı
    anda on iki testi düşürdü, hepsi aynı sebeple ve hepsi ayrı ayrı
    düzeltilmek zorunda kaldı.

    Tek yerde toplandı: bir sonraki sütun buraya eklenir, testlere değil.
    """
    from datetime import datetime, timezone
    import uuid as _uuid

    base = dict(
        id=str(_uuid.uuid4()),
        tc_no="12345678901",
        email="test@dummy.moneyfast.local",
        phone_number="+905550000000",
        first_name="Test",
        last_name="Kullanici",
        is_active=True,
        is_verified=True,
        notification_preferences={},
        transaction_limit=50000,
        user_preferences={},
        created_at=datetime.now(timezone.utc),
        hashed_password="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)
