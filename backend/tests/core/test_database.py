"""Unit tests for app/core/database.py — özellikle get_db()'nin generator
davranışı: başarı yolunda ve tüketici erken kapattığında `db.close()`'un
her koşulda çağrıldığının (finally garantisi) doğrulanması."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.database import (
    MAX_OVERFLOW,
    POOL_SIZE,
    engine_options,
    get_db,
)


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


class TestEngineOptions:
    """Engine argümanları veritabanına göre seçiliyor.

    `def` uç noktalar Starlette'in iş parçacığı havuzunda çalıştığı için
    bağlantı havuzunun o havuza göre boyutlanması gerekiyor; ayrıca SQLite
    bu argümanların hiçbirini kabul etmiyor.
    """

    def test_postgres_gets_a_pool_sized_for_the_thread_pool(self):
        """Havuz iş parçacığı havuzundan küçük kalırsa, olay döngüsünden
        kurtardığımız eşzamanlılık bağlantı beklerken geri kaybedilir."""
        options = engine_options("postgresql+psycopg2://u:p@db/moneyfast")

        assert options["pool_size"] == POOL_SIZE
        assert options["max_overflow"] == MAX_OVERFLOW

    def test_postgres_pings_before_handing_out_a_connection(self):
        """Boşta kalmış bir bağlantı üzerinden gelen ilk istek
        `OperationalError` ile düşüyordu — "bazen hata veriyor, yeniden
        deneyince geliyor" davranışının veriyle ilgisi olmayan yarısı."""
        options = engine_options("postgresql+psycopg2://u:p@db/moneyfast")

        assert options["pool_pre_ping"] is True
        assert options["pool_recycle"] > 0

    def test_sqlite_gets_none_of_them(self):
        """Bellek içi SQLite `SingletonThreadPool` kullanır ve
        `max_overflow` KABUL ETMEZ: koşulsuz verilseydi test paketi import
        anında `TypeError` ile ölürdü (bkz. tests/conftest.py)."""
        assert engine_options("sqlite+pysqlite:///:memory:") == {}

    def test_a_sqlite_file_url_is_also_sqlite(self):
        assert engine_options("sqlite:///./moneyfast.db") == {}
