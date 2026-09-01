"""Teknik göstergeler ve onları anlatan Türkçe cümle.

Saf fonksiyonlar: girdi OHLCV barları, çıktı sayılar ve metin. Veritabanı
yok, ağ yok — `risk/returns.py` ile aynı gerekçe, elle doğrulanabilir
girdilere karşı test edilebilsin diye.

**Yetersiz geçmişte alan `None` döner.** 200 günlük ortalama 200 bar ister;
60 barı olan bir enstrümanda o ortalama YOKTUR. Elde olan barlarla hesaplayıp
"200 günlük ortalama" demek, olmayan bir ölçümü varmış gibi göstermek olurdu
-- ısı haritasının piyasa değeri bilinmeyen enstrümanı çizmeyi reddetmesiyle
aynı kural.

Sayılar ile CÜMLE burada birlikte duruyor. Modele "şu göstergeleri yorumla"
demek, yorumun her turda biraz kayması demekti; hangi durumun hangi ifadeye
karşılık geldiği koda yazılı.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from app.modules.risk import returns as risk_returns

#: Hareketli ortalama pencereleri. 200 en uzun olan, yani en çok bar isteyen.
SMA_WINDOWS = (20, 50, 200)

#: RSI'ın standart penceresi. 14 dışında bir değer kullanılabilir ama
#: gösterge adıyla birlikte anılan sayı budur ve alan adı bunu taşıyor.
RSI_PERIOD = 14

#: "Son dönem" ne kadar: yükseliş/düşüş gün sayımı ve hacim karşılaştırması.
RECENT_WINDOW = 20

#: 52 hafta ≈ bir yıllık işlem günü.
YEAR_WINDOW = 252

#: Uç noktanın kaç bar okuyacağı. En uzun pencere 52 hafta aralığı (252);
#: 200 günlük ortalama onun içinde kalıyor. Fazlası okunmuyor: her ek bar
#: hiçbir göstergeye girmeden taşınan bir satır.
BARS_NEEDED = YEAR_WINDOW

#: Fiyatın bir ortalamaya göre "üzerinde/altında" sayılması için gereken en
#: küçük uzaklık. Binde birlik bir fark yön değil gürültüdür; eşiksiz bir
#: karşılaştırma her gün başka bir eğilim ilan ederdi.
TREND_EPSILON_PCT = 1.0

#: RSI eşikleri. Gelenek 70/30; burada YALNIZCA tanımlayıcı olarak
#: kullanılıyor -- "aşırı alım" bir değer yargısı değil, göstergenin kendi
#: terimi, ve cümlede o terimle değil ne ölçtüğüyle anlatılıyor.
RSI_HIGH = 70.0
RSI_LOW = 30.0


def _closes(bars: Sequence[dict[str, Any]]) -> list[float]:
    return [float(bar["close"]) for bar in bars]


def sma(values: Sequence[float], window: int) -> Optional[float]:
    """Son `window` değerin ortalaması; yeterli veri yoksa None."""
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def rsi(values: Sequence[float], period: int = RSI_PERIOD) -> Optional[float]:
    """Wilder'ın göreli güç endeksi, 0-100.

    `period + 1` kapanış gerekiyor: n fark için n+1 fiyat. Wilder'ın
    düzleştirmesi (basit ortalama değil) kullanılıyor -- gösterge adıyla
    anılan tanım bu, ve iki yöntem aynı seride farklı sayı üretir.
    """
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    # Pencere boyunca hiç düşüş yoksa RS tanımsız; gösterge tavanda.
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _pct_from(price: float, reference: Optional[float]) -> Optional[float]:
    if reference is None or reference == 0:
        return None
    return (price - reference) / reference * 100.0


def _range_position(price: float, low: float, high: float) -> Optional[float]:
    """Fiyatın [low, high] aralığındaki yeri, yüzde.

    High ile low eşitse aralık yoktur: tek fiyatta işlem görmüş bir seride
    "%50 seviyesinde" demek, olmayan bir aralığın ortasını işaret etmek olur.
    """
    if high <= low:
        return None
    return (price - low) / (high - low) * 100.0


def compute(bars: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Bir enstrümanın teknik durumu. Bar yoksa her alan None."""
    closes = _closes(bars)
    empty = {
        "observations": len(closes),
        "last_close": None,
        "sma_20": None, "sma_50": None, "sma_200": None,
        "pct_from_sma_20": None, "pct_from_sma_50": None, "pct_from_sma_200": None,
        "rsi_14": None,
        "week52_high": None, "week52_low": None, "week52_position_pct": None,
        "up_days_recent": None, "recent_window": None,
        "volume_vs_average": None,
        "annualised_volatility": None, "max_drawdown_pct": None,
        "trend": "UNKNOWN",
    }
    if not closes:
        return empty

    price = closes[-1]
    smas = {window: sma(closes, window) for window in SMA_WINDOWS}

    year = closes[-YEAR_WINDOW:]
    high, low = max(year), min(year)

    recent = closes[-(RECENT_WINDOW + 1):]
    up_days = (
        sum(1 for a, b in zip(recent, recent[1:]) if b > a)
        if len(recent) > 1
        else None
    )

    series = risk_returns.simple_returns(closes)
    drawdown = risk_returns.max_drawdown(closes, [bar["timestamp"] for bar in bars])

    return {
        "observations": len(closes),
        "last_close": price,
        "sma_20": smas[20], "sma_50": smas[50], "sma_200": smas[200],
        "pct_from_sma_20": _pct_from(price, smas[20]),
        "pct_from_sma_50": _pct_from(price, smas[50]),
        "pct_from_sma_200": _pct_from(price, smas[200]),
        "rsi_14": rsi(closes),
        "week52_high": high,
        "week52_low": low,
        "week52_position_pct": _range_position(price, low, high),
        "up_days_recent": up_days,
        "recent_window": len(recent) - 1 if len(recent) > 1 else None,
        "volume_vs_average": _volume_ratio(bars),
        "annualised_volatility": risk_returns.annualised_volatility(series),
        "max_drawdown_pct": _drawdown_pct(drawdown),
        "trend": classify(price, smas[20], smas[50]),
    }


def _drawdown_pct(drawdown: Any) -> Optional[float]:
    """`max_drawdown`'ın sözlüğünden yüzdeyi çıkarır.

    Anahtar `value` — kesir olarak, negatif. Hiç düşmemiş bir seride
    `max_drawdown` sözlük değil `None` döner ve burası da `None` döner:
    "en büyük düşüş: %0" demek, olmayan bir ölçümü sıfır diye raporlamak
    olurdu.
    """
    if not isinstance(drawdown, dict):
        return None
    value = drawdown.get("value")
    return None if value is None else float(value) * 100.0


def _volume_ratio(bars: Sequence[dict[str, Any]]) -> Optional[float]:
    """Son seansın hacmi, önceki `RECENT_WINDOW` seansın ortalamasına oranla.

    Son bar ortalamanın DIŞINDA tutuluyor: kendisini içeren bir ortalamaya
    bölmek, olağandışı bir günü kendi etkisiyle sönümler.
    """
    volumes = [bar.get("volume") for bar in bars]
    if len(volumes) < RECENT_WINDOW + 1 or volumes[-1] is None:
        return None
    window = [v for v in volumes[-(RECENT_WINDOW + 1):-1] if v is not None]
    if len(window) < RECENT_WINDOW:
        return None
    average = sum(window) / len(window)
    if average == 0:
        return None
    return float(volumes[-1]) / average


def classify(
    price: float, sma_20: Optional[float], sma_50: Optional[float]
) -> str:
    """Fiyatın iki ortalamaya göre konumu: yükseliş, düşüş ya da yatay.

    Her iki ortalamanın da üstünde olmak yükseliş, altında olmak düşüş
    sayılıyor; ikisi ayrışıyorsa yön yoktur ve "yatay" denir. İki ortalamanın
    çeliştiği bir seride tek birine bakıp yön ilan etmek, ölçümün
    söylemediğini söylemek olurdu.
    """
    if sma_20 is None or sma_50 is None:
        return "UNKNOWN"
    above_20 = _pct_from(price, sma_20)
    above_50 = _pct_from(price, sma_50)
    if above_20 is None or above_50 is None:
        return "UNKNOWN"
    if above_20 > TREND_EPSILON_PCT and above_50 > TREND_EPSILON_PCT:
        return "UPTREND"
    if above_20 < -TREND_EPSILON_PCT and above_50 < -TREND_EPSILON_PCT:
        return "DOWNTREND"
    return "SIDEWAYS"


#: Eğilimin adı. Sayıdan cümleye geçen tek yer burası.
_TREND_TR = {
    "UPTREND": "yükseliş eğiliminde",
    "DOWNTREND": "düşüş eğiliminde",
    "SIDEWAYS": "yatay seyrediyor",
    "UNKNOWN": "yönü ölçülemiyor",
}

#: Koşullu devam okuması. KOŞULLU olması esas: "bu görünüm sürerse" ile
#: başlayan bir cümle, gözlenen durumun devamından bahseder; "yükselecek"
#: gelecekten bahseder ve onu kimse bilmiyor.
_OUTLOOK_TR = {
    "UPTREND": (
        "Bu görünüm sürdüğü sürece yükseliş eğiliminin devamı beklenebilir"
    ),
    "DOWNTREND": (
        "Bu görünüm sürdüğü sürece düşüş eğiliminin devamı beklenebilir"
    ),
}

#: Her koşullu okumanın yanında duran çekince. Ayrılamaz: cümleyi ikiye bölüp
#: yalnızca ilk yarısını göstermek, koşulu düşürüp iddiayı bırakmak olur.
HEDGE_TR = "ancak geçmiş fiyat hareketi geleceği belirlemez"

#: Yeterince bar yoksa hiçbir şey söylenmez.
INSUFFICIENT_TR = (
    "Bu enstrüman için teknik bir görünüm çıkaracak kadar fiyat geçmişi yok."
)


#: Sayının okunuşuna göre iyelik+bulunma eki: "14'ünde", "3'ünde", "6'sında".
#:
#: Ek, rakamın YAZILIŞINA değil OKUNUŞUNA uyar -- "dört" ile bittiği için 14
#: "14'ünde"dir, "14'inde" değil. Tablo 0-20 ile sınırlı ve bu bilinçli:
#: `up_days_recent` en fazla `RECENT_WINDOW` olabiliyor, dolayısıyla üretilen
#: her sayı burada. Aralığın dışına çıkan bir değer sessizce yanlış ek almak
#: yerine eksiz kalır.
_LOCATIVE_TR = {
    0: "ında", 1: "inde", 2: "sinde", 3: "ünde", 4: "ünde", 5: "inde",
    6: "sında", 7: "sinde", 8: "inde", 9: "unda", 10: "unda", 11: "inde",
    12: "sinde", 13: "ünde", 14: "ünde", 15: "inde", 16: "sında",
    17: "sinde", 18: "inde", 19: "unda", 20: "sinde",
}


def _locative(count: int) -> str:
    """`14` -> `14'ünde`. Bilinmeyen sayı eksiz döner, uydurma ek almaz."""
    suffix = _LOCATIVE_TR.get(count)
    return f"{count}'{suffix}" if suffix else str(count)


def _tr(value: float, digits: int = 1) -> str:
    """Türkçe sayı biçimi: ondalık virgül, binlik nokta."""
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def narrate(symbol: str, signals: dict[str, Any]) -> Optional[str]:
    """Göstergeleri tek bir Türkçe paragrafa çevirir.

    Yalnızca ÖLÇÜLEN şeyleri söyler: hangi ortalamanın neresinde durduğu, kaç
    gün yükselerek kapattığı, 52 hafta aralığındaki yeri. Ardından koşullu bir
    devam okuması ve onun çekincesi gelir.

    Dönen metin kullanıcıya gösterilecek hâliyle tamdır; model onu yeniden
    yazmaz, olduğu gibi aktarır. Yorumu modele bırakmak, aynı sayıların her
    turda biraz farklı anlatılması demekti.
    """
    trend = signals.get("trend") or "UNKNOWN"
    if trend == "UNKNOWN" or signals.get("last_close") is None:
        return None

    facts: list[str] = []
    for window in (50, 20):
        distance = signals.get(f"pct_from_sma_{window}")
        if distance is None:
            continue
        side = "üzerinde" if distance >= 0 else "altında"
        facts.append(
            f"{window} günlük ortalamasının %{_tr(abs(distance))} {side}"
        )
        break

    up_days = signals.get("up_days_recent")
    window = signals.get("recent_window")
    if up_days is not None and window:
        facts.append(
            f"son {window} işlem gününün {_locative(up_days)} yükselerek kapattı"
        )

    position = signals.get("week52_position_pct")
    if position is not None:
        facts.append(f"52 hafta aralığının %{_tr(position)} seviyesinde")

    if not facts:
        return None

    body = f"{symbol}, " + ", ".join(facts) + f"; teknik olarak {_TREND_TR[trend]}."

    outlook = _OUTLOOK_TR.get(trend)
    if outlook:
        body += f" {outlook} — {HEDGE_TR}."
    return body


# ── Portföy geneli görünüm ───────────────────────────────────────────────────
#
# Motor tek enstrüman için yazılmıştı ve yalnızca hisse detay sayfasında ve
# sohbette tek sembolle çağrılıyordu. "Portföyümdeki hisseler teknik olarak
# nerede duruyor" sorusunun cevabı hesaplanabiliyordu ama hiçbir yerde
# toplanmıyordu.
#
# Toplulaştırma burada, uç noktada değil: cümleyi kim üretiyorsa hem ekran hem
# sohbet ondan okumalı. `narrate` ile aynı sebep -- aynı sayıların iki yüzeyde
# farklı anlatılması, kullanıcının hangisine güveneceğini bilememesi demek.


def _plural_locative(count: int) -> str:
    """`5` -> `5'i`, `1` -> `1'i`. Sayıdan cümleye geçen ikinci yer.

    `_locative` bulunma hâli üretiyor ("14'ünde"); burada gereken iyelik
    ("5'i"). Ayrı tablo değil, ayrı ek: aynı okunuşa farklı ek geliyor.
    """
    return f"{count}'{_POSSESSIVE_TR.get(count, 'i')}"


#: Sayının OKUNUŞUNA göre iyelik eki: "beş" -> "5'i", "altı" -> "6'sı".
#: Ünlüyle biten okunuşlar araya kaynaştırma alıyor. 0-20 arası yazılı; bir
#: portföyün pozisyon sayısı bunu aşabilir, o yüzden varsayılan var ve
#: varsayılan sessizce yanlış olmaktansa en yaygın eki kullanıyor.
_POSSESSIVE_TR = {
    0: "ı", 1: "i", 2: "si", 3: "ü", 4: "ü", 5: "i", 6: "sı", 7: "si",
    8: "i", 9: "u", 10: "u", 11: "i", 12: "si", 13: "ü", 14: "ü", 15: "i",
    16: "sı", 17: "si", 18: "i", 19: "u", 20: "si",
}

#: Toplulaştırmada kullanılan ortalama. 50 gün, 20 ya da 200 değil: 20 çok
#: kısa (her dalgalanmada taraf değiştiriyor), 200 ise evrenin bir kısmında
#: hiç hesaplanamıyor -- 200 barı olmayan bir enstrüman ölçülemeyen sayılır ve
#: portföyün yarısı "bilinmiyor" olarak dönerdi.
AGGREGATE_SMA = 50


def aggregate(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Pozisyonların teknik durumunun portföy geneli özeti.

    `rows`: her biri `symbol`, `signals` ve (varsa) `value` taşıyan pozisyonlar.
    `value`, taban para birimine ÇEVRİLMİŞ pozisyon değeri; çevrilemeyenlerde
    None ve o pozisyon ağırlık hesabına girmez (bkz. `ai_service.holding_value`
    -- kuru olmayan pozisyon toplama katılmaz, 1.0 varsayılmaz).

    SAYI VE DEĞER AYRI RAPORLANIYOR. Sekiz pozisyonun beşinin ortalamasının
    altında olması ile portföy değerinin %62'sinin altında olması farklı
    şeyler; büyük tek pozisyonlu bir portföyde ikisi zıt yönü gösterir. Tek
    bir yüzde vermek, hangisinin kastedildiğini okunamaz yapardı.
    """
    counts = {"UPTREND": 0, "DOWNTREND": 0, "SIDEWAYS": 0, "UNKNOWN": 0}
    unmeasured: list[str] = []
    below = above = 0
    value_below = value_total = 0.0

    for row in rows:
        signals = row.get("signals") or {}
        trend = signals.get("trend") or "UNKNOWN"
        counts[trend] = counts.get(trend, 0) + 1
        if trend == "UNKNOWN":
            unmeasured.append(row.get("symbol") or "?")

        distance = signals.get(f"pct_from_sma_{AGGREGATE_SMA}")
        if distance is None:
            # Ortalaması hesaplanamayan pozisyon hiçbir tarafa sayılmaz.
            # "Üstünde değil" ile "ölçülemedi" karşıt iddialar.
            continue
        value = row.get("value")
        if value is not None:
            value_total += float(value)
        if distance < 0:
            below += 1
            if value is not None:
                value_below += float(value)
        else:
            above += 1

    measured = below + above
    weight_below = (value_below / value_total) if value_total > 0 else None
    return {
        "position_count": len(rows),
        "measured_count": measured,
        "unmeasured_symbols": unmeasured,
        "by_trend": {key: counts[key] for key in ("UPTREND", "DOWNTREND", "SIDEWAYS")},
        f"below_sma_{AGGREGATE_SMA}": below,
        f"above_sma_{AGGREGATE_SMA}": above,
        f"weight_below_sma_{AGGREGATE_SMA}": weight_below,
        "statement": _aggregate_statement(
            len(rows), below, measured, weight_below, counts, unmeasured
        ),
    }


#: Portföyde hiç ölçülebilir pozisyon yoksa söylenen. Sayı üretmek yerine
#: neden üretilemediğini söylüyor.
NO_MEASURABLE_TR = (
    "Pozisyonlarınız için teknik bir görünüm çıkaracak kadar fiyat geçmişi yok."
)


def _aggregate_statement(
    total: int,
    below: int,
    measured: int,
    weight_below: Optional[float],
    counts: dict[str, int],
    unmeasured: Sequence[str],
) -> Optional[str]:
    """Toplulaştırmanın Türkçe okuması. Ölçülemeyeni gizlemez.

    Cümle "pozisyonunuzun" diyor, "portföyünüzün" değil: ikincisi değerden
    bahsediyormuş gibi okunur ve sayım değeri değil adedi ölçüyor. Değer
    payı ayrıca ve açıkça parantez içinde veriliyor.
    """
    if measured == 0:
        return NO_MEASURABLE_TR

    parts = [
        f"{total} pozisyonunuzun {_plural_locative(below)} "
        f"{AGGREGATE_SMA} günlük ortalamasının altında"
    ]
    if weight_below is not None:
        parts[0] += f" (portföy değerinin %{_tr(weight_below * 100)}'i)"

    trend_parts = [
        f"{_plural_locative(counts[key])} {_TREND_TR[key]}"
        for key in ("UPTREND", "DOWNTREND", "SIDEWAYS")
        if counts[key]
    ]
    if trend_parts:
        parts.append(", ".join(trend_parts))

    body = "; ".join(parts) + "."
    if unmeasured:
        body += (
            f" {len(unmeasured)} pozisyon için yeterli fiyat geçmişi yok: "
            + ", ".join(unmeasured) + "."
        )
    return body
