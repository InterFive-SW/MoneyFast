"""Anahtarlı haber sağlayıcıları — Finnhub ve Marketaux.

GDELT küresel makro tarafı karşılıyor ama şirket seviyesinde zayıf: indeksi
konu tabanlı, ticker tabanlı değil. Bu iki sağlayıcı o boşluğu dolduruyor.

**Neden bu ikisi.** Beş sağlayıcının güncel ücretsiz katmanı okundu:

| sağlayıcı | ücretsiz sınır | karar |
|---|---|---|
| Finnhub | 60 çağrı/dk | ALINDI -- açık ara en cömerti |
| Marketaux | 100 istek/gün x 3 makale | ALINDI -- ticker süzgeci var |
| Alpha Vantage | 25 istek/gün | alınmadı, saatte bir çağrıya denk |
| EODHD | 20 çağrı/gün | alınmadı, pratikte demo |
| NewsAPI | 100/gün | **alınmadı: şartları staging/production kullanımını YASAKLIYOR**, yalnızca localhost, 24 saat gecikme |

Son satır bir hız sorunu değil, lisans sorunu: dağıtılmış bir uygulamada
kullanmak şart ihlali olurdu.

**Anahtarı olmayan sağlayıcı sessizce atlanıyor.** Compose `${VAR:-}`
kullanıyor ve bu BOŞ DİZE üretiyor -- `getenv` için bu "set" demek, o yüzden
`os.getenv(...) or None` deseni zorunlu (`config.feeds()` aynı tuzağı
belgeliyor). `:?` KULLANILMIYOR: anahtarı olmayan herkesin `compose up`'ı
kırılırdı.

Çıkan sözlük diğer üç kaynağınkiyle BİREBİR aynı (8 anahtar,
`NewsItemIn` doğruluyor) ve `content_hash` öneksiz: aynı haber iki
sağlayıcıdan gelirse iki satır değil bir satır olmalı.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, NamedTuple, Optional

import httpx

from .. import config
from . import courtesy, relevance
from .gdelt_source import content_hash

log = logging.getLogger("moneyfast.ingestor.news_api")


class Provider(NamedTuple):
    """Bir haber sağlayıcısının tamamı: nereye, nasıl, ve cevabı nasıl okuruz."""

    #: Ortam değişkeninin adı. Yoksa sağlayıcı hiç çağrılmıyor.
    key_env: str
    base_url: str
    path: str
    #: İstek parametrelerini kuran fonksiyon; anahtarı da o yerleştiriyor
    #: çünkü sağlayıcılar anahtarı farklı adlarla istiyor (`token` / `api_token`).
    params: Callable[[str], dict[str, str]]
    #: Yanıt gövdesinden satır listesini çıkarır.
    rows: Callable[[Any], list[dict[str, Any]]]
    #: Tek satırı ortak haber sözlüğüne çevirir; okunamayan satırda None.
    normalise: Callable[[dict[str, Any]], Optional[dict[str, Any]]]
    #: İstekler arası en az bekleme. Sağlayıcının kendi sınırından geliyor.
    min_delay: float


# ── Finnhub ────────────────────────────────────────────────────────────────

def _finnhub_rows(payload: Any) -> list[dict[str, Any]]:
    """Finnhub düz bir dizi döndürüyor, zarf yok."""
    return [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []


def _finnhub_item(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    title = str(row.get("headline") or "").strip()
    if not title:
        return None
    summary = str(row.get("summary") or "").strip()
    # `datetime` saniye cinsinden epoch. Sayı değilse haber tarihlenemiyor
    # ve tazelik süzgecinden geçemez; atılıyor.
    stamp = row.get("datetime")
    if not isinstance(stamp, (int, float)) or stamp <= 0:
        return None
    return {
        "content_hash": content_hash(title, summary),
        "title": title,
        "summary": summary or None,
        # Yayıncının adı; Finnhub indeksleyen taraf, yazan değil.
        "source": str(row.get("source") or "").strip() or "Finnhub",
        "url": str(row.get("url") or "").strip() or None,
        "language": "en",
        # Sembolü backend çözüyor: enstrüman evreni orada, burada değil.
        "related_symbols": [],
        "published_at": datetime.fromtimestamp(float(stamp), tz=timezone.utc),
    }


# ── Marketaux ──────────────────────────────────────────────────────────────

def _marketaux_rows(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _marketaux_item(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    title = str(row.get("title") or "").strip()
    if not title:
        return None
    summary = str(row.get("description") or row.get("snippet") or "").strip()
    published = _parse_iso(row.get("published_at"))
    if published is None:
        return None
    return {
        "content_hash": content_hash(title, summary),
        "title": title,
        "summary": summary or None,
        "source": str(row.get("source") or "").strip() or "Marketaux",
        "url": str(row.get("url") or "").strip() or None,
        "language": str(row.get("language") or "en").strip().lower()[:10] or "en",
        # `entities` ticker taşıyor ama BURADA okunmuyor: sembol çözümü tek
        # bir yerde, backend'de. İki yerde çözmek, iki farklı evren demek.
        "related_symbols": [],
        "published_at": published,
    }


def _parse_iso(raw: Any) -> Optional[datetime]:
    """`2026-09-05T09:12:00.000000Z` -> tz-aware UTC. Çözülemezse None.

    `rss_source`in aksine ŞİMDİ ile damgalanmıyor: burada tarih sağlayıcının
    zorunlu alanı ve gelmemesi bir biçim değişikliği demek. Sessizce bugüne
    damgalamak, eski bir haberi yeni gibi gösterirdi.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        log.warning("unparsable published_at %r", text)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


PROVIDERS: dict[str, Provider] = {
    "finnhub": Provider(
        key_env="FINNHUB_API_KEY",
        base_url="https://finnhub.io",
        path="/api/v1/news",
        params=lambda key: {"category": "general", "token": key},
        rows=_finnhub_rows,
        normalise=_finnhub_item,
        # 60 çağrı/dk = saniyede bir; bir saniye bırakmak sınırın yarısında
        # kalmak demek ve tur zaten saatte bir.
        min_delay=1.0,
    ),
    "marketaux": Provider(
        key_env="MARKETAUX_API_KEY",
        base_url="https://api.marketaux.com",
        path="/v1/news/all",
        params=lambda key: {
            "api_token": key,
            "language": "en",
            "filter_entities": "true",
            "limit": "3",
        },
        rows=_marketaux_rows,
        normalise=_marketaux_item,
        # 100 istek/gün. Saatte bir tur, tur başına birkaç istek: rahat.
        min_delay=2.0,
    ),
}


def fetch_provider(name: str, client: httpx.Client) -> list[dict[str, Any]]:
    """Tek sağlayıcı. Hata hâlinde `[]` döner, YÜKSELMEZ.

    Ölü bir sağlayıcı turu durdurmamalı: haber toplama, tek bir servisin
    ulaşılamaz olmasından daha büyük bir iş.
    """
    provider = PROVIDERS[name]
    key = config.news_api_key(provider.key_env)
    if not key:
        # Anahtarsız sağlayıcı bir hata değil, bir tercih. Bu satır INFO,
        # WARNING değil: kurulmamış bir sağlayıcı her saat uyarı basmamalı.
        log.info("%s: no %s set, skipping", name, provider.key_env)
        return []

    url = f"{provider.base_url}{provider.path}"
    if not courtesy.may_fetch(url, client):
        return []
    courtesy.wait_for_host(url, minimum=provider.min_delay)

    try:
        response = client.get(
            url,
            params=provider.params(key),
            headers={"User-Agent": config.user_agent()},
            timeout=config.request_timeout(),
        )
    except Exception as exc:
        log.warning("%s unreachable: %s", name, exc)
        return []

    if response.status_code == 429:
        log.warning("%s rate limited: %s", name, response.text.strip()[:200])
        return []
    if response.status_code == 401 or response.status_code == 403:
        # Anahtar yanlış ya da süresi dolmuş. Ayrı loglanıyor: "anahtar yok"
        # ile "anahtar kabul edilmedi" farklı tamir talimatları.
        log.warning("%s rejected the API key (%s)", name, response.status_code)
        return []
    if response.status_code >= 400:
        log.warning("%s returned %s", name, response.status_code)
        return []

    try:
        payload = response.json()
    except ValueError:
        log.warning("%s non-JSON reply: %s", name, response.text.strip()[:200])
        return []

    rows = provider.rows(payload)
    items = [provider.normalise(row) for row in rows]
    usable = [item for item in items if item is not None]
    kept = [item for item in usable if relevance.is_market_relevant(item)]
    log.info(
        "%s: %d rows, %d usable, %d market-relevant", name, len(rows), len(usable), len(kept)
    )
    return kept


def fetch_all(names: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Yapılandırılmış her sağlayıcı, tekilleştirilerek."""
    names = names if names is not None else list(PROVIDERS)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    with httpx.Client(
        follow_redirects=True, headers={"User-Agent": config.user_agent()}
    ) as client:
        for name in names:
            for item in fetch_provider(name, client):
                # Aynı haber iki sağlayıcıdan gelebiliyor.
                if item["content_hash"] in seen:
                    continue
                seen.add(item["content_hash"])
                items.append(item)
    log.info("news apis: %d unique items across %d providers", len(items), len(names))
    return items
