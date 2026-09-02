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
from types import SimpleNamespace
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
def cash() -> float:
    """Opening balance for the staging tests.

    Override it in a test that needs a purchase to be unaffordable — staging
    now refuses a buy the balance cannot cover, so the balance is part of the
    fixture rather than an incidental mock attribute.
    """
    return 1_000_000.0


@pytest.fixture
def ai_client(mocker, holdings, quotes, resolved, cash):
    from fastapi.testclient import TestClient

    mocker.patch.object(market_service, "holdings", return_value=holdings)
    mocker.patch.object(market_service, "latest_quotes", return_value=quotes)
    mocker.patch.object(market_service, "resolve_symbol", side_effect=resolved)
    mocker.patch.object(
        market_service, "account", return_value=SimpleNamespace(id="acct-1", cash_balance=cash, currency_code="TRY", account_number="TR-TEST-0001")
    )
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

    def _resolve(_db, text, **_kwargs):
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


class TestVenue:
    """`exchange` UÇ NOKTADAN geçmeli, yalnızca `build_portfolio`'dan değil.

    Alan bir dönem `str` olarak zorunluydu ve eşleşmeyen her piyasa "XIST"
    ile dolduruluyordu -- yani döviz ve altın ajana "Borsa İstanbul'da işlem
    görüyor" diye gidiyordu. None'a çevrildiğinde yanıt modeli 500 verdi ve
    birim testler bunu görmedi, çünkü hepsi `build_portfolio`'yu doğrudan
    çağırıp yanıt modelini atlıyor. Bu sınıf o boşluğu kapatıyor.
    """

    @pytest.mark.parametrize(
        "holdings",
        [[{**HOLDINGS[0], "symbol": "USDTRY", "market": "FX"}]],
    )
    def test_a_currency_pair_serialises_with_a_null_venue(self, ai_client):
        response = ai_client.get(PORTFOLIO_URL)
        assert response.status_code == 200
        assert response.json()["positions"][0]["exchange"] is None

    @pytest.mark.parametrize(
        "holdings",
        [[{**HOLDINGS[0], "symbol": "XAUUSD", "market": "COMEX"}]],
    )
    def test_gold_serialises_with_a_null_venue(self, ai_client):
        response = ai_client.get(PORTFOLIO_URL)
        assert response.status_code == 200
        assert response.json()["positions"][0]["exchange"] is None

    def test_a_listed_share_still_reports_its_mic(self, ai_client):
        body = ai_client.get(PORTFOLIO_URL).json()
        thyao = next(p for p in body["positions"] if p["symbol"] == "THYAO")
        assert thyao["exchange"] == "XIST"


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


class TestBuyingPower:
    """The buy-side check that did not exist. A purchase used to be staged
    regardless of the balance, so an unaffordable order sat "pending
    confirmation" until confirm refused it — after the user had already been
    shown a confirm button.
    """

    @pytest.fixture
    def cash(self):
        return 1000.0

    def test_a_purchase_over_the_balance_is_rejected_at_staging(self, ai_client):
        body = stage_body(transaction_type="BUY", quantity=100)
        result = ai_client.post("/api/investment/transactions/stage", json=body).json()
        assert result["status"] == "REJECTED_VALIDATION"
        assert any("Bakiye yetersiz" in blocker for blocker in result["blockers"])

    def test_the_blocker_names_both_figures(self, ai_client):
        """"Insufficient" without the numbers leaves the user guessing how
        much short they are."""
        body = stage_body(transaction_type="BUY", quantity=100)
        result = ai_client.post("/api/investment/transactions/stage", json=body).json()
        blocker = next(b for b in result["blockers"] if "Bakiye yetersiz" in b)
        assert "1,000.00" in blocker

    def test_the_check_includes_fees_not_just_the_gross(self, ai_client, quotes):
        """İK-07 in its codified form: the balance must cover the amount AND
        the fee. A gross-only check would pass an order that overdraws once
        commission and BSMV land."""
        body = stage_body(transaction_type="BUY", quantity=100)
        result = ai_client.post("/api/investment/transactions/stage", json=body).json()
        blocker = next(b for b in result["blockers"] if "Bakiye yetersiz" in b)
        quoted = float(blocker.split("birlikte ")[1].split(" ")[0].replace(",", ""))
        gross = 100 * quotes["THYAO"]["price"]
        assert quoted > gross, "fees must be part of what the balance has to cover"


class TestForeignCurrencyStaging:
    """A USD instrument costs USD; the account holds TRY.

    Comparing the two without converting made a foreign purchase look ~48x
    cheaper than it is, which is how an unaffordable order passed the funds
    check. The blocker message also labelled BOTH sides with the instrument's
    currency, so a TRY balance was reported as USD.
    """

    @pytest.fixture
    def cash(self):
        return 20_000.0

    @pytest.fixture
    def resolved(self):
        def _resolve(_db, text, **_kwargs):
            symbol = (text or "").upper()
            if symbol in {"AAPL", "XAUUSD"}:
                return Product(symbol, "USD", "NASDAQ")
            return Product("THYAO") if symbol == "THYAO" else None
        return _resolve

    @pytest.fixture
    def quotes(self):
        return {
            "THYAO": {"price": 304.0},
            "AAPL": {"price": 314.88},
            "XAUUSD": {"price": 4577.90},
            "USDTRY": {"price": 47.9479},
        }

    def _stage(self, client, **overrides):
        body = stage_body(**overrides)
        return client.post("/api/investment/transactions/stage", json=body).json()

    def test_a_usd_purchase_is_measured_in_the_accounts_currency(self, ai_client):
        """1 AAPL is ~15.098 TL, not 315 TL. With a 20.000 TL balance it is
        affordable — but only just, and for the right reason."""
        result = self._stage(ai_client, instrument={"symbol": "AAPL"}, quantity=1)
        assert result["status"] == "PENDING_USER_CONFIRMATION"

    def test_an_unaffordable_usd_purchase_is_blocked(self, ai_client):
        """2 AAPL is ~30.000 TL against a 20.000 TL balance. Before the fix
        this compared 630 USD to 20.000 and sailed through."""
        result = self._stage(ai_client, instrument={"symbol": "AAPL"}, quantity=2)
        assert result["status"] == "REJECTED_VALIDATION"
        blocker = next(b for b in result["blockers"] if "Bakiye yetersiz" in b)
        assert "TRY" in blocker, "both sides must be quoted in the account's currency"
        assert "USD" not in blocker

    def test_the_proposal_records_the_rate_it_was_priced_at(self, ai_client):
        """Settlement reads this rather than re-fetching: the user approved a
        cost computed at this rate."""
        result = self._stage(ai_client, instrument={"symbol": "AAPL"}, quantity=1)
        fx = result["estimate"]["fx"]
        assert fx["from_currency"] == "USD"
        assert fx["to_currency"] == "TRY"
        assert fx["rate"] == pytest.approx(47.9479, rel=1e-4)

    def test_a_try_trade_records_no_conversion(self, ai_client):
        result = self._stage(ai_client, instrument={"symbol": "THYAO"}, quantity=1)
        assert result["estimate"]["fx"] is None


class TestMissingExchangeRate:
    """No USDTRY quote ingested. Guessing at 1.0 is what let a 15.000 TL
    position be bought for 315 TL, so the trade is refused instead."""

    @pytest.fixture
    def cash(self):
        return 1_000_000.0

    @pytest.fixture
    def resolved(self):
        return lambda _db, text, **_kwargs: (
            Product("AAPL", "USD", "NASDAQ") if (text or "").upper() == "AAPL" else None
        )

    @pytest.fixture
    def quotes(self):
        # Deliberately no USDTRY.
        return {"AAPL": {"price": 314.88}}

    def test_a_foreign_purchase_without_a_rate_is_refused(self, ai_client):
        result = ai_client.post(
            "/api/investment/transactions/stage",
            json=stage_body(instrument={"symbol": "AAPL"}, quantity=1),
        ).json()
        assert result["status"] == "REJECTED_VALIDATION"
        assert any("kur" in b.lower() for b in result["blockers"])

    def test_no_fx_block_is_invented(self, ai_client):
        """A proposal cannot carry a rate nobody measured."""
        from app.modules.investment import ai_service

        assert ai_service._fx_block("USD", "TRY", {"TRY": 1.0}) is None
        assert ai_service._fx_block("USD", "TRY", None) is None
        assert ai_service._fx_block("TRY", "TRY", {"TRY": 1.0}) is None


class TestSourceAccountResolution:
    """`source_account_id` was stored but never validated, so the chat asked
    for an id, accepted "1", and used it for nothing — then confirm could not
    find the account and the transfer failed after the user had approved it."""

    def _resolve(self, **kwargs):
        from app.modules.investment.router import _resolve_source_account

        defaults = dict(
            db=MagicMock(spec=Session), requested=None, owner=None,
            owner_id="user-1", transaction_type="BUY",
        )
        defaults.update(kwargs)
        return _resolve_source_account(**defaults)

    def _owner(self, number="TR-INV-1"):
        return SimpleNamespace(id="acct-1", account_number=number)

    def test_a_trade_defaults_to_the_investment_account(self):
        assert self._resolve(owner=self._owner()) == "TR-INV-1"

    def test_a_meaningless_id_is_replaced_not_trusted(self):
        """"1" is what users typed when asked for an account id."""
        assert self._resolve(requested="1", owner=self._owner()) == "TR-INV-1"

    def test_the_users_own_account_number_is_honoured(self):
        assert self._resolve(requested="TR-INV-1", owner=self._owner()) == "TR-INV-1"

    def test_with_no_account_the_request_is_left_alone(self):
        """Nothing to substitute; the tool's own validation reports it."""
        assert self._resolve(requested="whatever", owner=None) == "whatever"

    def test_a_transfer_uses_the_deposit_account(self, mocker):
        from app.modules.banking import service as banking_service

        mocker.patch.object(
            banking_service, "ensure_account",
            return_value=SimpleNamespace(account_number="1000000000001"),
        )
        assert self._resolve(transaction_type="TRANSFER") == "1000000000001"

    def test_a_transfer_honours_a_deposit_account_the_user_owns(self, mocker):
        from app.modules.banking import service as banking_service

        mocker.patch.object(
            banking_service, "find_account",
            return_value=SimpleNamespace(account_number="1000000000009", user_id="user-1"),
        )
        assert self._resolve(
            requested="1000000000009", transaction_type="TRANSFER"
        ) == "1000000000009"

    def test_a_transfer_from_someone_elses_account_falls_back_to_your_own(self, mocker):
        """Silently substituting is safe here — the transfer service checks
        ownership again and would refuse it anyway."""
        from app.modules.banking import service as banking_service

        mocker.patch.object(
            banking_service, "find_account",
            return_value=SimpleNamespace(account_number="1000000000002", user_id="someone-else"),
        )
        mocker.patch.object(
            banking_service, "ensure_account",
            return_value=SimpleNamespace(account_number="1000000000001"),
        )
        assert self._resolve(
            requested="1000000000002", transaction_type="TRANSFER"
        ) == "1000000000001"

    def test_an_anonymous_transfer_keeps_what_was_asked_for(self, mocker):
        assert self._resolve(
            requested="1000000000002", owner_id=None, transaction_type="TRANSFER"
        ) == "1000000000002"


class TestTransferPricing:
    """A transfer is not a brokerage order. Charging it commission and BSMV
    priced a 200 TL transfer at 200,30 TL."""

    def test_no_commission_or_tax_is_applied(self):
        from app.modules.investment import ai_service

        estimate = ai_service._estimate(
            "TRANSFER", None, {"amount": 200.0, "currency": "TRY"}, None, None, "TRY"
        )
        assert estimate["net_amount"] == pytest.approx(200.0)
        assert estimate["fees"] == []
        assert estimate["taxes"] == []

    def test_a_trade_still_carries_its_fees(self):
        from app.modules.investment import ai_service

        estimate = ai_service._estimate("BUY", 10, None, 100.0, None, "TRY")
        assert estimate["net_amount"] > 1000.0
        assert estimate["fees"]
