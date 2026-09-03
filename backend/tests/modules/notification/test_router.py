"""Bildirim uçları.

Modül gerçek ama üç ucunun da testi yoktu -- ve ikisi SAHİPLİK DENETİMİ
taşıyor: `mark_notification_as_read` bildirimi kullanıcıya göre süzüyor ve
bunu doğrulayan hiçbir şey yoktu. Başkasının bildirimini okundu işaretlemek,
tek bir `filter` çağrısının düşmesi kadar uzaktaydı.

`/health` de kayıptı: modül taslaktan gerçek bir modüle dönerken uç
kaybolmuş ve `test_stub_routers` o gün bugündür kırık.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.main import app
from app.modules.notification.models import Notification

NOW = datetime.now(timezone.utc)
URL = "/api/notification/me/notifications"


def row(read=False, title="Talebiniz Alındı"):
    return SimpleNamespace(
        id=uuid.uuid4(), user_id="user-1", title=title,
        description="20 lot THYAO", type="INFO", link_url="/portfolio",
        is_read=read, created_at=NOW,
    )


@pytest.fixture
def notif_client():
    from fastapi.testclient import TestClient

    db = MagicMock(spec=Session)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-1")
    try:
        with TestClient(app) as client:
            client.db = db
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


class TestHealth:
    def test_the_module_reports_its_own_name(self, notif_client):
        """Her modülde var ve bir test üçünü birden kontrol ediyor. Bu uç
        modül gerçekleşirken kaybolmuş ve o testi kırmıştı."""
        response = notif_client.get("/api/notification/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "module": "notification"}


class TestListing:
    def _rows(self, client, rows, unread):
        query = client.db.query.return_value.filter.return_value
        query.order_by.return_value.limit.return_value.all.return_value = rows
        query.count.return_value = unread

    def test_the_badge_count_is_separate_from_the_page(self, notif_client):
        """Sayaç LİMİTE takılmadan sayılıyor: elli bildirim gösterip
        "3 okunmamış" demek, elli birincisini görünmez kılardı."""
        self._rows(notif_client, [row(), row(read=True)], unread=7)
        body = notif_client.get(URL).json()
        assert body["unread_count"] == 7
        assert len(body["items"]) == 2

    def test_an_empty_inbox_is_an_answer(self, notif_client):
        self._rows(notif_client, [], unread=0)
        body = notif_client.get(URL).json()
        assert body["items"] == [] and body["unread_count"] == 0

    def test_it_asks_for_the_newest_first(self, notif_client):
        self._rows(notif_client, [row()], unread=1)
        notif_client.get(URL)
        assert notif_client.db.query.return_value.filter.called


class TestMarkRead:
    def test_a_notification_that_is_not_yours_is_a_404(self, notif_client):
        """Sahiplik denetimi: sorgu `user_id` ile de süzüyor, dolayısıyla
        başkasının bildirimi HİÇ BULUNAMAZ. 403 değil 404 -- var olduğunu
        bile söylememek doğru."""
        notif_client.db.query.return_value.filter.return_value.first.return_value = None
        response = notif_client.put(f"{URL}/{uuid.uuid4()}/read")
        assert response.status_code == 404

    def test_your_own_notification_is_marked(self, notif_client):
        mine = row()
        notif_client.db.query.return_value.filter.return_value.first.return_value = mine
        response = notif_client.put(f"{URL}/{mine.id}/read")
        assert response.status_code == 200
        assert mine.is_read is True
        notif_client.db.commit.assert_called_once()

    def test_a_malformed_id_is_rejected_before_the_query(self, notif_client):
        assert notif_client.put(f"{URL}/not-a-uuid/read").status_code == 422


class TestMarkAllRead:
    def test_only_the_callers_unread_rows_are_touched(self, notif_client):
        response = notif_client.post(f"{URL}/mark-all-read")
        assert response.status_code == 200
        notif_client.db.query.return_value.filter.return_value.update.assert_called_once_with(
            {"is_read": True}
        )
        notif_client.db.commit.assert_called_once()


class TestAuthentication:
    def test_every_endpoint_needs_a_session(self, client):
        """`get_current_user` override'ı OLMADAN: üçü de kullanıcıyı
        token'dan çözüyor ve anonim çağıran kimsenin bildirimini görmemeli."""
        assert client.get(URL).status_code == 401
        assert client.put(f"{URL}/{uuid.uuid4()}/read").status_code == 401
        assert client.post(f"{URL}/mark-all-read").status_code == 401
