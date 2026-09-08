"""Risk tolerans anketi: tanım ve puanlama.

Anketin var olma sebebi, `compliance/rules.py:SUI-001`'in gerekçesiydi:
*"Sistem kullanıcının risk profilini tutmuyor; uygunluk iddiası dayanaksızdır."*
Beyan edilmiş bir tolerans, uygunluğu dayanaksız bir iddiadan kullanıcının
kendi cümlesine çeviriyor. Bu testler o cümlenin doğru üretildiğini koruyor.
"""

from __future__ import annotations

import pytest

from app.modules.risk import questionnaire


def answers(**overrides: str) -> dict[str, str]:
    """Orta bandda duran tam bir cevap seti; testler tek tek saptırır."""
    base = {
        "horizon": "3_5y",
        "drawdown_reaction": "hold",
        "experience": "stocks",
        "liquidity": "maybe",
        "income_stability": "mostly",
        "goal": "balanced",
    }
    base.update(overrides)
    return base


class TestDefinition:
    def test_weights_sum_to_one_hundred(self):
        """Ham puan 0..100'e normalizasyonsuz oturuyor; toplam bozulursa
        bandlar sessizce kayar."""
        assert sum(q.weight for q in questionnaire.QUESTIONS) == 100.0

    def test_every_question_has_at_least_two_options(self):
        for question in questionnaire.QUESTIONS:
            assert len(question.options) >= 2, question.key

    def test_option_points_stay_between_zero_and_one(self):
        for question in questionnaire.QUESTIONS:
            for option in question.options:
                assert 0.0 <= option["points"] <= 1.0, f"{question.key}={option['value']}"

    def test_each_question_offers_both_extremes(self):
        """En temkinli ve en risk alan cevap her soruda seçilebilir olmalı;
        aksi hâlde bandların uçlarına hiç ulaşılamaz."""
        for question in questionnaire.QUESTIONS:
            points = [option["points"] for option in question.options]
            assert min(points) == 0.0, question.key
            assert max(points) == 1.0, question.key

    def test_question_keys_are_unique(self):
        keys = [question.key for question in QUESTIONS_LIST]
        assert len(keys) == len(set(keys))

    def test_loss_tolerance_carries_the_most_weight(self):
        """Ölçümün çıkaramayacağı tek şey bu: bir düşüşü gözlemleyebiliriz,
        o düşüşte kişinin satıp satmayacağını gözlemleyemeyiz."""
        heaviest = max(questionnaire.QUESTIONS, key=lambda q: q.weight)
        assert heaviest.key == "drawdown_reaction"

    def test_payload_carries_the_version_and_hides_the_scoring(self):
        """Puanlar istemciye gitmez: seçeneklerin ağırlığını görmek, anketi
        bir teste çevirir ve insanlar teste cevap verir, kendilerine değil."""
        payload = questionnaire.as_payload()
        assert payload["version"] == questionnaire.VERSION
        assert len(payload["questions"]) == len(questionnaire.QUESTIONS)
        for question in payload["questions"]:
            for option in question["options"]:
                assert set(option) == {"value", "label"}


QUESTIONS_LIST = questionnaire.QUESTIONS


class TestValidation:
    def test_a_complete_answer_set_is_accepted(self):
        assert questionnaire.missing_answers(answers()) == []
        assert questionnaire.unknown_answers(answers()) == []

    def test_missing_questions_are_named(self):
        partial = answers()
        del partial["goal"]
        del partial["liquidity"]
        assert set(questionnaire.missing_answers(partial)) == {"goal", "liquidity"}

    def test_an_unknown_question_is_rejected(self):
        assert questionnaire.unknown_answers({"favourite_colour": "mavi"}) == [
            "favourite_colour"
        ]

    def test_an_unknown_option_is_rejected_with_its_value(self):
        assert questionnaire.unknown_answers({"goal": "moon"}) == ["goal=moon"]


class TestScoring:
    def test_the_most_cautious_answers_score_zero(self):
        scored = questionnaire.score_answers(
            answers(
                horizon="under_1y",
                drawdown_reaction="sell_all",
                experience="none",
                liquidity="immediately",
                income_stability="unstable",
                goal="preserve",
            )
        )
        assert scored["raw_score"] == 0.0
        assert scored["tolerance_level"] == "Düşük"

    def test_the_boldest_answers_score_one_hundred(self):
        scored = questionnaire.score_answers(
            answers(
                horizon="over_5y",
                drawdown_reaction="buy_more",
                experience="derivatives",
                liquidity="no",
                income_stability="stable",
                goal="growth",
            )
        )
        assert scored["raw_score"] == 100.0
        assert scored["tolerance_level"] == "Yüksek"

    def test_the_score_moves_monotonically(self):
        cautious = questionnaire.score_answers(answers(drawdown_reaction="sell_all"))
        bold = questionnaire.score_answers(answers(drawdown_reaction="buy_more"))
        assert bold["raw_score"] > cautious["raw_score"]

    @pytest.mark.parametrize(
        "raw_answers,expected",
        [
            (dict(drawdown_reaction="sell_all", horizon="under_1y", experience="none",
                  liquidity="immediately", income_stability="unstable", goal="preserve"), "Düşük"),
            (dict(), "Orta"),
            (dict(drawdown_reaction="buy_more", horizon="over_5y", experience="derivatives",
                  liquidity="no", income_stability="stable", goal="growth"), "Yüksek"),
        ],
    )
    def test_bands(self, raw_answers, expected):
        assert questionnaire.score_answers(answers(**raw_answers))["tolerance_level"] == expected

    def test_every_tolerance_label_exists_on_the_measured_axis(self):
        """Karşılaştırma etiket üzerinden yapılıyor; beyan edilen bir etiketin
        ölçülen eksende karşılığı yoksa kıyaslanacak bir şey kalmaz.

        İki küme artık EŞİT DEĞİL, kapsanıyor: ölçülen taraf dördüncü bir
        bant kazandı (`Risksiz`), beyan edilen taraf üç bantta kaldı ve öyle
        kalması gerekiyor -- anket ağırlıkları o üç banda göre kalibre
        edilmiş. Karşılaştırma için gereken şey eşitlik değil, ortak eksen."""
        from app.modules.risk import profile

        measured_labels = {label for _, label in profile.BANDS}
        assert set(questionnaire.TOLERANCE_LEVELS) < measured_labels
        # `profile` anketi import ETMİYOR, kümeyi kendi yazıyor; ayrışırlarsa
        # beyan edilen geçerli bir etiket "karşılaştırılamaz"a düşerdi.
        assert set(questionnaire.TOLERANCE_LEVELS) == set(profile._DECLARABLE_LEVELS)

    def test_the_horizon_is_carried_separately_and_in_turkish(self):
        """Vade toleranstan ayrı: biri dalgalanmaya dayanma isteğini, diğeri
        parayı ne zaman isteyeceğini söylüyor."""
        scored = questionnaire.score_answers(answers(horizon="under_1y"))
        assert scored["investment_horizon"] == "1 yıldan kısa"

    def test_the_version_travels_with_the_score(self):
        assert questionnaire.score_answers(answers())["version"] == questionnaire.VERSION
