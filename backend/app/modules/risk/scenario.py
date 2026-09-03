"""Koşullu senaryo ve stres testi — ikisi de ÖLÇÜM, tahmin değil.

Bu modül tek bir soruyu cevaplıyor: *bir faktör şu kadar oynasaydı, geçmişte
ölçülen birlikte harekete göre portföy ne kadar etkilenirdi?* Cevap bir tahmin
değil; geçmiş getirilerin aritmetiği, koşula bağlanmış hâli.

Ayrım önemli, çünkü ürünün ileriye dönük konuşma sınırı kodda yazılı
(`compliance/rules.py:GUA-003`): çekinceye bağlanmamış yön iddiası engelleniyor,
koşullu ve çekinceli okuma engellenmiyor. Burada üretilen her cümle ikinci
türden ve bir test bunu sabitliyor.

DUYARLILIK YALNIZ BAŞINA YANILTICI. Bir beta, faktörün portföyün hareketini ne
kadar AÇIKLADIĞINI söylemez. Ölçülen 0,42'lik bir beta, faktör değişkenliğin
yalnızca %3'ünü açıklıyorken de çıkabilir; o durumda "dolar %10 çıksa portföyün
%4,2 etkilenir" cümlesi, veri onu desteklemezken kesinlik kurar. Bu yüzden
korelasyon ve açıklama gücü (r²) yanıtın ZORUNLU parçası ve zayıf olduğunda
cümlenin kendisi bunu söylüyor.

Yeni veri kaynağı gerekmiyor: USDTRY ve XU100 mumları zaten toplanıyor,
tarih hizalama `returns.paired_returns`'te, beta `returns.beta()`'da.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from . import returns as risk_returns

#: Ölçülebilir faktörler ve kullanıcıya gösterilecek adları.
#:
#: Kapalı bir küme, çünkü her biri için GÜNLÜK bir fiyat serisi gerekiyor ve
#: bir enstrümanın adını buraya yazmak onu ölçülebilir yapmıyor. Faiz bilerek
#: YOK: sistemde faiz SERİSİ tutulmuyor (`TR_POLICY_RATE` bir sabit),
#: dolayısıyla "faizler artarsa" USDTRY gibi ölçülemez. Ölçülemeyen bir
#: faktörü ölçülebilirmiş gibi sunmak, uydurulmuş bir sayıyı ölçüm diye
#: vermek olurdu; uç nokta bunun yerine reddediyor ve sebebini söylüyor.
FACTORS = {
    "USDTRY": "Dolar/TL",
    "EURTRY": "Euro/TL",
    "XU100": "BIST 100",
    "XAUUSD": "Ons altın",
}

#: Duyarlılığın hesaplanması için gereken en az ortak gün. Üçün altında
#: kovaryans tanımsız; altmışın altında sayı gürültüdür ve bu, yanıtta
#: `is_statistically_reliable` ile söyleniyor -- hesaplama reddedilmiyor,
#: güvenilirliği raporlanıyor.
MIN_OBSERVATIONS = 3

#: Faktörün portföyü "açıkladığı" sayılması için gereken en düşük r².
#: Altındaysa duyarlılık yine raporlanıyor ama cümle bunun zayıf olduğunu
#: SÖYLÜYOR. Eşik gelenekten değil, ölçümden: bu portföylerde XU100 için r²
#: 0,4-0,7 bandında, döviz için 0,00-0,15 bandında çıkıyor ve ikisi arasındaki
#: boşluk buraya düşüyor.
WEAK_FIT_R2 = 0.20


def sensitivity(
    dates: Sequence[Any],
    values: Sequence[float],
    factor_bars: Sequence[tuple],
) -> Optional[dict[str, Any]]:
    """Portföyün bir faktöre duyarlılığı: beta, korelasyon ve açıklama gücü.

    Tarihe göre hizalanmış getiriler üzerinden. Uzunluğa göre hizalamak,
    faktörün eksik olduğu her günden önceki tüm gözlemleri yanlış günle
    eşleştirirdi -- `paired_returns`'ün var olma sebebi bu.

    Ortak gün yetmiyorsa None: sıfır beta "portföy bu faktörden hiç
    etkilenmiyor" diye okunur ve bu, "ölçemedik"in tam tersi bir iddia.
    """
    portfolio, factor = risk_returns.paired_returns(dates, values, factor_bars)
    if len(portfolio) < MIN_OBSERVATIONS:
        return None

    slope = risk_returns.beta(portfolio, factor)
    if slope is None:
        return None

    corr = risk_returns.correlation(portfolio, factor)
    return {
        "beta": slope,
        "correlation": corr,
        # r²: faktörün portföy hareketinin ne kadarını açıkladığı. Betanın
        # yanında ZORUNLU -- tek başına bir beta, ilişkinin ne kadar gerçek
        # olduğu hakkında hiçbir şey söylemiyor.
        "r_squared": None if corr is None else corr * corr,
        "observation_count": len(portfolio),
        "is_statistically_reliable": len(portfolio) >= risk_returns.MIN_RELIABLE_OBSERVATIONS,
    }


def impact(beta: float, shock_pct: float) -> float:
    """Şokun portföye tahmini yansıması, yüzde olarak.

    Doğrusal: beta bir günlük birlikte hareketin katsayısı ve onu %10'luk bir
    şoka uygulamak, ilişkinin o ölçekte de aynı kaldığını VARSAYIYOR. Varsayım
    yanıtta `assumptions` içinde yazılı; gizlenmiş bir varsayım, olmayan bir
    kesinlik üretir.
    """
    return beta * shock_pct


#: Dönemin Türkçesi. Cümlede "son 1Y" yazmak, iç bir kodu kullanıcıya
#: göstermek olurdu (`prompts.py`'deki NAMING kuralıyla aynı sebep).
LOOKBACK_TR = {
    "1M": "1 ay", "3M": "3 ay", "6M": "6 ay",
    "1Y": "1 yıl", "3Y": "3 yıl", "5Y": "5 yıl", "MAX": "tüm geçmiş",
}

#: Koşullu okumanın yanındaki çekince. `technicals.HEDGE_TR` ile aynı cümle
#: bilerek: ürünün iki yerde iki farklı çekince yazması, birinin daha az
#: bağlayıcı olduğu izlenimi verirdi.
HEDGE_TR = "geçmiş fiyat hareketi geleceği belirlemez"

#: Açıklama gücü düşükken eklenen cümle. Sayıyı SİLMİYOR -- ölçüm gerçek --
#: ama ne kadar taşıdığını söylüyor.
WEAK_FIT_TR = (
    "Ancak bu faktör portföyünüzün geçmiş hareketinin yalnızca %{pct} kadarını "
    "açıklıyor, dolayısıyla bu duyarlılık zayıf bir ilişkiye dayanıyor"
)


def _tr(value: float, digits: int = 1) -> str:
    """Türkçe sayı biçimi: ondalık virgül, binlik nokta."""
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def narrate(
    factor_name: str, shock_pct: float, measured: dict[str, Any], lookback: str
) -> str:
    """Senaryonun Türkçe okuması.

    KOŞULLU kurulmuş: "yükselseydi ... etkilenirdi". `GUA-003` çekinceye
    bağlanmamış yön iddiasını engelliyor ve bu cümle bir yön iddiası değil --
    faktörün ne yapacağı hakkında hiçbir şey söylemiyor, yalnızca yapsaydı ne
    olacağını söylüyor. Çekince yine de aynı cümlede: koşul ile çekinceyi
    ayırmak, ilk yarıyı tek başına bir beklenti hâline getirirdi.
    """
    direction = "yükselseydi" if shock_pct >= 0 else "düşseydi"
    effect = impact(measured["beta"], shock_pct)
    period = LOOKBACK_TR.get(lookback, lookback)
    opening = (
        f"{factor_name} %{_tr(abs(shock_pct))} {direction}, son {period} "
        f"ölçülen duyarlılığa göre portföyünüzün değeri "
    )

    # Bire yuvarlanan bir etkiyi "%0,0 artardı" diye yazmak, ölçülmüş bir
    # sıfır iddiası olur. Ölçüm bunu söylemiyor: söylediği, etkinin bu
    # hassasiyette görünmediği.
    if abs(effect) < 0.05:
        body = opening + "bu hassasiyette ölçülebilir bir değişim göstermezdi"
    else:
        moves = "artardı" if effect >= 0 else "azalırdı"
        body = opening + f"yaklaşık %{_tr(abs(effect))} {moves}"

    r2 = measured.get("r_squared")
    if r2 is not None and r2 < WEAK_FIT_R2:
        body += ". " + WEAK_FIT_TR.format(pct=_tr(r2 * 100))
    if not measured.get("is_statistically_reliable"):
        body += (
            f". Ölçüm {measured['observation_count']} ortak güne dayanıyor, "
            f"istatistiksel olarak güvenilir sayılacak kadar uzun değil"
        )
    # Bağlaç, cümle zaten "Ancak" ile devam ettiyse tekrarlanmıyor.
    connector = "ve" if body.rstrip().endswith("değil") or ". Ancak" in body else "ancak"
    return f"{body} — {connector} {HEDGE_TR}."


# ── Stres testi: ikisi de ÖLÇÜM ──────────────────────────────────────────────


def worst_days(
    dates: Sequence[Any], values: Sequence[float], count: int = 5
) -> list[dict[str, Any]]:
    """Portföyün en kötü günleri, tarihleriyle.

    Uydurulmuş bir senaryo değil: o günler gerçekten oldu. Varsayımsal bir
    kayıp tahmininin aksine bunun doğrulanabilir bir karşılığı var.
    """
    series = risk_returns.simple_returns(values)
    if not series:
        return []
    # `simple_returns` n-1 değer üretiyor; i'inci getiri dates[i+1] gününe ait.
    rows = [
        {"date": dates[index + 1], "return_pct": value * 100}
        for index, value in enumerate(series)
    ]
    rows.sort(key=lambda row: row["return_pct"])
    return rows[:count]


def factor_replay(
    dates: Sequence[Any],
    values: Sequence[float],
    factor_bars: Sequence[tuple],
    window: int = 5,
) -> Optional[dict[str, Any]]:
    """Faktörün en sert oynadığı pencerede portföyün ne yaptığı.

    TARİHSEL REPLAY: bir model çıktısı değil, o günlerde gerçekten olan.
    Faktörün ve portföyün AYNI günlerdeki değişimi yan yana konuyor; yorumu
    okuyan yapıyor.

    Pencere kayan: en sert hareket tek bir günde olmayabilir ve "dolar bir
    haftada %12 çıktığında ne oldu" sorusu, "en kötü tek gün"den daha çok
    şeye benziyor.
    """
    day_map = risk_returns._day_map(factor_bars)
    shared = [(day, value) for day, value in zip(dates, values) if day in day_map]
    if len(shared) < window + 1:
        return None

    best_index, best_move = None, 0.0
    for index in range(len(shared) - window):
        start_day, _ = shared[index]
        end_day, _ = shared[index + window]
        move = (day_map[end_day] / day_map[start_day] - 1) * 100
        if abs(move) > abs(best_move):
            best_index, best_move = index, move

    if best_index is None:
        return None

    start_day, start_value = shared[best_index]
    end_day, end_value = shared[best_index + window]
    return {
        "start_date": start_day,
        "end_date": end_day,
        "factor_move_pct": best_move,
        "portfolio_move_pct": (end_value / start_value - 1) * 100,
        "trading_days": window,
    }
