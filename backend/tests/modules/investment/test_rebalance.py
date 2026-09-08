"""Sapmanın lot karşılığı ve hangi enstrümanın seçildiği.

Sistem artık enstrüman SEÇİYOR ve bu bilinçli bir politika değişikliği
(bkz. teknik dokümantasyon, Bölüm 11 "Kaldırılan yasaklar"). Yerine konan
kontrol burada çivileniyor: **sayısı olmayan satır listeye girmiyor.** Bir
aday listeye ancak onu seçtiren ölçüm taşınabiliyorsa giriyor; hiçbiri yoksa
enstrüman `unresolved`'a "veri yok" notuyla düşüyor.

Testlerin geri kalanı emir üretilemeyen her satırın NEDENİNİ SÖYLEDİĞİNİ ve
aritmetiğin (taban yuvarlama, satılabilir tavan, kur) doğruluğunu koruyor.
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


class _AnyMeasured:
    """Her sembol için bir ölçüm döndüren harita.

    Aşağıdaki testlerin konusu ARİTMETİK -- taban yuvarlama, satılabilir
    tavan, kur, nakit. Gerekçe kapısı ayrı bir konu ve `TestRationaleGate`'te
    çivili; burada her adayın bir gerekçesi olduğu varsayılıyor ki ölçülen
    şey gerçekten aritmetik olsun.
    """

    def get(self, _symbol, _default=None):
        return {"pe_ratio": 10.0}


_ANY = _AnyMeasured()


def _plan(drift_rows, positions, rates=None, base_currency="TRY", **kwargs):
    """`rebalance.plan`, her adaya bir gerekçe verilmiş hâliyle."""
    kwargs.setdefault("fundamentals", _ANY)
    return rebalance.plan(drift_rows, positions, rates or {}, base_currency, **kwargs)


def _measured(*symbols, share=0.30):
    """Her sembol için bir seçim gerekçesi.

    Testlerin çoğunun konusu aritmetik, seçim değil -- ama gerekçesi olmayan
    aday listeye HİÇ girmiyor, dolayısıyla aritmetiği ölçmek için önce bir
    gerekçe gerekiyor. Kural `TestRationaleGate`'te ayrıca çivili.
    """
    return {symbol: {"contribution": share, "weight": 0.10} for symbol in symbols}


class TestSelection:
    """Kova farkı orantılı DAĞITILMIYOR, aday SEÇİLİYOR.

    Sıralama satışta en yüksek risk katkısıyla başlıyor: riski düşürmek
    isteyen için en büyük pozisyon değil, portföy oynaklığının en büyük
    payını üreten pozisyon önemli.
    """

    def test_the_largest_risk_contributor_is_sold_first(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 7_500.0)],
            [
                _holding("KUCUK", "bist_equity", 100, 100.0, 10_000.0),
                _holding("BUYUK", "bist_equity", 100, 100.0, 10_000.0),
            ],
            {}, "TRY", available_cash=0.0,
            contributions={
                "KUCUK": {"contribution": 0.10, "weight": 0.5},
                "BUYUK": {"contribution": 0.60, "weight": 0.5},
            },
        )
        assert [row["symbol"] for row in out["rows"]] == ["BUYUK"]
        assert out["rows"][0]["quantity"] == 75.0

    def test_the_gap_spills_to_the_next_candidate(self):
        """Bir enstrümandan elde olandan fazlası istenemez; sıra bir
        sonrakine geçiyor."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 15_000.0)],
            [
                _holding("BUYUK", "bist_equity", 100, 100.0, 10_000.0),
                _holding("KUCUK", "bist_equity", 100, 100.0, 10_000.0),
            ],
            {}, "TRY", available_cash=0.0,
            contributions={
                "BUYUK": {"contribution": 0.60, "weight": 0.5},
                "KUCUK": {"contribution": 0.10, "weight": 0.5},
            },
        )
        assert [row["symbol"] for row in out["rows"]] == ["BUYUK", "KUCUK"]
        assert [row["quantity"] for row in out["rows"]] == [100.0, 50.0]

    def test_a_buy_starts_with_the_smallest_contributor(self):
        """Alışta kural satışın AYNASI: eklenecek ilk şey, oynaklığa en az
        katkı veren pozisyon."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", -5_000.0)],
            [
                _holding("BUYUK", "bist_equity", 100, 100.0, 10_000.0),
                _holding("KUCUK", "bist_equity", 100, 100.0, 10_000.0),
            ],
            {}, "TRY", available_cash=99_999.0,
            contributions={
                "BUYUK": {"contribution": 0.60, "weight": 0.5},
                "KUCUK": {"contribution": 0.10, "weight": 0.5},
            },
        )
        assert [row["symbol"] for row in out["rows"]] == ["KUCUK"]

    def test_a_candidate_without_a_measured_contribution_sorts_last(self):
        """Ölçülemeyen bir aday, ölçülmüş bir adayın önüne geçmemeli."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 15_000.0)],
            [
                _holding("OLCUSUZ", "bist_equity", 100, 100.0, 10_000.0),
                _holding("OLCULU", "bist_equity", 100, 100.0, 10_000.0),
            ],
            {}, "TRY", available_cash=0.0,
            contributions={"OLCULU": {"contribution": 0.40, "weight": 0.5}},
            fundamentals={"OLCUSUZ": {"pe_ratio": 12.0}},
        )
        assert [row["symbol"] for row in out["rows"]] == ["OLCULU", "OLCUSUZ"]

    def test_a_positive_gap_sells_and_a_negative_one_buys(self):
        """İşaret YÖNÜ taşıyor: pozitif fazla, negatif eksik."""
        sell = rebalance.plan(
            [_drift("bist_equity", "BIST", 1_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0, contributions=_measured("A"),
        )
        buy = rebalance.plan(
            [_drift("bist_equity", "BIST", -1_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=99_999.0, contributions=_measured("A"),
        )
        assert sell["rows"][0]["side"] == rebalance.SELL
        assert buy["rows"][0]["side"] == rebalance.BUY


class TestRationaleGate:
    """Kaldırılan yasakların yerine konan BİRİNCİ kontrol.

    Boş bir gerekçe alanıyla öneri sunmak, gerekçeyi kullanıcının uydurmasına
    bırakmak olurdu -- ve bir tavsiyeyi bir ölçüm raporundan ayıran tek şey
    bu.
    """

    def test_no_measurement_means_no_order(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"] == []

    def test_the_skipped_instrument_is_named_with_its_reason(self):
        """Sessizce atlanmış bir aday, kullanıcının hedefine ulaşamamasının
        sebebini görünmez yapardı."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["unresolved"][0]["symbol"] == "A"
        assert "seçim gerekçesi ölçülemedi" in out["unresolved"][0]["reason"]

    def test_a_single_fundamental_is_enough(self):
        """Risk katkısı ölçülemeyen bir portföyde seçim yalnızca temel
        veriyle yapılabiliyor; bu bir eksiklik değil, kapsama."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
            fundamentals={"A": {"pe_ratio": 9.4}},
        )
        assert out["rows"][0]["symbol"] == "A"
        assert out["rows"][0]["rationale"][0]["kind"] == rebalance.VALUATION

    def test_a_news_reading_alone_is_enough(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
            news={"A": {"mechanism": "Sözleşme tutarı yıllık ihracata ekleniyor."}},
        )
        assert out["rows"][0]["rationale"][0]["kind"] == rebalance.NEWS
        # Haber bir SAYI değil; `value` uydurulmuyor.
        assert out["rows"][0]["rationale"][0]["value"] is None

    def test_every_row_carries_its_rationale(self):
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0, contributions=_measured("A"),
        )
        assert all(row["rationale"] for row in out["rows"])


class TestSelectionEdges:
    def test_a_holding_with_no_value_left_takes_nothing(self):
        """Sıra bir sonrakine geçmiş ve elinde satılacak değeri kalmamış bir
        aday için emir üretilmiyor -- sıfır adetlik bir satır, yapılacak bir
        şey yokken yapılacak bir şey varmış gibi görünürdü."""
        out = rebalance.plan(
            # Fark DOLU'nun tamamından büyük: sıra BOS'a geliyor ve orada
            # satılacak değer kalmamış oluyor.
            [_drift("bist_equity", "BIST Hisse", 15_000.0)],
            [
                _holding("DOLU", "bist_equity", 100, 100.0, 10_000.0),
                _holding("BOS", "bist_equity", 5, 100.0, 0.0),
            ],
            {}, "TRY", available_cash=0.0,
            contributions={
                "DOLU": {"contribution": 0.50, "weight": 0.5},
                "BOS": {"contribution": 0.30, "weight": 0.3},
            },
        )
        assert [row["symbol"] for row in out["rows"]] == ["DOLU"]


class TestRationaleWording:
    def test_a_negative_profitability_keeps_its_sign(self):
        """Ölçülen hata: özkaynak kârlılığı -0,3521 olan bir şirket
        "Özkaynak kârlılığı %35,2" diye yazılıyordu -- zarar eden bir şirketi
        kâr ediyor gibi göstermek."""
        rows = rebalance.rationale_for(
            rebalance.SELL, None, {"return_on_equity": -0.3521}, None
        )
        assert "-%35,2" in rows[0]["text"]

    def test_the_sign_precedes_the_percent_sign(self):
        """Türkçede "-%35,2" yazılır; "%-35,2" ekranda dizgi hatası gibi
        okunuyor."""
        assert rebalance._pct(-0.35) == "-%35,0"

    def test_a_dampening_position_is_described_in_words(self):
        """Negatif katkı bir hata değil, sönümleyen bir varlık."""
        rows = rebalance.rationale_for(
            rebalance.SELL, {"contribution": -0.084, "weight": 0.05}, None, None
        )
        assert "azaltıyor" in rows[0]["text"]

    def test_a_tiny_contribution_is_not_a_reason(self):
        """Yüzde birlik bir katkı, satışı açıklayan bir sayı değil."""
        assert rebalance.rationale_for(
            rebalance.SELL, {"contribution": 0.01, "weight": 0.02}, None, None
        ) == []

    def test_a_ratio_is_never_called_cheap_or_expensive(self):
        """Bir orana iyi ya da kötü demek, o oranın ne olduğunu söylemekten
        farklı bir iddia."""
        rows = rebalance.rationale_for(
            rebalance.SELL, None,
            {"pe_ratio": 4.0, "return_on_equity": 0.9, "debt_to_equity": 12.0}, None,
        )
        text = " ".join(row["text"] for row in rows).lower()
        for banned in ("ucuz", "pahalı", "cazip", "iyi", "kötü", "yüksek", "düşük"):
            assert banned not in text


class TestCoverage:
    """Kapsama DÜZ DEĞİL ve bunu söylemeden bir liste sunmak, eksik bir
    ölçümü tam bir ölçüm gibi göstermek olurdu."""

    def test_it_counts_positions_not_percentages(self):
        """Üç pozisyonun ikisi ile doksanın altmışı aynı orana düşer; payda
        yazılı olduğunda okuyan ikisini ayırt edebiliyor."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST", 1_000.0)],
            [
                _holding("A", "bist_equity", 100, 100.0, 10_000.0),
                _holding("B", "bist_equity", 100, 100.0, 10_000.0),
            ],
            {}, "TRY", available_cash=0.0,
            contributions={"A": {"contribution": 0.3, "weight": 0.5}},
            fundamentals={"A": {"pe_ratio": 9.0}, "B": {"pe_ratio": 11.0}},
            news={"A": {"mechanism": "x"}},
        )
        assert out["data_quality"] == {
            "positions": 2, "risk_contribution": 1, "fundamentals": 2, "news": 1
        }


class TestRounding:
    def test_quantities_are_floored_not_rounded(self):
        """Yukarı yuvarlamak kullanıcının kendi hedefini aşar ve satışta elde
        olmayan adedi satmaya çalışır."""
        out = _plan(
            [_drift("bist_equity", "BIST", 1_990.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["quantity"] == 19.0

    def test_the_rounding_residual_is_reported(self):
        """Saklanan bir artık, görünmeyen bir artıktan iyidir."""
        out = _plan(
            [_drift("bist_equity", "BIST", 1_990.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["residual_base"] == pytest.approx(90.0)
        assert out["rounding_residual_base"] == pytest.approx(90.0)

    def test_a_fund_keeps_its_fractional_units(self):
        """Fon adetleri `Numeric(19,6)`; hisse adetleri tam sayı."""
        out = _plan(
            [_drift("bist_equity", "BIST", 150.0)],
            [_holding("FON", "bist_equity", 100, 100.0, 10_000.0, kind="fund")],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["quantity"] == pytest.approx(1.5)

    def test_a_sub_unit_gap_produces_no_order_but_says_why(self):
        out = _plan(
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
        out = _plan(
            [_drift("bist_equity", "BIST", 100_000.0)],
            [_holding("A", "bist_equity", 5, 100.0, 500.0)],
            {}, "TRY", available_cash=0.0,
        )
        assert out["rows"][0]["quantity"] == 5.0


class TestCurrency:
    def test_a_foreign_price_is_converted_before_the_quantity(self):
        out = _plan(
            [_drift("us_equity", "ABD Hisse", -7_000.0)],
            [_holding("AAPL", "us_equity", 10, 200.0, 70_000.0, currency="USD")],
            {"USD": 35.0}, "TRY", available_cash=99_999.0,
        )
        # 7.000 TL / (200 USD * 35) = 1 adet
        assert out["rows"][0]["quantity"] == 1.0

    def test_a_missing_rate_produces_no_order(self):
        """1.0 VARSAYILMIYOR: bu depoda bir kez ölçüldü, 15.098 TL'lik bir
        alım 315 TL'ye yapılıyordu."""
        out = _plan(
            [_drift("us_equity", "ABD Hisse", -7_000.0)],
            [_holding("AAPL", "us_equity", 10, 200.0, 70_000.0, currency="USD")],
            {}, "TRY", available_cash=99_999.0,
        )
        assert out["rows"] == []
        assert "kuru okunamadı" in out["unresolved"][0]["reason"]


class TestWhatCannotBeOrdered:
    def test_an_empty_bucket_leaves_the_choice_to_the_user(self):
        out = _plan(
            [_drift("gold", "Altın", -5_000.0)], [], {}, "TRY",
        )
        assert out["rows"] == []
        assert "sizin seçiminiz" in out["unresolved"][0]["reason"]

    def test_cash_never_gets_an_order_of_its_own(self):
        """Nakit diğer emirlerin SONUCU; bir "nakit al" emri üretmek alınacak
        bir enstrüman uydurmak olurdu."""
        out = _plan(
            [_drift("cash", "Nakit (TRY)", 2_000.0)], [], {}, "TRY",
        )
        assert out["rows"] == []
        assert "diğer emirlerin sonucunda" in out["unresolved"][0]["reason"]

    def test_a_negligible_cash_gap_is_not_even_mentioned(self):
        out = _plan(
            [_drift("cash", "Nakit (TRY)", 0.001)], [], {}, "TRY",
        )
        assert out["unresolved"] == []

    def test_a_bucket_without_a_target_is_skipped(self):
        """Hedefi olmayan kova sapma üretmiyor; `gap_amount` None."""
        out = _plan(
            [{"bucket": "gold", "label": "Altın", "gap_amount": None}],
            [], {}, "TRY",
        )
        assert out["rows"] == [] and out["unresolved"] == []

    def test_the_other_bucket_is_never_ordered(self):
        """`other` hedef alamıyor, dolayısıyla emri de olamaz."""
        out = _plan(
            [_drift("other", "Diğer", 5_000.0)],
            [_holding("X", "other", 10, 100.0, 1_000.0)],
            {}, "TRY",
        )
        assert out["rows"] == [] and out["unresolved"] == []

    def test_a_priceless_holding_produces_no_order(self):
        out = _plan(
            [_drift("bist_equity", "BIST", 5_000.0)],
            [_holding("A", "bist_equity", 10, None, 1_000.0)],
            {}, "TRY",
        )
        assert "güncel fiyat yok" in out["unresolved"][0]["reason"]

    def test_a_valueless_bucket_is_reported(self):
        out = _plan(
            [_drift("bist_equity", "BIST", 5_000.0)],
            [_holding("A", "bist_equity", 10, 100.0, 0.0)],
            {}, "TRY",
        )
        assert "değeri ölçülemedi" in out["unresolved"][0]["reason"]


class TestCash:
    def test_blocked_cash_is_subtracted_from_what_is_usable(self):
        """GTC bir emir parayı süresiz tutabiliyor; bakiyede eksilen ama
        nedeni yazmayan bir tutar kullanıcıya hata gibi görünür."""
        out = _plan(
            [], [], {}, "TRY", blocked_cash=1_000.0, available_cash=5_000.0
        )
        assert out["usable_cash_base"] == 4_000.0
        assert out["blocked_cash_base"] == 1_000.0

    def test_an_unaffordable_buy_warns_but_still_lists(self):
        """Listeyi gizlemek, kullanıcıya neyin eksik olduğunu söylememek
        olurdu; `stage` kendi bakiye kapısını zaten uyguluyor."""
        out = _plan(
            [_drift("bist_equity", "BIST", -10_000.0)],
            [_holding("A", "bist_equity", 10, 100.0, 1_000.0)],
            {}, "TRY", blocked_cash=0.0, available_cash=500.0,
        )
        assert out["rows"], "emirler yine listeleniyor"
        assert "Bloke tutar düşülmüştür" in out["warning"]

    def test_an_affordable_buy_has_no_warning(self):
        out = _plan(
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
        out = _plan(
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
        out = _plan(
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
        out = _plan(
            [_drift("gold", "Altın", -5_000.0)], [], {}, "TRY",
        )
        assert "1 kova için emir üretilemedi" in out["summary"]

    def test_nothing_to_do_says_so(self):
        out = _plan([], [], {}, "TRY")
        assert "emre dönüşen bir fark yok" in out["summary"]

    def test_only_sells_reads_naturally(self):
        out = _plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY",
        )
        assert " ve " not in out["summary"].split(" satırı")[0]

    def test_only_buys_reads_naturally(self):
        out = _plan(
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
        out = _plan(
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
        # Bant cümlesi de bu uçtan çıkıyor ve aynı taramadan geçmeli.
        texts += [
            rebalance.band_statement("Orta", "Orta", "Orta", "USER"),
            rebalance.band_statement("Düşük", "Yüksek", "Düşük", "BAND"),
            rebalance.band_statement("Orta", "Orta", "Orta", "BAND"),
            rebalance.band_statement("Yüksek", None, "Yüksek", "BAND"),
            rebalance.band_statement(None, "Risksiz", "Risksiz", "BAND"),
            rebalance.band_statement(None, None, None, "NONE"),
        ]
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
        out = _plan([], [], {}, "TRY")
        assert out["disclaimer"] == rebalance.DISCLAIMER_TR
        assert "yatırım tavsiyesi değildir" in out["disclaimer"]


class TestSummaryCounts:
    def test_unresolved_instruments_are_not_called_buckets(self):
        """Ölçülen hata: on dört çözülemeyen satırın tamamı "kova" diye
        yazılıyordu ve kullanıcının o hesabında on dört kovası yok."""
        out = rebalance.plan(
            [_drift("bist_equity", "BIST Hisse", 10_000.0),
             _drift("gold", "Altın", -5_000.0)],
            [_holding("A", "bist_equity", 100, 100.0, 10_000.0)],
            {}, "TRY", available_cash=0.0,
        )
        # A gerekçesiz (enstrüman), altın kovasında pozisyon yok (kova).
        assert "1 kova ve 1 enstrüman için emir üretilemedi" in out["summary"]

    def test_only_buckets_reads_naturally(self):
        out = rebalance.plan(
            [_drift("gold", "Altın", -5_000.0)], [], {}, "TRY", available_cash=0.0,
        )
        assert "1 kova için emir üretilemedi" in out["summary"]


class TestBandTargets:
    """Bandın kova hedefleri, `investment.risk_band_targets`'tan.

    Sabitlenen tek şey davranış: satırı olmayan kova sözlükte de yok, ve
    sıfırla doldurulmuyor. `drift()` ikisini ayırıyor -- "hedefin yok" ile
    "hedefin sıfır" farklı iki şey ve ikincisi o kovadaki her şeyi satmak
    demek olurdu.
    """

    def _db(self, rows):
        from unittest.mock import MagicMock

        from sqlalchemy.orm import Session

        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = rows
        return db

    def test_rows_become_a_bucket_map(self):
        db = self._db([("cash", 60), ("bist_equity", 20)])
        assert rebalance.band_targets(db, "Düşük") == {"cash": 60.0, "bist_equity": 20.0}

    def test_a_bucket_without_a_row_is_absent_not_zero(self):
        """Sıfır, o kovadaki her şeyi sat demek olurdu."""
        db = self._db([("cash", 80)])
        targets = rebalance.band_targets(db, "Risksiz")
        assert "us_equity" not in targets
        assert targets.get("us_equity") is None

    def test_an_unknown_band_has_no_targets(self):
        assert rebalance.band_targets(self._db([]), "Belirsiz") == {}


class TestBandStatement:
    """Hedefin nereden geldiğini söyleyen cümle, KODDA kurulu.

    `profile.suitability()` ile aynı sınır: cümle iki olgunun
    karşılaştırması, kişi hakkında bir yargı değil. "Size uygun",
    "önerilen", "sizin için" geçmiyor ve `TestWording` bunu tarıyor.
    """

    def test_a_users_own_target_needs_no_band(self):
        text = rebalance.band_statement("Orta", "Orta", "Orta", "USER")
        assert "kendi belirlediğiniz" in text
        assert "bant" not in text.lower()

    def test_a_divergence_names_both_sides_and_the_binding_one(self):
        text = rebalance.band_statement("Düşük", "Yüksek", "Düşük", "BAND")
        assert "Düşük" in text and "Yüksek" in text and "daha temkinli" in text

    def test_agreement_says_so(self):
        text = rebalance.band_statement("Orta", "Orta", "Orta", "BAND")
        assert "aynı bandda" in text

    def test_one_missing_side_is_named_as_unread(self):
        measured_only = rebalance.band_statement("Yüksek", None, "Yüksek", "BAND")
        declared_only = rebalance.band_statement(None, "Düşük", "Düşük", "BAND")
        assert "okunamadığı" in measured_only and "Yüksek" in measured_only
        assert "okunamadığı" in declared_only and "Düşük" in declared_only

    def test_no_band_asks_for_what_is_missing(self):
        text = rebalance.band_statement(None, None, None, "NONE")
        assert "gerekiyor" in text

    def test_a_band_of_none_never_produces_a_band_sentence(self):
        """`source` BAND derken bandın `None` olması tutarsız bir durum;
        cümle onu bant varmış gibi anlatmamalı."""
        text = rebalance.band_statement("Orta", "Orta", None, "BAND")
        assert "gerekiyor" in text
