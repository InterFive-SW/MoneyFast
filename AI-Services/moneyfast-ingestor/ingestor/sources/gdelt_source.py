"""Küresel haber — GDELT Context 2.0 API.

RSS beslemeleri ve KAP Türkiye'yi karşılıyor; ikisi de yurt dışında ne olup
bittiğini görmüyor. Kullanıcının sorduğu şey tam olarak buydu: bir jeopolitik
gelişmenin petrol fiyatını, onun da havayolu maliyetini etkilediğini
anlatabilen bir sohbet. O zincirin ilk halkası derlemde yoksa geri kalanı
tahmin olur.

**Neden GDELT.** Açık ve ücretsiz bir araştırma veri seti; anahtar
gerektirmiyor ve şartları ticari kullanıma açıkça izin veriyor ("unlimited and
unrestricted use ... without fee"), karşılığında ATIF istiyor -- bkz.
`docs/GLOBAL_NEWS.md`. `api.gdeltproject.org` bir `robots.txt` yayımlamıyor,
yani teamül gereği izin var ve `courtesy.may_fetch` bunu zaten böyle okuyor.

**Neden DOC değil Context.** İki uç var. `doc/doc?mode=artlist` başlık ve
bağlantı veriyor, METİN vermiyor; `context/context` ise eşleşen CÜMLEYİ ve
onu saran paragrafı veriyor. Korpusa yalnızca başlık yazmak, "ABD'nin
saldırısı petrolü nasıl etkiler" sorusuna cevap veremeyen bir kayıt üretirdi
-- gömme vektörü on kelimeden çıkarılamaz. Ölçülen bir `context` alanı:

    "UBI also said a rate hike in October could not be ruled out if the US
    Federal Reserve raises rates in September... It added that oil prices
    above USD 90 a barrel could increase inflation and pressure on the
    rupee, while easing geopolitical tensions could give the RBI more
    policy flexibility."

Bunun ikinci bir faydası var: yayıncının kendi sayfası HİÇ çekilmiyor.
Metin GDELT'in kendi indeksinden geliyor, dolayısıyla üçüncü tarafların
`robots.txt`leri sorusu hiç doğmuyor.

**Ölçülen sınırlar** (varsayım değil, hepsi denendi):

* Hız: uç noktanın kendi 429 gövdesi *"Please limit requests to one every 5
  seconds"* diyor. Operatörün yazılı isteği; `MIN_HOST_DELAY_SECONDS` bunun
  altına inemiyor.
* `timespan`: 7 gün "The TIMESPAN is too large" ile reddediliyor, 3 gün
  çalışıyor.
* `maxrecords`: 250 "A maximum of 200 records can be returned" ile
  reddediliyor.
* Dil: bu uç İNGİLİZCE bir tam metin indeksi. `sourcelang:turkish`
  "Invalid/Unsupported Language" veriyor ve Türkçe bir ifade sorgusu boş
  `{}` dönüyor. Türkçe tarafı zaten RSS ve KAP karşılıyor; burası küresel
  tarafı karşılıyor ve ikisi çakışmıyor.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from .. import config
from . import courtesy

log = logging.getLogger("moneyfast.ingestor.gdelt")

#: Uç noktanın kendi 429 gövdesinde yazan sınır. Aşağı çekilemiyor: bu bir
#: tahmin değil, operatörün yazılı isteği.
MIN_HOST_DELAY_SECONDS = 5.0

#: `timespan=7d` reddediliyor, `3d` çalışıyor.
MAX_TIMESPAN_DAYS = 3

#: `maxrecords=250` reddediliyor.
MAX_RECORDS = 200

#: GDELT dili sözcük olarak yazıyor ("ENGLISH"), bizim şemamız iki harfli
#: kod tutuyor. Eşlenmeyen dil DÜŞÜRÜLMÜYOR, olduğu gibi küçültülüp
#: saklanıyor: tanınmayan bir dil, haberin kendisini atmak için sebep değil.
_LANGUAGES = {
    "ENGLISH": "en",
    "TURKISH": "tr",
    "GERMAN": "de",
    "FRENCH": "fr",
    "SPANISH": "es",
    "ARABIC": "ar",
    "RUSSIAN": "ru",
}


def content_hash(title: str, body: str) -> str:
    """Tekilleştirme anahtarı.

    `rss_source.content_hash` ile aynı biçim ve aynı gerekçe -- metinden,
    URL'den değil: aynı haber farklı bağlantılarla yeniden yayımlanıyor.
    Önek `gdelt:` DEĞİL: aynı haber hem bir RSS beslemesinden hem buradan
    gelirse ikisi AYNI satır olmalı, iki satır değil.
    """
    return hashlib.sha256(f"{title}\n{body}".strip().encode("utf-8")).hexdigest()


def _published(raw: Any) -> datetime:
    """`seendate` -> UTC. Biçim `20260904T121735Z`.

    Çözülemeyen bir damga ŞİMDİ olarak damgalanıyor, `rss_source._published`
    ile aynı gerekçeyle: tarihsiz bir haber tazelik süzgecinden geçemez ve
    "en son" sorularının dayanağı bu alan.
    """
    text = str(raw or "")
    try:
        return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        log.warning("unparsable seendate %r, stamping now", text)
        return datetime.now(timezone.utc)


def _language(raw: Any) -> str:
    text = str(raw or "").strip().upper()
    return _LANGUAGES.get(text, text.lower()[:10] or "en")


def _body(article: dict[str, Any]) -> str:
    """Saklanacak metin: paragraf varsa o, yoksa eşleşen cümle.

    `context` `sentence`i İÇERİYOR, dolayısıyla ikisini birleştirmek aynı
    cümleyi iki kez yazmak olurdu -- gömme vektöründe o cümleyi olduğundan
    ağır gösterirdi.
    """
    context = str(article.get("context") or "").strip()
    sentence = str(article.get("sentence") or "").strip()
    return context or sentence


def normalise(article: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Tek bir GDELT satırı -> sink'in beklediği haber sözlüğü.

    Başlığı ya da metni olmayan satır DÜŞÜYOR. Metin olmadan kayıt bir
    bağlantıdan ibaret kalır ve korpusa yazılmasının bütün sebebi metindi.
    """
    title = str(article.get("title") or "").strip()
    body = _body(article)
    if not title or not body:
        return None

    url = str(article.get("url") or "").strip() or None
    return {
        "content_hash": content_hash(title, body),
        "title": title,
        "summary": body,
        # Yayıncının alan adı. GDELT'in kendi adı DEĞİL: haberi yazan o
        # değil, indeksleyen o. Atıf `docs/GLOBAL_NEWS.md`de ve arayüzde.
        "source": str(article.get("domain") or "").strip() or "GDELT",
        "url": url,
        "language": _language(article.get("language")),
        # Sembol ÇIKARILMIYOR. Backend `symbol_match` ile evrene karşı
        # çözüyor ve bu süreçte veritabanı kredensiyeli yok -- RSS yolunun
        # aynısı.
        "related_symbols": [],
        "published_at": _published(article.get("seendate")),
    }


def fetch_query(query: str, client: httpx.Client) -> list[dict[str, Any]]:
    """Tek bir sorgu. Hata hâlinde `[]` döner, YÜKSELMEZ.

    Ölü bir sorgu turu durdurmamalı: haber toplama, tek bir konunun
    ulaşılamaz olmasından daha büyük bir iş.
    """
    url = f"{config.gdelt_base_url()}/api/v2/context/context"
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(min(MAX_RECORDS, config.gdelt_max_records())),
        "timespan": f"{min(MAX_TIMESPAN_DAYS, config.gdelt_timespan_days())}d",
    }

    if not courtesy.may_fetch(url, client):
        return []
    # Uç noktanın istediği 5 saniye, projenin varsayılan gecikmesinden uzun.
    courtesy.wait_for_host(url, minimum=MIN_HOST_DELAY_SECONDS)

    try:
        response = client.get(
            url,
            params=params,
            headers={"User-Agent": config.user_agent()},
            timeout=config.request_timeout(),
        )
    except Exception as exc:
        log.warning("gdelt unreachable for %r: %s", query, exc)
        return []

    if response.status_code == 429:
        # Gövdesi düz metin ve sınırı SÖYLÜYOR; loglanıyor ki bir sonraki
        # okuyan sayıyı koddan değil kaynağından öğrensin.
        log.warning("gdelt rate limited: %s", response.text.strip()[:200])
        return []
    if response.status_code >= 400:
        log.warning("gdelt returned %s for %r", response.status_code, query)
        return []

    try:
        payload = response.json()
    except ValueError:
        # Sınır ihlalleri JSON DEĞİL düz metin dönüyor ("The TIMESPAN is too
        # large.", "A maximum of 200 records can be returned."). Sessizce
        # boş geçmek, sorgunun yanlış kurulduğunu gizlerdi.
        log.warning("gdelt non-JSON reply for %r: %s", query, response.text.strip()[:200])
        return []

    articles = payload.get("articles") if isinstance(payload, dict) else None
    if not isinstance(articles, list):
        # Eşleşme yoksa uç `{}` dönüyor -- hata değil, ölçülmüş bir sessizlik.
        log.info("gdelt: no matches for %r", query)
        return []

    items = [normalise(row) for row in articles if isinstance(row, dict)]
    kept = [item for item in items if item is not None]
    log.info("gdelt: %d/%d usable rows for %r", len(kept), len(articles), query)
    return kept


def fetch_all(queries: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Yapılandırılmış her sorgu, tekilleştirilerek.

    Sorgular ARDIŞIK: eş zamanlı iki istek ölçüldüğünde 429 aldı. Beş
    saniyelik gecikme zaten sıraya sokuyor, paralellik yalnızca sınırı
    ihlal etmenin bir yolu olurdu.
    """
    queries = queries if queries is not None else config.gdelt_queries()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    with httpx.Client(
        follow_redirects=True, headers={"User-Agent": config.user_agent()}
    ) as client:
        for query in queries:
            for item in fetch_query(query, client):
                # Aynı haber iki konuya birden düşebiliyor (petrol sorgusu ile
                # jeopolitik sorgusu aynı yazıyı getiriyor).
                if item["content_hash"] in seen:
                    continue
                seen.add(item["content_hash"])
                items.append(item)
    log.info("gdelt: %d unique items across %d queries", len(items), len(queries))
    return items
