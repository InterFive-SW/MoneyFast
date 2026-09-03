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
from backend_client import (
    AuthorizationError,
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)
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
    async def test_register_attaches_both_tools(self, mocker):
        fake_mcp = mocker.MagicMock()
        risk_strategy_tools.register(fake_mcp)
        assert fake_mcp.tool.call_count == 2
        registered = [
            call.args[0] for call in fake_mcp.tool.return_value.call_args_list
        ]
        assert registered == [
            risk_strategy_tools.calculate_portfolio_risk_metrics,
            risk_strategy_tools.get_risk_profile_summary,
        ]

    async def test_the_tools_are_coroutine_functions(self):
        import inspect

        assert inspect.iscoroutinefunction(
            risk_strategy_tools.calculate_portfolio_risk_metrics
        )
        assert inspect.iscoroutinefunction(
            risk_strategy_tools.get_risk_profile_summary
        )


# ==========================================================================
# get_risk_profile_summary -- the interpreted layer.
#
# calculate_portfolio_risk_metrics returns statistics and no score. The score
# and the band exist only behind GET /risk/profile/{user_id}, so before this
# tool the assistant answered "how risky is my portfolio" with a volatility
# percentage while the risk page answered with a 0-100 score. Whatever this
# tool passes through is what the user is told, which is why the guards below
# are strict about nulls and about the alignment enum.
# ==========================================================================
SUMMARY = risk_strategy_tools.get_risk_profile_summary


class TestSummaryPreflight:
    async def test_a_missing_user_id_raises_before_any_request(self, fake_backend):
        with pytest.raises(InvalidInputError, match="user_id is required"):
            await SUMMARY("")
        assert fake_backend.attempts == 0


class TestSummaryRequest:
    async def test_gets_the_user_scoped_profile_endpoint(self, fake_backend):
        await SUMMARY("usr_9001")
        assert fake_backend.last.method == "GET"
        assert "/risk/profile/usr_9001" in str(fake_backend.last.url)

    async def test_lookback_defaults_to_the_window_the_page_shows(self, fake_backend):
        await SUMMARY("usr_9001")
        assert fake_backend.last.url.params["lookback"] == "1Y"

    async def test_an_explicit_lookback_is_passed_through(self, fake_backend):
        await SUMMARY("usr_9001", lookback="3M")
        assert fake_backend.last.url.params["lookback"] == "3M"

    async def test_a_null_lookback_falls_back_rather_than_omitting(self, fake_backend):
        """None would be dropped by `clean`, and the backend would apply its
        own default -- which is the same value, but silently. Sending it keeps
        the window the tool reported and the window used identical."""
        await SUMMARY("usr_9001", lookback=None)
        assert fake_backend.last.url.params["lookback"] == "1Y"


class TestSummaryPayload:
    async def test_top_level_shape(self, fake_backend):
        out = await SUMMARY("usr_9001")
        assert set(out) == {
            "as_of", "score", "level", "position_count", "suitability",
            # v2.17: ölçüm ile kullanıcının kendi beyanının iki
            # karşılaştırması daha -- ürün grubu beyanı ve kendi girdiği
            # hedef ağırlıklar.
            "group_exposure", "allocation_drift",
            "declared", "metrics", "findings", "data_quality", "warnings",
        }

    async def test_a_backend_without_the_new_blocks_still_passes(self, fake_backend):
        """Sözleşme yalnızca EKLEMELİ değişiyor: iki alan `require`
        listesinde DEĞİL, dolayısıyla onları taşımayan bir yanıt hâlâ
        geçerli. Yokluk None -- "hiç gelmedi" ile "hedef yok" farklı."""
        out = await SUMMARY("usr_9001")
        assert out["group_exposure"] is None or isinstance(out["group_exposure"], dict)

    async def test_the_new_blocks_travel_when_present(
        self, fake_backend, risk_summary_payload
    ):
        fake_backend.json("risk_summary", {
            **risk_summary_payload,
            "allocation_drift": {"has_target": True, "total_value": 100.0,
                                 "buckets": [], "statement": "Hedefin üzerinde."},
            "group_exposure": {"assessed": True, "total_value": 100.0, "groups": []},
        })
        out = await SUMMARY("usr_9001")
        assert out["allocation_drift"]["statement"] == "Hedefin üzerinde."
        assert out["group_exposure"]["assessed"] is True

    async def test_the_score_and_band_survive_intact(self, fake_backend):
        out = await SUMMARY("usr_9001")
        assert out["score"] == pytest.approx(83.4)
        assert out["level"] == "Düşük"

    async def test_the_comparison_sentence_is_relayed_verbatim(self, fake_backend):
        """The wording is built backend-side, on purpose: it is the one place
        a measurement and a declaration appear in the same sentence, and it
        stays on the right side of the advisory line by construction rather
        than by the model's phrasing."""
        out = await SUMMARY("usr_9001")
        assert out["suitability"]["statement"].startswith("Ölçülen portföy riskiniz")
        assert out["suitability"]["alignment"] == "PORTFOLIO_CALMER"

    async def test_an_unmeasurable_score_stays_null(self, fake_backend, risk_summary_payload):
        """0.0 is the WORST score on a scale where high means calm, so
        defaulting a missing one inverts the answer."""
        fake_backend.json("risk_summary", {**risk_summary_payload, "score": None,
                                           "level": None})
        out = await SUMMARY("usr_9001")
        assert out["score"] is None
        assert out["level"] is None

    async def test_no_questionnaire_yields_a_null_declaration(
        self, fake_backend, risk_summary_payload
    ):
        fake_backend.json("risk_summary", {
            **risk_summary_payload,
            "declared": None,
            "suitability": {**risk_summary_payload["suitability"],
                            "declared_tolerance": None, "alignment": "UNKNOWN"},
        })
        out = await SUMMARY("usr_9001")
        assert out["declared"] is None
        assert out["suitability"]["alignment"] == "UNKNOWN"


class TestSummaryGuards:
    @pytest.mark.parametrize("missing", [
        "as_of", "score", "level", "position_count", "suitability",
        "declared", "metrics", "findings", "data_quality", "warnings",
    ])
    async def test_every_top_level_key_is_load_bearing(
        self, fake_backend, risk_summary_payload, missing
    ):
        fake_backend.json("risk_summary", without(risk_summary_payload, missing))
        with pytest.raises(ContractViolationError, match=missing):
            await SUMMARY("usr_9001")

    @pytest.mark.parametrize(
        "missing", ["measured_level", "declared_tolerance", "alignment", "statement"]
    )
    async def test_the_comparison_block_must_be_complete(
        self, fake_backend, risk_summary_payload, missing
    ):
        fake_backend.json("risk_summary", {
            **risk_summary_payload,
            "suitability": without(risk_summary_payload["suitability"], missing),
        })
        with pytest.raises(ContractViolationError, match=missing):
            await SUMMARY("usr_9001")

    async def test_a_non_object_comparison_block_raises(
        self, fake_backend, risk_summary_payload
    ):
        fake_backend.json("risk_summary", {**risk_summary_payload, "suitability": "ALIGNED"})
        with pytest.raises(ContractViolationError, match="must be an object"):
            await SUMMARY("usr_9001")

    async def test_an_unknown_alignment_raises_rather_than_passing_through(
        self, fake_backend, risk_summary_payload
    ):
        """A label the tool does not recognise is contract drift. Passed
        through, the model narrates it to the user as though it meant
        something."""
        fake_backend.json("risk_summary", {
            **risk_summary_payload,
            "suitability": {**risk_summary_payload["suitability"],
                            "alignment": "MOSTLY_FINE"},
        })
        with pytest.raises(ContractViolationError, match="unknown alignment"):
            await SUMMARY("usr_9001")

    async def test_a_non_object_metric_block_raises(self, fake_backend, risk_summary_payload):
        fake_backend.json("risk_summary", {**risk_summary_payload, "metrics": []})
        with pytest.raises(ContractViolationError, match="'metrics' must be an object"):
            await SUMMARY("usr_9001")

    async def test_a_non_object_quality_block_raises(self, fake_backend, risk_summary_payload):
        fake_backend.json("risk_summary", {**risk_summary_payload, "data_quality": "fine"})
        with pytest.raises(ContractViolationError, match="'data_quality' must be an object"):
            await SUMMARY("usr_9001")

    async def test_a_non_numeric_score_raises(self, fake_backend, risk_summary_payload):
        fake_backend.json("risk_summary", {**risk_summary_payload, "score": "düşük"})
        with pytest.raises(ContractViolationError, match="must be a number or null"):
            await SUMMARY("usr_9001")

    async def test_null_lists_normalise_to_empty(self, fake_backend, risk_summary_payload):
        """Present-and-null is the backend saying "nothing to report"; absent
        would be a contract violation, and the test above covers that."""
        fake_backend.json("risk_summary", {**risk_summary_payload,
                                           "findings": None, "warnings": None})
        out = await SUMMARY("usr_9001")
        assert out["findings"] == []
        assert out["warnings"] == []

    async def test_as_of_is_a_utc_timestamp(self, fake_backend):
        out = await SUMMARY("usr_9001")
        assert_iso8601_utc(out["as_of"])


class TestSummaryFailures:
    async def test_rejected_service_credentials_surface_as_authorization(self, fake_backend):
        """The endpoint names its subject in the path, so it is guarded. A
        misconfigured key must not read as "this user has no risk profile"."""
        fake_backend.status("risk_summary", 401)
        with pytest.raises(AuthorizationError):
            await SUMMARY("usr_9001")

    async def test_an_unconfigured_backend_guard_is_an_outage(self, fake_backend):
        """503 when BACKEND_API_KEY is unset backend-side; retryable."""
        fake_backend.status("risk_summary", 503)
        with pytest.raises(UpstreamUnavailableError):
            await SUMMARY("usr_9001")

    async def test_an_unknown_user_is_invalid_input(self, fake_backend):
        fake_backend.status("risk_summary", 404)
        with pytest.raises(InvalidInputError):
            await SUMMARY("usr_9001")

    async def test_timeout_raises_upstream_unavailable(self, fake_backend):
        fake_backend.fail("risk_summary", httpx.ReadTimeout("profile slow"))
        with pytest.raises(UpstreamUnavailableError):
            await SUMMARY("usr_9001")



# ==========================================================================
# Lookback canonicalisation.
#
# Not a hypothetical: two consecutive live turns asking "portföyüm ne kadar
# riskli" produced lookback "1y" and then "365". Both were rejected with a
# 422 that reached the user as "Verilere şu anda ulaşamadım" -- an outage
# message for a portfolio whose data was entirely present.
# ==========================================================================
class TestLookbackCanonicalisation:
    @pytest.mark.parametrize("written,canonical", [
        ("1y", "1Y"), ("3m", "3M"), ("max", "MAX"), (" 1Y ", "1Y"),
    ])
    async def test_casing_and_padding_are_normalised(self, written, canonical):
        assert risk_strategy_tools.canonical_lookback(written, "t") == canonical

    @pytest.mark.parametrize("written,canonical", [
        ("365", "1Y"), ("252", "1Y"), ("12M", "1Y"), ("YTD", "1Y"),
        ("90", "3M"), ("30", "1M"), ("180", "6M"), ("ALL", "MAX"),
    ])
    async def test_the_shapes_the_model_actually_writes(self, written, canonical):
        assert risk_strategy_tools.canonical_lookback(written, "t") == canonical

    async def test_nothing_given_means_the_default_window(self):
        assert risk_strategy_tools.canonical_lookback(None, "t") == "1Y"
        assert risk_strategy_tools.canonical_lookback("", "t") == "1Y"

    async def test_an_unrecognised_window_still_raises(self):
        """Rounding an unknown window to 1Y is the behaviour this path exists
        to prevent: `window_for` would return a year of data under whatever
        label the caller sent, and never say so."""
        with pytest.raises(InvalidInputError, match="not one of"):
            risk_strategy_tools.canonical_lookback("son 3 ay", "t")

    async def test_the_metrics_tool_sends_the_canonical_form(
        self, fake_backend, sample_positions
    ):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, lookback="365"
        )
        assert fake_backend.body()["lookback"] == "1Y"

    async def test_the_summary_tool_sends_the_canonical_form(self, fake_backend):
        await SUMMARY("usr_9001", lookback="1y")
        assert fake_backend.last.url.params["lookback"] == "1Y"

    async def test_both_tools_resolve_a_window_the_same_way(
        self, fake_backend, sample_positions
    ):
        """A score measured over one window beside statistics measured over
        another is two answers about two different portfolios-in-time."""
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, lookback="12m"
        )
        sent_to_metrics = fake_backend.body()["lookback"]
        await SUMMARY("usr_9001", lookback="12m")
        assert fake_backend.last.url.params["lookback"] == sent_to_metrics

    async def test_a_bad_window_fails_before_the_request(
        self, fake_backend, sample_positions
    ):
        with pytest.raises(InvalidInputError):
            await risk_strategy_tools.calculate_portfolio_risk_metrics(
                sample_positions, lookback="haftalık"
            )
        assert fake_backend.attempts == 0


class TestMetricNames:
    """Sözleşme geçerli metrikleri baştan beri LİSTELİYORDU ama hiçbir şey
    doğrulamıyordu.

    Ölçüldü: risk özetine `allocation_drift` eklendikten sonra planlayıcı onu
    istenecek bir metrik sandı, `metrics: ["allocation_drift"]` gönderdi ve
    kullanıcı "hedef dağılımımdan ne kadar saptım" sorusuna "ölçüm elde
    edilemedi" cevabı aldı -- oysa sapma aynı turda başarıyla alınmıştı.
    """

    @pytest.mark.parametrize("written", ["allocation_drift", "GROUP_EXPOSURE"])
    async def test_the_alongside_blocks_are_stripped_not_refused(
        self, fake_backend, sample_positions, written
    ):
        """Model yanlış bir şey İSTEMİYOR, yanlış kapıyı çalıyor: iki blok da
        turda zaten geliyor.

        Reddetmek denendi ve yetmedi -- kural sözleşmeye ve prompt'a
        yazıldıktan sonra da planlayıcı aynı değeri gönderdi ve turun tek
        düzeltme denemesi de onu tekrarladı."""
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, metrics=[written]
        )
        assert "metrics" not in fake_backend.body()

    @pytest.mark.parametrize(
        "written,canonical",
        [("ES", "CVAR"), ("expected_shortfall", "CVAR"), ("drawdown", "MAX_DRAWDOWN"),
         ("sharpe_ratio", "SHARPE"), ("hhi", "CONCENTRATION"),
         ("value_at_risk", "VAR"), ("correlation", "CORRELATION_MATRIX")],
    )
    async def test_another_name_for_the_same_measurement_is_folded(
        self, fake_backend, sample_positions, written, canonical
    ):
        """Ölçüldü: planlayıcı `ES` gönderdi -- Expected Shortfall, CVaR'ın
        standart adı -- ve tur düştü. Reddetmek, cevabı modelin hangi
        eşanlamlıyı seçtiğine bağlı kılıyor."""
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, metrics=[written]
        )
        assert fake_backend.body()["metrics"] == [canonical]

    async def test_a_genuinely_unknown_metric_still_raises(
        self, fake_backend, sample_positions
    ):
        with pytest.raises(InvalidInputError) as excinfo:
            await risk_strategy_tools.calculate_portfolio_risk_metrics(
                sample_positions, metrics=["SORTINO"]
            )
        assert fake_backend.attempts == 0
        assert "VOLATILITY" in str(excinfo.value)

    async def test_a_valid_metric_survives_beside_a_stripped_one(
        self, fake_backend, sample_positions
    ):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, metrics=["allocation_drift", "SHARPE"]
        )
        assert fake_backend.body()["metrics"] == ["SHARPE"]

    async def test_valid_names_pass_through(self, fake_backend, sample_positions):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, metrics=["VOLATILITY", "SHARPE"]
        )
        assert fake_backend.body()["metrics"] == ["VOLATILITY", "SHARPE"]

    @pytest.mark.parametrize("written", ["volatility", " Sharpe ", "max-drawdown"])
    async def test_casing_and_separators_are_tolerated(
        self, fake_backend, sample_positions, written
    ):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, metrics=[written]
        )
        assert fake_backend.body()["metrics"][0] in risk_strategy_tools.ALLOWED_METRICS

    async def test_duplicates_collapse(self, fake_backend, sample_positions):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(
            sample_positions, metrics=["VOLATILITY", "volatility"]
        )
        assert fake_backend.body()["metrics"] == ["VOLATILITY"]

    async def test_none_still_means_every_default_metric(
        self, fake_backend, sample_positions
    ):
        await risk_strategy_tools.calculate_portfolio_risk_metrics(sample_positions)
        assert "metrics" not in fake_backend.body()
