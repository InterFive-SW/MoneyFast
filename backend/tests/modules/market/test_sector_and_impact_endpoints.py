"""Sektör eşlemesi ve haber etkisi olgu paketi.

İkisi de Bölüm 12'nin veri yolları: biri ajanın sektörü uydurmasını
engelliyor, diğeri haber okumasının üzerine kurulacağı ÖLÇÜLMÜŞ zemini
veriyor.

Yoldan kullanıcı adı alan uç servis token'ı istiyor: korumasızken bir
kullanıcı id'si bilen herkes o kişinin tuttuğu sembolleri okuyabilirdi.
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
from app.modules.market import impact

USER = "11111111-1111-1111-1111-111111111111"


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


class TestSectors:
    """Sembol -> sektör. Kapatılan boşluk: `sector_by_symbol()` vardı ve
    ekranları besliyordu, ama hiçbir MCP aracı sektör döndürmüyordu."""

    URL = "/api/market/sectors"

    def test_the_map_is_grouped_by_sector(self, client, mocker):
        mocker.patch.object(
            market_service, "sector_by_symbol",
            return_value={"AKBNK": "Financial Services", "GARAN": "Financial Services",
                          "THYAO": "Industrials"},
        )
        mocker.patch.object(market_service, "count_active_products", return_value=5)
        body = client.get(self.URL).json()
        assert [row["sector"] for row in body["sectors"]] == [
            "Financial Services", "Industrials"]
        assert body["sectors"][0]["symbols"] == ["AKBNK", "GARAN"]

    def test_the_unclassified_count_is_measured_not_guessed(self, client, mocker):
        """Neyi kaçırdığını söylemeyen bir harita, tam bir harita gibi
        okunur."""
        mocker.patch.object(
            market_service, "sector_by_symbol",
            return_value={"AKBNK": "Financial Services"},
        )
        mocker.patch.object(market_service, "count_active_products", return_value=10)
        assert client.get(self.URL).json()["unclassified"] == 9

    def test_an_instrument_without_a_sector_is_absent_not_blank(self, client, mocker):
        """Boş bir dize döndürmek, ölçülmemiş bir sektörü ölçülmüş gibi
        gösterirdi."""
        mocker.patch.object(
            market_service, "sector_by_symbol",
            return_value={"AKBNK": "Financial Services"},
        )
        mocker.patch.object(market_service, "count_active_products", return_value=2)
        body = client.get(self.URL).json()
        assert "THYAO" not in body["symbols"]
        assert all(row["sector"] for row in body["sectors"])

    def test_an_empty_universe_is_a_valid_answer(self, client, mocker):
        mocker.patch.object(market_service, "sector_by_symbol", return_value={})
        mocker.patch.object(market_service, "count_active_products", return_value=0)
        body = client.get(self.URL).json()
        assert body["sectors"] == [] and body["unclassified"] == 0

    def test_a_sector_filter_narrows_the_map(self, client, mocker):
        """Süzgeç SUNUCUDA: bin satırlık bir sözlük, tek bir sektör
        sorulduğunda okunmayacak bir yük.

        Türkçe ad sağlayıcının İngilizce etiketine ÇEVRİLİYOR: çeviri yokken
        "bankacılık" hiçbir şeyle eşleşmiyor ve sonuç, veri duruyorken boş
        dönüyordu."""
        mocker.patch.object(
            market_service, "sector_by_symbol",
            return_value={"AKBNK": "Financial Services", "THYAO": "Industrials"},
        )
        mocker.patch.object(market_service, "count_active_products", return_value=2)
        body = client.get(f"{self.URL}?sector=bankacılık").json()
        assert [row["sector"] for row in body["sectors"]] == ["Financial Services"]
        assert set(body["symbols"]) == {"AKBNK"}

    def test_the_filter_ignores_case(self, client, mocker):
        """Sağlayıcının etiketi İngilizce ve çağıranın onu birebir yazmasını
        beklemek, bir eşleşmeyi yazım tercihine bağlamak olurdu."""
        mocker.patch.object(
            market_service, "sector_by_symbol",
            return_value={"AKBNK": "Financial Services"},
        )
        mocker.patch.object(market_service, "count_active_products", return_value=1)
        body = client.get(f"{self.URL}?sector=FINANCIAL services").json()
        assert body["sectors"][0]["sector"] == "Financial Services"

    def test_an_unknown_sector_is_an_empty_answer_not_an_error(self, client, mocker):
        mocker.patch.object(
            market_service, "sector_by_symbol",
            return_value={"AKBNK": "Financial Services"},
        )
        mocker.patch.object(market_service, "count_active_products", return_value=1)
        body = client.get(f"{self.URL}?sector=Uzay").json()
        assert body["sectors"] == [] and body["symbols"] == {}

    def test_no_session_is_required(self, client, mocker):
        """Bu eşleme kullanıcıya ait hiçbir şey içermiyor."""
        mocker.patch.object(market_service, "sector_by_symbol", return_value={})
        mocker.patch.object(market_service, "count_active_products", return_value=0)
        assert client.get(self.URL).status_code == 200


class TestImpactPackageEndpoint:
    """Deterministik olgu paketi. Konusunu YOLDA adlandırıyor, dolayısıyla
    servis token'ıyla korunuyor: korumasızken bir kullanıcı id'si bilen
    herkes o kişinin TUTTUĞU SEMBOLLERİ okuyabilirdi."""

    URL = f"/api/market/news/impact/{USER}"

    def _wire(self, mocker, rows=(), holdings=None):
        from app.modules.market import service as market_module

        mocker.patch.object(
            market_service, "holdings",
            return_value=holdings if holdings is not None else [
                {"symbol": "AKBNK", "name": "Akbank", "quantity": 10}
            ],
        )
        mocker.patch.object(
            market_service, "candle_closes",
            return_value=[(None, 100.0 + index) for index in range(60)],
        )
        mocker.patch.object(
            market_service, "fundamentals_for", return_value={"pe_ratio": 4.2}
        )
        mocker.patch.object(
            market_service, "sector_by_symbol",
            return_value={"AKBNK": "Financial Services"},
        )
        mocker.patch.object(
            market_module, "portfolio_news",
            return_value=(list(rows), {"AKBNK": len(rows)}),
        )

    def test_the_session_endpoint_serves_the_same_body(self, client, mocker):
        """Ayrışsalardı ekran ile sohbet aynı portföy için farklı sayılar
        gösterebilirdi."""
        self._wire(mocker)
        mine = client.post("/api/market/news/impact").json()
        named = client.post(self.URL).json()
        assert mine == named

    def test_the_session_endpoint_needs_a_session(self, client, mocker):
        """"Portföyünüz" başlığı altında başkasının pozisyonlarını ölçmek,
        `/news/portfolio`nun kaçındığı hatanın aynısı olurdu."""
        from fastapi.testclient import TestClient

        from app.main import app

        self._wire(mocker)
        app.dependency_overrides.pop(get_current_user_id, None)
        with TestClient(app) as anonymous:
            assert anonymous.post("/api/market/news/impact").status_code == 401

    def test_it_builds_a_package(self, client, mocker):
        self._wire(mocker)
        body = client.post(self.URL).json()
        assert body["symbols"][0]["symbol"] == "AKBNK"
        assert body["symbols"][0]["sector"] == "Financial Services"
        assert body["coverage"]["symbols"] == 1

    def test_the_window_travels(self, client, mocker):
        self._wire(mocker)
        assert client.post(f"{self.URL}?days=30").json()["window_days"] == 30

    def test_an_out_of_range_window_is_refused(self, client, mocker):
        self._wire(mocker)
        assert client.post(f"{self.URL}?days=0").status_code == 422

    def test_the_symbol_limit_is_bounded(self, client, mocker):
        self._wire(mocker)
        assert client.post(f"{self.URL}?limit=0").status_code == 422
        assert client.post(f"{self.URL}?limit=99").status_code == 422

    def test_without_a_service_token_it_is_refused(self, client, monkeypatch):
        from fastapi.testclient import TestClient

        from app.main import app

        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            with TestClient(app) as guarded:
                assert guarded.post(self.URL).status_code in (401, 403, 503)
        finally:
            app.dependency_overrides.clear()
