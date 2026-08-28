"""Portföy Analizi assembly.

The properties that matter are the ones that make an analysis screen lie:
percentages that do not sum, a trend built from a stale price carried forward,
and a volatility figure computed from a handful of bars presented as a
measurement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.analytics import service

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def holding(symbol="THYAO", quantity=100.0, price=300.0, avg_cost=250.0):
    return {"symbol": symbol, "quantity": quantity, "price": price, "avg_cost": avg_cost}


def closes(symbol_prices, days=5, start=NOW):
    """A closes-reader returning `days` bars of the given price per symbol."""
    def reader(symbol):
        price = symbol_prices.get(symbol)
        if price is None:
            return []
        return [(start - timedelta(days=n), price) for n in range(days - 1, -1, -1)]
    return reader


def build(**overrides):
    kwargs = dict(
        db=MagicMock(spec=Session),
        user_id="user-1",
        holdings=[holding()],
        cash=25000.0,
        sector_map={"THYAO": "Industrials"},
        closes_for=closes({"THYAO": 300.0}),
        proposals=[],
        as_of=NOW,
        delay_minutes=15,
    )
    kwargs.update(overrides)
    return service.build(**kwargs)


class TestValuation:
    def test_total_is_cash_plus_positions(self):
        result = build(holdings=[holding(quantity=100, price=300)], cash=25000.0)
        assert result["total_value"] == pytest.approx(55000.0)
        assert result["invested"] == pytest.approx(30000.0)

    def test_unrealised_pnl_uses_the_cost_basis(self):
        result = build(holdings=[holding(quantity=100, price=300, avg_cost=250)])
        assert result["unrealised_pnl"] == pytest.approx(5000.0)
        assert result["unrealised_pnl_percent"] == pytest.approx(20.0)

    def test_a_zero_cost_basis_yields_no_percentage_rather_than_infinity(self):
        result = build(holdings=[holding(avg_cost=0.0)])
        assert result["unrealised_pnl_percent"] is None

    def test_an_unpriced_holding_is_excluded_and_named(self):
        """Valuing it at zero would report the position as a total loss."""
        result = build(holdings=[holding(), holding(symbol="IPEKE", price=None)])
        assert result["invested"] == pytest.approx(30000.0)
        assert any("IPEKE" in w for w in result["warnings"])


class TestAllocation:
    def test_percentages_sum_to_one_hundred(self):
        """BR-02. A pie chart whose slices do not sum is not a breakdown."""
        result = build(
            holdings=[holding("THYAO", 100, 300), holding("ASELS", 200, 50)],
            cash=25000.0,
            closes_for=closes({"THYAO": 300.0, "ASELS": 50.0}),
        )
        total = sum(slice_["percentage"] for slice_ in result["allocation"])
        assert total == pytest.approx(100.0, abs=0.005), "BR-02: exactly 100%"

    def test_cash_is_a_slice_of_its_own(self):
        result = build(cash=25000.0)
        assert result["allocation"][0]["label"] == "Nakit (TRY)"

    def test_largest_position_comes_first(self):
        result = build(
            holdings=[holding("SMALL", 1, 10), holding("BIG", 100, 300)],
            cash=0.0,
            closes_for=closes({"SMALL": 10.0, "BIG": 300.0}),
        )
        labels = [s["label"] for s in result["allocation"] if s["label"] != "Nakit (TRY)"]
        assert labels[0] == "BIG"

    def test_an_unknown_sector_is_labelled_not_guessed(self):
        result = build(sector_map={})
        assert result["sectors"][0]["label"] == "Bilinmiyor"


class TestTrend:
    def test_value_series_is_quantity_times_close(self):
        result = build(holdings=[holding(quantity=10, price=300)], closes_for=closes({"THYAO": 300.0}))
        assert result["trend"][0]["value"] == pytest.approx(3000.0)

    def test_only_dates_every_symbol_traded_are_used(self):
        """Carrying a stale price forward would show the portfolio moving on a
        day that instrument did not trade — a fabricated point."""
        def reader(symbol):
            if symbol == "THYAO":
                return [(NOW - timedelta(days=n), 300.0) for n in range(4, -1, -1)]
            # ASELS has the three most recent days; the intersection is those.
            return [(NOW - timedelta(days=n), 50.0) for n in range(2, -1, -1)]

        result = build(
            holdings=[holding("THYAO", 10, 300), holding("ASELS", 10, 50)],
            closes_for=reader,
        )
        assert len(result["trend"]) == 3

    def test_a_symbol_too_thin_to_measure_is_dropped_and_the_gap_disclosed(self):
        """Two bars is a price ratio, not a series.

        The threshold used to differ between this module (2) and `risk` (3),
        which is one of the reasons the two reported different numbers for one
        portfolio. Now that both read the same builder there is one bar, and
        it is the stricter one. What matters is that dropping a holding is
        SAID: the series then ends below the total shown above it.
        """
        def reader(symbol):
            if symbol == "THYAO":
                return [(NOW - timedelta(days=n), 300.0) for n in range(4, -1, -1)]
            return [(NOW - timedelta(days=n), 50.0) for n in range(1, -1, -1)]

        result = build(
            holdings=[holding("THYAO", 10, 300), holding("ASELS", 10, 50)],
            closes_for=reader,
        )
        assert result["excluded_symbols"] == ["ASELS"]
        assert any("ASELS" in w and "toplamın altında" in w for w in result["warnings"])
        # THYAO alone: the value carries only what could be measured.
        assert result["trend"][-1]["value"] == pytest.approx(3000.0)

    def test_a_symbol_without_history_is_excluded_and_named(self):
        result = build(
            holdings=[holding("THYAO"), holding("IPEKE", 10, 5)],
            closes_for=closes({"THYAO": 300.0}),
        )
        assert result["excluded_symbols"] == ["IPEKE"]
        assert any("IPEKE" in w for w in result["warnings"])

    def test_the_trend_is_disclosed_as_a_reconstruction(self):
        """It reprices today's basket over past closes. The account's real
        historical value is not recorded anywhere, and presenting this as if
        it were would be the more comfortable lie."""
        result = build()
        assert any("bugünkü pozisyonların" in w for w in result["warnings"])

    def test_no_priced_holdings_yields_an_empty_trend_not_a_crash(self):
        result = build(holdings=[], closes_for=closes({}))
        assert result["trend"] == []
        assert result["performance"]["observations"] == 0


class TestPerformance:
    def test_a_short_window_is_flagged_unreliable(self):
        """Five bars is arithmetic, not evidence."""
        result = build(closes_for=closes({"THYAO": 300.0}, days=5))
        assert result["performance"]["is_statistically_reliable"] is False

    def test_a_full_window_is_reliable(self):
        result = build(closes_for=closes({"THYAO": 300.0}, days=200))
        assert result["performance"]["is_statistically_reliable"] is True

    def test_total_return_is_measured_end_over_start(self):
        # Three bars, because a series needs two returns to be one.
        def rising(symbol):
            return [
                (NOW - timedelta(days=3), 100.0),
                (NOW - timedelta(days=2), 105.0),
                (NOW - timedelta(days=1), 110.0),
            ]

        result = build(holdings=[holding(quantity=1, price=110)], closes_for=rising)
        assert result["performance"]["total_return_percent"] == pytest.approx(10.0)

    def test_a_single_point_yields_no_return_rather_than_zero(self):
        """Zero means "it did not move", which is a measurement. One point
        supports no measurement at all.

        Both bars fall on the same DAY, so the series has one point and is
        dropped entirely rather than drawn as a one-point line. That is the
        change from the old builder, which indexed by position and so counted
        the same day twice.
        """
        def one_bar(symbol):
            return [(NOW, 100.0), (NOW, 100.0)]

        result = build(closes_for=one_bar)
        assert result["trend"] == []
        assert result["performance"]["total_return_percent"] is None


class TestActivity:
    def _proposal(self, status="CONFIRMED", kind="BUY", net=1000.0, confirmed=NOW):
        return SimpleNamespace(
            status=status, transaction_type=kind,
            payload={"estimate": {"net_amount": net}}, confirmed_at=confirmed,
        )

    def test_only_confirmed_proposals_count(self):
        """A rejected or pending proposal is not activity; it is an intention."""
        result = build(proposals=[
            self._proposal(),
            self._proposal(status="REJECTED_VALIDATION"),
            self._proposal(status="PENDING_USER_CONFIRMATION"),
        ])
        assert result["activity"]["confirmed_count"] == 1

    def test_buys_and_sells_are_counted_separately(self):
        result = build(proposals=[self._proposal(kind="BUY"), self._proposal(kind="SELL")])
        assert result["activity"]["buy_count"] == 1
        assert result["activity"]["sell_count"] == 1

    def test_traded_value_sums_the_net_amounts(self):
        result = build(proposals=[self._proposal(net=1000.0), self._proposal(net=2500.0)])
        assert result["activity"]["total_traded_value"] == pytest.approx(3500.0)

    def test_a_proposal_without_an_estimate_does_not_break_the_total(self):
        broken = SimpleNamespace(
            status="CONFIRMED", transaction_type="BUY", payload={}, confirmed_at=NOW
        )
        result = build(proposals=[broken, self._proposal(net=1000.0)])
        assert result["activity"]["total_traded_value"] == pytest.approx(1000.0)

    def test_the_latest_confirmation_is_reported(self):
        older = self._proposal(confirmed=NOW - timedelta(days=3))
        result = build(proposals=[older, self._proposal(confirmed=NOW)])
        assert result["activity"]["last_transaction_at"] == NOW

    def test_no_activity_is_zeroes_not_nulls(self):
        result = build(proposals=[])
        assert result["activity"]["confirmed_count"] == 0
        assert result["activity"]["last_transaction_at"] is None


class TestNoOverlappingHistory:
    def test_symbols_with_no_shared_trading_days_yield_no_trend(self):
        """Two instruments whose bars never coincide cannot produce a
        portfolio value for any single day. An empty trend says that; picking
        one symbol's days and guessing the other's price would not."""
        def disjoint(symbol):
            if symbol == "THYAO":
                return [(NOW - timedelta(days=n), 300.0) for n in (10, 9)]
            return [(NOW - timedelta(days=n), 50.0) for n in (2, 1)]

        result = build(
            holdings=[holding("THYAO", 10, 300), holding("ASELS", 10, 50)],
            closes_for=disjoint,
        )
        assert result["trend"] == []


class TestPercentagesAlwaysSumToOneHundred:
    """BR-02 is stated as "always", so rounding drift is a violation, not a
    tolerance. Twelve positions rounded independently landed on 100.02%."""

    def test_many_positions_still_sum_exactly(self):
        holdings = [holding(f"SYM{n}", quantity=3, price=101.0 + n) for n in range(12)]
        result = build(
            holdings=holdings,
            cash=1234.56,
            closes_for=closes({f"SYM{n}": 101.0 + n for n in range(12)}),
        )
        total = sum(s["percentage"] for s in result["allocation"])
        assert total == pytest.approx(100.0, abs=0.005)

    def test_sectors_sum_exactly_too(self):
        holdings = [holding(f"SYM{n}", quantity=3, price=101.0 + n) for n in range(7)]
        result = build(
            holdings=holdings,
            sector_map={f"SYM{n}": f"Sector{n % 3}" for n in range(7)},
            closes_for=closes({f"SYM{n}": 101.0 + n for n in range(7)}),
        )
        total = sum(s["percentage"] for s in result["sectors"])
        assert total == pytest.approx(100.0, abs=0.005)

    def test_the_residual_lands_on_the_largest_slice(self):
        """Proportionally smallest there, and it cannot flip how a small
        holding's share reads."""
        result = build(
            holdings=[holding("BIG", 100, 300), holding("SMALL", 1, 3)],
            cash=0.0,
            closes_for=closes({"BIG": 300.0, "SMALL": 3.0}),
        )
        largest = max(result["allocation"], key=lambda s: s["percentage"])
        assert largest["label"] == "BIG"

    def test_an_empty_portfolio_normalises_to_nothing(self):
        result = build(holdings=[], cash=0.0, closes_for=closes({}))
        assert result["sectors"] == []


class TestDrawdown:
    def test_a_decline_is_reported_as_a_percentage(self):
        """The key is `value`; reading a differently-named one silently
        reported every portfolio as having never fallen."""
        def dipping(symbol):
            prices = [100.0, 120.0, 60.0, 90.0]
            return [(NOW - timedelta(days=len(prices) - n), p) for n, p in enumerate(prices)]

        result = build(holdings=[holding(quantity=1, price=90)], closes_for=dipping)
        assert result["performance"]["max_drawdown_percent"] == pytest.approx(-50.0)

    def test_a_series_that_only_rises_has_no_drawdown(self):
        def rising(symbol):
            prices = [100.0, 110.0, 120.0]
            return [(NOW - timedelta(days=len(prices) - n), p) for n, p in enumerate(prices)]

        result = build(holdings=[holding(quantity=1, price=120)], closes_for=rising)
        assert result["performance"]["max_drawdown_percent"] is None


class TestCurrencyConversion:
    """Values are converted before they are summed.

    Adding a dollar holding straight into a lira total counted it at roughly
    1/48th: this page reported ₺404.467 while /portfolio/summary reported
    ₺1.087.834 for the same portfolio.
    """

    RATES = {"TRY": 1.0, "USD": 47.9479}

    def _usd(self, symbol="AAPL", quantity=10.0, price=300.0, avg_cost=250.0):
        return {
            "symbol": symbol, "name": symbol, "market": "NASDAQ", "currency": "USD",
            "product_type": "stock", "quantity": quantity, "price": price,
            "avg_cost": avg_cost, "opened_at": None,
        }

    def _build(self, holdings, **kwargs):
        kwargs.setdefault("rates", self.RATES)
        return build(holdings=holdings, closes_for=closes({}), **kwargs)

    def test_a_dollar_holding_is_counted_at_its_lira_value(self):
        result = self._build([self._usd(quantity=10, price=300)], cash=0.0)
        # 10 x 300 USD = 3.000 USD = 143.843,70 TRY
        assert result["invested"] == pytest.approx(3000 * 47.9479, rel=1e-6)

    def test_a_lira_holding_is_not_converted_twice(self):
        result = self._build([holding("THYAO", 100, 300)], cash=0.0)
        assert result["invested"] == pytest.approx(30000.0)

    def test_mixed_currencies_sum_in_the_base_currency(self):
        result = self._build(
            [holding("THYAO", 100, 300), self._usd(quantity=10, price=300)], cash=0.0,
        )
        assert result["invested"] == pytest.approx(30000 + 3000 * 47.9479, rel=1e-6)

    def test_a_holding_with_no_rate_is_excluded_and_named(self):
        """Converting at an invented rate is how the number went wrong in the
        first place; leaving it out and saying so is the honest alternative."""
        result = self._build(
            [self._usd("AAPL")], cash=0.0, rates={"TRY": 1.0},
        )
        assert result["invested"] == 0.0
        assert any("AAPL" in w for w in result["warnings"])

    def test_the_report_declares_its_currency(self):
        result = self._build([holding()], cash=0.0)
        assert result["base_currency"] == "TRY"

    def test_allocation_slices_use_converted_values(self):
        result = self._build([self._usd(quantity=10, price=300)], cash=0.0)
        slice_ = next(s for s in result["allocation"] if s["label"] == "AAPL")
        assert slice_["value"] == pytest.approx(3000 * 47.9479, rel=1e-6)

    def test_sector_totals_use_converted_values(self):
        result = self._build(
            [self._usd(quantity=10, price=300)], cash=0.0,
            sector_map={"AAPL": "Technology"},
        )
        assert result["sectors"][0]["value"] == pytest.approx(3000 * 47.9479, rel=1e-6)
