"""Piyasa ilgisi süzgeci.

Korunan asıl iddia kullanıcının kendi cümlesi: *"that finance includes
politic news. so that if someone starts a war or something include them here
cuz it makes the economics move."* Bir savaş ekonomik bir olaydır ve bu
süzgeç onu ELEMEZ.
"""

from __future__ import annotations

import pytest

from ingestor.sources import relevance


def item(title, summary=""):
    return {"title": title, "summary": summary}


class TestPoliticsStays:
    @pytest.mark.parametrize("headline", [
        "US launches strikes on Iranian oil infrastructure",
        "EU agrees new sanctions package on Russian crude",
        "Turkey election result shifts central bank outlook",
        "Coup attempt halts shipping through the strait",
        "White House announces 25% tariff on imported steel",
        "Rusya'ya yeni yaptırım paketi açıklandı",
    ])
    def test_geopolitics_is_market_news(self, headline):
        """Fiyat kanalı: yaptırım, tarife, boğaz kapanması. Bunları "siyaset"
        diye elemek, portföyü gerçekten hareket ettiren haberi tam da
        hareket ettirdiği anda atmak olurdu."""
        assert relevance.is_market_relevant(item(headline))


class TestOffTopicGoes:
    @pytest.mark.parametrize("headline", [
        "Premier League club signs striker for record fee",
        "Fenerbahçe derbi öncesi kadrosunu açıkladı",
        "Celebrity wedding draws red carpet crowd",
        "Your horoscope for Friday",
        "Easy recipe: 20-minute pasta",
    ])
    def test_sport_and_gossip_are_dropped(self, headline):
        assert not relevance.is_market_relevant(item(headline))


class TestOrderMatters:
    def test_a_market_term_rescues_a_sport_headline(self):
        """ÖNCE piyasa terimi, SONRA kara liste. Ters sırada bu haber
        elenirdi -- bir satın alma haberi olduğu hâlde, içinde "Premier
        League" geçtiği için."""
        assert relevance.is_market_relevant(
            item("Premier League broadcast rights deal worth £6.7bn",
                 "The acquisition lifts the group's revenue outlook."))

    def test_a_market_term_in_the_summary_counts_too(self):
        assert relevance.is_market_relevant(
            item("Olympic host city named", "Bond yields moved on the news."))


class TestUnknownStays:
    def test_an_unclassifiable_headline_is_kept(self):
        """Kara liste: bilinmeyen konuyu atmak, izin listesine dönmek olurdu
        ve kaçırılan bir haber görünmez, araya karışan bir futbol haberi
        görünür."""
        assert relevance.is_market_relevant(item("Ministry publishes new regulation"))

    def test_an_empty_item_is_kept(self):
        assert relevance.is_market_relevant(item("", ""))

    def test_missing_fields_do_not_raise(self):
        assert relevance.is_market_relevant({})

    def test_null_fields_do_not_raise(self):
        assert relevance.is_market_relevant({"title": None, "summary": None})


class TestListDiscipline:
    @pytest.mark.parametrize("word", ["transfer", "gol", "gold"])
    def test_ambiguous_words_are_not_in_the_denylist(self, word):
        """`transfer` finansta da geçiyor (para transferi), `gol` bir sayı
        birimi ve `gold` içinde de var. Şüpheli sözcük listeden ÇIKARILDI --
        yanlış eleme, elemesizlikten kötü."""
        assert word not in relevance._OFF_TOPIC

    def test_the_denylist_is_lowercase(self):
        """Karşılaştırma küçük harfte yapılıyor; büyük harfli bir girdi hiç
        eşleşmez ve sessizce ölü kalırdı."""
        assert all(term == term.lower() for term in relevance._OFF_TOPIC)
        assert all(term == term.lower() for term in relevance._MARKET_TERMS)
