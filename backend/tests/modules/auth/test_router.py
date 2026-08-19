"""Unit tests for app/modules/auth/router.py.

Router şu an "YER TUTUCU SİMÜLASYONU" bloklarıyla çalışıyor (auth/service.py
DB bağlanana kadar çağrılmıyor, bkz. test_service.py). Bu dosya mevcut
simülasyon davranışını bir sözleşme olarak sabitliyor: DB entegrasyonu
geldiğinde `service.py`'nin gerçek fonksiyonları devreye alınacak ve bu
testler o zaman güncellenecek — ama HTTP sözleşmesi (durum kodları, response
şekli) aynı kalmalı.
"""

from __future__ import annotations

VALID_REGISTER_PAYLOAD = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "tc_no": "12345678901",
    "email": "ada@example.com",
    "phone_number": "+905551112233",
    "password": "Password123",
}


def test_register_returns_simulated_user_with_201(client):
    response = client.post("/api/auth/register", json=VALID_REGISTER_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["tc_no"] == "12345678901"
    assert body["email"] == "ada@example.com"
    assert body["is_active"] is True


def test_register_rejects_invalid_payload_with_422(client):
    bad_payload = {**VALID_REGISTER_PAYLOAD, "password": "short"}

    response = client.post("/api/auth/register", json=bad_payload)

    assert response.status_code == 422


def test_login_with_correct_simulated_password_returns_token(client):
    response = client.post(
        "/api/auth/login", json={"tc_no": "12345678901", "password": "Password123"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_with_wrong_password_returns_401(client):
    response = client.post(
        "/api/auth/login", json={"tc_no": "12345678901", "password": "WrongPass1"}
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_invalid_tc_no_format_returns_422(client):
    response = client.post(
        "/api/auth/login", json={"tc_no": "abc", "password": "Password123"}
    )

    assert response.status_code == 422


def test_forgot_password_always_returns_generic_success_message(client):
    response = client.post(
        "/api/auth/forgot-password", json={"email": "someone@example.com"}
    )

    assert response.status_code == 200
    assert "reset link" in response.json()["message"]


def test_forgot_password_invalid_email_returns_422(client):
    response = client.post("/api/auth/forgot-password", json={"email": "not-an-email"})

    assert response.status_code == 422


def test_get_current_user_without_token_returns_401(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_get_current_user_with_garbage_token_returns_401(client):
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


def test_get_current_user_with_valid_token_returns_simulated_profile(client):
    login_response = client.post(
        "/api/auth/login", json={"tc_no": "98765432109", "password": "Password123"}
    )
    token = login_response.json()["access_token"]

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["tc_no"] == "98765432109"
    assert body["email"] == "simulated@example.com"


def test_auth_health_reports_module_name(client):
    response = client.get("/api/auth/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "auth"}
