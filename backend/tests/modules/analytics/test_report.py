"""Detaylı rapor: sistemin ölçtüğü her şeyin tek belgede toplanması.

Bu dosyanın koruduğu üç şey:

CÜMLELER BİR KEZ KURULUR. Ekran, PDF ve sohbet aynı metni okuyor. Bu depoda
iki yüzeyin ayrışması defalarca ölçüldü -- `suitability` sayfa ile sohbette,
kova adları dağılım ile hedefte. Rapor üç yüzeye birden gittiği için risk üç
katı, ve bölüm cümleleri kendi kaynaklarından OLDUĞU GİBİ alınıyor.

BÖLÜM DÜŞMEZ. Verisi olmayan bölüm yokluğunu söyleyerek duruyor; sessizce
düşen bir bölüm, o ölçümün yapılmadığını değil raporun bozuk olduğunu
düşündürür.

TAZELİK RAPORUN İÇİNDE. Belgenin üretildiği an ile fiyatların ait olduğu an
farklı şeyler.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.analytics import report
from app.modules.banking import service as banking_service
from app.modules.investment import ai_service, market_service
from app.modules.investment import service as investment_service
from app.modules.risk import store as risk_store

NOW = datetime.now(timezone.utc)


def holding(symbol="THYAO", market="BIST", quantity=10.0, price=100.0, currency="TRY"):
    return {"symbol": symbol, "name": symbol, "market": market, "currency": currency,
            "quantity": quantity, "price": price, "avg_cost": price,
            "product_type": "stock", "market_timestamp": NOW, "opened_at": NOW}


@pytest.fixture
def wired(mocker):
    """Raporun okuduğu her servis, tek yerde."""
    mocker.patch.object(market_service, "holdings", return_value=[holding()])
    mocker.patch.object(
        market_service, "latest_quotes",
        return_value={"THYAO": {"price": 100.0, "market_timestamp": NOW,
                                "currency": "TRY"}},
    )
    mocker.patch.object(
        market_service, "freshness", return_value=(NOW - timedelta(minutes=18), 15, True, False)
    )
    mocker.patch.object(
        market_service, "account",
        return_value=SimpleNamespace(id="a1", cash_balance=1000.0,
                                     currency_code="TRY", account_number="TR-1"),
    )
    mocker.patch.object(ai_service, "fx_rates", return_value={"USD": 40.0})
    # Değerleme taklit ediliyor: bu dosyanın konusu raporun BÖLÜMLERİ, kur
    # çevriminin doğruluğu değil -- onun kendi testleri var.
    mocker.patch.object(
        ai_service, "holding_value",
        side_effect=lambda row, _rates: float(row["quantity"]) * float(row["price"]),
    )
    mocker.patch.object(investment_service, "allocation_targets", return_value={})
    mocker.patch.object(risk_store, "latest_profile", return_value=None)
    mocker.patch.object(risk_store, "snapshot_history", return_value=[])
    mocker.patch.object(
        banking_service, "cash_flow", return_value=banking_service._empty_cash_flow(90)
    )
    return MagicMock(spec=Session)


class TestShape:
    def test_every_section_is_present_in_order(self, wired):
        out = report.build_report(wired, "user-1")
        assert [s["key"] for s in out["sections"]] == [
            "overview", "allocation", "drift", "risk", "cash_flow", "positions",
        ]

    def test_every_section_carries_a_sentence(self, wired):
        for section in report.build_report(wired, "user-1")["sections"]:
            assert section["summary"], section["key"]
            assert section["title"]

    def test_freshness_is_measured_over_the_reported_instruments_only(
        self, wired, mocker
    ):
        """Kapalı bir borsanın son kapanışı, kullanıcının sahip OLMADIĞI bir
        enstrümanda duruyorsa raporu bayat göstermemeli.

        Ölçüldü: BIST fiyatları otuz saniyelikken rapor "462 dakika
        gecikmeli" diyordu, çünkü evrenin tamamı gönderiliyordu ve ABD
        borsası on sekiz saattir kapalıydı.
        """
        stale = NOW - timedelta(hours=18)
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={
                "THYAO": {"price": 100.0, "received_at": NOW, "currency": "TRY"},
                # Portföyde YOK, ve on sekiz saattir kapalı bir borsadan.
                "AAPL": {"price": 200.0, "received_at": stale, "currency": "USD"},
            },
        )
        spy = mocker.patch.object(
            market_service, "freshness", return_value=(NOW, 15, True, False)
        )
        report.build_report(wired, "user-1")
        assert set(spy.call_args.args[0]) == {"THYAO"}

    def test_an_empty_portfolio_falls_back_to_the_whole_universe(self, wired, mocker):
        """Hiç pozisyon yoksa süzgeç her şeyi eler; o durumda tazeliği hiç
        bildirmemektense evrenin tamamından okumak doğru."""
        mocker.patch.object(market_service, "holdings", return_value=[])
        spy = mocker.patch.object(
            market_service, "freshness", return_value=(NOW, 15, True, False)
        )
        report.build_report(wired, "user-1")
        assert spy.call_args.args[0]

    def test_a_closed_market_is_named_as_the_reason(self, wired, mocker):
        """Eski fiyat iki şey olabilir: piyasa kapalı (normal) ya da veri
        akışı durmuş (arıza). İkisi kullanıcıya farklı söylenmeli."""
        stale = NOW - timedelta(hours=18)
        mocker.patch.object(
            market_service, "holdings",
            return_value=[holding("AAPL", market="NASDAQ")],
        )
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={"AAPL": {"price": 200.0, "received_at": stale}},
        )
        mocker.patch.object(
            market_service, "freshness", return_value=(stale, 15, True, True)
        )
        mocker.patch.object(market_service, "open_markets", return_value={"BIST"})
        out = report.build_report(wired, "user-1")
        assert out["stale_reason"] == "MARKET_CLOSED"

    def test_a_stale_price_on_an_OPEN_market_is_not_called_closed(
        self, wired, mocker
    ):
        """Açık bir piyasada eskiyen fiyat bir ARIZADIR; ona "piyasa kapalı"
        demek arızayı normal diye göstermek olurdu."""
        stale = NOW - timedelta(hours=18)
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={"THYAO": {"price": 100.0, "received_at": stale}},
        )
        mocker.patch.object(
            market_service, "freshness", return_value=(stale, 15, True, True)
        )
        mocker.patch.object(market_service, "open_markets", return_value={"BIST"})
        assert report.build_report(wired, "user-1")["stale_reason"] is None

    def test_unknown_session_state_asserts_nothing(self, wired, mocker):
        """Ingestor durduğunda hem fiyatlar hem seans kaydı eskiyor."""
        stale = NOW - timedelta(hours=18)
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={"THYAO": {"price": 100.0, "received_at": stale}},
        )
        mocker.patch.object(
            market_service, "freshness", return_value=(stale, 15, True, True)
        )
        mocker.patch.object(market_service, "open_markets", return_value=None)
        assert report.build_report(wired, "user-1")["stale_reason"] is None

    def test_a_quote_without_a_timestamp_is_skipped(self, wired, mocker):
        """Ne zaman görüldüğü bilinmeyen bir kotasyon, eskiliğin sebebi
        hakkında bir şey söylemiyor."""
        stale = NOW - timedelta(hours=18)
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={"THYAO": {"price": 100.0}},
        )
        mocker.patch.object(
            market_service, "freshness", return_value=(stale, 15, True, True)
        )
        mocker.patch.object(market_service, "open_markets", return_value={"FX"})
        assert report.build_report(wired, "user-1")["stale_reason"] is None

    def test_a_quote_whose_instrument_has_no_market_is_ignored(self, wired, mocker):
        """Piyasası bilinmeyen bir enstrüman, fiyatların neden eski olduğu
        hakkında bir şey söylemez. `_stale_reason` doğrudan çağrılıyor: rapor
        yolu kotaları zaten tutulanlara süzüyor."""
        mocker.patch.object(market_service, "open_markets", return_value={"FX"})
        stale = NOW - timedelta(hours=18)
        reason = report._stale_reason(
            wired,
            [({"symbol": "GIZLI", "market": None}, 1.0)],
            {"GIZLI": {"received_at": stale}},
        )
        assert reason is None

    def test_a_naive_timestamp_is_read_as_utc(self, wired, mocker):
        stale = (NOW - timedelta(hours=18)).replace(tzinfo=None)
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={"THYAO": {"price": 100.0, "received_at": stale}},
        )
        mocker.patch.object(
            market_service, "freshness",
            return_value=(NOW - timedelta(hours=18), 15, True, True),
        )
        mocker.patch.object(market_service, "open_markets", return_value={"FX"})
        assert report.build_report(wired, "user-1")["stale_reason"] == "MARKET_CLOSED"

    def test_a_fresh_report_has_no_reason_to_give(self, wired, mocker):
        spy = mocker.patch.object(market_service, "open_markets", return_value=set())
        out = report.build_report(wired, "user-1")
        assert out["stale_reason"] is None
        # Taze bir raporda seans bilgisi hiç SORULMUYOR.
        assert not spy.called

    def test_the_price_time_is_separate_from_the_build_time(self, wired):
        """Belgenin üretildiği an ile fiyatların ait olduğu an farklı şeyler,
        ve aradaki fark bu ürünün açıklamak zorunda olduğu gecikme."""
        out = report.build_report(wired, "user-1")
        assert out["as_of"] != out["generated_at"]
        # `delay_minutes` BESLEMENİN gecikmesi, gözlemin yaşı değil: ikisi bir
        # dönem toplanıyordu ve kapalı bir borsanın son kapanışı "1095 dakika
        # gecikmeli" diye raporlanıyordu.
        assert out["delay_minutes"] == 15 and out["is_delayed"] is True


class TestOverview:
    def test_cash_and_positions_are_both_counted(self, wired):
        out = report.build_report(wired, "user-1")
        overview = out["sections"][0]
        assert "2.000,00 TRY" in overview["summary"]

    def test_an_unpriced_holding_is_named_rather_than_silently_missing(
        self, wired, mocker
    ):
        """Toplamın sessizce eksik olması, raporun en kolay yanlış okunan
        yeri olurdu."""
        mocker.patch.object(
            market_service, "holdings",
            return_value=[holding(), holding("XXXX")],
        )
        mocker.patch.object(
            ai_service, "holding_value",
            side_effect=lambda row, _rates: None if row["symbol"] == "XXXX" else 1000.0,
        )
        lines = report.build_report(wired, "user-1")["sections"][0]["lines"]
        assert any("XXXX" in line for line in lines)


class TestEmptyPortfolio:
    def test_allocation_says_there_is_nothing_to_split(self, wired, mocker):
        """Boş bir portföyde her kovaya %0 yazmak, dağılımı olmayan bir
        portföye dağılımı varmış gibi davranmak olurdu."""
        mocker.patch.object(market_service, "holdings", return_value=[])
        mocker.patch.object(
            market_service, "account",
            return_value=SimpleNamespace(id="a1", cash_balance=0.0,
                                         currency_code="TRY", account_number="TR-1"),
        )
        out = report.build_report(wired, "user-1")
        allocation_section = next(s for s in out["sections"] if s["key"] == "allocation")
        assert "hesaplanacak bir varlık bulunamadı" in allocation_section["summary"]

    def test_positions_says_so_rather_than_showing_an_empty_table(self, wired, mocker):
        mocker.patch.object(market_service, "holdings", return_value=[])
        positions = next(
            s for s in report.build_report(wired, "user-1")["sections"]
            if s["key"] == "positions"
        )
        assert "bulunamadı" in positions["summary"]
        assert positions["rows"] == []


class TestSentencesComeFromTheirSource:
    def test_the_drift_sentence_is_not_rewritten_by_the_report(self, wired, mocker):
        """Raporun kendi cümlesini kurması, aynı sapmanın ekranda ve raporda
        farklı anlatılması demekti."""
        mocker.patch.object(
            investment_service, "allocation_targets",
            return_value={"bist_equity": 50.0, "cash": 50.0},
        )
        out = report.build_report(wired, "user-1")
        drift = next(s for s in out["sections"] if s["key"] == "drift")
        from app.modules.investment import allocation

        expected = allocation.drift(
            allocation.current_amounts([(holding(), 1000.0)], 1000.0),
            {"bist_equity": 50.0, "cash": 50.0},
        )["statement"]
        assert drift["summary"] == expected

    def test_the_suitability_sentence_is_the_risk_modules_own(self, wired):
        out = report.build_report(wired, "user-1")
        risk = next(s for s in out["sections"] if s["key"] == "risk")
        from app.modules.risk import profile

        assert risk["summary"] == profile.suitability(None, None)["statement"]


class TestAbsence:
    def test_a_user_without_banking_records_still_gets_the_section(self, wired):
        """Ölçüldü: 23 kullanıcının 3'ünde bankacılık hareketi var."""
        cash_flow = next(
            s for s in report.build_report(wired, "user-1")["sections"]
            if s["key"] == "cash_flow"
        )
        assert "bulunmuyor" in cash_flow["summary"]

    def test_an_unmeasured_risk_score_is_said_rather_than_written_as_a_number(
        self, wired
    ):
        """Puan YOK ile puan DÜŞÜK farklı şeyler."""
        risk = next(
            s for s in report.build_report(wired, "user-1")["sections"]
            if s["key"] == "risk"
        )
        assert any("henüz hesaplanmadı" in line for line in risk["lines"])

    def test_an_anonymous_caller_gets_no_personal_sections_but_all_the_headings(
        self, wired
    ):
        out = report.build_report(wired, None)
        assert [s["key"] for s in out["sections"]] == [
            "overview", "allocation", "drift", "risk", "cash_flow", "positions",
        ]


class TestRiskScore:
    def test_a_recorded_snapshot_is_read_rather_than_recomputed(self, wired, mocker):
        """Yeniden hesaplamak, aynı gün raporun ve Analiz sayfasının iki
        farklı puan göstermesine açık olurdu."""
        mocker.patch.object(
            risk_store, "snapshot_history",
            return_value=[SimpleNamespace(score=83.4, level="Düşük")],
        )
        risk = next(
            s for s in report.build_report(wired, "user-1")["sections"]
            if s["key"] == "risk"
        )
        assert any("83.4 / 100" in line for line in risk["lines"])
        assert any("100 en sakin" in line for line in risk["lines"])


class TestCashFlowSection:
    def test_the_coverage_caveat_travels_with_the_figures(self, wired, mocker):
        """Backend'de üretilen cümle; ödeme sayısı ay sayısından azken aylık
        ortalama kişinin kazandığının altında kalıyor."""
        mocker.patch.object(banking_service, "cash_flow", return_value={
            "has_data": True, "period_days": 90, "months_observed": 3.0,
            "currency_code": "TRY", "income_total": 124000.0, "income_events": 2,
            "expense_total": 38350.0, "net_total": 85650.0,
            "monthly_income": 41333.33, "monthly_expense": 12783.33,
            "monthly_net": 28550.0, "categories": [],
            "coverage_note": "Son 90 günde 2 gelir ödemesi görüldü.",
            "first_transaction_at": None, "last_transaction_at": None,
        })
        section = next(
            s for s in report.build_report(wired, "user-1")["sections"]
            if s["key"] == "cash_flow"
        )
        assert "Son 90 günde 2 gelir ödemesi görüldü." in section["lines"]

    def test_a_full_window_carries_no_caveat_line(self, wired, mocker):
        """Ödeme sayısı ay sayısını karşılıyorsa uyarı YOK; her rapora bir
        uyarı koymak, uyarının anlamını yok ederdi."""
        mocker.patch.object(banking_service, "cash_flow", return_value={
            "has_data": True, "period_days": 90, "months_observed": 3.0,
            "currency_code": "TRY", "income_total": 124000.0, "income_events": 4,
            "expense_total": 38350.0, "net_total": 85650.0,
            "monthly_income": 41333.33, "monthly_expense": 12783.33,
            "monthly_net": 28550.0,
            "categories": [{"category": "Kira", "amount": 28000.0,
                            "monthly_amount": 9333.33, "share_percent": 73.0}],
            "coverage_note": None,
            "first_transaction_at": None, "last_transaction_at": None,
        })
        section = next(
            s for s in report.build_report(wired, "user-1")["sections"]
            if s["key"] == "cash_flow"
        )
        assert len(section["lines"]) == 4
        assert any("Kira" in line for line in section["lines"])


class TestFormatting:
    @pytest.mark.parametrize(
        "amount,expected",
        [(1234.5, "1.234,50 TRY"), (0.0, "0,00 TRY"), (None, "veri yok"),
         (1_000_000.0, "1.000.000,00 TRY")],
    )
    def test_money_uses_turkish_separators(self, amount, expected):
        """Biçimi her bölümde yeniden yazmak, aynı belgede iki farklı sayı
        görünümü demekti."""
        assert report._money(amount) == expected

    def test_a_missing_percentage_says_so_rather_than_printing_zero(self):
        assert report._percent(None) == "veri yok"
        assert report._percent(12.5) == "%12.5"
