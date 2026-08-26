"""Candle coverage: what the ingestor asks before back-filling history.

Daily bars were a 19:15 cron and nothing else, so a clone started in the
morning showed empty charts all day. The workaround was committing 7.5 MB of
candles as seed data — history for a series the ingestor produces on its own.

This endpoint replaces that. It answers "what do you already have", so the
ingestor can fetch only what is thin: a full universe on first boot, nothing
on a restart. The tests that matter are the two extremes — an instrument with
no bars must still be reported, and a covered one must be reported as covered.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.investment import market_service

NOW = datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc)


class _Query:
    """Enough of the SQLAlchemy query chain for the two grouped reads."""

    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def group_by(self, *_a, **_k):
        return self

    def all(self):
        return self._rows


class TestCoverageService:
    def _session(self, counts, latest, products):
        db = MagicMock(spec=Session)
        db.query.side_effect = [_Query(counts), _Query(latest), _Query(products)]
        return db

    def test_reports_bars_and_the_newest_date(self):
        product = SimpleNamespace(id="p-1", symbol="TEST-THYAO")
        db = self._session([("p-1", 260)], [("p-1", NOW)], [product])

        assert market_service.candle_coverage(db) == {
            "TEST-THYAO": {"bars": 260, "last": "2026-08-22"}
        }

    def test_an_instrument_with_no_bars_is_still_listed(self):
        """The whole point of the call. Omitting empty symbols would make
        "has nothing" indistinguishable from "not an instrument", and the
        backfill would skip exactly the rows it exists to fill."""
        product = SimpleNamespace(id="p-2", symbol="TEST-NEW")
        db = self._session([], [], [product])

        assert market_service.candle_coverage(db) == {
            "TEST-NEW": {"bars": 0, "last": None}
        }


class TestCoverageEndpoint:
    def test_is_guarded_by_the_service_token(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        assert client.get("/api/market/candles/coverage").status_code == 401

    def test_returns_the_service_answer(self, client, mocker, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        payload = {"TEST-THYAO": {"bars": 12, "last": "2026-08-22"}}
        mocker.patch.object(market_service, "candle_coverage", return_value=payload)
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            response = client.get(
                "/api/market/candles/coverage",
                headers={"Authorization": "Bearer secret"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        assert response.json() == payload
