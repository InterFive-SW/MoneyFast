"""Ölçülen kanıtların hangi yöne meylettiği, gerekçesiyle birlikte.

`technicals.py` ile aynı disiplin ve onun bir üst katmanı: saf fonksiyonlar,
veritabanı yok, girdi dışarıdan verilir. Ayrı bir modül olmasının sebebi
`technicals`'ın kendi sözü -- girdisi OHLCV barları, çıktısı sayılar ve metin.
Temel veri ve haber onun girdi kümesinde değil; oraya koymak o sözü yalanlardı.
Bu modül `technicals`i TEK YÖNLÜ import eder ve çekince ile koşullu okuma
oradan gelir, kopyalanmaz: iki yerde yaşayan bir çekince birinde düşer.

**Bu bir tavsiye değil, bir ölçüm özeti.** Üretilen cümle üç şeyi birden
yapmak zorunda: koşullu olmak, dayandığı ölçümü adıyla söylemek, ve çekincesini
aynı nefeste taşımak. `technicals.narrate()` bu kalıbı zaten kurmuştu; buradaki
tek fark, kanıtın üç kaynaktan gelmesi. Kalıbın dışına çıkan bir cümle
uygunluk kurallarına takılır ve `test_signals.py::TestWording` bunu her
üretilebilir cümle için sınar -- geçmesi tesadüf olmasın diye.

Hiçbir yerde hedef fiyat, "al/sat", "en iyi" ya da uygunluk yargısı yok.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

from . import technicals

log = logging.getLogger("moneyfast.market")

#: Sorulabilecek ileri vadeler. Kapalı küme, çünkü elimizdeki kanıtların
#: konuştuğu vade sınırlı: hareketli ortalamalar birkaç aylık, çeyreklik
#: bilanço üç aylık, haber günlük. "İki yıl sonra ne olur" sorusuna bu
#: verilerle dürüst bir cevap yok ve uydurmaktansa reddetmek gerekiyor.
#:
#: Ağırlıklar vade ile değişiyor: vade kısaldıkça fiyat hareketi, uzadıkça
#: bilanço ağırlık kazanıyor. Bu bir VARSAYIM ve yanıtta açıkça yazılıyor.
HORIZONS: dict[str, dict[str, Any]] = {
    "1M": {
        "label": "1 ay",
        "weights": {"TECHNICAL": 65.0, "FUNDAMENTAL": 20.0, "NEWS": 15.0},
    },
    "3M": {
        "label": "3 ay",
        "weights": {"TECHNICAL": 45.0, "FUNDAMENTAL": 40.0, "NEWS": 15.0},
    },
    "6M": {
        "label": "6 ay",
        "weights": {"TECHNICAL": 30.0, "FUNDAMENTAL": 55.0, "NEWS": 15.0},
    },
}

DEFAULT_HORIZON = "3M"

#: Vade dışı bir istek için verilen cevap. Boş sonuç değil, REDDETME: elimizde
#: olmayan bir ölçümü varmış gibi göstermemek, `technicals`in yetersiz bar
#: kuralıyla aynı.
OUT_OF_RANGE_TR = (
    "Elimizdeki ölçümler bu vadeye konuşamaz; 1, 3 ve 6 aylık okuma verebilirim."
)

#: Yön kurulabilmesi için gereken en az ölçülen kanıt ve en az ölçülen kaynak.
#:
#: İkisi birden: tek kaynaktan gelen üç kanıt aslında tek bir şeyin üç
#: görünümü olabiliyor (fiyat ortalamanın üzerindeyse, muhtemelen 52 hafta
#: aralığının da üst yarısındadır). İki kaynak şartı bunu engelliyor.
MIN_EVIDENCE = 3
MIN_SOURCES = 2

#: Yön ilan etmek için gereken en küçük meyil. Altında MIXED -- yani iki taraf
#: da ölçülüyor ve hiçbiri ağır basmıyor. Eşiksiz bir karşılaştırma her gün
#: başka bir yön ilan ederdi; `technicals.TREND_EPSILON_PCT` ile aynı gerekçe.
LEAN_THRESHOLD = 0.34

#: Haber penceresi. Doksan gün, `market/service.py`'deki portföy haber
#: penceresiyle aynı ve aynı gerekçeyle: eşleştirme bilerek dar olduğu için
#: otuz gün çoğu hissede tek haber bile bulmuyor.
NEWS_WINDOW_DAYS = 90

#: Pencere içinde okunan en fazla haber satırı. Sayım bu kadarla sınırlı ama
#: pratikte sınıra hiç değmiyor: tek bir sembolün doksan günlük etiketli haber
#: sayısı ölçüldüğünde tek haneli (ASELS 9). Yüksek tutuluyor ki "son 90 günde
#: N haber" cümlesi bir limitin altında sessizce yanlış çıkmasın.
NEWS_SAMPLE_LIMIT = 200

#: Temel veri eşikleri. Hepsi modülde sabit ve gerekçeli; "iyi/kötü" değil,
#: sağlayıcının yayımladığı dağılımda hangi tarafta durduğu.
ROE_STRONG = 0.15
ROE_WEAK = 0.0
MARGIN_STRONG = 0.10
MARGIN_WEAK = 0.0
GROWTH_STRONG = 0.10
GROWTH_WEAK = 0.0
#: Borç/özkaynak yüzde olarak geliyor (200 = 2 kat).
DEBT_HEAVY = 200.0

#: Yükseliş/düşüş gün sayımının yön saydığı oranlar.
UP_DAYS_STRONG = 0.65
UP_DAYS_WEAK = 0.35

#: 52 hafta aralığındaki konum. Metin KONUM der, "ucuz/pahalı" demez --
#: `MARKET_DATA_AGENT`'ın "never call a price cheap or expensive" kuralı
#: cümlenin kendisinde de geçerli.
RANGE_HIGH_PCT = 80.0
RANGE_LOW_PCT = 20.0

UP = "UP"
DOWN = "DOWN"
NEUTRAL = "NEUTRAL"

TECHNICAL = "TECHNICAL"
FUNDAMENTAL = "FUNDAMENTAL"
NEWS = "NEWS"


def _evidence(source: str, key: str, direction: str, value: Any, text: str) -> dict:
    return {
        "source": source,
        "key": key,
        "direction": direction,
        "value": value,
        "text": text,
    }


def _side(distance: float) -> str:
    return "üzerinde" if distance >= 0 else "altında"


# ── Teknik kanıt ────────────────────────────────────────────────────────────


def technical_evidence(signals: dict[str, Any]) -> list[dict]:
    """`technicals.compute()` çıktısını kanıt maddelerine çevirir.

    Yeniden hesap YOK: aynı sayıyı iki yerde hesaplamak, ikisinin ayrışması
    demek. Ölçülemeyen gösterge kanıt üretmez, sıfır saymaz.
    """
    rows: list[dict] = []

    fast, slow = signals.get("sma_50"), signals.get("sma_200")
    if fast is not None and slow is not None and slow != 0:
        gap = (fast - slow) / slow * 100.0
        if abs(gap) <= technicals.TREND_EPSILON_PCT:
            direction = NEUTRAL
        else:
            direction = UP if gap > 0 else DOWN
        rows.append(_evidence(
            TECHNICAL, "sma_50_vs_200", direction, round(gap, 2),
            f"50 günlük ortalaması 200 günlüğün "
            f"%{technicals.format_number(abs(gap))} {_side(gap)}",
        ))

    for window in (200, 50):
        distance = signals.get(f"pct_from_sma_{window}")
        if distance is None:
            continue
        if abs(distance) <= technicals.TREND_EPSILON_PCT:
            direction = NEUTRAL
        else:
            direction = UP if distance > 0 else DOWN
        rows.append(_evidence(
            TECHNICAL, f"price_vs_sma_{window}", direction, round(distance, 2),
            f"fiyatı {window} günlük ortalamasının "
            f"%{technicals.format_number(abs(distance))} {_side(distance)}",
        ))
        break

    trend = signals.get("trend")
    if trend in ("UPTREND", "DOWNTREND", "SIDEWAYS"):
        direction = {"UPTREND": UP, "DOWNTREND": DOWN}.get(trend, NEUTRAL)
        rows.append(_evidence(
            TECHNICAL, "trend", direction, trend,
            technicals._TREND_TR[trend],
        ))

    up_days, window = signals.get("up_days_recent"), signals.get("recent_window")
    if up_days is not None and window:
        share = up_days / window
        if share >= UP_DAYS_STRONG:
            direction = UP
        elif share <= UP_DAYS_WEAK:
            direction = DOWN
        else:
            direction = NEUTRAL
        rows.append(_evidence(
            TECHNICAL, "up_days_recent", direction, up_days,
            f"son {window} işlem gününün {technicals._locative(up_days)} "
            f"yükselerek kapattı",
        ))

    position = signals.get("week52_position_pct")
    if position is not None:
        if position >= RANGE_HIGH_PCT:
            direction = UP
        elif position <= RANGE_LOW_PCT:
            direction = DOWN
        else:
            direction = NEUTRAL
        rows.append(_evidence(
            TECHNICAL, "week52_position", direction, round(position, 1),
            f"52 hafta aralığının %{technicals.format_number(position, 0)} "
            f"seviyesinde",
        ))

    rsi = signals.get("rsi_14")
    if rsi is not None:
        # RSI yön OYU VERMEZ. 70 üstü "düşecek" demek değil: gösterge momentumu
        # ölçüyor ve yüksek momentum hem devam hem dönüş sayılabiliyor. Ölçüm
        # olarak listede duruyor, yöne katılmıyor.
        rows.append(_evidence(
            TECHNICAL, "rsi_14", NEUTRAL, round(rsi, 1),
            f"göreli güç endeksi {technicals.format_number(rsi, 0)}",
        ))

    return rows


# ── Temel kanıt ─────────────────────────────────────────────────────────────


def _quarter_index(period_end: Any) -> Optional[int]:
    """Çeyreğin mutlak sırası; `market_service._quarter_index` ile aynı formül."""
    try:
        return period_end.year * 4 + (period_end.month - 1) // 3
    except AttributeError:
        return None


def _year_ago_period(periods: Sequence[dict]) -> Optional[dict]:
    """Tam dört çeyrek geridekini KONUMDAN değil indeksten bulur.

    `periods[4]` demek, sağlayıcının hiç çeyrek atlamadığını varsaymak olurdu;
    atlıyor -- `quarterly_for` bunun için `year_ago_available` bayrağını ayrıca
    hesaplıyor. Yanlış satırı "geçen yılın aynı çeyreği" diye okumak, büyüme
    oranını sessizce yanlış yapardı.
    """
    if not periods:
        return None
    latest = _quarter_index(periods[0].get("period_end"))
    if latest is None:
        return None
    for period in periods[1:]:
        if _quarter_index(period.get("period_end")) == latest - 4:
            return period
    return None


def _ratio_evidence(key: str, value: Optional[float], strong: float,
                    weak: float, text: str, invert: bool = False) -> Optional[dict]:
    if value is None:
        return None
    if invert:
        direction = DOWN if value >= strong else NEUTRAL
    elif value >= strong:
        direction = UP
    elif value <= weak:
        direction = DOWN
    else:
        direction = NEUTRAL
    return _evidence(FUNDAMENTAL, key, direction, value, text)


def fundamental_evidence(
    fundamentals: Optional[dict[str, Any]],
    quarterly: Optional[dict[str, Any]],
) -> list[dict]:
    """Anlık oranlar ve çeyreklik seri.

    **Anlık görüntüden "arttı/düştü" ASLA üretilmez.** Snapshot bir seviyedir,
    değişim değil; değişim yalnızca çeyreklik seriden gelir ve o seri de
    yalnızca dönemler bitişikse okunur -- sağlayıcı çeyrek atlıyor ve iki
    atlanmış çeyreği yan yana koymak "bir önceki çeyreğe göre" demeyi
    yanlış yapardı.
    """
    rows: list[dict] = []

    periods = (quarterly or {}).get("periods") or []
    if len(periods) >= 2 and (quarterly or {}).get("previous_is_adjacent"):
        current, previous = periods[0], periods[1]
        base = previous.get("net_income")
        latest = current.get("net_income")
        if base and latest is not None:
            change = (latest - base) / abs(base) * 100.0
            direction = UP if change > 0 else (DOWN if change < 0 else NEUTRAL)
            verb = "arttı" if change >= 0 else "azaldı"
            rows.append(_evidence(
                FUNDAMENTAL, "quarterly_net_income_qoq", direction,
                round(change, 1),
                f"{current.get('label') or 'son çeyrek'} net kârı bir önceki "
                f"çeyreğe göre %{technicals.format_number(abs(change))} {verb}",
            ))

    year_ago = _year_ago_period(periods) if (quarterly or {}).get("year_ago_available") else None
    if year_ago is not None:
        current = periods[0]
        base = year_ago.get("total_revenue")
        latest = current.get("total_revenue")
        if base and latest is not None:
            change = (latest - base) / abs(base) * 100.0
            direction = UP if change > 0 else (DOWN if change < 0 else NEUTRAL)
            verb = "arttı" if change >= 0 else "azaldı"
            rows.append(_evidence(
                FUNDAMENTAL, "quarterly_revenue_yoy", direction, round(change, 1),
                f"hasılatı geçen yılın aynı çeyreğine göre "
                f"%{technicals.format_number(abs(change))} {verb}",
            ))

    data = fundamentals or {}
    candidates = (
        _ratio_evidence(
            "return_on_equity", data.get("return_on_equity"), ROE_STRONG, ROE_WEAK,
            f"özkaynak kârlılığı %{technicals.format_number((data.get('return_on_equity') or 0) * 100)}",
        ),
        _ratio_evidence(
            "profit_margin", data.get("profit_margin"), MARGIN_STRONG, MARGIN_WEAK,
            f"net kâr marjı %{technicals.format_number((data.get('profit_margin') or 0) * 100)}",
        ),
        _ratio_evidence(
            "revenue_growth", data.get("revenue_growth"), GROWTH_STRONG, GROWTH_WEAK,
            f"yıllık hasılat büyümesi %{technicals.format_number((data.get('revenue_growth') or 0) * 100)}",
        ),
        _ratio_evidence(
            "debt_to_equity", data.get("debt_to_equity"), DEBT_HEAVY, DEBT_HEAVY,
            f"borç/özkaynak oranı %{technicals.format_number(data.get('debt_to_equity') or 0, 0)}",
            invert=True,
        ),
    )
    rows.extend(row for row in candidates if row is not None)
    return rows


# ── Haber kanıtı ────────────────────────────────────────────────────────────


def news_evidence(items: Sequence[Any], window_days: int = NEWS_WINDOW_DAYS) -> list[dict]:
    """Haber SAYISI ve türü; yön oyu YOK.

    Bilinçli: sistemde ölçülmüş bir duygu skoru yok (`sentiment` her satırda
    sabit `"neutral"`). Bir haber başlığından yön çıkarmak, ölçmediğimiz bir
    şeyi ölçmüş gibi göstermek olurdu. Kanıt olarak var -- kaç haber, kaçı
    KAP bildirimi -- ama yöne katılmıyor ve cümle bunu açıkça söylüyor.
    """
    if not items:
        return []
    filings = sum(1 for item in items if getattr(item, "source", None) == "KAP")
    text = f"son {window_days} günde {len(items)} haber etiketlendi"
    if filings:
        text += f" ({filings} KAP bildirimi)"
    return [_evidence(NEWS, "news_volume", NEUTRAL, len(items), text)]


# ── Birleştirme ─────────────────────────────────────────────────────────────


def _source_lean(rows: Iterable[dict]) -> Optional[float]:
    votes = [
        1.0 if row["direction"] == UP else (-1.0 if row["direction"] == DOWN else 0.0)
        for row in rows
    ]
    if not votes:
        return None
    return sum(votes) / len(votes)


def combine(evidence: Sequence[dict], horizon: str) -> dict[str, Any]:
    """Kanıtları tek bir meyle indirir.

    Ölçülemeyen kaynak DIŞLANIR ve kalan ağırlıklar yeniden normalize edilir --
    sıfır sayılmaz. `risk/profile.py:score_from` ile birebir aynı kural ve aynı
    gerekçe: ölçülemeyen bir düşüşü "düşüş yok" saymak, geçmişi kısa olan
    enstrümanı ödüllendirmek olurdu.
    """
    weights = HORIZONS[horizon]["weights"]
    by_source: dict[str, Optional[float]] = {}
    for source in (TECHNICAL, FUNDAMENTAL, NEWS):
        by_source[source] = _source_lean(
            [row for row in evidence if row["source"] == source]
        )

    measured = {s: lean for s, lean in by_source.items() if lean is not None}
    total_weight = sum(weights[s] for s in measured)
    lean = (
        sum(weights[s] * lean for s, lean in measured.items()) / total_weight
        if total_weight
        else 0.0
    )

    if len(evidence) < MIN_EVIDENCE or len(measured) < MIN_SOURCES:
        direction = "INSUFFICIENT"
    elif lean >= LEAN_THRESHOLD:
        direction = "UP_LEAN"
    elif lean <= -LEAN_THRESHOLD:
        direction = "DOWN_LEAN"
    else:
        direction = "MIXED"

    return {
        "direction": direction,
        "lean": round(lean, 3),
        "by_source": by_source,
        "sources_measured": len(measured),
    }


# ── Cümle ───────────────────────────────────────────────────────────────────

_LEAD_TR = {
    "UP_LEAN": "Yükseliş yönünde ölçülen kanıtlar ağır basıyor",
    "DOWN_LEAN": "Düşüş yönünde ölçülen kanıtlar ağır basıyor",
    "MIXED": "Ölçülen kanıtlar iki yöne birden işaret ediyor",
}

_OUTLOOK_FOR_LEAN = {"UP_LEAN": "UPTREND", "DOWN_LEAN": "DOWNTREND"}

#: Haberin neden yöne katılmadığını söyleyen cümle. Eksik bir ölçümü sessizce
#: geçmek yerine adıyla anmak, `technicals`in `None` döndürme kuralının
#: cümledeki karşılığı.
NEWS_CAVEAT_TR = "Haber içerikleri bu okumada tartılmadı"


def narrate(
    symbol: str,
    horizon: str,
    result: dict[str, Any],
    evidence: Sequence[dict],
    observations: Optional[int],
    missing: Sequence[str],
) -> str:
    """Okumanın kullanıcıya gösterilecek tam metni.

    Cümle BURADA kuruluyor, modelde değil -- `technicals.narrate()` ile aynı
    gerekçe. Koşullu devam okuması yalnızca bir yön ilan edildiğinde ekleniyor
    ve `HEDGE_TR` ondan ayrılamıyor: MIXED bir okumada devam cümlesi YOKTUR,
    çünkü devam edecek bir görünüm de yoktur.
    """
    label = HORIZONS[horizon]["label"]
    direction = result["direction"]

    if direction == "INSUFFICIENT":
        parts = [f"{symbol} için {label}lık bir yön okuması çıkaracak kadar ölçüm yok."]
        if observations is not None:
            parts.append(f"{observations} işlem günü fiyat geçmişi var.")
        # `missing` burada HER ZAMAN dolu ve bu bir değişmez: dört kapsama
        # anahtarının hepsi ölçülmüş olsaydı elde 4 kanıt ve 3 kaynak olurdu,
        # yani okuma INSUFFICIENT olmazdı. Koşul koymak, hiç girilmeyen bir
        # dal bırakmak olurdu.
        parts.append("Ölçülemeyen: " + ", ".join(missing) + ".")
        return " ".join(parts)

    supporting = [row["text"] for row in evidence if row["direction"] == UP] \
        if direction == "UP_LEAN" else \
        [row["text"] for row in evidence if row["direction"] == DOWN]
    opposing = [row["text"] for row in evidence if row["direction"] == DOWN] \
        if direction == "UP_LEAN" else \
        [row["text"] for row in evidence if row["direction"] == UP]

    lines = [f"{symbol} — {label}lık okuma. {_LEAD_TR[direction]}"]
    if direction == "MIXED":
        ups = [row["text"] for row in evidence if row["direction"] == UP]
        downs = [row["text"] for row in evidence if row["direction"] == DOWN]
        lines[0] += ": " + "; ".join(ups + downs) + "."
    else:
        lines[0] += ": " + "; ".join(supporting) + "."
        if opposing:
            lines.append("Karşı tarafta: " + "; ".join(opposing) + ".")

    outlook = _OUTLOOK_FOR_LEAN.get(direction)
    if outlook:
        # Koşullu okuma ve çekincesi AYNI cümlede. Ayırmak, koşulu düşürüp
        # iddiayı bırakmak olurdu.
        lines.append(
            f"{technicals._OUTLOOK_TR[outlook]} — {technicals.HEDGE_TR}."
        )

    if observations is not None:
        lines.append(f"{observations} işlem günü ölçüldü.")
    if any(row["source"] == NEWS for row in evidence):
        lines.append(NEWS_CAVEAT_TR + ".")
    return " ".join(lines)


def evaluate(
    symbol: str,
    horizon: str,
    signals: dict[str, Any],
    fundamentals: Optional[dict[str, Any]] = None,
    quarterly: Optional[dict[str, Any]] = None,
    news_items: Sequence[Any] = (),
) -> dict[str, Any]:
    """Bir enstrümanın yön okuması. Vade dışıysa okuma kurulmaz.

    Çağıran veritabanını okur ve hazır girdileri verir; bu fonksiyon saf
    kalır ve elle doğrulanabilir girdilere karşı test edilebilir.
    """
    if horizon not in HORIZONS:
        return {
            "symbol": symbol,
            "horizon": horizon,
            "direction": "OUT_OF_RANGE",
            "lean": None,
            "evidence": [],
            "coverage": {
                "sources_measured": 0,
                "evidence_count": 0,
                "missing": [],
                "observations": None,
            },
            "by_source": {},
            "narrative": OUT_OF_RANGE_TR,
            "horizon_note": None,
        }

    evidence = (
        technical_evidence(signals)
        + fundamental_evidence(fundamentals, quarterly)
        + news_evidence(list(news_items))
    )
    result = combine(evidence, horizon)

    present = {row["key"] for row in evidence}
    missing = [
        name for key, name in (
            ("sma_50_vs_200", "200 günlük ortalama"),
            ("quarterly_net_income_qoq", "çeyreklik kâr serisi"),
            ("return_on_equity", "temel veri"),
            ("news_volume", "haber"),
        )
        if key not in present
    ]

    observations = signals.get("observations")
    return {
        "symbol": symbol,
        "horizon": horizon,
        "direction": result["direction"],
        "lean": result["lean"],
        "evidence": evidence,
        "coverage": {
            "sources_measured": result["sources_measured"],
            "evidence_count": len(evidence),
            "missing": missing,
            "observations": observations,
        },
        "by_source": result["by_source"],
        "narrative": narrate(
            symbol, horizon, result, evidence, observations, missing
        ),
        "horizon_note": _horizon_note(horizon),
    }


def _horizon_note(horizon: str) -> str:
    """Ağırlıklandırmanın bir varsayım olduğunu söyleyen cümle.

    Söylenmesi şart: "3 aylık okuma" diyen bir cevap, o vadeye nasıl
    varıldığını göstermeden bir otorite iddiası taşır.
    """
    weights = HORIZONS[horizon]["weights"]
    return (
        f"{HORIZONS[horizon]['label']}lık okumada teknik göstergeler "
        f"%{int(weights[TECHNICAL])}, temel veriler %{int(weights[FUNDAMENTAL])} "
        f"ağırlıkla tartıldı; bu bir varsayım."
    )


async def refresh_all_signals() -> dict[str, int]:
    """Evrenin tamamı için yön okumalarını yeniden hesaplar.

    Gecelik iş. Neden burada değil de zamanlayıcıda tetikleniyor: hesap
    `market` modülünün işi, ne zaman çalışacağı uygulamanın.

    **Tek bir enstrümanın hatası turu düşürmez.** 1.011 enstrümanın birinde
    beklenmedik bir değer, tarama tablosunun tamamının boş kalması demek
    olmamalı -- ingestor'ın parçalı itme gerekçesiyle aynı.

    Yazma tek seferde: satır satır commit etmek, yarıda kesilen bir turda
    tablonun yarısını dünün, yarısını bugünün okumasıyla bırakırdı.
    """
    # Modül içi import: `signals` saf kalıyor ve veritabanını yalnızca bu
    # fonksiyon tanıyor. Üstte import etmek, saf motoru DB'ye bağlardı.
    from app.core.database import SessionLocal
    from app.modules.investment import market_service
    from app.modules.investment.models import InvestmentProduct
    from . import service as market_module, technicals

    written: dict[str, int] = {}
    db = SessionLocal()
    try:
        products = (
            db.query(InvestmentProduct)
            .filter(
                InvestmentProduct.status == "active",
                InvestmentProduct.product_type == "stock",
            )
            .all()
        )
        for horizon in HORIZONS:
            rows = []
            for product in products:
                try:
                    bars = market_service.candle_series(
                        db, product.symbol, limit=technicals.BARS_NEEDED
                    )
                    payload = evaluate(
                        product.symbol,
                        horizon,
                        technicals.compute(bars),
                        market_service.fundamentals_for(db, product.symbol),
                        market_service.quarterly_for(db, product.symbol),
                        market_module.latest_news(
                            db,
                            limit=NEWS_SAMPLE_LIMIT,
                            symbols=[product.symbol],
                            since=datetime.now(timezone.utc)
                            - timedelta(days=NEWS_WINDOW_DAYS),
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("direction failed for %s: %s", product.symbol, exc)
                    continue
                rows.append({
                    "product_id": product.id,
                    "horizon": horizon,
                    "symbol": product.symbol,
                    "direction": payload["direction"],
                    "lean": payload["lean"],
                    "evidence": payload["evidence"],
                    "observations": payload["coverage"]["observations"],
                    "narrative": payload["narrative"],
                    "computed_at": datetime.now(timezone.utc),
                })
            written[horizon] = market_module.store_direction_signals(db, rows)
        log.info("direction signals refreshed: %s", written)
        return written
    finally:
        db.close()
