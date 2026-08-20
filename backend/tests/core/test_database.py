"""Unit tests for app/core/database.py — özellikle get_db()'nin generator
davranışı: başarı yolunda ve tüketici erken kapattığında `db.close()`'un
her koşulda çağrıldığının (finally garantisi) doğrulanması."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.database import get_db


def test_get_db_yields_session_and_closes_it_after_exhaustion():
    fake_session = MagicMock()
    with patch("app.core.database.SessionLocal", return_value=fake_session):
        gen = get_db()
        db = next(gen)

        assert db is fake_session
        fake_session.close.assert_not_called()

        with pytest.raises(StopIteration):
            next(gen)

    fake_session.close.assert_called_once()


def test_get_db_closes_session_when_generator_is_closed_early():
    """FastAPI, bir istek erken sonlanırsa dependency generator'ı
    `gen.close()` ile de sonlandırabilir; finally bloğunun bu durumda da
    çalıştığını doğruluyoruz."""
    fake_session = MagicMock()
    with patch("app.core.database.SessionLocal", return_value=fake_session):
        gen = get_db()
        next(gen)
        gen.close()

    fake_session.close.assert_called_once()
