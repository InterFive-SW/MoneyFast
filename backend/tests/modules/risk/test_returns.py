"""Return-series mathematics.

Hand-checked inputs throughout. These are the functions where an off-by-one in
a window or a wrong denominator produces a number that still looks plausible,
so the tests use series whose answers can be worked out on paper.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest

from app.modules.risk import returns

DAY = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestSimpleReturns:
    def test_period_over_period(self):
        assert returns.simple_returns([100, 110, 121]) == pytest.approx([0.1, 0.1])

    def test_a_single_price_yields_no_returns(self):
        assert returns.simple_returns([100]) == []

    def test_non_positive_price_is_skipped_not_divided_by(self):
        """A zero close is bad data. Dividing by it produces an infinity that
        then poisons every downstream statistic."""
        assert returns.simple_returns([100, 0, 50]) == pytest.approx([-1.0])


class TestDispersion:
    def test_sample_stdev_uses_n_minus_one(self):
        # Population stdev of [2,4,4,4,5,5,7,9] is 2.0; sample is ~2.138.
        assert returns.stdev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.138, abs=0.001)

    def test_stdev_of_one_value_is_zero_not_an_error(self):
        assert returns.stdev([0.01]) == 0.0

    def test_volatility_is_annualised_by_root_252(self):
        daily = [0.01, -0.01] * 50
        expected = returns.stdev(daily) * math.sqrt(252)
        assert returns.annualised_volatility(daily) == pytest.approx(expected)

    def test_volatility_needs_two_observations(self):
        assert returns.annualised_volatility([0.01]) is None

    def test_downside_deviation_ignores_gains(self):
        """Only losses count, but the denominator is every observation — the
        standard definition. Dividing by the loss count would make a portfolio
        that rarely loses look more volatile than one that always does."""
        gains_only = [0.01] * 50
        assert returns.downside_deviation(gains_only) == pytest.approx(0.0)
        mixed = [0.01, -0.01] * 25
        assert returns.downside_deviation(mixed) > 0


class TestMaxDrawdown:
    def test_finds_the_deepest_decline(self):
        result = returns.max_drawdown([100, 120, 60, 90])
        assert result["value"] == pytest.approx(-0.5)

    def test_reports_peak_and_trough_dates(self):
        stamps = [DAY + timedelta(days=i) for i in range(4)]
        result = returns.max_drawdown([100, 120, 60, 90], stamps)
        assert result["peak_date"] == "2026-01-02"
        assert result["trough_date"] == "2026-01-03"

    def test_recovery_date_is_none_when_never_recovered(self):
        """Meaningfully different from "recovered today"; filling it in with
        the last date would claim a recovery that never happened."""
        stamps = [DAY + timedelta(days=i) for i in range(4)]
        assert returns.max_drawdown([100, 120, 60, 90], stamps)["recovery_date"] is None

    def test_recovery_date_is_reported_when_regained(self):
        stamps = [DAY + timedelta(days=i) for i in range(5)]
        result = returns.max_drawdown([100, 120, 60, 90, 130], stamps)
        assert result["recovery_date"] == "2026-01-05"

    def test_a_monotonic_rise_has_no_drawdown(self):
        assert returns.max_drawdown([100, 110, 120]) is None


class TestValueAtRisk:
    def test_historical_var_is_the_empirical_quantile(self):
        series = [i / 1000 - 0.05 for i in range(100)]  # -0.05 .. 0.049
        var = returns.historical_var(series, 0.95)
        assert var == pytest.approx(-0.045, abs=0.002)

    def test_cvar_is_at_least_as_severe_as_var(self):
        """Expected shortfall averages the tail beyond the threshold, so it
        can never be milder than the threshold itself."""
        series = [i / 1000 - 0.05 for i in range(100)]
        assert returns.conditional_var(series, 0.95) <= returns.historical_var(series, 0.95)

    def test_var_needs_a_usable_sample(self):
        assert returns.historical_var([0.01] * 5) is None
        assert returns.conditional_var([0.01] * 5) is None

    def test_parametric_var_uses_the_confidence_z_score(self):
        series = [0.001 * (-1) ** i for i in range(100)]
        strict = returns.parametric_var(series, 0.99)
        loose = returns.parametric_var(series, 0.90)
        assert strict < loose, "a higher confidence must imply a worse loss"


class TestRelativeMetrics:
    def test_beta_of_a_series_against_itself_is_one(self):
        series = [0.01, -0.02, 0.03, -0.01] * 10
        assert returns.beta(series, series) == pytest.approx(1.0)

    def test_beta_is_none_when_the_benchmark_never_moves(self):
        """Returning 0.0 would claim the asset is uncorrelated rather than
        that the question cannot be answered."""
        assert returns.beta([0.01, 0.02], [0.0, 0.0]) is None

    def test_correlation_of_a_series_with_itself_is_one(self):
        series = [0.01, -0.02, 0.03, -0.01] * 10
        assert returns.correlation(series, series) == pytest.approx(1.0)

    def test_correlation_of_an_inverted_series_is_minus_one(self):
        series = [0.01, -0.02, 0.03, -0.01] * 10
        assert returns.correlation(series, [-x for x in series]) == pytest.approx(-1.0)

    def test_correlation_is_none_when_one_side_is_flat(self):
        assert returns.correlation([0.01, 0.02], [0.0, 0.0]) is None


class TestSharpe:
    def test_excess_return_over_volatility(self):
        series = [0.001] * 252
        # Zero volatility on a constant series, so the ratio is undefined.
        assert returns.sharpe(series, 0.0) is None

    def test_a_higher_risk_free_rate_lowers_the_ratio(self):
        series = [0.002, -0.001] * 126
        assert returns.sharpe(series, 0.40) < returns.sharpe(series, 0.10)


#: Five consecutive days, oldest first, as the candle reader hands them over.
def _bars(prices, start_day=5):
    return [
        (datetime(2026, 8, start_day + i, 18, 0, tzinfo=timezone.utc), price)
        for i, price in enumerate(prices)
    ]


class TestValueSeries:
    """The single portfolio series both `risk` and `analytics` read.

    It replaced `portfolio_returns`, which lined constituents up by tail
    INDEX. That is only correct when every holding traded on exactly the same
    days, and measured against live data they do not: XU100 was missing four
    days the holdings had, which put every earlier observation against the
    wrong day and produced a beta of 0.0062 against the index a 94%-DOAS
    portfolio actually tracks closely.
    """

    def test_value_follows_the_holdings(self):
        holdings = [{"symbol": "A", "market_value": 100.0, "instrument_currency": "TRY"}]
        dates, values, excluded = returns.value_series(
            holdings, lambda s: _bars([100.0, 110.0, 120.0])
        )
        assert len(dates) == 3
        assert excluded == []
        # Carried as market value scaled by its own price index, so the LAST
        # day reproduces the holding's current value exactly.
        assert values[-1] == pytest.approx(100.0)
        assert values[0] == pytest.approx(100.0 * (100.0 / 120.0))

    def test_only_days_every_holding_traded_are_used(self):
        """A date one name is missing is dropped for everyone.

        Carrying its previous close forward would move the portfolio on a day
        that name did not trade.
        """
        def reader(symbol):
            return _bars([10.0, 11.0, 12.0, 13.0]) if symbol == "A" else _bars([5.0, 5.5, 6.0], 6)

        dates, values, _ = returns.value_series(
            [
                {"symbol": "A", "market_value": 100.0},
                {"symbol": "B", "market_value": 100.0},
            ],
            reader,
        )
        # A covers the 5th-8th, B the 6th-8th. The shared span is three days.
        assert len(dates) == 3
        assert dates[0].isoformat() == "2026-08-06"

    def test_alignment_is_by_date_not_by_position(self):
        """The regression this whole builder exists for.

        Both series are four bars long, but B is missing the 6th and has the
        9th instead. Index alignment would pair the 5th with the 5th and then
        silently pair the 7th with the 8th. Date alignment keeps only the days
        both actually have.
        """
        def reader(symbol):
            if symbol == "A":
                return _bars([10.0, 11.0, 12.0, 13.0])
            return [
                (datetime(2026, 8, d, 18, 0, tzinfo=timezone.utc), p)
                for d, p in [(5, 5.0), (7, 6.0), (8, 7.0), (9, 8.0)]
            ]

        dates, _, _ = returns.value_series(
            [{"symbol": "A", "market_value": 1.0}, {"symbol": "B", "market_value": 1.0}],
            reader,
        )
        assert [d.day for d in dates] == [5, 7, 8]

    def test_a_foreign_holding_is_converted_at_each_day_rate(self):
        """`analytics` summed price x quantity with no conversion, adding
        dollars to lira. Every day is converted at THAT day's rate; a day
        without a rate is dropped rather than valued at an invented one."""
        def reader(symbol):
            if symbol == "USD":
                return _bars([10.0, 10.0, 10.0])
            return _bars([30.0, 40.0, 50.0])  # USDTRY

        dates, values, _ = returns.value_series(
            [{"symbol": "USD", "market_value": 500.0, "instrument_currency": "USD"}],
            reader,
        )
        assert len(dates) == 3
        # Price flat, rate up 30 -> 50: in lira the holding rose by the rate.
        assert values[0] == pytest.approx(500.0 * (300.0 / 500.0))
        assert values[-1] == pytest.approx(500.0)

    def test_the_rate_series_is_fetched_once_per_currency(self):
        """Six Nasdaq holdings should cost one USDTRY read, not six.

        `closes_for` is a database call per invocation, so a cache miss per
        holding turns a page load into a query storm on exactly the portfolios
        that hold the most names.
        """
        calls: list[str] = []

        def reader(symbol):
            calls.append(symbol)
            if symbol == "USDTRY":
                return _bars([30.0, 31.0, 32.0])
            return _bars([10.0, 11.0, 12.0])

        returns.value_series(
            [
                {"symbol": "AAPL", "market_value": 100.0, "instrument_currency": "USD"},
                {"symbol": "MSFT", "market_value": 100.0, "instrument_currency": "USD"},
                {"symbol": "NVDA", "market_value": 100.0, "instrument_currency": "USD"},
            ],
            reader,
        )
        assert calls.count("USDTRY") == 1

    def test_a_holding_whose_rate_is_missing_is_excluded_not_assumed(self):
        def reader(symbol):
            return [] if symbol == "GBPTRY" else _bars([10.0, 11.0, 12.0])

        _, _, excluded = returns.value_series(
            [{"symbol": "GBX", "market_value": 100.0, "instrument_currency": "GBP"}],
            reader,
        )
        assert excluded == ["GBX"]

    def test_a_thin_history_is_excluded_and_named(self):
        _, _, excluded = returns.value_series(
            [{"symbol": "NEW", "market_value": 100.0}], lambda s: _bars([10.0, 11.0])
        )
        assert excluded == ["NEW"]

    def test_a_worthless_holding_is_skipped_without_being_blamed(self):
        """It contributes nothing either way, and letting its trading days
        constrain the shared window would shorten the series for every other
        holding on account of a position worth zero."""
        def reader(symbol):
            return _bars([10.0, 11.0, 12.0]) if symbol == "A" else _bars([1.0, 1.0], 9)

        dates, _, excluded = returns.value_series(
            [
                {"symbol": "A", "market_value": 100.0},
                {"symbol": "EMPTY", "market_value": 0.0},
            ],
            reader,
        )
        assert excluded == []
        assert len(dates) == 3

    def test_non_positive_closes_are_dropped(self):
        """A zero close produces an infinite return that poisons everything
        downstream."""
        dates, _, _ = returns.value_series(
            [{"symbol": "A", "market_value": 100.0}],
            lambda s: _bars([10.0, 0.0, 12.0, 13.0]),
        )
        assert len(dates) == 3

    def test_no_holdings_is_safe(self):
        assert returns.value_series([], lambda s: []) == ([], [], [])

    def test_a_single_shared_day_is_not_a_series(self):
        def reader(symbol):
            return _bars([10.0, 11.0, 12.0]) if symbol == "A" else _bars([5.0, 6.0, 7.0], 7)

        dates, values, _ = returns.value_series(
            [{"symbol": "A", "market_value": 1.0}, {"symbol": "B", "market_value": 1.0}],
            reader,
        )
        assert (dates, values) == ([], [])


class TestRebalancedReturns:
    """DAILY_REBALANCE really is a different portfolio.

    The contract offers two rebalancing assumptions and the parameter was
    accepted, echoed in `assumptions`, and then ignored -- one fixed
    computation came back under whichever name was asked for.
    """

    def test_weights_reset_each_day(self):
        """Two equal holdings, one doubling and one flat.

        Rebalanced, each day's return is the average of the constituents'.
        Buy-and-hold lets the winner's weight grow, so the two series differ.
        """
        def reader(symbol):
            return _bars([10.0, 20.0, 40.0]) if symbol == "UP" else _bars([10.0, 10.0, 10.0])

        holdings = [
            {"symbol": "UP", "market_value": 100.0},
            {"symbol": "FLAT", "market_value": 100.0},
        ]
        rebalanced = returns.rebalanced_returns(holdings, reader)
        # Each day UP returns +100%, FLAT 0%: the average is +50%.
        assert rebalanced == pytest.approx([0.5, 0.5])

        _, values, _ = returns.value_series(holdings, reader)
        assert returns.simple_returns(values) != pytest.approx(rebalanced)

    def test_weighted_by_market_value_not_headcount(self):
        def reader(symbol):
            return _bars([10.0, 20.0, 40.0]) if symbol == "UP" else _bars([10.0, 10.0, 10.0])

        rebalanced = returns.rebalanced_returns(
            [
                {"symbol": "UP", "market_value": 300.0},
                {"symbol": "FLAT", "market_value": 100.0},
            ],
            reader,
        )
        assert rebalanced == pytest.approx([0.75, 0.75])

    def test_only_shared_days_are_used(self):
        def reader(symbol):
            return _bars([10.0, 11.0, 12.0, 13.0]) if symbol == "A" else _bars([5.0, 6.0, 7.0], 6)

        rebalanced = returns.rebalanced_returns(
            [{"symbol": "A", "market_value": 1.0}, {"symbol": "B", "market_value": 1.0}],
            reader,
        )
        # Three shared days give two returns.
        assert len(rebalanced) == 2

    def test_no_history_is_no_series(self):
        assert returns.rebalanced_returns([], lambda s: []) == []

    def test_too_few_shared_days_is_no_series(self):
        def reader(symbol):
            return _bars([10.0, 11.0, 12.0]) if symbol == "A" else _bars([5.0, 6.0, 7.0], 7)

        assert returns.rebalanced_returns(
            [{"symbol": "A", "market_value": 1.0}, {"symbol": "B", "market_value": 1.0}],
            reader,
        ) == []

    def test_a_worthless_portfolio_yields_no_series(self):
        """A holding worth nothing is skipped before it can be weighted, so
        an all-zero portfolio has no constituents rather than a zero divisor."""
        assert returns.rebalanced_returns(
            [{"symbol": "A", "market_value": 0.0}], lambda s: _bars([10.0, 11.0, 12.0])
        ) == []


class TestPairedReturns:
    def test_pairs_only_days_both_sides_have(self):
        dates = [date(2026, 8, d) for d in (5, 6, 7, 8)]
        values = [100.0, 101.0, 102.0, 103.0]
        # The benchmark is missing the 6th -- exactly XU100's real defect.
        bars = [
            (datetime(2026, 8, d, 18, 0, tzinfo=timezone.utc), p)
            for d, p in [(5, 10.0), (7, 10.5), (8, 10.8)]
        ]
        left, right = returns.paired_returns(dates, values, bars)
        assert len(left) == len(right) == 2
        # The portfolio return for the 7th is measured from the 5th, because
        # that is the previous day the pair actually shares.
        assert left[0] == pytest.approx(102.0 / 100.0 - 1)

    def test_too_little_overlap_is_no_pairing(self):
        dates = [date(2026, 8, 5), date(2026, 8, 6)]
        bars = [(datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc), 10.0)]
        assert returns.paired_returns(dates, [1.0, 2.0], bars) == ([], [])


class TestAlignTo:
    def test_returns_closes_on_the_given_days_only(self):
        dates = [date(2026, 8, 5), date(2026, 8, 7)]
        bars = [
            (datetime(2026, 8, d, 18, 0, tzinfo=timezone.utc), p)
            for d, p in [(5, 10.0), (6, 11.0), (7, 12.0)]
        ]
        assert returns.align_to(dates, bars) == [10.0, 12.0]

    def test_no_overlap_is_empty(self):
        assert returns.align_to([date(2026, 1, 1)], []) == []


class TestLookbackWindows:
    @pytest.mark.parametrize("label,days", [("1M", 22), ("6M", 126), ("1Y", 252), ("5Y", 1260)])
    def test_known_windows(self, label, days):
        assert returns.window_for(label) == days

    def test_unknown_window_defaults_to_one_year(self):
        assert returns.window_for("FOREVER") == 252
        assert returns.window_for(None) == 252


class TestDrawdownEdges:
    def test_a_single_price_has_no_drawdown(self):
        assert returns.max_drawdown([100]) is None

    def test_an_empty_series_has_no_drawdown(self):
        assert returns.max_drawdown([]) is None


class TestUndefinedStatistics:
    def test_correlation_of_a_constant_series_is_none(self):
        """Zero variance means the question has no answer; 0.0 would claim
        the series are uncorrelated."""
        assert returns.correlation([0.01] * 10, [0.02] * 10) is None

    def test_covariance_of_a_single_observation_is_zero(self):
        assert returns.covariance([0.01], [0.02]) == 0.0

    def test_sharpe_is_none_without_volatility(self):
        assert returns.sharpe([], 0.4) is None


class TestSmallSamples:
    def test_parametric_var_needs_a_usable_sample(self):
        """Twenty observations is already thin for a tail estimate; fewer is
        not an estimate at all."""
        assert returns.parametric_var([0.01] * 5) is None

