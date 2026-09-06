"""Fon uçları — TEFAS.

`Fonlar` ekranı `MOCK_FUNDS` üzerinden çiziliyordu. Buradaki iddialar
arkasındaki gerçek veriye dair: süzgeçler SUNUCUDA (evren 2.602 fon),
getiriler NAV serisinden HESAPLANIYOR, ve fon günde TEK fiyat yayımladığı
için günlük mum diye bir şey yok.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_service_token
from app.main import app
from app.modules.market import funds as funds_service


def fund(code="AFA", title="ATA PORTFÖY"):
    return SimpleNamespace(
        code=code, title=title, founder="ATA", operator="ATA",
        umbrella="ALTIN", fund_type="YAT", price=12.5, shares=1000.0,
        investors=500, size=12500.0, as_of=date(2026, 9, 4),
        category_rank=71, category_size=86, active=True,
    )


def price(day: str, value: float):
    return SimpleNamespace(as_of=date.fromisoformat(day), price=value)


@pytest.fixture
def db():
    return MagicMock(spec=Session)


@pytest.fixture
def client(db, mocker):
    mocker.patch.object(funds_service, "list_funds", return_value=[fund()])
    mocker.patch.object(
        funds_service, "facets",
        return_value={"founders": ["ATA"], "umbrellas": ["ALTIN"]},
    )
    mocker.patch.object(
        funds_service, "price_series",
        return_value=[price("2026-09-01", 12.0), price("2026-09-04", 12.5)],
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_service_token] = lambda: None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


class TestListing:
    def test_the_filters_travel_to_the_query_not_the_browser(self, client):
        """Evren 2.602 fon; hepsini tarayıcıya gönderip orada süzmek, her
        açılışta birkaç yüz kilobayt ve süzgeç mantığının ikinci bir
        kopyası demekti."""
        response = client.get(
            "/api/market/funds?founder=ATA&umbrella=ALTIN&fund_type=YAT&q=ata&limit=5"
        )
        assert response.status_code == 200
        kwargs = funds_service.list_funds.call_args.kwargs
        assert kwargs["founder"] == "ATA"
        assert kwargs["search"] == "ata"
        assert kwargs["limit"] == 5

    def test_the_dropdowns_come_from_the_data(self, client):
        body = client.get("/api/market/funds").json()
        assert body["founders"] == ["ATA"]
        assert body["umbrellas"] == ["ALTIN"]

    def test_a_row_carries_tefas_own_category_measurements(self, client):
        """Bir getirinin iyi mi kötü mü olduğunu tek başına getiri
        söylemiyor; sıra söylüyor.

        "Kategori getirisi" ARTIK YOK: `fonProfilDtyGetir` kategorinin
        ortalamasını değil, karşılaştırma göstergelerini döndürüyor ve
        yanıt her fon için aynı -- ekrandaki sayı 1.021 fonda aynıydı
        (migration 0041)."""
        row = client.get("/api/market/funds").json()["items"][0]
        assert row["categoryRank"] == 71
        assert row["categorySize"] == 86
        assert "categoryReturn" not in row

    def test_a_limit_beyond_the_ceiling_is_refused(self, client):
        assert client.get(
            f"/api/market/funds?limit={funds_service.MAX_LIMIT + 1}"
        ).status_code == 422


class TestSingleFund:
    def test_a_known_code_is_returned(self, client):
        assert client.get("/api/market/funds/AFA").json()["code"] == "AFA"

    def test_an_unknown_code_is_a_404(self, client):
        """Boş bir fon kartı çizmek, olmayan bir fonu varmış gibi
        gösterirdi."""
        assert client.get("/api/market/funds/YOK").status_code == 404


class TestSeries:
    def test_the_series_is_returned_oldest_first(self, client):
        body = client.get("/api/market/funds/AFA/prices").json()
        assert [p["date"] for p in body["points"]] == ["2026-09-01", "2026-09-04"]

    def test_an_unknown_code_is_an_empty_series_not_an_error(self, client, mocker):
        """"Bu fonun geçmişi yok" bir CEVAPTIR ve grafik onu boş çizebilir --
        `/market/candles` ile aynı duruş."""
        mocker.patch.object(funds_service, "price_series", return_value=[])
        body = client.get("/api/market/funds/YOK/prices").json()
        assert body["points"] == []
        assert body["code"] == "YOK"


class TestCandles:
    def test_the_bucket_width_travels_with_the_candles(self, client, mocker):
        """Kullanıcı baktığı çubuğun bir günü mü bir haftayı mı özetlediğini
        bilmeli."""
        mocker.patch.object(funds_service, "candles", return_value=[])
        body = client.get("/api/market/funds/AFA/candles?window=1Y").json()
        assert body["bucket"] == "month"

    def test_an_unknown_window_is_refused_rather_than_defaulted(self, client):
        response = client.get("/api/market/funds/AFA/candles?window=17G")
        assert response.status_code == 422
        assert "17G" in response.json()["detail"]


class TestServiceEndpoints:
    def test_the_ingest_writes_rows_prices_and_quotes(self, client, db, mocker):
        """Kotasyon da tazeleniyor: portföy değeri ve bekleyen fon emirleri
        `market_quotes`tan okuyor, `market.funds`tan değil."""
        mocker.patch.object(funds_service, "upsert_funds", return_value=2)
        mocker.patch.object(funds_service, "upsert_prices", return_value=5)
        mocker.patch.object(funds_service, "sync_quotes", return_value=1)

        body = client.post(
            "/api/market/funds/ingest",
            json={"funds": [{"code": "AFA", "title": "ATA"}], "prices": []},
        ).json()
        assert body == {"funds_written": 2, "prices_written": 5, "quotes_written": 1}
        db.commit.assert_called_once()

    def test_the_collector_reads_what_is_missing(self, client, mocker):
        """Şemsiye türü ve NAV serisi fon BAŞINA birer istek; eksikleri
        bilmeden her tur baştan başlardı."""
        mocker.patch.object(
            funds_service, "coverage",
            return_value={"missing_prices": ["AFA"], "missing_category": []},
        )
        body = client.get("/api/market/funds/meta/coverage").json()
        assert body["missing_prices"] == ["AFA"]
