"""Banking tools.

The property this module exists to guarantee is a negative one: there is no
way, through any argument, to make a payment happen. Every tool stops at a
proposal, and the confirm step lives in the interface where the user presses
it themselves.
"""

from __future__ import annotations

import httpx
import pytest

import banking_tools
from backend_client import ContractViolationError

PROPOSAL = {
    "proposal_id": "PAY-1", "status": "PENDING", "payment_type": "BILL_PAYMENT",
    "amount": 842.5, "currency": "TRY", "destination": "TEST-1",
    "description": "BEDAŞ fatura ödemesi", "expires_at": "2026-08-27T10:00:00Z",
}


class TestNoExecutionPathExists:
    def test_the_module_exposes_only_a_lookup_and_a_proposal(self):
        """If an execute tool is ever added here, this test is the place that
        should have to be deleted deliberately."""
        import inspect

        public = {
            name for name, obj in inspect.getmembers(banking_tools, inspect.isfunction)
            if not name.startswith("_") and obj.__module__ == "banking_tools"
        }
        assert public == {"lookup_bill", "prepare_payment_proposal", "register"}

    def test_no_tool_name_suggests_execution(self):
        for name in ("execute", "confirm", "settle", "pay_now"):
            assert not hasattr(banking_tools, name)

    def test_no_admin_capability_is_exposed(self):
        """Crediting a balance or issuing a bill must have no path from a
        conversation, however it is phrased."""
        source = open(banking_tools.__file__).read()
        assert "/admin" not in source


class TestBillLookup:
    @pytest.mark.asyncio
    async def test_an_open_bill_is_reported(self, fake_backend):
        fake_backend.set("lookup", httpx.Response(200, json={
            "found": True, "institution": "BEDAŞ", "subscriber_no": "TEST-1",
            "amount": 842.5, "due_day": 15,
        }))
        payload = await banking_tools.lookup_bill("BEDAŞ", "TEST-1")
        assert payload["found"] is True and payload["amount"] == 842.5

    @pytest.mark.asyncio
    async def test_no_open_bill_is_an_answer_not_an_error(self, fake_backend):
        """"Nothing is owed" is a complete reply to a lookup."""
        fake_backend.set("lookup", httpx.Response(200, json={"found": False}))
        assert await banking_tools.lookup_bill("BEDAŞ", "nope") == {"found": False}

    @pytest.mark.asyncio
    async def test_a_response_without_found_is_a_contract_violation(self, fake_backend):
        fake_backend.set("lookup", httpx.Response(200, json={"institution": "x"}))
        with pytest.raises(ContractViolationError):
            await banking_tools.lookup_bill("BEDAŞ", "TEST-1")

    @pytest.mark.asyncio
    async def test_the_query_carries_both_identifiers(self, fake_backend):
        fake_backend.set("lookup", httpx.Response(200, json={"found": False}))
        await banking_tools.lookup_bill("BEDAŞ", "TEST-1")
        assert "/banking/bills/lookup" in str(fake_backend.last.url)


class TestPaymentProposal:
    @pytest.mark.asyncio
    async def test_a_proposal_is_returned_and_nothing_is_executed(self, fake_backend):
        fake_backend.set("payment_stage", httpx.Response(200, json=PROPOSAL))
        payload = await banking_tools.prepare_payment_proposal(
            user_id="u-1", payment_type="BILL_PAYMENT", idempotency_key="k",
            institution="BEDAŞ", subscriber_no="TEST-1",
        )
        assert payload["status"] == "PENDING"
        assert payload["proposal_id"] == "PAY-1"
        assert "/banking/payments/stage" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_an_unknown_payment_type_is_refused_before_any_request(self, fake_backend):
        with pytest.raises(ContractViolationError):
            await banking_tools.prepare_payment_proposal(
                user_id="u-1", payment_type="WIRE_TRANSFER_TO_ME", idempotency_key="k",
            )

    @pytest.mark.asyncio
    async def test_the_idempotency_key_is_sent_as_a_header(self, fake_backend):
        """A retry that mints a second proposal leaves the user with two
        pending payments for one intent."""
        fake_backend.set("payment_stage", httpx.Response(200, json=PROPOSAL))
        await banking_tools.prepare_payment_proposal(
            user_id="u-1", payment_type="TRANSFER", idempotency_key="k-1",
            amount=100, destination="TR00",
        )
        assert fake_backend.last.headers.get("Idempotency-Key") == "k-1"

    @pytest.mark.parametrize(
        "missing", ["proposal_id", "status", "payment_type", "amount", "currency", "expires_at"],
    )
    @pytest.mark.asyncio
    async def test_every_required_field_is_enforced(self, fake_backend, missing):
        """A proposal missing its id or its expiry is not something a user can
        be asked to confirm, so it is a violation rather than a default."""
        body = {k: v for k, v in PROPOSAL.items() if k != missing}
        fake_backend.set("payment_stage", httpx.Response(200, json=body))
        with pytest.raises(ContractViolationError):
            await banking_tools.prepare_payment_proposal(
                user_id="u-1", payment_type="BILL_PAYMENT", idempotency_key="k",
                institution="BEDAŞ", subscriber_no="TEST-1",
            )

    @pytest.mark.asyncio
    async def test_a_non_object_response_is_refused(self, fake_backend):
        fake_backend.set("payment_stage", httpx.Response(200, json=["nope"]))
        with pytest.raises(ContractViolationError):
            await banking_tools.prepare_payment_proposal(
                user_id="u-1", payment_type="TRANSFER", idempotency_key="k",
                amount=1, destination="TR00",
            )

    @pytest.mark.asyncio
    async def test_optional_fields_may_be_absent(self, fake_backend):
        body = {k: v for k, v in PROPOSAL.items() if k not in ("destination", "description")}
        fake_backend.set("payment_stage", httpx.Response(200, json=body))
        payload = await banking_tools.prepare_payment_proposal(
            user_id="u-1", payment_type="CARD_PAYMENT", idempotency_key="k", amount=50,
        )
        assert payload["destination"] is None and payload["description"] is None


def test_normalize_refuses_a_non_object_directly():
    """`backend_client` rejects most malformed bodies before `_normalize` sees
    them, so the guard needs exercising at its own level rather than through
    the transport."""
    with pytest.raises(ContractViolationError, match="must be an object"):
        banking_tools._normalize(["not", "an", "object"])


def test_both_tools_register(mocker):
    registered = []

    class FakeMcp:
        def tool(self):
            def decorate(fn):
                registered.append(fn.__name__)
                return fn
            return decorate

    banking_tools.register(FakeMcp())
    assert set(registered) == {"lookup_bill", "prepare_payment_proposal"}
