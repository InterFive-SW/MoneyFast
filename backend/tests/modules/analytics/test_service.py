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

    def test_a_short_history_no_longer_truncates_the_whole_series(self):
        """Kesişim yerine birleşim.

        Önceden yalnızca HER sembolün barı olan günler kullanılıyordu, yani tek
        bir kısa geçmişli isim bütün seriyi kırpıyordu -- grafiğin en eski
        pozisyondan değil, en GENÇ pozisyondan başlaması demekti bu.

        Artık her gün yazılıyor; o gün barı olmayan bir pozisyon son
        kapanışıyla değerleniyor. Bir portföyün değeri, içindeki bir ismin
        işlem görmediği gün de vardır.
        """
        def reader(symbol):
            if symbol == "THYAO":
                return [(NOW - timedelta(days=n), 300.0) for n in range(4, -1, -1)]
            # ASELS only has the two most recent days.
            return [(NOW - timedelta(days=n), 50.0) for n in range(1, -1, -1)]

        result = build(
            holdings=[holding("THYAO", 10, 300), holding("ASELS", 10, 50)],
            closes_for=reader,
        )
        assert len(result["trend"]) == 5
        # En eski üç günde yalnızca THYAO fiyatlı: 10 x 300.
        assert result["trend"][0]["value"] == pytest.approx(3000.0)
        # Son iki günde ikisi de: 3000 + 10 x 50.
        assert result["trend"][-1]["value"] == pytest.approx(3500.0)

    def test_a_position_contributes_nothing_before_it_was_opened(self):
        """Dün alınan bir hisse geçen yılın portföy değerinde görünmemeli.

        Trend, bugünkü pozisyonları geçmiş fiyatlarla yeniden değerliyordu;
        grafiğin anlattığı şey portföyün geçmişi değil, bugünkü portföyün
        geçmişte ne edeceğiydi.
        """
        opened = NOW - timedelta(days=1)
        rows = [holding("THYAO", 10, 300), holding("ASELS", 10, 50)]
        rows[1]["opened_at"] = opened

        result = build(
            holdings=rows,
            closes_for=lambda symbol: [
                (NOW - timedelta(days=n), 300.0 if symbol == "THYAO" else 50.0)
                for n in range(4, -1, -1)
            ],
        )
        # Açılışından önceki günler yalnızca THYAO; sonrakiler ikisi birden.
        assert result["trend"][0]["value"] == pytest.approx(3000.0)
        assert result["trend"][-1]["value"] == pytest.approx(3500.0)

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
        def rising(symbol):
            return [(NOW - timedelta(days=2), 100.0), (NOW - timedelta(days=1), 110.0)]

        result = build(holdings=[holding(quantity=1, price=110)], closes_for=rising)
        assert result["performance"]["total_return_percent"] == pytest.approx(10.0)

    def test_a_single_point_yields_no_return_rather_than_zero(self):
        """Zero means "it did not move", which is a measurement. One point
        supports no measurement at all."""
        def one_bar(symbol):
            return [(NOW, 100.0), (NOW, 100.0)]

        result = build(closes_for=one_bar)
        assert len(result["trend"]) == 1
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
    def test_disjoint_histories_still_produce_a_series(self):
        """Barları hiç çakışmayan iki enstrüman.

        Eskiden bu boş bir trend veriyordu: kesişim boştu. Ama portföyün
        değeri her gün vardır -- ilk iki gün yalnızca THYAO tutuluyordu,
        sonraki iki günde ASELS de eklendi ve THYAO son kapanışıyla duruyor.
        Günü tamamen düşürmek, portföyün o gün yok olduğunu söylemek olurdu.
        """
        def disjoint(symbol):
            if symbol == "THYAO":
                return [(NOW - timedelta(days=n), 300.0) for n in (10, 9)]
            return [(NOW - timedelta(days=n), 50.0) for n in (2, 1)]

        result = build(
            holdings=[holding("THYAO", 10, 300), holding("ASELS", 10, 50)],
            closes_for=disjoint,
        )
        assert len(result["trend"]) == 4
        assert result["trend"][0]["value"] == pytest.approx(3000.0)
        assert result["trend"][-1]["value"] == pytest.approx(3500.0)

    def test_a_currency_with_no_rate_is_left_out_and_named(self):
        """Kuru bilinmeyen pozisyon toplama katılmaz; 1.0 varsaymak 100 doları
        100 lira sanmaktır."""
        result = build(
            holdings=[{**holding("MSFT", 10, 400), "currency": "USD"}],
            closes_for=closes({"MSFT": 400.0}),
            rates={"TRY": 1.0},
        )
        assert any("MSFT" in w for w in result["warnings"])
        assert result["trend"] == []

    def test_a_foreign_holding_is_converted_before_it_is_summed(self):
        """Çevirmeden toplamak, dolar pozisyonlarını lira sanmaktır -- grafiğin
        1.382.868 TL'lik portföyü 411.991'de göstermesinin sebebi buydu."""
        result = build(
            holdings=[{**holding("MSFT", 10, 400), "currency": "USD"}],
            closes_for=closes({"MSFT": 400.0}),
            rates={"USD": 40.0, "TRY": 1.0},
        )
        assert result["trend"][0]["value"] == pytest.approx(160_000.0)


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


class TestQuantityTimeline:
    """Miktar, zamanın fonksiyonu.

    Grafik bugünkü pozisyonları geçmiş fiyatlarla yeniden değerliyordu: dün
    alınan bir hisse geçen yılın portföy değerinde de görünüyordu.
    """

    def _proposal(self, symbol, side, quantity, when, status="CONFIRMED"):
        return SimpleNamespace(
            symbol=symbol, transaction_type=side, quantity=quantity,
            status=status, confirmed_at=when, created_at=when,
        )

    def test_a_later_purchase_is_unwound_going_back(self):
        """Bugün 15 adet varsa ve 5'i dün alındıysa, iki gün önce 10 vardı."""
        rows = [holding("THYAO", 15, 300)]
        timeline = service._quantity_timeline(
            rows, [self._proposal("THYAO", "BUY", 5, NOW - timedelta(days=1))]
        )
        assert timeline["THYAO"](NOW) == pytest.approx(15.0)
        assert timeline["THYAO"](NOW - timedelta(days=2)) == pytest.approx(10.0)

    def test_a_later_sale_means_more_was_held_before(self):
        rows = [holding("THYAO", 10, 300)]
        timeline = service._quantity_timeline(
            rows, [self._proposal("THYAO", "SELL", 4, NOW - timedelta(days=1))]
        )
        assert timeline["THYAO"](NOW - timedelta(days=2)) == pytest.approx(14.0)

    def test_nothing_is_held_before_the_position_was_opened(self):
        rows = [holding("THYAO", 10, 300)]
        rows[0]["opened_at"] = NOW - timedelta(days=3)
        timeline = service._quantity_timeline(rows, [])
        assert timeline["THYAO"](NOW - timedelta(days=4)) == 0.0
        assert timeline["THYAO"](NOW) == pytest.approx(10.0)

    def test_quantity_never_goes_negative(self):
        """Tohumlanmış bir pozisyonun kaydı olmayan geçmişi eksi adet
        üretmemeli."""
        rows = [holding("THYAO", 1, 300)]
        timeline = service._quantity_timeline(
            rows, [self._proposal("THYAO", "BUY", 50, NOW)]
        )
        assert timeline["THYAO"](NOW - timedelta(days=1)) == 0.0

    def test_unconfirmed_and_unknown_rows_are_ignored(self):
        """Onaylanmamış bir öneri para hareket ettirmedi; miktarı da
        değiştirmez."""
        rows = [holding("THYAO", 10, 300)]
        noise = [
            self._proposal("THYAO", "BUY", 5, NOW, status="PENDING_USER_CONFIRMATION"),
            self._proposal("THYAO", "TRANSFER", 5, NOW),
            self._proposal(None, "BUY", 5, NOW),
            self._proposal("THYAO", "BUY", 5, None),
            self._proposal("THYAO", "BUY", "abc", NOW),
        ]
        timeline = service._quantity_timeline(rows, noise)
        assert timeline["THYAO"](NOW - timedelta(days=1)) == pytest.approx(10.0)


class TestPortfolioCandles:
    """Portföy değerinin mumları."""

    def _bars(self, prices):
        def reader(symbol):
            base = prices.get(symbol)
            if base is None:
                return []
            return [
                (NOW + timedelta(hours=n), base + n, base + n + 1) for n in range(4)
            ]
        return reader

    def test_a_bucket_with_several_points_gets_real_wicks(self):
        """Gün içi barların olduğu kovada yüksek/düşük gerçekten gözlenmiş
        portföy değerleridir."""
        candles = service.portfolio_candles(
            [holding("THYAO", 10, 300)], self._bars({"THYAO": 100.0}),
            bucket_seconds=0,
        )
        assert len(candles) == 1
        candle = candles[0]
        assert candle["open"] == pytest.approx(1000.0)
        assert candle["close"] == pytest.approx(1040.0)
        assert candle["high"] > max(candle["open"], candle["close"]) - 0.01
        assert candle["low"] <= candle["open"]

    def test_a_single_observation_is_a_body_with_no_wick(self):
        """Enstrümanların günlük en yükseklerini toplamak yanlış olurdu: o
        tepeler aynı anda oluşmadı."""
        def one_bar(symbol):
            return [(NOW, 100.0, 110.0), (NOW + timedelta(days=1), 110.0, 120.0)]

        candles = service.portfolio_candles(
            [holding("THYAO", 1, 300)], one_bar, bucket_seconds=0,
        )
        first = candles[0]
        assert first["high"] == pytest.approx(max(first["open"], first["close"]))
        assert first["low"] == pytest.approx(min(first["open"], first["close"]))

    def test_the_window_is_measured_from_the_last_point(self):
        """Piyasa kapalıyken "son yedi takvim günü" boş bir grafik demek
        olurdu."""
        def old(symbol):
            return [(NOW - timedelta(days=n), 100.0, 101.0) for n in (40, 39, 1, 0)]

        candles = service.portfolio_candles(
            [holding("THYAO", 1, 300)], old, bucket_seconds=0, window_days=7,
        )
        assert len(candles) == 2

    def test_no_bars_is_an_empty_series_not_a_crash(self):
        assert service.portfolio_candles([holding()], lambda _s: []) == []

    def test_an_unconvertible_point_is_skipped(self):
        """Kuru olmayan bir anda pozisyon toplama katılmaz."""
        candles = service.portfolio_candles(
            [{**holding("MSFT", 1, 400), "currency": "USD"}],
            self._bars({"MSFT": 100.0}),
            rate_at=lambda _c, _m: None,
        )
        assert candles == []


class TestHistoricalFxRate:
    """Kur GEÇMİŞTEN okunur.

    Bütün geçmişi bugünün kuruyla çevirmek, portföyün geçmiş değerini bugünün
    kurunun hikâyesiyle karıştırırdı: geçen yılın dolar pozisyonu geçen yılın
    kuruyla değerlenmeli.
    """

    def _rows(self):
        return [{**holding("MSFT", 10, 400), "currency": "USD"}]

    def test_the_rate_of_that_day_is_used(self):
        history = [
            (NOW - timedelta(days=2), 30.0),
            (NOW - timedelta(days=1), 40.0),
        ]
        rate_at = service._rate_lookup(
            self._rows(), "TRY", lambda _code: history, {"USD": 50.0},
        )
        assert rate_at("USD", NOW - timedelta(days=2)) == pytest.approx(30.0)
        assert rate_at("USD", NOW - timedelta(days=1)) == pytest.approx(40.0)
        # Son kur sonrasında en son bilinen kur taşınır.
        assert rate_at("USD", NOW) == pytest.approx(40.0)

    def test_before_any_historical_rate_it_falls_back_to_today(self):
        history = [(NOW, 40.0)]
        rate_at = service._rate_lookup(
            self._rows(), "TRY", lambda _code: history, {"USD": 50.0},
        )
        assert rate_at("USD", NOW - timedelta(days=5)) == pytest.approx(50.0)

    def test_the_base_currency_needs_no_conversion(self):
        rate_at = service._rate_lookup([holding()], "TRY", None, {})
        assert rate_at("TRY", NOW) == 1.0
        assert rate_at(None, NOW) == 1.0

    def test_with_no_history_the_current_rate_is_used(self):
        rate_at = service._rate_lookup(self._rows(), "TRY", None, {"USD": 45.0})
        assert rate_at("USD", NOW) == pytest.approx(45.0)

    def test_an_unknown_currency_reports_none_rather_than_one(self):
        """1.0 varsaymak 100 doları 100 lira sanmaktır."""
        rate_at = service._rate_lookup(self._rows(), "TRY", None, {})
        assert rate_at("USD", NOW) is None

    def test_a_point_with_no_rate_is_left_out_of_the_trend(self):
        result = build(
            holdings=[
                holding("THYAO", 10, 300),
                {**holding("MSFT", 10, 400), "currency": "USD"},
            ],
            closes_for=closes({"THYAO": 300.0, "MSFT": 400.0}),
            rates={"TRY": 1.0, "USD": 40.0},
            fx_closes_for=lambda _code: [],
        )
        # THYAO 3000 + MSFT 10 x 400 x 40 = 163.000
        assert result["trend"][-1]["value"] == pytest.approx(163_000.0)


class TestPointsWithNothingToPrice:
    """Fiyatlanamayan bir an, sıfır değerli bir portföy DEĞİLDİR."""

    def test_a_trend_point_with_no_rate_anywhere_is_skipped(self):
        """Tek pozisyonun kuru o anda bilinmiyorsa nokta hiç yazılmaz;
        sıfır yazmak portföyün o an yok olduğunu söylemek olurdu."""
        rows = [{**holding("MSFT", 10, 400), "currency": "USD"}]
        trend, _ = service._trend(
            rows, closes({"MSFT": 400.0}), rate_at=lambda _c, _m: None,
        )
        assert trend == []

    def test_a_point_before_every_position_opened_is_skipped(self):
        rows = [holding("THYAO", 10, 300)]
        rows[0]["opened_at"] = NOW
        trend, _ = service._trend(rows, closes({"THYAO": 300.0}))
        # Yalnızca açılış anındaki nokta kalır; öncesi portföy değil.
        assert len(trend) == 1

    def test_a_candle_bucket_before_the_position_opened_is_skipped(self):
        rows = [holding("THYAO", 10, 300)]
        rows[0]["opened_at"] = NOW

        def bars(_symbol):
            return [
                (NOW - timedelta(days=2), 100.0, 101.0),
                (NOW, 100.0, 101.0),
                (NOW + timedelta(days=1), 102.0, 103.0),
            ]

        candles = service.portfolio_candles(rows, bars, bucket_seconds=0)
        assert len(candles) == 2


class TestASymbolWithNoBarYet:
    def test_it_contributes_nothing_until_its_first_bar(self):
        """Bir enstrümanın o noktada henüz hiç barı yoksa geriye doğru fiyat
        uydurulmaz; katkısı yoktur."""
        def bars(symbol):
            if symbol == "THYAO":
                return [(NOW + timedelta(hours=n), 100.0, 101.0) for n in range(4)]
            # ASELS yalnızca son iki saatte fiyatlı.
            return [(NOW + timedelta(hours=n), 50.0, 51.0) for n in (2, 3)]

        candles = service.portfolio_candles(
            [holding("THYAO", 1, 300), holding("ASELS", 1, 50)],
            bars,
            bucket_seconds=3600,
        )
        # İlk kovada yalnızca THYAO; sonuncusunda ikisi birden.
        assert candles[0]["close"] == pytest.approx(101.0)
        assert candles[-1]["close"] == pytest.approx(101.0 + 51.0)
