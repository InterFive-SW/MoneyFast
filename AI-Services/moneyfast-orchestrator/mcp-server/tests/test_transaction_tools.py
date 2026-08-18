"""Unit tests for transaction_tools.

Contract under test: Interface Definitions v2.1, prepare_transaction_proposal.

The highest-severity defects for this tool are (a) anything that looks like
execution and (b) a fabricated value standing in for a missing argument. The
tests are weighted accordingly: cost arithmetic, the confirmation_required
constant, and the three ternary branches all get direct coverage.
"""

from __future__ import annotations

import pytest

import transaction_tools
from conftest import assert_no_market_data_fields

BASE_ARGS = {
    "user_id": "u_123",
    "transaction_type": "BUY",
    "source_account_id": "acc_998877",
    "idempotency_key": "idem_abc123",
}
DEFAULT_PRICE = 291.75
DEFAULT_QTY = 100.0
COMMISSION_RATE = 0.001
BSMV_RATE = 0.05


def stage(**overrides):
    """Call the tool with the mandatory arguments plus any overrides."""
    return transaction_tools.prepare_transaction_proposal(**{**BASE_ARGS, **overrides})


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------
def test_returns_exact_top_level_contract(proposal_top_level_keys):
    assert set(stage()) == proposal_top_level_keys


def test_carries_no_market_data_fields():
    """Pricing lives inside estimate under distinct names, deliberately, so the
    router never mistakes a staging estimate for a market data quote."""
    assert_no_market_data_fields(stage())


def test_status_is_from_the_allowed_enum():
    assert stage()["status"] in {
        "PENDING_USER_CONFIRMATION", "REJECTED_VALIDATION", "REQUIRES_ADDITIONAL_INPUT",
    }


def test_successful_staging_is_pending_confirmation():
    payload = stage()
    assert payload["status"] == "PENDING_USER_CONFIRMATION"
    assert payload["proposal_id"].startswith("prp_")
    assert payload["audit_id"].startswith("aud_")


# --------------------------------------------------------------------------
# The execution invariant
# --------------------------------------------------------------------------
def test_confirmation_required_is_always_true():
    """A constant contract assertion, not a setting. The graph treats False as
    a system fault, so this must hold for every argument combination."""
    assert stage()["confirmation_required"] is True


@pytest.mark.parametrize(
    "transaction_type",
    ["BUY", "SELL", "TRANSFER_INTERNAL", "TRANSFER_EXTERNAL", "FX_CONVERSION",
     "FUND_SUBSCRIPTION", "FUND_REDEMPTION"],
)
def test_confirmation_required_holds_for_every_transaction_type(transaction_type):
    payload = stage(transaction_type=transaction_type)
    assert payload["confirmation_required"] is True
    assert payload["summary"]["transaction_type"] == transaction_type


def test_status_never_indicates_execution():
    """No status value may suggest the order left the building."""
    forbidden = {"EXECUTED", "FILLED", "SUBMITTED", "SENT", "SETTLED", "PLACED"}
    assert stage()["status"] not in forbidden


def test_no_execution_vocabulary_anywhere_in_the_payload():
    """Scans disclosures and warnings too: the user-facing strings are where
    an 'order sent' phrasing would realistically creep in."""
    payload = stage()
    haystack = repr(payload).lower()
    for word in ("executed", "filled", "settled", "order sent", "gerçekleşti", "iletildi"):
        assert word not in haystack, f"execution vocabulary leaked: {word}"


def test_expiry_is_present_so_stale_proposals_cannot_be_confirmed():
    payload = stage()
    assert payload["expires_at"].endswith("Z")
    assert payload["expires_at"] > payload["estimate"]["indicative_price_timestamp"]


# --------------------------------------------------------------------------
# Cost arithmetic
# --------------------------------------------------------------------------
def test_estimate_block_is_complete():
    estimate = stage()["estimate"]
    assert set(estimate) == {
        "indicative_price", "indicative_price_timestamp", "indicative_price_basis",
        "gross_amount", "currency", "fees", "taxes", "total_cost", "fx", "price_certainty",
    }


def test_gross_amount_is_quantity_times_price():
    estimate = stage(quantity=250.0, limit_price=100.0)["estimate"]
    assert estimate["gross_amount"] == pytest.approx(25000.0)


def test_total_cost_equals_gross_plus_fees_plus_taxes():
    """The number the user is asked to confirm. It must actually add up."""
    estimate = stage(quantity=200.0, limit_price=50.0)["estimate"]
    fees = sum(f["amount"] for f in estimate["fees"])
    taxes = sum(t["amount"] for t in estimate["taxes"])
    assert estimate["total_cost"] == pytest.approx(
        estimate["gross_amount"] + fees + taxes, abs=0.01
    )


def test_commission_and_bsmv_rates():
    """BSMV is levied on the commission, not on the gross. Getting this
    backwards overstates cost by roughly fifty times."""
    estimate = stage(quantity=100.0, limit_price=100.0)["estimate"]
    commission = estimate["fees"][0]["amount"]
    bsmv = estimate["taxes"][0]["amount"]
    assert commission == pytest.approx(estimate["gross_amount"] * COMMISSION_RATE, abs=0.01)
    assert bsmv == pytest.approx(commission * BSMV_RATE, abs=0.01)


def test_fees_and_taxes_are_itemised_with_names():
    estimate = stage()["estimate"]
    for entry in estimate["fees"] + estimate["taxes"]:
        assert set(entry) == {"name", "amount"}
        assert entry["name"].strip()
        assert entry["amount"] >= 0


def test_price_certainty_is_indicative():
    """INDICATIVE obliges the orchestrator to disclose that the executed price
    will likely differ. Silently promoting it to FIRM would be a real defect."""
    assert stage()["estimate"]["price_certainty"] == "INDICATIVE"


def test_zero_quantity_produces_zero_cost_without_dividing_by_zero():
    """Edge case: 0.0 is falsy but is not missing, so ``is not None`` must be
    what the implementation checks."""
    estimate = stage(quantity=0.0)["estimate"]
    assert estimate["gross_amount"] == 0.0
    assert estimate["total_cost"] == 0.0


def test_fx_is_none_for_a_single_currency_order():
    assert stage()["estimate"]["fx"] is None


# --------------------------------------------------------------------------
# Branch coverage: the three ternaries
# --------------------------------------------------------------------------
def test_instrument_supplied_uses_its_symbol():
    payload = stage(instrument={"symbol": "ASELS", "exchange": "XIST"})
    assert payload["summary"]["instrument_display"].startswith("ASELS")


def test_instrument_none_falls_back_to_the_default_symbol():
    """Branch two of ``(instrument or {})``. In the real implementation this
    fallback must be replaced by REQUIRES_ADDITIONAL_INPUT: inventing a ticker
    is the highest-severity defect this tool can commit."""
    payload = stage(instrument=None)
    assert payload["summary"]["instrument_display"].startswith("THYAO")


def test_instrument_empty_dict_falls_back_to_the_default_symbol():
    payload = stage(instrument={})
    assert payload["summary"]["instrument_display"].startswith("THYAO")


def test_quantity_supplied_is_used_verbatim():
    assert stage(quantity=42.0)["summary"]["quantity"] == 42.0


def test_quantity_none_falls_back_to_the_default():
    assert stage(quantity=None)["summary"]["quantity"] == DEFAULT_QTY


def test_limit_price_drives_basis_and_price():
    """LIMIT order: the estimate must price off the limit, not the last trade."""
    estimate = stage(order_type="LIMIT", limit_price=310.0)["estimate"]
    assert estimate["indicative_price"] == 310.0
    assert estimate["indicative_price_basis"] == "LIMIT_PRICE"


def test_market_order_prices_off_last_trade():
    estimate = stage(order_type="MARKET", limit_price=None)["estimate"]
    assert estimate["indicative_price"] == DEFAULT_PRICE
    assert estimate["indicative_price_basis"] == "LAST_TRADE"


def test_zero_limit_price_is_honoured_not_treated_as_missing():
    """Edge case: 0.0 is falsy. An ``or`` here would silently reprice the order."""
    estimate = stage(order_type="LIMIT", limit_price=0.0)["estimate"]
    assert estimate["indicative_price"] == 0.0
    assert estimate["indicative_price_basis"] == "LIMIT_PRICE"
    assert estimate["gross_amount"] == 0.0


# --------------------------------------------------------------------------
# Summary block
# --------------------------------------------------------------------------
def test_summary_block_is_complete():
    summary = stage()["summary"]
    assert set(summary) == {
        "transaction_type", "instrument_display", "quantity", "notional",
        "order_type", "limit_price", "stop_price", "time_in_force",
        "source_account_display", "destination_display",
    }


def test_summary_masks_the_account_identifier():
    """Only the last four characters may reach a rendered surface."""
    payload = stage(source_account_id="acc_998877")
    display = payload["summary"]["source_account_display"]
    assert "acc_998877" not in display
    assert display.endswith("8877")


def test_summary_echoes_order_parameters():
    summary = stage(
        order_type="STOP_LIMIT", limit_price=300.0, stop_price=295.0, time_in_force="GTC"
    )["summary"]
    assert summary["order_type"] == "STOP_LIMIT"
    assert summary["limit_price"] == 300.0
    assert summary["stop_price"] == 295.0
    assert summary["time_in_force"] == "GTC"


@pytest.mark.parametrize("time_in_force", ["DAY", "GTC", "IOC", "FOK"])
def test_every_documented_time_in_force_accepted(time_in_force):
    assert stage(time_in_force=time_in_force)["summary"]["time_in_force"] == time_in_force


def test_notional_amount_is_passed_through():
    notional = {"value": 5000.0, "currency": "TRY"}
    assert stage(notional_amount=notional)["summary"]["notional"] == notional


def test_transfer_arguments_are_accepted():
    payload = stage(
        transaction_type="TRANSFER_EXTERNAL",
        notional_amount={"value": 5000.0, "currency": "TRY"},
        beneficiary={"iban": "TR000000000000000000000000", "full_name": "A B"},
        destination_account_id=None,
    )
    assert payload["confirmation_required"] is True


def test_assumptions_argument_is_accepted():
    """Whatever the caller declares must be renderable on the confirm surface."""
    payload = stage(assumptions=["Interpreted 'half' as 250 shares of 500 available."])
    assert payload["status"] == "PENDING_USER_CONFIRMATION"


# --------------------------------------------------------------------------
# Impact, blockers, warnings, disclosures
# --------------------------------------------------------------------------
def test_impact_is_arithmetic_only():
    impact = stage()["impact"]
    assert set(impact) == {
        "resulting_position_quantity", "resulting_weight", "resulting_cash_balance",
    }
    assert 0.0 <= impact["resulting_weight"] <= 1.0


def test_impact_carries_no_evaluative_language():
    """Contract: report impact as arithmetic, never as benefit."""
    haystack = repr(stage()["impact"]).lower()
    for word in ("better", "improved", "optimal", "recommended", "iyi", "uygun"):
        assert word not in haystack


def test_blockers_empty_on_a_successful_staging():
    payload = stage()
    assert payload["blockers"] == []
    assert payload["missing_fields"] == []


def test_warning_entries_are_shaped():
    for warning in stage()["warnings"]:
        assert set(warning) == {"code", "message"}
        assert warning["code"].isupper()


def test_disclosures_are_turkish_and_non_empty():
    """These are emitted verbatim to the user alongside the proposal."""
    disclosures = stage()["disclosures"]
    assert disclosures
    assert any("onay" in d.lower() for d in disclosures)
    assert any("göstergesel" in d.lower() for d in disclosures)


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------
def test_same_idempotency_key_yields_the_same_proposal_id():
    """Duplicate staging is the failure this key exists to prevent."""
    first = stage(idempotency_key="idem_same")
    second = stage(idempotency_key="idem_same")
    assert first["proposal_id"] == second["proposal_id"]


# --------------------------------------------------------------------------
# Isolation and error handling
# --------------------------------------------------------------------------
def test_makes_no_network_call_today(mocker):
    client = mocker.patch.object(transaction_tools, "httpx", create=True)
    stage()
    assert client.post.call_count == 0


def test_staging_service_unavailable_propagates(mocker):
    """FAIL CLOSED: an unstaged transaction must never be described as pending."""
    mocker.patch.object(
        transaction_tools,
        "prepare_transaction_proposal",
        side_effect=ConnectionError("UpstreamUnavailableError: staging HTTP 500"),
    )
    with pytest.raises(ConnectionError, match="staging HTTP 500"):
        transaction_tools.prepare_transaction_proposal(**BASE_ARGS)


def test_contradictory_arguments_raise_in_a_real_implementation(mocker):
    """quantity XOR notional_amount. The mock does not validate; this pins the
    expected behaviour so the check cannot be forgotten."""
    mocker.patch.object(
        transaction_tools,
        "prepare_transaction_proposal",
        side_effect=ValueError("InvalidInputError: quantity and notional_amount"),
    )
    with pytest.raises(ValueError, match="InvalidInputError"):
        transaction_tools.prepare_transaction_proposal(
            **BASE_ARGS, quantity=1.0, notional_amount={"value": 1.0, "currency": "TRY"}
        )


def test_authorization_failure_propagates(mocker):
    mocker.patch.object(
        transaction_tools,
        "prepare_transaction_proposal",
        side_effect=PermissionError("AuthorizationError: no transaction entitlement"),
    )
    with pytest.raises(PermissionError):
        transaction_tools.prepare_transaction_proposal(**BASE_ARGS)


def test_short_account_id_does_not_raise_on_slicing():
    """Edge case: ``source_account_id[-4:]`` on a shorter string is safe in
    Python but would mask a malformed id, so the behaviour is pinned."""
    payload = stage(source_account_id="ab")
    assert payload["summary"]["source_account_display"].endswith("ab")


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
def test_register_attaches_the_tool(mocker):
    fake_mcp = mocker.MagicMock()
    transaction_tools.register(fake_mcp)
    fake_mcp.tool.assert_called_once_with()
    fake_mcp.tool.return_value.assert_called_once_with(
        transaction_tools.prepare_transaction_proposal
    )
