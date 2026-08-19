"""Unit tests for app/modules/auth/service.py.

Bu modül şu an `auth/router.py` tarafından ÇAĞRILMIYOR (DB entegrasyonunu
bekleyen hazır kod) ama gerçek DB sorguları içerdiği için ayrıca ve
doğrudan test ediliyor. `mock_db` (conftest.py) `Session` şeklinde bir
MagicMock; `db.query(...).filter(...).first()` zincirinin dönüş değeri her
testte senaryoya göre ayarlanıyor.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.auth.schemas import LoginRequest, RegisterRequest
from app.modules.auth.service import authenticate_user, create_user

VALID_REGISTER_PAYLOAD = dict(
    first_name="Ada",
    last_name="Lovelace",
    tc_no="12345678901",
    email="ada@example.com",
    phone_number="+905551112233",
    password="Password123",
)


# --------------------------------------------------------------------------
# authenticate_user
# --------------------------------------------------------------------------
def test_authenticate_user_raises_401_when_user_not_found(mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    payload = LoginRequest(tc_no="12345678901", password="Password123")

    with pytest.raises(HTTPException) as exc_info:
        authenticate_user(payload, mock_db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "TC Kimlik No veya şifre hatalı"


def test_authenticate_user_raises_401_when_password_is_wrong(
    mock_db, password_hash_factory
):
    fake_user = SimpleNamespace(
        tc_no="12345678901", hashed_password=password_hash_factory("Password123")
    )
    mock_db.query.return_value.filter.return_value.first.return_value = fake_user
    payload = LoginRequest(tc_no="12345678901", password="WrongPassword1")

    with pytest.raises(HTTPException) as exc_info:
        authenticate_user(payload, mock_db)

    assert exc_info.value.status_code == 401


def test_authenticate_user_returns_token_on_success(mock_db, password_hash_factory):
    fake_user = SimpleNamespace(
        tc_no="12345678901", hashed_password=password_hash_factory("Password123")
    )
    mock_db.query.return_value.filter.return_value.first.return_value = fake_user
    payload = LoginRequest(tc_no="12345678901", password="Password123")

    result = authenticate_user(payload, mock_db)

    assert result.token_type == "bearer"
    assert result.access_token


# --------------------------------------------------------------------------
# create_user
# --------------------------------------------------------------------------
def test_create_user_raises_409_when_tc_no_already_registered(mock_db):
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id="existing-user")
    ]
    payload = RegisterRequest(**VALID_REGISTER_PAYLOAD)

    with pytest.raises(HTTPException) as exc_info:
        create_user(payload, mock_db)

    assert exc_info.value.status_code == 409
    assert "TC Kimlik No" in exc_info.value.detail


def test_create_user_raises_409_when_email_already_registered(mock_db):
    # İlk çağrı (tc_no kontrolü) None döner, ikinci çağrı (email kontrolü)
    # mevcut bir kullanıcı döner — service.py'deki sıralı iki sorguyla eşleşir.
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,
        SimpleNamespace(id="existing-user"),
    ]
    payload = RegisterRequest(**VALID_REGISTER_PAYLOAD)

    with pytest.raises(HTTPException) as exc_info:
        create_user(payload, mock_db)

    assert exc_info.value.status_code == 409
    assert "E-posta" in exc_info.value.detail


def test_create_user_persists_and_returns_user_response_on_success(mock_db):
    mock_db.query.return_value.filter.return_value.first.side_effect = [None, None]

    def _simulate_refresh(user):
        """Gerçek bir `Session.refresh()`, sunucu tarafında (INSERT sırasında)
        üretilen default'ları (id, created_at, is_active) nesneye geri
        yükler. `mock_db` gerçek bir bağlantıya sahip olmadığı için o INSERT
        hiç çalışmaz; bu davranışı burada elle simüle ediyoruz — aksi halde
        `user.id` None kalır ve UserResponse doğrulaması başarısız olur."""
        user.id = str(uuid.uuid4())
        user.is_active = True
        user.created_at = datetime.now(timezone.utc)

    mock_db.refresh.side_effect = _simulate_refresh
    payload = RegisterRequest(**VALID_REGISTER_PAYLOAD)

    result = create_user(payload, mock_db)

    assert result.tc_no == "12345678901"
    assert result.email == "ada@example.com"
    assert result.is_active is True
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
