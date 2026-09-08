"""Haberin bir enstrümana etkisi: modelin yargısı, kodun ölçümü.

**İş bölümü tek cümlede:** modeli haberi YORUMLAMAK için kullanıyoruz, cümle
kurmak için değil. `agents` servisi her haber için yapılandırılmış satırlar
döndürüyor (`symbol`, `direction`, `scope`, `mechanism`), kod onları topluyor,
ölçülen sayılarla yan yana koyuyor ve kullanıcının okuduğu cümleyi KURUYOR.
Bu ayrım projede yeni değil -- `technicals.narrate()`, `profile.suitability()`
ve `allocation._statement()` aynı kalıbı kullanıyor: cümle kodda kurulur,
koşulludur, çekincesini aynı nefeste taşır.

Üç kilit, üçü de kodda çünkü prompt tavsiyedir:

1. **Sembol kapalı bir evrenden gelir.** Model yalnızca kendisine verilen
   listeden seçebiliyor ve `agents` tarafı listede olmayanı düşürüyor.
2. **Sayı modelden gelmez.** `mechanism` bir cümle; yüzdeler ve fiyat
   hareketleri `market_candles`tan ÖLÇÜLÜYOR. Modelin ürettiği bir yüzde,
   ölçülmemiş bir şeyi ölçülmüş gibi gösterirdi.
3. **Yasak dil satırı düşürür.** `mechanism` modelin yazdığı metin ve
   doğrudan kullanıcıya gidiyor; uygunluk kapısı ise yalnızca sohbet
   taslağına bakıyor (`orchestrator.py`). Bu yüzden depoda yazılı olan tek
   kural kümesi -- `compliance.rules` -- burada da uygulanıyor. Regex'leri
   kopyalamak, bir kuralın iki yerde yaşaması demek olurdu.

`market` modülünün `compliance`e olan bu bağımlılığı TEK YÖNLÜ ve saf:
`rules.find_violations` bir regex taraması, veritabanı görmüyor.
"""

import logging
import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.compliance.rules import find_violations

from .models import NewsImpact, NewsItem

log = logging.getLogger("moneyfast.market.news_impact")

UP = "UP"
DOWN = "DOWN"
NEUTRAL = "NEUTRAL"
DIRECT = "DIRECT"
SPILLOVER = "SPILLOVER"

#: Günlük özetin baktığı pencere. Bir GÜN, `NEWS_WINDOW_DAYS`in doksan günü
#: değil: bu ekranın sorusu "bugün portföyüme ne dokundu", "bu hisse hakkında
#: ne var" değil. İki pencereyi karıştırmak, üç haftalık bir başlığı bugünkü
#: gelişme gibi gösterirdi.
DIGEST_WINDOW_HOURS = 24

#: Yargılanacak haberin en fazla yaşı. Daha eskisi yargılanmıyor: bir haberin
#: etkisi hakkındaki yorum, o haber okunduğunda değerli.
JUDGE_WINDOW_HOURS = 48

#: Bir turda kaç haber yargılanır. Sınır token kotasından geliyor, tahminden
#: değil: Groq ücretsiz katmanı günde 200.000 token veriyor ve bir haber
#: yargısı ölçülen ~1.200 token tutuyor (yönerge + havuz + başlık + yanıt).
#: Günde iki tur x 40 haber ~ 96.000 token, yani kotanın yarısı; kalan yarı
#: sohbete kalıyor. Sohbeti aç bırakan bir arka plan işi, kullanıcının
#: gördüğü tek yüzeyi bozardı.
#:
#: Aşan haberler bir sonraki tura kalıyor -- kuyruk `pending_news` sorgusunun
#: kendisi, ayrı bir durum tablosu yok. Günde 400-800 haber geliyor,
#: dolayısıyla hepsi DEĞİL, önceliklendirilmiş bir kısmı yorumlanıyor;
#: sıralama etiketli haberi öne alıyor, yani portföye dokunanı.
JUDGE_BATCH_LIMIT = 40

#: `agents` servisine tek istekte gönderilen haber sayısı. Parçalama gerekçesi
#: `ingestor._push_fundamentals_chunked` ile aynı: tek gövdede giden kırk
#: haberin birinde çıkan hata, kırkını birden düşürürdü.
#:
#: On, yirmi değil: dakikada 8.000 token sınırı var ve haber başına bir LLM
#: turu düşüyor, yani bir parça zaten sınırın üzerinde. Küçük parça,
#: kesildiğinde daha azını kaybediyor.
JUDGE_CHUNK = 10

#: Tipik hareket ölçümü için gereken en az bar. Altında ÖLÇÜM YAPILMIYOR --
#: on barlık bir seriden çıkan "tipik" bir sayı, tipik olmayan bir şeyi
#: tipik gibi gösterirdi.
MIN_BARS_FOR_TYPICAL = 40

#: Tipik hareketin ölçüldüğü ufuk. Beş işlem günü: bir haberin fiyata
#: yansıması için makul, ve `signals.py`nin aylık ufuklarından ayrı bir soru.
MOVE_WINDOW_DAYS = 5

#: Her yüzeyde, koşulsuz. Kullanıcının okuduğu şey bir modelin yorumu ve bu
#: cümle onu söylüyor.
DISCLAIMER_TR = (
    "Bu özet, haber metinlerinin yapay zeka tarafından yorumlanmasıdır; "
    "yatırım tavsiyesi değildir ve haberin fiyata nasıl yansıyacağını "
    "belirlemez."
)

_DIRECTION_TR = {UP: "yükseliş", DOWN: "düşüş", NEUTRAL: "yön belirtmeyen"}

#: Gerekçenin en az uzunluğu. Prompt "tam bir cümle" diyor; bu onun ZEMİNİ.
#: Ölçüldü: gerçek çıktıda "Yönetim kurulu değişikliği" (26 karakter) gibi
#: etiketler geldi -- şirketin nasıl etkilendiğini hiç söylemeyen isim
#: tamlamaları. Otuz karakter bunları eliyor ve gerçek bir mekanizma cümlesine
#: dokunmuyor: ölçülen 23 satırın en kısa geçerli gerekçesi 44 karakter
#: ("Petrol fiyatlarındaki düşüş XOM'u etkiliyor.").
#:
#: Eşik bir DİL testi değil, bir taban: kısa bir metnin mekanizma olması
#: mümkün değil, uzun olması ise mekanizma olduğunu göstermiyor. Üst tarafı
#: prompt'un işi; prompt tavsiyedir, bu taban zorlayıcıdır.
MIN_MECHANISM_CHARS = 30


# ── Modelin çıktısını kabul etme ────────────────────────────────────────────


def acceptable(mechanism: str) -> bool:
    """Modelin yazdığı gerekçe kullanıcıya gösterilebilir mi.

    `CRITICAL` ve `HIGH` bulgular satırı DÜŞÜRÜYOR, düzeltmiyor: burada
    düzeltilecek bir taslak yok, tek cümlelik bir gerekçe var ve içinden bir
    parça kesilmiş bir gerekçe, gerekçe olmaktan çıkar. Aynı haber bir sonraki
    turda yeniden yargılanmaz -- yargılanmayan haber özetten düşer, ki bu
    yanlış bir gerekçe göstermekten iyidir.
    """
    text = (mechanism or "").strip()
    if len(text) < MIN_MECHANISM_CHARS:
        return False
    findings = find_violations(text, "STANDARD", contains_personal_data=False)
    return not any(
        finding["severity"] in ("CRITICAL", "HIGH") for finding in findings
    )


def store_impacts(
    db: Session,
    news_id: str,
    published_at: datetime,
    rows: Sequence[dict[str, Any]],
    model: Optional[str] = None,
) -> int:
    """Bir haberin etki satırlarını yazar.

    `ON CONFLICT DO NOTHING`: aynı haber aynı sembol için iki kez
    yargılanmıyor. İkinci bir yargı, birinciyle çelişse bile sessizce yanına
    eklenirdi ve günlük özet aynı haberi iki kez sayardı.
    """
    payload = [
        {
            "news_id": news_id,
            "symbol": row["symbol"],
            "direction": row["direction"],
            "scope": row.get("scope", DIRECT),
            "magnitude": row.get("magnitude", "LOW"),
            "confidence": row.get("confidence", 0.5),
            "mechanism": row["mechanism"].strip(),
            "published_at": published_at,
            "model": model,
            "analyzed_at": datetime.now(timezone.utc),
        }
        for row in rows
        if row.get("symbol") and row.get("direction") and acceptable(row.get("mechanism", ""))
    ]
    if not payload:
        return 0
    db.execute(
        insert(NewsImpact)
        .values(payload)
        .on_conflict_do_nothing(index_elements=["news_id", "symbol"])
    )
    return len(payload)


# ── Kuyruk ──────────────────────────────────────────────────────────────────


#: Sendikasyon ayıklaması için başlığın normalleştirilmiş hâli. Aynı ajans
#: haberi onlarca istasyonun sitesinde `"... | NewsRadio WIOD"` gibi kendi
#: kuyruğuyla yayımlanıyor ve `content_hash` bunları AYRI haber sayıyor --
#: haklı olarak, metinleri farklı. Yorum için ise aynı gelişme.
#:
#: Ölçüldü: 48 saatlik pencerede 787 haberin 667'si tekil, yani 120'si (%15)
#: aynı gelişmenin kopyası. Kopyaları yargılamak hem kotayı hem de özeti
#: bozardı: "bugün beş gelişme" diyen bir cümle, aslında tek bir gelişmeyi
#: beş kez saymış olurdu.
#: Yalnızca dikey çizgi. Tire ve uzun tire DIŞARIDA: KAP başlıkları
#: `"ŞİRKET A.Ş. — Kar Payı Dağıtım Bildirimi"` biçiminde ve o kuyruk
#: haberin KENDİSİ. Atılsaydı aynı şirketin aynı gündeki iki ayrı bildirimi
#: tek gelişme sayılırdı -- eleyicinin önlemesi gereken hatanın tersi.
#: Ölçülen %15'lik kopya oranının tamamı zaten dikey çizgiden geliyor.
_TITLE_TAIL = re.compile(r"\|[^|]{0,40}$")
_TITLE_NOISE = re.compile(r"[^0-9a-zçğıöşü ]+")


def title_key(title: str) -> str:
    """Sendikasyon kuyruğu atılmış, normalleştirilmiş başlık."""
    text = _TITLE_TAIL.sub("", (title or "").lower().strip())
    return _TITLE_NOISE.sub("", text).strip()


def pending_news(
    db: Session,
    limit: int = JUDGE_BATCH_LIMIT,
    hours: int = JUDGE_WINDOW_HOURS,
) -> list[NewsItem]:
    """Pencere içinde HENÜZ yargılanmamış haberler, yeniden eskiye.

    Kuyruk ayrı bir tabloda değil, sorgunun kendisinde: yazılmış bir etki
    satırı "bu haber işlendi" demek. Ayrı bir durum sütunu, satırlar yazılıp
    sütun yazılamadığında iki kaynağın ayrışacağı bir yer açardı.

    Etiketsiz haberler DIŞARIDA BIRAKILMIYOR. Bir faiz kararı hiçbir hisseyi
    etiketlemez ama neredeyse hepsine dokunur; yargının asıl kattığı değer
    tam orada. Etiketli olanlar önce geliyor çünkü kullanıcının portföyüne
    doğrudan dokunan haber, bütçe dolduğunda kesilmemesi gereken haberdir.

    Sendikasyon kopyaları eleniyor (`title_key`): hem bu turun içinde hem de
    pencerede ZATEN yargılanmış olanlara karşı. İkincisi olmadan aynı ajans
    haberi her turda bir kopyasıyla yeniden yargılanırdı.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    judged = select(NewsImpact.news_id).where(NewsImpact.published_at >= since)
    tagged = func.coalesce(func.array_length(NewsItem.related_symbols, 1), 0)

    seen = {
        title_key(title)
        for (title,) in db.execute(
            select(NewsItem.title).where(
                NewsItem.published_at >= since, NewsItem.id.in_(judged)
            )
        ).all()
    }
    seen.discard("")

    # Kopyalar elendikten sonra `limit` kadar haber kalması için fazlası
    # okunuyor. Çarpan ölçüme dayanıyor: kopya oranı %15, iki kat fazlası
    # rahat yetiyor ve okunan şey yalnızca bir başlık.
    rows = (
        db.execute(
            select(NewsItem)
            .where(NewsItem.published_at >= since, NewsItem.id.notin_(judged))
            .order_by(
                (tagged > 0).desc(),
                NewsItem.published_at.desc(),
                NewsItem.id.desc(),
            )
            .limit(max(1, limit) * 2)
        )
        .scalars()
        .all()
    )

    picked: list[NewsItem] = []
    for row in rows:
        key = title_key(row.title)
        if key and key in seen:
            continue
        seen.add(key)
        picked.append(row)
        if len(picked) >= max(1, limit):
            break
    return picked


def impacts_since(
    db: Session,
    symbols: Optional[Sequence[str]] = None,
    hours: int = DIGEST_WINDOW_HOURS,
    limit: int = 400,
) -> list[NewsImpact]:
    """Pencere içindeki etki satırları; `symbols` verilirse yalnızca onlar.

    Sembol süzgeci SUNUCUDA: portföy özeti "en yeni 400 satır"ın içinden
    kendi sembollerini ayıklamaya çalışsaydı, o dörtyüzde portföyün sembolü
    yoksa sonuç "haber yok" gibi okunurdu -- oysa soru hiç sorulmamış olurdu.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
    query = db.query(NewsImpact).filter(NewsImpact.published_at >= since)
    wanted = [symbol for symbol in dict.fromkeys(symbols or []) if symbol]
    if symbols is not None:
        if not wanted:
            return []
        query = query.filter(NewsImpact.symbol.in_(wanted))
    return (
        query.order_by(NewsImpact.published_at.desc(), NewsImpact.symbol)
        .limit(max(1, limit))
        .all()
    )


# ── Ölçüm: sayılar buradan gelir, modelden değil ────────────────────────────


def typical_move(closes: Sequence[float], window: int = MOVE_WINDOW_DAYS) -> Optional[float]:
    """Bu sembolde `window` işlem günlük hareketlerin tipik büyüklüğü (%).

    Medyan, ortalama değil: tek bir tavan/taban serisi ortalamayı kendine
    çeker ve "tipik" olmayan bir sayıyı tipik diye sunardı.

    Neden burada: bir haberin "büyük etki" diye okunması, o hissede zaten
    olağan olan bir hareketin büyüklüğü bilinmeden anlamsız. Model
    `magnitude` beyan ediyor; bu sayı onu ölçülen bir zemine oturtuyor.
    """
    if len(closes) < MIN_BARS_FOR_TYPICAL:
        return None
    moves = [
        abs(closes[index] - closes[index - window]) / closes[index - window] * 100
        for index in range(window, len(closes))
        if closes[index - window]
    ]
    if not moves:
        return None
    return round(statistics.median(moves), 2)


def recent_move(closes: Sequence[float], window: int = MOVE_WINDOW_DAYS) -> Optional[float]:
    """Son `window` işlem günündeki gerçekleşen değişim (%), işaretli.

    İşaret KORUNUYOR: haberin yönüyle fiyatın yönünü yan yana koymak, ikisinin
    aynı şey olmadığını gösteren tek şey. Mutlak değere indirmek, "yükseliş
    yönünde okundu ve fiyat da yükseldi" ile "okundu ama düştü" arasındaki
    farkı silerdi.
    """
    if len(closes) <= window or not closes[-window - 1]:
        return None
    return round((closes[-1] - closes[-window - 1]) / closes[-window - 1] * 100, 2)


# ── Toplama ve cümle ────────────────────────────────────────────────────────


def _tally(rows: Iterable[NewsImpact]) -> dict[str, int]:
    counts = {UP: 0, DOWN: 0, NEUTRAL: 0}
    for row in rows:
        if row.direction in counts:
            counts[row.direction] += 1
    return counts


def _lead(counts: dict[str, int]) -> str:
    """Sayımdan yön cümlesi. Eşitlik bir yön DEĞİL.

    Yönsüzlüğün iki ayrı hâli var ve karıştırılmıyor. Hiç yön okunmamışsa
    (hepsi NEUTRAL) "iki yöne birden" demek, ölçülmemiş bir çekişmeyi
    ölçülmüş gibi göstermek olurdu -- ölçüldü: iki NEUTRAL bildirim taşıyan
    VESTL, "iki yöne birden okundu" diye yazılıyordu.
    """
    if counts[UP] > counts[DOWN]:
        return "yükseliş yönünde okundu"
    if counts[DOWN] > counts[UP]:
        return "düşüş yönünde okundu"
    if counts[UP] == 0:
        return "yön belirtmeyen gelişmeler olarak okundu"
    return "iki yöne birden okundu"


def _pct(value: Optional[float]) -> str:
    return f"%{abs(value):.2f}".replace(".", ",")


def symbol_entry(
    symbol: str,
    rows: Sequence[NewsImpact],
    closes: Optional[Sequence[float]] = None,
) -> dict[str, Any]:
    """Tek sembol için özet satırı: sayım, gerekçeler ve ÖLÇÜLEN zemin.

    Gerekçeler modelin yazdığı hâliyle taşınıyor, birleştirilip yeniden
    yazılmıyor: iki gerekçeyi tek cümleye eritmek, hangisinin hangi haberden
    geldiğini okunamaz yapardı. `news_id` her satırda duruyor ki bir iddia
    kaynağına kadar izlenebilsin.

    Ölçüm cümlesi yalnızca ÖLÇÜLDÜĞÜNDE yazılıyor. Yetersiz bar için
    "hareket %0" demek, ölçülmemiş bir şeyi ölçülmüş gibi göstermek olurdu.
    """
    counts = _tally(rows)
    direct = [row for row in rows if row.scope == DIRECT]
    spill = [row for row in rows if row.scope == SPILLOVER]

    sentence = f"{symbol}: {len(rows)} haber yorumu, {_lead(counts)}."
    # Yayılma cümlesi üç ayrı hâlde kuruluyor. "Bunların 1 tanesi", tek satırlı
    # bir özette hem yanlış Türkçe hem de yanlış bilgi: sayılacak bir "bunlar"
    # yok. Doğrudan etkinin HİÇ olmadığı hâli ayrıca söylemek gerekiyor --
    # kullanıcı "bu hisse hakkında haber çıktı" diye okumamalı.
    if spill and not direct:
        sentence += (
            " Haberlerin hiçbiri doğrudan bu şirket hakkında değil;"
            " ilgili bir gelişmenin yansıması olarak okundu."
            if len(spill) > 1
            else " Haber doğrudan bu şirket hakkında değil;"
            " ilgili bir gelişmenin yansıması olarak okundu."
        )
    elif spill:
        sentence += (
            f" Bunların {len(spill)} tanesi doğrudan bu şirket hakkında değil,"
            " ilgili bir gelişmenin yansıması olarak okundu."
        )

    measured = None
    if closes is not None:
        typical = typical_move(closes)
        realized = recent_move(closes)
        if typical is not None and realized is not None:
            way = "yükseldi" if realized >= 0 else "geriledi"
            sentence += (
                f" Ölçülen: hisse son {MOVE_WINDOW_DAYS} işlem gününde"
                f" {_pct(realized)} {way}; bu sembolde {MOVE_WINDOW_DAYS} günlük"
                f" hareketler tipik olarak {_pct(typical)} büyüklüğünde."
            )
            measured = {"typicalMovePct": typical, "recentMovePct": realized}

    return {
        "symbol": symbol,
        "sentence": sentence,
        "counts": counts,
        "directCount": len(direct),
        "spilloverCount": len(spill),
        "measured": measured,
        "reasons": [
            {
                "newsId": row.news_id,
                "direction": row.direction,
                "scope": row.scope,
                "magnitude": row.magnitude,
                "mechanism": row.mechanism,
                "publishedAt": row.published_at,
            }
            for row in sorted(
                rows, key=lambda row: (float(row.confidence or 0)), reverse=True
            )
        ],
    }


def group_by_symbol(rows: Sequence[NewsImpact]) -> dict[str, list[NewsImpact]]:
    grouped: dict[str, list[NewsImpact]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)
    return grouped


def portfolio_headline(entries: Sequence[dict[str, Any]], hours: int) -> str:
    """Portföyün tamamı için tek cümle.

    Sayılan şey SEMBOL, haber değil: aynı haber üç hisseyi etkilediğinde
    "üç gelişme" demek, bir gelişmeyi üçe katlamak olurdu.
    """
    if not entries:
        return (
            f"Son {hours} saatte portföyünüzdeki enstrümanlara bağlanan bir"
            " haber yorumu bulunmuyor."
        )
    up = sum(1 for entry in entries if entry["counts"][UP] > entry["counts"][DOWN])
    down = sum(1 for entry in entries if entry["counts"][DOWN] > entry["counts"][UP])
    # Yönsüzlüğün iki hâli burada da ayrı: `_lead` ile aynı gerekçe. Yalnızca
    # NEUTRAL yorum almış bir enstrümanı "iki yöne birden" saymak, olmayan bir
    # çekişmeyi sayıya dökerdi.
    both = sum(
        1
        for entry in entries
        if entry["counts"][UP] == entry["counts"][DOWN] and entry["counts"][UP] > 0
    )
    flat = len(entries) - up - down - both
    parts = []
    if up:
        parts.append(f"{up} tanesi yükseliş yönünde")
    if down:
        parts.append(f"{down} tanesi düşüş yönünde")
    if both:
        parts.append(f"{both} tanesi iki yöne birden")
    if flat:
        parts.append(f"{flat} tanesi yön belirtmeyen gelişmeler olarak")
    return (
        f"Son {hours} saatte portföyünüzdeki {len(entries)} enstrüman haberlere"
        f" konu oldu; {', '.join(parts)} okundu."
    )


def market_entries(rows: Sequence[NewsImpact], limit: int = 12) -> list[dict[str, Any]]:
    """Piyasa geneli: hangi enstrüman, hangi yönde ve NEDEN.

    Sıralama etkilenen haber sayısına göre, `confidence`a göre DEĞİL: modelin
    kendi beyan ettiği güven bir ölçüm değil ve onunla sıralamak, ekrandaki
    sıraya ölçülmemiş bir otorite verirdi. Sayı ise sayılabilir bir olgu.
    """
    grouped = group_by_symbol(rows)
    entries = [
        symbol_entry(symbol, symbol_rows) for symbol, symbol_rows in grouped.items()
    ]
    entries.sort(key=lambda entry: (-sum(entry["counts"].values()), entry["symbol"]))
    return entries[: max(1, limit)]


# ── Toplu iş ────────────────────────────────────────────────────────────────


#: `agents` servisine verilen süre. Haber başına bir LLM turu var ve parça
#: yirmi haber; ölçülen tur ~1,5 saniye, yani parça başına yarım dakika. Üst
#: sınır bunun üç katı: yavaş bir sağlayıcı turu düşürmemeli, ama askıda
#: kalan bir istek de zamanlayıcının bir sonraki turunu bloke etmemeli.
JUDGE_TIMEOUT_SECONDS = 180


#: Yayılma havuzunun her borsadan aldığı sembol sayısı. Model, haberin
#: dokunduğu BAŞKA enstrümanları ancak kendisine verilen listeden seçebiliyor
#: ve evrenin tamamı (ölçüldü: 1.009 aktif enstrüman) her istekte ~2.500
#: token tutardı -- günlük kotanın tamamı, tek bir turda.
#:
#: Havuz ELLE SEÇİLMİYOR, ÖLÇÜLÜYOR: son kotasyondaki işlem hacmine göre
#: borsa başına ilk N. Endeks üyeliği lisanslı bir üründür ve elle yazılmış
#: bir "önemli hisseler" listesi, altından sessizce eskiyen bir varsayım
#: olurdu. Hacim ise her turda yeniden ölçülüyor.
SPILLOVER_POOL_PER_MARKET = 25


def _universe(db: Session, tagged: Sequence[str] = ()) -> list[str]:
    """Modelin seçebileceği enstrümanlar: haberin kendi etiketleri + havuz.

    Evren isteğin İÇİNDE gidiyor: `agents` servisinin veritabanı yok ve
    olmamalı. Kapalı liste aynı zamanda tek uydurma kilidi -- listede olmayan
    bir ad orada düşürülüyor.

    Haberin KENDİ etiketleri havuzdan bağımsız olarak ekleniyor: hacmi düşük
    bir hisse hakkındaki bir KAP bildirimi, o hisse havuza girmiyor diye
    yorumlanamaz hâle gelmemeli. Doğrudan etki her zaman sorulabilir olmalı;
    havuz yalnızca YAYILMANIN nereye bakabileceğini sınırlıyor.

    Hisse dışı enstrümanlar (kur, endeks, emtia) her zaman içeride ve sayıca
    az: bir faiz ya da enflasyon haberinin dokunduğu ilk şey onlar.
    """
    from app.modules.investment.models import InvestmentProduct, MarketQuote

    picks: list[str] = [symbol for symbol in dict.fromkeys(tagged) if symbol]

    non_equity = db.execute(
        select(InvestmentProduct.symbol)
        .where(
            InvestmentProduct.status == "active",
            InvestmentProduct.product_type != "stock",
        )
        .order_by(InvestmentProduct.symbol)
    ).all()
    picks.extend(symbol for (symbol,) in non_equity)

    # Hacim borsa BAŞINA sıralanıyor: farklı para birimlerindeki ciroları tek
    # listede karşılaştırmak, "bir fiyat para birimi olmadan taşınmaz"
    # kuralının ihlali olurdu. Ciro (adet x fiyat) çıplak adetten daha iyi bir
    # ölçü: adet sıralaması kuruş fiyatlı hisseleri başa taşıyor.
    turnover = (
        select(
            InvestmentProduct.market,
            InvestmentProduct.symbol,
            (MarketQuote.volume * MarketQuote.price).label("turnover"),
            func.row_number()
            .over(
                partition_by=InvestmentProduct.market,
                order_by=(MarketQuote.volume * MarketQuote.price).desc(),
            )
            .label("rank"),
        )
        .join(MarketQuote, MarketQuote.product_id == InvestmentProduct.id)
        .where(
            InvestmentProduct.status == "active",
            InvestmentProduct.product_type == "stock",
            MarketQuote.volume.isnot(None),
        )
        .subquery()
    )
    rows = db.execute(
        select(turnover.c.symbol)
        .where(turnover.c.rank <= SPILLOVER_POOL_PER_MARKET)
        .order_by(turnover.c.market, turnover.c.rank)
    ).all()
    picks.extend(symbol for (symbol,) in rows)

    return list(dict.fromkeys(picks))


async def analyze_recent_news() -> dict[str, int]:
    """Yargılanmamış haberleri `agents`e gönderir ve dönen satırları saklar.

    **Neden backend zamanlıyor ama yorumlamıyor:** CLAUDE.md'nin kuralı --
    "LLM çıkışı yalnızca `agents` servisinde ve yalnızca Groq'a". Burada
    kuyruk, evren ve saklama var; yorum orada.

    **Bir parçanın hatası turu düşürmez.** Yüz haberin yirmilik bir parçası
    zaman aşımına uğradığında kalan parçalar yazılmalı; aksi hâlde tek bir
    yavaş istek o günün özetini tamamen boş bırakırdı.

    Commit parça başına: turun tamamını tek transaction'da tutmak, yarıda
    kesilen bir turda yargılanmış ama saklanmamış haberler demekti -- ve
    kuyruk sorgusu onları yeniden gönderirdi, yani aynı token iki kez.
    """
    import httpx

    from app.core.config import settings
    from app.core.database import SessionLocal

    db = SessionLocal()
    stored = 0
    analyzed = 0
    failed = 0
    try:
        items = pending_news(db)
        if not items:
            log.info("news impact: yargılanacak haber yok")
            return {"analyzed": 0, "stored": 0, "failed": 0}
        by_id = {item.id: item for item in items}

        async with httpx.AsyncClient(timeout=JUDGE_TIMEOUT_SECONDS) as client:
            for start in range(0, len(items), JUDGE_CHUNK):
                chunk = items[start : start + JUDGE_CHUNK]
                # Evren PARÇA BAŞINA kuruluyor: havuz ortak ama haberin kendi
                # etiketleri parçadan parçaya değişiyor ve sabit bir evren,
                # hacmi düşük bir hisse hakkındaki bildirimi yorumlanamaz
                # bırakırdı.
                universe = _universe(
                    db,
                    [
                        symbol
                        for item in chunk
                        for symbol in (item.related_symbols or [])
                    ],
                )
                try:
                    response = await client.post(
                        f"{settings.AI_ORCHESTRATOR_URL}/analyze/news-impact",
                        json={
                            "items": [
                                {
                                    "news_id": item.id,
                                    "title": item.title,
                                    "summary": (item.summary or "")[:4000],
                                    "source": item.source,
                                }
                                for item in chunk
                            ],
                            "universe": universe,
                        },
                    )
                    response.raise_for_status()
                    body = response.json()
                except Exception as exc:  # noqa: BLE001
                    log.warning("news impact chunk failed: %s", exc)
                    failed += len(chunk)
                    continue

                model = body.get("model")
                for result in body.get("results") or []:
                    item = by_id.get(result.get("news_id"))
                    if item is None:
                        continue
                    analyzed += 1
                    stored += store_impacts(
                        db,
                        item.id,
                        item.published_at,
                        result.get("impacts") or [],
                        model=model,
                    )
                db.commit()

        log.info(
            "news impact: %d haber yorumlandı, %d satır saklandı, %d başarısız",
            analyzed, stored, failed,
        )
        return {"analyzed": analyzed, "stored": stored, "failed": failed}
    finally:
        db.close()
