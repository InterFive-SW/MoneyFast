"""Backend unit test suite — ortak fixture'lar.

Üç bölüm halinde:
  1. Import-time ortam kurulumu (herhangi bir `app.*` importundan ÖNCE çalışmalı)
  2. İzolasyon: gerçek ağ erişimini engelleyen autouse fixture
  3. Paylaşılan fixture'lar: FastAPI TestClient, mock DB session, yavaş yan etkileri
     (asyncio.sleep, bcrypt) hızlandıran yardımcılar

Bu suite tamamen izole çalışır: gerçek bir Postgres'e ihtiyaç duymaz (DATABASE_URL
in-memory SQLite'a ayarlanır, `create_engine` lazy olduğu için hiç bağlantı açılmaz)
ve gerçek bir ağ isteği atmaz (`block_network` autouse fixture'ı garanti eder).
"""

from __future__ import annotations

import os
import socket
from typing import Any, Callable
from unittest.mock import MagicMock

# --------------------------------------------------------------------------
# 1. Ortam kurulumu — herhangi bir `app.*` modülü import edilmeden önce.
#
# app/core/config.py:Settings() modül seviyesinde instantiate ediliyor ve
# DATABASE_URL + SECRET_KEY zorunlu (default yok). Bu satırlar burada,
# dosyanın en üstünde olmazsa `import app.main` ValidationError ile patlar.
# --------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
# ACCESS_TOKEN_EXPIRE_MINUTES ve ALGORITHM'in default'ları zaten var, dokunmuyoruz.
# AI_ORCHESTRATOR_URL'in de default'u var; testlerde httpx her zaman mock'landığı
# için gerçek bir URL olması önemli değil.

import pytest  # noqa: E402  (env kurulumundan sonra import edilmeli)
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


# --------------------------------------------------------------------------
# 2. İzolasyon — gerçek soket açan bir test sessizce ağa çıkmak yerine
#    yüksek sesle patlamalı. AI ekibinin mcp-server/tests/conftest.py'sindeki
#    aynı fikir; backend'de ekstra değeri var: ai_orchestrator'ın httpx
#    çağrıları mock'lanmazsa burada yakalanır.
# --------------------------------------------------------------------------
class NetworkAccessAttempted(RuntimeError):
    """Bir unit test gerçek bir soket açmaya çalıştığında fırlatılır."""


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise NetworkAccessAttempted(
            "Unit test gerçek ağ erişimi denedi. HTTP istemcisini mock'la "
            "(örn. mocker.patch('httpx.AsyncClient', ...))."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


# --------------------------------------------------------------------------
# 3. Paylaşılan fixture'lar
# --------------------------------------------------------------------------
@pytest.fixture
def mock_db() -> MagicMock:
    """`Session` şeklinde sahte bir DB — service.py testleri için.

    `db.query(User).filter(...).first()` zincirini desteklemesi için
    `query` metodunun döndürdüğü mock'u ayrıca yapılandırmak testin kendi
    işi (bkz. tests/modules/auth/test_service.py).
    """
    return MagicMock(spec=Session)


@pytest.fixture
def client() -> TestClient:
    """`get_db` override edilmiş bir TestClient.

    Override, gerçek `SessionLocal()` açılmasını engeller — override
    edilmeseydi auth router'ın `Depends(get_db)` alan endpoint'leri gerçek
    (var olmayan) bir Postgres'e bağlanmaya çalışırdı.
    """

    def _override_get_db():
        yield MagicMock(spec=Session)

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session")
def password_hash_factory() -> Callable[[str], str]:
    """Bcrypt hash'lemesi ~250ms sürüyor; testler arası sonucu yeniden
    kullanmak için session-scoped bir factory (fonksiyonu memoize eder)."""
    from app.core.security import hash_password

    cache: dict[str, str] = {}

    def _hash(password: str) -> str:
        if password not in cache:
            cache[password] = hash_password(password)
        return cache[password]

    return _hash
