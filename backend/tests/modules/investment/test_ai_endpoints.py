"""AI-facing investment endpoints — MCP v2.1 contract tests.

The claim being tested: the MCP tool layer does not default a missing key, it
raises ContractViolationError. So these responses have to be complete, not
merely close, and the tests assert the exact key set.

Holdings now come from `investment.portfolio_positions` rather than a Python
fixture, so the doubles here mirror what `market_service.holdings()` returns —
quantity and cost basis from the database, price already joined from the
current quote.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.investment import ai_service, market_service

PORTFOLIO_URL = "/api/investment/portfolio/TEST-USER-1/positions"
STAGE_URL = "/api/investment/transactions/stage"

NOW = datetime.now(timezone.utc)

HOLDINGS = [
    {"symbol": "THYAO", "name": "Türk Hava Yolları", "market": "BIST", "currency": "TRY",
     "quantity": 120.0, "avg_cost": 280.0, "price": 295.5, "previous_close": 291.0,
     "change_percent": 1.55, "market_timestamp": NOW, "opened_at": NOW},
    {"symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ", "currency": "USD",
     "quantity": 15.0, "avg_cost": 195.0, "price": 215.3, "previous_close": 214.0,
     "change_percent": 0.6, "market_timestamp": NOW, "opened_at": NOW},
]

QUOTES = {
    "THYAO": {"price": 295.5, "market_timestamp": NOW, "change_percent": 1.55,
              "change_amount": 4.5, "previous_close": 291.0, "currency": "TRY",
              "volume": 100, "source": "yfinance"},
    "USDTRY": {"price": 41.0, "market_timestamp": NOW, "change_percent": 0.1,
               "change_amount": 0.04, "previous_close": 40.96, "currency": "TRY",
               "volume": None, "source": "yfinance"},
}

# backend_client.freshness() + portfolio_tools._normalize() read these.
REQUIRED_TOP_LEVEL = {
    "as_of", "source", "is_delayed", "delay_minutes",
    "base_currency", "positions", "totals", "warnings",
}
REQUIRED_POSITION_KEYS = {
    "symbol", "isin", "name", "asset_class", "exchange", "quantity", "avg_cost",
    "instrument_currency", "last_price", "market_value", "cost_basis",
    "unrealized_pnl", "unrealized_pnl_pct", "weight", "available_quantity", "opened_at",
}


class Product:
    def __init__(self, symbol, currency="TRY", market="BIST"):
        self.symbol = symbol
        self.currency_code = currency
        self.market = market
        self.data_symbol = f"{symbol}.IS"
        self.name = symbol
        self.product_type = "stock"


@pytest.fixture
def ai_client(mocker, holdings, quotes, resolved):
    from fastapi.testclient import TestClient

    mocker.patch.object(market_service, "holdings", return_value=holdings)
    mocker.patch.object(market_service, "latest_quotes", return_value=quotes)
    mocker.patch.object(market_service, "resolve_symbol", side_effect=resolved)
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def holdings():
    return list(HOLDINGS)


@pytest.fixture
def quotes():
    return dict(QUOTES)


@pytest.fixture
def resolved():
    """Default resolver: knows THYAO and AAPL, nothing else."""
    known = {"THYAO": Product("THYAO"), "AAPL": Product("AAPL", "USD", "NASDAQ")}

    def _resolve(_db, text):
        if not text:
            return None
        return known.get(str(text).upper().removeprefix("TEST-").removesuffix(".IS"))

    return _resolve


def stage_body(**overrides):
    body = {
        "user_id": "TEST-USER-1",
        "transaction_type": "BUY",
        "source_account_id": "TR-DEMO-0001",
        "idempotency_key": "idem-key-001",
        "instrument": {"symbol": "THYAO"},
        "quantity": 10,
        "order_type": "MARKET",
    }
    body.update(overrides)
    return body


class TestPortfolioContract:
    def test_top_level_keys_are_complete(self, ai_client):
        assert set(ai_client.get(PORTFOLIO_URL).json()) == REQUIRED_TOP_LEVEL

    def test_position_keys_are_complete(self, ai_client):
        body = ai_client.get(PORTFOLIO_URL).json()
        assert set(body["positions"][0]) == REQUIRED_POSITION_KEYS

    def test_symbols_have_no_test_prefix(self, ai_client):
        """The prefix is what made the assistant reject an ordinary "THYAO"."""
        body = ai_client.get(PORTFOLIO_URL).json()
        assert all(not p["symbol"].startswith("TEST-") for p in body["positions"])

    def test_as_of_reflects_the_quote_not_now(self, ai_client):
        body = ai_client.get(PORTFOLIO_URL).json()
        assert body["as_of"].startswith(NOW.strftime("%Y-%m-%dT%H:%M"))


class TestValuation:
    def test_try_position_values_at_price_times_quantity(self, ai_client):
        body = ai_client.get(PORTFOLIO_URL).json()
        thyao = next(p for p in body["positions"] if p["symbol"] == "THYAO")
        assert thyao["market_value"] == pytest.approx(120 * 295.5)
        assert thyao["cost_basis"] == pytest.approx(120 * 280.0)

    def test_foreign_position_is_converted_at_the_live_rate(self, ai_client):
        """One quotes table means the chatbot and the dashboard cannot use
        different exchange rates."""
        body = ai_client.get(PORTFOLIO_URL).json()
        aapl = next(p for p in body["positions"] if p["symbol"] == "AAPL")
        assert aapl["market_value"] == pytest.approx(15 * 215.3 * 41.0)

    def test_weights_sum_to_one(self, ai_client):
        body = ai_client.get(PORTFOLIO_URL).json()
        assert sum(p["weight"] for p in body["positions"]) == pytest.approx(1.0, abs=1e-4)

    def test_totals_agree_with_the_positions(self, ai_client):
        body = ai_client.get(PORTFOLIO_URL).json()
        assert body["totals"]["total_market_value"] == pytest.approx(
            sum(p["market_value"] for p in body["positions"]), abs=0.01
        )

    def test_unsupported_base_currency_is_a_client_error(self, ai_client):
        response = ai_client.get(f"{PORTFOLIO_URL}?base_currency=JPY")
        assert response.status_code == 400


class TestMissingData:
    @pytest.mark.parametrize("quotes", [{}])
    def test_missing_fx_rate_omits_foreign_holdings_with_a_warning(self, ai_client):
        """Converting at an invented rate would put a fabricated number in a
        portfolio total. The holding is excluded and the user told why."""
        body = ai_client.get(PORTFOLIO_URL).json()
        assert [p["symbol"] for p in body["positions"]] == ["THYAO"]
        assert any("USDTRY" in w for w in body["warnings"])

    @pytest.mark.parametrize(
        "holdings",
        [[{**HOLDINGS[0], "price": None}]],
    )
    def test_unpriced_holding_is_excluded_not_valued_at_zero(self, ai_client):
        """A zero price renders as a holding that lost all its value."""
        body = ai_client.get(PORTFOLIO_URL).json()
        assert body["positions"] == []
        assert any("fiyat alınamadı" in w for w in body["warnings"])

    @pytest.mark.parametrize("holdings", [[]])
    def test_empty_portfolio_is_a_complete_answer(self, ai_client):
        body = ai_client.get(PORTFOLIO_URL).json()
        assert body["positions"] == []
        assert body["totals"]["position_count"] == 0


class TestSymbolResolution:
    """The bug that made an ordinary buy order fail: the user typed THYAO and
    the system only knew TEST-THYAO."""

    @pytest.mark.parametrize("typed", ["THYAO", "thyao", "THYAO.IS", "TEST-THYAO"])
    def test_all_spellings_stage_successfully(self, ai_client, typed):
        body = ai_client.post(
            STAGE_URL, json=stage_body(instrument={"symbol": typed})
        ).json()
        assert body["status"] == "PENDING_USER_CONFIRMATION"
        assert body["summary"]["symbol"] == "THYAO"

    def test_an_instrument_that_does_not_exist_is_still_refused(self, ai_client):
        body = ai_client.post(
            STAGE_URL, json=stage_body(instrument={"symbol": "NOTAREALTICKER"})
        ).json()
        assert body["status"] == "REJECTED_VALIDATION"


class TestStaging:
    def test_valid_order_is_staged(self, ai_client):
        body = ai_client.post(STAGE_URL, json=stage_body()).json()
        assert body["status"] == "PENDING_USER_CONFIRMATION"
        assert body["confirmation_required"] is True

    def test_estimate_is_indicative_and_priced_from_the_live_quote(self, ai_client):
        body = ai_client.post(STAGE_URL, json=stage_body()).json()
        assert body["estimate"]["price_certainty"] == "INDICATIVE"
        assert body["estimate"]["gross_amount"] == pytest.approx(10 * 295.5)

    def test_oversized_sell_is_blocked_against_real_holdings(self, ai_client):
        """120 shares held. Staging a 500-share sell would present an
        impossible order as pending."""
        body = ai_client.post(
            STAGE_URL, json=stage_body(transaction_type="SELL", quantity=500)
        ).json()
        assert body["status"] == "REJECTED_VALIDATION"
        assert any("Satılabilir miktar" in b for b in body["blockers"])

    def test_sell_within_holdings_is_staged(self, ai_client):
        body = ai_client.post(
            STAGE_URL, json=stage_body(transaction_type="SELL", quantity=50)
        ).json()
        assert body["status"] == "PENDING_USER_CONFIRMATION"

    def test_missing_symbol_requires_input(self, ai_client):
        body = ai_client.post(STAGE_URL, json=stage_body(instrument=None)).json()
        assert body["status"] == "REQUIRES_ADDITIONAL_INPUT"
        assert "instrument.symbol" in body["missing_fields"]

    def test_limit_order_uses_the_limit_price_as_reference(self, ai_client):
        body = ai_client.post(
            STAGE_URL, json=stage_body(order_type="LIMIT", limit_price=128.0)
        ).json()
        assert body["estimate"]["reference_price"] == pytest.approx(128.0)

    def test_same_idempotency_key_yields_the_same_proposal(self, ai_client):
        first = ai_client.post(STAGE_URL, json=stage_body()).json()
        second = ai_client.post(STAGE_URL, json=stage_body()).json()
        assert first["proposal_id"] == second["proposal_id"]


class TestFxRates:
    def test_rate_comes_from_the_live_quote(self):
        assert ai_service.fx_rates(QUOTES)["USD"] == pytest.approx(41.0)

    def test_no_fallback_rate_is_invented(self):
        """A hardcoded rate is a made-up portfolio total. USD is simply
        absent until the quote arrives."""
        assert "USD" not in ai_service.fx_rates({})
        assert ai_service.fx_rates(None) == {"TRY": 1.0}

    def test_unknown_currency_raises_rather_than_defaulting(self):
        with pytest.raises(KeyError):
            ai_service._convert(100.0, "GBP", "TRY", {"TRY": 1.0})
