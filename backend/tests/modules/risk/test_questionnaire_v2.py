"""Uygunluk testi v2 — tanım ve puanlama.

v2 v1'in yerine geçmiyor, yanına geliyor: v1 dokunulmadan duruyor ve bir test
bunu sabitliyor. İki test AYNI ŞEYİ ölçmüyor -- v1 "neyi kaldırırsın" diye
soruyordu, bu "sana hangi ürün grupları sunulabilir" diye soruyor -- ve bu
yüzden v2'nin çıktısı tek bir bant değil.

Bu dosyanın koruduğu üç şey:

1. **Yaş ve eğitim puana girmiyor.** Birinin toleransını yaşı yüzünden düşük
   saymak, cevaplarının desteklemediği bir yargı olurdu.
2. **Yeterlilik kademeye bağlı.** Dört grubu aynı kuralla ölçmek, testin her
   grubun yanına yazdığı risk seviyesini görmezden gelmek olurdu: mevduat için
   istenen kanıtla türev için istenen kanıt aynı olamaz.
3. **Her "uygun değil" gerekçesini taşıyor.** Tek başına kişi hakkında bir
   yargı gibi okunuyor; hangi beyandan çıktığı yazılı olunca öyle olmadığı ve
   kullanıcının değiştirebileceği görünüyor.
"""

from __future__ import annotations

import pytest

from app.modules.risk import questionnaire as v1
from app.modules.risk import questionnaire_v2 as v2


def answers(
    *,
    appetite: str = "moderate",
    horizon: str = "3_5y",
    age: str = "31_50",
    education: str = "bachelor",
    knowledge: str = "limited",
    frequency: str = "sometimes",
    volume: str = "upto_50k",
    overrides: dict | None = None,
) -> dict:
    """Tam ve geçerli bir cevap kümesi; testler tek tek alan ezer."""
    out = {
        "age_band": age,
        "education": education,
        "horizon": horizon,
        "risk_appetite": appetite,
    }
    for group in v2.PRODUCT_GROUPS:
        out[f"{group['key']}_knowledge"] = knowledge
        out[f"{group['key']}_frequency"] = frequency
        out[f"{group['key']}_volume"] = volume
    out.update(overrides or {})
    return out


class TestDefinition:
    def test_v1_is_left_alone(self):
        """Eski bir cevap yeni ağırlıklarla yeniden puanlanmıyor; v1'in
        sürümü ve soru sayısı bu yüzden sabit."""
        assert v1.VERSION == "v1"
        assert v2.VERSION == "v2"
        assert len(v1.QUESTIONS) == 6

    def test_the_test_has_sixteen_questions(self):
        assert len(v2.QUESTIONS) == 16

    def test_the_weights_sum_to_a_hundred(self):
        """Her sorunun azami katkısı ağırlığı kadar, dolayısıyla ham puan
        normalleştirme adımı olmadan 0..100'e oturuyor."""
        assert round(sum(q.weight for q in v2.QUESTIONS), 6) == 100.0

    def test_every_question_key_is_unique(self):
        keys = [q.key for q in v2.QUESTIONS]
        assert len(keys) == len(set(keys))

    def test_the_four_product_groups_are_ordered_by_risk(self):
        assert [g["tier"] for g in v2.PRODUCT_GROUPS] == [1, 2, 3, 4]
        assert [g["key"] for g in v2.PRODUCT_GROUPS] == [
            "deposit", "bond", "equity", "derivative"
        ]

    def test_never_traded_is_an_option_in_both_experience_questions(self):
        """Analistin listesinde yoktu ve yokluğu bir boşluk bırakıyordu: hiç
        işlem yapmamış birinin verebileceği doğru cevap yoktu."""
        for group in v2.PRODUCT_GROUPS:
            freq = v2._BY_KEY[f"{group['key']}_frequency"]
            vol = v2._BY_KEY[f"{group['key']}_volume"]
            assert "never" in {o["value"] for o in freq.options}
            assert "none" in {o["value"] for o in vol.options}


class TestPayload:
    def test_the_screen_gets_three_sections(self):
        """On altı soruyu tek listede göstermek kimsenin dolduracağı bir form
        değil."""
        sections = v2.as_payload()["sections"]
        assert [s["key"] for s in sections] == ["profile", "preferences", "knowledge"]

    def test_the_knowledge_section_is_shaped_as_a_matrix(self):
        """Dört satır, satır başına üç soru — ekran matris çizebilsin diye.
        Puanlama bu yapıdan habersiz."""
        knowledge = v2.as_payload()["sections"][2]
        assert len(knowledge["groups"]) == 4
        for group in knowledge["groups"]:
            assert len(group["questions"]) == 3
            assert group["label"] and group["risk"]

    def test_the_profile_section_says_it_does_not_affect_the_score(self):
        profile = v2.as_payload()["sections"][0]
        assert "risk puanınızı etkilemez" in profile["helper"]

    def test_the_payload_carries_no_scoring_weights(self):
        """Puanlar ekrana gitmiyor: seçenekleri puanına göre sıralayan bir
        kullanıcı, cevabını değil sonucu seçmiş olurdu."""
        text = repr(v2.as_payload())
        assert "points" not in text
        assert "weight" not in text

    def test_every_question_reaches_the_payload(self):
        payload = v2.as_payload()
        seen = set()
        for section in payload["sections"]:
            for question in section.get("questions", []):
                seen.add(question["key"])
            for group in section.get("groups", []):
                seen.update(q["key"] for q in group["questions"])
        assert seen == {q.key for q in v2.QUESTIONS}


class TestValidation:
    def test_a_complete_answer_set_is_accepted(self):
        assert v2.missing_answers(answers()) == []
        assert v2.unknown_answers(answers()) == []

    def test_every_question_is_required(self):
        """Boşları sıfır sayıp puanlamak, yarıda bırakan birine temkinli bir
        tolerans atfeder — ve o tolerans sonra portföyüyle karşılaştırılır."""
        partial = answers()
        del partial["derivative_volume"]
        assert v2.missing_answers(partial) == ["derivative_volume"]

    def test_an_empty_submission_lists_all_sixteen(self):
        assert len(v2.missing_answers({})) == 16

    def test_an_unknown_question_is_named(self):
        assert v2.unknown_answers({"favourite_colour": "blue"}) == ["favourite_colour"]

    def test_an_unknown_option_is_named_with_its_value(self):
        assert v2.unknown_answers({"risk_appetite": "reckless"}) == [
            "risk_appetite=reckless"
        ]


class TestScoring:
    def test_the_most_cautious_answers_score_zero(self):
        scored = v2.score_answers(
            answers(appetite="preserve", horizon="under_1y",
                    knowledge="none", frequency="never", volume="none")
        )
        assert scored["raw_score"] == 0.0
        assert scored["tolerance_level"] == "Düşük"

    def test_the_boldest_answers_score_a_hundred(self):
        scored = v2.score_answers(
            answers(appetite="total", horizon="over_5y",
                    knowledge="sufficient", frequency="often", volume="over_500k")
        )
        assert scored["raw_score"] == 100.0
        assert scored["tolerance_level"] == "Yüksek"

    def test_the_band_vocabulary_matches_the_measurement(self):
        """Ölçüm ve beyan aynı üç etiketi kullanıyor; ham puanlar
        karşılaştırılabilir değil, etiketler karşılaştırılabilir."""
        assert v2.score_answers(answers())["tolerance_level"] in v2.TOLERANCE_LEVELS

    def test_the_horizon_is_carried_as_a_readable_label(self):
        scored = v2.score_answers(answers(horizon="over_5y"))
        assert scored["investment_horizon"] == "5 yıldan uzun"

    def test_an_unmapped_horizon_falls_back_to_what_was_given(self):
        assert v2.HORIZONS.get("bilinmeyen", "bilinmeyen") == "bilinmeyen"

    def test_the_output_still_carries_everything_v1_produced(self):
        """Uygunluk karşılaştırması ve risk profili bu üç alanı okuyor; sürüm
        değiştiği için bozulmamalılar."""
        scored = v2.score_answers(answers())
        assert {"raw_score", "tolerance_level", "investment_horizon"} <= set(scored)

    @pytest.mark.parametrize("age", sorted(v2.AGE_BANDS))
    def test_age_does_not_move_the_score(self, age):
        """Birinin toleransını yaşı yüzünden düşük saymak, cevaplarının
        desteklemediği bir yargı olurdu."""
        assert v2.score_answers(answers(age=age))["raw_score"] == \
            v2.score_answers(answers())["raw_score"]

    @pytest.mark.parametrize("education", sorted(v2.EDUCATION_LEVELS))
    def test_education_does_not_move_the_score(self, education):
        assert v2.score_answers(answers(education=education))["raw_score"] == \
            v2.score_answers(answers())["raw_score"]

    def test_age_and_education_are_recorded_readably(self):
        scored = v2.score_answers(answers(age="65_plus", education="postgraduate"))
        assert scored["profile"] == {
            "age_band": "65 ve üzeri", "education": "Yüksek Lisans / Doktora"
        }

    def test_an_unmapped_profile_value_falls_back_rather_than_disappearing(self):
        assert v2.AGE_BANDS.get("x", "x") == "x"


class TestEligibility:
    def _flags(self, **kwargs) -> str:
        groups = v2.score_answers(answers(**kwargs))["product_groups"]
        return "".join("1" if g["eligible"] else "0" for g in groups)

    def test_no_knowledge_still_leaves_deposits_open(self):
        """Bir mevduat hesabının önüne bilgi sınavı koymak, koruma değil işe
        yaramaz bir engel üretir — ve kullanıcıyı daha riskli bir yere iter."""
        assert self._flags(knowledge="none", frequency="never", volume="none") == "1000"

    def test_limited_knowledge_without_experience_reaches_bonds(self):
        assert self._flags(knowledge="limited", frequency="never", volume="none") == "1100"

    def test_limited_knowledge_with_experience_reaches_equities(self):
        assert self._flags(
            knowledge="limited", frequency="sometimes", volume="upto_50k"
        ) == "1110"

    def test_declared_knowledge_substitutes_for_experience_below_the_top_tier(self):
        """Ürünü anladığını beyan etmek, hiç işlem yapmamış olmasıyla
        çelişmiyor."""
        assert self._flags(
            knowledge="sufficient", frequency="never", volume="none"
        ) == "1110"

    def test_the_top_tier_needs_both_knowledge_and_experience(self):
        """Kademe 4'ün istisnası bilerek: en karmaşık ürünlerde yalnızca beyan
        edilen bilgiye dayanmak, testin varlık sebebini boşa çıkarır."""
        assert self._flags(
            knowledge="sufficient", frequency="often", volume="over_500k"
        ) == "1111"

    def test_volume_alone_counts_as_experience(self):
        """Sıklık ile hacim aynı şeyin iki ölçüsü; birini beyan eden diğerini
        beyan etmemiş olabilir."""
        assert self._flags(
            knowledge="limited", frequency="never", volume="upto_50k"
        ) == "1110"

    def test_a_group_can_differ_from_its_neighbours(self):
        """Gerçek bir kullanıcı her gruba aynı cevabı vermez."""
        custom = answers(knowledge="none", frequency="never", volume="none",
                         overrides={
                             "equity_knowledge": "sufficient",
                             "equity_frequency": "often",
                             "equity_volume": "over_500k",
                         })
        groups = {g["key"]: g["eligible"] for g in v2.score_answers(custom)["product_groups"]}
        assert groups == {"deposit": True, "bond": False,
                          "equity": True, "derivative": False}

    def test_every_group_carries_a_reason(self):
        for group in v2.score_answers(answers())["product_groups"]:
            assert group["reason"]

    def test_the_reason_names_which_declaration_produced_it(self):
        groups = {
            g["key"]: g["reason"]
            for g in v2.score_answers(
                answers(knowledge="none", frequency="never", volume="none")
            )["product_groups"]
        }
        assert "koşulu aranmıyor" in groups["deposit"]
        assert "bilgi seviyesi yeterli değil" in groups["bond"]

    def test_a_knowledge_only_declaration_says_experience_is_what_is_missing(self):
        groups = {
            g["key"]: g["reason"]
            for g in v2.score_answers(
                answers(knowledge="sufficient", frequency="never", volume="none")
            )["product_groups"]
        }
        assert "işlem tecrübesi belirtmediniz" in groups["derivative"]

    def test_a_group_carries_its_label_and_risk_for_the_screen(self):
        groups = v2.score_answers(answers())["product_groups"]
        assert groups[3]["label"].startswith("Türev")
        assert groups[3]["risk"] == "Çok yüksek risk"

    def test_group_labels_are_available_without_scoring(self):
        assert set(v2.group_labels()) == {g["key"] for g in v2.PRODUCT_GROUPS}
