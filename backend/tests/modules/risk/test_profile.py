"""The derived risk score and its findings.

Everything here replaces a fixture: a score of 68, four invented findings and
a debt-to-income ratio computed from numbers nobody measured. What makes the
replacement worth having is that each output can be traced to a measurement,
so these tests assert the derivation, not just the shape.
"""

from __future__ import annotations

import pytest

from app.modules.risk import profile


def metrics(volatility=0.20, hhi=0.20, drawdown=-0.15, **extra):
    payload = {
        "volatility_annualized": volatility,
        "concentration": {"hhi": hhi, **extra.pop("concentration", {})},
        "max_drawdown": {"value": drawdown} if drawdown is not None else {},
    }
    payload.update(extra)
    return payload


class TestScore:
    def test_a_calm_portfolio_scores_high(self):
        result = profile.score_from(metrics(volatility=0.08, hhi=0.08, drawdown=-0.05))
        assert result["score"] == 100.0
        # Üç bileşenin üçü de tabanının altında: dört bantlı ölçekte bu
        # "Düşük" değil "Risksiz". Ayrım yeniden dengeleme için gerekli --
        # ağırlıklı nakit bir portföye hisse kovası hedefi vermek, ona
        # tutmadığı bir riski önermek olurdu.
        assert result["level"] == "Risksiz"

    def test_a_violent_portfolio_scores_low(self):
        result = profile.score_from(metrics(volatility=0.60, hhi=0.90, drawdown=-0.70))
        assert result["score"] == 0.0
        assert result["level"] == "Yüksek"

    def test_the_score_moves_with_the_measurement(self):
        calm = profile.score_from(metrics(volatility=0.12))["score"]
        wild = profile.score_from(metrics(volatility=0.40))["score"]
        assert wild < calm

    def test_a_single_position_is_maximally_concentrated(self):
        """One holding is an HHI of 1.0, which must not read as diversified."""
        result = profile.score_from(metrics(hhi=1.0))
        concentration = next(c for c in result["components"] if c["name"] == "concentration")
        assert concentration["penalty"] == 1.0

    def test_an_unmeasurable_component_is_excluded_not_zeroed(self):
        """Scoring a missing drawdown as zero would REWARD a portfolio for
        having too little history to judge.

        Volatility and concentration are both pinned at maximum penalty here.
        Renormalised over the two components that COULD be measured, the score
        is 0. Had the missing drawdown counted as a zero penalty, its 20% would
        have been handed over free and the score would read 20.
        """
        result = profile.score_from(
            metrics(volatility=0.45, hhi=0.50, drawdown=None)
        )
        drawdown = next(c for c in result["components"] if c["name"] == "drawdown")
        assert drawdown["penalty"] is None
        assert result["score"] == 0.0

    def test_nothing_measurable_refuses_to_score(self):
        """A default of 50 is a number the user could act on."""
        result = profile.score_from({})
        assert result["score"] is None
        assert result["level"] is None

    def test_every_component_reports_its_raw_measurement(self):
        """A score whose derivation cannot be inspected is the fixture with
        extra steps."""
        result = profile.score_from(metrics(volatility=0.25))
        volatility = next(c for c in result["components"] if c["name"] == "volatility")
        assert volatility["measured"] == pytest.approx(0.25)
        assert volatility["weight"] == profile.WEIGHTS["volatility"]

    def test_weights_sum_to_one_hundred(self):
        assert sum(profile.WEIGHTS.values()) == 100.0

    @pytest.mark.parametrize(
        "score,expected",
        [(100.0, "Risksiz"), (85.0, "Risksiz"), (84.9, "Düşük"), (70.0, "Düşük"),
         (69.9, "Orta"), (55.0, "Orta"), (45.0, "Orta"), (44.9, "Yüksek"),
         (10.0, "Yüksek"), (0.0, "Yüksek")],
    )
    def test_bands(self, score, expected):
        """Eşikler DAHİL: 85 tam olarak "Risksiz", 84,9 değil."""
        assert profile._band(score) == expected

    def test_the_measured_scale_has_four_bands(self):
        assert len(profile.BANDS) == 4
        assert [label for _threshold, label in profile.BANDS] == [
            "Risksiz", "Düşük", "Orta", "Yüksek"]

    def test_the_declared_scale_still_has_three(self):
        """Anket ağırlıkları üç banda göre kalibre edilmiş; dördüncüyü
        eklemek anketin yeniden kalibre edilmesini gerektirirdi."""
        from app.modules.risk import questionnaire

        assert len(questionnaire.TOLERANCE_BANDS) == 3
        assert "Risksiz" not in {label for _t, label in questionnaire.TOLERANCE_BANDS}

    def test_every_band_label_sits_on_the_comparison_axis(self):
        """`suitability()` etiketleri eksendeki SIRALARINA göre
        karşılaştırıyor; eksende olmayan bir etiket sessizce
        "karşılaştırılamaz"a düşerdi."""
        for _threshold, label in profile.BANDS:
            assert label in profile._LEVEL_ORDER


class TestFindings:
    def test_a_concentrated_portfolio_is_flagged_with_its_number(self):
        found = profile.findings_from(
            metrics(concentration={"top_3_weight": 0.66, "effective_n": 3.2}), 11
        )
        top3 = next(f for f in found if f["id"] == "concentration-top3")
        assert top3["impact"] == "negative"
        assert top3["value"] == pytest.approx(0.66)
        assert "%66,0".replace(",", ".") in top3["description"] or "66.0" in top3["description"]

    def test_a_balanced_portfolio_is_reported_positively(self):
        found = profile.findings_from(metrics(concentration={"top_3_weight": 0.30}), 11)
        top3 = next(f for f in found if f["id"] == "concentration-top3")
        assert top3["impact"] == "positive"

    def test_drawdown_names_its_dates(self):
        payload = metrics()
        payload["max_drawdown"] = {
            "value": -0.31, "peak_date": "2026-06-01", "trough_date": "2026-06-25",
        }
        found = profile.findings_from(payload, 5)
        drawdown = next(f for f in found if f["id"] == "max-drawdown")
        assert "2026-06-01" in drawdown["description"]
        assert drawdown["impact"] == "negative"

    def test_single_currency_exposure_is_named(self):
        found = profile.findings_from(
            metrics(concentration={"by_currency": {"TRY": 1.0}}), 8
        )
        assert any(f["id"] == "single-currency" for f in found)

    def test_a_mixed_currency_portfolio_is_not_flagged(self):
        found = profile.findings_from(
            metrics(concentration={"by_currency": {"TRY": 0.6, "USD": 0.4}}), 8
        )
        assert not any(f["id"] == "single-currency" for f in found)

    def test_nothing_measured_produces_no_findings(self):
        assert profile.findings_from({}, 0) == []

    def test_every_finding_carries_the_number_behind_it(self):
        found = profile.findings_from(
            metrics(concentration={"top_3_weight": 0.7, "effective_n": 2.0}), 4
        )
        assert found and all(f["value"] is not None for f in found)


class TestSuggestions:
    def test_a_dominant_position_is_surfaced_by_name(self):
        out = profile.suggestions_from(
            metrics(concentration={
                "top_1_weight": 0.42,
                "largest_position": {"symbol": "NVDA"},
            })
        )
        largest = next(s for s in out if s["id"] == "review-largest")
        assert "NVDA" in largest["title"]
        assert largest["priority"] == "high"

    def test_suggestions_never_tell_the_user_to_trade(self):
        """The non-advisory rule applies here exactly as it does in the chat."""
        out = profile.suggestions_from(
            metrics(concentration={
                "top_1_weight": 0.5,
                "largest_position": {"symbol": "NVDA"},
                "by_sector": {"Technology": 0.8},
            })
        )
        forbidden = ("satın al", "sat ", "azalt", "artır", "öneririz")
        for suggestion in out:
            text = f"{suggestion['title']} {suggestion['description']}".lower()
            assert not any(word in text for word in forbidden), text

    def test_a_dominant_sector_is_surfaced(self):
        out = profile.suggestions_from(
            metrics(concentration={"by_sector": {"Technology": 0.67, "Banking": 0.33}})
        )
        assert any(s["id"] == "sector-weight" for s in out)

    def test_unclassified_is_not_reported_as_a_sector(self):
        """It is the absence of a sector, not a sector."""
        out = profile.suggestions_from(
            metrics(concentration={"by_sector": {"UNCLASSIFIED": 1.0}})
        )
        assert not any(s["id"] == "sector-weight" for s in out)

    def test_excluded_symbols_are_disclosed(self):
        out = profile.suggestions_from(
            metrics(data_quality={"excluded_symbols": ["ARM", "ALAB"]})
        )
        missing = next(s for s in out if s["id"] == "missing-history")
        assert "ARM" in missing["description"]

    def test_a_tidy_portfolio_needs_no_suggestions(self):
        assert profile.suggestions_from(metrics(concentration={"top_1_weight": 0.1})) == []
