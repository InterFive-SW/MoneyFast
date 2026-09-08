"""Ölçüm ile beyanın karşılaştırılması.

Ürünün bu iki şeyi aynı cümlede kullanmasına izin verilen tek yer burası ve
danışmanlık çizgisinin doğru tarafında kalmasının sebebi şu: iki yarı da
olgu. Biri fiyat geçmişinden hesaplanıyor, diğeri kullanıcının kendi cevabı.
Hiçbiri kişi hakkında bir yargı değil ve hiçbiri ne yapılması gerektiğini
söylemiyor.
"""

from __future__ import annotations

import pytest

from app.modules.risk import profile


class TestAlignment:
    def test_same_band_is_aligned(self):
        result = profile.suitability("Orta", "Orta")
        assert result["alignment"] == profile.ALIGNMENT_ALIGNED
        assert "aynı bandda" in result["statement"]

    def test_portfolio_above_the_declared_band(self):
        result = profile.suitability("Yüksek", "Düşük")
        assert result["alignment"] == profile.ALIGNMENT_RISKIER
        assert "üzerinde" in result["statement"]

    def test_portfolio_below_the_declared_band(self):
        result = profile.suitability("Düşük", "Yüksek")
        assert result["alignment"] == profile.ALIGNMENT_CALMER
        assert "altında" in result["statement"]

    def test_a_riskless_measurement_sits_below_every_declared_band(self):
        """Dördüncü bant beyan tarafında YOK, ama karşılaştırma yine
        kurulabiliyor: "Risksiz" ortak eksenin en altında duruyor."""
        for declared in ("Düşük", "Orta", "Yüksek"):
            result = profile.suitability("Risksiz", declared)
            assert result["alignment"] == profile.ALIGNMENT_CALMER
            assert "altında" in result["statement"]

    def test_a_riskless_declaration_cannot_be_compared(self):
        """Anket "Risksiz" üretemiyor; üretmiş görünen bir değer, ölçekleri
        karışmış bir kayıt demek ve karşılaştırma onu kabul etmemeli.

        Kabul etseydi cevap "ikisi aynı bandda" olurdu -- var olmayan bir
        beyanla var olan bir ölçümü eşitleyen bir cümle."""
        result = profile.suitability("Risksiz", "Risksiz")
        assert result["alignment"] == profile.ALIGNMENT_UNKNOWN

    @pytest.mark.parametrize(
        "measured,declared",
        [(None, "Orta"), ("Orta", None), (None, None), ("Belirsiz", "Orta"), ("Orta", "Agresif")],
    )
    def test_anything_unmeasurable_or_undeclared_is_unknown(self, measured, declared):
        """Yalnızca yarısı bilinen bir karşılaştırma, karşılaştırma değildir."""
        result = profile.suitability(measured, declared)
        assert result["alignment"] == profile.ALIGNMENT_UNKNOWN
        assert "gerekiyor" in result["statement"]

    def test_both_sides_are_echoed_back(self):
        """Kullanıcı cümlenin hangi iki değerden kurulduğunu görebilmeli."""
        result = profile.suitability("Yüksek", "Orta")
        assert result["measured_level"] == "Yüksek"
        assert result["declared_tolerance"] == "Orta"


class TestWording:
    """Cümlenin kendisi bir uyumluluk kuralına takılmamalı ve bir direktif
    içermemeli."""

    ALL = [
        profile.suitability(measured, declared)["statement"]
        for measured in ("Düşük", "Orta", "Yüksek")
        for declared in ("Düşük", "Orta", "Yüksek")
    ] + [profile.suitability(None, None)["statement"]]

    def test_no_statement_trips_the_suitability_rule(self):
        """SUI-001 "size uygun" / "risk profilinize uygun" kalıplarını
        engelliyor. Ürettiğimiz cümle bir karşılaştırma, bir uygunluk iddiası
        değil — ve bunun tesadüf olmadığını burası sabitliyor."""
        from app.modules.compliance import rules

        rule = next(r for r in rules.RULES if r.rule_id == "SUI-001")
        for statement in self.ALL:
            assert not rule.regex.search(statement), statement

    def test_no_statement_contains_a_directive(self):
        for statement in self.ALL:
            lowered = statement.lower()
            for banned in ("azalt", "artır", "satın al", "öneririz", "meli", "malı"):
                assert banned not in lowered, f"{banned}: {statement}"

    def test_every_statement_names_both_numbers_it_compares(self):
        """Gerekçesiz bir karşılaştırma, kullanıcının doğrulayamayacağı bir
        iddiadır."""
        for measured in ("Düşük", "Orta", "Yüksek"):
            for declared in ("Düşük", "Orta", "Yüksek"):
                statement = profile.suitability(measured, declared)["statement"]
                assert measured in statement
                assert declared in statement


def _pos(symbol, value, asset_class="stock"):
    return {"symbol": symbol, "market_value": value, "asset_class": asset_class}


def _group(key, eligible, label="Grup", reason="gerekçe"):
    return {"key": key, "label": label, "eligible": eligible, "reason": reason}


class TestGroupExposure:
    """`suitability`'nin ikinci yarısı: o, ölçülen risk seviyesini beyan
    edilen toleransla karşılaştırıyor; bu, ürün grubu başına TUTULAN ağırlığı
    o grup için verilen bilgi ve tecrübe beyanıyla.

    Aynı çizgi, aynı sebeple: iki yarı da olgu. Biri portföyden ölçülüyor,
    diğeri kullanıcının kendi cevabı.
    """

    EQUITY = [_group("equity", True, "Ortaklık Payı")]

    def test_holdings_are_grouped_and_weighted(self):
        out = profile.group_exposure(
            [_pos("THYAO", 7500.0), _pos("AKBNK", 2500.0)], self.EQUITY
        )
        row = out["groups"][0]
        assert row["group"] == "equity"
        assert row["value"] == 10000.0
        assert row["share_percent"] == 100.0

    def test_a_declared_group_reports_the_declaration(self):
        out = profile.group_exposure([_pos("THYAO", 100.0)], self.EQUITY)
        assert out["groups"][0]["status"] == profile.EXPOSURE_COVERED
        assert out["groups"][0]["eligible"] is True

    def test_an_undeclared_group_reports_the_users_own_answer(self):
        """"Beyan etmemiştiniz" kullanıcının KENDİ cevabını aktarır; "size
        uygun değil" onun hakkında karar verirdi."""
        out = profile.group_exposure(
            [_pos("THYAO", 100.0)], [_group("equity", False)]
        )
        row = out["groups"][0]
        assert row["status"] == profile.EXPOSURE_NOT_ASSESSED
        assert row["eligible"] is False
        assert "beyan etmemiştiniz" in row["statement"]

    def test_a_group_never_asked_about_is_distinct_from_one_declined(self):
        """Biri "soruldu, yeterli çıkmadı", diğeri "hiç sorulmadı"."""
        out = profile.group_exposure([_pos("THYAO", 100.0)], [])
        row = out["groups"][0]
        assert row["eligible"] is None
        assert "bir kaydınız yok" in row["statement"]

    def test_gold_and_currency_are_reported_as_outside_the_test(self):
        """Spot altın ve döviz dört grubun HİÇBİRİNDE yok. Bir enstrümanı ona
        ait olmayan bir gruba sokmak, o grup için verilmiş bir beyanı hakkında
        hiç soru sorulmamış bir ürüne uygulamak olurdu."""
        out = profile.group_exposure(
            [_pos("THYAO", 900.0), _pos("XAUUSD", 100.0, "commodity")], self.EQUITY
        )
        outside = out["groups"][-1]
        assert outside["group"] is None
        assert outside["status"] == profile.EXPOSURE_OUTSIDE_TEST
        assert outside["share_percent"] == 10.0
        assert "commodity" in outside["statement"]

    def test_uncovered_holdings_are_never_silently_dropped(self):
        """Düşürmek, portföyün bir kısmını değerlendirilmiş gibi
        göstermek olurdu."""
        out = profile.group_exposure(
            [_pos("USDTRY", 400.0, "fx"), _pos("XAUUSD", 600.0, "commodity")],
            self.EQUITY,
        )
        assert out["total_value"] == 1000.0
        assert sum(row["value"] for row in out["groups"]) == 1000.0

    def test_an_empty_portfolio_reports_no_groups(self):
        out = profile.group_exposure([], self.EQUITY)
        assert out["groups"] == []
        assert out["total_value"] == 0.0

    def test_a_never_taken_test_is_distinct_from_an_empty_result(self):
        assert profile.group_exposure([_pos("THYAO", 1.0)], None)["assessed"] is False
        assert profile.group_exposure([_pos("THYAO", 1.0)], self.EQUITY)["assessed"] is True

    def test_groups_are_ordered_by_weight(self):
        out = profile.group_exposure(
            [_pos("THYAO", 100.0), _pos("XAUUSD", 900.0, "commodity")], self.EQUITY
        )
        assert [row["value"] for row in out["groups"]] == [100.0, 900.0]

    ALL = [
        row["statement"]
        for groups in ([_group("equity", True)], [_group("equity", False)], [], None)
        for row in profile.group_exposure(
            [_pos("THYAO", 900.0), _pos("XAUUSD", 100.0, "commodity")], groups
        )["groups"]
    ]

    def test_no_statement_trips_the_suitability_rule(self):
        """SUI-001 tam olarak "size uygun" / "risk profilinize uygun"
        kalıplarını engelliyor. Bu cümleler ondan bilerek kaçınıyor ve bunun
        tesadüf olmadığını burası sabitliyor -- canlı uyumluluk motoruna karşı
        da doğrulandı."""
        from app.modules.compliance import rules

        rule = next(r for r in rules.RULES if r.rule_id == "SUI-001")
        for statement in self.ALL:
            assert not rule.regex.search(statement), statement

    def test_no_statement_tells_the_user_what_to_do_with_a_position(self):
        for statement in self.ALL:
            lowered = statement.lower()
            for banned in ("azalt", "artır", "satın al", "satmalı", "öneririz"):
                assert banned not in lowered, f"{banned}: {statement}"


class TestTemplateComparison:
    """`suitability` ile AYNI dil ve aynı sınır: iki OLGU yan yana konuyor.

    Öne çıkarma bir SIRALAMA girdisi, bir seçim değil -- sistem şablonu
    seçmiyor, kullanıcı seçiyor.
    """

    ALL = [
        profile.template_comparison("Dengeli", vol, declared)["statement"]
        for vol in (None, 0.05, 0.14, 0.35)
        for declared in (None, "Düşük", "Orta", "Yüksek")
    ] + [
        profile.template_comparison("Dengeli", None, "Orta", ["ABD Hisse"])["statement"]
    ]

    def test_no_statement_trips_the_suitability_rule(self):
        """SUI-001 "size uygun" kalıplarını engelliyor. Ürettiğimiz cümle bir
        karşılaştırma, bir uygunluk iddiası değil -- ve bunun tesadüf
        olmadığını burası sabitliyor."""
        from app.modules.compliance import rules

        rule = next(r for r in rules.RULES if r.rule_id == "SUI-001")
        for statement in self.ALL:
            assert not rule.regex.search(statement), statement

    def test_no_statement_trips_any_advice_rule(self):
        from app.modules.compliance import rules

        watched = {"ADV-001", "ADV-002", "ADV-003", "GUA-001", "GUA-002",
                   "GUA-003", "SOL-001"}
        for rule in (r for r in rules.RULES if r.rule_id in watched):
            for statement in self.ALL:
                assert not rule.regex.search(statement), f"{rule.rule_id}: {statement}"

    def test_no_statement_recommends_or_ranks(self):
        for statement in self.ALL:
            lowered = statement.lower()
            for banned in ("önerilen", "öneririz", "size uygun", "en iyi",
                           "tercih edin", "seçin", "ideal"):
                assert banned not in lowered, f"{banned}: {statement}"

    def test_a_matching_band_is_highlighted(self):
        out = profile.template_comparison("Dengeli", 0.05, "Düşük")
        assert out["band"] == "Düşük"
        assert out["highlighted"] is True
        assert "aynı bandda" in out["statement"]

    def test_a_mismatch_names_which_side(self):
        higher = profile.template_comparison("Ağırlıklı hisse", 0.35, "Düşük")
        lower = profile.template_comparison("Ağırlıklı nakit", 0.05, "Yüksek")
        assert "üzerinde ölçülüyor" in higher["statement"]
        assert "altında ölçülüyor" in lower["statement"]
        assert higher["highlighted"] is False and lower["highlighted"] is False

    def test_without_a_questionnaire_nothing_is_highlighted(self):
        """Beyan yoksa karşılaştırılacak ikinci olgu da yok."""
        out = profile.template_comparison("Dengeli", 0.14, None)
        assert out["highlighted"] is False
        assert "risk anketi gerekiyor" in out["statement"]
        assert "%14,0" in out["statement"], "ölçüm yine söyleniyor"

    def test_an_unmeasured_template_names_what_was_missing(self):
        out = profile.template_comparison("Dengeli", None, "Orta", ["ABD Hisse"])
        assert out["band"] is None
        assert out["highlighted"] is False
        assert "ABD Hisse" in out["statement"]

    def test_the_bands_come_from_the_scoring_scale(self):
        """İki farklı ölçekten "Orta" karşılaştırmak, aynı kelimeyle iki
        farklı şey söylemek olurdu.

        İlk denemede eşikler elle seçilmişti ve üç şablonun ÜÇÜ de "Düşük"
        çıkıyordu -- öne çıkarma anlamını yitiriyordu."""
        assert profile.VOLATILITY_BANDS[0][0] == profile.VOLATILITY_FLOOR
        assert profile.volatility_band(0.05) == "Düşük"
        assert profile.volatility_band(0.15) == "Orta"
        assert profile.volatility_band(0.40) == "Yüksek"

    def test_an_unmeasured_volatility_has_no_band(self):
        """Ölçülmemiş bir karışımı orta bandda göstermek, olmayan bir ölçümü
        varmış gibi sunmak olurdu."""
        assert profile.volatility_band(None) is None


class TestBindingBand:
    """İki riskin daha temkinli olanı. Ortalama DEĞİL, minimum -- ve
    karşılaştırma etiket sırasına göre, skorlar üzerinde aritmetik yapmadan.
    """

    def test_the_more_cautious_side_binds(self):
        """Belgedeki örnek: ankette "Yüksek", ölçümde "Orta". Daha riskli bir
        hedef vermek yalnızca beyana dayanırdı."""
        assert profile.binding_band("Orta", "Yüksek") == "Orta"

    def test_it_binds_the_other_way_too(self):
        """Tersi durumda beyanı görmezden gelmek olurdu."""
        assert profile.binding_band("Yüksek", "Düşük") == "Düşük"

    def test_agreement_binds_to_itself(self):
        assert profile.binding_band("Orta", "Orta") == "Orta"

    def test_the_fourth_band_can_bind(self):
        assert profile.binding_band("Risksiz", "Yüksek") == "Risksiz"

    def test_a_missing_measurement_leaves_the_declaration_binding(self):
        """Eksik olanı en temkinli saymak, ölçülemeyen bir portföye nakit
        hedefi vermek olurdu."""
        assert profile.binding_band(None, "Orta") == "Orta"

    def test_a_missing_declaration_leaves_the_measurement_binding(self):
        assert profile.binding_band("Yüksek", None) == "Yüksek"

    def test_neither_side_means_no_band(self):
        """Bant yok; çağıran bunu bir hedef YOKLUĞU olarak görmek zorunda."""
        assert profile.binding_band(None, None) is None

    def test_an_unknown_label_is_not_a_band(self):
        assert profile.binding_band("Belirsiz", "Aşırı") is None

    def test_no_arithmetic_is_done_on_the_scores(self):
        """Ölçülen skor ters (100 = sakin), anketin ham puanı değil. İkisi
        arasındaki her işlem er ya da geç ters okunur; fonksiyon skor
        ALMIYOR, yalnızca etiket."""
        import inspect

        signature = inspect.signature(profile.binding_band)
        assert list(signature.parameters) == ["measured_level", "declared_tolerance"]


class TestSuitabilityGate:
    """Kaldırılan yasakların yerine konan İKİNCİ kontrol.

    Test zaten vardı ve dört ürün grubu için kademe gereksinimlerini
    yazıyordu; burada ilk kez bir YETENEĞİ KAPATMAK için kullanılıyor.
    """

    def _declared(self, version="v2", groups=None):
        from types import SimpleNamespace

        return SimpleNamespace(
            questionnaire_version=version,
            product_groups=groups if groups is not None else [
                {"key": "equity", "label": "Hisse", "eligible": True, "reason": "ok"},
            ],
        )

    def test_no_profile_closes_the_gate(self):
        gate = profile.suitability_gate(None)
        assert gate["open"] is False
        assert "uygunluk testini tamamlamanız" in gate["reason"]

    def test_the_v1_questionnaire_does_not_open_it(self):
        """v1 bir RİSK TOLERANSI anketi: ürün grubu başına bilgi ve tecrübe
        beyanı yok, dolayısıyla kademe koşulları hakkında hiçbir şey
        söyleyemiyor."""
        assert profile.suitability_gate(self._declared(version="v1"))["open"] is False

    def test_an_empty_group_list_does_not_open_it(self):
        assert profile.suitability_gate(self._declared(groups=[]))["open"] is False

    def test_a_completed_test_opens_it(self):
        gate = profile.suitability_gate(self._declared())
        assert gate["open"] is True
        assert gate["groups"]["equity"]["eligible"] is True

    def test_an_ineligible_group_keeps_its_own_reason(self):
        """"Uygun değil" tek başına kişi hakkında bir yargı gibi okunur;
        hangi beyandan çıktığı yazılı olunca kullanıcı cevabını
        değiştirebileceğini de görür."""
        gate = profile.suitability_gate(self._declared(groups=[
            {"key": "equity", "label": "Hisse", "eligible": False,
             "reason": "Bu ürünler hakkında beyan ettiğiniz bilgi seviyesi yeterli değil."},
        ]))
        assert gate["groups"]["equity"]["eligible"] is False
        assert "bilgi seviyesi" in gate["groups"]["equity"]["reason"]

    def test_a_group_without_a_key_is_dropped(self):
        gate = profile.suitability_gate(self._declared(groups=[
            {"label": "Anahtarsız", "eligible": True},
            {"key": "equity", "label": "Hisse", "eligible": True, "reason": "ok"},
        ]))
        assert set(gate["groups"]) == {"equity"}

    def test_the_gate_never_raises(self):
        """Kapı REDDETME değil bir DURUM döndürüyor: hata koduyla kapatmak,
        ekranda bir arıza gibi okunurdu -- oysa yapılacak bir şey var."""
        assert profile.suitability_gate(object())["open"] is False
