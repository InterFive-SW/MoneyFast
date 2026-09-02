"""Uygunluk testi v2 — tanımı ve puanlaması.

v1'in YERİNE geçmiyor, YANINA geliyor. `questionnaire.py` dokunulmadan
duruyor, çünkü her değerlendirme satırı hangi sürümle puanlandığını taşıyor ve
eski bir cevap yeni ağırlıklarla yeniden puanlanmıyor -- birinin gördüğü puan,
kaydında kalan puandır.

**v1 ile aynı şeyi ölçmüyor.** v1 bir risk TOLERANSI anketiydi: "neyi
kaldırırsın". Bu bir UYGUNLUK testi ve amacı farklı -- mevzuatın sorduğu soru
"bu kişiye hangi ürün grupları sunulabilir". Bu yüzden çıktısı tek bir bant
değil: bant da var, ama yanında ürün grubu başına bir yeterlilik var.

ÜÇ BÖLÜM, ÜÇ FARKLI İŞ:

1. *Müşteri profili* (yaş, eğitim). Kayda geçer, PUANA GİRMEZ. Birinin
   toleransını yaşı yüzünden düşük saymak, cevaplarının desteklemediği bir
   yargıdır; testin bu alanlar için söylediği amaç da zaten kapasite bağlamı,
   tolerans değil. Puanlanmaları istenirse ağırlık eklemek tek satır -- ama o
   karar analistin, kodun değil.
2. *Yatırım tercihleri*. Bandı esas olarak bu belirliyor.
3. *Bilgi ve tecrübe*, ürün grubu başına üç soru. Hem bandı besliyor hem de
   grup başına yeterliliği üretiyor.

YETERLİLİK BİR YARGI DEĞİL. "Türev ürünler size uygun değil" cümlesi kişi
hakkında bir görüş gibi okunabilir; değil. Kullanıcının KENDİ beyanına yazılı
bir kural uygulanıyor: bilgisi olmadığını söyleyen birine o grup uygun
sayılmıyor. Kural aşağıda açıkça duruyor ki gözden geçirilebilsin.
"""

from typing import Any, Dict, List, Optional

from .questionnaire import HORIZONS, TOLERANCE_BANDS, TOLERANCE_LEVELS, Question

VERSION = "v2"

#: Yaş aralıkları. Kayıt amaçlı; puana girmiyor.
AGE_BANDS = {
    "18_30": "18 - 30",
    "31_50": "31 - 50",
    "51_65": "51 - 65",
    "65_plus": "65 ve üzeri",
}

#: Eğitim durumu. Kayıt amaçlı; puana girmiyor.
EDUCATION_LEVELS = {
    "primary": "İlköğretim",
    "high_school": "Lise",
    "bachelor": "Ön Lisans / Lisans",
    "postgraduate": "Yüksek Lisans / Doktora",
}

#: Testin sorduğu dört ürün grubu, risk sırasına göre. Anahtar kısa tutuldu:
#: cevap satırlarında `deposit_knowledge` gibi anahtarlar üretiyor ve bunlar
#: JSONB'de saklandığı için okunabilir olmaları gerekiyor.
PRODUCT_GROUPS: List[Dict[str, Any]] = [
    {
        "key": "deposit",
        "label": "Mevduat, Repo-Ters Repo, BPP",
        "risk": "Çok düşük risk",
        "tier": 1,
    },
    {
        "key": "bond",
        "label": "Hazine Bonosu, Devlet Tahvili, Kira Sertifikaları",
        "risk": "Düşük risk",
        "tier": 2,
    },
    {
        "key": "equity",
        "label": "Ortaklık Payı (Hisse Senedi), Eurobond, Dövizli Tahviller",
        "risk": "Orta / yüksek risk",
        "tier": 3,
    },
    {
        "key": "derivative",
        "label": "Türev İşlemler, Varant, Yatırım Kuruluşu Sertifikası",
        "risk": "Çok yüksek risk",
        "tier": 4,
    },
]

#: Grup başına üç soru. Metin her grupta aynı; değişen yalnızca hangi ürünler
#: hakkında sorulduğu, o da grubun kendi etiketinde yazılı.
_GROUP_QUESTIONS = [
    {
        "suffix": "knowledge",
        "prompt": "Bu ürünler hakkında bilgi seviyeniz nedir?",
        "options": [
            {"value": "none", "label": "Bilgim yok", "points": 0.0},
            {"value": "limited", "label": "Kısıtlı", "points": 0.5},
            {"value": "sufficient", "label": "Yeterince bilgim var", "points": 1.0},
        ],
    },
    {
        "suffix": "frequency",
        "prompt": "Ne sıklıkla bu ürünlerde işlem yapıyorsunuz?",
        "options": [
            {"value": "never", "label": "Hiç", "points": 0.0},
            {"value": "rarely", "label": "Nadiren (yılda birkaç)", "points": 0.4},
            {"value": "sometimes", "label": "Ara sıra (ayda birkaç)", "points": 0.7},
            {"value": "often", "label": "Sıklıkla (haftada birkaç)", "points": 1.0},
        ],
    },
    {
        "suffix": "volume",
        "prompt": "Geçmiş bir yılda bu ürünlerdeki işlem hacminiz ne kadardır?",
        "options": [
            {"value": "none", "label": "İşlem yapmadım", "points": 0.0},
            {"value": "upto_50k", "label": "1 - 50.000 TL", "points": 0.4},
            {"value": "upto_500k", "label": "50.001 - 500.000 TL", "points": 0.7},
            {"value": "over_500k", "label": "500.001 TL ve üzeri", "points": 1.0},
        ],
    },
]

#: Analistin listesinde olmayan iki seçenek EKLENDİ: sıklıkta "Hiç" ve hacimde
#: "İşlem yapmadım". Listede yoklardı ve yoklukları bir boşluk bırakıyordu --
#: hiç işlem yapmamış birinin verebileceği doğru cevap yoktu ve "yılda birkaç"
#: demek zorunda kalıyordu. Beyanı olmayan bir tecrübeyi var saymak, testin
#: bütün amacını tersine çevirir.
NEVER_TRADED = {"frequency": "never", "volume": "none"}


def _group_key(group: str, suffix: str) -> str:
    return f"{group}_{suffix}"


def _build_questions() -> List[Question]:
    """Testin tamamı, düz bir soru listesi olarak.

    Bölümler ve matris YALNIZCA sunum meselesi; puanlama düz liste üzerinden
    çalışıyor. İç içe bir yapıyı puanlamak, ekranın düzenini puanlamanın
    içine taşımak olurdu.
    """
    questions: List[Question] = [
        Question(
            key="age_band",
            prompt="Yaşınız",
            weight=0.0,
            options=[
                {"value": key, "label": label, "points": 0.0}
                for key, label in AGE_BANDS.items()
            ],
        ),
        Question(
            key="education",
            prompt="Eğitim durumunuz",
            weight=0.0,
            options=[
                {"value": key, "label": label, "points": 0.0}
                for key, label in EDUCATION_LEVELS.items()
            ],
        ),
        Question(
            key="horizon",
            prompt="Yatırımlarınızı genellikle hangi vadede değerlendirirsiniz?",
            helper="Kısa vade, dalgalanmayı bekleyebilme imkânını doğrudan sınırlar.",
            weight=20.0,
            options=[
                {"value": "under_1y", "label": "Kısa vade (0-6 ay)", "points": 0.0},
                {"value": "1_3y", "label": "Orta vade (6-12 ay)", "points": 0.35},
                {"value": "3_5y", "label": "Uzun vade (1-3 yıl)", "points": 0.7},
                {"value": "over_5y", "label": "Daha uzun vade (3+ yıl)", "points": 1.0},
            ],
        ),
        Question(
            key="risk_appetite",
            prompt=(
                "Yatırım kararı verirken risk ve getiri beklentiniz açısından "
                "sizi en çok hangi seçenek ifade eder?"
            ),
            helper="Bir düşüşü ölçebiliriz; o düşüşte ne hissedeceğinizi ölçemeyiz.",
            weight=50.0,
            options=[
                {"value": "preserve", "points": 0.0,
                 "label": "Anapara aynen korunsun isterim (sadece risksiz ürünler)"},
                {"value": "minimal", "points": 0.25,
                 "label": "Anaparadan çok az kaybedebilirim (düşük risk / düşük getiri)"},
                {"value": "moderate", "points": 0.5,
                 "label": "Anaparadan biraz kaybedebilirim (orta risk / orta getiri)"},
                {"value": "high", "points": 0.75,
                 "label": "Anaparadan çok kaybedebilirim (yüksek risk / yüksek getiri)"},
                {"value": "total", "points": 1.0,
                 "label": "Anaparayı tamamen kaybedebilirim (çok yüksek risk / çok yüksek getiri)"},
            ],
        ),
    ]

    # Bilgi ve tecrübe bölümü bandın %30'unu taşıyor, on iki soruya eşit
    # dağıtılmış. Tek bir grubun tek bir sorusunun bandı sürüklememesi için:
    # türevde "sıklıkla işlem yaparım" demek tek başına yüksek tolerans
    # değildir, ve mevduatta "bilgim yok" demek tek başına düşük tolerans
    # değildir.
    per_question = 30.0 / (len(PRODUCT_GROUPS) * len(_GROUP_QUESTIONS))
    for group in PRODUCT_GROUPS:
        for template in _GROUP_QUESTIONS:
            questions.append(
                Question(
                    key=_group_key(group["key"], template["suffix"]),
                    prompt=template["prompt"],
                    weight=per_question,
                    options=[dict(option) for option in template["options"]],
                )
            )
    return questions


QUESTIONS: List[Question] = _build_questions()

_BY_KEY = {question.key: question for question in QUESTIONS}


def as_payload() -> Dict[str, Any]:
    """Test, ekranın kurabileceği biçimde.

    Bölümlü, çünkü on altı soruyu tek bir listede göstermek kimsenin
    dolduracağı bir form değil. Üçüncü bölüm ayrıca `groups` taşıyor: dört
    satır, satır başına üç soru -- ekran bunu bir matris olarak çizebilsin
    diye. Puanlama bu yapıdan habersiz.
    """
    def render(question: Question) -> Dict[str, Any]:
        return {
            "key": question.key,
            "prompt": question.prompt,
            "helper": question.helper,
            "options": [
                {"value": option["value"], "label": option["label"]}
                for option in question.options
            ],
        }

    return {
        "version": VERSION,
        "sections": [
            {
                "key": "profile",
                "title": "Müşteri profili",
                "helper": "Kayda geçer; risk puanınızı etkilemez.",
                "questions": [render(_BY_KEY["age_band"]), render(_BY_KEY["education"])],
            },
            {
                "key": "preferences",
                "title": "Yatırım tercihleri",
                "questions": [
                    render(_BY_KEY["horizon"]),
                    render(_BY_KEY["risk_appetite"]),
                ],
            },
            {
                "key": "knowledge",
                "title": "Bilgi ve tecrübe",
                "helper": "Her ürün grubu için üç soru.",
                "groups": [
                    {
                        "key": group["key"],
                        "label": group["label"],
                        "risk": group["risk"],
                        "questions": [
                            render(_BY_KEY[_group_key(group["key"], template["suffix"])])
                            for template in _GROUP_QUESTIONS
                        ],
                    }
                    for group in PRODUCT_GROUPS
                ],
            },
        ],
    }


def missing_answers(answers: Dict[str, str]) -> List[str]:
    """Cevaplanmamış soruların anahtarları. Hepsi zorunlu.

    Boşları sıfır sayıp puanlamak, yarıda bırakan birine temkinli bir tolerans
    atfeder -- ve o tolerans sonra portföyüyle karşılaştırılır.
    """
    return [question.key for question in QUESTIONS if question.key not in answers]


def unknown_answers(answers: Dict[str, str]) -> List[str]:
    """Var olmayan bir soruyu ya da seçeneği adlandıran cevaplar."""
    bad: List[str] = []
    for key, value in answers.items():
        question = _BY_KEY.get(key)
        if question is None:
            bad.append(key)
            continue
        if value not in {option["value"] for option in question.options}:
            bad.append(f"{key}={value}")
    return bad


def _points(key: str, value: str) -> float:
    question = _BY_KEY[key]
    return float(
        next(option["points"] for option in question.options if option["value"] == value)
    )


def _band(raw_score: float) -> str:
    for threshold, label in TOLERANCE_BANDS:
        if raw_score >= threshold:
            return label
    return TOLERANCE_BANDS[-1][1]  # pragma: no cover - son bant sıfırdan başlıyor


#: Kademe başına ne aranıyor. Dört grubu aynı kuralla ölçmek, testin kendi
#: verdiği bilgiyi -- her grubun yanında yazan risk seviyesini -- görmezden
#: gelmek olurdu: mevduat için istenen kanıtla türev için istenen kanıt aynı
#: olamaz.
#:
#: Kademe 1 (mevduat, repo): koşul YOK. Bir mevduat hesabının önüne bilgi
#: sınavı koymak, testin amaçladığı korumayı değil, işe yaramaz bir engel
#: üretir -- ve "bilgim yok" diyen birine mevduatı kapatmak, onu daha riskli
#: bir yere itmekten başka bir şey yapmaz.
#: Kademe 2 (tahvil, bono): en az kısıtlı bilgi.
#: Kademe 3 (hisse, Eurobond): kısıtlı bilgi + tecrübe, ya da yeterli bilgi.
#: Kademe 4 (türev, varant): YETERLİ bilgi VE tecrübe, ikisi birden.
TIER_REQUIREMENTS: Dict[int, Dict[str, Any]] = {
    1: {"knowledge": None, "experience": False},
    2: {"knowledge": "limited", "experience": False},
    3: {"knowledge": "limited", "experience": True},
    4: {"knowledge": "sufficient", "experience": True},
}

#: Bilgi seviyeleri, düşükten yükseğe. Karşılaştırma sırayla yapılıyor.
_KNOWLEDGE_ORDER = ["none", "limited", "sufficient"]


def _meets(knowledge: str, required: Optional[str]) -> bool:
    if required is None:
        return True
    return _KNOWLEDGE_ORDER.index(knowledge) >= _KNOWLEDGE_ORDER.index(required)


def _group_result(group: Dict[str, Any], answers: Dict[str, str]) -> Dict[str, Any]:
    """Bir ürün grubunun yeterliliği ve GEREKÇESİ.

    Gerekçe saklanıyor, çünkü "uygun değil" tek başına kişi hakkında bir yargı
    gibi okunuyor. Hangi beyandan çıktığı yazılı olunca kullanıcı hem yargı
    olmadığını hem de cevabını değiştirerek sonucu değiştirebileceğini görüyor.
    """
    group_key = group["key"]
    knowledge = answers[_group_key(group_key, "knowledge")]
    frequency = answers[_group_key(group_key, "frequency")]
    volume = answers[_group_key(group_key, "volume")]

    has_experience = (
        frequency != NEVER_TRADED["frequency"] or volume != NEVER_TRADED["volume"]
    )
    rule = TIER_REQUIREMENTS[group["tier"]]
    knowledge_ok = _meets(knowledge, rule["knowledge"])
    # Yeterli bilgi beyan eden birinden ayrıca tecrübe aranmıyor: ürünü
    # anladığını söylemek, hiç işlem yapmamış olmasıyla çelişmiyor. Kademe 4
    # bunun istisnası ve bilerek: en karmaşık ürünlerde beyan edilen bilgiye
    # tek başına dayanmak, testin varlık sebebini boşa çıkarır.
    experience_ok = (
        not rule["experience"]
        or has_experience
        or (knowledge == "sufficient" and group["tier"] < 4)
    )
    eligible = knowledge_ok and experience_ok

    if eligible and rule["knowledge"] is None:
        reason = "Bu grup için bilgi ve tecrübe koşulu aranmıyor."
    elif eligible:
        reason = "Beyan ettiğiniz bilgi ve tecrübe bu grup için yeterli."
    elif not knowledge_ok:
        reason = "Bu ürünler hakkında beyan ettiğiniz bilgi seviyesi yeterli değil."
    else:
        reason = "Bilgi beyanınız var ancak bu grupta işlem tecrübesi belirtmediniz."

    return {
        "key": group_key,
        "label": group["label"],
        "risk": group["risk"],
        "knowledge": knowledge,
        "frequency": frequency,
        "volume": volume,
        "has_experience": has_experience,
        "eligible": eligible,
        "reason": reason,
    }


def score_answers(answers: Dict[str, str]) -> Dict[str, Any]:
    """Cevapları 0..100 ham puana, bir banda ve grup başına yeterliliğe çevirir.

    Cevapların tam ve geçerli olduğunu varsayar; router önce doğruluyor.

    Çıktı v1'in ürettiği üç alanı AYNEN taşıyor (`raw_score`,
    `tolerance_level`, `investment_horizon`), çünkü uygunluk karşılaştırması
    ve risk profili bunları okuyor ve sürüm değiştirdi diye bozulmamalı.
    Yeni olan `profile` ve `product_groups`.
    """
    total = sum(
        question.weight * _points(question.key, answers[question.key])
        for question in QUESTIONS
    )
    raw = round(total, 1)

    return {
        "version": VERSION,
        "raw_score": raw,
        "tolerance_level": _band(raw),
        "investment_horizon": HORIZONS.get(answers["horizon"], answers["horizon"]),
        # Puana girmiyor; kayda geçiyor.
        "profile": {
            "age_band": AGE_BANDS.get(answers["age_band"], answers["age_band"]),
            "education": EDUCATION_LEVELS.get(answers["education"], answers["education"]),
        },
        "product_groups": [
            _group_result(group, answers) for group in PRODUCT_GROUPS
        ],
    }


def group_labels() -> Dict[str, str]:
    """Grup anahtarından kullanıcıya gösterilecek ada."""
    return {group["key"]: group["label"] for group in PRODUCT_GROUPS}
