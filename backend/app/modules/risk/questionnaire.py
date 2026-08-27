"""Risk tolerance questionnaire — definition and scoring.

Why this exists at all: `compliance/rules.py` blocks the phrase "risk
profilinize uygun" with the reason *"Sistem kullanıcının risk profilini
tutmuyor; uygunluk iddiası dayanaksızdır."* That reason was correct. Without a
declared tolerance, every suitability statement the product could make was an
assertion about the user that nobody had asked them.

The questionnaire changes what kind of claim is available. It does NOT let the
system decide what suits someone — it lets the USER say what they will
tolerate, after which comparing that answer against a measurement is a
statement of fact rather than a judgement. "Ölçülen riskiniz Yüksek, beyan
ettiğiniz tolerans Orta" describes two things that are both true; it does not
tell anyone what to do about it.

Pure functions only. No database, no session, no I/O — the store handles that.
Kept separate so the scoring can be tested against hand-written answers and so
a future questionnaire version can live beside this one rather than replacing
it in place.
"""

from typing import Any, Dict, List, Optional

#: Bumped whenever a question, an option, or a weight changes. Stored on every
#: assessment row so an old answer is never re-scored under new rules -- the
#: score someone saw is the score that stays on their record.
VERSION = "v1"

#: The three-label scale, shared with `profile.BANDS`.
#:
#: Deliberately the SAME vocabulary the measurement uses. The measured score is
#: inverted (100 = calm) and the questionnaire's raw score is not, so putting
#: the two numbers side by side would invite exactly the wrong reading. On the
#: label scale the comparison needs no arithmetic and cannot be misread.
TOLERANCE_LEVELS = ("Düşük", "Orta", "Yüksek")

#: Raw score -> declared tolerance. Thresholds, high to low.
TOLERANCE_BANDS = ((67.0, "Yüksek"), (34.0, "Orta"), (0.0, "Düşük"))

#: Horizon is carried separately from the tolerance score because it answers a
#: different question. Someone can be comfortable with volatility and still
#: need the money in six months; the two constrain different things.
HORIZONS = {
    "under_1y": "1 yıldan kısa",
    "1_3y": "1-3 yıl",
    "3_5y": "3-5 yıl",
    "over_5y": "5 yıldan uzun",
}


class Question:
    """One question, its options, and what each option contributes.

    `weight` is how much this question moves the total; `points` is 0..1 per
    option. Every question's maximum contribution is its weight, so the raw
    score lands on 0..100 without a normalisation step to get wrong.
    """

    def __init__(
        self,
        key: str,
        prompt: str,
        weight: float,
        options: List[Dict[str, Any]],
        helper: Optional[str] = None,
    ) -> None:
        self.key = key
        self.prompt = prompt
        self.weight = weight
        self.options = options
        self.helper = helper


#: Six questions. Weights sum to 100.
#:
#: Loss tolerance carries the most because it is the one thing a measurement
#: cannot infer: a portfolio's drawdown is observable, but whether the person
#: holding it would have sold at the bottom is not.
QUESTIONS: List[Question] = [
    Question(
        key="horizon",
        prompt="Bu parayı ne zaman kullanmayı planlıyorsunuz?",
        helper="Kısa vade, dalgalanmayı bekleyebilme imkânını doğrudan sınırlar.",
        weight=20.0,
        options=[
            {"value": "under_1y", "label": "1 yıldan kısa sürede", "points": 0.0},
            {"value": "1_3y", "label": "1-3 yıl içinde", "points": 0.35},
            {"value": "3_5y", "label": "3-5 yıl içinde", "points": 0.7},
            {"value": "over_5y", "label": "5 yıldan uzun bir süre sonra", "points": 1.0},
        ],
    ),
    Question(
        key="drawdown_reaction",
        prompt="Portföyünüz bir yıl içinde %30 değer kaybetse ne yapardınız?",
        helper="Geçmiş bir düşüşü ölçebiliriz; o düşüşte ne hissedeceğinizi ölçemeyiz.",
        weight=30.0,
        options=[
            {"value": "sell_all", "label": "Tamamını satardım", "points": 0.0},
            {"value": "sell_some", "label": "Bir kısmını satardım", "points": 0.3},
            {"value": "hold", "label": "Bekler, hiçbir şey yapmazdım", "points": 0.7},
            {"value": "buy_more", "label": "Daha fazla alırdım", "points": 1.0},
        ],
    ),
    Question(
        key="experience",
        prompt="Yatırım konusundaki deneyiminiz nedir?",
        weight=15.0,
        options=[
            {"value": "none", "label": "Hiç yatırım yapmadım", "points": 0.0},
            {"value": "basic", "label": "Mevduat ve fon düzeyinde", "points": 0.35},
            {"value": "stocks", "label": "Hisse senedi alıp sattım", "points": 0.7},
            {"value": "derivatives", "label": "Türev ve kaldıraçlı ürünler dâhil", "points": 1.0},
        ],
    ),
    Question(
        key="liquidity",
        prompt="Beklenmedik bir gider çıksa, bu paraya dokunmak zorunda kalır mıydınız?",
        helper="Acil durum ihtiyacı, en kötü anda satmak zorunda kalma riskidir.",
        weight=15.0,
        options=[
            {"value": "immediately", "label": "Evet, hemen", "points": 0.0},
            {"value": "maybe", "label": "Kısmen, bir bölümüne", "points": 0.4},
            {"value": "no", "label": "Hayır, ayrı bir acil durum birikimim var", "points": 1.0},
        ],
    ),
    Question(
        key="income_stability",
        prompt="Düzenli geliriniz ne kadar öngörülebilir?",
        weight=10.0,
        options=[
            {"value": "unstable", "label": "Değişken, öngörmesi zor", "points": 0.0},
            {"value": "mostly", "label": "Çoğunlukla düzenli", "points": 0.5},
            {"value": "stable", "label": "Düzenli ve istikrarlı", "points": 1.0},
        ],
    ),
    Question(
        key="goal",
        prompt="Bu yatırımdaki birincil önceliğiniz nedir?",
        weight=10.0,
        options=[
            {"value": "preserve", "label": "Anaparayı korumak", "points": 0.0},
            {"value": "balanced", "label": "Dengeli büyümek", "points": 0.5},
            {"value": "growth", "label": "Mümkün olan en yüksek büyüme", "points": 1.0},
        ],
    ),
]

_BY_KEY = {question.key: question for question in QUESTIONS}


def as_payload() -> Dict[str, Any]:
    """The questionnaire, shaped for the screen."""
    return {
        "version": VERSION,
        "questions": [
            {
                "key": question.key,
                "prompt": question.prompt,
                "helper": question.helper,
                "options": [
                    {"value": option["value"], "label": option["label"]}
                    for option in question.options
                ],
            }
            for question in QUESTIONS
        ],
    }


def missing_answers(answers: Dict[str, str]) -> List[str]:
    """Question keys the caller did not answer.

    Every question is required. A partial questionnaire scored as though the
    blanks were zeros would report a cautious tolerance for someone who simply
    stopped halfway, and that answer would then be compared against their
    portfolio as if they had given it.
    """
    return [question.key for question in QUESTIONS if question.key not in answers]


def unknown_answers(answers: Dict[str, str]) -> List[str]:
    """Answers naming a question or an option that does not exist."""
    bad: List[str] = []
    for key, value in answers.items():
        question = _BY_KEY.get(key)
        if question is None:
            bad.append(key)
            continue
        if value not in {option["value"] for option in question.options}:
            bad.append(f"{key}={value}")
    return bad


def _band(raw_score: float) -> str:
    for threshold, label in TOLERANCE_BANDS:
        if raw_score >= threshold:
            return label
    return TOLERANCE_BANDS[-1][1]  # pragma: no cover - the last band starts at zero


def score_answers(answers: Dict[str, str]) -> Dict[str, Any]:
    """Turn answers into a raw 0..100 score and a declared tolerance.

    Assumes the answers are complete and valid; the router validates first so
    a partial submission is rejected rather than silently scored.
    """
    total = 0.0
    for question in QUESTIONS:
        chosen = answers[question.key]
        points = next(
            option["points"] for option in question.options if option["value"] == chosen
        )
        total += question.weight * float(points)

    raw = round(total, 1)
    return {
        "version": VERSION,
        "raw_score": raw,
        "tolerance_level": _band(raw),
        "investment_horizon": HORIZONS.get(answers["horizon"], answers["horizon"]),
    }
