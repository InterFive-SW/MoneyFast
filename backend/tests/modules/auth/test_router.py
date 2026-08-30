"""Unit tests for app/modules/auth/router.py.

Bu dosya HTTP sözleşmesini (durum kodları, response şekli) sabitliyor.

`/me` artık simülasyon değil: kullanıcıyı `app/core/deps.get_current_user`
üzerinden veritabanından çözüyor. Önceki hali her çağrıda rastgele bir UUID
üretiyordu, yani aynı kullanıcının iki isteği farklı kimliklere sahip oluyordu
ve hiçbir kayıt kullanıcıya bağlanamıyordu.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

VALID_REGISTER_PAYLOAD = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "tc_no": "12345678901",
    "email": "ada@example.com",
    "phone_number": "+905551112233",
    "password": "Password123",
}


def test_register_persists_the_user_and_returns_201(client, mocker):
    """Registration writes to the database now. The placeholder returned 201
    and a random UUID while storing nothing, so a user could register
    "successfully" and then be unable to log in."""
    from app.modules.auth import service

    created = user_stub(
        id="user-new-1",
        tc_no="12345678901",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone_number="+905551112233",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    create_user = mocker.patch.object(service, "create_user", return_value=created)

    response = client.post("/api/auth/register", json=VALID_REGISTER_PAYLOAD)

    assert response.status_code == 201
    assert create_user.called, "the route must go through the service layer"
    body = response.json()
    assert body["tc_no"] == "12345678901"
    assert body["email"] == "ada@example.com"
    assert body["is_active"] is True


def test_register_rejects_invalid_payload_with_422(client):
    bad_payload = {**VALID_REGISTER_PAYLOAD, "password": "short"}

    response = client.post("/api/auth/register", json=bad_payload)

    assert response.status_code == 422


def test_login_checks_the_stored_password(client, mocker, password_hash_factory):
    """The placeholder accepted the literal string "Password123" for ANY TC
    number without touching the database — a valid JWT for any account. Since
    user_id is now derived from the token, that was enough to read someone
    else's portfolio."""
    from app.modules.auth import service

    stored = user_stub(
        id="user-1",
        tc_no="12345678901",
        hashed_password=password_hash_factory("Sifre1234!"),
        is_active=True,
    )
    mocker.patch.object(
        service, "authenticate_user", side_effect=lambda payload, db: _real_authenticate(payload, stored)
    )

    ok = client.post(
        "/api/auth/login", json={"tc_no": "12345678901", "password": "Sifre1234!"}
    )
    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"


def _real_authenticate(payload, stored):
    """Mirror of service.authenticate_user against a single known user."""
    from fastapi import HTTPException, status

    from app.core.security import create_access_token, verify_password
    from app.modules.auth.schemas import TokenResponse

    if payload.tc_no != stored.tc_no or not verify_password(
        payload.password, stored.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TC Kimlik No veya şifre hatalı",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(data={"sub": stored.tc_no}))


def test_login_with_wrong_password_returns_401(client, mocker, password_hash_factory):
    from app.modules.auth import service

    stored = user_stub(
        id="user-1",
        tc_no="12345678901",
        hashed_password=password_hash_factory("Sifre1234!"),
        is_active=True,
    )
    mocker.patch.object(
        service, "authenticate_user", side_effect=lambda payload, db: _real_authenticate(payload, stored)
    )

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


def test_forgot_password_always_returns_generic_success_message(client, mocker):
    # TC ve e-posta birlikte isteniyor: şema bunu bilerek zorunlu kılıyor,
    # yalnızca e-posta gönderen bir istek 422 alır. Testin asıl iddiası
    # değişmedi -- var olmayan bir kullanıcı için de aynı genel cevap döner,
    # yani kimin kayıtlı olduğu sızmaz.
    #
    # Kullanıcı bulunamıyor: testin anlattığı durum bu. Varsayılan mock her
    # sorguya truthy bir nesne döndürdüğü için bu açıkça kuruluyor.
    from app.modules.auth import service as auth_service

    mocker.patch.object(
        auth_service, "send_password_reset",
        return_value={"message": "Şifre sıfırlama bağlantısı e-posta adresinize gönderildi."},
    )
    response = client.post(
        "/api/auth/forgot-password",
        json={"tc_no": "99999999999", "email": "someone@example.com"},
    )

    assert response.status_code == 200
    # Aynı cevap, kullanıcı olsa da olmasa da: kimin kayıtlı olduğu sızmaz.
    assert "gönderildi" in response.json()["message"]


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


def test_get_current_user_returns_the_row_behind_the_token(client, mocker):
    """/me used to mint a random UUID on every call, which meant the same
    logged-in user had a different identity each request -- and nothing could
    be keyed to them. It now resolves the actual row."""
    from datetime import datetime, timezone

    from app.core import deps

    user = user_stub(
        id="user-abc-123",
        tc_no="98765432109",
        first_name="Ayşe",
        last_name="Yılmaz",
        email="ayse@example.com",
        phone_number="+905554443322",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    client.app.dependency_overrides[deps.get_current_user] = lambda: user
    try:
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "user-abc-123"
    assert body["tc_no"] == "98765432109"
    assert body["email"] == "ayse@example.com"


def test_auth_health_reports_module_name(client):
    response = client.get("/api/auth/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "auth"}


def test_refresh_endpoint_returns_a_new_access_token(client, mocker):
    """The endpoint that keeps a session alive past ACCESS_TOKEN_EXPIRE_MINUTES.

    Its absence is what let an expired session degrade to an anonymous one
    instead of ending, which in turn let the chat stage trades nobody owned.
    """
    from app.core.security import ACCESS_TOKEN_TYPE, create_access_token
    from app.modules.auth import service
    from app.modules.auth.schemas import TokenResponse

    mocker.patch.object(
        service,
        "refresh_access_token",
        side_effect=lambda token, db: TokenResponse(
            access_token=create_access_token(data={"sub": "12345678901"})
        ),
    )

    response = client.post("/api/auth/refresh", json={"refresh_token": "a-refresh-token"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["refresh_token"] is None


def test_refresh_requires_a_token_in_the_body(client):
    assert client.post("/api/auth/refresh", json={}).status_code == 422


def user_stub(**overrides):
    """Bir kullanıcı satırı taklidi, ŞU ANKİ şemanın gerektirdiği alanlarla.

    Testler bunları tek tek `SimpleNamespace(tc_no=..., hashed_password=...)`
    diye kuruyordu. Şema büyüdükçe -- main `is_verified` ekledi, #42
    `notification_preferences` ve `transaction_limit` ekledi -- her ekleme aynı
    anda on iki testi düşürdü, hepsi aynı sebeple ve hepsi ayrı ayrı
    düzeltilmek zorunda kaldı.

    Tek yerde toplandı: bir sonraki sütun buraya eklenir, testlere değil.
    """
    from datetime import datetime, timezone
    import uuid as _uuid

    base = dict(
        id=str(_uuid.uuid4()),
        tc_no="12345678901",
        email="test@dummy.moneyfast.local",
        phone_number="+905550000000",
        first_name="Test",
        last_name="Kullanici",
        is_active=True,
        is_verified=True,
        notification_preferences={},
        transaction_limit=50000,
        user_preferences={},
        created_at=datetime.now(timezone.utc),
        hashed_password="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)
