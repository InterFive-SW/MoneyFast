"""Kovalar, mevcut ağırlıklar ve kullanıcının hedefinden sapma.

Bu dosyanın koruduğu asıl şey DANIŞMANLIK ÇİZGİSİ. Hedefi kullanıcı koyuyor,
sistem değil -- `compliance/rules.py:SUI-001`'in gerekçesi "sistem ölçüm ile
kullanıcının kendi beyanını karşılaştırır, bir ürünün kişiye uygunluğuna
karar vermez" diyor, ve bir model portföy önermek tam olarak o kararı vermek
olurdu. Üstelik dört SPK ürün grubundan yalnızca hisse senedinin bu sistemde
enstrümanı var (1009 hisse, 3 döviz, 1 altın; sıfır tahvil, sıfır mevduat),
dolayısıyla önerilen hedefin çoğu uygulanamaz bir talimat olurdu.

İkincisi: HEDEFSİZ ile HEDEFİ SIFIR aynı şey değil. İkincisi elde tutulan her
kuruşu sapma gibi gösterirdi.
"""

from __future__ import annotations

import pytest

from app.modules.investment import allocation


def _row(market):
    return {"symbol": "X", "market": market}


class TestBuckets:
    def test_every_bucket_has_a_label_and_a_colour(self):
        for key, (label, colour) in allocation.BUCKETS.items():
            assert label and colour.startswith("#"), key

    def test_gold_and_currency_are_separate_buckets(self):
        """Proje dokümanı üçünü adıyla ayırıyor: "hisse, altın ve döviz"."""
        assert allocation.bucket_for("COMEX") != allocation.bucket_for("FX")

    def test_an_unmapped_venue_falls_to_other_rather_than_disappearing(self):
        """Grafikten kaybolan bir pozisyon, yanlış kovaya düşenden çok daha
        zor fark edilir."""
        assert allocation.bucket_for("XETRA") == allocation.OTHER
        assert allocation.bucket_for(None) == allocation.OTHER

    def test_other_cannot_be_a_target(self):
        """Kimse "sınıflandıramadığım şeylerde %10 olsun" diye hedef koymaz,
        ve koyabilseydi bu, eşlenmemiş bir piyasayı hedef hâline getirirdi."""
        assert allocation.OTHER not in allocation.TARGETABLE
        assert allocation.CASH in allocation.TARGETABLE


class TestCurrentAmounts:
    def test_holdings_land_in_their_venues_bucket(self):
        amounts = allocation.current_amounts(
            [(_row("BIST"), 900.0), (_row("COMEX"), 100.0)], cash=0.0
        )
        assert amounts["bist_equity"] == 900.0
        assert amounts["gold"] == 100.0

    def test_cash_is_its_own_bucket(self):
        amounts = allocation.current_amounts([], cash=250.0)
        assert amounts[allocation.CASH] == 250.0

    def test_two_venues_share_the_us_bucket(self):
        amounts = allocation.current_amounts(
            [(_row("NASDAQ"), 10.0), (_row("NYSE"), 5.0)], cash=0.0
        )
        assert amounts["us_equity"] == 15.0


class TestPercentages:
    def test_weights_are_shares_of_the_whole(self):
        pct = allocation.as_percentages({"a": 25.0, "b": 75.0})
        assert pct == {"a": 25.0, "b": 75.0}

    def test_an_empty_portfolio_has_no_distribution_rather_than_zeros(self):
        """Her kovaya %0 yazmak, dağılımı olmayan bir portföye dağılımı
        varmış gibi davranmak olurdu."""
        assert allocation.as_percentages({"a": 0.0, "b": 0.0}) == {"a": None, "b": None}


class TestDrift:
    AMOUNTS = {"cash": 100.0, "bist_equity": 900.0, "us_equity": 0.0,
               "gold": 0.0, "fx": 0.0, "other": 0.0}

    def test_the_gap_is_measured_minus_declared(self):
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 60.0, "cash": 40.0})
        bist = next(r for r in out["buckets"] if r["bucket"] == "bist_equity")
        assert bist["current_percent"] == 90.0
        assert bist["gap_points"] == 30.0

    def test_the_gap_amount_carries_direction(self):
        """Pozitif fazla, negatif eksik. İşaret ters okunursa kullanıcı
        hedefinin tersine hareket eder."""
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 60.0, "cash": 40.0})
        bist = next(r for r in out["buckets"] if r["bucket"] == "bist_equity")
        cash = next(r for r in out["buckets"] if r["bucket"] == "cash")
        assert bist["gap_amount"] > 0 and cash["gap_amount"] < 0

    def test_the_gaps_cancel_out(self):
        """Fazlalar ve eksikler toplamda sıfır olmalı; olmazsa toplam yüzde
        100 değildir ve o hedef zaten kabul edilmemeliydi."""
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 60.0, "cash": 40.0})
        assert round(sum(r["gap_points"] for r in out["buckets"]), 6) == 0.0

    def test_a_bucket_without_a_target_is_not_treated_as_zero(self):
        """"Hedefim yok" ile "hedefim sıfır" farklı şeyler."""
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 100.0})
        cash = next(r for r in out["buckets"] if r["bucket"] == "cash")
        assert cash["target_percent"] is None
        assert cash["gap_points"] is None

    def test_an_empty_bucket_with_no_target_is_omitted(self):
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 100.0})
        assert all(r["bucket"] != "gold" for r in out["buckets"])

    def test_an_empty_bucket_WITH_a_target_is_reported(self):
        """Hedefi olup elde hiç olmayan kova, sapmanın en önemli satırı."""
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 85.0, "gold": 15.0})
        gold = next(r for r in out["buckets"] if r["bucket"] == "gold")
        assert gold["current_percent"] == 0.0
        assert gold["gap_points"] == -15.0


class TestStatement:
    """Cümle KODDA üretiliyor. Sapmanın yönü yanlış okunursa kullanıcı
    hedefinin tersine hareket eder ve bu, prompt'a ya da arayüze bırakılacak
    bir şey değil."""

    AMOUNTS = TestDrift.AMOUNTS

    def test_no_target_says_so_and_says_what_setting_one_does(self):
        out = allocation.drift(self.AMOUNTS, {})
        assert out["has_target"] is False
        assert "Hedef dağılım belirlemediniz" in out["statement"]

    def test_an_empty_portfolio_with_a_target_says_there_is_nothing_to_compare(self):
        out = allocation.drift({key: 0.0 for key in allocation.BUCKETS},
                               {"bist_equity": 100.0})
        assert "karşılaştırılacak bir portföy değeri yok" in out["statement"]

    #: Üç hedefli, asimetrik durum. İki hedefli bir portföyde farklar her
    #: zaman birbirinin aynası olur ve "en büyük fark" beraberlikte kalır.
    THREE = {"bist_equity": 60.0, "gold": 25.0, "cash": 15.0}

    def test_the_widest_gap_is_named_with_both_numbers(self):
        out = allocation.drift(self.AMOUNTS, self.THREE)
        assert "BIST Hisse" in out["statement"]
        assert "%60" in out["statement"] and "%90" in out["statement"]

    def test_a_tie_is_broken_by_the_canonical_bucket_order(self):
        """İki hedefli bir portföyde fazla ve eksik her zaman eşit büyüklükte.
        Hangisinin anıldığı rastgele değil, `BUCKETS` sırası -- yoksa aynı
        veri iki çağrıda iki farklı cümle üretirdi."""
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 60.0, "cash": 40.0})
        first = next(iter(allocation.BUCKETS))
        assert allocation.label_for(first) in out["statement"]

    def test_a_portfolio_on_target_says_so(self):
        out = allocation.drift(self.AMOUNTS, {"bist_equity": 90.0, "cash": 10.0})
        assert "aynı noktada" in out["statement"]

    def test_direction_is_stated_both_ways(self):
        over = allocation.drift(self.AMOUNTS, self.THREE)
        # Elde hiç altın yok, hedef %50: en büyük fark eksik yönünde.
        under = allocation.drift(
            self.AMOUNTS, {"gold": 50.0, "bist_equity": 45.0, "cash": 5.0}
        )
        assert "üzerinde" in over["statement"]
        assert "altında" in under["statement"]

    ALL = [
        allocation.drift(TestDrift.AMOUNTS, targets)["statement"]
        for targets in ({}, {"bist_equity": 60.0, "gold": 25.0, "cash": 15.0},
                        {"bist_equity": 90.0, "cash": 10.0},
                        {"gold": 50.0, "bist_equity": 45.0, "cash": 5.0})
    ]

    def test_no_statement_trips_the_suitability_rule(self):
        """Hedef kullanıcının kendi beyanı, dolayısıyla karşılaştırma bir
        uygunluk iddiası değil -- ve bunun tesadüf olmadığını burası
        sabitliyor."""
        from app.modules.compliance import rules

        rule = next(r for r in rules.RULES if r.rule_id == "SUI-001")
        for statement in self.ALL:
            assert not rule.regex.search(statement), statement

    def test_no_statement_tells_the_user_to_trade(self):
        for statement in self.ALL:
            lowered = statement.lower()
            for banned in ("satın al", "satmalı", "azaltın", "artırın", "öneririz"):
                assert banned not in lowered, f"{banned}: {statement}"
