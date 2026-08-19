"""Unit tests for app/modules/auth/models.py — `id` ve `created_at`
kolonlarındaki `default=lambda: ...` değerlerinin gerçekten uygulandığını
doğrular. Bu default'lar SQLAlchemy tarafından yalnızca INSERT/flush
sırasında hesaplanır; bu yüzden gerçek (izole, in-memory) bir SQLite
bağlantısı kullanıyoruz — `mock_db` (MagicMock) burada işe yaramaz çünkü
gerçek bir flush çalıştırmaz.
"""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.modules.auth.models import User


def _fresh_sqlite_session():
    """Her test için tamamen izole, tek kullanımlık bir in-memory SQLite DB."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_user_id_gets_a_uuid_default_when_not_provided():
    session = _fresh_sqlite_session()
    user = User(
        tc_no="12345678901",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone_number="+905551112233",
        hashed_password="hashed",
    )

    session.add(user)
    session.flush()

    assert user.id is not None
    uuid.UUID(user.id)  # geçerli bir UUID string'i olmalı, aksi halde raise eder
    session.close()


def test_user_created_at_gets_a_utc_timestamp_default_when_not_provided():
    session = _fresh_sqlite_session()
    user = User(
        tc_no="10987654321",
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
        phone_number="+905551112244",
        hashed_password="hashed",
    )

    session.add(user)
    session.flush()

    assert user.created_at is not None
    session.close()


def test_user_is_active_defaults_to_true():
    session = _fresh_sqlite_session()
    user = User(
        tc_no="11122233344",
        first_name="Alan",
        last_name="Turing",
        email="alan@example.com",
        phone_number="+905551112255",
        hashed_password="hashed",
    )

    session.add(user)
    session.flush()

    assert user.is_active is True
    session.close()
