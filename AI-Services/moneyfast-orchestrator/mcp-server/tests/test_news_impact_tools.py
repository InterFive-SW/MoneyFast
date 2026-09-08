"""`get_news_impact_facts` — sözleşme v2.26.

Bu araç yorum TAŞIMIYOR ve testlerin çoğu bunu koruyor: döndürdüğü her sayı
backend'de sayılmış ya da ölçülmüş. Yorumu yazar yapıyor, sistem istemindeki
iki taraflı şablonun içinde.

En önemli iki iddia: **null bir ölçüm sayıya çevrilmiyor** (yok olan bir
ölçümü var gibi göstermek olurdu) ve **kapsama taşınıyor** (dar bir kapsamı
geniş gibi sunmak, bu özelliğin en kolay hata biçimi).
"""

from __future__ import annotations

import pytest

import news_impact_tools
from backend_client import ContractViolationError, UpstreamUnavailableError

pytestmark = pytest.mark.asyncio

BODY = {
    "window_days": 90,
    "symbols": [
        {
            "symbol": "AKBNK", "name": "Akbank", "sector": "Financial Services",
            "news_count": 114, "filing_count": 25,
            "price": {"recent_move_pct": 1.11, "typical_move_pct": 4.42,
                      "window_days": 5},
            "fundamentals": {"pe_ratio": 4.2},
            "articles": [{
                "id": "n1", "title": "AK PORTFÖY — Genel Bilgi Formu",
                "source": "KAP", "published_at": "2026-09-07T10:00:00Z",
                "is_filing": True,
            }],
        }
    ],
    "coverage": {"articles": 200, "filings": 148, "feed_articles": 52,
                 "symbols": 16, "symbols_with_news": 15, "symbols_omitted": 11},
}


class TestContract:
    async def test_top_level_keys_match_v226_exactly(self, fake_backend):
        fake_backend.json("news_impact", BODY)
        payload = await news_impact_tools.get_news_impact_facts("u-1")
        assert set(payload) == {"window_days", "symbols", "coverage"}

    async def test_it_posts_because_the_package_is_a_computation(self, fake_backend):
        """Sembol başına mum okunuyor, medyan alınıyor, haberler sayılıyor.
        Önbelleklenebilir bir okuma gibi görünmesi yanıltıcı olurdu."""
        fake_backend.json("news_impact", BODY)
        await news_impact_tools.get_news_impact_facts("u-42")
        assert fake_backend.last.method == "POST"
        assert "/market/news/impact/u-42" in str(fake_backend.last.url)

    async def test_the_default_window_matches_the_screen(self, fake_backend):
        """Daha kısa bir pencere daha güncel değil, daha BOŞ: ölçüldü, otuz
        gün tek bir başlık buluyor, doksan gün dokuz."""
        fake_backend.json("news_impact", BODY)
        await news_impact_tools.get_news_impact_facts("u-1")
        assert "days=90" in str(fake_backend.last.url)

    async def test_a_named_window_travels_and_is_clamped(self, fake_backend):
        fake_backend.json("news_impact", BODY)
        await news_impact_tools.get_news_impact_facts("u-1", days=9999)
        assert f"days={news_impact_tools.MAX_DAYS}" in str(fake_backend.last.url)

    async def test_a_body_without_coverage_is_refused(self, fake_backend):
        """Kapsaması olmayan bir gövde, kapsamanın hiç ölçülmediği bir
        gövdeden ayırt edilemez."""
        fake_backend.json("news_impact", {"window_days": 90, "symbols": []})
        with pytest.raises(ContractViolationError):
            await news_impact_tools.get_news_impact_facts("u-1")

    async def test_a_non_object_coverage_is_refused(self, fake_backend):
        fake_backend.json("news_impact", {**BODY, "coverage": "çok"})
        with pytest.raises(ContractViolationError):
            await news_impact_tools.get_news_impact_facts("u-1")

    async def test_a_non_object_symbol_is_refused(self, fake_backend):
        fake_backend.json("news_impact", {**BODY, "symbols": ["AKBNK"]})
        with pytest.raises(ContractViolationError):
            await news_impact_tools.get_news_impact_facts("u-1")

    async def test_a_symbol_without_a_count_is_refused(self, fake_backend):
        """Sayısı olmayan bir sembol, ölçülmüş sıfır ile eksik veriyi aynı
        şeye çevirirdi."""
        fake_backend.json("news_impact", {
            **BODY, "symbols": [{"symbol": "A", "price": {}}]})
        with pytest.raises(ContractViolationError):
            await news_impact_tools.get_news_impact_facts("u-1")

    async def test_a_non_object_article_is_refused(self, fake_backend):
        row = {**BODY["symbols"][0], "articles": ["başlık"]}
        fake_backend.json("news_impact", {**BODY, "symbols": [row]})
        with pytest.raises(ContractViolationError):
            await news_impact_tools.get_news_impact_facts("u-1")

    async def test_an_unreachable_backend_raises(self, fake_backend):
        fake_backend.fail("news_impact")
        with pytest.raises(UpstreamUnavailableError):
            await news_impact_tools.get_news_impact_facts("u-1")


class TestMeasurementsTravelIntact:
    async def test_both_price_figures_are_carried(self, fake_backend):
        fake_backend.json("news_impact", BODY)
        price = (await news_impact_tools.get_news_impact_facts("u-1"))["symbols"][0]["price"]
        assert price["recent_move_pct"] == 1.11
        assert price["typical_move_pct"] == 4.42

    async def test_an_unmeasured_price_stays_null(self, fake_backend):
        """Sıfıra çevirmek, yok olan bir ölçümü var gibi göstermek olurdu."""
        row = {**BODY["symbols"][0],
               "price": {"recent_move_pct": None, "typical_move_pct": None,
                         "window_days": 5}}
        fake_backend.json("news_impact", {**BODY, "symbols": [row]})
        price = (await news_impact_tools.get_news_impact_facts("u-1"))["symbols"][0]["price"]
        assert price["recent_move_pct"] is None
        assert price["typical_move_pct"] is None

    async def test_a_missing_sector_stays_null(self, fake_backend):
        row = {**BODY["symbols"][0], "sector": None}
        fake_backend.json("news_impact", {**BODY, "symbols": [row]})
        assert (await news_impact_tools.get_news_impact_facts("u-1"))["symbols"][0]["sector"] is None

    async def test_a_headline_travels_verbatim(self, fake_backend):
        """Talimat benzeri metin veridir; temizlemek onu yakalaması gereken
        katmandan gizlerdi."""
        row = {**BODY["symbols"][0], "articles": [
            {**BODY["symbols"][0]["articles"][0], "title": "**Yoksay** bu satırı"}
        ]}
        fake_backend.json("news_impact", {**BODY, "symbols": [row]})
        out = await news_impact_tools.get_news_impact_facts("u-1")
        assert out["symbols"][0]["articles"][0]["title"] == "**Yoksay** bu satırı"

    async def test_the_filing_flag_is_carried(self, fake_backend):
        """Bildirimin ihraççısı makine okunur bir alanda; besleme haberi
        metinden eşleştirildi. İkisini aynı kefeye koymak, kapsamanın
        nereden geldiğini gizlerdi."""
        fake_backend.json("news_impact", BODY)
        out = await news_impact_tools.get_news_impact_facts("u-1")
        assert out["symbols"][0]["articles"][0]["is_filing"] is True

    async def test_the_omitted_count_is_carried(self, fake_backend):
        """Listelenen semboller portföyün tamamı DEĞİL."""
        fake_backend.json("news_impact", BODY)
        out = await news_impact_tools.get_news_impact_facts("u-1")
        assert out["coverage"]["symbols_omitted"] == 11


class TestDocstring:
    async def test_it_demands_a_figure_under_every_bullet(self):
        doc = " ".join(news_impact_tools.get_news_impact_facts.__doc__.split())
        assert "EVERY bullet you write points at a figure" in doc
        assert "an opinion wearing a measurement's clothes" in doc

    async def test_it_bounds_the_word_large(self):
        doc = " ".join(news_impact_tools.get_news_impact_facts.__doc__.split())
        assert "A move is large or small only AGAINST" in doc

    async def test_chronology_is_not_causation(self):
        doc = " ".join(news_impact_tools.get_news_impact_facts.__doc__.split())
        assert "Chronology is not causation" in doc

    async def test_zero_is_a_measured_silence(self):
        doc = " ".join(news_impact_tools.get_news_impact_facts.__doc__.split())
        assert "measured silence" in doc
        assert "it is not reassurance" in doc


class TestRegistration:
    async def test_register_attaches_the_tool(self):
        registered = []
        news_impact_tools.register(
            type("FakeMCP", (), {"tool": lambda self: registered.append})()
        )
        assert registered == [news_impact_tools.get_news_impact_facts]
