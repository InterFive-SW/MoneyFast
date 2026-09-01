"""Portföy geneli teknik görünüm.

Motor tek enstrüman için yazılmıştı; bu katman onu portföye toplulaştırıyor.
Korunan asıl ayrım SAYI ile DEĞER: üç pozisyonun ikisinin ortalamasının
altında olmasıyla portföy değerinin %95'inin altında olması farklı şeyler ve
tek bir yüzde vermek hangisinin kastedildiğini okunamaz yapardı. Ölçülen test
portföyünde ikisi tam olarak bu kadar ayrışıyor.

İkinci ayrım: "ortalamasının üzerinde DEĞİL" ile "ortalaması hesaplanamadı"
karşıt iddialar. Geçmişi yetmeyen pozisyon hiçbir tarafa sayılmaz, adıyla
raporlanır.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.main import app
from app.modules.investment import ai_service, market_service
from app.modules.market import technicals

URL = "/api/market/portfolio/technical"


def _row(symbol, trend="UPTREND", pct_50=2.0, value=100.0):
    return {
        "symbol": symbol,
        "signals": {"trend": trend, "pct_from_sma_50": pct_50},
        "value": value,
    }


class TestAggregate:
    def test_counts_and_weight_are_reported_separately(self):
        """Ölçülen gerçek durum: iki pozisyon altta ama değerin neredeyse
        tamamı onlarda. Tek bir yüzde bunu gizlerdi."""
        summary = technicals.aggregate([
            _row("BUYUK", "DOWNTREND", -9.0, value=950.0),
            _row("ORTA", "DOWNTREND", -4.0, value=40.0),
            _row("KUCUK", "UPTREND", 1.3, value=10.0),
        ])
        assert summary["below_sma_50"] == 2
        assert summary["above_sma_50"] == 1
        assert summary["weight_below_sma_50"] == pytest.approx(0.99, abs=0.005)

    def test_trend_counts_cover_the_three_measured_states(self):
        summary = technicals.aggregate([
            _row("A", "UPTREND"), _row("B", "DOWNTREND", -2.0),
            _row("C", "SIDEWAYS", 0.4), _row("D", "SIDEWAYS", -0.2),
        ])
        assert summary["by_trend"] == {"UPTREND": 1, "DOWNTREND": 1, "SIDEWAYS": 2}

    def test_a_position_without_a_moving_average_is_counted_on_neither_side(self):
        """"Üzerinde değil" ile "hesaplanamadı" aynı şey değil."""
        summary = technicals.aggregate([
            _row("A", "UPTREND", 3.0),
            {"symbol": "YENI", "signals": {"trend": "UNKNOWN", "pct_from_sma_50": None}},
        ])
        assert summary["below_sma_50"] == 0
        assert summary["above_sma_50"] == 1
        assert summary["measured_count"] == 1
        assert summary["position_count"] == 2
        assert summary["unmeasured_symbols"] == ["YENI"]

    def test_an_unmeasured_position_is_named_in_the_sentence(self):
        summary = technicals.aggregate([
            _row("A", "UPTREND", 3.0),
            {"symbol": "YENI", "signals": {"trend": "UNKNOWN", "pct_from_sma_50": None}},
        ])
        assert "YENI" in summary["statement"]
        assert "yeterli fiyat geçmişi yok" in summary["statement"]

    def test_a_position_without_a_symbol_still_reports_as_unmeasured(self):
        summary = technicals.aggregate([{"signals": {"trend": "UNKNOWN"}}])
        assert summary["unmeasured_symbols"] == ["?"]

    def test_a_row_with_no_signals_block_does_not_crash(self):
        summary = technicals.aggregate([{"symbol": "A"}])
        assert summary["by_trend"] == {"UPTREND": 0, "DOWNTREND": 0, "SIDEWAYS": 0}

    def test_an_unconvertible_position_is_excluded_from_the_weight(self):
        """Kuru olmayan pozisyon toplama katılmaz; 1.0 varsaymak 481 dolarlık
        bir varlığı 481 lira saymak olurdu."""
        summary = technicals.aggregate([
            _row("TRY_HISSE", "DOWNTREND", -5.0, value=100.0),
            {"symbol": "USD_HISSE", "signals": {"trend": "UPTREND", "pct_from_sma_50": 2.0},
             "value": None},
        ])
        assert summary["weight_below_sma_50"] == pytest.approx(1.0)
        assert summary["below_sma_50"] == 1
        assert summary["above_sma_50"] == 1

    def test_no_value_at_all_leaves_the_weight_unknown_not_zero(self):
        """Sıfır ağırlık, "hiçbiri altında değil" diye okunurdu."""
        summary = technicals.aggregate([
            {"symbol": "A", "signals": {"trend": "DOWNTREND", "pct_from_sma_50": -3.0}},
        ])
        assert summary["weight_below_sma_50"] is None
        assert "portföy değerinin" not in summary["statement"]

    def test_an_empty_portfolio_says_why_rather_than_reporting_zero(self):
        summary = technicals.aggregate([])
        assert summary["statement"] == technicals.NO_MEASURABLE_TR
        assert summary["position_count"] == 0

    def test_a_measured_position_with_no_trend_produces_no_trend_clause(self):
        """Savunmacı dal. `compute` bu ikiliyi üretmez -- 50 günlük ortalaması
        olan bir serinin 20 günlüğü de vardır, dolayısıyla eğilim ölçülür --
        ama `aggregate` kendisine ne verilirse onu işliyor ve boş bir eğilim
        listesi cümleyi "...altında; ." hâline getirirdi."""
        summary = technicals.aggregate([
            {"symbol": "A", "signals": {"trend": "UNKNOWN", "pct_from_sma_50": -3.0}},
        ])
        # Eğilim yan cümlesi hiç kurulmuyor; ortalama ölçümü ise duruyor.
        # İkisi ayrı ölçüm, dolayısıyla aynı pozisyon birinde sayılıp
        # diğerinde "geçmişi yetmiyor" olarak anılabilir.
        assert "eğiliminde" not in summary["statement"]
        assert "ortalamasının altında." in summary["statement"]
        assert summary["measured_count"] == 1
        assert summary["unmeasured_symbols"] == ["A"]

    def test_a_portfolio_with_no_history_says_why(self):
        summary = technicals.aggregate([
            {"symbol": "A", "signals": {"trend": "UNKNOWN", "pct_from_sma_50": None}},
        ])
        assert summary["statement"] == technicals.NO_MEASURABLE_TR

    def test_the_sentence_says_positions_not_portfolio(self):
        """"Portföyünüzün %66'sı" değerden bahsediyormuş gibi okunur; sayım
        adedi ölçüyor."""
        summary = technicals.aggregate([
            _row("A", "DOWNTREND", -3.0, value=50.0),
            _row("B", "UPTREND", 3.0, value=50.0),
        ])
        assert "2 pozisyonunuzun 1'i" in summary["statement"]
        assert "portföy değerinin %50,0'i" in summary["statement"]

    @pytest.mark.parametrize("count,expected", [(1, "1'i"), (5, "5'i"), (6, "6'sı"), (99, "99'i")])
    def test_the_possessive_suffix_follows_how_the_number_is_read(self, count, expected):
        """Ek rakamın yazılışına değil okunuşuna uyar: "altı" -> "6'sı".
        Tablonun dışındaki bir sayı en yaygın eki alır, uydurma değil."""
        assert technicals._plural_locative(count) == expected


@pytest.fixture
def as_user(client):
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)


class TestEndpoint:
    @pytest.fixture(autouse=True)
    def _stubs(self, mocker):
        mocker.patch.object(market_service, "latest_quotes", return_value={})
        mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0})
        mocker.patch.object(
            market_service, "candle_series",
            return_value=[{"close": 10.0 + i, "timestamp": f"2026-01-{i + 1:02d}",
                           "volume": 100} for i in range(60)],
        )

    def test_every_position_carries_its_own_reading(self, as_user, mocker):
        mocker.patch.object(
            market_service, "holdings",
            return_value=[
                {"symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
                 "quantity": 10, "price": 60.0},
            ],
        )
        mocker.patch.object(ai_service, "holding_value", return_value=600.0)
        body = as_user.get(URL).json()
        assert body["positions"][0]["symbol"] == "AKBNK"
        assert body["positions"][0]["signals"]["trend"] == "UPTREND"
        assert body["positions"][0]["narrative"].startswith("AKBNK,")
        assert body["summary"]["position_count"] == 1

    def test_the_page_and_the_summary_read_the_same_engine(self, as_user, mocker):
        """Tek hisse görünümüyle aynı `compute`/`narrate`: iki yüzeyin aynı
        hisse için farklı bir eğilim söylemesi mümkün olmamalı."""
        mocker.patch.object(
            market_service, "holdings",
            return_value=[{"symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
                           "quantity": 1, "price": 60.0}],
        )
        mocker.patch.object(ai_service, "holding_value", return_value=60.0)
        compute = mocker.spy(technicals, "compute")
        as_user.get(URL)
        assert compute.called

    def test_an_unconvertible_position_is_named_not_dropped(self, as_user, mocker):
        mocker.patch.object(
            market_service, "holdings",
            return_value=[{"symbol": "AAPL", "name": "Apple", "currency": "USD",
                           "quantity": 1, "price": 300.0}],
        )
        mocker.patch.object(ai_service, "holding_value", return_value=None)
        body = as_user.get(URL).json()
        assert body["unconvertible"] == ["AAPL"]
        # Düşürülmüyor: teknik durumu ölçülebiliyor, yalnızca ağırlığı değil.
        assert body["positions"][0]["symbol"] == "AAPL"
        assert body["positions"][0]["value"] is None

    def test_a_holding_without_a_name_falls_back_to_its_symbol(self, as_user, mocker):
        mocker.patch.object(
            market_service, "holdings",
            return_value=[{"symbol": "AKBNK", "currency": None, "quantity": 1, "price": 1.0}],
        )
        mocker.patch.object(ai_service, "holding_value", return_value=1.0)
        body = as_user.get(URL).json()
        assert body["positions"][0]["name"] == "AKBNK"
        assert body["positions"][0]["currency"] == "TRY"

    def test_an_empty_portfolio_returns_a_body_not_an_error(self, as_user, mocker):
        mocker.patch.object(market_service, "holdings", return_value=[])
        body = as_user.get(URL).json()
        assert body["positions"] == []
        assert body["summary"]["statement"] == technicals.NO_MEASURABLE_TR

    def test_an_anonymous_caller_is_refused(self, client):
        assert client.get(URL).status_code == 401


class TestAgentEndpoint:
    """MCP yolu: kullanıcı doğrulanmış oturum zarfından gelip yola konuyor."""

    @pytest.fixture(autouse=True)
    def _stubs(self, mocker):
        mocker.patch.object(market_service, "latest_quotes", return_value={})
        mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0})
        mocker.patch.object(market_service, "candle_series", return_value=[])

    def test_the_user_comes_from_the_path(self, client, mocker):
        from unittest.mock import MagicMock

        from app.core.database import get_db

        holdings = mocker.patch.object(market_service, "holdings", return_value=[])
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            response = client.get(f"{URL}/user-42")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 200
        assert holdings.call_args.kwargs["user_id"] == "user-42"

    def test_both_endpoints_answer_from_the_same_helper(self, as_user, mocker):
        """Panelin ve sohbetin aynı portföy için farklı bir eğilim söylemesi
        mümkün olmamalı."""
        mocker.patch.object(
            market_service, "holdings",
            return_value=[{"symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
                           "quantity": 1, "price": 1.0}],
        )
        mocker.patch.object(ai_service, "holding_value", return_value=1.0)
        assert as_user.get(URL).json() == as_user.get(f"{URL}/user-1").json()
