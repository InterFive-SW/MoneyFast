"""Banking endpoints.

The authorization rules matter as much as the arithmetic: an account you do
not own must be indistinguishable from one that does not exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id
from app.main import app
from app.modules.banking import service

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def bank_account(user_id="user-1", number="1000000000001", balance=50000.0):
    return SimpleNamespace(
        id="acc-1", user_id=user_id, account_number=number,
        iban="TR00" + number.zfill(16), account_type="vadesiz",
        currency_code="TRY", balance=balance, status="active", updated_at=None,
    )


@pytest.fixture
def bank_client():
    db = MagicMock(spec=Session)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    try:
        with TestClient(app) as client:
            client.db = db
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user_id, None)


class TestAccounts:
    def test_the_users_accounts_are_listed(self, bank_client, mocker):
        mocker.patch.object(service, "accounts_for", return_value=[bank_account()])
        body = bank_client.get("/api/banking/accounts").json()
        assert body[0]["account_number"] == "1000000000001"
        assert body[0]["balance"] == 50000.0

    def test_a_user_with_no_account_gets_one_opened(self, bank_client, mocker):
        """Otherwise a registered user simply cannot transfer, with no way to
        fix it from the UI."""
        opened = bank_account()
        mocker.patch.object(service, "accounts_for", side_effect=[[], [opened]])
        ensure = mocker.patch.object(service, "ensure_account", return_value=opened)
        body = bank_client.get("/api/banking/accounts").json()
        assert ensure.called
        assert body[0]["account_number"] == "1000000000001"


class TestTransfers:
    def _result(self):
        return {
            "reference_number": "TRF-ABC123", "status": "completed",
            "amount": 250.0, "fee": 2.5, "currency": "TRY",
            "source_balance_after": 49747.5, "destination_account": "1000000000002",
        }

    def test_a_transfer_returns_its_reference_and_new_balance(self, bank_client, mocker):
        mocker.patch.object(service, "transfer", return_value=self._result())
        body = bank_client.post(
            "/api/banking/transfers",
            json={"source": "1000000000001", "destination": "1000000000002", "amount": 250},
        ).json()
        assert body["reference_number"] == "TRF-ABC123"
        assert body["source_balance_after"] == 49747.5

    def test_the_source_defaults_to_the_callers_own_account(self, bank_client, mocker):
        """A user with one account should not have to look up its number to
        move their own money."""
        mocker.patch.object(service, "ensure_account", return_value=bank_account())
        transfer = mocker.patch.object(service, "transfer", return_value=self._result())
        bank_client.post(
            "/api/banking/transfers",
            json={"destination": "1000000000002", "amount": 100},
        )
        assert transfer.call_args.kwargs["source_reference"] == "1000000000001"

    def test_a_refused_transfer_is_a_422_carrying_the_reason(self, bank_client, mocker):
        """The user needs to know it was the balance, not a server fault."""
        mocker.patch.object(
            service, "transfer",
            side_effect=service.TransferError("Bakiye yetersiz: ..."),
        )
        response = bank_client.post(
            "/api/banking/transfers",
            json={"source": "1000000000001", "destination": "1000000000002", "amount": 999999},
        )
        assert response.status_code == 422
        assert "Bakiye yetersiz" in response.json()["detail"]
        assert bank_client.db.rollback.called

    @pytest.mark.parametrize("amount", [0, -5])
    def test_a_non_positive_amount_is_rejected_by_the_schema(self, bank_client, amount):
        response = bank_client.post(
            "/api/banking/transfers",
            json={"destination": "1000000000002", "amount": amount},
        )
        assert response.status_code == 422

    def test_a_missing_destination_is_rejected(self, bank_client):
        response = bank_client.post("/api/banking/transfers", json={"amount": 100})
        assert response.status_code == 422


class TestStatement:
    def _leg(self, direction="DEBIT"):
        return SimpleNamespace(
            direction=direction, amount=250.0, balance_after=49747.5,
            counterparty_iban="TR002", description="kira", created_at=NOW,
        )

    def test_movements_are_listed_for_an_owned_account(self, bank_client, mocker):
        mocker.patch.object(service, "find_account", return_value=bank_account())
        bank_client.db.execute.return_value.all.return_value = [
            (self._leg(), SimpleNamespace(reference_number="TRF-1"))
        ]
        body = bank_client.get("/api/banking/accounts/1000000000001/statement").json()
        assert body["balance"] == 50000.0
        assert body["movements"][0]["direction"] == "DEBIT"
        assert body["movements"][0]["reference_number"] == "TRF-1"

    def test_someone_elses_account_is_a_404_not_a_403(self, bank_client, mocker):
        """Confirming the account exists but belongs to another person is
        already more than the caller should learn."""
        mocker.patch.object(service, "find_account", return_value=bank_account(user_id="other"))
        assert bank_client.get("/api/banking/accounts/1000000000001/statement").status_code == 404

    def test_an_unknown_account_is_a_404(self, bank_client, mocker):
        mocker.patch.object(service, "find_account", return_value=None)
        assert bank_client.get("/api/banking/accounts/NOPE/statement").status_code == 404

    def test_the_limit_is_bounded(self, bank_client):
        response = bank_client.get("/api/banking/accounts/1000000000001/statement?limit=99999")
        assert response.status_code == 422
