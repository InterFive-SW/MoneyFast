"""Unit tests for compliance_tools.

Contract under test: Interface Definitions v2.1, validate_compliance_rules,
now backed by POST /compliance/validate.

This is the one tool where a permissive bug is not a defect but an incident.
The normalizer resolves every ambiguity toward BLOCK, and the tests below
exist to make each of those resolutions expensive to remove:

* an unrecognised verdict is refused, never read as PASS;
* a CRITICAL violation forces BLOCK even if the engine said otherwise;
* REVISE without a remediated draft becomes BLOCK, because the original is
  not a fallback;
* every transport failure raises, so the orchestrator can fail closed.

There is no offline mode and no cached verdict. A test that had to stub one
would be evidence of a hole.
"""

from __future__ import annotations

import httpx
import pytest

import compliance_tools
from backend_client import (
    AuthorizationError,
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)
from conftest import assert_no_market_data_fields, without

ADVICE_DRAFT = "THYAO'yu almanızı öneririm, kesin kazandırır."
NEUTRAL_DRAFT = "THYAO'nun F/K oranı 8,4 seviyesinde."

pytestmark = pytest.mark.asyncio


async def validate(**kwargs):
    kwargs.setdefault("draft_response", NEUTRAL_DRAFT)
    kwargs.setdefault("user_query", "F/K nedir?")
    return await compliance_tools.validate_compliance_rules(**kwargs)


# ==========================================================================
# Request construction
# ==========================================================================
class TestRequest:
    async def test_posts_to_the_validate_endpoint(self, fake_backend):
        await validate()
        assert fake_backend.last.method == "POST"
        assert "/compliance/validate" in str(fake_backend.last.url)

    async def test_complete_draft_is_submitted_verbatim(self, fake_backend):
        """Partial submission invalidates the verdict, so the tool never
        truncates or summarises the draft."""
        await validate(draft_response=ADVICE_DRAFT)
        assert fake_backend.body()["draft_response"] == ADVICE_DRAFT

    async def test_user_query_is_submitted(self, fake_backend):
        """Intent changes the ruling: the same text can be permitted as
        education and prohibited as an answer to "what should I buy"."""
        await validate(user_query="Ne alayım?")
        assert fake_backend.body()["user_query"] == "Ne alayım?"

    async def test_default_arguments(self, fake_backend):
        await validate()
        body = fake_backend.body()
        assert body["jurisdiction"] == "TR"
        assert body["strictness"] == "STANDARD"
        assert body["contains_personal_data"] is False
        assert body["contains_transaction_proposal"] is False

    async def test_tools_used_defaults_to_an_empty_list_not_omitted(self, fake_backend):
        """The backend distinguishes "no tool contributed" from "the caller
        forgot to say", so this field is always present."""
        await validate(tools_used=None)
        assert fake_backend.body()["tools_used"] == []

    async def test_tools_used_is_forwarded(self, fake_backend):
        await validate(tools_used=["get_portfolio_positions", "calculate_portfolio_risk_metrics"])
        assert fake_backend.body()["tools_used"] == [
            "get_portfolio_positions", "calculate_portfolio_risk_metrics"
        ]

    @pytest.mark.parametrize("personal", [True, False])
    @pytest.mark.parametrize("proposal", [True, False])
    async def test_context_flags_are_forwarded_in_every_combination(
        self, fake_backend, personal, proposal
    ):
        await validate(contains_personal_data=personal, contains_transaction_proposal=proposal)
        body = fake_backend.body()
        assert body["contains_personal_data"] is personal
        assert body["contains_transaction_proposal"] is proposal

    @pytest.mark.parametrize("strictness", ["STANDARD", "STRICT"])
    async def test_strictness_is_forwarded(self, fake_backend, strictness):
        await validate(strictness=strictness)
        assert fake_backend.body()["strictness"] == strictness

    @pytest.mark.parametrize("jurisdiction", ["TR", "DE", "US"])
    async def test_jurisdiction_is_forwarded(self, fake_backend, jurisdiction):
        await validate(jurisdiction=jurisdiction)
        assert fake_backend.body()["jurisdiction"] == jurisdiction

    async def test_empty_draft_is_still_submitted(self, fake_backend):
        """Edge case: an empty string is a value the engine may want to rule
        on, and clean() only drops None."""
        await validate(draft_response="", user_query="")
        assert fake_backend.body()["draft_response"] == ""


# ==========================================================================
# Verdict relay
# ==========================================================================
class TestVerdictRelay:
    async def test_exact_top_level_contract(self, compliance_top_level_keys):
        assert set(await validate()) == compliance_top_level_keys

    async def test_carries_no_market_data_fields(self):
        """Their presence would teach a calling model to expect freshness
        semantics where none exist, and from there to invent them."""
        assert_no_market_data_fields(await validate())

    async def test_pass_is_relayed_unchanged(self):
        verdict = await validate()
        assert verdict["verdict"] == "PASS"
        assert verdict["violations"] == []
        assert verdict["remediated_response"] is None
        assert verdict["blocked_reason_user_facing"] is None

    async def test_lowercase_verdict_is_normalised(self, fake_backend, compliance_payload):
        compliance_payload["verdict"] = "pass"
        fake_backend.json("compliance", compliance_payload)
        assert (await validate())["verdict"] == "PASS"

    async def test_revise_relays_the_remediated_draft(
        self, fake_backend, compliance_payload
    ):
        compliance_payload["verdict"] = "REVISE"
        compliance_payload["remediated_response"] = "Düzeltilmiş taslak."
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate(draft_response=ADVICE_DRAFT)
        assert verdict["verdict"] == "REVISE"
        assert verdict["remediated_response"] == "Düzeltilmiş taslak."
        assert verdict["blocked_reason_user_facing"] is None

    async def test_block_relays_the_user_facing_reason(
        self, fake_backend, compliance_payload
    ):
        compliance_payload["verdict"] = "BLOCK"
        compliance_payload["blocked_reason_user_facing"] = "Getiri garantisi veremem."
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate(draft_response=ADVICE_DRAFT)
        assert verdict["verdict"] == "BLOCK"
        assert verdict["blocked_reason_user_facing"] == "Getiri garantisi veremem."
        assert verdict["remediated_response"] is None

    async def test_stale_remediation_is_cleared_on_a_block(
        self, fake_backend, compliance_payload
    ):
        """A BLOCK payload that still carries remediated text must not leave
        the orchestrator anything emittable."""
        compliance_payload["verdict"] = "BLOCK"
        compliance_payload["remediated_response"] = "leftover text"
        fake_backend.json("compliance", compliance_payload)
        assert (await validate())["remediated_response"] is None

    async def test_stale_block_reason_is_cleared_on_a_pass(
        self, fake_backend, compliance_payload
    ):
        compliance_payload["blocked_reason_user_facing"] = "leftover reason"
        fake_backend.json("compliance", compliance_payload)
        assert (await validate())["blocked_reason_user_facing"] is None

    async def test_violations_and_disclosures_pass_through_verbatim(
        self, fake_backend, compliance_payload
    ):
        """Disclosure text is emitted to the user verbatim; never reshaped,
        translated or merged."""
        disclosure = {
            "disclosure_id": "DISC-TR-001",
            "text": "Burada yer alan bilgiler yatırım danışmanlığı kapsamında değildir.",
            "placement": "APPEND",
        }
        compliance_payload["required_disclosures"] = [disclosure]
        fake_backend.json("compliance", compliance_payload)
        assert (await validate())["required_disclosures"] == [disclosure]

    async def test_missing_optional_lists_default_to_empty(
        self, fake_backend, compliance_payload
    ):
        fake_backend.json(
            "compliance", without(compliance_payload, "violations", "required_disclosures")
        )
        verdict = await validate()
        assert verdict["violations"] == []
        assert verdict["required_disclosures"] == []

    async def test_missing_rule_pack_version_is_marked_unknown(
        self, fake_backend, compliance_payload
    ):
        """Logged with the turn. UNKNOWN is visibly wrong in an audit trail,
        which is better than an empty string that looks intentional."""
        fake_backend.json("compliance", without(compliance_payload, "rule_pack_version"))
        assert (await validate())["rule_pack_version"] == "UNKNOWN"


# ==========================================================================
# Ambiguity resolves toward BLOCK
# ==========================================================================
class TestFailsClosed:
    @pytest.mark.parametrize("verdict", ["APPROVED", "OK", "ALLOW", "", "pass!"])
    async def test_unrecognised_verdict_is_refused_never_read_as_pass(
        self, fake_backend, compliance_payload, verdict
    ):
        """A verdict the tool cannot interpret is a system fault. Guessing in
        the permissive direction is the specific failure this guard exists to
        prevent."""
        compliance_payload["verdict"] = verdict
        fake_backend.json("compliance", compliance_payload)
        with pytest.raises(ContractViolationError, match="unrecognised verdict"):
            await validate()

    async def test_missing_verdict_is_a_violation(self, fake_backend, compliance_payload):
        fake_backend.json("compliance", without(compliance_payload, "verdict"))
        with pytest.raises(ContractViolationError, match="verdict"):
            await validate()

    async def test_missing_audit_id_is_a_violation(self, fake_backend, compliance_payload):
        """Without it the validation event cannot be tied to the turn, and the
        audit trail is the thing that makes the gate provable after the fact."""
        fake_backend.json("compliance", without(compliance_payload, "audit_id"))
        with pytest.raises(ContractViolationError, match="audit_id"):
            await validate()

    async def test_critical_violation_overrides_a_pass(
        self, fake_backend, compliance_payload
    ):
        """Defence in depth. The engine should already have blocked this; if a
        rule-pack bug lets a CRITICAL through with PASS, the tool still stops
        it."""
        compliance_payload["violations"] = [
            {"rule_id": "GUAR-002", "severity": "CRITICAL", "rule_name": "Guaranteed return"}
        ]
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate(draft_response=ADVICE_DRAFT)
        assert verdict["verdict"] == "BLOCK"

    async def test_critical_violation_overrides_a_revise(
        self, fake_backend, compliance_payload
    ):
        compliance_payload["verdict"] = "REVISE"
        compliance_payload["remediated_response"] = "Düzeltilmiş."
        compliance_payload["violations"] = [{"rule_id": "X", "severity": "critical"}]
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate()
        assert verdict["verdict"] == "BLOCK"
        assert verdict["remediated_response"] is None

    async def test_non_critical_violations_do_not_force_a_block(
        self, fake_backend, compliance_payload
    ):
        """The override must be surgical: HIGH is not CRITICAL, and treating
        it as one would make the gate useless through over-blocking."""
        compliance_payload["violations"] = [
            {"rule_id": "ADV-001", "severity": "HIGH"},
            {"rule_id": "ADV-002", "severity": "LOW"},
        ]
        fake_backend.json("compliance", compliance_payload)
        assert (await validate())["verdict"] == "PASS"

    async def test_malformed_violation_entries_do_not_crash_the_scan(
        self, fake_backend, compliance_payload
    ):
        """A non-object entry is skipped rather than raising: the severity
        scan must survive a sloppy payload, because crashing here would take
        down the gate it is protecting."""
        compliance_payload["violations"] = ["not an object", None, {"severity": "LOW"}]
        fake_backend.json("compliance", compliance_payload)
        assert (await validate())["verdict"] == "PASS"

    async def test_violation_without_a_severity_is_not_treated_as_critical(
        self, fake_backend, compliance_payload
    ):
        compliance_payload["violations"] = [{"rule_id": "ADV-001"}]
        fake_backend.json("compliance", compliance_payload)
        assert (await validate())["verdict"] == "PASS"

    async def test_block_stays_block_when_it_carries_a_critical(
        self, fake_backend, compliance_payload
    ):
        compliance_payload["verdict"] = "BLOCK"
        compliance_payload["violations"] = [{"severity": "CRITICAL"}]
        compliance_payload["blocked_reason_user_facing"] = "Yanıt veremem."
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate()
        assert verdict["verdict"] == "BLOCK"
        assert verdict["blocked_reason_user_facing"] == "Yanıt veremem."

    @pytest.mark.parametrize("remediation", [None, ""])
    async def test_revise_without_usable_remediation_becomes_block(
        self, fake_backend, compliance_payload, remediation
    ):
        """REVISE means "emit this instead". With nothing to emit, the only
        safe reading is BLOCK; the original draft is never a fallback."""
        compliance_payload["verdict"] = "REVISE"
        compliance_payload["remediated_response"] = remediation
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate(draft_response=ADVICE_DRAFT)
        assert verdict["verdict"] == "BLOCK"
        assert verdict["remediated_response"] is None

    async def test_whitespace_only_remediation_becomes_block(
        self, fake_backend, compliance_payload
    ):
        """A remediation consisting only of whitespace must trigger a BLOCK, 
        otherwise the orchestrator emits a blank message."""
        compliance_payload["verdict"] = "REVISE"
        compliance_payload["remediated_response"] = "   "
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate()
        assert verdict["verdict"] == "BLOCK"
        assert verdict["remediated_response"] is None

    async def test_blank_remediation_string_is_treated_as_absent(
        self, fake_backend, compliance_payload
    ):
        compliance_payload["verdict"] = "REVISE"
        compliance_payload["remediated_response"] = ""
        fake_backend.json("compliance", compliance_payload)
        verdict = await validate()
        assert verdict["verdict"] == "BLOCK"
        assert verdict["remediated_response"] is None

    async def test_block_without_a_reason_gets_the_turkish_default(
        self, fake_backend, compliance_payload
    ):
        """The user is owed an explanation in their own language even when the
        engine supplies none."""
        compliance_payload["verdict"] = "BLOCK"
        compliance_payload["blocked_reason_user_facing"] = None
        fake_backend.json("compliance", compliance_payload)
        reason = (await validate())["blocked_reason_user_facing"]
        assert reason == compliance_tools.DEFAULT_BLOCK_REASON_TR
        assert any(ch in reason for ch in "ıİşğüöç"), "must be Turkish"

    async def test_default_block_reason_leaks_no_internals(self):
        """Rule ids, span offsets and rule pack versions never reach the user."""
        reason = compliance_tools.DEFAULT_BLOCK_REASON_TR
        for leak in ("rule", "ADV-", "GUAR-", "TR_RETAIL", "severity", "span"):
            assert leak.lower() not in reason.lower()


# ==========================================================================
# Transport failures: the orchestrator turns these into BLOCK
# ==========================================================================
class TestTransportFailures:
    async def test_engine_outage_raises_rather_than_returning_a_verdict(
        self, fake_backend
    ):
        """The whole fail-closed design rests on this. A tool that returned a
        default PASS here would cost a licence rather than a reply."""
        fake_backend.status("compliance", 503)
        with pytest.raises(UpstreamUnavailableError):
            await validate()

    async def test_timeout_raises(self, fake_backend):
        fake_backend.fail("compliance", httpx.ReadTimeout("engine slow"))
        with pytest.raises(UpstreamUnavailableError):
            await validate()

    async def test_unsupported_jurisdiction_raises_rather_than_defaulting(
        self, fake_backend
    ):
        """Falling back to a permissive rule pack would be a silent hole."""
        fake_backend.status("compliance", 400, {"error": "UnsupportedJurisdictionError: ZZ"})
        with pytest.raises(InvalidInputError):
            await validate(jurisdiction="ZZ")

    async def test_unauthorized_raises(self, fake_backend):
        fake_backend.status("compliance", 401)
        with pytest.raises(AuthorizationError):
            await validate()

    async def test_non_json_response_raises(self, fake_backend):
        fake_backend.set("compliance", httpx.Response(200, text="<html>gateway</html>"))
        with pytest.raises(UpstreamUnavailableError):
            await validate()

    async def test_no_module_level_verdict_constant_exists(self):
        """Regression guard against reintroducing a canned PASS. If a cached
        or default verdict is ever added, this test names it."""
        module_dict = vars(compliance_tools)
        canned = [
            name for name, value in module_dict.items()
            if isinstance(value, dict) and value.get("verdict") == "PASS"
        ]
        assert canned == [], f"canned PASS verdict found: {canned}"


# ==========================================================================
# Registration
# ==========================================================================
class TestRegistration:
    async def test_register_attaches_the_tool(self, mocker):
        fake_mcp = mocker.MagicMock()
        compliance_tools.register(fake_mcp)
        fake_mcp.tool.assert_called_once_with()
        fake_mcp.tool.return_value.assert_called_once_with(
            compliance_tools.validate_compliance_rules
        )

    async def test_the_tool_is_a_coroutine_function(self):
        import inspect

        assert inspect.iscoroutinefunction(compliance_tools.validate_compliance_rules)

    async def test_verdict_enum_matches_the_contract(self):
        assert compliance_tools.VERDICTS == frozenset({"PASS", "REVISE", "BLOCK"})
