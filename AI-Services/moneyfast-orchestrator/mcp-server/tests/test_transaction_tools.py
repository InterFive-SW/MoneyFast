"""Unit tests for transaction_tools.

Contract under test: Interface Definitions v2.1, prepare_transaction_proposal,
now backed by POST /transactions/stage.

Two invariants dominate this file because both are ways a user could end up
believing money moved:

* confirmation_required is the constant True. Anything else is a system fault
  and the proposal is refused rather than rendered.
* status must be one of the three documented values. An unrecognised status
  could mean anything, including something that already executed.

The rest guards against a fabricated value standing in for a missing argument,
which the contract calls the highest-severity defect this tool can commit.
"""

from __future__ import annotations

import httpx
import pytest

import transaction_tools
from backend_client import (
    AuthorizationError,
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)
from conftest import assert_no_market_data_fields, without

pytestmark = pytest.mark.asyncio


async def stage(stage_args, **overrides):
    return await transaction_tools.prepare_transaction_proposal(**{**stage_args, **overrides})


# ==========================================================================
# Client-side validation, before any request
# ==========================================================================
class TestPreflightValidation:
    async def test_quantity_and_notional_are_mutually_exclusive(
        self, fake_backend, stage_args
    ):
        with pytest.raises(InvalidInputError, match="mutually exclusive"):
            await stage(
                stage_args, quantity=100.0, notional_amount={"value": 5000.0, "currency": "TRY"}
            )
        assert fake_backend.attempts == 0, "a contradiction must never reach staging"

    async def test_either_one_alone_is_accepted(self, fake_backend, stage_args):
        await stage(stage_args, quantity=100.0)
        await stage(stage_args, notional_amount={"value": 5000.0, "currency": "TRY"})
        assert fake_backend.attempts == 2

    @pytest.mark.parametrize("order_type", ["LIMIT", "STOP_LIMIT"])
    async def test_limit_orders_require_a_limit_price(
        self, fake_backend, stage_args, order_type
    ):
        with pytest.raises(InvalidInputError, match="limit_price"):
            await stage(stage_args, order_type=order_type, stop_price=290.0)
        assert fake_backend.attempts == 0

    @pytest.mark.parametrize("order_type", ["STOP", "STOP_LIMIT"])
    async def test_stop_orders_require_a_stop_price(
        self, fake_backend, stage_args, order_type
    ):
        with pytest.raises(InvalidInputError, match="stop_price"):
            await stage(stage_args, order_type=order_type, limit_price=300.0)
        assert fake_backend.attempts == 0

    async def test_stop_limit_requires_both_prices(self, fake_backend, stage_args):
        await stage(stage_args, order_type="STOP_LIMIT", limit_price=300.0, stop_price=295.0)
        assert fake_backend.attempts == 1

    async def test_zero_limit_price_satisfies_the_requirement(
        self, fake_backend, stage_args
    ):
        """0.0 is falsy but is a stated price. An ``or`` check here would
        reject a legitimate order or silently reprice it."""
        await stage(stage_args, order_type="LIMIT", limit_price=0.0)
        assert fake_backend.body()["limit_price"] == 0.0

    async def test_market_order_needs_no_prices(self, fake_backend, stage_args):
        await stage(stage_args, order_type="MARKET")
        assert fake_backend.attempts == 1

    @pytest.mark.parametrize("key", ["", None])
    async def test_missing_idempotency_key_is_rejected(self, fake_backend, stage_args, key):
        """Without it a retry creates a second proposal, which is the failure
        this endpoint most needs to avoid."""
        with pytest.raises(InvalidInputError, match="idempotency_key"):
            await stage(stage_args, idempotency_key=key)
        assert fake_backend.attempts == 0


# ==========================================================================
# Request construction
# ==========================================================================
class TestRequest:
    async def test_posts_to_the_staging_endpoint(self, fake_backend, stage_args):
        await stage(stage_args)
        assert fake_backend.last.method == "POST"
        assert "/transactions/stage" in str(fake_backend.last.url)

    async def test_idempotency_key_travels_in_the_header_and_the_body(
        self, fake_backend, stage_args
    ):
        """The header is what a gateway or proxy deduplicates on; the body is
        what the service itself keys on. Both matter."""
        await stage(stage_args)
        assert fake_backend.last.headers["idempotency-key"] == "idem_abc123"
        assert fake_backend.body()["idempotency_key"] == "idem_abc123"

    async def test_mandatory_arguments_are_forwarded(self, fake_backend, stage_args):
        await stage(stage_args)
        body = fake_backend.body()
        assert body["user_id"] == "u_123"
        assert body["transaction_type"] == "BUY"
        assert body["source_account_id"] == "acc_998877"

    async def test_defaults_are_forwarded(self, fake_backend, stage_args):
        await stage(stage_args)
        body = fake_backend.body()
        assert body["order_type"] == "MARKET"
        assert body["time_in_force"] == "DAY"
        assert body["assumptions"] == []

    async def test_optional_arguments_are_omitted_when_none(self, fake_backend, stage_args):
        await stage(stage_args)
        body = fake_backend.body()
        for key in ("instrument", "quantity", "notional_amount",
                    "destination_account_id", "beneficiary", "limit_price", "stop_price"):
            assert key not in body

    async def test_instrument_and_quantity_are_forwarded(self, fake_backend, stage_args):
        await stage(
            stage_args,
            instrument={"symbol": "ASELS", "exchange": "XIST"},
            quantity=250.0,
        )
        body = fake_backend.body()
        assert body["instrument"] == {"symbol": "ASELS", "exchange": "XIST"}
        assert body["quantity"] == 250.0

    async def test_zero_quantity_is_forwarded_not_dropped(self, fake_backend, stage_args):
        await stage(stage_args, quantity=0.0)
        assert fake_backend.body()["quantity"] == 0.0

    async def test_assumptions_are_forwarded_verbatim(self, fake_backend, stage_args):
        """Each entry is rendered on the confirmation surface, so an inference
        the tool made but did not declare is a control failure."""
        assumptions = ["Interpreted 'half my position' as 250 shares of 500 available."]
        await stage(stage_args, assumptions=assumptions)
        assert fake_backend.body()["assumptions"] == assumptions

    async def test_transfer_arguments_are_forwarded(self, fake_backend, stage_args):
        beneficiary = {"iban": "TR000000000000000000000000", "full_name": "A B"}
        await stage(
            stage_args,
            transaction_type="TRANSFER_EXTERNAL",
            notional_amount={"value": 5000.0, "currency": "TRY"},
            beneficiary=beneficiary,
            destination_account_id="acc_dest",
        )
        body = fake_backend.body()
        assert body["beneficiary"] == beneficiary
        assert body["destination_account_id"] == "acc_dest"

    @pytest.mark.parametrize("time_in_force", ["DAY", "GTC", "IOC", "FOK"])
    async def test_every_documented_time_in_force(
        self, fake_backend, stage_args, time_in_force
    ):
        await stage(stage_args, time_in_force=time_in_force)
        assert fake_backend.body()["time_in_force"] == time_in_force

    @pytest.mark.parametrize(
        "transaction_type",
        ["BUY", "SELL", "TRANSFER_INTERNAL", "TRANSFER_EXTERNAL", "FX_CONVERSION",
         "FUND_SUBSCRIPTION", "FUND_REDEMPTION"],
    )
    async def test_every_documented_transaction_type(
        self, fake_backend, stage_args, transaction_type
    ):
        payload = await stage(stage_args, transaction_type=transaction_type)
        assert payload["confirmation_required"] is True


# ==========================================================================
# The execution invariants
# ==========================================================================
class TestExecutionInvariants:
    async def test_confirmation_required_is_true_on_a_successful_staging(
        self, stage_args
    ):
        assert (await stage(stage_args))["confirmation_required"] is True

    @pytest.mark.parametrize("value", [False, None, 0, "true", 1])
    async def test_anything_other_than_true_is_refused(
        self, fake_backend, stage_payload, stage_args, value
    ):
        """The single most important assertion in this file.

        A proposal presented without a confirmation step is indistinguishable
        to a user from a completed order. Note ``1`` and ``"true"`` are
        included: a truthy check here would pass them, and identity is what
        the contract calls for."""
        stage_payload["confirmation_required"] = value
        fake_backend.json("stage", stage_payload)
        with pytest.raises(ContractViolationError, match="confirmation_required"):
            await stage(stage_args)

    async def test_absent_confirmation_flag_is_refused(
        self, fake_backend, stage_payload, stage_args
    ):
        fake_backend.json("stage", without(stage_payload, "confirmation_required"))
        with pytest.raises(ContractViolationError, match="confirmation_required"):
            await stage(stage_args)

    @pytest.mark.parametrize(
        "status", ["EXECUTED", "FILLED", "SUBMITTED", "SETTLED", "PENDING", ""]
    )
    async def test_unrecognised_status_is_refused(
        self, fake_backend, stage_payload, stage_args, status
    ):
        """An unrecognised status could mean anything, including something
        that already executed. Refusing to present it is the only safe read."""
        stage_payload["status"] = status
        fake_backend.json("stage", stage_payload)
        with pytest.raises(ContractViolationError, match="unrecognised status"):
            await stage(stage_args)

    @pytest.mark.parametrize(
        "status",
        ["PENDING_USER_CONFIRMATION", "REJECTED_VALIDATION", "REQUIRES_ADDITIONAL_INPUT"],
    )
    async def test_documented_statuses_are_accepted(
        self, fake_backend, stage_payload, stage_args, status
    ):
        stage_payload["status"] = status
        if status != "PENDING_USER_CONFIRMATION":
            stage_payload["blockers"] = []
        fake_backend.json("stage", stage_payload)
        assert (await stage(stage_args))["status"] == status

    async def test_lowercase_status_is_normalised(
        self, fake_backend, stage_payload, stage_args
    ):
        stage_payload["status"] = "pending_user_confirmation"
        fake_backend.json("stage", stage_payload)
        assert (await stage(stage_args))["status"] == "PENDING_USER_CONFIRMATION"

    async def test_pending_status_with_blockers_is_incoherent_and_refused(
        self, fake_backend, stage_payload, stage_args
    ):
        """Blockers mean not staged. Presenting a blocked proposal as awaiting
        confirmation invites a user to confirm something that cannot run."""
        stage_payload["blockers"] = [
            {"code": "INSUFFICIENT_BALANCE", "message": "Bakiye yetersiz.",
             "is_user_resolvable": True}
        ]
        fake_backend.json("stage", stage_payload)
        with pytest.raises(ContractViolationError, match="blockers"):
            await stage(stage_args)

    async def test_rejected_status_may_carry_blockers(
        self, fake_backend, stage_payload, stage_args
    ):
        stage_payload["status"] = "REJECTED_VALIDATION"
        stage_payload["blockers"] = [{"code": "MARKET_CLOSED", "message": "Piyasa kapalı."}]
        fake_backend.json("stage", stage_payload)
        payload = await stage(stage_args)
        assert payload["status"] == "REJECTED_VALIDATION"
        assert payload["blockers"][0]["code"] == "MARKET_CLOSED"

    async def test_requires_input_carries_missing_fields(
        self, fake_backend, stage_payload, stage_args
    ):
        stage_payload["status"] = "REQUIRES_ADDITIONAL_INPUT"
        stage_payload["missing_fields"] = ["quantity"]
        fake_backend.json("stage", stage_payload)
        payload = await stage(stage_args)
        assert payload["missing_fields"] == ["quantity"]


# ==========================================================================
# Payload shape
# ==========================================================================
class TestPayloadShape:
    async def test_exact_top_level_contract(self, stage_args, proposal_top_level_keys):
        assert set(await stage(stage_args)) == proposal_top_level_keys

    async def test_carries_no_market_data_fields(self, stage_args):
        """Pricing lives inside estimate under distinct names, deliberately,
        so the router never mistakes a staging estimate for a quote."""
        assert_no_market_data_fields(await stage(stage_args))

    async def test_unknown_backend_fields_are_dropped(
        self, fake_backend, stage_payload, stage_args
    ):
        stage_payload["internal_order_ref"] = "ORD-999"
        fake_backend.json("stage", stage_payload)
        assert "internal_order_ref" not in await stage(stage_args)

    async def test_missing_optional_blocks_default_safely(
        self, fake_backend, stage_payload, stage_args
    ):
        fake_backend.json(
            "stage",
            without(stage_payload, "summary", "impact", "blockers", "warnings",
                    "missing_fields", "disclosures", "expires_at", "audit_id"),
        )
        payload = await stage(stage_args)
        assert payload["summary"] == {}
        assert payload["impact"] is None
        assert payload["blockers"] == []
        assert payload["warnings"] == []
        assert payload["missing_fields"] == []
        assert payload["disclosures"] == []
        assert payload["expires_at"] == ""
        assert payload["audit_id"] == ""

    async def test_disclosures_pass_through_verbatim(self, stage_args):
        """Presented alongside the proposal, unedited."""
        payload = await stage(stage_args)
        assert payload["disclosures"] == [
            "Emir, ekrandaki onay adımı tamamlanmadan iletilmez."
        ]

    @pytest.mark.parametrize("missing", ["proposal_id", "status"])
    async def test_missing_identity_fields_are_a_violation(
        self, fake_backend, stage_payload, stage_args, missing
    ):
        fake_backend.json("stage", without(stage_payload, missing))
        with pytest.raises(ContractViolationError, match=missing):
            await stage(stage_args)


# ==========================================================================
# The cost estimate
# ==========================================================================
class TestEstimate:
    async def test_estimate_passes_through(self, stage_args):
        estimate = (await stage(stage_args))["estimate"]
        assert estimate["gross_amount"] == 29175.00
        assert estimate["total_cost"] == 29205.64
        assert estimate["fees"][0]["name"] == "Aracı kurum komisyonu"

    async def test_price_certainty_defaults_to_indicative(
        self, fake_backend, stage_payload, stage_args
    ):
        """FIRM removes the obligation to disclose that the executed price will
        differ, so it is never assumed: the backend has to say so."""
        del stage_payload["estimate"]["price_certainty"]
        fake_backend.json("stage", stage_payload)
        assert (await stage(stage_args))["estimate"]["price_certainty"] == "INDICATIVE"

    @pytest.mark.parametrize("value", ["indicative", "PROBABLE", "", None, "guaranteed"])
    async def test_unrecognised_certainty_falls_back_to_indicative(
        self, fake_backend, stage_payload, stage_args, value
    ):
        stage_payload["estimate"]["price_certainty"] = value
        fake_backend.json("stage", stage_payload)
        assert (await stage(stage_args))["estimate"]["price_certainty"] == "INDICATIVE"

    @pytest.mark.parametrize("value", ["FIRM", "firm"])
    async def test_firm_is_honoured_when_stated(
        self, fake_backend, stage_payload, stage_args, value
    ):
        stage_payload["estimate"]["price_certainty"] = value
        fake_backend.json("stage", stage_payload)
        assert (await stage(stage_args))["estimate"]["price_certainty"] == "FIRM"

    async def test_fee_and_tax_lists_default_to_empty(
        self, fake_backend, stage_payload, stage_args
    ):
        stage_payload["estimate"] = {"gross_amount": 100.0, "currency": "TRY"}
        fake_backend.json("stage", stage_payload)
        estimate = (await stage(stage_args))["estimate"]
        assert estimate["fees"] == []
        assert estimate["taxes"] == []
        assert estimate["fx"] is None

    async def test_absent_estimate_is_none_not_an_empty_object(
        self, fake_backend, stage_payload, stage_args
    ):
        """A REJECTED_VALIDATION proposal has no costing. None says "not
        computed"; {} would read as "computed, and free"."""
        stage_payload["status"] = "REJECTED_VALIDATION"
        fake_backend.json("stage", without(stage_payload, "estimate"))
        assert (await stage(stage_args))["estimate"] is None

    @pytest.mark.parametrize("bad", ["estimate", 42, [], True])
    async def test_non_object_estimate_is_a_violation(
        self, fake_backend, stage_payload, stage_args, bad
    ):
        stage_payload["estimate"] = bad
        fake_backend.json("stage", stage_payload)
        with pytest.raises(ContractViolationError, match="estimate"):
            await stage(stage_args)


# ==========================================================================
# Failure propagation
# ==========================================================================
class TestFailures:
    async def test_staging_outage_raises_rather_than_reporting_pending(
        self, fake_backend, stage_args
    ):
        """FAIL CLOSED. An unstaged transaction must never be described as
        pending, because the user would then wait for a confirmation prompt
        that never arrives."""
        fake_backend.status("stage", 503)
        with pytest.raises(UpstreamUnavailableError):
            await stage(stage_args)

    async def test_no_transaction_entitlement_raises(self, fake_backend, stage_args):
        fake_backend.status("stage", 403)
        with pytest.raises(AuthorizationError):
            await stage(stage_args)
        assert fake_backend.attempts == 1, "never retry, never try another account"

    async def test_backend_rejection_raises_invalid_input(self, fake_backend, stage_args):
        fake_backend.status("stage", 422, {"error": "InvalidInputError"})
        with pytest.raises(InvalidInputError):
            await stage(stage_args)

    async def test_timeout_raises(self, fake_backend, stage_args):
        fake_backend.fail("stage", httpx.ReadTimeout("staging slow"))
        with pytest.raises(UpstreamUnavailableError):
            await stage(stage_args)

    async def test_retry_reuses_the_same_idempotency_key(self, fake_backend, stage_args):
        """A retry that generates a fresh key would create a duplicate
        proposal, which is the exact failure the key exists to prevent."""
        fake_backend.set(
            "stage",
            httpx.Response(503, json={"error": "restarting"}),
            httpx.Response(503, json={"error": "restarting"}),
        )
        with pytest.raises(UpstreamUnavailableError):
            await stage(stage_args)
        keys = {r.headers.get("idempotency-key") for r in fake_backend.requests}
        assert keys == {"idem_abc123"}
        assert fake_backend.attempts == 2


# ==========================================================================
# Registration
# ==========================================================================
class TestRegistration:
    async def test_register_attaches_the_tool(self, mocker):
        fake_mcp = mocker.MagicMock()
        transaction_tools.register(fake_mcp)
        fake_mcp.tool.assert_called_once_with()
        fake_mcp.tool.return_value.assert_called_once_with(
            transaction_tools.prepare_transaction_proposal
        )

    async def test_the_tool_is_a_coroutine_function(self):
        import inspect

        assert inspect.iscoroutinefunction(transaction_tools.prepare_transaction_proposal)

    async def test_status_enum_matches_the_contract(self):
        assert transaction_tools.STATUSES == frozenset({
            "PENDING_USER_CONFIRMATION", "REJECTED_VALIDATION", "REQUIRES_ADDITIONAL_INPUT",
        })

    async def test_module_exposes_no_execution_path(self):
        """Settlement lives behind the frontend confirmation control, in a
        separate service. A function here whose name suggests otherwise is a
        design regression worth failing on."""
        forbidden = ("execute", "submit_order", "settle", "confirm", "place_order")
        names = [n for n in vars(transaction_tools) if callable(vars(transaction_tools)[n])]
        for name in names:
            assert not any(word in name.lower() for word in forbidden), name
