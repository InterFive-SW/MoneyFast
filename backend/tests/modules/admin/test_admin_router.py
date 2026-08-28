"""The admin HTTP surface.

Exercised through the app so the `require_admin` dependency is really in the
chain -- a service-level test would pass just as happily on an endpoint whose
gate had been forgotten.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.admin import service
from app.modules.admin.deps import require_admin


@pytest.fixture
def admin_client(client):
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
        id="a-1", username="admin", full_name="Sistem Yöneticisi", is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


class TestGateIsWiredIn:
    @pytest.mark.parametrize("method,path", [
        ("get", "/api/admin/users"),
        ("get", "/api/admin/bills"),
        ("post", "/api/admin/bills"),
        ("post", "/api/admin/users/u-1/cash"),
        ("post", "/api/admin/users/u-1/positions"),
        ("delete", "/api/admin/bills/b-1"),
    ])
    def test_every_route_refuses_an_unauthenticated_caller(self, client, method, path):
        # GET and DELETE take no body on this client.
        call = getattr(client, method)
        response = call(path) if method in {'get', 'delete'} else call(path, json={})
        assert response.status_code == 401


class TestLogin:
    def test_a_wrong_password_is_refused(self, client, mocker):
        from app.modules.admin import router as admin_router

        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            username="admin", hashed_password="hash", is_active=True, full_name="x",
        )
        app.dependency_overrides[get_db] = lambda: db
        mocker.patch.object(admin_router, "verify_password", return_value=False)
        try:
            response = client.post(
                "/api/admin/login", json={"username": "admin", "password": "nope"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 401

    def test_an_unknown_administrator_gets_the_same_answer(self, client):
        """A caller must not learn which administrators exist."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = lambda: db
        try:
            response = client.post(
                "/api/admin/login", json={"username": "ghost", "password": "x"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 401

    def test_a_correct_password_mints_an_admin_token(self, client, mocker):
        from app.modules.admin import router as admin_router

        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            username="admin", hashed_password="hash", is_active=True,
            full_name="Sistem Yöneticisi",
        )
        app.dependency_overrides[get_db] = lambda: db
        mocker.patch.object(admin_router, "verify_password", return_value=True)
        try:
            response = client.post(
                "/api/admin/login", json={"username": "admin", "password": "ok"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_a_deactivated_administrator_cannot_log_in(self, client, mocker):
        from app.modules.admin import router as admin_router

        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            username="admin", hashed_password="h", is_active=False, full_name="x",
        )
        app.dependency_overrides[get_db] = lambda: db
        mocker.patch.object(admin_router, "verify_password", return_value=True)
        try:
            response = client.post(
                "/api/admin/login", json={"username": "admin", "password": "ok"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 401


class TestActions:
    def test_the_customer_list_is_returned(self, admin_client, mocker):
        mocker.patch.object(service, "list_customers", return_value=[{
            "id": "u-1", "tc_no": "11111111110", "email": "t@example.com",
            "full_name": "Test Kullanici", "is_active": True, "cash_balance": 100.0,
            "currency_code": "TRY", "portfolio_value": 250.0, "position_count": 2,
            "created_at": datetime.now(timezone.utc),
        }])
        body = admin_client.get("/api/admin/users").json()
        assert body[0]["tc_no"] == "11111111110"

    def test_a_cash_adjustment_is_applied(self, admin_client, mocker):
        mocker.patch.object(service, "adjust_cash", return_value={
            "reference_number": "TRF-1", "balance_after": 3500.0, "message": "ok",
        })
        response = admin_client.post("/api/admin/users/u-1/cash", json={"amount": 2500})
        assert response.status_code == 200
        assert response.json()["balance_after"] == 3500.0

    def test_a_refused_adjustment_is_422_not_500(self, admin_client, mocker):
        mocker.patch.object(
            service, "adjust_cash", side_effect=service.AdminActionError("Bakiye eksiye düşemez"),
        )
        response = admin_client.post("/api/admin/users/u-1/cash", json={"amount": -9e9})
        assert response.status_code == 422

    def test_a_position_adjustment_is_applied(self, admin_client, mocker):
        mocker.patch.object(service, "adjust_position", return_value={
            "message": "THYAO: 0 → 5 adet.", "quantity_after": 5.0,
        })
        response = admin_client.post(
            "/api/admin/users/u-1/positions", json={"symbol": "THY", "quantity": 5},
        )
        assert response.json()["quantity_after"] == 5.0

    def test_a_refused_position_adjustment_is_422(self, admin_client, mocker):
        mocker.patch.object(
            service, "adjust_position",
            side_effect=service.AdminActionError("Enstrüman bulunamadı"),
        )
        response = admin_client.post(
            "/api/admin/users/u-1/positions", json={"symbol": "zzz", "quantity": 1},
        )
        assert response.status_code == 422

    def test_a_bill_is_issued(self, admin_client, mocker):
        mocker.patch.object(service, "issue_bill", return_value=SimpleNamespace(
            id="b-1", institution="BEDAŞ", bill_type="electricity",
            subscriber_no="TEST-1", amount=100.0, due_day=15, status="pending",
            paid_by=None, paid_at=None, created_at=datetime.now(timezone.utc),
        ))
        response = admin_client.post("/api/admin/bills", json={
            "institution": "BEDAŞ", "bill_type": "electricity",
            "subscriber_no": "TEST-1", "amount": 100, "due_day": 15,
        })
        assert response.status_code == 200

    def test_a_duplicate_bill_is_422(self, admin_client, mocker):
        mocker.patch.object(
            service, "issue_bill", side_effect=service.AdminActionError("zaten var"),
        )
        response = admin_client.post("/api/admin/bills", json={
            "institution": "BEDAŞ", "bill_type": "electricity",
            "subscriber_no": "TEST-1", "amount": 100, "due_day": 15,
        })
        assert response.status_code == 422

    def test_bills_are_listed(self, admin_client):
        assert admin_client.get("/api/admin/bills").status_code == 200

    def test_withdrawing_a_bill(self, admin_client, mocker):
        mocker.patch.object(service, "withdraw_bill", return_value=True)
        assert admin_client.delete("/api/admin/bills/b-1").status_code == 204

    def test_withdrawing_a_missing_bill_is_404(self, admin_client, mocker):
        mocker.patch.object(service, "withdraw_bill", return_value=False)
        assert admin_client.delete("/api/admin/bills/nope").status_code == 404

    def test_withdrawing_a_paid_bill_is_422(self, admin_client, mocker):
        mocker.patch.object(
            service, "withdraw_bill",
            side_effect=service.AdminActionError("Ödenmiş bir fatura silinemez."),
        )
        assert admin_client.delete("/api/admin/bills/b-1").status_code == 422


class TestModelDefaults:
    def test_ids_and_timestamps_are_generated(self):
        """Column defaults only run at flush, so they need exercising here."""
        from app.modules.admin.models import AdminUser, _now, _uuid

        assert _uuid() != _uuid()
        assert _now().tzinfo is not None
        assert AdminUser.__tablename__ == "admin_users"


class TestAccountsAndSubscriptions:
    """The two endpoints that answer "which account" and "whose bill"."""

    def test_a_customers_accounts_are_listed_for_the_operator(self, admin_client, mocker):
        from app.modules.banking import service as banking_service

        mocker.patch.object(banking_service, "portfolio_accounts", return_value=[
            {"id": "a-1", "account_number": "1", "iban": "TR1", "account_type": "vadesiz",
             "currency_code": "TRY", "balance": 100.0, "is_investment": False},
            {"id": "ia-1", "account_number": "TR-INV", "iban": None,
             "account_type": "yatirim", "currency_code": "TRY", "balance": 250.0,
             "is_investment": True},
        ])
        body = admin_client.get("/api/admin/users/u-1/accounts").json()
        assert [a["account_type"] for a in body] == ["vadesiz", "yatirim"]

    def test_the_account_selector_reaches_the_service(self, admin_client, mocker):
        """Without this the adjustment always took the deposit account, which
        is why crediting a customer never touched their investment cash."""
        adjusted = mocker.patch.object(service, "adjust_cash", return_value={
            "reference_number": None, "balance_after": 1500.0, "message": "ok",
        })
        admin_client.post(
            "/api/admin/users/u-1/cash", json={"amount": 500, "account_id": "ia-1"},
        )
        assert adjusted.call_args.kwargs["account_id"] == "ia-1"

    def test_a_subscriber_number_is_assigned(self, admin_client, mocker):
        mocker.patch.object(service, "assign_subscription", return_value={
            "id": "p-1", "user_id": "u-1", "full_name": "Test Kullanici",
            "label": "Ev", "institution": "İGDAŞ", "subscriber_no": "S-1",
        })
        response = admin_client.post("/api/admin/subscriptions", json={
            "user_id": "u-1", "institution": "İGDAŞ", "subscriber_no": "S-1",
        })
        assert response.status_code == 200
        assert response.json()["full_name"] == "Test Kullanici"

    def test_assigning_to_an_unknown_customer_is_422(self, admin_client, mocker):
        mocker.patch.object(
            service, "assign_subscription",
            side_effect=service.AdminActionError("Kullanıcı bulunamadı."),
        )
        response = admin_client.post("/api/admin/subscriptions", json={
            "user_id": "ghost", "institution": "X", "subscriber_no": "1",
        })
        assert response.status_code == 422

    def test_assigned_numbers_are_listed(self, admin_client, mocker):
        mocker.patch.object(service, "list_subscriptions", return_value=[{
            "id": "p-1", "user_id": "u-1", "full_name": "Test Kullanici",
            "label": "Ev", "institution": "İGDAŞ", "subscriber_no": "S-1",
        }])
        body = admin_client.get("/api/admin/subscriptions").json()
        assert body[0]["subscriber_no"] == "S-1"

    def test_the_bill_list_carries_the_resolved_names(self, admin_client, mocker):
        from datetime import datetime, timezone

        mocker.patch.object(service, "describe_bills", return_value=[{
            "id": "b-1", "holder_name": "Fatura Sahibi", "assigned_to": "Atanan",
            "paid_by_name": None, "institution": "İGDAŞ", "bill_type": "internet",
            "subscriber_no": "S-1", "amount": 10.0, "due_day": 5, "status": "pending",
            "paid_by": None, "paid_at": None, "created_at": datetime.now(timezone.utc),
        }])
        bill = admin_client.get("/api/admin/bills").json()["bills"][0]
        assert bill["holder_name"] == "Fatura Sahibi" and bill["assigned_to"] == "Atanan"


class TestIssuingProducts:
    def test_a_card_is_issued(self, admin_client, mocker):
        from app.modules.banking import products

        mocker.patch.object(products, "issue_card", return_value=SimpleNamespace(
            id="c-1", name="Platinum", card_number="5287 **** **** 8024",
        ))
        response = admin_client.post("/api/admin/cards", json={
            "user_id": "u-1", "name": "Platinum", "brand": "mastercard",
            "credit_limit": 50000, "current_debt": 8450.75, "due_day": 12,
        })
        assert response.status_code == 200
        assert "****" in response.json()["card_number"]

    def test_a_refused_card_is_422(self, admin_client, mocker):
        from app.modules.banking import products

        mocker.patch.object(
            products, "issue_card",
            side_effect=products.ProductError("Borç, sıfır ile limit arasında olmalı."),
        )
        assert admin_client.post("/api/admin/cards", json={
            "user_id": "u-1", "name": "X", "credit_limit": 100, "current_debt": 500,
        }).status_code == 422

    def test_a_loan_is_issued(self, admin_client, mocker):
        from app.modules.banking import products

        mocker.patch.object(products, "issue_loan", return_value=SimpleNamespace(
            id="l-1", title="İhtiyaç Kredisi", remaining_amount=60000.0,
        ))
        response = admin_client.post("/api/admin/loans", json={
            "user_id": "u-1", "title": "İhtiyaç Kredisi",
            "principal": 60000, "installment_count": 12,
        })
        assert response.json()["remaining_amount"] == 60000.0

    def test_a_refused_loan_is_422(self, admin_client, mocker):
        from app.modules.banking import products

        mocker.patch.object(
            products, "issue_loan",
            side_effect=products.ProductError("Taksit sayısı sıfırdan büyük olmalı."),
        )
        assert admin_client.post("/api/admin/loans", json={
            "user_id": "u-1", "title": "X", "principal": 100, "installment_count": 1,
        }).status_code == 422
