"""Unit tests for app/core/config.py.

`settings` singleton modül import anında oluşuyor; conftest.py bu import
gerçekleşmeden ÖNCE DATABASE_URL ve SECRET_KEY'i ayarlıyor (bkz.
tests/conftest.py bölüm 1). Burada hem o singleton'ın geçerliliğini, hem de
`Settings` sınıfının default/zorunlu-alan davranışını ayrıca doğruluyoruz.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings as settings_singleton


def test_settings_singleton_uses_conftest_environment():
    assert settings_singleton.DATABASE_URL == "sqlite+pysqlite:///:memory:"
    assert settings_singleton.SECRET_KEY == "test-secret-key"


def test_default_algorithm_expiry_and_orchestrator_url_are_applied():
    s = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        SECRET_KEY="another-secret",
    )
    assert s.ALGORITHM == "HS256"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert s.AI_ORCHESTRATOR_URL == "http://agents:8080"


def test_explicit_values_override_defaults():
    s = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        SECRET_KEY="another-secret",
        ALGORITHM="HS512",
        ACCESS_TOKEN_EXPIRE_MINUTES=5,
        AI_ORCHESTRATOR_URL="http://custom-orchestrator:9999",
    )
    assert s.ALGORITHM == "HS512"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 5
    assert s.AI_ORCHESTRATOR_URL == "http://custom-orchestrator:9999"


def test_missing_database_url_raises_validation_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY="only-secret")


def test_missing_secret_key_raises_validation_error(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="sqlite+pysqlite:///:memory:")
