"""Confirmation of a staged transaction proposal.

This endpoint is the system's one legitimate place for a user to say yes. The
MCP contract calls explicit confirmation non-delegable: the agent may never
confirm, and conversational assent ("evet", "onaylıyorum") is not confirmation.
The tests below pin the checks that make that claim true — a proposal must
exist, belong to the caller, and still be alive.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_optional_user_id
from app.main import app

URL = "/api/investment/transactions/{}/confirm"


def make_proposal(**overrides):
    proposal = SimpleNamespace(
        id="PROP-ABC123",
        user_id="user-1",
        status="PENDING_USER_CONFIRMATION",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        confirmed_at=None,
        cancelled_at=None,
        # Settlement reads these. The tests in this file are about who may
        # confirm and when — settlement itself is exercised in
        # test_settlement.py against the real function.
        transaction_type="BUY",
        symbol="THYAO",
        quantity=10,
        source_account_id="TR-TEST-0001",
        destination_account_id=None,
        # Emir türü artık onay yolunu ayırıyor: piyasa emri hemen
        # gerçekleşiyor, limit emri `WAITING_PRICE`ta bekliyor.
        order_type="MARKET",
        limit_price=None,
        created_at=datetime.now(timezone.utc),
        payload={"estimate": {"net_amount": 3022.26, "reference_price": 301.75}},
    )
    for key, value in overrides.items():
        setattr(proposal, key, value)
    return proposal


@pytest.fixture
def confirm_client(proposal_or_none, caller_id, mocker):
    """TestClient whose db.get resolves to a staged proposal.

    Settlement is stubbed: these tests pin down authorization, expiry and
    idempotency. What the settlement itself does to cash and holdings is
    covered in test_settlement.py.
    """
    from fastapi.testclient import TestClient
    from app.modules.investment import market_service, service

    from app.modules.auth.models import User

    db = MagicMock(spec=Session)
    # `db.get` MODELE göre cevap veriyor: onay yolu önce öneriyi, sonra
    # e-posta tercihi için kullanıcıyı okuyor ve ikisine aynı nesneyi
    # döndürmek öneriyi kullanıcı sanan bir hata üretiyordu.
    db.get.side_effect = lambda model, _key: (
        SimpleNamespace(id="user-1", email="", notification_preferences={})
        if model is User else proposal_or_none
    )
    mocker.patch.object(
        market_service, "account", return_value=SimpleNamespace(id="acct-1", cash_balance=25000.0, currency_code="TRY", account_number="TR-TEST-0001")
    )
    mocker.patch.object(
        service, "settle",
        return_value={"direction": "BUY", "symbol": "THYAO", "quantity": 10,
                      "cash_delta": -3022.26, "cash_after": 21977.74},
    )
    # Onay iki adımdan geçiyor: blokaj, sonra takas. İkisi de burada
    # sahte -- bu dosya KİMİN ve NE ZAMAN onaylayabileceğini sabitliyor.
    mocker.patch.object(
        service, "block_funds",
        return_value={"cash_after": 21977.74, "cash_delta": -3022.26},
    )
    mocker.patch.object(service, "finalize_settlement")
    mocker.patch("app.modules.investment.router.send_transaction_request_email")

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_optional_user_id] = lambda: caller_id
    try:
        with TestClient(app) as client:
            client.db = db
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_optional_user_id, None)


@pytest.fixture
def caller_id():
    return "user-1"


class TestHappyPath:
    @pytest.mark.parametrize("proposal_or_none", [make_proposal()])
    def test_live_proposal_is_confirmed(self, confirm_client, proposal_or_none):
        response = confirm_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert proposal_or_none.confirmed_at is not None
        assert proposal_or_none.status == "CONFIRMED"

    @pytest.mark.parametrize(
        "proposal_or_none",
        [make_proposal(status="CONFIRMED", confirmed_at=datetime.now(timezone.utc))]
    )
    def test_confirming_twice_is_idempotent(self, confirm_client):
        """The user cannot tell whether their first press registered, so a
        second one reports the same outcome rather than an error."""
        response = confirm_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"


class TestRefusals:
    @pytest.mark.parametrize("proposal_or_none", [None])
    def test_unknown_proposal_is_rejected(self, confirm_client):
        """A proposal_id the client invented must not be honoured."""
        assert confirm_client.post(URL.format("PROP-MADE-UP")).status_code == 404

    @pytest.mark.parametrize("proposal_or_none", [make_proposal(user_id="someone-else")])
    def test_another_users_proposal_is_indistinguishable_from_missing(self, confirm_client):
        """404 rather than 403: a 403 would confirm the proposal exists, which
        is already more than this caller should learn."""
        response = confirm_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 404
        assert "bulunamadı" in response.json()["detail"]

    @pytest.mark.parametrize(
        "proposal_or_none",
        [make_proposal(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))],
    )
    def test_expired_proposal_is_rejected(self, confirm_client, proposal_or_none):
        """Prices move. Confirming a stale proposal would execute against
        figures the user was shown a quarter of an hour ago."""
        response = confirm_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 410
        assert proposal_or_none.confirmed_at is None

    @pytest.mark.parametrize(
        "proposal_or_none",
        [make_proposal(expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).replace(tzinfo=None))],
    )
    def test_naive_expiry_timestamp_is_still_compared_correctly(self, confirm_client):
        """Some drivers hand back a naive datetime. Comparing it to an aware
        `now` raises TypeError, which would surface as a 500 and let the
        caller retry into an unhandled path."""
        assert confirm_client.post(URL.format("PROP-ABC123")).status_code == 410

    @pytest.mark.parametrize(
        "proposal_or_none", [make_proposal(cancelled_at=datetime.now(timezone.utc))]
    )
    def test_cancelled_proposal_is_rejected(self, confirm_client, proposal_or_none):
        response = confirm_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 409
        assert proposal_or_none.confirmed_at is None


class TestAnonymousCaller:
    @pytest.mark.parametrize("proposal_or_none", [make_proposal(user_id="user-1")])
    @pytest.mark.parametrize("caller_id", [None])
    def test_anonymous_caller_cannot_confirm_an_owned_proposal(self, confirm_client):
        assert confirm_client.post(URL.format("PROP-ABC123")).status_code == 404

    @pytest.mark.parametrize("proposal_or_none", [make_proposal(user_id=None)])
    @pytest.mark.parametrize("caller_id", [None])
    def test_unowned_proposal_may_be_confirmed_anonymously(self, confirm_client):
        """Staged before login. There is no owner to protect, so the expiry
        window is the only gate."""
        assert confirm_client.post(URL.format("PROP-ABC123")).status_code == 200


class TestStagingPersistence:
    """A proposal has to be recorded for the confirm step to be verifiable."""

    def _client(self, existing, mocker):
        from fastapi.testclient import TestClient

        from app.modules.investment import market_service

        db = MagicMock(spec=Session)
        db.get.return_value = existing
        # Staging now resolves the symbol and prices it from the live quote
        # before validating, so both lookups have to be staged.
        mocker.patch.object(
            market_service, "resolve_symbol",
            return_value=SimpleNamespace(symbol="THYAO", currency_code="TRY"),
        )
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={"THYAO": {"price": 304.0}},
        )
        mocker.patch.object(
            market_service, "holdings",
            return_value=[{"symbol": "THYAO", "quantity": 120.0}],
        )
        # Staging now checks a buy against the balance, so the account has to
        # be able to afford the order or nothing is persisted.
        mocker.patch.object(
            market_service, "account",
            return_value=SimpleNamespace(id="acct-1", cash_balance=1_000_000.0, currency_code="TRY", account_number="TR-TEST-0001"),
        )
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        client.db = db
        return client

    @staticmethod
    def _body(**overrides):
        body = {
            "user_id": "user-1",
            "transaction_type": "BUY",
            "source_account_id": "TEST-ACC-BIST-001",
            "idempotency_key": "idem-persist-1",
            "instrument": {"symbol": "THYAO"},
            "quantity": 10,
        }
        body.update(overrides)
        return body

    def test_confirmable_proposal_is_stored(self, mocker):
        client = self._client(existing=None, mocker=mocker)
        try:
            response = client.post("/api/investment/transactions/stage", json=self._body())
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        stored = client.db.add.call_args.args[0]
        assert stored.id == response.json()["proposal_id"]
        assert stored.status == "PENDING_USER_CONFIRMATION"
        assert stored.symbol == "THYAO"
        assert stored.expires_at.tzinfo is not None
        assert client.db.commit.called

    def test_rejected_proposal_is_not_stored(self, mocker):
        """A refusal is a message to the user, not something to act on later.
        Storing it would give the client a proposal_id to confirm."""
        client = self._client(existing=None, mocker=mocker)
        try:
            response = client.post(
                "/api/investment/transactions/stage",
                json=self._body(transaction_type="SELL", quantity=99999),
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.json()["status"] == "REJECTED_VALIDATION"
        assert client.db.add.called is False

    def test_incomplete_proposal_is_not_stored(self, mocker):
        client = self._client(existing=None, mocker=mocker)
        try:
            response = client.post(
                "/api/investment/transactions/stage", json=self._body(instrument=None)
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.json()["status"] == "REQUIRES_ADDITIONAL_INPUT"
        assert client.db.add.called is False

    def test_retry_with_the_same_key_does_not_create_a_second_row(self, mocker):
        """The whole point of the idempotency key. Two pending proposals for
        one intent would show the user two orders to confirm."""
        client = self._client(existing=make_proposal(), mocker=mocker)
        try:
            client.post("/api/investment/transactions/stage", json=self._body())
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert client.db.add.called is False


class TestSettlementFailuresAtConfirm:
    """Confirm applies the trade. When it cannot, nothing may be marked done."""

    @pytest.fixture
    def settle_client(self, mocker):
        from fastapi.testclient import TestClient
        from app.modules.investment import market_service, service

        db = MagicMock(spec=Session)
        db.get.return_value = make_proposal(user_id=None)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_optional_user_id] = lambda: None
        self.db = db
        self.market_service = market_service
        self.service = service
        try:
            with TestClient(app) as client:
                client.db = db
                yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_optional_user_id, None)

    def test_no_account_is_a_409_and_the_proposal_stays_pending(self, settle_client, mocker):
        mocker.patch.object(self.market_service, "account", return_value=None)
        response = settle_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 409
        assert settle_client.db.get.return_value.status == "PENDING_USER_CONFIRMATION"
        assert not settle_client.db.commit.called

    def test_a_settlement_refusal_rolls_back_and_reports_the_reason(
        self, settle_client, mocker
    ):
        """The balance can change between staging and confirming — a second
        proposal staged against the same cash, for instance. The user is told
        why rather than seeing a generic failure."""
        mocker.patch.object(
            self.market_service, "account",
            return_value=SimpleNamespace(id="acct-1", cash_balance=10.0, currency_code="TRY", account_number="TR-TEST-0001"),
        )
        mocker.patch.object(
            self.service, "settle",
            side_effect=self.service.SettlementError("Bakiye yetersiz: ..."),
        )
        response = settle_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 409
        assert "Bakiye yetersiz" in response.json()["detail"]
        assert settle_client.db.rollback.called
        assert settle_client.db.get.return_value.status == "PENDING_USER_CONFIRMATION"


class TestTransferConfirmation:
    """A transfer settles against the banking ledger, not the investment
    account. Routing it through securities settlement is what produced a
    "Satım" with a blank ticker priced with brokerage commission."""

    @pytest.fixture
    def transfer_client(self, mocker):
        from fastapi.testclient import TestClient
        from app.modules.banking import service as banking_service

        db = MagicMock(spec=Session)
        db.get.return_value = make_proposal(
            transaction_type="TRANSFER",
            symbol=None,
            quantity=None,
            source_account_id="1000000000001",
            destination_account_id="1000000000002",
            payload={"estimate": {"net_amount": 300.0, "currency": "TRY"}},
        )
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_optional_user_id] = lambda: "user-1"
        self.banking = banking_service
        try:
            with TestClient(app) as client:
                client.db = db
                yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_optional_user_id, None)

    def test_a_confirmed_transfer_moves_money_through_the_ledger(
        self, transfer_client, mocker
    ):
        transfer = mocker.patch.object(
            self.banking, "transfer",
            return_value={
                "reference_number": "TRF-ABC", "status": "completed",
                "amount": 300.0, "fee": 2.5, "currency": "TRY",
                "source_balance_after": 47697.5, "destination_account": "1000000000002",
            },
        )
        body = transfer_client.post(URL.format("PROP-ABC123")).json()
        assert body["status"] == "confirmed"
        assert "TRF-ABC" in body["message"], "the receipt number is the audit trail"
        assert transfer.call_args.kwargs["amount"] == 300.0

    def test_a_refused_transfer_leaves_the_proposal_pending(self, transfer_client, mocker):
        mocker.patch.object(
            self.banking, "transfer",
            side_effect=self.banking.TransferError("Bakiye yetersiz: ..."),
        )
        response = transfer_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 409
        assert "Bakiye yetersiz" in response.json()["detail"]
        assert transfer_client.db.get.return_value.status == "PENDING_USER_CONFIRMATION"

    def test_a_transfer_without_an_amount_is_refused(self, transfer_client, mocker):
        transfer_client.db.get.return_value.payload = {}
        response = transfer_client.post(URL.format("PROP-ABC123"))
        assert response.status_code == 409

    def test_securities_settlement_is_not_used_for_a_transfer(
        self, transfer_client, mocker
    ):
        from app.modules.investment import service as investment_service

        settle = mocker.patch.object(investment_service, "settle")
        mocker.patch.object(
            self.banking, "transfer",
            return_value={
                "reference_number": "TRF-ABC", "status": "completed",
                "amount": 300.0, "fee": 0.0, "currency": "TRY",
                "source_balance_after": 100.0, "destination_account": "x",
            },
        )
        transfer_client.post(URL.format("PROP-ABC123"))
        assert not settle.called
