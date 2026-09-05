"""Piyasayla ilgili mi? — anahtarlı haber sağlayıcıları için ikinci savunma.

**Siyaset haberi ELENMEZ.** Kuralı kullanıcı koydu ve doğru koydu:

> "that finance includes politic news. so that if someone starts a war or
>  something include them here cuz it makes the economics move."

Bir savaş ekonomik bir olaydır. Yaptırım, seçim, darbe, boğaz kapanması,
tarife -- hepsi fiyat kanalı. Bunları "siyaset" diye elemek, portföyü
gerçekten hareket ettiren haberi tam da hareket ettirdiği anda atmak olur.

Bu yüzden süzgeç "finans dışını at" DEĞİL, "piyasayla ilgisiz olanı at".
Ve `rss_source.NON_FINANCIAL_SECTIONS` ile aynı duruşta: **kara liste**,
izin listesi değil. Gerekçe orada yazılı ve burada da geçerli -- kaçırılan
bir haber görünmez, araya karışan bir futbol haberi görünür.

Fark şu: RSS'te sınıflandırma YAYINCININ kendi bölüm adından geliyordu
(`/spor/`). Burada öyle bir alan yok, dolayısıyla eleme başlık ve özet
metnine bakıyor ve bu daha kırılgan. O yüzden liste DAR tutuldu: yalnızca
tek anlamı olan, finansal bağlamda pratikte hiç geçmeyen sözcükler.
"""

from __future__ import annotations

import re
from typing import Any

#: Elenen konular. Her biri tek anlamlı ve finansal bir cümlede geçmiyor.
#:
#: `transfer` YOK: finansta da bir anlamı var (para transferi, hisse
#: transferi). `gol` YOK: "gol" bir sayı birimi olarak da geçebiliyor ve
#: `gold` içinde de var. Şüpheli her sözcük listeden ÇIKARILDI -- yanlış
#: eleme, elemesizlikten kötü.
_OFF_TOPIC = (
    # spor
    "football", "soccer", "basketball", "premier league", "champions league",
    "nba ", "nfl ", "fifa", "uefa", "olympic", "world cup", "transfer window",
    "süper lig", "fenerbahçe", "galatasaray", "beşiktaş", "trabzonspor",
    # magazin / ünlü
    "celebrity", "red carpet", "box office", "grammy", "oscars",
    "kardashian", "royal family", "magazin",
    # yerel asayiş / yaşam
    "horoscope", "astrology", "recipe", "obituary", "weather forecast",
    "burç", "astroloji", "yemek tarifi",
)

#: Elemeyi EZEN sözcükler.
#:
#: Bir haber hem sporu hem ekonomiyi anabiliyor ("Premier League broadcast
#: rights deal worth £6.7bn"), ve bu bir piyasa haberi. Bu liste, kara
#: listenin yanlış elediği durumu geri kazanıyor: ekonomik bir terim
#: geçiyorsa haber kalıyor.
_MARKET_TERMS = (
    "stock", "share", "bond", "yield", "inflation", "interest rate",
    "central bank", "federal reserve", "earnings", "revenue", "ipo",
    "merger", "acquisition", "dividend", "tariff", "sanction", "opec",
    "oil price", "commodity", "currency", "exchange rate", "gdp",
    "borsa", "hisse", "faiz", "enflasyon", "merkez bankası", "tahvil",
    "ihracat", "ithalat", "kur", "petrol", "yaptırım", "gümrük vergisi",
)


def _folded(item: dict[str, Any]) -> str:
    """Başlık ve özet, küçük harfe indirilmiş tek metin."""
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"
    return re.sub(r"\s+", " ", text).strip().lower()


def is_market_relevant(item: dict[str, Any]) -> bool:
    """Bu haber piyasa derlemesine girmeli mi?

    Sıra önemli: önce piyasa terimi aranıyor, sonra kara liste. Ters sırada
    "Premier League yayın hakları 6,7 milyar sterline satıldı" elenirdi --
    bir spor sözcüğü geçtiği için, bir satın alma haberi olduğu hâlde.

    Hiçbir şeye uymayan haber KALIYOR. Bu bir kara liste ve bilinmeyen
    konuyu atmak, izin listesine dönmek olurdu.
    """
    text = _folded(item)
    if any(term in text for term in _MARKET_TERMS):
        return True
    return not any(term in text for term in _OFF_TOPIC)
