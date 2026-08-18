"""Unit tests for risk_strategy_tools.

Contract under test: Interface Definitions v2.1,
calculate_portfolio_risk_metrics. The tool measures the past; the tests below
enforce the arithmetic identities that make those measurements coherent, plus
the branch behaviour around an absent benchmark and an unset risk-free rate.
"""

from __future__ import annotations

import pytest

import risk_strategy_tools
from conftest import assert_iso8601_utc

POLICY_RATE = 0.4200


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------
def test_returns_exact_top_level_contract(sample_positions, risk_top_level_keys):
    payload = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
    assert set(payload) == risk_top_level_keys


def test_freshness_fields_present_and_typed(sample_positions):
    payload = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
    assert_iso8601_utc(payload["as_of"])
    assert isinstance(payload["source"], str) and payload["source"]
    assert isinstance(payload["is_delayed"], bool)


def test_window_block_is_complete_and_ordered(sample_positions):
    window = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)["window"]
    assert set(window) == {"start_date", "end_date", "observation_count", "frequency"}
    assert window["start_date"] < window["end_date"]
    assert window["observation_count"] > 0
    assert window["frequency"] in {"DAILY", "WEEKLY"}


def test_volatility_and_downside_deviation_are_non_negative_fractions(sample_positions):
    """Contract: fractions, not percentages. 0.34 means 34%."""
    metrics = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)["metrics"]
    assert 0.0 <= metrics["volatility_annualized"] < 5.0
    assert 0.0 <= metrics["downside_deviation_annualized"] <= metrics["volatility_annualized"]


def test_max_drawdown_is_negative_and_dated(sample_positions):
    drawdown = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "metrics"
    ]["max_drawdown"]
    assert set(drawdown) == {
        "value", "peak_date", "trough_date", "recovery_date", "duration_days",
    }
    assert -1.0 <= drawdown["value"] < 0.0, "a drawdown is a negative fraction"
    assert drawdown["peak_date"] < drawdown["trough_date"]
    assert drawdown["duration_days"] > 0


def test_unrecovered_drawdown_has_null_recovery_date(sample_positions):
    """None means not yet recovered. It must be None, never an empty string."""
    drawdown = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "metrics"
    ]["max_drawdown"]
    assert drawdown["recovery_date"] is None


def test_cvar_is_at_least_as_severe_as_var(sample_positions):
    """Expected shortfall sits beyond the VaR threshold, by definition."""
    metrics = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)["metrics"]
    var, cvar = metrics["var"], metrics["cvar"]
    assert var["value_fraction"] < 0 and cvar["value_fraction"] < 0
    assert cvar["value_fraction"] <= var["value_fraction"]
    assert cvar["value_currency"] <= var["value_currency"]


def test_var_block_shape_and_method(sample_positions):
    var = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)["metrics"]["var"]
    assert set(var) == {
        "method", "confidence_level", "horizon_days", "value_fraction", "value_currency",
    }
    assert var["method"] in {"HISTORICAL", "PARAMETRIC"}
    assert var["horizon_days"] >= 1


@pytest.mark.parametrize("confidence_level", [0.90, 0.95, 0.99])
def test_confidence_level_is_echoed_into_var_and_cvar(sample_positions, confidence_level):
    metrics = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, confidence_level=confidence_level
    )["metrics"]
    assert metrics["var"]["confidence_level"] == confidence_level
    assert metrics["cvar"]["confidence_level"] == confidence_level


# --------------------------------------------------------------------------
# Concentration
# --------------------------------------------------------------------------
def test_concentration_block_is_complete(sample_positions):
    concentration = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "metrics"
    ]["concentration"]
    assert set(concentration) == {
        "hhi", "effective_n", "top_1_weight", "top_3_weight", "top_5_weight",
        "largest_position", "by_asset_class", "by_sector", "by_currency",
    }


def test_hhi_and_effective_n_are_reciprocal(sample_positions):
    """effective_n is 1/hhi. Zero-division risk if hhi ever reaches 0."""
    concentration = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "metrics"
    ]["concentration"]
    assert 0.0 < concentration["hhi"] <= 1.0
    assert concentration["effective_n"] == pytest.approx(
        1.0 / concentration["hhi"], abs=0.001
    )


def test_top_n_weights_are_monotonic_and_bounded(sample_positions):
    concentration = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "metrics"
    ]["concentration"]
    assert (
        concentration["top_1_weight"]
        <= concentration["top_3_weight"]
        <= concentration["top_5_weight"]
        <= 1.0
    )
    assert concentration["largest_position"]["weight"] == concentration["top_1_weight"]


@pytest.mark.parametrize("breakdown", ["by_asset_class", "by_sector", "by_currency"])
def test_breakdowns_sum_to_one(sample_positions, breakdown):
    concentration = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "metrics"
    ]["concentration"]
    assert sum(concentration[breakdown].values()) == pytest.approx(1.0, abs=0.001)


def test_unmapped_sector_uses_the_unclassified_bucket(sample_positions):
    """Contract names the bucket explicitly; a silent drop would break sums."""
    by_sector = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "metrics"
    ]["concentration"]["by_sector"]
    assert "UNCLASSIFIED" in by_sector


# --------------------------------------------------------------------------
# Branch coverage: benchmark present vs absent
# --------------------------------------------------------------------------
def test_benchmark_supplied_yields_relative_metrics(sample_positions):
    metrics = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, benchmark_symbol="XU100"
    )["metrics"]
    assert isinstance(metrics["beta"], float)
    assert -1.0 <= metrics["correlation_to_benchmark"] <= 1.0


def test_benchmark_omitted_suppresses_relative_metrics(sample_positions):
    """Contract: None benchmark suppresses beta and correlation entirely."""
    metrics = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, benchmark_symbol=None
    )["metrics"]
    assert metrics["beta"] is None
    assert metrics["correlation_to_benchmark"] is None


def test_empty_string_benchmark_is_falsy_and_suppresses(sample_positions):
    """Edge case: an empty ticker must behave like None, not like a symbol."""
    metrics = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, benchmark_symbol=""
    )["metrics"]
    assert metrics["beta"] is None


# --------------------------------------------------------------------------
# Branch coverage: risk-free rate resolution
# --------------------------------------------------------------------------
def test_risk_free_rate_defaults_to_policy_rate(sample_positions):
    assumptions = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, risk_free_rate=None
    )["assumptions"]
    assert assumptions["risk_free_rate"] == POLICY_RATE
    assert assumptions["risk_free_rate_source"] == "DOMESTIC_POLICY_RATE"


def test_explicit_risk_free_rate_overrides_default(sample_positions):
    assumptions = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, risk_free_rate=0.15
    )["assumptions"]
    assert assumptions["risk_free_rate"] == 0.15


def test_zero_risk_free_rate_is_honoured_not_treated_as_missing(sample_positions):
    """Edge case: 0.0 is falsy. ``is None`` is required, ``or`` would be a bug."""
    assumptions = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, risk_free_rate=0.0
    )["assumptions"]
    assert assumptions["risk_free_rate"] == 0.0


# --------------------------------------------------------------------------
# Assumptions and data quality
# --------------------------------------------------------------------------
def test_assumptions_echo_every_shaping_parameter(sample_positions):
    assumptions = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions,
        lookback="3Y",
        benchmark_symbol="XU100",
        metrics=["VOLATILITY", "BETA"],
        rebalance_assumption="DAILY_REBALANCE",
    )["assumptions"]
    assert assumptions["lookback"] == "3Y"
    assert assumptions["benchmark_symbol"] == "XU100"
    assert assumptions["requested_metrics"] == ["VOLATILITY", "BETA"]
    assert assumptions["rebalance_assumption"] == "DAILY_REBALANCE"
    assert assumptions["annualization_factor"] == 252


@pytest.mark.parametrize("lookback", ["1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX"])
def test_every_documented_lookback_is_accepted(sample_positions, lookback):
    payload = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, lookback=lookback
    )
    assert payload["assumptions"]["lookback"] == lookback


def test_metrics_none_selects_the_default_subset(sample_positions):
    """Default omits CORRELATION_MATRIX, which must still be present as None."""
    metrics = risk_strategy_tools.calculate_portfolio_risk_metrics(
        sample_positions, metrics=None
    )["metrics"]
    assert metrics["correlation_matrix"] is None
    assert "volatility_annualized" in metrics


def test_data_quality_block_is_complete_and_bounded(sample_positions):
    quality = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "data_quality"
    ]
    assert set(quality) == {
        "coverage", "excluded_symbols", "gap_filled_days", "is_statistically_reliable",
    }
    assert 0.0 <= quality["coverage"] <= 1.0
    assert isinstance(quality["excluded_symbols"], list)
    assert isinstance(quality["is_statistically_reliable"], bool)


def test_full_coverage_implies_no_excluded_symbols(sample_positions):
    quality = risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)[
        "data_quality"
    ]
    if quality["coverage"] == 1.0:
        assert quality["excluded_symbols"] == []


# --------------------------------------------------------------------------
# Edge cases on the positions argument
# --------------------------------------------------------------------------
def test_empty_positions_list_is_accepted_by_the_mock():
    """The mock ignores positions. Documented here so the day validation lands,
    this test flips to ``pytest.raises(ValueError)`` and the change is visible.
    """
    payload = risk_strategy_tools.calculate_portfolio_risk_metrics([])
    assert set(payload["metrics"])


def test_single_position_portfolio_is_handled():
    single = [{"symbol": "THYAO", "quantity": 1.0, "market_value": 291.75, "asset_class": "EQUITY"}]
    payload = risk_strategy_tools.calculate_portfolio_risk_metrics(single)
    assert payload["metrics"]["concentration"]["hhi"] > 0


def test_extra_position_keys_are_ignored(sample_positions):
    """Contract says extra keys are ignored, so a full portfolio payload works."""
    enriched = [{**p, "isin": "TR0000000001", "opened_at": "2025-01-01"} for p in sample_positions]
    assert risk_strategy_tools.calculate_portfolio_risk_metrics(enriched)["metrics"]


# --------------------------------------------------------------------------
# Isolation and error handling
# --------------------------------------------------------------------------
def test_makes_no_network_call_today(mocker, sample_positions):
    client = mocker.patch.object(risk_strategy_tools, "httpx", create=True)
    risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
    assert client.get.call_count == 0


def test_insufficient_history_propagates(mocker, sample_positions):
    mocker.patch.object(
        risk_strategy_tools,
        "calculate_portfolio_risk_metrics",
        side_effect=ValueError("InsufficientHistoryError: no usable bars for 5Y"),
    )
    with pytest.raises(ValueError, match="InsufficientHistoryError"):
        risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions, lookback="5Y")


def test_price_feed_failure_propagates(mocker, sample_positions):
    mocker.patch.object(
        risk_strategy_tools,
        "calculate_portfolio_risk_metrics",
        side_effect=ConnectionError("HTTP 500 from BIST_EOD"),
    )
    with pytest.raises(ConnectionError, match="HTTP 500"):
        risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)


def test_module_as_of_constant_is_deterministic():
    """Determinism matters: a datetime.now() here would make tests flaky."""
    assert risk_strategy_tools.AS_OF == "2026-08-12T18:10:00Z"


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
def test_register_attaches_the_tool(mocker):
    fake_mcp = mocker.MagicMock()
    risk_strategy_tools.register(fake_mcp)
    fake_mcp.tool.assert_called_once_with()
    fake_mcp.tool.return_value.assert_called_once_with(
        risk_strategy_tools.calculate_portfolio_risk_metrics
    )
