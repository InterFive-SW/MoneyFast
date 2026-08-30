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
