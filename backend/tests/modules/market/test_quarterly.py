"""Çeyreklik gelir tablosu serisi.

`instrument_fundamentals` bir ANLIK GÖRÜNTÜ: alan başına tek güncel değer,
her turda üstüne yazılıyor. Bu tablo dönem dönem biriktiriyor ve "son çeyrek
kârı önceki çeyreğe göre" cümlesini ilk kez mümkün kılan şey bu.

Bu dosyanın koruduğu asıl şey BİTİŞİKLİK. Sağlayıcının dönemleri ardışık
gelmiyor: evrenden rastgele 40 BIST hissesi ölçüldüğünde 3'ünde 2025Q3 gelir
tablosunda hiç yoktu (nakit akışında vardı). "Son iki satırı al" diyen bir
karşılaştırma o hisselerde 2025Q2 ile 2025Q4'ü kıyaslar ve bunu SÖYLEMEZ.
Kural sunucuda, tek yerde: her tüketicinin aynı hatayı ayrı ayrı yapmaması
için.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.investment import market_service


def row(period_end: date, net_income=1_000, **overrides):
    base = dict(
        period_end=period_end,
        total_revenue=10_000,
        net_income=net_income,
        pretax_income=1_200,
        operating_expense=3_000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _db(rows, product=SimpleNamespace(id="p1", symbol="AKBNK", name="Akbank",
                                      currency_code="TRY")):
    db = MagicMock(spec=Session)
    chain = db.query.return_value.filter.return_value.order_by.return_value
    chain.limit.return_value.all.return_value = rows
    return db


class TestQuarterLabel:
    @pytest.mark.parametrize("day,label", [
        (date(2026, 3, 31), "2026Q1"),
        (date(2026, 6, 30), "2026Q2"),
        (date(2026, 9, 30), "2026Q3"),
        (date(2025, 12, 31), "2025Q4"),
    ])
    def test_the_label_comes_from_the_period_end(self, day, label):
        """Etiket saklanmıyor, türetiliyor: hiçbir zaman değişmeyecek ve
        tamamen dönem sonundan çıkarılabilen bir değer için ikinci bir sütun,
        ikisinin ayrışabileceği bir yer açardı."""
        assert market_service.quarter_label(day) == label

    def test_a_mid_quarter_date_still_lands_in_its_quarter(self):
        assert market_service.quarter_label(date(2026, 1, 31)) == "2026Q1"


class TestAdjacency:
    def test_consecutive_quarters_are_adjacent(self):
        assert market_service._quarter_index(date(2026, 6, 30)) - \
            market_service._quarter_index(date(2026, 3, 31)) == 1

    def test_a_missing_quarter_shows_as_a_gap_of_two(self):
        """Ölçülen gerçek durum: AKBNK, GARAN ve EREGL'de 2025Q3 yok."""
        assert market_service._quarter_index(date(2025, 12, 31)) - \
            market_service._quarter_index(date(2025, 6, 30)) == 2

    def test_a_year_is_four_quarters(self):
        assert market_service._quarter_index(date(2026, 6, 30)) - \
            market_service._quarter_index(date(2025, 6, 30)) == 4


class TestQuarterlyFor:
    @pytest.fixture(autouse=True)
    def _product(self, mocker):
        mocker.patch.object(
            market_service, "get_product",
            return_value=SimpleNamespace(id="p1", symbol="AKBNK", name="Akbank",
                                         currency_code="TRY"),
        )

    def test_the_series_comes_back_newest_first_with_labels(self):
        rows = [row(date(2026, 6, 30)), row(date(2026, 3, 31))]
        found = market_service.quarterly_for(_db(rows), "AKBNK")
        assert [p["label"] for p in found["periods"]] == ["2026Q2", "2026Q1"]

    def test_an_adjacent_previous_quarter_is_reported(self):
        rows = [row(date(2026, 6, 30)), row(date(2026, 3, 31))]
        assert market_service.quarterly_for(_db(rows), "AKBNK")["previous_is_adjacent"]

    def test_a_gap_before_the_latest_quarter_is_reported(self):
        """ASIL KORUNAN ŞEY. 2025Q4 ile 2025Q2 arasında 2025Q3 yok; bir
        karşılaştırma bunu bilmeden yapılamaz."""
        rows = [row(date(2025, 12, 31)), row(date(2025, 6, 30))]
        found = market_service.quarterly_for(_db(rows), "AKBNK")
        assert found["previous_is_adjacent"] is False

    def test_a_single_quarter_has_no_previous(self):
        found = market_service.quarterly_for(_db([row(date(2026, 6, 30))]), "AKBNK")
        assert found["previous_is_adjacent"] is False
        assert found["year_ago_available"] is False

    def test_the_year_ago_quarter_is_found_across_a_gap(self):
        """Bir yıl öncesi, ARADAKİ boşluktan bağımsız: 2026Q2'nin karşılığı
        2025Q2 ve o elimizde olduğu sürece yıllık karşılaştırma yapılabilir."""
        rows = [row(date(2026, 6, 30)), row(date(2026, 3, 31)),
                row(date(2025, 12, 31)), row(date(2025, 6, 30))]
        assert market_service.quarterly_for(_db(rows), "AKBNK")["year_ago_available"]

    def test_a_year_ago_quarter_that_is_absent_is_reported_absent(self):
        rows = [row(date(2026, 6, 30)), row(date(2026, 3, 31))]
        assert market_service.quarterly_for(_db(rows), "AKBNK")["year_ago_available"] is False

    def test_a_null_figure_stays_null(self):
        """34 hissenin 16'sında serinin bir yerinde eksik değer var. Sıfıra
        çevirmek "o çeyrek raporlandı, kâr sıfır çıktı" demek olurdu."""
        rows = [row(date(2026, 6, 30), net_income=None)]
        found = market_service.quarterly_for(_db(rows), "AKBNK")
        assert found["periods"][0]["net_income"] is None

    def test_an_instrument_with_no_rows_returns_nothing(self):
        assert market_service.quarterly_for(_db([]), "AKBNK") is None

    def test_an_unknown_symbol_returns_nothing(self, mocker):
        mocker.patch.object(market_service, "get_product", return_value=None)
        assert market_service.quarterly_for(_db([row(date(2026, 6, 30))]), "YOKBU") is None

    def test_the_instrument_currency_travels(self):
        found = market_service.quarterly_for(_db([row(date(2026, 6, 30))]), "AKBNK")
        assert found["currency"] == "TRY"


class TestUpsert:
    def _db_with_universe(self):
        db = MagicMock(spec=Session)
        db.query.return_value.all.return_value = [
            SimpleNamespace(id="p1", symbol="AKBNK"),
            SimpleNamespace(id="p2", symbol="THYAO"),
        ]
        return db

    def test_an_empty_batch_writes_nothing(self):
        db = MagicMock(spec=Session)
        assert market_service.upsert_quarterly(db, []) == 0
        assert db.execute.called is False

    def test_rows_are_written_for_known_symbols(self):
        db = self._db_with_universe()
        written = market_service.upsert_quarterly(db, [
            {"symbol": "AKBNK", "period_end": "2026-06-30", "net_income": 5},
            {"symbol": "THYAO", "period_end": "2026-06-30", "net_income": 7},
        ])
        assert written == 2
        assert db.commit.called

    def test_an_unknown_symbol_is_skipped_not_invented(self):
        """Evrende karşılığı olmayan bir sembol için satır yazmak, hiçbir
        enstrümana bağlı olmayan bir kayıt bırakırdı."""
        db = self._db_with_universe()
        assert market_service.upsert_quarterly(
            db, [{"symbol": "YOKBU", "period_end": "2026-06-30"}]
        ) == 0
        assert db.execute.called is False

    def test_the_symbol_is_matched_case_insensitively(self):
        db = self._db_with_universe()
        assert market_service.upsert_quarterly(
            db, [{"symbol": "akbnk", "period_end": "2026-06-30"}]
        ) == 1

    def test_a_row_without_a_symbol_is_skipped(self):
        db = self._db_with_universe()
        assert market_service.upsert_quarterly(db, [{"period_end": "2026-06-30"}]) == 0


class TestEndpoints:
    """İki uç: okuma herkese açık, yazma servis token'ıyla."""

    @pytest.fixture
    def api(self, mocker):
        from fastapi.testclient import TestClient

        from app.core.database import get_db
        from app.main import app

        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            with TestClient(app) as client:
                yield client
        finally:
            app.dependency_overrides.pop(get_db, None)

    SERIES = {
        "symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
        "periods": [{"period_end": "2026-06-30", "label": "2026Q2",
                     "total_revenue": None, "net_income": 15,
                     "pretax_income": None, "operating_expense": None}],
        "previous_is_adjacent": True, "year_ago_available": True,
    }

    def test_the_series_is_returned(self, api, mocker):
        mocker.patch.object(market_service, "quarterly_for", return_value=self.SERIES)
        body = api.get("/api/market/quarterly?symbol=AKBNK").json()
        assert body["periods"][0]["label"] == "2026Q2"
        assert body["previous_is_adjacent"] is True

    def test_an_instrument_without_data_is_an_empty_series_not_a_404(self, api, mocker):
        """Ölçülen kapsamada evrenin ~%15'i için "veri yok" DOĞRU cevap;
        404 ise "böyle bir şirket yok" der ve bu yanlış."""
        mocker.patch.object(market_service, "quarterly_for", return_value=None)
        mocker.patch.object(
            market_service, "resolve_symbol",
            return_value=SimpleNamespace(symbol="AKBNK", name="Akbank",
                                         currency_code="TRY"),
        )
        response = api.get("/api/market/quarterly?symbol=akbnk")
        assert response.status_code == 200
        assert response.json() == {
            "symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
            "periods": [],
            # Boş dalda bayraklar şemanın varsayılanından geliyor ve o
            # varsayılan FALSE olmak zorunda: hiç dönemi olmayan bir seride
            # "önceki çeyrekle bitişik" demek, yapılamayacak bir kıyası
            # yapılabilir göstermek olurdu.
            "previous_is_adjacent": False, "year_ago_available": False,
        }

    def test_an_unknown_symbol_still_answers_in_its_own_terms(self, api, mocker):
        """Enstrüman hiç çözülmese bile boş seri: sembol kullanıcının yazdığı
        gibi değil, büyük harfe çevrilmiş olarak geri döner."""
        mocker.patch.object(market_service, "quarterly_for", return_value=None)
        mocker.patch.object(market_service, "resolve_symbol", return_value=None)
        body = api.get("/api/market/quarterly?symbol=yok").json()
        assert body["symbol"] == "YOK"
        assert body["currency"] == "TRY"
        assert body["periods"] == []

    def test_a_nameless_product_falls_back_to_the_symbol(self, api, mocker):
        mocker.patch.object(market_service, "quarterly_for", return_value=None)
        mocker.patch.object(
            market_service, "resolve_symbol",
            return_value=SimpleNamespace(symbol="AKBNK", name=None, currency_code=None),
        )
        body = api.get("/api/market/quarterly?symbol=akbnk").json()
        assert body["name"] == "AKBNK"
        assert body["currency"] == "TRY"

    def test_rows_are_written(self, api, mocker, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        spy = mocker.patch.object(market_service, "upsert_quarterly", return_value=2)
        response = api.post(
            "/api/market/quarterly/ingest",
            headers={"Authorization": "Bearer secret"},
            json={"items": [{"symbol": "AKBNK", "period_end": "2026-06-30",
                             "net_income": 15}]},
        )
        assert response.json()["quarterly_written"] == 2
        assert spy.called

    def test_an_unreported_line_reaches_the_store_as_none(self, api, mocker, monkeypatch):
        """Eksik kalem sıfır değil: sağlayıcının o çeyrek için yayımlamadığı
        bir satır, sıfır kâr açıklamış bir şirketten farklıdır."""
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        spy = mocker.patch.object(market_service, "upsert_quarterly", return_value=1)
        api.post(
            "/api/market/quarterly/ingest",
            headers={"Authorization": "Bearer secret"},
            json={"items": [{"symbol": "AKBNK", "period_end": "2026-06-30",
                             "net_income": 15}]},
        )
        assert spy.call_args.args[1][0]["total_revenue"] is None

    def test_it_is_guarded_like_the_other_ingests(self, api, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        assert api.post("/api/market/quarterly/ingest",
                        json={"items": []}).status_code == 401
