"""Haber etkisi için DETERMİNİSTİK olgu paketi.

Bu modülde yorum yok ve olmayacak. Ürettiği her sayı ya sayılmış ya
ölçülmüş: kaç haber, kaçı KAP bildirimi, hissenin son beş işlem günündeki
gerçekleşen hareketi, o sembolde beş günlük hareketlerin tipik büyüklüğü,
sağlayıcının yayımladığı oranlar, ve sembolün sektörü.

**Yorumu `agents` yapıyor, burası değil.** Sistemin çıktı şablonu zaten
tahmin isteyen sorular için yazılmıştı -- "Artış lehine / Düşüş lehine",
sonra bu rakamların yakalamadığı şey, sonra bir kanaat cümlesi. Haber etki
analizi o şablonun İÇİNE oturuyor ve şablonun her maddesi "ölçülmüş bir
olgu, sayısıyla" istiyor. Bu modül tam olarak o maddeleri veriyor.

Ayrım neden önemli: bir modelin ürettiği yorum denetlenemez, ama üzerine
kurulduğu olgular denetlenebilir. Kullanıcı "bu rakam nereden geliyor" diye
sorduğunda cevabı olan bir sistem ile olmayan bir sistem arasındaki fark bu.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from . import service

#: Fiyat hareketinin ölçüldüğü ufuk ve ölçüm için gereken en az bar.
#: Bir haberin fiyata yansıması için makul bir pencere; `signals.py`'nin
#: aylık ufuklarından AYRI bir soru ve öyle kalması gerekiyor.
MOVE_WINDOW_DAYS = 5

#: Altında ölçüm YAPILMIYOR. On barlık bir seriden çıkan "tipik" bir sayı,
#: tipik olmayan bir şeyi tipik gibi gösterirdi.
MIN_BARS_FOR_TYPICAL = 40

#: Sembol başına taşınan en fazla başlık, ve pakete giren en fazla sembol.
#:
#: İkisi de ÖLÇÜLEREK kondu. Sınırsız paket 23 KB çıkıyordu ve tek başına
#: 8.000 token/dakika sınırını aşıyor: on altı pozisyon, sembol başına altı
#: başlık, ve KAP etiketlemesi yoğun olduğu için tek bir bankada doksan
#: günde 114 haber.
#:
#: Sembol sıralaması HABER SAYISINA göre: pencerede hakkında hiçbir şey
#: yayımlanmamış bir pozisyon, haber etkisi sorusunun cevabına en az katan
#: satır. Kesilen sembol sayısı `coverage`ta yazılı -- sessizce kırpılmış
#: bir portföy, "portföyünüzde şunlar oldu" cümlesini yanlış yapardı.
MAX_ARTICLES_PER_SYMBOL = 3
MAX_SYMBOLS = 5

#: Sağlayıcıdan taşınan oranlar. Tamamı DEĞİL: şablonun iki tarafına
#: gerçekten madde olabilecek olanlar. Bir bankanın brüt marjı yok ve
#: olmaması eksiklik değil, dolayısıyla eksik alan atlanıyor.
FUNDAMENTAL_KEYS = (
    "pe_ratio", "pb_ratio", "profit_margin", "return_on_equity",
    "debt_to_equity", "revenue_growth", "dividend_yield",
)


def typical_move(
    closes: Sequence[float], window: int = MOVE_WINDOW_DAYS
) -> Optional[float]:
    """Bu sembolde `window` işlem günlük hareketlerin tipik büyüklüğü (%).

    Medyan, ortalama değil: tek bir tavan/taban serisi ortalamayı kendine
    çeker ve "tipik" olmayan bir sayıyı tipik diye sunardı.

    Neden gerekli: bir hareketin "büyük" diye okunması, o hissede zaten
    olağan olan hareketin büyüklüğü bilinmeden anlamsız. %5 bir sembolde
    olağanüstü, başka birinde sıradan.
    """
    import statistics

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


def recent_move(
    closes: Sequence[float], window: int = MOVE_WINDOW_DAYS
) -> Optional[float]:
    """Son `window` işlem günündeki gerçekleşen değişim (%), İŞARETLİ.

    İşaret korunuyor: haberin yönüyle fiyatın yönünü yan yana koymak, ikisinin
    aynı şey olmadığını gösteren tek şey.
    """
    if len(closes) <= window or not closes[-window - 1]:
        return None
    return round((closes[-1] - closes[-window - 1]) / closes[-window - 1] * 100, 2)


def _article(row: Any) -> dict[str, Any]:
    """Bir başlık, ALINTILANABİLİR hâliyle.

    Başlık AYNEN taşınıyor. İçindeki talimat benzeri metin veridir ve burada
    temizlemek, onu yakalaması gereken katmandan gizlerdi -- RAG parçacığıyla
    aynı gerekçe.
    """
    return {
        "id": row.id,
        "title": row.title,
        "source": row.source,
        "published_at": row.published_at,
        # KAP bildirimi mi. İhraççısı makine okunur bir alanda yazılı,
        # dolayısıyla bir KAP satırının o şirkete bağlı olduğu ÖLÇÜLMÜŞ;
        # RSS'te eşleşme metinden çözülüyor ve daha zayıf. İkisini aynı
        # kefeye koymak, kapsamanın nereden geldiğini gizlerdi.
        "is_filing": row.source == "KAP",
    }


def fact_package(
    db: Session,
    holdings: Sequence[dict[str, Any]],
    closes_for: Any,
    fundamentals_for: Any,
    sectors: dict[str, str],
    days: int = service.NEWS_WINDOW_DAYS,
    limit: int = MAX_SYMBOLS,
) -> dict[str, Any]:
    """Kullanıcının pozisyonları için ölçülmüş olgular, sembol sembol.

    Okuma bloğu çağırandan geliyor (`closes_for`, `fundamentals_for`): bu
    modül veritabanı sorgusu yazmıyor ve yazmamalı -- ürettiği şey bir
    projeksiyon, bir okuma değil.

    Semboller HABER SAYISINA göre sıralanıp kırpılıyor: pencerede hakkında
    hiçbir şey yayımlanmamış bir pozisyon, haber etkisi sorusuna en az katan
    satır. Kaçının kesildiği `coverage`ta yazılı -- sessizce kırpılmış bir
    portföy, "portföyünüzde şunlar oldu" cümlesini yanlış yapardı.

    Sıfır haber, ölçülmüş bir SONUÇ: "o hisse hakkında bu pencerede bir şey
    yayımlanmadı" ile "veri gelmedi" karşıt iddialar. Bu yüzden sıfırlı
    semboller de sayılıyor (`symbols_with_news` ile birlikte okunuyor),
    yalnızca başlık taşımıyorlar.
    """
    symbols = service.held_symbols(holdings)
    rows, counts = service.portfolio_news(db, symbols, limit=200, days=days)

    by_symbol: dict[str, list[Any]] = {symbol: [] for symbol in symbols}
    for row in rows:
        for symbol in row.related_symbols or []:
            if symbol in by_symbol:
                by_symbol[symbol].append(row)

    names = {
        holding["symbol"]: holding.get("name") or holding["symbol"]
        for holding in holdings
        if holding.get("symbol")
    }

    # Kırpma SIRALAMADAN SONRA: en çok haberi olan sembol pakette kalmalı.
    ranked = sorted(symbols, key=lambda symbol: -counts.get(symbol, 0))
    kept = ranked[: max(1, limit)]

    out_symbols = []
    for symbol in kept:
        articles = by_symbol.get(symbol) or []
        closes = [close for _stamp, close in closes_for(symbol)]
        fundamentals = fundamentals_for(symbol) or {}
        measured = {
            key: fundamentals[key]
            for key in FUNDAMENTAL_KEYS
            # Eksik alan ATLANIYOR, sıfırlanmıyor: bir bankanın brüt marjı
            # yok ve onu 0 diye raporlamak, şirketin hiç sahip olmadığı bir
            # olguyu bildirmek olurdu.
            if fundamentals.get(key) is not None
        }
        out_symbols.append({
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "sector": sectors.get(symbol),
            "news_count": counts.get(symbol, 0),
            "filing_count": sum(1 for row in articles if row.source == "KAP"),
            "price": {
                "typical_move_pct": typical_move(closes),
                "recent_move_pct": recent_move(closes),
                "window_days": MOVE_WINDOW_DAYS,
            },
            "fundamentals": measured,
            "articles": [
                _article(row) for row in articles[:MAX_ARTICLES_PER_SYMBOL]
            ],
        })

    filings = sum(1 for row in rows if row.source == "KAP")
    return {
        "window_days": days,
        "symbols": out_symbols,
        # Hangi kaynaktan kaç belge geldi. Ölçüldü: son otuz günde RSS
        # haberlerinin yalnızca %5,6'sı bir sembole bağlanıyor, KAP'ta bu
        # oran %83 -- yani etki analizi pratikte KAP AĞIRLIKLI çalışıyor.
        # Bunu söylemeden bir okuma sunmak, dar bir kapsamı geniş gibi
        # göstermek olurdu.
        "coverage": {
            "articles": len(rows),
            "filings": filings,
            "feed_articles": len(rows) - filings,
            "symbols": len(symbols),
            "symbols_with_news": sum(
                1 for symbol in symbols if counts.get(symbol, 0) > 0
            ),
            # Kaç pozisyon pakete girmedi. Sıfır da yazılıyor: alanın
            # yokluğu ile sıfır olması aynı şey değil.
            "symbols_omitted": max(0, len(symbols) - len(kept)),
        },
    }
