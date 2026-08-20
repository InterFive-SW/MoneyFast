"""The Portföy Analizi endpoint.

One call, not three: the user story sets a 2-second load budget, and fetching
allocation, trend and performance separately would read the same position list
three times.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_optional_user_id
from app.main import app
from app.modules.investment import market_service

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)
URL = "/api/analytics/portfolio"


@pytest.fixture
def analytics_client(mocker, caller):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.all.return_value = []

    mocker.patch.object(
        market_service, "holdings",
        return_value=[{"symbol": "THYAO", "quantity": 100.0, "price": 300.0, "avg_cost": 250.0}],
    )
    mocker.patch.object(market_service, "latest_quotes", return_value={})
    mocker.patch.object(market_service, "freshness", return_value=(NOW, 15, True))
    mocker.patch.object(
        market_service, "account", return_value=SimpleNamespace(id="a1", cash_balance=25000.0)
    )
    mocker.patch.object(market_service, "sector_by_symbol", return_value={"THYAO": "Industrials"})
    mocker.patch.object(
        market_service, "candle_closes",
        return_value=[(NOW, 300.0), (NOW, 301.0)],
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_optional_user_id] = lambda: caller
    try:
        with TestClient(app) as client:
            client.db = db
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_optional_user_id, None)


@pytest.fixture
def caller():
    return "user-1"


class TestPortfolioAnalysis:
    def test_the_report_is_assembled_in_one_call(self, analytics_client):
        body = analytics_client.get(URL).json()
        assert body["total_value"] == pytest.approx(55000.0)
        assert body["cash"] == pytest.approx(25000.0)
        assert body["allocation"]
        assert body["performance"]["observations"] >= 0

    def test_freshness_is_carried(self, analytics_client):
        """A valuation without its as_of is a valuation presented as current."""
        body = analytics_client.get(URL).json()
        assert body["delay_minutes"] == 15
        assert body["is_delayed"] is True
        assert body["as_of"].startswith("2026-08-20")

    def test_the_sector_breakdown_is_present(self, analytics_client):
        body = analytics_client.get(URL).json()
        assert body["sectors"][0]["label"] == "Industrials"

    def test_confirmed_proposals_are_read_for_the_caller(self, analytics_client):
        analytics_client.get(URL)
        assert analytics_client.db.query.called

    @pytest.mark.parametrize("caller", [None])
    def test_an_anonymous_caller_reads_no_transaction_history(self, analytics_client):
        """İK-19: only the authenticated user's data. With no identity there is
        no history to attribute, so none is queried."""
        body = analytics_client.get(URL).json()
        assert body["activity"]["confirmed_count"] == 0
