"""The user-facing risk profile: a score, the findings behind it, and next steps.

`service.calculate` already produces the measurements — annualised volatility,
downside deviation, max drawdown, historical VaR, HHI and effective N. What it
does not do is say what they mean to someone who is not a quant, which is what
the Risk page needs.

Everything here is DERIVED, and derived visibly. The page it replaces read
from a hardcoded fixture: a score of 68, four invented findings and a
debt-to-income ratio computed from numbers nobody measured. A score whose
derivation cannot be inspected is that fixture with extra steps, so each
component is returned next to the raw metric that produced it.

Scoring, stated plainly so it can be argued with:

    score = 100 - (45 * volatility_penalty
                 + 35 * concentration_penalty
                 + 20 * drawdown_penalty)

Higher is calmer. The weights say that how much a portfolio moves matters most,
how much of it sits in one name matters nearly as much, and how far it has
actually fallen matters but is already partly reflected in the other two.

A component whose input is missing is EXCLUDED and the remaining weights are
renormalised, rather than scored as zero. Treating an unmeasurable drawdown as
"no drawdown" would reward a portfolio for having too little history to judge.
"""

from __future__ import annotations

from typing import Any, Optional

#: Component weights. They sum to 100; see the module docstring.
WEIGHTS = {"volatility": 45.0, "concentration": 35.0, "drawdown": 20.0}

#: Annualised volatility mapped onto 0..1. 10% is an unremarkable diversified
#: equity portfolio; at 45% the portfolio's yearly swing is about half its
#: value, which is the top of the scale rather than a boundary of good taste.
VOLATILITY_FLOOR, VOLATILITY_CEILING = 0.10, 0.45

#: Herfindahl index. 0.10 is roughly ten evenly weighted positions; 0.50 is
#: roughly two. Below the floor, adding names changes little.
HHI_FLOOR, HHI_CEILING = 0.10, 0.50

#: Peak-to-trough decline. A 10% pullback is ordinary; a 50% one is the kind
#: of fall that ends with the position being sold at the bottom.
DRAWDOWN_FLOOR, DRAWDOWN_CEILING = 0.10, 0.50

#: Score bands, high to low. The Turkish labels are what the UI renders.
BANDS = ((70.0, "Düşük"), (45.0, "Orta"), (0.0, "Yüksek"))


def _penalty(value: Optional[float], floor: float, ceiling: float) -> Optional[float]:
    """Map a metric onto 0..1, or None when it could not be measured."""
    if value is None:
        return None
    if ceiling <= floor:  # pragma: no cover - guards a nonsensical config
        return 0.0
    return max(0.0, min(1.0, (value - floor) / (ceiling - floor)))


def _band(score: float) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return BANDS[-1][1]  # pragma: no cover - the last band starts at zero


def score_from(metrics: dict[str, Any]) -> dict[str, Any]:
    """Turn measured metrics into a 0-100 score plus its own breakdown."""
    concentration = metrics.get("concentration") or {}
    drawdown = metrics.get("max_drawdown") or {}

    raw = {
        "volatility": metrics.get("volatility_annualized"),
        "concentration": concentration.get("hhi"),
        # Stored negative (a fall). The penalty is about magnitude.
        "drawdown": abs(drawdown["value"]) if drawdown.get("value") is not None else None,
    }
    bounds = {
        "volatility": (VOLATILITY_FLOOR, VOLATILITY_CEILING),
        "concentration": (HHI_FLOOR, HHI_CEILING),
        "drawdown": (DRAWDOWN_FLOOR, DRAWDOWN_CEILING),
    }

    components = []
    penalty_total = 0.0
    weight_total = 0.0
    for name, weight in WEIGHTS.items():
        penalty = _penalty(raw[name], *bounds[name])
        components.append(
            {
                "name": name,
                "measured": raw[name],
                "weight": weight,
                # None, not 0.0: the UI shows "ölçülemedi" rather than a bar
                # at zero, which would read as a clean bill of health.
                "penalty": penalty,
            }
        )
        if penalty is None:
            continue
        penalty_total += weight * penalty
        weight_total += weight

    if weight_total == 0:
        # Nothing measurable. Refusing to score is the honest answer; a
        # default of 50 would be a number the user could act on.
        return {"score": None, "level": None, "components": components}

    # Renormalised over the components that could actually be measured.
    score = round(100.0 - (penalty_total / weight_total) * 100.0, 1)
    return {"score": score, "level": _band(score), "components": components}


def findings_from(metrics: dict[str, Any], position_count: int) -> list[dict[str, Any]]:
    """Observations, each carrying the number that produced it.

    Replaces four static strings that described a portfolio nobody owned. The
    `value` field is what keeps these honest: a finding the user cannot trace
    back to a measurement is an opinion.
    """
    concentration = metrics.get("concentration") or {}
    drawdown = metrics.get("max_drawdown") or {}
    out: list[dict[str, Any]] = []

    top_3 = concentration.get("top_3_weight")
    if top_3 is not None:
        heavy = top_3 > 0.60
        out.append({
            "id": "concentration-top3",
            "title": "En büyük üç pozisyon" if heavy else "Pozisyon dağılımı dengeli",
            "description": (
                f"Portföyünüzün %{top_3 * 100:.1f}'i en büyük üç pozisyonda. "
                "Bu üçünden birinin sert hareketi toplamı belirgin şekilde etkiler."
                if heavy else
                f"En büyük üç pozisyon toplamın %{top_3 * 100:.1f}'ini oluşturuyor."
            ),
            "impact": "negative" if heavy else "positive",
            "value": round(top_3, 4),
        })

    effective_n = concentration.get("effective_n")
    if effective_n is not None:
        thin = effective_n < 5
        out.append({
            "id": "effective-n",
            "title": "Etkin çeşitlilik",
            "description": (
                f"{position_count} pozisyonunuz var, ancak ağırlıklar dikkate "
                f"alındığında etkin çeşitlilik {effective_n:.1f} hisseye denk geliyor."
            ),
            "impact": "negative" if thin else "positive",
            "value": round(effective_n, 2),
        })

    volatility = metrics.get("volatility_annualized")
    if volatility is not None:
        out.append({
            "id": "volatility",
            "title": "Yıllık oynaklık",
            "description": (
                f"Portföyünüzün yıllıklandırılmış oynaklığı %{volatility * 100:.1f}. "
                "Bu, geçmiş dalgalanmanın ölçüsüdür; gelecekteki hareketi tahmin etmez."
            ),
            "impact": "negative" if volatility > 0.30 else "neutral",
            "value": round(volatility, 4),
        })

    if drawdown.get("value") is not None:
        depth = abs(drawdown["value"])
        out.append({
            "id": "max-drawdown",
            "title": "En büyük düşüş",
            "description": (
                f"Seçilen dönemde tepe noktadan %{depth * 100:.1f} geri çekilme "
                f"yaşandı ({drawdown.get('peak_date')} → {drawdown.get('trough_date')})."
            ),
            "impact": "negative" if depth > 0.20 else "neutral",
            "value": round(depth, 4),
        })

    by_currency = concentration.get("by_currency") or {}
    if len(by_currency) == 1:
        only = next(iter(by_currency))
        out.append({
            "id": "single-currency",
            "title": "Tek para birimi",
            "description": (
                f"Tüm pozisyonlarınız {only} cinsinden. Kur hareketi portföyün "
                "tamamını aynı yönde etkiler."
            ),
            "impact": "neutral",
            "value": 1.0,
        })

    return out


def suggestions_from(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Things the user could LOOK AT, never things they should buy or sell.

    The non-advisory rule applies here exactly as it does in the chat: each
    entry names something to examine or compute, and the action opens a screen
    rather than an order.
    """
    concentration = metrics.get("concentration") or {}
    out: list[dict[str, Any]] = []

    top_1 = concentration.get("top_1_weight")
    largest = (concentration.get("largest_position") or {}).get("symbol")
    if top_1 is not None and top_1 > 0.25 and largest:
        out.append({
            "id": "review-largest",
            "title": f"{largest} ağırlığını inceleyin",
            "description": (
                f"Tek bir pozisyon portföyün %{top_1 * 100:.1f}'ini oluşturuyor. "
                "Bu pozisyonun geçmiş oynaklığına ve düşüşlerine bakabilirsiniz."
            ),
            "actionLabel": "Pozisyonu incele",
            "priority": "high" if top_1 > 0.35 else "medium",
        })

    by_sector = concentration.get("by_sector") or {}
    dominant = max(by_sector.items(), key=lambda kv: kv[1], default=None)
    if dominant and dominant[1] > 0.40 and dominant[0] != "UNCLASSIFIED":
        out.append({
            "id": "sector-weight",
            "title": f"{dominant[0]} sektör ağırlığı",
            "description": (
                f"Portföyün %{dominant[1] * 100:.1f}'i bu sektörde. Sektör "
                "dağılımını Analiz sayfasında görebilirsiniz."
            ),
            "actionLabel": "Sektör dağılımını gör",
            "priority": "medium",
        })

    excluded = ((metrics.get("data_quality") or {}).get("excluded_symbols")) or []
    if excluded:
        out.append({
            "id": "missing-history",
            "title": "Geçmişi eksik enstrümanlar",
            "description": (
                f"{', '.join(excluded[:5])} için yeterli fiyat geçmişi yok; bu "
                "enstrümanlar oynaklık ve düşüş hesabına dâhil edilmedi."
            ),
            "actionLabel": "Detayları gör",
            "priority": "low",
        })

    return out


# ---------------------------------------------------------------------------
# Suitability: measurement against the user's own declared tolerance
# ---------------------------------------------------------------------------
#: Ordered low to high so the two labels can be compared by position. The
#: comparison is deliberately made on LABELS, never on the two scores: the
#: measured score is inverted (100 = calm) and the questionnaire's raw score is
#: not, so any arithmetic between them would be read backwards by someone
#: eventually. On the label scale there is no arithmetic to get wrong.
_LEVEL_ORDER = ("Düşük", "Orta", "Yüksek")

ALIGNMENT_UNKNOWN = "UNKNOWN"
ALIGNMENT_ALIGNED = "ALIGNED"
ALIGNMENT_RISKIER = "PORTFOLIO_RISKIER"
ALIGNMENT_CALMER = "PORTFOLIO_CALMER"


def suitability(
    measured_level: Optional[str], declared_tolerance: Optional[str]
) -> dict[str, Any]:
    """Compare what was measured against what the user said they tolerate.

    This is the one place the product is allowed to put those two things in the
    same sentence, and it stays on the right side of the advisory line because
    both halves are facts: one is computed from price history, the other is
    what the user themselves answered. Neither is a judgement about them, and
    nothing here says what to do about a mismatch.

    `compliance/rules.py:SUI-001` blocks "risk profilinize uygun" because a
    suitability CLAIM has no basis. A comparison is not that claim, and the
    wording below avoids the banned phrasing on purpose rather than by luck.
    """
    if measured_level not in _LEVEL_ORDER or declared_tolerance not in _LEVEL_ORDER:
        return {
            "measured_level": measured_level,
            "declared_tolerance": declared_tolerance,
            "alignment": ALIGNMENT_UNKNOWN,
            "statement": (
                "Karşılaştırma için hem ölçülebilir bir portföy hem de "
                "tamamlanmış bir risk anketi gerekiyor."
            ),
        }

    measured_index = _LEVEL_ORDER.index(measured_level)
    declared_index = _LEVEL_ORDER.index(declared_tolerance)

    if measured_index == declared_index:
        alignment = ALIGNMENT_ALIGNED
        statement = (
            f"Ölçülen portföy riskiniz \"{measured_level}\" seviyesinde ve ankette "
            f"belirttiğiniz tolerans da \"{declared_tolerance}\". İkisi aynı bandda."
        )
    elif measured_index > declared_index:
        alignment = ALIGNMENT_RISKIER
        statement = (
            f"Ölçülen portföy riskiniz \"{measured_level}\" seviyesinde; ankette "
            f"belirttiğiniz tolerans \"{declared_tolerance}\". Portföy, beyan "
            "ettiğiniz bandın üzerinde ölçülüyor."
        )
    else:
        alignment = ALIGNMENT_CALMER
        statement = (
            f"Ölçülen portföy riskiniz \"{measured_level}\" seviyesinde; ankette "
            f"belirttiğiniz tolerans \"{declared_tolerance}\". Portföy, beyan "
            "ettiğiniz bandın altında ölçülüyor."
        )

    return {
        "measured_level": measured_level,
        "declared_tolerance": declared_tolerance,
        "alignment": alignment,
        "statement": statement,
    }


#: Enstrüman türünden SPK ürün grubuna. YALNIZCA testin gerçekten kapsadığı
#: eşleme yazılı.
#:
#: `equity` grubunun etiketi "Ortaklık Payı (Hisse Senedi), Eurobond, Dövizli
#: Tahviller" -- hisse senedi orada. Spot altın ve döviz paritesi DÖRT GRUBUN
#: HİÇBİRİNDE yok, dolayısıyla buraya da yazılmadılar: bir enstrümanı ona ait
#: olmayan bir gruba sokmak, o grup için verilmiş bir yeterlilik beyanını
#: hakkında hiç soru sorulmamış bir ürüne uygulamak olurdu. Kapsanmayan
#: pozisyon düşürülmez, kapsanmadığı SÖYLENİR.
GROUP_BY_PRODUCT_TYPE = {"stock": "equity"}

EXPOSURE_COVERED = "COVERED"
EXPOSURE_NOT_ASSESSED = "NOT_ASSESSED"
EXPOSURE_OUTSIDE_TEST = "OUTSIDE_TEST"


def group_exposure(
    positions: list[dict[str, Any]],
    product_groups: Optional[list[dict[str, Any]]],
) -> dict[str, Any]:
    """Hangi SPK ürün grubunda ne kadar duruyor, ve test o grup için ne demişti.

    `suitability()` ile aynı çizgide ve aynı sebeple: iki OLGU yan yana
    konuyor -- portföyde ölçülen ağırlık, ve kullanıcının ankette kendi
    verdiği bilgi/tecrübe beyanı. Hiçbiri kişi hakkında bir yargı değil ve
    hiçbir yerde ne yapması gerektiği söylenmiyor.

    `compliance/rules.py:SUI-001` "size uygun" kalıbını engelliyor çünkü bir
    uygunluk İDDİASININ dayanağı yok. Aşağıdaki cümleler o kalıptan şans
    eseri değil, bilerek kaçınıyor: "beyan etmediniz" kullanıcının kendi
    cevabını aktarır, "size uygun değil" ise onun hakkında karar verir.
    """
    total = sum(float(row.get("market_value") or 0.0) for row in positions)
    by_group: dict[str, float] = {}
    outside = 0.0
    outside_types: set[str] = set()

    for row in positions:
        product_type = str(row.get("asset_class") or "").lower()
        value = float(row.get("market_value") or 0.0)
        group = GROUP_BY_PRODUCT_TYPE.get(product_type)
        if group is None:
            outside += value
            outside_types.add(product_type or "bilinmiyor")
            continue
        by_group[group] = by_group.get(group, 0.0) + value

    assessed = {
        str(entry.get("key")): entry for entry in (product_groups or [])
    }

    rows: list[dict[str, Any]] = []
    for group, value in sorted(by_group.items(), key=lambda item: -item[1]):
        entry = assessed.get(group)
        share = round(value / total * 100, 1) if total else None
        label = str(entry.get("label")) if entry else group
        if entry is None:
            status, statement = EXPOSURE_NOT_ASSESSED, (
                f"Portföyünüzün %{share} kadarı bu grupta; uygunluk testinde "
                f"bu grup için bir kaydınız yok."
            )
        elif entry.get("eligible"):
            status, statement = EXPOSURE_COVERED, (
                f"Portföyünüzün %{share} kadarı bu grupta. Ankette bu grup için "
                f"bilgi ve tecrübe beyan etmiştiniz."
            )
        else:
            # "Beyan etmediniz" kullanıcının KENDİ cevabını aktarıyor.
            # "Size uygun değil" onun hakkında karar verirdi ve SUI-001 tam
            # olarak o cümleyi engelliyor.
            status, statement = EXPOSURE_NOT_ASSESSED, (
                f"Portföyünüzün %{share} kadarı bu grupta. Ankette bu grup için "
                f"yeterli bilgi ve tecrübe beyan etmemiştiniz; beyanınızı "
                f"testi yenileyerek güncelleyebilirsiniz."
            )
        rows.append({
            "group": group,
            "label": label,
            "value": round(value, 2),
            "share_percent": share,
            "status": status,
            "eligible": None if entry is None else bool(entry.get("eligible")),
            "reason": (entry or {}).get("reason"),
            "statement": statement,
        })

    if outside > 0:
        share = round(outside / total * 100, 1) if total else None
        rows.append({
            "group": None,
            "label": "Uygunluk testinin kapsamadığı varlıklar",
            "value": round(outside, 2),
            "share_percent": share,
            "status": EXPOSURE_OUTSIDE_TEST,
            "eligible": None,
            "reason": None,
            # Kapsanmayan pozisyonu sessizce düşürmek, portföyün bir kısmını
            # değerlendirilmiş gibi göstermek olurdu.
            "statement": (
                f"Portföyünüzün %{share} kadarı ({', '.join(sorted(outside_types))}) "
                f"uygunluk testindeki dört ürün grubunun hiçbirine girmiyor; "
                f"bunlar hakkında ankette soru sorulmuyor."
            ),
        })

    return {
        "assessed": bool(product_groups),
        "total_value": round(total, 2),
        "groups": rows,
    }
