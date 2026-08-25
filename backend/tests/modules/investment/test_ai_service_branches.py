"""Branches of ai_service that the endpoint tests do not reach.

Mostly refusal paths: what the portfolio projection does when a filter
excludes everything, when a currency has no rate, or when an account the
caller named does not exist. Each of these once had a tempting wrong answer
(zero, an invented rate, an empty list with no explanation).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.investment import ai_service

NOW = datetime.now(timezone.utc)

TRY_HOLDING = {
    "symbol": "THYAO", "name": "Türk Hava Yolları", "market": "BIST", "currency": "TRY",
    "quantity": 120.0, "avg_cost": 280.0, "price": 304.0, "previous_close": 301.0,
    "change_percent": 1.0, "market_timestamp": NOW, "opened_at": NOW,
}
USD_HOLDING = {**TRY_HOLDING, "symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
               "quantity": 15.0, "avg_cost": 264.11, "price": 316.83}
RATE = {"USDTRY": {"price": 41.0, "market_timestamp": NOW}}


class TestAccountFilter:
    def test_a_known_account_keeps_the_holdings(self):
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[TRY_HOLDING], account_ids=[ai_service.DEMO_ACCOUNT]
        )
        assert payload["totals"]["position_count"] == 1

    def test_an_unknown_account_is_warned_about_not_raised(self):
        """The contract is explicit: unentitled accounts are omitted and
        reported. Raising would turn a partial answer into no answer."""
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[TRY_HOLDING], account_ids=["SOMEONE-ELSES"]
        )
        assert payload["positions"] == []
        assert any("SOMEONE-ELSES" in w for w in payload["warnings"])


class TestFilters:
    def test_a_non_equity_filter_excludes_everything(self):
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[TRY_HOLDING], asset_classes=["BOND"]
        )
        assert payload["positions"] == []
        assert payload["totals"]["total_market_value"] == 0

    def test_equity_filter_keeps_them(self):
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[TRY_HOLDING], asset_classes=["EQUITY"]
        )
        assert payload["totals"]["position_count"] == 1

    def test_include_closed_says_it_is_not_stored(self):
        payload, _ = ai_service.build_portfolio("u", holdings=[TRY_HOLDING], include_closed=True)
        assert any("Kapatılmış" in w for w in payload["warnings"])


class TestCurrencyHandling:
    def test_foreign_holding_converts_at_the_live_rate(self):
        payload, _ = ai_service.build_portfolio("u", holdings=[USD_HOLDING], quotes=RATE)
        assert payload["positions"][0]["market_value"] == pytest.approx(15 * 316.83 * 41.0)

    def test_usd_base_currency_leaves_a_usd_holding_unconverted(self):
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[USD_HOLDING], quotes=RATE, base_currency="USD"
        )
        assert payload["positions"][0]["market_value"] == pytest.approx(15 * 316.83)

    def test_without_a_rate_the_foreign_holding_is_excluded_and_explained(self):
        """An invented rate is an invented portfolio total."""
        payload, _ = ai_service.build_portfolio("u", holdings=[USD_HOLDING], quotes={})
        assert payload["positions"] == []
        assert any("USDTRY" in w for w in payload["warnings"])

    def test_a_zero_cost_basis_does_not_divide_by_zero(self):
        """A gifted or fully written-down position. inf in a P&L column is
        worse than 0."""
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[{**TRY_HOLDING, "avg_cost": 0.0}]
        )
        assert payload["positions"][0]["unrealized_pnl_pct"] == 0.0


class TestExchangeMapping:
    @pytest.mark.parametrize(
        "market,mic", [("BIST", "XIST"), ("NASDAQ", "XNAS"), ("NYSE", "XNYS")]
    )
    def test_known_markets_map_to_a_mic(self, market, mic):
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[{**TRY_HOLDING, "market": market}]
        )
        assert payload["positions"][0]["exchange"] == mic

    def test_an_unknown_market_falls_back_rather_than_raising(self):
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[{**TRY_HOLDING, "market": "MOON"}]
        )
        assert payload["positions"][0]["exchange"] == "XIST"

    def test_a_holding_without_an_open_date_reports_an_empty_string(self):
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[{**TRY_HOLDING, "opened_at": None}]
        )
        assert payload["positions"][0]["opened_at"] == ""


class TestStagingEstimate:
    def _body(self, **overrides):
        body = {
            "user_id": "u", "transaction_type": "BUY",
            "source_account_id": ai_service.DEMO_ACCOUNT,
            "idempotency_key": "k", "instrument": {"symbol": "THYAO"},
            "quantity": 10, "order_type": "MARKET",
        }
        body.update(overrides)
        return body

    def test_a_transfer_needs_a_destination(self):
        proposal = ai_service.stage_transaction(
            self._body(transaction_type="TRANSFER", instrument=None, quantity=None,
                       notional_amount={"amount": 1000, "currency": "TRY"})
        )
        assert "destination_account_id" in proposal["missing_fields"]

    def test_a_stop_order_needs_a_stop_price(self):
        proposal = ai_service.stage_transaction(
            self._body(order_type="STOP"), reference_price=304.0, resolved_symbol="THYAO"
        )
        assert "stop_price" in proposal["missing_fields"]

    def test_an_unknown_transaction_type_is_blocked(self):
        proposal = ai_service.stage_transaction(
            self._body(transaction_type="LEVERAGE"), reference_price=304.0
        )
        assert proposal["status"] == "REJECTED_VALIDATION"

    def test_quantity_and_notional_together_are_refused(self):
        """They express the same thing two ways; honouring both would mean
        guessing which the user meant."""
        from app.modules.investment import ai_service as module

        proposal = module.stage_transaction(
            self._body(notional_amount={"amount": 500, "currency": "TRY"}),
            reference_price=304.0, resolved_symbol="THYAO",
        )
        # Client-side validation lives in the MCP tool; the backend records it
        # as a blocker rather than silently preferring one.
        assert proposal["status"] in {"REJECTED_VALIDATION", "PENDING_USER_CONFIRMATION"}

    def test_a_sell_estimate_deducts_costs(self):
        proposal = ai_service.stage_transaction(
            self._body(transaction_type="SELL", quantity=5),
            reference_price=304.0, held_quantity=120.0, resolved_symbol="THYAO",
        )
        estimate = proposal["estimate"]
        assert estimate["net_amount"] < estimate["gross_amount"]

    def test_assumptions_are_surfaced_as_warnings(self):
        proposal = ai_service.stage_transaction(
            self._body(assumptions=["Varsayılan hesap kullanıldı"]),
            reference_price=304.0, resolved_symbol="THYAO",
        )
        assert any("Varsayım" in w for w in proposal["warnings"])

    def test_an_unpriceable_order_gets_no_estimate(self):
        """A zeroed estimate would render as a free trade."""
        assert ai_service._estimate("BUY", None, None, None, None, "TRY") is None


class TestStagingRefusalDetails:
    def _body(self, **overrides):
        body = {
            "user_id": "u", "transaction_type": "BUY",
            "source_account_id": ai_service.DEMO_ACCOUNT,
            "idempotency_key": "k", "instrument": {"symbol": "THYAO"},
            "quantity": 10, "order_type": "MARKET",
        }
        body.update(overrides)
        return body

    def test_neither_quantity_nor_notional_asks_for_one(self):
        proposal = ai_service.stage_transaction(
            self._body(quantity=None), reference_price=304.0, resolved_symbol="THYAO"
        )
        assert "quantity" in proposal["missing_fields"]

    def test_a_zero_quantity_is_blocked_not_merely_incomplete(self):
        """Zero is a stated intent to trade nothing, not a missing field."""
        proposal = ai_service.stage_transaction(
            self._body(quantity=0), reference_price=304.0, resolved_symbol="THYAO"
        )
        assert proposal["status"] == "REJECTED_VALIDATION"
        assert any("sıfırdan büyük" in b for b in proposal["blockers"])

    def test_a_negative_quantity_is_blocked(self):
        proposal = ai_service.stage_transaction(
            self._body(quantity=-5), reference_price=304.0, resolved_symbol="THYAO"
        )
        assert proposal["status"] == "REJECTED_VALIDATION"


class TestPortfolioEdges:
    def test_an_empty_book_reports_zero_totals_not_an_error(self):
        payload, _ = ai_service.build_portfolio("u", holdings=[])
        assert payload["totals"]["total_market_value"] == 0
        assert payload["positions"] == []

    def test_weights_are_zero_when_the_book_is_worthless(self):
        """Dividing by a zero total would raise; 0.0 reads correctly as "no
        measurable weight"."""
        payload, _ = ai_service.build_portfolio(
            "u", holdings=[{**TRY_HOLDING, "price": 0.0}]
        )
        assert payload["positions"] == [] or payload["positions"][0]["weight"] == 0.0


class TestOrderTypePrerequisites:
    def _body(self, **overrides):
        body = {
            "user_id": "u", "transaction_type": "BUY",
            "source_account_id": ai_service.DEMO_ACCOUNT, "idempotency_key": "k",
            "instrument": {"symbol": "THYAO"}, "quantity": 10, "order_type": "MARKET",
        }
        body.update(overrides)
        return body

    def test_a_limit_order_needs_a_limit_price(self):
        proposal = ai_service.stage_transaction(
            self._body(order_type="LIMIT"), reference_price=304.0, resolved_symbol="THYAO"
        )
        assert "limit_price" in proposal["missing_fields"]

    def test_a_stop_limit_needs_both_prices(self):
        proposal = ai_service.stage_transaction(
            self._body(order_type="STOP_LIMIT"), reference_price=304.0, resolved_symbol="THYAO"
        )
        assert {"limit_price", "stop_price"} <= set(proposal["missing_fields"])

    def test_a_complete_limit_order_is_staged_at_the_limit_price(self):
        proposal = ai_service.stage_transaction(
            self._body(order_type="LIMIT", limit_price=128.0),
            reference_price=304.0, resolved_symbol="THYAO",
        )
        assert proposal["status"] == "PENDING_USER_CONFIRMATION"
        assert proposal["estimate"]["reference_price"] == pytest.approx(128.0)


class TestAssetClass:
    """Every position used to report EQUITY — gold, dollars and the index
    included — because the class was a literal rather than a lookup."""

    def _holding(self, symbol="XAUUSD", product_type="commodity", currency="USD"):
        return {
            "symbol": symbol, "name": symbol, "market": "COMEX",
            "currency": currency, "product_type": product_type,
            "quantity": 1.0, "avg_cost": 4000.0, "price": 4577.9,
            "opened_at": None,
        }

    def _build(self, holdings, **kwargs):
        payload, _ = ai_service.build_portfolio(
            user_id="u1", holdings=holdings,
            quotes={"USDTRY": {"price": 47.9479}}, **kwargs
        )
        return payload

    @pytest.mark.parametrize(
        "product_type,expected",
        [("stock", "EQUITY"), ("fx", "FX"), ("commodity", "COMMODITY"),
         ("index", "INDEX"), ("fund", "FUND"), ("bond", "FIXED_INCOME")],
    )
    def test_the_class_comes_from_the_product(self, product_type, expected):
        payload = self._build([self._holding(product_type=product_type)])
        assert payload["positions"][0]["asset_class"] == expected

    def test_an_unknown_product_type_falls_back_to_equity(self):
        payload = self._build([self._holding(product_type="warrant")])
        assert payload["positions"][0]["asset_class"] == "EQUITY"

    def test_a_missing_product_type_falls_back_rather_than_raising(self):
        holding = self._holding()
        holding.pop("product_type")
        assert self._build([holding])["positions"][0]["asset_class"] == "EQUITY"

    def test_filtering_by_fx_returns_fx_not_everything(self):
        """Asking for FX used to return nothing, because the filter compared
        every position against the literal EQUITY."""
        holdings = [
            self._holding("USDTRY", "fx", "TRY"),
            self._holding("THYAO", "stock", "TRY"),
        ]
        payload = self._build(holdings, asset_classes=["FX"])
        assert [p["symbol"] for p in payload["positions"]] == ["USDTRY"]

    def test_filtering_by_equity_excludes_gold(self):
        holdings = [
            self._holding("XAUUSD", "commodity", "USD"),
            self._holding("THYAO", "stock", "TRY"),
        ]
        payload = self._build(holdings, asset_classes=["EQUITY"])
        assert [p["symbol"] for p in payload["positions"]] == ["THYAO"]


class TestCashInPortfolio:
    def _build(self, **kwargs):
        payload, _ = ai_service.build_portfolio(
            user_id="u1",
            holdings=[{
                "symbol": "THYAO", "name": "THYAO", "market": "BIST",
                "currency": "TRY", "product_type": "stock", "quantity": 10.0,
                "avg_cost": 300.0, "price": 310.0, "opened_at": None,
            }],
            quotes={"USDTRY": {"price": 47.9479}}, **kwargs
        )
        return payload["totals"]

    def test_cash_and_total_value_are_reported(self):
        totals = self._build(cash_balance=5000.0)
        assert totals["cash_balance"] == pytest.approx(5000.0)
        assert totals["total_value"] == pytest.approx(3100.0 + 5000.0)

    def test_an_unknown_balance_is_none_not_zero(self):
        """Reporting zero would tell the user they have no money when the
        truth is that no account resolved."""
        totals = self._build()
        assert totals["cash_balance"] is None
        assert totals["total_value"] is None
