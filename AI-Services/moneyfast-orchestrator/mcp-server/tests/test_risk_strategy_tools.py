"""Unit tests for risk_strategy_tools.

Contract under test: Interface Definitions v2.1,
calculate_portfolio_risk_metrics, now backed by POST /risk/calculate.

Two behaviours get the most attention because both are ways a number reaches
a user with more authority than it has earned: relative metrics surviving
without a benchmark, and a small sample being presented as reliable.
"""

from __future__ import annotations

import httpx
import pytest

import risk_strategy_tools
from backend_client import ContractViolationError, InvalidInputError, UpstreamUnavailableError
from conftest import assert_iso8601_utc, without

pytestmark = pytest.mark.asyncio


# ==========================================================================
# Pre-flight validation
# ==========================================================================
class TestPreflight:
    async def test_empty_positions_raises_before_any_request(self, fake_backend):
        """An empty position set cannot produce a meaningful metric, and the
        contract documents this as InvalidInputError rather than an empty
        result. Failing locally also saves a pointless round trip."""
        with pytest.raises(InvalidInputError, match="positions is empty"):
            await risk_strategy_tools.calculate_portfolio_risk_metrics([])
        assert fake_backend.attempts == 0

    async def test_a_single_position_is_enough(self, fake_backend, sample_positions):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions[:1])
        assert fake_backend.attempts == 1


# ==========================================================================
# Request construction
# ==========================================================================
class TestRequest:
    async def test_posts_to_the_risk_endpoint(self, fake_backend, sample_positions):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert fake_backend.last.method == "POST"
        assert "/risk/calculate" in str(fake_backend.last.url)

    async def test_positions_are_sent_unmodified(self, fake_backend, sample_positions):
        """Weights are recomputed backend-side from market_value, so the tool
        must not pre-normalize."""
        await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert fake_backend.body()["positions"] == sample_positions

    async def test_default_body(self, fake_backend, sample_positions):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        body = fake_backend.body()
        assert body["lookback"] == "1Y"
        assert body["confidence_level"] == 0.95
        assert body["rebalance_assumption"] == "BUY_AND_HOLD"

    async def test_unset_risk_free_rate_is_omitted_not_null(
        self, fake_backend, sample_positions
    ):
        """Omitting the field lets the backend resolve the policy rate and
        report it back; sending null could be read as "use zero"."""
        await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert "risk_free_rate" not in fake_backend.body()

    async def test_zero_risk_free_rate_is_sent(self, fake_backend, sample_positions):
        """0.0 is falsy but is a real rate. Dropping it would silently swap in
        the policy rate and change every Sharpe figure."""
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, risk_free_rate=0.0
        )
        assert fake_backend.body()["risk_free_rate"] == 0.0

    async def test_explicit_arguments_are_forwarded(self, fake_backend, sample_positions):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions,
            lookback="3Y",
            benchmark_symbol="XU100",
            metrics=["VOLATILITY", "BETA"],
            confidence_level=0.99,
            risk_free_rate=0.15,
            rebalance_assumption="DAILY_REBALANCE",
        )
        body = fake_backend.body()
        assert body["lookback"] == "3Y"
        assert body["benchmark_symbol"] == "XU100"
        assert body["metrics"] == ["VOLATILITY", "BETA"]
        assert body["confidence_level"] == 0.99
        assert body["risk_free_rate"] == 0.15
        assert body["rebalance_assumption"] == "DAILY_REBALANCE"

    @pytest.mark.parametrize("lookback", ["1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX"])
    async def test_every_documented_lookback_is_accepted(
        self, fake_backend, sample_positions, lookback
    ):
        payload = await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, lookback=lookback
        )
        assert payload["assumptions"]["lookback"] == lookback


# ==========================================================================
# Happy path
# ==========================================================================
class TestHappyPath:
    async def test_exact_top_level_contract(self, sample_positions, risk_top_level_keys):
        payload = await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert set(payload) == risk_top_level_keys

    async def test_freshness_is_propagated(self, sample_positions):
        payload = await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert_iso8601_utc(payload["as_of"])
        assert payload["source"] == "BIST_EOD"
        assert payload["is_delayed"] is False

    async def test_window_and_metrics_pass_through(self, sample_positions):
        payload = await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, benchmark_symbol="XU100"
        )
        assert payload["window"]["observation_count"] == 249
        assert payload["metrics"]["volatility_annualized"] == 0.3418
        assert payload["metrics"]["max_drawdown"]["recovery_date"] is None

    async def test_unknown_top_level_fields_are_dropped(
        self, fake_backend, risk_payload, sample_positions
    ):
        risk_payload["engine_version"] = "3.1"
        fake_backend.json("risk", risk_payload)
        payload = await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert "engine_version" not in payload


# ==========================================================================
# Benchmark suppression
# ==========================================================================
class TestBenchmarkSuppression:
    async def test_relative_metrics_survive_when_a_benchmark_was_requested(
        self, sample_positions
    ):
        metrics = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(
                sample_positions, benchmark_symbol="XU100"
            )
        )["metrics"]
        assert metrics["beta"] == 1.14
        assert metrics["correlation_to_benchmark"] == 0.81

    async def test_relative_metrics_are_forced_to_none_without_a_benchmark(
        self, sample_positions
    ):
        """The stub backend returns a beta regardless. Trusting it would let a
        default-index beta reach the user as if they had asked for it."""
        metrics = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        )["metrics"]
        assert metrics["beta"] is None
        assert metrics["correlation_to_benchmark"] is None

    async def test_empty_string_benchmark_behaves_like_none(self, sample_positions):
        metrics = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(
                sample_positions, benchmark_symbol=""
            )
        )["metrics"]
        assert metrics["beta"] is None

    async def test_correlation_matrix_is_present_as_none_when_absent(self, sample_positions):
        """Default omits it, but the key must exist so strict consumers do not
        have to distinguish absent from null."""
        metrics = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        )["metrics"]
        assert metrics["correlation_matrix"] is None

    async def test_supplied_correlation_matrix_is_kept(
        self, fake_backend, risk_payload, sample_positions
    ):
        matrix = {"symbols": ["THYAO", "ASELS"], "matrix": [[1.0, 0.4], [0.4, 1.0]]}
        risk_payload["metrics"]["correlation_matrix"] = matrix
        fake_backend.json("risk", risk_payload)
        payload = await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, metrics=["CORRELATION_MATRIX"]
        )
        assert payload["metrics"]["correlation_matrix"] == matrix


# ==========================================================================
# Assumptions
# ==========================================================================
class TestAssumptions:
    async def test_backend_assumptions_are_preserved(self, sample_positions):
        assumptions = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        )["assumptions"]
        assert assumptions["risk_free_rate"] == 0.42
        assert assumptions["annualization_factor"] == 252

    async def test_request_parameters_are_backfilled_when_absent(
        self, fake_backend, risk_payload, sample_positions
    ):
        """These must be disclosed when presenting Sharpe, VaR or CVaR, so the
        tool guarantees they are present even if the backend is terse."""
        risk_payload["assumptions"] = {"risk_free_rate": 0.42}
        fake_backend.json("risk", risk_payload)
        assumptions = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(
                sample_positions,
                lookback="5Y",
                benchmark_symbol="XU100",
                metrics=["SHARPE"],
                rebalance_assumption="DAILY_REBALANCE",
            )
        )["assumptions"]
        assert assumptions["lookback"] == "5Y"
        assert assumptions["benchmark_symbol"] == "XU100"
        assert assumptions["requested_metrics"] == ["SHARPE"]
        assert assumptions["rebalance_assumption"] == "DAILY_REBALANCE"

    async def test_backend_values_win_over_the_backfill(
        self, fake_backend, risk_payload, sample_positions
    ):
        """If the engine actually used a different window, its word wins: the
        block documents what shaped the result, not what was asked for."""
        risk_payload["assumptions"]["lookback"] = "3Y"
        fake_backend.json("risk", risk_payload)
        assumptions = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(
                sample_positions, lookback="1Y"
            )
        )["assumptions"]
        assert assumptions["lookback"] == "3Y"

    async def test_missing_risk_free_rate_is_a_violation(
        self, fake_backend, risk_payload, sample_positions
    ):
        """Sharpe is uninterpretable without the rate it was computed against,
        and the contract requires that rate to be disclosed."""
        del risk_payload["assumptions"]["risk_free_rate"]
        fake_backend.json("risk", risk_payload)
        with pytest.raises(ContractViolationError, match="risk_free_rate"):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)

    async def test_explicit_null_risk_free_rate_is_accepted(
        self, fake_backend, risk_payload, sample_positions
    ):
        """Present-but-null is a statement; absent is silence."""
        risk_payload["assumptions"]["risk_free_rate"] = None
        fake_backend.json("risk", risk_payload)
        payload = await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert payload["assumptions"]["risk_free_rate"] is None


# ==========================================================================
# Data quality
# ==========================================================================
class TestDataQuality:
    async def test_block_is_complete_and_typed(self, sample_positions):
        quality = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        )["data_quality"]
        assert set(quality) == {
            "coverage", "excluded_symbols", "gap_filled_days", "is_statistically_reliable",
        }
        assert quality["coverage"] == 1.0
        assert quality["is_statistically_reliable"] is True

    async def test_reliability_defaults_to_false_when_unstated(
        self, fake_backend, risk_payload, sample_positions
    ):
        """The optimistic default would let a three-observation window be
        presented as a firm volatility figure."""
        risk_payload["data_quality"] = {"coverage": 0.4}
        fake_backend.json("risk", risk_payload)
        quality = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        )["data_quality"]
        assert quality["is_statistically_reliable"] is False
        assert quality["coverage"] == 0.4
        assert quality["excluded_symbols"] == []
        assert quality["gap_filled_days"] == 0

    async def test_coverage_defaults_to_zero_when_unstated(
        self, fake_backend, risk_payload, sample_positions
    ):
        """Zero coverage forces the orchestrator to caveat, which is the safe
        direction to fail."""
        risk_payload["data_quality"] = {}
        fake_backend.json("risk", risk_payload)
        quality = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        )["data_quality"]
        assert quality["coverage"] == 0.0

    async def test_excluded_symbols_pass_through(
        self, fake_backend, risk_payload, sample_positions
    ):
        risk_payload["data_quality"]["excluded_symbols"] = ["NEWCO"]
        fake_backend.json("risk", risk_payload)
        quality = (
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        )["data_quality"]
        assert quality["excluded_symbols"] == ["NEWCO"]

    @pytest.mark.parametrize("bad", ["fine", 1.0, [], None])
    async def test_non_object_data_quality_is_a_violation(
        self, fake_backend, risk_payload, sample_positions, bad
    ):
        risk_payload["data_quality"] = bad
        fake_backend.json("risk", risk_payload)
        with pytest.raises(ContractViolationError, match="data_quality"):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)


# ==========================================================================
# Contract guards
# ==========================================================================
class TestContractGuards:
    @pytest.mark.parametrize("missing", ["as_of", "source", "is_delayed"])
    async def test_missing_freshness_field_is_a_violation(
        self, fake_backend, risk_payload, sample_positions, missing
    ):
        fake_backend.json("risk", without(risk_payload, missing))
        with pytest.raises(ContractViolationError):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)

    @pytest.mark.parametrize("missing", ["window", "metrics", "assumptions", "data_quality"])
    async def test_missing_top_level_block_is_a_violation(
        self, fake_backend, risk_payload, sample_positions, missing
    ):
        fake_backend.json("risk", without(risk_payload, missing))
        with pytest.raises(ContractViolationError, match=missing):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)

    @pytest.mark.parametrize("bad", ["metrics", 42, [], None])
    async def test_non_object_metrics_is_a_violation(
        self, fake_backend, risk_payload, sample_positions, bad
    ):
        risk_payload["metrics"] = bad
        fake_backend.json("risk", risk_payload)
        with pytest.raises(ContractViolationError, match="must be an object"):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)


# ==========================================================================
# Failure propagation
# ==========================================================================
class TestFailures:
    async def test_insufficient_history_raises_invalid_input(
        self, fake_backend, sample_positions
    ):
        """Contract: do NOT silently fall back to a shorter window."""
        fake_backend.status("risk", 422, {"error": "InsufficientHistoryError"})
        with pytest.raises(InvalidInputError):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(
                sample_positions, lookback="5Y"
            )

    async def test_metric_engine_outage_raises(self, fake_backend, sample_positions):
        fake_backend.status("risk", 500)
        with pytest.raises(UpstreamUnavailableError):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)

    async def test_timeout_raises_upstream_unavailable(self, fake_backend, sample_positions):
        fake_backend.fail("risk", httpx.ReadTimeout("engine slow"))
        with pytest.raises(UpstreamUnavailableError):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)


# ==========================================================================
# Registration
# ==========================================================================
class TestRegistration:
    async def test_register_attaches_the_tool(self, mocker):
        fake_mcp = mocker.MagicMock()
        risk_strategy_tools.register(fake_mcp)
        fake_mcp.tool.assert_called_once_with()
        fake_mcp.tool.return_value.assert_called_once_with(
            risk_strategy_tools.calculate_portfolio_risk_metrics
        )

    async def test_the_tool_is_a_coroutine_function(self):
        import inspect

        assert inspect.iscoroutinefunction(
            risk_strategy_tools.calculate_portfolio_risk_metrics
        )
