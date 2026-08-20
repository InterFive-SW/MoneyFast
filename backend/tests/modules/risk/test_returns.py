"""Return-series mathematics.

Hand-checked inputs throughout. These are the functions where an off-by-one in
a window or a wrong denominator produces a number that still looks plausible,
so the tests use series whose answers can be worked out on paper.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

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


class TestPortfolioReturns:
    def test_weighted_combination(self):
        series = {"A": [0.10, 0.10], "B": [0.0, 0.0]}
        combined = returns.portfolio_returns(series, {"A": 0.5, "B": 0.5})
        assert combined == pytest.approx([0.05, 0.05])

    def test_truncates_to_the_shortest_history(self):
        """Padding a short series would silently assume the missing days were
        flat, understating the portfolio's volatility."""
        series = {"A": [0.01] * 10, "B": [0.02] * 3}
        assert len(returns.portfolio_returns(series, {"A": 0.5, "B": 0.5})) == 3

    def test_zero_weights_yield_no_series(self):
        assert returns.portfolio_returns({"A": [0.01, 0.02]}, {"A": 0.0}) == []

    def test_empty_input_is_safe(self):
        assert returns.portfolio_returns({}, {}) == []


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

    def test_portfolio_returns_with_all_zero_weights(self):
        assert returns.portfolio_returns({"A": [0.01, 0.02]}, {"A": 0.0, "B": 0.0}) == []


class TestPortfolioReturnsGuards:
    def test_a_negative_total_weight_yields_no_series(self):
        """Short positions can make the weights sum to zero. Dividing by that
        would raise; an empty series says "not measurable" instead."""
        series = {"A": [0.01, 0.02], "B": [0.03, 0.04]}
        assert returns.portfolio_returns(series, {"A": 1.0, "B": -1.0}) == []
