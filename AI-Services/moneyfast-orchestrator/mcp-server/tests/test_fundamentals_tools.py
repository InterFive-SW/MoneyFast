"""`get_company_fundamentals` — sözleşme v2.14.

Bu araç yeni veri toplamıyor: otuz beş alan zaten toplanıyordu ve `GET
/market/fundamentals` hepsini veriyordu, ama yalnızca hisse detay sayfası
okuyordu. Ajanın bir şirket hakkında görebildiği her şey fiyat, değişim,
hacim ve dört orandan ibaretti.

Bu dosyanın koruduğu en önemli şey ANLIK GÖRÜNTÜ / SERİ ayrımı. Sistem alan
başına tek bir güncel değer saklıyor ve geçmiş tutmuyor; dolayısıyla "son
çeyrek kârı arttı" gibi bir cümle kurulamaz -- kıyaslanacak ikinci bir dönem
yok. Sözleşme bunu açıkça söylüyor, çünkü söylemezse model iki dönem varmış
gibi yazar.

İkincisi: NULL SIFIR DEĞİL. Ölçüldü -- 1.011 enstrümanın 979'unda kâr marjı,
892'sinde borç/özkaynak, yalnızca 484'ünde analist görüşü var.
"""

from __future__ import annotations

import httpx
import pytest

import fundamentals_tools as ft
from backend_client import (
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)

TOOL_KEYS = {"instruments", "not_found", "missing_data"}


def body(symbol="AKBNK", **overrides):
    """Backend'in sağlıklı yanıtı."""
    payload = {
        "symbol": symbol,
        "name": "Akbank T.A.Ş.",
        "currency": "TRY",
        "updated_at": "2026-09-02T10:00:00Z",
        "sector": "Financial Services",
        "industry": "Banks - Regional",
        "pe_ratio": 6.4, "pb_ratio": 1.2, "forward_pe": 5.8,
        "market_cap": 384_000_000_000, "enterprise_value": None,
        "total_revenue": 210_000_000_000, "revenue_growth": 0.34,
        "gross_margin": None, "operating_margin": 0.41,
        "ebitda_margin": None, "profit_margin": 0.284,
        "return_on_equity": 0.31, "return_on_assets": 0.03,
        "debt_to_equity": None, "current_ratio": None,
        "total_debt": 90_000_000_000, "total_cash": 120_000_000_000,
        "free_cash_flow": None, "operating_cash_flow": 44_000_000_000,
        "trailing_eps": 11.2, "forward_eps": 12.9, "earnings_growth": 0.22,
        "dividend_yield": 0.031, "dividend_rate": 2.3, "payout_ratio": 0.2,
        "ex_dividend_date": "2026-04-02",
        "beta": 1.1, "week52_high": 84.0, "week52_low": 48.5,
        "earnings_date": "2026-11-04",
        "recommendation_key": "buy", "analyst_count": 17,
        "target_mean_price": 92.4,
    }
    payload.update(overrides)
    return payload


class TestContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v214_exactly(self, fake_backend):
        fake_backend.json("fundamentals", body())
        out = await ft.get_company_fundamentals(["AKBNK"])
        assert set(out) == TOOL_KEYS

    @pytest.mark.asyncio
    async def test_every_documented_field_travels(self, fake_backend):
        fake_backend.json("fundamentals", body())
        out = await ft.get_company_fundamentals(["AKBNK"])
        assert set(out["instruments"][0]["fundamentals"]) == set(ft.FIELDS)
        assert set(out["instruments"][0]) == {"symbol", "name", "currency", "fundamentals"}

    @pytest.mark.asyncio
    async def test_the_fetch_time_does_not_travel(self, fake_backend):
        """`updated_at` ajana verilecek bir tarih DEĞİL: veriyi ne zaman
        çektiğimizi söylüyor ve modelin onu raporlama dönemi sanması, bu
        aracın yaratabileceği tek ciddi yanlış."""
        fake_backend.json("fundamentals", body())
        out = await ft.get_company_fundamentals(["AKBNK"])
        assert "updated_at" not in out["instruments"][0]
        assert "updated_at" not in out["instruments"][0]["fundamentals"]

    @pytest.mark.asyncio
    async def test_the_symbol_is_uppercased_and_sent(self, fake_backend):
        fake_backend.json("fundamentals", body())
        await ft.get_company_fundamentals(["akbnk"])
        assert "symbol=AKBNK" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_several_symbols_are_fetched_one_by_one(self, fake_backend):
        """Uç nokta tek sembol alıyor. Toplu bir uç eklemek yerine sembol
        başına bir istek: bu faz var olan veriyi erişilebilir kılıyor,
        backend'e yeni yüzey açmıyor."""
        fake_backend.json("fundamentals", body())
        out = await ft.get_company_fundamentals(["AKBNK", "THYAO", "ASELS"])
        assert len(out["instruments"]) == 3
        assert fake_backend.attempts == 3

    @pytest.mark.asyncio
    async def test_a_missing_symbol_field_is_a_contract_violation(self, fake_backend):
        fake_backend.json("fundamentals", {"name": "Bir Şey"})
        with pytest.raises(ContractViolationError):
            await ft.get_company_fundamentals(["AKBNK"])

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises_rather_than_recalling(
        self, fake_backend, no_sleep
    ):
        """Gerçek bir şirket için hatırlanan bir marj, en inandırıcı yanlış
        cevap türüdür."""
        fake_backend.fail("fundamentals")
        with pytest.raises(UpstreamUnavailableError):
            await ft.get_company_fundamentals(["AKBNK"])

    @pytest.mark.asyncio
    async def test_it_carries_no_market_data_fields(self, fake_backend):
        """`as_of`/`source`/`is_delayed` bu aracın alanları değil: bu bir
        fiyat okuması değil, saklanan bir kayıt."""
        from conftest import assert_no_market_data_fields

        fake_backend.json("fundamentals", body())
        assert_no_market_data_fields(await ft.get_company_fundamentals(["AKBNK"]))


class TestInput:
    @pytest.mark.asyncio
    async def test_no_symbol_is_refused(self, fake_backend):
        with pytest.raises(InvalidInputError):
            await ft.get_company_fundamentals([])

    @pytest.mark.asyncio
    async def test_blank_symbols_are_refused(self, fake_backend):
        with pytest.raises(InvalidInputError):
            await ft.get_company_fundamentals(["", "   "])

    @pytest.mark.asyncio
    async def test_none_is_refused(self, fake_backend):
        with pytest.raises(InvalidInputError):
            await ft.get_company_fundamentals(None)

    @pytest.mark.asyncio
    async def test_too_many_symbols_are_refused_not_truncated(self, fake_backend):
        """Sessizce düşen bir sembol, bakılmış gibi cevaplanır ve kullanıcı
        hangisinin düştüğünü bilemez."""
        fake_backend.json("fundamentals", body())
        with pytest.raises(InvalidInputError):
            await ft.get_company_fundamentals(["A", "B", "C", "D", "E", "F"])
        assert fake_backend.attempts == 0

    @pytest.mark.asyncio
    async def test_the_cap_itself_is_allowed(self, fake_backend):
        fake_backend.json("fundamentals", body())
        out = await ft.get_company_fundamentals(["A", "B", "C", "D", "E"])
        assert len(out["instruments"]) == ft.MAX_SYMBOLS


class TestAbsence:
    @pytest.mark.asyncio
    async def test_a_null_field_stays_null(self, fake_backend):
        """Ölçüldü: 1.011 enstrümanın 892'sinde borç/özkaynak var. Sıfıra
        çevirmek, borcu olmayan bir şirket iddiası olurdu."""
        fake_backend.json("fundamentals", body())
        figures = (await ft.get_company_fundamentals(["AKBNK"]))["instruments"][0]["fundamentals"]
        assert figures["debt_to_equity"] is None
        assert figures["gross_margin"] is None
        assert figures["profit_margin"] == 0.284

    @pytest.mark.asyncio
    async def test_a_field_the_backend_omits_is_null_not_absent(self, fake_backend):
        """Anahtarı düşürmek, `fundamentals["profit_margin"]` okuyan bir
        tüketiciye KeyError verirdi."""
        payload = body()
        del payload["profit_margin"]
        fake_backend.json("fundamentals", payload)
        figures = (await ft.get_company_fundamentals(["AKBNK"]))["instruments"][0]["fundamentals"]
        assert figures["profit_margin"] is None
        assert set(figures) == set(ft.FIELDS)

    @pytest.mark.asyncio
    async def test_an_unknown_symbol_is_reported_not_invented(self, fake_backend):
        """Backend bilinmeyen sembol için yalnızca `{"symbol": ...}` dönüyor,
        hata değil."""
        fake_backend.json("fundamentals", {"symbol": "YOKBU"})
        out = await ft.get_company_fundamentals(["YOKBU"])
        assert out["not_found"] == ["YOKBU"]
        assert out["instruments"] == []

    @pytest.mark.asyncio
    async def test_an_instrument_without_figures_is_separate_from_a_missing_one(
        self, fake_backend
    ):
        """Biri "böyle bir şirket yok", diğeri "şirket var, verisi henüz
        çekilmemiş" -- ve ajanın söyleyeceği cümle ikisinde farklı."""
        blank = {"symbol": "YENI", "name": "Yeni A.Ş.", "currency": "TRY"}
        fake_backend.json("fundamentals", blank)
        out = await ft.get_company_fundamentals(["YENI"])
        assert out["missing_data"] == ["YENI"]
        assert out["not_found"] == []
        assert out["instruments"] == []

    @pytest.mark.asyncio
    async def test_a_name_the_backend_omits_falls_back_to_the_request(self, fake_backend):
        payload = body()
        del payload["name"]
        fake_backend.json("fundamentals", payload)
        out = await ft.get_company_fundamentals(["AKBNK"])
        # `name` yoksa kayıt bulunamamış sayılıyor: backend adı olan her
        # enstrüman için döndürüyor, yokluğu "böyle bir şey yok" demek.
        assert out["not_found"] == ["AKBNK"]

    @pytest.mark.asyncio
    async def test_a_currency_the_backend_omits_defaults_to_lira(self, fake_backend):
        payload = body()
        del payload["currency"]
        fake_backend.json("fundamentals", payload)
        out = await ft.get_company_fundamentals(["AKBNK"])
        assert out["instruments"][0]["currency"] == "TRY"


class TestAnalystConsensus:
    @pytest.mark.asyncio
    async def test_the_three_values_travel_together(self, fake_backend):
        """Analist sayısı olmayan bir hedef fiyat, yazarı olmayan bir sayı."""
        fake_backend.json("fundamentals", body())
        figures = (await ft.get_company_fundamentals(["AKBNK"]))["instruments"][0]["fundamentals"]
        assert figures["recommendation_key"] == "buy"
        assert figures["analyst_count"] == 17
        assert figures["target_mean_price"] == 92.4

    @pytest.mark.asyncio
    async def test_no_analyst_view_is_null_across_all_three(self, fake_backend):
        """Evrenin yarısında analist görüşü YOK: 1.011'de 484."""
        fake_backend.json("fundamentals", body(
            recommendation_key=None, analyst_count=None, target_mean_price=None,
        ))
        figures = (await ft.get_company_fundamentals(["AKBNK"]))["instruments"][0]["fundamentals"]
        assert figures["recommendation_key"] is None
        assert figures["analyst_count"] is None
        assert figures["target_mean_price"] is None


class TestContractWording:
    """Sözleşme metni, ölçülen yanlışları AÇIKÇA yasaklamalı.

    Prompt tavsiyedir ve bu depo bunu birkaç kez öğrendi; ama araç
    açıklaması modelin gördüğü tek sözleşme ve orada yazmayan bir kural
    hiç yok sayılır.
    """

    def test_the_snapshot_limit_is_stated(self):
        doc = ft.get_company_fundamentals.__doc__
        assert "SNAPSHOT, NOT A SERIES" in doc
        assert "son çeyrek" in doc

    def test_growth_ratios_may_not_be_given_a_period(self):
        """Ölçüldü: model kâr büyümesini "gelecek yıl için tahmin ediliyor"
        diye anlattı -- verinin yapmadığı bir iddia."""
        doc = ft.get_company_fundamentals.__doc__
        assert "the period they span is NOT stored" in doc
        assert "gelecek yıl" in doc

    def test_only_the_forward_fields_may_be_called_estimates(self):
        doc = ft.get_company_fundamentals.__doc__
        assert "ONLY two fields you may describe that way" in doc

    def test_null_is_not_zero(self):
        doc = ft.get_company_fundamentals.__doc__
        assert "NOT zero" in doc
        assert "never print 0" in doc

    def test_field_keys_may_not_be_spoken(self):
        doc = ft.get_company_fundamentals.__doc__
        assert "kâr marjı" in doc and "profit_margin" in doc

    def test_the_analyst_target_is_theirs_not_ours(self):
        """Bu ürün fiyat hedefi üretmiyor; başkasının ürettiğini raporlamak
        farklı bir şey ve sayının yazarı olmalı."""
        doc = ft.get_company_fundamentals.__doc__
        assert "never a price target this product produces" in doc
        assert "without the count is a number with no author" in doc


class TestRegistration:
    def test_the_first_tool_is_attached_first(self):
        registered = []
        ft.register(type("FakeMCP", (), {"tool": lambda self: registered.append})())
        assert registered[0] is ft.get_company_fundamentals


# ==========================================================================
# get_quarterly_financials — sözleşme v2.15
# ==========================================================================
"""Çeyreklik seri: `get_company_fundamentals`'ın sahip OLMADIĞI şey.

O araç alan başına tek güncel değer saklıyor, geçmiş yok. Bu araç her çeyreği
ayrı saklıyor ve bir şirketin adı konmuş bir çeyrekte ne kazandığını
söyleyebilen tek yol bu.

Bu bölümün koruduğu asıl şey BİTİŞİKLİK. Sağlayıcı çeyrek atlıyor: evrenden
rastgele 40 BIST hissesi ölçüldüğünde 3'ünde 2025Q3 gelir tablosunda hiç
yoktu. "Son iki satırı karşılaştır" diyen bir cevap o hisselerde 2025Q2 ile
2025Q4'ü yan yana koyar ve bunu söylemez.
"""

QUARTERLY_KEYS = {
    "symbol", "name", "currency", "periods",
    "previous_is_adjacent", "year_ago_available",
}
PERIOD_KEYS = {
    "period_end", "label",
    "total_revenue", "net_income", "pretax_income", "operating_expense",
}


def period(label="2026Q2", end="2026-06-30", net_income=15_198_000_000, **overrides):
    row = {
        "period_end": end, "label": label,
        "total_revenue": 71_000_000_000, "net_income": net_income,
        "pretax_income": 19_000_000_000, "operating_expense": 30_000_000_000,
    }
    row.update(overrides)
    return row


def quarterly_body(**overrides):
    payload = {
        "symbol": "AKBNK", "name": "Akbank T.A.Ş.", "currency": "TRY",
        "periods": [period(), period("2026Q1", "2026-03-31", 14_100_000_000)],
        "previous_is_adjacent": True,
        "year_ago_available": True,
    }
    payload.update(overrides)
    return payload


class TestQuarterlyContract:
    @pytest.mark.asyncio
    async def test_keys_match_the_contract_exactly(self, fake_backend):
        fake_backend.json("quarterly", quarterly_body())
        out = await ft.get_quarterly_financials("AKBNK")
        assert set(out) == QUARTERLY_KEYS
        assert set(out["periods"][0]) == PERIOD_KEYS

    @pytest.mark.asyncio
    async def test_the_symbol_is_uppercased(self, fake_backend):
        fake_backend.json("quarterly", quarterly_body())
        await ft.get_quarterly_financials("akbnk")
        assert "symbol=AKBNK" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_periods_come_back_newest_first_with_their_labels(self, fake_backend):
        fake_backend.json("quarterly", quarterly_body())
        out = await ft.get_quarterly_financials("AKBNK")
        assert [p["label"] for p in out["periods"]] == ["2026Q2", "2026Q1"]

    @pytest.mark.asyncio
    async def test_a_period_without_a_label_is_a_contract_violation(self, fake_backend):
        """Dönemi adlandırmadan rakam vermek, serinin deliklerini okunamaz
        kılar; etiket zorunlu."""
        bad = period()
        del bad["label"]
        fake_backend.json("quarterly", quarterly_body(periods=[bad]))
        with pytest.raises(ContractViolationError):
            await ft.get_quarterly_financials("AKBNK")

    @pytest.mark.asyncio
    async def test_a_non_object_period_is_refused(self, fake_backend):
        fake_backend.json("quarterly", quarterly_body(periods=["2026Q2"]))
        with pytest.raises(ContractViolationError):
            await ft.get_quarterly_financials("AKBNK")

    @pytest.mark.asyncio
    async def test_a_missing_periods_block_is_a_contract_violation(self, fake_backend):
        fake_backend.json("quarterly", {"symbol": "AKBNK"})
        with pytest.raises(ContractViolationError):
            await ft.get_quarterly_financials("AKBNK")

    @pytest.mark.asyncio
    async def test_no_symbol_is_refused(self, fake_backend):
        with pytest.raises(InvalidInputError):
            await ft.get_quarterly_financials("   ")

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises(self, fake_backend, no_sleep):
        fake_backend.fail("quarterly")
        with pytest.raises(UpstreamUnavailableError):
            await ft.get_quarterly_financials("AKBNK")


class TestQuarterlyGaps:
    @pytest.mark.asyncio
    async def test_the_adjacency_flag_is_carried_not_recomputed(self, fake_backend):
        """Kural sunucuda, tek yerde. Burada yeniden hesaplamak, iki yerin
        ayrışabileceği bir yer açardı."""
        fake_backend.json("quarterly", quarterly_body(previous_is_adjacent=False))
        out = await ft.get_quarterly_financials("AKBNK")
        assert out["previous_is_adjacent"] is False

    @pytest.mark.asyncio
    async def test_a_missing_flag_defaults_to_not_adjacent(self, fake_backend):
        """Varsayılan GÜVENLİ tarafta: bayrak gelmezse karşılaştırma
        yapılmıyor. Tersi, boşluk üzerinden bir kıyas üretirdi."""
        payload = quarterly_body()
        del payload["previous_is_adjacent"]
        del payload["year_ago_available"]
        fake_backend.json("quarterly", payload)
        out = await ft.get_quarterly_financials("AKBNK")
        assert out["previous_is_adjacent"] is False
        assert out["year_ago_available"] is False

    @pytest.mark.asyncio
    async def test_an_instrument_with_no_quarters_is_an_empty_series(self, fake_backend):
        """Ölçüldü: 40 hissenin 6'sında hiç çeyreklik veri yok. Bu bir
        kesinti değil ve sıfır değil."""
        fake_backend.json("quarterly", quarterly_body(
            periods=[], previous_is_adjacent=False, year_ago_available=False,
        ))
        out = await ft.get_quarterly_financials("YENI")
        assert out["periods"] == []

    @pytest.mark.asyncio
    async def test_a_null_figure_stays_null(self, fake_backend):
        """34 hissenin 16'sında serinin bir yerinde delik var."""
        fake_backend.json("quarterly", quarterly_body(
            periods=[period(net_income=None)],
        ))
        out = await ft.get_quarterly_financials("AKBNK")
        assert out["periods"][0]["net_income"] is None

    @pytest.mark.asyncio
    async def test_a_field_the_backend_omits_is_null_not_absent(self, fake_backend):
        row = period()
        del row["pretax_income"]
        fake_backend.json("quarterly", quarterly_body(periods=[row]))
        out = await ft.get_quarterly_financials("AKBNK")
        assert out["periods"][0]["pretax_income"] is None
        assert set(out["periods"][0]) == PERIOD_KEYS


class TestQuarterlyContractWording:
    def test_the_period_must_be_named(self):
        doc = ft.get_quarterly_financials.__doc__
        assert "NAME THE PERIOD in every figure" in doc

    def test_comparison_is_gated_on_adjacency(self):
        doc = ft.get_quarterly_financials.__doc__
        assert "ONLY when `previous_is_adjacent` is true" in doc
        assert "a comparison across a gap reads as quarter-over-quarter" in doc

    def test_an_empty_series_is_not_an_outage(self):
        doc = ft.get_quarterly_financials.__doc__
        assert "not an outage and not a zero" in doc

    def test_a_comparison_is_written_oldest_first(self):
        """Ölçülen kusur: cümle düşüş diyor, ok yükseliş gösteriyor.

        Seri yeniden eskiye geliyor -- "son çeyrek" sorusunun cevabı ilk satır
        olmalı -- ve model onu geldiği sırayla oka diziyordu.
        """
        doc = ft.get_quarterly_financials.__doc__
        assert "CHRONOLOGICAL order" in doc
        assert "older quarter first" in doc
        assert "%-20,7 azalma" in doc

    def test_past_results_may_not_be_extrapolated(self):
        doc = ft.get_quarterly_financials.__doc__
        assert "Do not extrapolate the next quarter" in doc


class TestQuarterlyRegistration:
    def test_both_tools_are_attached(self):
        registered = []
        ft.register(type("FakeMCP", (), {"tool": lambda self: registered.append})())
        assert registered == [ft.get_company_fundamentals, ft.get_quarterly_financials]
