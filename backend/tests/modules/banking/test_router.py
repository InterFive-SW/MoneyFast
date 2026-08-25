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


class TestSpendingEndpoint:
    def test_categories_and_total_are_reported(self, bank_client, mocker):
        mocker.patch.object(
            service, "spending_by_category",
            side_effect=[
                [{"category": "Market", "amount": 5000.0}],
                [{"category": "Market", "amount": 9000.0}],  # both windows
            ],
        )
        body = bank_client.get("/api/banking/spending").json()
        assert body["total_expense"] == 5000.0
        assert body["categories"][0]["category"] == "Market"

    def test_the_trend_compares_against_the_previous_window(self, bank_client, mocker):
        # Current 5.000; both windows 9.000 → earlier 4.000 → +25%.
        mocker.patch.object(
            service, "spending_by_category",
            side_effect=[
                [{"category": "Market", "amount": 5000.0}],
                [{"category": "Market", "amount": 9000.0}],
            ],
        )
        assert bank_client.get("/api/banking/spending").json()["change_percent"] == 25.0

    def test_a_first_window_reports_no_trend_rather_than_zero(self, bank_client, mocker):
        """0% claims spending was flat; None says there is nothing to compare."""
        mocker.patch.object(service, "spending_by_category", side_effect=[[], []])
        assert bank_client.get("/api/banking/spending").json()["change_percent"] is None

    def test_the_window_is_bounded(self, bank_client):
        assert bank_client.get("/api/banking/spending?days=9999").status_code == 422


class TestBalanceHistoryEndpoint:
    def _points(self, mocker, points, balance=132785.38):
        mocker.patch.object(service, "balance_history", return_value=points)
        mocker.patch.object(
            service, "accounts_for",
            return_value=[SimpleNamespace(balance=balance, currency_code="TRY")],
        )

    def test_the_sparkline_and_total_are_returned(self, bank_client, mocker):
        self._points(mocker, [{"at": NOW, "balance": 100000.0}, {"at": NOW, "balance": 132785.38}])
        body = bank_client.get("/api/banking/balance-history").json()
        assert body["total"] == 132785.38
        assert len(body["points"]) == 2

    def test_the_change_is_measured_from_the_oldest_point(self, bank_client, mocker):
        self._points(mocker, [{"at": NOW, "balance": 100000.0}], balance=110000.0)
        body = bank_client.get("/api/banking/balance-history").json()
        assert body["change_amount"] == 10000.0
        assert body["change_percent"] == 10.0

    def test_a_negative_opening_balance_yields_no_percentage(self, bank_client, mocker):
        """Dividing by a negative opening balance produces a percentage that
        reads backwards."""
        self._points(mocker, [{"at": NOW, "balance": -5000.0}], balance=1000.0)
        assert bank_client.get("/api/banking/balance-history").json()["change_percent"] is None

    def test_no_history_is_not_an_error(self, bank_client, mocker):
        self._points(mocker, [])
        body = bank_client.get("/api/banking/balance-history").json()
        assert body["points"] == []
        assert body["change_amount"] == 0.0


class TestSavingsGoalsEndpoint:
    def test_goals_are_listed(self, bank_client, mocker):
        mocker.patch.object(
            service, "goals_for",
            return_value=[SimpleNamespace(
                id="g1", name="Araba", target_amount=500000.0, current_amount=150000.0,
                currency_code="TRY", icon="🚗", color="#10b981", deadline="2028-01",
            )],
        )
        body = bank_client.get("/api/banking/savings-goals").json()
        assert body[0]["name"] == "Araba"
        assert body[0]["target_amount"] == 500000.0

    def test_a_goal_can_be_created(self, bank_client):
        # A real session populates the client-side column defaults at flush;
        # the double has to stand in for that or the response cannot validate.
        def _refresh(goal):
            goal.id = goal.id or "g-new"
            goal.currency_code = goal.currency_code or "TRY"

        bank_client.db.refresh.side_effect = _refresh

        response = bank_client.post(
            "/api/banking/savings-goals",
            json={"name": "Tatil", "target_amount": 80000, "current_amount": 1000},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Tatil"
        assert bank_client.db.add.called

    def test_a_goal_must_have_a_positive_target(self, bank_client):
        """A zero target makes the progress bar divide by zero."""
        response = bank_client.post(
            "/api/banking/savings-goals", json={"name": "X", "target_amount": 0},
        )
        assert response.status_code == 422
