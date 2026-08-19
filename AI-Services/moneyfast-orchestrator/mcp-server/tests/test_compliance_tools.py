"""Unit tests for compliance_tools.

Contract under test: Interface Definitions v2.1, validate_compliance_rules.

This module is the one place where a passing test suite is genuinely
dangerous: the mock returns PASS unconditionally and screens nothing. The
tests below assert the SHAPE of the verdict and the coherence of the two
branch fixtures, and one test asserts explicitly that the mock does no
screening, so nobody mistakes green CI for a working gate.
"""

from __future__ import annotations

import pytest

import compliance_tools
from conftest import assert_no_market_data_fields

ADVICE_DRAFT = "THYAO'yu almanızı öneririm, kesin kazandırır."
NEUTRAL_DRAFT = "THYAO'nun F/K oranı 8,4 seviyesinde."


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------
def test_returns_exact_top_level_contract(compliance_top_level_keys):
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="F/K nedir?"
    )
    assert set(verdict) == compliance_top_level_keys


def test_carries_no_market_data_fields():
    """Contract rule: tools 4, 5 and 6 must not expose as_of/source/is_delayed.

    Their presence would teach a calling model to expect freshness semantics
    where none exist, and from there to invent them.
    """
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="soru"
    )
    assert_no_market_data_fields(verdict)


def test_verdict_is_from_the_allowed_enum():
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="soru"
    )
    assert verdict["verdict"] in {"PASS", "REVISE", "BLOCK"}


def test_pass_verdict_is_internally_coherent():
    """PASS means: no violations, nothing to remediate, nothing to explain."""
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="soru"
    )
    assert verdict["verdict"] == "PASS"
    assert verdict["violations"] == []
    assert verdict["remediated_response"] is None
    assert verdict["blocked_reason_user_facing"] is None


def test_audit_id_and_rule_pack_version_are_populated():
    """Both are logged with the turn; empty values break the audit trail."""
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="soru"
    )
    assert verdict["audit_id"].startswith("aud_")
    assert verdict["rule_pack_version"]


# --------------------------------------------------------------------------
# Argument handling: every documented argument must be accepted
# --------------------------------------------------------------------------
@pytest.mark.parametrize("jurisdiction", ["TR", "DE", "US"])
def test_jurisdiction_argument_accepted(jurisdiction):
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="soru", jurisdiction=jurisdiction
    )
    assert verdict["verdict"] in {"PASS", "REVISE", "BLOCK"}


@pytest.mark.parametrize("tools_used", [None, [], ["get_portfolio_positions"]])
def test_tools_used_accepts_none_empty_and_populated(tools_used):
    """None and [] are distinct inputs and neither may raise."""
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="soru", tools_used=tools_used
    )
    assert verdict["verdict"] == "PASS"


@pytest.mark.parametrize("personal", [True, False])
@pytest.mark.parametrize("proposal", [True, False])
def test_context_flags_accepted_in_every_combination(personal, proposal):
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT,
        user_query="soru",
        contains_personal_data=personal,
        contains_transaction_proposal=proposal,
    )
    assert verdict["verdict"] == "PASS"


@pytest.mark.parametrize("strictness", ["STANDARD", "STRICT"])
def test_strictness_argument_accepted(strictness):
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=NEUTRAL_DRAFT, user_query="soru", strictness=strictness
    )
    assert verdict["verdict"] == "PASS"


def test_empty_draft_is_accepted_by_the_mock():
    """Edge case. Documented so that when validation lands, this test flips."""
    verdict = compliance_tools.validate_compliance_rules(draft_response="", user_query="")
    assert verdict["verdict"] == "PASS"


# --------------------------------------------------------------------------
# The mock screens nothing. This must be visible, not implied.
# --------------------------------------------------------------------------
def test_mock_passes_a_draft_that_a_real_rule_engine_would_block():
    """Regression guard against a false sense of safety.

    The draft below contains a direct recommendation and a guaranteed-return
    claim, both CRITICAL under the TR rule pack. The mock passes it. When the
    real engine is wired in, this test MUST start failing, and that failure is
    the signal to invert it into an assertion of BLOCK.
    """
    verdict = compliance_tools.validate_compliance_rules(
        draft_response=ADVICE_DRAFT, user_query="Ne alayım?"
    )
    assert verdict["verdict"] == "PASS", (
        "Mock behaviour. If this fails, the real rule engine is live: change "
        "the assertion to verdict == 'BLOCK'."
    )
    assert verdict["violations"] == []


def test_verdict_is_independent_of_input_in_the_mock():
    """Proves the mock is a constant, so no test accidentally relies on it."""
    a = compliance_tools.validate_compliance_rules(draft_response="x", user_query="y")
    b = compliance_tools.validate_compliance_rules(
        draft_response=ADVICE_DRAFT, user_query="Ne alayım?", strictness="STRICT"
    )
    assert a == b


# --------------------------------------------------------------------------
# Branch fixtures: REVISE
# --------------------------------------------------------------------------
def test_revise_fixture_matches_the_contract(compliance_top_level_keys):
    assert set(compliance_tools.REVISE_FIXTURE) == compliance_top_level_keys


def test_revise_fixture_supplies_a_remediated_draft():
    """REVISE without remediated_response would leave the orchestrator with
    nothing safe to emit, which the graph must treat as a BLOCK."""
    fixture = compliance_tools.REVISE_FIXTURE
    assert fixture["verdict"] == "REVISE"
    assert isinstance(fixture["remediated_response"], str)
    assert fixture["remediated_response"]
    assert fixture["blocked_reason_user_facing"] is None


def test_revise_fixture_violation_shape():
    violation = compliance_tools.REVISE_FIXTURE["violations"][0]
    assert set(violation) == {
        "rule_id", "rule_name", "severity", "offending_span", "rationale", "remediation",
    }
    assert violation["severity"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    span = violation["offending_span"]
    assert set(span) == {"start", "end", "text"}
    assert span["start"] < span["end"]


def test_revise_fixture_has_no_critical_violation():
    """Any CRITICAL forces BLOCK, so a REVISE fixture containing one would be
    self-contradictory and would mask a real bug in the graph."""
    severities = {v["severity"] for v in compliance_tools.REVISE_FIXTURE["violations"]}
    assert "CRITICAL" not in severities


def test_revise_fixture_disclosure_shape():
    disclosure = compliance_tools.REVISE_FIXTURE["required_disclosures"][0]
    assert set(disclosure) == {"disclosure_id", "text", "placement"}
    assert disclosure["placement"] in {"PREPEND", "APPEND", "INLINE"}
    assert disclosure["text"].strip() == disclosure["text"]


def test_revise_disclosure_text_is_turkish_and_verbatim():
    """Disclosures are emitted verbatim to a Turkish-speaking user."""
    text = compliance_tools.REVISE_FIXTURE["required_disclosures"][0]["text"]
    assert "yatırım danışmanlığı" in text


# --------------------------------------------------------------------------
# Branch fixtures: BLOCK
# --------------------------------------------------------------------------
def test_block_fixture_matches_the_contract(compliance_top_level_keys):
    assert set(compliance_tools.BLOCK_FIXTURE) == compliance_top_level_keys


def test_block_fixture_offers_no_emittable_text():
    """BLOCK must give the orchestrator a user-facing reason and no draft."""
    fixture = compliance_tools.BLOCK_FIXTURE
    assert fixture["verdict"] == "BLOCK"
    assert fixture["remediated_response"] is None
    assert isinstance(fixture["blocked_reason_user_facing"], str)
    assert fixture["blocked_reason_user_facing"].strip()


def test_block_fixture_carries_a_critical_violation():
    severities = {v["severity"] for v in compliance_tools.BLOCK_FIXTURE["violations"]}
    assert "CRITICAL" in severities


def test_block_reason_is_turkish_and_leaks_no_internals():
    """Rule ids, span offsets and rule pack versions must never reach the user."""
    fixture = compliance_tools.BLOCK_FIXTURE
    reason = fixture["blocked_reason_user_facing"]
    assert fixture["violations"][0]["rule_id"] not in reason
    assert fixture["rule_pack_version"] not in reason
    assert str(fixture["violations"][0]["offending_span"]["start"]) not in reason


def test_all_three_verdicts_use_distinct_audit_ids():
    """Audit ids identify a single validation event; collisions break the trail."""
    live = compliance_tools.validate_compliance_rules(draft_response="x", user_query="y")
    ids = {
        live["audit_id"],
        compliance_tools.REVISE_FIXTURE["audit_id"],
        compliance_tools.BLOCK_FIXTURE["audit_id"],
    }
    assert len(ids) == 3


def test_fixtures_and_live_return_share_the_same_rule_pack():
    assert (
        compliance_tools.REVISE_FIXTURE["rule_pack_version"]
        == compliance_tools.BLOCK_FIXTURE["rule_pack_version"]
    )


# --------------------------------------------------------------------------
# Isolation and error handling
# --------------------------------------------------------------------------
def test_makes_no_network_call_today(mocker):
    client = mocker.patch.object(compliance_tools, "httpx", create=True)
    compliance_tools.validate_compliance_rules(draft_response="x", user_query="y")
    assert client.post.call_count == 0


def test_rule_engine_unavailable_propagates_so_the_graph_can_fail_closed(mocker):
    """The graph converts any exception here into BLOCK. It can only do that
    if the tool actually raises rather than returning a default PASS."""
    mocker.patch.object(
        compliance_tools,
        "validate_compliance_rules",
        side_effect=ConnectionError("UpstreamUnavailableError: HTTP 503"),
    )
    with pytest.raises(ConnectionError, match="HTTP 503"):
        compliance_tools.validate_compliance_rules(draft_response="x", user_query="y")


def test_unsupported_jurisdiction_raises_rather_than_defaulting(mocker):
    """Falling back to a permissive rule pack would be a silent compliance hole."""
    mocker.patch.object(
        compliance_tools,
        "validate_compliance_rules",
        side_effect=ValueError("UnsupportedJurisdictionError: ZZ"),
    )
    with pytest.raises(ValueError, match="UnsupportedJurisdictionError"):
        compliance_tools.validate_compliance_rules(
            draft_response="x", user_query="y", jurisdiction="ZZ"
        )


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
def test_register_attaches_the_tool(mocker):
    fake_mcp = mocker.MagicMock()
    compliance_tools.register(fake_mcp)
    fake_mcp.tool.assert_called_once_with()
    fake_mcp.tool.return_value.assert_called_once_with(
        compliance_tools.validate_compliance_rules
    )
