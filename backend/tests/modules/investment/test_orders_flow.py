"""Emir akışı: onay, bekleme, dolum, iptal.

Kırılan varsayım şuydu: onaylanan bir alım ANINDA gerçekleşiyordu ve limit
fiyat yalnızca fiyatlama girdisiydi -- yani kullanıcı "290'a düşünce al"
dediğinde emir, piyasa 305'ken bile 290'dan doluyordu. Artık onay emri
YERLEŞTİRİYOR; gerçekleşme eşleştiricinin işi.

İkinci kırılan varsayım kalıcılıkla ilgili: bekleme `asyncio.sleep(15)`
içindeydi ve süreç o aralıkta ölürse satır `PENDING`, para bloke ve onu
bitirecek hiçbir şey kalmıyordu.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id, get_optional_user_id, require_service_token
from app.main import app
from app.modules.investment import market_service, matching, service

CONFIRM = "/api/investment/transactions/{}/confirm"
CANCEL = "/api/investment/transactions/{}/cancel"
AGENT_ORDERS = "/api/investment/agent/{}/orders"
AGENT_CANCEL = "/api/investment/agent/{}/orders/{}/cancel"

NOW = datetime.now(timezone.utc)


def make_proposal(**overrides):
    row = SimpleNamespace(
        id="PROP-1",
        user_id="user-1",
        status="PENDING_USER_CONFIRMATION",
        transaction_type="BUY",
        symbol="THYAO",
        quantity=10,
        order_type="MARKET",
        limit_price=None,
        source_account_id="TR-TEST-0001",
        destination_account_id=None,
        payload={"estimate": {"net_amount": 3022.26, "reference_price": 301.75}},
        expires_at=NOW + timedelta(minutes=10),
        confirmed_at=None,
        cancelled_at=None,
        created_at=NOW,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


DEFAULT_USER = SimpleNamespace(
    id="user-1", email="a@b.test", notification_preferences={},
)


def stage(db, proposal, user=DEFAULT_USER):
    """`db.get` MODELE göre cevap verir.

    Tek bir `return_value` yetmiyor: onay yolu önce öneriyi, sonra e-posta
    tercihi için kullanıcıyı okuyor ve ikisine aynı nesneyi döndürmek,
    öneriyi kullanıcı sanan bir hata üretiyordu.
    """
    from app.modules.auth.models import User

    def _get(model, _key):
        return user if model is User else proposal

    db.get.side_effect = _get


@pytest.fixture
def db():
    session = MagicMock(spec=Session)
    stage(session, None)
    return session


@pytest.fixture
def client(db, mocker):
    mocker.patch.object(
        market_service, "account",
        return_value=SimpleNamespace(
            id="acct-1", cash_balance=50_000.0, currency_code="TRY",
            account_number="TR-TEST-0001",
        ),
    )
    mocker.patch.object(
        service, "block_funds",
        return_value={"cash_after": 46_977.74, "cash_delta": -3022.26},
    )
    mocker.patch.object(service, "finalize_settlement")
    mocker.patch.object(service, "rollback_funds")
    # Arka plan görevi TestClient kapanırken GERÇEKTEN çalışıyor; posta
    # katmanını açık bırakmak, testin bir SMTP istemcisi kurmasına yol
    # açıyordu.
    mocker.patch("app.modules.investment.router.send_transaction_request_email")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_optional_user_id] = lambda: "user-1"
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[require_service_token] = lambda: None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


class TestConfirm:
    def test_a_market_order_settles_immediately(self, client, db):
        """Piyasa emrinin bekleyecek bir şeyi yok; fiyat zaten oluşmuş.
        Eskiden 15 saniyelik bir uyku vardı ve o yalnızca bir gecikme
        animasyonuydu."""
        row = make_proposal()
        stage(db, row)
        response = client.post(CONFIRM.format("PROP-1"))
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert row.status == "CONFIRMED"
        assert row.confirmed_at is not None
        service.finalize_settlement.assert_called_once()

    def test_a_limit_order_waits_instead_of_filling(self, client, db):
        row = make_proposal(order_type="LIMIT", limit_price=290.0)
        stage(db, row)
        response = client.post(CONFIRM.format("PROP-1"))
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_price"
        assert row.status == matching.WAITING_PRICE
        # Emir YERLEŞTİ, gerçekleşmedi.
        assert row.confirmed_at is None
        service.finalize_settlement.assert_not_called()
        # Para BLOKE: kullanıcı bakiyesinin neden azaldığını görmeli.
        service.block_funds.assert_called_once()

    def test_a_limit_type_without_a_price_still_settles(self, client, db):
        """`LIMIT` etiketi taşıyıp fiyatı olmayan bir satır beklerse asla
        dolamaz: neye göre tetikleneceği tanımsız."""
        row = make_proposal(order_type="LIMIT", limit_price=None)
        stage(db, row)
        assert client.post(CONFIRM.format("PROP-1")).json()["status"] == "confirmed"

    def test_re_confirming_a_waiting_order_does_not_block_twice(self, client, db):
        """Bekleyen bir emir onay ALMIŞ bir emirdir; ikinci onay blokajı
        ikinci kez uygulardı."""
        stage(db, make_proposal(status=matching.WAITING_PRICE))
        response = client.post(CONFIRM.format("PROP-1"))
        assert response.status_code == 200
        service.block_funds.assert_not_called()

    def test_a_failing_settlement_answers_409_rather_than_500(self, client, db, mocker):
        stage(db, make_proposal())
        mocker.patch.object(
            service, "finalize_settlement",
            side_effect=service.SettlementError("enstrüman kaydı yok"),
        )
        response = client.post(CONFIRM.format("PROP-1"))
        assert response.status_code == 409
        assert "enstrüman" in response.json()["detail"]

    def test_no_account_answers_409(self, client, db, mocker):
        stage(db, make_proposal())
        mocker.patch.object(market_service, "account", return_value=None)
        assert client.post(CONFIRM.format("PROP-1")).status_code == 409

    def test_a_demo_only_account_cannot_settle_a_real_trade(self, client, db, mocker):
        """Uç nokta hesabı demo yedeğiyle çözüyor, takas ise `allow_demo_fallback=False`
        ile: demo portföyünü OKUMAK zararsız, ona karşı işlem fiyatlamak
        değil. İkisinin ayrışabildiği yer burası."""
        stage(db, make_proposal())
        owner = SimpleNamespace(
            id="acct-demo", cash_balance=1.0, currency_code="TRY",
            account_number="TR-DEMO-0001",
        )
        mocker.patch.object(
            market_service, "account",
            side_effect=lambda _db, **kw: None if kw.get("allow_demo_fallback") is False else owner,
        )
        response = client.post(CONFIRM.format("PROP-1"))
        assert response.status_code == 409
        assert "yatırım hesabı" in response.json()["detail"]


class TestConfirmEmail:
    def _user(self, prefs=None, email="a@b.test"):
        return SimpleNamespace(
            id="user-1", email=email,
            notification_preferences=prefs if prefs is not None else {},
        )

    def test_the_request_email_is_queued(self, client, db, mocker):
        row = make_proposal()
        stage(db, row, self._user())
        send = mocker.patch("app.modules.investment.router.send_transaction_request_email")
        client.post(CONFIRM.format("PROP-1"))
        assert send.call_args.kwargs["email_to"] == "a@b.test"

    @pytest.mark.parametrize("user", [
        None,
        SimpleNamespace(id="user-1", email="", notification_preferences={}),
        SimpleNamespace(
            id="user-1", email="a@b.test",
            notification_preferences={"transactions": {"email": False}},
        ),
    ])
    def test_no_addressee_means_no_mail(self, client, db, mocker, user):
        stage(db, make_proposal(), user)
        send = mocker.patch("app.modules.investment.router.send_transaction_request_email")
        client.post(CONFIRM.format("PROP-1"))
        send.assert_not_called()


class TestCancel:
    def test_a_waiting_order_is_withdrawn_and_the_money_returned(self, client, db):
        row = make_proposal(status=matching.WAITING_PRICE)
        stage(db, row)
        assert client.post(CANCEL.format("PROP-1")).status_code == 204
        assert row.status == "CANCELLED"
        assert row.cancelled_at is not None
        service.rollback_funds.assert_called_once()

    def test_an_unconfirmed_proposal_is_withdrawn_without_a_refund(self, client, db):
        """Henüz onaylanmadı, dolayısıyla bloke edilmiş bir şey de yok."""
        row = make_proposal()
        stage(db, row)
        assert client.post(CANCEL.format("PROP-1")).status_code == 204
        assert row.status == "CANCELLED"
        service.rollback_funds.assert_not_called()

    def test_cancelling_twice_is_idempotent(self, client, db):
        stage(db, make_proposal(status="CANCELLED"))
        assert client.post(CANCEL.format("PROP-1")).status_code == 204
        service.rollback_funds.assert_not_called()

    def test_a_filled_order_cannot_be_cancelled(self, client, db):
        """Gerçekleşmiş bir emri geri almak, ters yönde ikinci bir emirdir."""
        stage(db, make_proposal(status="CONFIRMED"))
        response = client.post(CANCEL.format("PROP-1"))
        assert response.status_code == 409
        assert "iptal edilemez" in response.json()["detail"]

    def test_an_unknown_order_is_a_404(self, client, db):
        stage(db, None)
        assert client.post(CANCEL.format("PROP-X")).status_code == 404

    def test_another_users_order_is_indistinguishable_from_missing(self, client, db):
        """403 dönmek, o numarada bir emir OLDUĞUNU doğrulardı."""
        stage(db, make_proposal(user_id="someone-else"))
        assert client.post(CANCEL.format("PROP-1")).status_code == 404

    def test_no_account_answers_409(self, client, db, mocker):
        stage(db, make_proposal(status=matching.WAITING_PRICE))
        mocker.patch.object(market_service, "account", return_value=None)
        assert client.post(CANCEL.format("PROP-1")).status_code == 409

    def test_a_failing_refund_answers_409_rather_than_losing_the_money(
        self, client, db, mocker
    ):
        row = make_proposal(status=matching.WAITING_PRICE)
        stage(db, row)
        mocker.patch.object(
            service, "rollback_funds", side_effect=service.SettlementError("iade edilemedi")
        )
        response = client.post(CANCEL.format("PROP-1"))
        assert response.status_code == 409
        # Emir HÂLÂ bekliyor: iade edilemediyse iptal de edilmedi.
        assert row.status == matching.WAITING_PRICE


class TestAgentSurface:
    def test_the_agent_reads_the_same_order_list(self, client, db, mocker):
        """İkinci bir kaynak değil: panel ile sohbetin emir listesi konusunda
        çelişmesi mümkün olmamalı."""
        rows = mocker.patch.object(market_service, "recent_orders", return_value=[])
        response = client.get(AGENT_ORDERS.format("user-1"))
        assert response.status_code == 200
        rows.assert_called_once_with(db, "user-1")

    def test_the_agent_cancel_returns_a_body(self, client, db):
        """MCP istemcisi her yanıtı JSON nesnesi olarak çözüyor; boş gövde
        orada "backend JSON döndürmedi" hatasına dönüşürdü."""
        stage(db, make_proposal(status=matching.WAITING_PRICE))
        response = client.post(AGENT_CANCEL.format("user-1", "PROP-1"))
        assert response.status_code == 200
        assert response.json() == {"order_id": "PROP-1", "cancelled": True}

    def test_the_agent_cannot_cancel_someone_elses_order(self, client, db):
        stage(db, make_proposal(user_id="someone-else"))
        assert client.post(AGENT_CANCEL.format("user-1", "PROP-1")).status_code == 404
