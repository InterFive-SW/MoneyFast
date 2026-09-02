"""Kayıtlı bildirim numaraları: `ingestor`'ın KAP'tan önce sorduğu şey.

KAP'ın bildirim listesi her koşuda iki bin kayıt döndürüyor ve her birinin
GÖVDESİ ayrı bir sayfada. Sormadan çekmek, aynı iki bin sayfayı on beş
dakikada bir yeniden istemek olurdu -- `candles/coverage` ile aynı desen ve
aynı sebep.

Numara ayrı bir sütunda saklanmıyor: bildirimin adresi zaten
`.../Bildirim/1656735`. İkinci kez saklamak, ikisinin ayrışabileceği bir yer
açardı.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.market import service as news_service

URL = "/api/market/news/known-ids"


def _db(urls):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.all.return_value = [(u,) for u in urls]
    return db


class TestKnownNewsIds:
    def test_the_number_is_read_from_the_address(self):
        found = news_service.known_news_ids(
            _db(["https://www.kap.org.tr/tr/Bildirim/1656735"]), "KAP"
        )
        assert found == [1656735]

    def test_a_trailing_slash_does_not_hide_the_number(self):
        assert news_service.known_news_ids(
            _db(["https://www.kap.org.tr/tr/Bildirim/1656735/"]), "KAP"
        ) == [1656735]

    def test_an_address_without_a_number_is_skipped(self):
        """RSS haberlerinin adresinde numara yok ve olmaması bir hata değil."""
        assert news_service.known_news_ids(
            _db(["https://www.dunya.com/haber/borsa-yukseldi"]), "KAP"
        ) == []

    def test_duplicates_collapse_and_the_result_is_ordered(self):
        rows = [
            "https://www.kap.org.tr/tr/Bildirim/1656740",
            "https://www.kap.org.tr/tr/Bildirim/1656735",
            "https://www.kap.org.tr/tr/Bildirim/1656740",
        ]
        assert news_service.known_news_ids(_db(rows), "KAP") == [1656735, 1656740]

    def test_a_short_trailing_number_is_not_taken_for_a_disclosure(self):
        """Haber adresleri de sayıyla bitebiliyor (`/haber/12`). Gerçek
        bildirim numaraları yedi haneli; kısa bir sayıyı numara saymak,
        gövdesi hiç çekilmemiş bir bildirimi çekilmiş gibi gösterirdi."""
        assert news_service.known_news_ids(
            _db(["https://example.com/haber/12"]), "KAP"
        ) == []

    def test_nothing_stored_is_an_empty_list(self):
        assert news_service.known_news_ids(_db([]), "KAP") == []

    def test_the_source_filters_the_read(self):
        """Bir RSS haberinin adresindeki bir sayı, KAP numarası sanılmamalı."""
        db = _db([])
        news_service.known_news_ids(db, "KAP")
        assert db.query.return_value.filter.called


class TestEndpoint:
    def test_is_guarded_by_the_service_token(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        assert client.get(URL, params={"source": "KAP"}).status_code == 401

    def test_returns_the_service_answer(self, client, mocker, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        mocker.patch.object(news_service, "known_news_ids", return_value=[1, 2])
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            response = client.get(
                URL, params={"source": "KAP"},
                headers={"Authorization": "Bearer secret"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 200
        assert response.json() == {"source": "KAP", "ids": [1, 2]}

    def test_a_missing_source_is_refused(self, client, monkeypatch):
        """Kaynaksız bir sorgu, tüm haberlerin adreslerini tarardı."""
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        response = client.get(URL, headers={"Authorization": "Bearer secret"})
        assert response.status_code == 422
