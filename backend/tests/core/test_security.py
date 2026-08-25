"""Unit tests for app/core/security.py — hash/verify, JWT üretimi ve çözümü."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_produces_a_bcrypt_hash_different_from_plaintext(
    password_hash_factory,
):
    hashed = password_hash_factory("Password123")
    assert hashed != "Password123"
    assert hashed.startswith("$2b$")


def test_verify_password_accepts_correct_plaintext(password_hash_factory):
    hashed = password_hash_factory("Password123")
    assert verify_password("Password123", hashed) is True


def test_verify_password_rejects_incorrect_plaintext(password_hash_factory):
    hashed = password_hash_factory("Password123")
    assert verify_password("WrongPassword1", hashed) is False


def test_create_access_token_uses_default_expiry_when_none_given():
    token = create_access_token(data={"sub": "12345678901"})
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "12345678901"
    assert "exp" in payload


def test_create_access_token_honors_explicit_expires_delta():
    token = create_access_token(data={"sub": "u1"}, expires_delta=timedelta(minutes=1))
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "u1"


def test_create_access_token_does_not_mutate_caller_supplied_dict():
    original = {"sub": "u1"}
    create_access_token(data=original)
    assert original == {"sub": "u1"}  # `.copy()` kullanılıyor, "exp" eklenmemeli


def test_decode_access_token_returns_payload_for_valid_token():
    token = create_access_token(data={"sub": "u2"})
    payload = decode_access_token(token)
    assert payload["sub"] == "u2"


def test_decode_access_token_returns_empty_dict_for_garbage_token():
    assert decode_access_token("not-a-real-jwt") == {}


def test_decode_access_token_returns_empty_dict_for_expired_token():
    expired_token = create_access_token(
        data={"sub": "u3"}, expires_delta=timedelta(minutes=-1)
    )
    assert decode_access_token(expired_token) == {}


def test_decode_access_token_returns_empty_dict_for_wrong_signature():
    token = jwt.encode(
        {"sub": "u4"}, "a-completely-different-secret", algorithm=settings.ALGORITHM
    )
    assert decode_access_token(token) == {}


class TestTokenKinds:
    """Access and refresh tokens are not interchangeable.

    A refresh token lives for days. If it were accepted wherever an access
    token is, one leaked token would be as good as the password for a week.
    """

    def test_access_token_is_typed(self):
        payload = decode_access_token(create_access_token(data={"sub": "u5"}))
        assert payload["typ"] == ACCESS_TOKEN_TYPE

    def test_refresh_token_is_typed(self):
        payload = decode_access_token(create_refresh_token(data={"sub": "u6"}))
        assert payload["typ"] == REFRESH_TOKEN_TYPE

    def test_refresh_token_outlives_the_access_token(self):
        access = decode_access_token(create_access_token(data={"sub": "u7"}))
        refresh = decode_access_token(create_refresh_token(data={"sub": "u7"}))
        assert refresh["exp"] > access["exp"]

    def test_refresh_expiry_is_honoured(self):
        expired = create_refresh_token(
            data={"sub": "u8"}, expires_delta=timedelta(minutes=-1)
        )
        assert decode_access_token(expired) == {}
