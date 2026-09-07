"""Sapmanın lot karşılığı.

Bu modülün tamamı bir sınırın üzerinde duruyor: sistem hedefi KOYMUYOR ve
enstrüman SEÇMİYOR. Kova farkı mevcut ağırlıklara orantılı dağıtılıyor --
seçmek bir tavsiye olurdu, orantılı dağıtmak aritmetiktir. Testlerin çoğu bu
sınırı ve emir üretilemeyen her satırın NEDENİNİ SÖYLEDİĞİNİ sabitliyor.
"""

from __future__ import annotations

import pytest

from app.modules.investment import rebalance


def _holding(symbol, bucket, quantity, price, value, currency="TRY", kind="stock"):
    return {
        "symbol": symbol, "bucket": bucket, "quantity": quantity,
        "price": price, "currency": currency, "value_base": value,
        "asset_kind": kind, "name": symbol,
    }


def _drift(bucket, label, gap):
    return {"bucket": bucket, "label": label, "gap_amount": gap}


class TestProportionalSplit:
    def test_a_bucket_gap_is_split_by_current_weight(self):
        """Hangi enstrümanın satılacağını SEÇMEK bir tavsiye olurdu."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [
                _holding("A", "bist_equity", 100, 100.0, 7_500.0),
                _holding("B", "bist_equity", 100, 100.0, 2_500.0),
            ],
            {}, "TRY", available_cash=0.0,
        )
        quantities = {row["symbol"]: row["quantity"] for row in out["rows"]}
        assert quantities == {"A": 75.0, "B": 25.0}

    def test_a_positive_gap_sells_and_a_negative_one_buys(self):
        """İşaret YÖNÜ taşıyor: pozitif fazla, negatif eksik."""
        sell = rebalance.plan(
            [_drift("bist_equity", "BIST", 1_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        buy = rebalance.plan(
            [_drift("bist_equity", "BIST", -1_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=99_999.0,
        )
        assert sell["rows"][0]["side"] == rebalance.SELL
        assert buy["rows"][0]["side"] == rebalance.BUY


class TestRounding:
    def test_quantities_are_floored_not_rounded(self):
        """Yukarı yuvarlamak kullanıcının kendi hedefini aşar ve satışta elde
        olmayan adedi satmaya çalışır."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 1_990.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["quantity"] == 19.0

    def test_the_rounding_residual_is_reported(self):
        """Saklanan bir artık, görünmeyen bir artıktan iyidir."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 1_990.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["residual_base"] == pytest.approx(90.0)
        assert out["rounding_residual_base"] == pytest.approx(90.0)

    def test_a_fund_keeps_its_fractional_units(self):
        """Fon adetleri `Numeric(19,6)`; hisse adetleri tam sayı."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 150.0)],
            [_holding("FON", "bist_equity", 100, 100.0, 10_000.0, kind="fund")],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["quantity"] == pytest.approx(1.5)

    def test_a_sub_unit_gap_produces_no_order_but_says_why(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 50.0)],
            [_holding("A", "bist_equity", 10, 100.0, 1_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"] == []
        assert "bir birimden küçük" in out["unresolved"][0]["reason"]
        assert "100,00" in out["unresolved"][0]["reason"], "Türkçe sayı biçimi"


class TestSellableCeiling:
    def test_a_sell_never_exceeds_what_is_held(self):
        """Elde olmayanı satmaya çalışmak `stage`in blokerine düşerdi; oraya
        hiç gitmeden burada kesiliyor."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 100_000.0)],
            [_holding("A", "bist_equity", 5, 100.0, 500.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["quantity"] == 5.0


class TestCurrency:
    def test_a_foreign_price_is_converted_before_the_quantity(self):
        out = rebalance.plan(
            [_drift("us_equity", "ABD Hisse", -7_000.0)],
            [_holding("AAPL", "us_equity", 10, 200.0, 70_000.0, currency="USD")],
            {"USD": 35.0}, "TRY", available_cash=99_999.0,
        )
        # 7.000 TL / (200 USD * 35) = 1 adet
        assert out["rows"][0]["quantity"] == 1.0

    def test_a_missing_rate_produces_no_order(self):
        """1.0 VARSAYILMIYOR: bu depoda bir kez ölçüldü, 15.098 TL'lik bir
        alım 315 TL'ye yapılıyordu."""
        out = rebalance.plan(
            [_drift("us_equity", "ABD Hisse", -7_000.0)],
            [_holding("AAPL", "us_equity", 10, 200.0, 70_000.0, currency="USD")],
            {}, "TRY", available_cash=99_999.0,
        )
        assert out["rows"] == []
        assert "kuru okunamadı" in out["unresolved"][0]["reason"]


class TestWhatCannotBeOrdered:
    def test_an_empty_bucket_leaves_the_choice_to_the_user(self):
        out = rebalance.plan(
            [_drift("gold", "Altın", -5_000.0)], [], {}, "TRY",
        )
        assert out["rows"] == []
        assert "sizin seçiminiz" in out["unresolved"][0]["reason"]

    def test_cash_never_gets_an_order_of_its_own(self):
        """Nakit diğer emirlerin SONUCU; bir "nakit al" emri üretmek alınacak
        bir enstrüman uydurmak olurdu."""
        out = rebalance.plan(
            [_drift("cash", "Nakit (TRY)", 2_000.0)], [], {}, "TRY",
        )
        assert out["rows"] == []
        assert "diğer emirlerin sonucunda" in out["unresolved"][0]["reason"]

    def test_a_negligible_cash_gap_is_not_even_mentioned(self):
        out = rebalance.plan(
            [_drift("cash", "Nakit (TRY)", 0.001)], [], {}, "TRY",
        )
        assert out["unresolved"] == []

    def test_a_bucket_without_a_target_is_skipped(self):
        """Hedefi olmayan kova sapma üretmiyor; `gap_amount` None."""
        out = rebalance.plan(
            [{"bucket": "gold", "label": "Altın", "gap_amount": None}],
            [], {}, "TRY",
        )
        assert out["rows"] == [] and out["unresolved"] == []

    def test_the_other_bucket_is_never_ordered(self):
        """`other` hedef alamıyor, dolayısıyla emri de olamaz."""
        out = rebalance.plan(
            [_drift("other", "Diğer", 5_000.0)],
            [_holding("X", "other", 10, 100.0, 1_000.0)],
            {}, "TRY",
        )
        assert out["rows"] == [] and out["unresolved"] == []

    def test_a_priceless_holding_produces_no_order(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 5_000.0)],
            [_holding("A", "bist_equity", 10, None, 1_000.0)],
            {}, "TRY",
        )
        assert "güncel fiyat yok" in out["unresolved"][0]["reason"]

    def test_a_valueless_bucket_is_reported(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 5_000.0)],
            [_holding("A", "bist_equity", 10, 100.0, 0.0)],
            {}, "TRY",
        )
        assert "değeri ölçülemedi" in out["unresolved"][0]["reason"]


class TestCash:
    def test_blocked_cash_is_subtracted_from_what_is_usable(self):
        """GTC bir emir parayı süresiz tutabiliyor; bakiyede eksilen ama
        nedeni yazmayan bir tutar kullanıcıya hata gibi görünür."""
        out = rebalance.plan(
            [], [], {}, "TRY", blocked_cash=1_000.0, available_cash=5_000.0
        )
        assert out["usable_cash_base"] == 4_000.0
        assert out["blocked_cash_base"] == 1_000.0

    def test_an_unaffordable_buy_warns_but_still_lists(self):
        """Listeyi gizlemek, kullanıcıya neyin eksik olduğunu söylememek
        olurdu; `stage` kendi bakiye kapısını zaten uyguluyor."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", -10_000.0)],
            [_holding("A", "bist_equity", 10, 100.0, 1_000.0)],
            {}, "TRY", blocked_cash=0.0, available_cash=500.0,
        )
        assert out["rows"], "emirler yine listeleniyor"
        assert "Bloke tutar düşülmüştür" in out["warning"]

    def test_an_affordable_buy_has_no_warning(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", -1_000.0)],
            [_holding("A", "bist_equity", 10, 100.0, 1_000.0)],
            {}, "TRY", available_cash=99_999.0,
        )
        assert out["warning"] is None


class TestSummary:
    """Sohbete GİDEN cümle. Emir satırları ona hiç ulaşmıyor.

    Gerekçe: ekranda kullanıcı hedefi kendi koydu ve her satırı kendi
    tıklaması onaylıyor. Aynı listeyi sohbette adet ve yönle yeniden basmak o
    nedensellik zincirini koparıyor -- ölçüldü, model satırları bir alım-satım
    tablosuna çevirdi ve çekince eklendikten sonra bile çıktı bir tavsiyeden
    ayırt edilemiyordu.
    """

    def test_it_describes_the_shape_not_the_rows(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY",
        )
        assert "1 satış" in out["summary"]
        assert "BIST Hisse" in out["summary"]
        # Sembol ve adet cümlede YOK.
        assert "A için" not in out["summary"]
        assert "100 adet" not in out["summary"]

    def test_both_sides_are_counted(self):
        out = rebalance.plan(
            [
                _drift("bist_equity", "BIST Hisse", 10_000.0),
                _drift("us_equity", "ABD Hisse", -7_000.0),
            ],
            [
                _holding("A", "bist_equity", 100, 100.0, 10_000.0),
                _holding("AAPL", "us_equity", 10, 200.0, 70_000.0, currency="USD"),
            ],
            {"USD": 35.0}, "TRY", available_cash=99_999.0,
        )
        assert "1 satış ve 1 alış" in out["summary"]

    def test_buckets_without_an_order_are_counted_too(self):
        """Kaç kovanın emir üretemediği listenin şeklinin parçası; sessizce
        atlamak hedefe ulaşılamamasının sebebini görünmez yapardı."""
        out = rebalance.plan(
            [_drift("gold", "Altın", -5_000.0)], [], {}, "TRY",
        )
        assert "1 kova için emir üretilemedi" in out["summary"]

    def test_nothing_to_do_says_so(self):
        out = rebalance.plan([], [], {}, "TRY")
        assert "emre dönüşen bir fark yok" in out["summary"]

    def test_only_sells_reads_naturally(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY",
        )
        assert " ve " not in out["summary"].split(" satırı")[0]

    def test_only_buys_reads_naturally(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", -10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=99_999.0,
        )
        assert "1 alış satırı" in out["summary"]


class TestWording:
    """Üretilen HİÇBİR cümle uygunluk kurallarına takılmamalı.

    Bu uç REST tarafında ve uygunluk kapısı yalnızca sohbet taslağına
    uygulanıyor -- kuralın çalıştığını garanti eden başka mekanizma yok.
    """

    def _statements(self):
        out = rebalance.plan(
            [
                _drift("bist_equity", "BIST Hisse", 10_000.0),
                _drift("us_equity", "ABD Hisse", -7_000.0),
                _drift("gold", "Altın", -5_000.0),
                _drift("cash", "Nakit (TRY)", 2_000.0),
            ],
            [
                _holding("A", "bist_equity", 100, 100.0, 10_000.0),
                _holding("AAPL", "us_equity", 10, 200.0, 70_000.0, currency="USD"),
                _holding("KUCUK", "bist_equity", 1, 100_000.0, 1.0),
            ],
            {"USD": 35.0}, "TRY", blocked_cash=100.0, available_cash=200.0,
        )
        texts = [row["statement"] for row in out["rows"]]
        texts += [row["reason"] for row in out["unresolved"]]
        texts.append(out["disclaimer"])
        texts.append(out["summary"])
        if out["warning"]:
            texts.append(out["warning"])
        return texts

    def test_nothing_trips_an_advice_or_suitability_rule(self):
        from app.modules.compliance import rules

        watched = {"ADV-001", "ADV-002", "ADV-003", "SUI-001",
                   "GUA-001", "GUA-002", "GUA-003", "EXE-001", "SOL-001"}
        for rule in (r for r in rules.RULES if r.rule_id in watched):
            for text in self._statements():
                assert not rule.regex.search(text), f"{rule.rule_id}: {text}"

    def test_no_statement_tells_the_user_what_to_do(self):
        """"almalısınız" yok, "karşılığı" var: cümle kullanıcının kendi
        hedefinin aritmetiğini anlatıyor."""
        for text in self._statements():
            lowered = text.lower()
            for banned in ("almalı", "satmalı", "öneri", "tavsiye ederiz",
                           "en iyi", "ideal", "size uygun"):
                assert banned not in lowered, f"{banned}: {text}"

    def test_the_disclaimer_travels_with_the_plan(self):
        """Sunucudan geliyor ki arayüzde ikinci kez yazılmasın: iki kopyadan
        biri değişip diğeri kalabilirdi."""
        out = rebalance.plan([], [], {}, "TRY")
        assert out["disclaimer"] == rebalance.DISCLAIMER_TR
        assert "yatırım tavsiyesi değildir" in out["disclaimer"]
