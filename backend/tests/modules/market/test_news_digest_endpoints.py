"""Haber özeti uçları.

`/news/portfolio` ile aynı korumalar ve aynı gerekçelerle: "portföyünüz"
başlığı altında başkasının portföyünü özetlemek, kullanıcının seçmediği bir
listeyi onunmuş gibi sunmak olurdu. Yoldan kullanıcı adı alan ikiz uç servis
token'ı istiyor.

Cümlelerin KODDA kurulduğu burada da sabitleniyor: yanıtta hazır bir
`sentence` ve koşulsuz bir `disclaimer` var. Arayüzün cümleyi yeniden kurması,
çekinceyi kodun dışına taşırdı.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id, require_service_token
from app.main import app
from app.modules.investment import market_service
from app.modules.market import news_impact

DIGEST = "/api/market/news/digest"
SUMMARY = "/api/market/news/impact-summary"
USER = "11111111-1111-1111-1111-111111111111"


def _impact(symbol="ASELS", direction=news_impact.UP, scope=news_impact.DIRECT,
            news_id="n1"):
    return SimpleNamespace(
        symbol=symbol, direction=direction, scope=scope, magnitude="MEDIUM",
        confidence=0.7, news_id=news_id,
        mechanism="Sözleşme tutarı şirketin yıllık ihracatına ekleniyor.",
        published_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )


@pytest.fixture
def client(mocker):
    from fastapi.testclient import TestClient

    mocker.patch.object(
        market_service, "holdings",
        return_value=[{"symbol": "ASELS", "quantity": 10, "name": "Aselsan"}],
    )
    mocker.patch.object(
        market_service, "candle_closes",
        return_value=[(None, 100.0 + index) for index in range(60)],
    )
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    app.dependency_overrides[get_current_user_id] = lambda: USER
    app.dependency_overrides[require_service_token] = lambda: None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


class TestDigest:
    def test_a_portfolio_with_news_is_summarised(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[_impact()])
        body = client.get(DIGEST).json()
        assert body["entries"][0]["symbol"] == "ASELS"
        assert "yükseliş yönünde" in body["entries"][0]["sentence"]
        assert body["headline"].startswith("Son 24 saatte")

    def test_the_measurement_comes_from_the_candles(self, client, mocker):
        """Sayı modelden değil, ölçümden. Fiyat serisi olmadan bu alan yok."""
        mocker.patch.object(news_impact, "impacts_since", return_value=[_impact()])
        entry = client.get(DIGEST).json()["entries"][0]
        assert entry["measured"]["typicalMovePct"] is not None
        assert "Ölçülen:" in entry["sentence"]

    def test_an_empty_window_still_returns_a_body(self, client, mocker):
        """Sessizce kaybolan bir panel, veri yokluğunu özellik yokluğu gibi
        gösterirdi."""
        mocker.patch.object(news_impact, "impacts_since", return_value=[])
        body = client.get(DIGEST).json()
        assert body["entries"] == []
        assert "bulunmuyor" in body["headline"]
        assert body["disclaimer"] == news_impact.DISCLAIMER_TR

    def test_the_disclaimer_is_unconditional(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[_impact()])
        assert client.get(DIGEST).json()["disclaimer"] == news_impact.DISCLAIMER_TR

    def test_the_window_is_carried_back(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[])
        assert client.get(f"{DIGEST}?hours=48").json()["windowHours"] == 48

    def test_an_out_of_range_window_is_refused(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[])
        assert client.get(f"{DIGEST}?hours=0").status_code == 422
        assert client.get(f"{DIGEST}?hours=999").status_code == 422

    def test_symbols_are_ordered_by_comment_count(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[
            _impact(symbol="AAA"),
            _impact(symbol="BBB"), _impact(symbol="BBB", news_id="n2"),
        ])
        body = client.get(DIGEST).json()
        assert [entry["symbol"] for entry in body["entries"]] == ["BBB", "AAA"]

    def test_the_twin_endpoint_names_its_user_in_the_path(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[_impact()])
        body = client.get(f"{DIGEST}/{USER}").json()
        assert body["entries"][0]["symbol"] == "ASELS"

    def test_the_twin_endpoint_is_guarded(self, mocker):
        """Korumasızken bir kullanıcı id'si bilen herkes o kişinin tuttuğu
        sembolleri okuyabilirdi."""
        from fastapi.testclient import TestClient

        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            with TestClient(app) as guarded:
                # 503 de bir REDDETME: anahtar tanımsızken koruma ucu
                # açmıyor, kapatıyor (`require_service_token`). Test ortamında
                # anahtar yok, dolayısıyla beklenen cevap budur -- önemli olan
                # 200 OLMAMASI.
                assert guarded.get(f"{DIGEST}/{USER}").status_code in (401, 403, 503)
        finally:
            app.dependency_overrides.clear()


class TestImpactSummary:
    def test_the_market_wide_read_needs_no_session(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[_impact()])
        body = client.get(SUMMARY).json()
        assert body["entries"][0]["symbol"] == "ASELS"
        assert body["disclaimer"] == news_impact.DISCLAIMER_TR

    def test_no_price_is_measured_here(self, client, mocker):
        """Kullanıcının hiç sormadığı on iki sembol için mum okumak, yapılmamış
        olması gereken bir iş olurdu."""
        mocker.patch.object(news_impact, "impacts_since", return_value=[_impact()])
        assert client.get(SUMMARY).json()["entries"][0]["measured"] is None

    def test_the_limit_is_honoured(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[
            _impact(symbol=f"S{index}") for index in range(20)
        ])
        assert len(client.get(f"{SUMMARY}?limit=3").json()["entries"]) == 3

    def test_an_empty_window_returns_an_empty_list(self, client, mocker):
        mocker.patch.object(news_impact, "impacts_since", return_value=[])
        body = client.get(SUMMARY).json()
        assert body["entries"] == [] and body["windowHours"] == 24
