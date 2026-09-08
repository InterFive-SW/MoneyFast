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
