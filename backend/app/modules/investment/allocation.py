"""Varlık dağılımı: kovalar, mevcut ağırlıklar ve kullanıcının hedefinden sapma.

Kovalar BURADA tanımlı ve tek kaynak. Dağılım grafiği ile hedef karşılaştırması
aynı listeden okumazsa, biri "ABD Hisse" derken diğeri "ABD Hisseleri" der ve
sapma hesabı sessizce sıfır çıkar -- bu depoda `sort_by` ve `market` filtresi
için aynı hata iki kez ölçüldü.

Anahtar SABİT, etiket değişebilir: hedef satırları veritabanında anahtarla
duruyor, dolayısıyla bir etiketi düzeltmek kimsenin kayıtlı hedefini
geçersizleştirmiyor.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.modules.risk import returns as risk_returns

CASH = "cash"
OTHER = "other"

#: Kova anahtarı -> (etiket, pasta rengi). Sıra da buradan: grafik ve hedef
#: formu aynı sırayı gösteriyor.
BUCKETS: dict[str, tuple[str, str]] = {
    CASH: ("Nakit (TRY)", "#64748b"),
    "bist_equity": ("BIST Hisse", "#0ea5e9"),
    "us_equity": ("ABD Hisse", "#22c55e"),
    # Altın sarı, döviz camgöbeği: pastada birbirinden ayırt edilebilsin.
    "gold": ("Altın", "#f59e0b"),
    "fx": ("Döviz", "#06b6d4"),
    OTHER: ("Diğer", "#a855f7"),
}

#: Enstrümanın İŞLEM YERİ -> kova. Para birimi değil: altın dolarla
#: fiyatlanıyor ama yabancı hisse değil ve bir dönem öyle sayılıyordu.
MARKET_TO_BUCKET: dict[str, str] = {
    "BIST": "bist_equity",
    "NASDAQ": "us_equity",
    "NYSE": "us_equity",
    "COMEX": "gold",
    "FX": "fx",
}

#: Kullanıcının hedef belirleyebileceği kovalar. `other` DIŞARIDA: kimse
#: "portföyümün %10'u sınıflandıramadığım şeylerde olsun" diye bir hedef
#: koymaz, ve koyabilseydi bu, eşlenmemiş bir piyasayı hedef hâline
#: getirirdi.
TARGETABLE = tuple(key for key in BUCKETS if key != OTHER)


def label_for(bucket: str) -> str:
    return BUCKETS.get(bucket, (bucket, ""))[0]


def colour_for(bucket: str) -> str:
    return BUCKETS.get(bucket, ("", "#a855f7"))[1]


def bucket_for(market: Optional[str]) -> str:
    """Eşleşmeyen piyasa `other`, düşürülmez.

    Dağılım grafiğinden kaybolan bir pozisyon, yanlış kovaya düşenden çok
    daha zor fark edilir.
    """
    return MARKET_TO_BUCKET.get(market or "", OTHER)


def current_amounts(
    valued_rows: Iterable[tuple[dict[str, Any], float]], cash: float
) -> dict[str, float]:
    """Kova başına tutar. `valued_rows`, (pozisyon, çevrilmiş değer) çiftleri.

    Değerleme çağırana bırakılıyor: kuru bilinmeyen bir pozisyonu 1.0
    varsayarak toplamak bu dosyanın işi değil ve `holding_value` bunu zaten
    doğru yapıyor.
    """
    amounts = {key: 0.0 for key in BUCKETS}
    amounts[CASH] = float(cash or 0.0)
    for row, value in valued_rows:
        amounts[bucket_for(row.get("market"))] += float(value)
    return amounts


def as_percentages(amounts: dict[str, float]) -> dict[str, Optional[float]]:
    """Yüzdeler, ya da toplam sıfırsa hepsi None.

    Boş bir portföyde her kovaya %0 yazmak, "hiçbirine sahip değilsiniz"
    yerine "dağılımınız şöyle" demek olurdu; dağılım yok.
    """
    total = sum(amounts.values())
    if total <= 0:
        return {key: None for key in amounts}
    return {key: round(value / total * 100, 1) for key, value in amounts.items()}


def drift(
    amounts: dict[str, float], targets: dict[str, float]
) -> dict[str, Any]:
    """Kullanıcının KENDİ hedefiyle ölçülen ağırlık arasındaki fark.

    Bu bir tavsiye değil, iki olgunun çıkarması: biri portföyden ölçülüyor,
    diğeri kullanıcının kendi girdiği sayı. `profile.suitability` ile aynı
    gerekçe -- ve aynı sınır: burada hiçbir yerde ne yapılması gerektiği
    söylenmiyor, yalnızca hedefe ulaşmak için kaç lira fark olduğu.

    Hedef koyulmamış kova hedefsiz kalır, %0 SAYILMAZ: "hedefim yok" ile
    "hedefim sıfır" farklı şeyler ve ikincisi elde tutulan her kuruşu sapma
    gibi gösterirdi.
    """
    total = sum(amounts.values())
    current = as_percentages(amounts)
    rows: list[dict[str, Any]] = []

    for key in BUCKETS:
        target = targets.get(key)
        amount = round(amounts.get(key, 0.0), 2)
        if target is None and amount == 0:
            continue
        actual = current.get(key)
        gap = None if (target is None or actual is None) else round(actual - target, 1)
        rows.append({
            "bucket": key,
            "label": label_for(key),
            "amount": amount,
            "current_percent": actual,
            "target_percent": target,
            "gap_points": gap,
            # Hedefe ulaşmak için kaç lira. İşaret YÖNÜ taşıyor: pozitif
            # fazla, negatif eksik. Emir üretmiyor -- kullanıcı isterse
            # mevcut öneri akışını kendisi başlatır.
            "gap_amount": None if gap is None else round(total * gap / 100, 2),
        })

    return {
        "has_target": bool(targets),
        "total_value": round(total, 2),
        "buckets": rows,
        "statement": _statement(rows, bool(targets), total),
    }


def _statement(rows: list[dict[str, Any]], has_target: bool, total: float) -> str:
    """Kodda üretilen cümle. Prompt'a bırakılan kurallar bu depoda tekrar
    tekrar uygulanmadı; sapmanın YÖNÜ yanlış okunursa kullanıcı hedefinin
    tersine hareket eder."""
    if not has_target:
        return (
            "Hedef dağılım belirlemediniz. Belirlerseniz portföyünüzün ondan "
            "ne kadar saptığı burada ölçülür."
        )
    if total <= 0:
        return (
            "Hedef dağılımınız kayıtlı ancak karşılaştırılacak bir portföy "
            "değeri yok."
        )
    widest = max(
        (row for row in rows if row["gap_points"] is not None),
        key=lambda row: abs(row["gap_points"]),
        default=None,
    )
    if widest is None or widest["gap_points"] == 0:
        return "Portföyünüz belirlediğiniz hedef dağılımla aynı noktada."
    direction = "üzerinde" if widest["gap_points"] > 0 else "altında"
    return (
        f"En büyük fark {widest['label']} kovasında: hedefiniz "
        f"%{widest['target_percent']:g}, ölçülen ağırlık "
        f"%{widest['current_percent']:g} — hedefin "
        f"{abs(widest['gap_points']):g} puan {direction}."
    )


# ── Hazır dağılım şablonları ────────────────────────────────────────────────
#
# Şablon bir MODEL PORTFÖY DEĞİL ve `AllocationTarget` modelindeki gerekçe
# burada da geçerli: sistemin hedefi koyması, tam olarak vermeyeceği kararı
# vermek olurdu. Bunlar formun BAŞLANGIÇ DEĞERİ; kaydedilen şey yine
# kullanıcının kendi PUT'u ve istediği gibi değiştirebiliyor.
#
# Adlar yargı taşımıyor: "Ağırlıklı nakit" ne yaptığını söylüyor, "temkinli"
# gibi bir nitelemede bulunmuyor -- ikincisi kullanıcının durumu hakkında bir
# iddia olurdu.

TEMPLATES: dict[str, dict[str, Any]] = {
    "cash_heavy": {
        "label": "Ağırlıklı nakit",
        "weights": {CASH: 60, "bist_equity": 20, "gold": 10, "fx": 10},
    },
    "balanced": {
        "label": "Dengeli",
        "weights": {
            CASH: 25, "bist_equity": 30, "us_equity": 20, "gold": 15, "fx": 10
        },
    },
    "equity_heavy": {
        "label": "Ağırlıklı hisse",
        "weights": {CASH: 10, "bist_equity": 45, "us_equity": 35, "gold": 10},
    },
}

#: Kovanın oynaklığını ölçmek için okunacak seri.
#:
#: `us_equity` için `SPX` migration 0043 ile eklendi; öncesinde evrende ABD
#: endeksi yoktu ve kova ölçülemiyordu. `INDEX_CODES` yalnızca ÜYELİK tablosu,
#: fiyat serisi değil.
#:
#: Nakit için vekil YOK ve olmaması bir eksiklik değil: getirisi sıfır
#: alınıyor ve bu bir VARSAYIM olarak raporlanıyor -- nakit faiz serisi
#: sistemde yok, `scenario.py`'nin faizi dışarıda bırakma gerekçesiyle aynı.
PROXY_FOR_BUCKET: dict[str, Optional[str]] = {
    "bist_equity": "XU100",
    "us_equity": "SPX",
    "gold": "XAUUSD",
    "fx": "USDTRY",
    CASH: None,
}

#: Ölçüm için gereken en az ORTAK işlem günü. Altmışın altında bir seri,
#: yıllıklandırıldığında gürültüyü bir orana çeviriyor.
MIN_COMMON_DAYS = 60

#: Ölçülemeyen kovaların toplam ağırlığı bu puanı aşarsa şablonun oynaklığı
#: hiç raporlanmıyor. Yüzde otuzu ölçülemeyen bir karışımın oynaklığını tek
#: bir sayı olarak sunmak, ölçülen yüzde yetmişi bütünmüş gibi göstermek
#: olurdu.
UNMEASURED_WEIGHT_LIMIT = 10


def template_volatility(
    weights: dict[str, float],
    closes_by_bucket: dict[str, list[tuple[Any, float]]],
) -> dict[str, Any]:
    """Bir ağırlık kümesinin geçmiş veriyle ÖLÇÜLEN yıllık oynaklığı.

    Seriler çağıran tarafından TL'ye çevrilmiş olarak veriliyor. Çevirmemek,
    ABD ve altın kovalarını TL yatırımcısı için sistematik olarak sakin
    gösterirdi -- bu depoda bir kez 48 kat olarak ölçülmüş hata sınıfı.

    Nakit getirisi sıfır ve bu bir VARSAYIM olarak dönüyor; sistemde nakit
    faiz serisi yok.

    Tarihe göre hizalanıyor, uzunluğa göre değil: iki seriyi son N gününe
    göre eşlemek, farklı günleri yan yana koymak olurdu (`paired_returns`ün
    kendi gerekçesi).
    """
    measured: dict[str, list[float]] = {}
    unmeasured: list[str] = []

    common: Optional[set] = None
    for bucket, weight in weights.items():
        if bucket == CASH:
            continue
        series = closes_by_bucket.get(bucket) or []
        if len(series) < MIN_COMMON_DAYS:
            unmeasured.append(bucket)
            continue
        dates = {row[0] for row in series}
        common = dates if common is None else (common & dates)

    if common is not None and len(common) < MIN_COMMON_DAYS:
        # Seriler tek tek yeterliydi ama ORTAK günleri yetmiyor: farklı
        # takvimlerde işlem gören iki piyasa (BIST ve NASDAQ) böyle.
        unmeasured = [b for b in weights if b != CASH]
        common = None

    for bucket, weight in weights.items():
        if bucket == CASH or bucket in unmeasured:
            continue
        series = [row for row in (closes_by_bucket.get(bucket) or [])
                  if common is None or row[0] in common]
        series.sort(key=lambda row: row[0])
        measured[bucket] = risk_returns.simple_returns([row[1] for row in series])

    unmeasured_weight = sum(
        weights.get(bucket, 0) for bucket in unmeasured
    )
    if unmeasured_weight > UNMEASURED_WEIGHT_LIMIT or not measured:
        return {
            "volatility": None,
            "unmeasured": sorted({label_for(b) for b in unmeasured}),
            "cash_assumed_flat": CASH in weights,
        }

    length = min(len(series) for series in measured.values())
    blended = [
        sum(
            weights[bucket] / 100.0 * measured[bucket][-length:][i]
            for bucket in measured
        )
        for i in range(length)
    ]
    return {
        "volatility": risk_returns.annualised_volatility(blended),
        "unmeasured": sorted({label_for(b) for b in unmeasured}),
        "cash_assumed_flat": CASH in weights,
    }
