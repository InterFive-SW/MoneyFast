"""Unit tests for app/modules/auth/service.py.

Bu modül şu an `auth/router.py` tarafından ÇAĞRILMIYOR (DB entegrasyonunu
bekleyen hazır kod) ama gerçek DB sorguları içerdiği için ayrıca ve
doğrudan test ediliyor. `mock_db` (conftest.py) `Session` şeklinde bir
MagicMock; `db.query(...).filter(...).first()` zincirinin dönüş değeri her
testte senaryoya göre ayarlanıyor.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.core.security import (
    RESET_TOKEN_TYPE,
    VERIFICATION_TOKEN_TYPE,
    create_reset_token,
    create_verification_token,
    hash_password,
    verify_password,
)
from app.modules.auth import service
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserUpdateRequest,
)


from tests.conftest import simulate_refresh
from fastapi import HTTPException

from app.core.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from app.modules.auth.schemas import LoginRequest, RegisterRequest
from app.modules.auth.service import (


    authenticate_user,
    create_user,
    refresh_access_token,
)

VALID_REGISTER_PAYLOAD = dict(
    first_name="Ada",
    last_name="Lovelace",
    tc_no="12345678901",
    email="ada@example.com",
    phone_number="+905551112233",
    password="Password123",
)


# --------------------------------------------------------------------------
# authenticate_user
# --------------------------------------------------------------------------
def test_authenticate_user_raises_401_when_user_not_found(mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    payload = LoginRequest(tc_no="12345678901", password="Password123")

    with pytest.raises(HTTPException) as exc_info:
        authenticate_user(payload, mock_db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "TC Kimlik No veya şifre hatalı"


def test_authenticate_user_raises_401_when_password_is_wrong(
    mock_db, password_hash_factory
):
    fake_user = user_stub(
        tc_no="12345678901", hashed_password=password_hash_factory("Password123")
    )
    mock_db.query.return_value.filter.return_value.first.return_value = fake_user
    payload = LoginRequest(tc_no="12345678901", password="WrongPassword1")

    with pytest.raises(HTTPException) as exc_info:
        authenticate_user(payload, mock_db)

    assert exc_info.value.status_code == 401


def test_authenticate_user_returns_token_on_success(mock_db, password_hash_factory):
    fake_user = user_stub(
        tc_no="12345678901", hashed_password=password_hash_factory("Password123")
    )
    mock_db.query.return_value.filter.return_value.first.return_value = fake_user
    payload = LoginRequest(tc_no="12345678901", password="Password123")

    result = authenticate_user(payload, mock_db)

    assert result.token_type == "bearer"
    assert result.access_token


# --------------------------------------------------------------------------
# create_user
# --------------------------------------------------------------------------
def test_create_user_raises_409_when_tc_no_already_registered(mock_db):
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        SimpleNamespace(id="existing-user")
    ]
    payload = RegisterRequest(**VALID_REGISTER_PAYLOAD)

    with pytest.raises(HTTPException) as exc_info:
        create_user(payload, mock_db, BackgroundTasks())

    assert exc_info.value.status_code == 409
    assert "TC Kimlik No" in exc_info.value.detail


def test_create_user_raises_409_when_email_already_registered(mock_db):
    # İlk çağrı (tc_no kontrolü) None döner, ikinci çağrı (email kontrolü)
    # mevcut bir kullanıcı döner — service.py'deki sıralı iki sorguyla eşleşir.
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,
        SimpleNamespace(id="existing-user"),
    ]
    payload = RegisterRequest(**VALID_REGISTER_PAYLOAD)

    with pytest.raises(HTTPException) as exc_info:
        create_user(payload, mock_db, BackgroundTasks())

    assert exc_info.value.status_code == 409
    assert "E-posta" in exc_info.value.detail


def test_create_user_persists_and_returns_user_response_on_success(mock_db):
    # Dört sorgu: TC, e-posta, yatırım hesabı ve mevduat hesabı.
    mock_db.query.return_value.filter.return_value.first.side_effect = [None] * 5

    def _simulate_flush():
        """Gerçek bir flush, Python tarafındaki `default` ile üretilen id'yi
        nesneye yazar. Yatırım hesabı bu id'ye bağlandığı için mock'ta da
        simüle edilmeli."""
        for obj in (call.args[0] for call in mock_db.add.call_args_list):
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())

    mock_db.flush.side_effect = _simulate_flush

    def _simulate_refresh(user):
        """Gerçek bir `Session.refresh()`, sunucu tarafında (INSERT sırasında)
        üretilen default'ları nesneye geri yükler. `mock_db` gerçek bir
        bağlantıya sahip olmadığı için o INSERT hiç çalışmaz.

        Sütun varsayılanları `simulate_refresh`'ten geliyor: her testin kendi
        eksik listesini tutması, yeni bir sütun eklendiğinde hepsinin aynı
        anda düşmesi demekti. `id` burada, çünkü onu üreten INSERT'in
        kendisi."""
        user.id = str(uuid.uuid4())
        simulate_refresh(user)

    mock_db.refresh.side_effect = _simulate_refresh
    payload = RegisterRequest(**VALID_REGISTER_PAYLOAD)

    result = create_user(payload, mock_db, BackgroundTasks())

    assert result.tc_no == "12345678901"
    assert result.email == "ada@example.com"
    assert result.is_active is True
    mock_db.commit.assert_called_once()


def test_registration_opens_an_investment_account(mock_db):
    """Bir kullanıcı hesapsız kalırsa işlem yapamaz; ikisi tek transaction'da
    yazılır, aksi halde yarım kalmış bir kayıt erişilebilir olurdu."""
    mock_db.query.return_value.filter.return_value.first.side_effect = [None] * 5

    def _simulate_flush():
        for obj in (call.args[0] for call in mock_db.add.call_args_list):
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())

    mock_db.flush.side_effect = _simulate_flush
    mock_db.refresh.side_effect = simulate_refresh

    create_user(RegisterRequest(**VALID_REGISTER_PAYLOAD), mock_db, BackgroundTasks())

    added = [call.args[0] for call in mock_db.add.call_args_list]
    account = next(a for a in added if type(a).__name__ == "InvestmentAccount")
    user = next(a for a in added if type(a).__name__ == "User")
    assert account.user_id == str(user.id)
    assert float(account.cash_balance) > 0
    # Tek commit: kullanıcı yazılıp hesap yazılmadan araya bir hata girerse
    # ikisi birden geri alınır.
    mock_db.commit.assert_called_once()


def test_registration_opens_a_deposit_account(mock_db):
    """Bir kullanıcı mevduat hesabı olmadan para gönderemez; kayıt anında
    açılır ki "para gönder" isteğinin bir kaynağı olsun."""
    mock_db.query.return_value.filter.return_value.first.side_effect = [None] * 5

    def _simulate_flush():
        for obj in (call.args[0] for call in mock_db.add.call_args_list):
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())

    mock_db.flush.side_effect = _simulate_flush
    mock_db.refresh.side_effect = simulate_refresh

    create_user(RegisterRequest(**VALID_REGISTER_PAYLOAD), mock_db, BackgroundTasks())

    added = [call.args[0] for call in mock_db.add.call_args_list]
    bank = next(a for a in added if type(a).__name__ == "BankAccount")
    user = next(a for a in added if type(a).__name__ == "User")
    assert bank.user_id == str(user.id)
    assert bank.iban.startswith("TR")
    assert float(bank.balance) > 0
    # Hepsi tek commit: yarım kalmış bir kayıt erişilebilir olmamalı.
    mock_db.commit.assert_called_once()


# --------------------------------------------------------------------------
# refresh_access_token
#
# Without this endpoint a session did not end at 30 minutes -- it silently
# became an anonymous one. The chat kept answering, so nobody noticed, but the
# transaction proposals it staged were owned by "anonymous" and the confirm
# step rejected them forever.
# --------------------------------------------------------------------------
def _active_user(tc_no: str = "12345678901"):
    return user_stub(id=str(uuid.uuid4()), tc_no=tc_no, is_active=True)


def test_refresh_issues_a_new_access_token(mock_db):
    user = _active_user()
    mock_db.query.return_value.filter.return_value.first.return_value = user
    token = create_refresh_token(data={"sub": user.tc_no})

    result = refresh_access_token(token, mock_db)

    payload = decode_access_token(result.access_token)
    assert payload["sub"] == user.tc_no
    assert payload["typ"] == ACCESS_TOKEN_TYPE


def test_refresh_does_not_mint_another_refresh_token(mock_db):
    """Rotating one out on every use would make the session unbounded: the
    refresh token's own expiry would never arrive."""
    user = _active_user()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    result = refresh_access_token(create_refresh_token(data={"sub": user.tc_no}), mock_db)

    assert result.refresh_token is None


def test_an_access_token_cannot_be_used_to_refresh(mock_db):
    """Otherwise a short-lived token could renew itself forever and the short
    lifetime would mean nothing."""
    user = _active_user()
    mock_db.query.return_value.filter.return_value.first.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        refresh_access_token(create_access_token(data={"sub": user.tc_no}), mock_db)

    assert exc_info.value.status_code == 401


def test_garbage_refresh_token_is_rejected(mock_db):
    with pytest.raises(HTTPException) as exc_info:
        refresh_access_token("not-a-jwt", mock_db)
    assert exc_info.value.status_code == 401


def test_deactivated_user_cannot_refresh(mock_db):
    """The session ends at the next refresh rather than running to the end of
    the refresh token's life."""
    user = _active_user()
    user.is_active = False
    mock_db.query.return_value.filter.return_value.first.return_value = user

    with pytest.raises(HTTPException) as exc_info:
        refresh_access_token(create_refresh_token(data={"sub": user.tc_no}), mock_db)

    assert exc_info.value.status_code == 401


def test_unknown_user_cannot_refresh(mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        refresh_access_token(create_refresh_token(data={"sub": "12345678901"}), mock_db)
    assert exc_info.value.status_code == 401


def test_login_now_returns_both_tokens(mock_db, password_hash_factory):
    user = _active_user()
    user.hashed_password = password_hash_factory("Password123")
    mock_db.query.return_value.filter.return_value.first.return_value = user

    result = authenticate_user(
        LoginRequest(tc_no=user.tc_no, password="Password123"), mock_db
    )

    assert decode_access_token(result.access_token)["typ"] == ACCESS_TOKEN_TYPE
    assert decode_access_token(result.refresh_token)["typ"] == REFRESH_TOKEN_TYPE


def test_registration_opens_a_savings_account_too(mock_db):
    """With one account the transfer screen could only ever send money AWAY.

    A `vadeli` account gives "para gönder" somewhere to send to, which is what
    makes moving money between your own accounts -- and into investing --
    possible at all. It opens empty: an account that arrives with money in it
    is a gift, not savings.
    """
    mock_db.query.return_value.filter.return_value.first.side_effect = [None] * 5

    def _simulate_flush():
        for obj in (call.args[0] for call in mock_db.add.call_args_list):
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())

    mock_db.flush.side_effect = _simulate_flush
    mock_db.refresh.side_effect = simulate_refresh

    create_user(RegisterRequest(**VALID_REGISTER_PAYLOAD), mock_db, BackgroundTasks())

    opened = [
        obj for obj in (call.args[0] for call in mock_db.add.call_args_list)
        if type(obj).__name__ == "BankAccount"
    ]
    types = {obj.account_type for obj in opened}
    assert types == {"vadesiz", "vadeli"}
    savings = next(o for o in opened if o.account_type == "vadeli")
    assert float(savings.balance) == 0


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
        # `.local` ayrılmış bir TLD ve `EmailStr` onu reddediyor;
        # `example.com` doğrulayıcıların kabul ettiği test alanı.
        email="test@example.com",
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


# ---------------------------------------------------------------------------
# E-posta doğrulama, şifre sıfırlama ve ayarlar (main + #42)
#
# Bu yollar birleşmeden önce hiç test edilmiyordu: `auth/service.py` %35
# kapsamayla geldi. Hesap doğrulama, şifre sıfırlama ve hesap kapatma, sessizce
# bozulduğunda kullanıcıyı sisteme sokmayan ya da içeride bırakmayan yollar.
# ---------------------------------------------------------------------------
class TestVerifyEmail:
    def test_a_valid_token_marks_the_account_verified(self, mock_db):
        user = user_stub(email="a@b.co", is_verified=False)
        mock_db.query.return_value.filter.return_value.first.return_value = user
        token = create_verification_token(email="a@b.co")

        result = service.verify_email(token, mock_db)

        assert user.is_verified is True
        assert "message" in result

    def test_a_reset_token_is_not_a_verification_token(self, mock_db):
        """`typ` denetimi olmasa, şifre sıfırlama bağlantısı hesabı doğrulamak
        için kullanılabilirdi."""
        token = create_reset_token(email="a@b.co")
        with pytest.raises(HTTPException) as exc:
            service.verify_email(token, mock_db)
        assert exc.value.status_code == 400

    def test_a_garbage_token_is_refused(self, mock_db):
        with pytest.raises(HTTPException) as exc:
            service.verify_email("not-a-token", mock_db)
        assert exc.value.status_code == 400

    def test_a_token_for_nobody_is_refused(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        token = create_verification_token(email="ghost@b.co")
        with pytest.raises(HTTPException):
            service.verify_email(token, mock_db)

    def test_verifying_twice_is_reported_not_repeated(self, mock_db):
        user = user_stub(email="a@b.co", is_verified=True)
        mock_db.query.return_value.filter.return_value.first.return_value = user
        token = create_verification_token(email="a@b.co")
        result = service.verify_email(token, mock_db)
        assert "message" in result


class TestPasswordReset:
    def test_a_matching_user_gets_a_mail_queued(self, mock_db):
        user = user_stub(email="a@b.co", tc_no="12345678901")
        mock_db.query.return_value.filter.return_value.first.return_value = user
        tasks = BackgroundTasks()

        payload = ForgotPasswordRequest(tc_no="12345678901", email="a@b.co")
        result = service.send_password_reset(payload, mock_db, tasks)

        assert len(tasks.tasks) == 1
        assert "gönderildi" in result["message"]

    def test_an_unknown_pair_gets_the_same_answer_and_no_mail(self, mock_db):
        """Kimin kayıtlı olduğu sızmaz: cevap aynı, e-posta gönderilmiyor."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        tasks = BackgroundTasks()

        payload = ForgotPasswordRequest(tc_no="99999999999", email="ghost@b.co")
        result = service.send_password_reset(payload, mock_db, tasks)

        assert tasks.tasks == []
        assert "gönderildi" in result["message"]

    def test_a_valid_reset_token_changes_the_password(self, mock_db):
        user = user_stub(email="a@b.co", hashed_password="eski")
        mock_db.query.return_value.filter.return_value.first.return_value = user
        token = create_reset_token(email="a@b.co")

        service.reset_password(
            ResetPasswordRequest(token=token, new_password="Password456!"), mock_db,
        )

        assert user.hashed_password != "eski"
        assert verify_password("Password456!", user.hashed_password)

    def test_a_verification_token_cannot_reset_a_password(self, mock_db):
        token = create_verification_token(email="a@b.co")
        with pytest.raises(HTTPException) as exc:
            service.reset_password(
                ResetPasswordRequest(token=token, new_password="Password456!"), mock_db,
            )
        assert exc.value.status_code == 400

    def test_a_reset_token_for_nobody_is_refused(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        token = create_reset_token(email="ghost@b.co")
        with pytest.raises(HTTPException):
            service.reset_password(
                ResetPasswordRequest(token=token, new_password="Password456!"), mock_db,
            )


class TestSettingsActions:
    """Ayarlar ekranının arkasındaki yollar (#42)."""

    def _signed_in(self, mock_db, **overrides):
        user = user_stub(**overrides)
        mock_db.query.return_value.filter.return_value.first.return_value = user
        return user

    def test_only_the_supplied_fields_change(self, mock_db):
        """Verilmeyen alan DOKUNULMAZ: bir anahtarı gönderen ekran, diğerlerini
        sıfırlamamalı."""
        user = self._signed_in(mock_db, email="eski@b.co", transaction_limit=1000)
        service.update_user_profile(
            user.tc_no, UserUpdateRequest(transaction_limit=25000), mock_db,
        )
        assert user.transaction_limit == 25000
        assert user.email == "eski@b.co"

    def test_preferences_are_merged_not_replaced(self, mock_db):
        """Bir tercihi değiştiren istek diğerlerini silmemeli."""
        user = self._signed_in(mock_db, user_preferences={"dil": "tr", "tema": "koyu"})
        service.update_user_profile(
            user.tc_no, UserUpdateRequest(user_preferences={"tema": "acik"}), mock_db,
        )
        assert user.user_preferences == {"dil": "tr", "tema": "acik"}

    def test_every_settable_field_can_be_set(self, mock_db):
        """Her alanın kendi dalı var; biri yazılmazsa ekran onu kaydediyor
        sanıp kaydetmemiş olur."""
        user = self._signed_in(mock_db)
        service.update_user_profile(
            user.tc_no,
            UserUpdateRequest(
                email="yeni@example.com",
                phone_number="+905559998877",
                notification_preferences={"email": {"transfer": True}},
            ),
            mock_db,
        )
        assert user.email == "yeni@example.com"
        assert user.phone_number == "+905559998877"
        assert user.notification_preferences == {"email": {"transfer": True}}

    def test_an_unknown_user_is_a_404(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            service.update_user_profile("00000000000", UserUpdateRequest(), mock_db)
        assert exc.value.status_code == 404

    def test_changing_a_password_requires_the_current_one(self, mock_db):
        """Mevcut şifre doğrulanmadan değiştirilebilseydi, ele geçirilmiş bir
        oturum hesabı kalıcı olarak devralabilirdi."""
        self._signed_in(mock_db, hashed_password=hash_password("Password123!"))
        with pytest.raises(HTTPException) as exc:
            service.change_user_password(
                "12345678901",
                ChangePasswordRequest(
                    current_password="Yanlis123!", new_password="Password456!",
                ),
                mock_db,
            )
        assert exc.value.status_code in (400, 401, 403)

    def test_the_right_current_password_changes_it(self, mock_db):
        user = self._signed_in(mock_db, hashed_password=hash_password("Password123!"))
        service.change_user_password(
            "12345678901",
            ChangePasswordRequest(
                current_password="Password123!", new_password="Password456!",
            ),
            mock_db,
        )
        assert verify_password("Password456!", user.hashed_password)

    def test_changing_the_password_of_nobody_is_a_404(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            service.change_user_password(
                "00000000000",
                ChangePasswordRequest(
                    current_password="Password123!", new_password="Password456!",
                ),
                mock_db,
            )
        assert exc.value.status_code == 404

    def test_deactivating_marks_the_account_inactive(self, mock_db):
        user = self._signed_in(mock_db, is_active=True)
        service.deactivate_account(user.tc_no, "artık kullanmıyorum", mock_db)
        assert user.is_active is False

    def test_deactivating_without_a_reason_is_allowed(self, mock_db):
        user = self._signed_in(mock_db, is_active=True)
        service.deactivate_account(user.tc_no, None, mock_db)
        assert user.is_active is False

    def test_deactivating_twice_is_refused(self, mock_db):
        self._signed_in(mock_db, is_active=False)
        with pytest.raises(HTTPException):
            service.deactivate_account("12345678901", None, mock_db)

    def test_deactivating_nobody_is_a_404(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            service.deactivate_account("00000000000", None, mock_db)
        assert exc.value.status_code == 404


class TestDataExport:
    """Veri dışa aktarma (#42): kullanıcının bütün verisi, PDF olarak."""

    @pytest.mark.asyncio
    async def test_it_gathers_the_profile_and_portfolio_then_queues_the_mail(
        self, mock_db, mocker,
    ):
        user = user_stub()
        mock_db.query.return_value.filter.return_value.first.return_value = user

        from app.modules.investment import market_service
        mocker.patch.object(market_service, "holdings", return_value=[])
        mocker.patch.object(market_service, "latest_quotes", return_value={})
        mocker.patch.object(market_service, "account", return_value=None)
        send = mocker.patch(
            "app.core.email.send_data_export_email", new_callable=mocker.AsyncMock,
        )

        tasks = BackgroundTasks()
        result = await service.request_data_export(user.tc_no, mock_db, tasks)

        # Arka plan görevi kuyruğa girdi; kullanıcı beklemiyor.
        assert tasks.tasks or send.called
        assert "message" in result

    @pytest.mark.asyncio
    async def test_an_unknown_user_cannot_export(self, mock_db):
        """Var olmayan bir kullanıcının verisi üretilmez."""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            await service.request_data_export("00000000000", mock_db, BackgroundTasks())
        assert exc.value.status_code == 404


class TestUnverifiedLogin:
    def test_an_unverified_account_cannot_log_in(self, mock_db):
        """E-posta doğrulanmadan giriş yapılamaz (main).

        Doğrulama zorunlu değilse, birinin e-posta adresiyle hesap açmak o
        adrese erişmeyi gerektirmez.
        """
        user = user_stub(
            is_verified=False, hashed_password=hash_password("Password123!"),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = user
        with pytest.raises(HTTPException) as exc:
            service.authenticate_user(
                LoginRequest(tc_no=user.tc_no, password="Password123!"), mock_db,
            )
        assert exc.value.status_code in (401, 403)
