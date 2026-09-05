"""Where collected data goes.

Everything leaves this service over HTTP. It holds no database credential at
all, which is what keeps `base-db` and `vector-db` isolated: a service that
reaches the internet should not also hold a key to the application database.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from . import config

log = logging.getLogger("moneyfast.ingestor.sinks")


def _headers() -> dict[str, str]:
    headers = {"content-type": "application/json"}
    token = config.service_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _serialise(value: Any) -> Any:
    """datetime -> ISO 8601. json.dumps cannot do it and httpx uses json."""
    from datetime import datetime

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    return value


#: The symbol map, cached. At six cycles a minute an uncached lookup is six
#: backend round trips a minute for a table that changes when someone adds an
#: instrument — which is to say, almost never.
_products_cache: Optional[list[dict[str, str]]] = None
_products_fetched_at: float = 0.0
PRODUCTS_TTL_SECONDS = 300.0


def fetch_products(client: httpx.Client, force: bool = False) -> list[dict[str, str]]:
    """The symbol map, from the backend.

    Asked for rather than configured here, so adding an instrument is one row
    in the database instead of a redeploy of this service.

    Cached for PRODUCTS_TTL_SECONDS. A stale cache costs at most one cycle of
    not pricing a newly added instrument; an uncached read costs a round trip
    on every tick forever.
    """
    global _products_cache, _products_fetched_at

    import time

    fresh = (time.monotonic() - _products_fetched_at) < PRODUCTS_TTL_SECONDS
    if _products_cache is not None and fresh and not force:
        return _products_cache

    response = client.get(
        f"{config.backend_url()}/investment/products",
        headers=_headers(),
        timeout=config.request_timeout(),
    )
    response.raise_for_status()
    _products_cache = response.json()
    _products_fetched_at = time.monotonic()
    log.info("symbol map refreshed: %d instruments", len(_products_cache))
    return _products_cache


def fetch_candle_coverage(client: httpx.Client) -> dict[str, dict]:
    """How many daily bars the backend already holds, per symbol.

    Asked before the start-up backfill so it fetches only what is missing.
    Never cached: it is read once per process start, and a stale answer would
    mean either re-fetching history that is already stored or, worse, deciding
    an empty instrument is covered.

    A failure is not fatal -- an empty map reads as "nothing is covered",
    which makes the backfill do the complete, safe thing.
    """
    try:
        response = client.get(
            f"{config.backend_url()}/market/candles/coverage",
            headers=_headers(),
            timeout=config.request_timeout(),
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("candle coverage unavailable, assuming none: %s", exc)
        return {}


def fetch_known_news_ids(client: httpx.Client, source: str) -> set[int]:
    """Which disclosures the backend already holds, by their own numbering.

    Asked before the KAP cycle so only unseen disclosures cost a detail
    request. The list endpoint returns two thousand records every run and each
    body is a separate page; fetching without asking would mean re-requesting
    the same two thousand pages every fifteen minutes.

    A failure is not fatal -- an empty set reads as "nothing is stored", and
    the per-run detail cap keeps that from becoming a stampede.
    """
    try:
        response = client.get(
            f"{config.backend_url()}/market/news/known-ids",
            params={"source": source},
            headers=_headers(),
            timeout=config.request_timeout(),
        )
        response.raise_for_status()
        return {int(x) for x in (response.json().get("ids") or [])}
    except Exception as exc:  # noqa: BLE001
        log.warning("known news ids unavailable for %s, assuming none: %s", source, exc)
        return set()


def reset_products_cache() -> None:
    """For tests, and for a forced refresh after a universe change."""
    global _products_cache, _products_fetched_at
    _products_cache = None
    _products_fetched_at = 0.0


def push_market_data(
    client: httpx.Client, quotes: list[dict], candles: list[dict]
) -> Optional[dict]:
    if not quotes and not candles:
        return None
    payload = _serialise({"quotes": quotes, "candles": candles})
    try:
        response = client.post(
            f"{config.backend_url()}/market/ingest",
            json=payload,
            headers=_headers(),
            timeout=config.request_timeout() * 3,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        log.error("market ingest failed: %s", exc)
        return None


def push_fundamentals(client: httpx.Client, rows: list[dict]) -> Optional[dict]:
    if not rows:
        return None
    try:
        response = client.post(
            f"{config.backend_url()}/market/fundamentals/ingest",
            json=_serialise({"items": rows}),
            headers=_headers(),
            timeout=config.request_timeout() * 3,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        log.error("fundamentals ingest failed: %s", exc)
        return None


#: Tek istekte gönderilecek en fazla haber. RSS turu onlarca satır üretiyor
#: ve bu sınıra hiç yaklaşmıyor; KAP'ın altı aylık taraması ~15.000 satır
#: üretiyor. Tek gövdede göndermek, mumlarda bir kez ölçülen hatanın aynısı
#: olurdu: istek zaman aşımına uğradı, sink None döndü, tur "0 yazıldı" diye
#: raporladı ve hiçbir yerde hata görünmedi.
NEWS_PUSH_CHUNK = 500

#: Tek istekte gönderilen çeyreklik satır sayısı. Enstrüman başına 5-8 dönem
#: geliyor, dolayısıyla evrenin tamamı ~6.000 satır demek ve hepsini tek
#: gövdede yollamak hem isteği hem tek bir veritabanı işlemini gereksizce
#: büyütürdü.
QUARTERLY_CHUNK = 500


def push_quarterly(client: httpx.Client, rows: list[dict]) -> Optional[dict]:
    """Çeyreklik gelir tablosu satırlarını backend'e yazar.

    Parçalanarak: bir parça düşerse diğerleri yazılmış kalıyor. Seri
    birikimli olduğu için eksik bir parça bir sonraki turda tamamlanıyor --
    anlık görüntüden farkı bu, orada eksik tur eksik veri demekti.
    """
    if not rows:
        return None
    written = 0
    for start in range(0, len(rows), QUARTERLY_CHUNK):
        chunk = rows[start:start + QUARTERLY_CHUNK]
        try:
            response = client.post(
                f"{config.backend_url()}/market/quarterly/ingest",
                json=_serialise({"items": chunk}),
                headers=_headers(),
                timeout=config.request_timeout() * 3,
            )
            response.raise_for_status()
            written += (response.json() or {}).get("quarterly_written", 0)
        except Exception as exc:
            log.error("quarterly ingest failed for a chunk of %d: %s", len(chunk), exc)
    return {"quarterly_written": written}


def push_news_to_backend(client: httpx.Client, items: list[dict]) -> Optional[dict]:
    if not items:
        return None

    written = 0
    delivered = False
    #: Backend'in çözdüğü sembol haritası. PARÇALAR BOYUNCA BİRİKTİRİLİYOR:
    #: yalnızca son parçanınkini döndürmek, `run_news`'in RAG'a ilettiği
    #: haritayı sessizce eksiltirdi -- ve o harita olmayınca korpustaki her
    #: RSS belgesi tickersız kalıyor. Tam olarak bu ölçülmüştü: "1.970 RSS
    #: belgesinin SIFIRINDA ticker vardı".
    symbols: dict[str, list[str]] = {}
    for start in range(0, len(items), NEWS_PUSH_CHUNK):
        batch = items[start:start + NEWS_PUSH_CHUNK]
        try:
            response = client.post(
                f"{config.backend_url()}/market/news/ingest",
                json=_serialise({"items": batch}),
                headers=_headers(),
                timeout=config.request_timeout() * 3,
            )
            response.raise_for_status()
            body = response.json() or {}
            written += body.get("news_written", 0)
            symbols.update(body.get("news_symbols") or {})
            delivered = True
        except Exception as exc:  # noqa: BLE001
            # Bir parçanın düşmesi kalanını götürmüyor: bir sonraki tur
            # zaten aynı pencereyi yeniden sunacak ve kayıtlılar elenecek.
            log.error("news ingest failed for a batch of %d: %s", len(batch), exc)
    if not delivered:
        return None
    return {
        "quotes_written": 0, "candles_written": 0,
        "news_written": written, "news_symbols": symbols,
    }


def push_news_to_rag(
    client: httpx.Client,
    items: list[dict],
    symbols: Optional[dict[str, list[str]]] = None,
) -> int:
    """Chunk and embed each article into the vector store.

    One request per article because `rag /ingest` splits and embeds a single
    document; the service reports `duplicate` for content it already holds, so
    re-offering the same feed is a no-op rather than a second copy.

    Failures are counted, not raised. News that reaches the dashboard but not
    the corpus is a degraded state, not a broken one — the chatbot will simply
    say it found no sources, which is true.

    `symbols` backend'in ÇÖZDÜĞÜ etiketler, hash'e göre. Bu servis enstrüman
    evrenini tutmuyor ve tutmamalı (kredensiyeli yok), dolayısıyla bir RSS
    haberinin hangi şirketten bahsettiğini tek bilen backend. Bir dönem sonuç
    geri alınmıyordu ve korpusa giden kopya beslemenin kendi (boş) etiketiyle
    yazılıyordu: ölçüldü, 1.970 RSS belgesinin SIFIRINDA ticker vardı ve
    ajanın `tickers` filtresi yalnızca KAP bildirimlerinde çalışıyordu.
    """
    written = 0
    resolved = symbols or {}
    for item in items:
        body = {
            "title": item["title"],
            "source": item["source"],
            "category": "market-news",
            # KAP bildirimi bir HABER değil, ihraççının kendi beyanı --
            # birincil kaynak. Sözleşmenin donuk `doc_types` kümesinde bunun
            # karşılığı zaten var (`FILING`); yeni bir tür icat etmek,
            # dondurulmuş bir alana belgelenmemiş bir değer koymak olurdu.
            #
            # Ayrım ajanın işine yarıyor: "şirket şunu bildirdi" ile "bir
            # gazete şunu yazdı" farklı güvenilirlikte ve arama artık ikisini
            # süzebiliyor.
            "document_type": _document_type(item),
            "content": item.get("summary") or item["title"],
            "source_url": item.get("url"),
            "language": item.get("language", "tr"),
            # One ticker per document; the corpus schema carries a single
            # ticker column. Multi-tagged stories keep their first symbol and
            # remain findable by text.
            #
            # Backend'in çözdüğü etiket ÖNCELİKLİ: evren orada ve eşleştirme
            # orada yapılıyor. Kaynağın kendi etiketi (KAP `stockCode`) zaten
            # backend'den aynen geri geliyor, dolayısıyla bu bir üstüne yazma
            # değil; yalnızca çözülemediğinde elde olana düşülüyor.
            "ticker": _first_ticker(item, resolved),
            "published_at": item["published_at"],
        }
        try:
            response = client.post(
                f"{config.rag_url()}/ingest",
                json=_serialise(body),
                timeout=config.request_timeout() * 2,
            )
            response.raise_for_status()
            if response.json().get("status") == "ingested":
                written += 1
        except Exception as exc:
            log.warning("rag ingest failed for %r: %s", item["title"][:60], exc)
    return written


#: Kaynağı bildirim yayımlayan yerler. Şimdilik tek üye; liste, ikincisi
#: geldiğinde `if source == "KAP"` yazmaktan daha okunabilir olsun diye.
FILING_SOURCES = frozenset({"KAP"})


def _document_type(item: dict) -> str:
    """Korpusa yazılacak belge türü."""
    return "FILING" if item.get("source") in FILING_SOURCES else "NEWS"

def _first_ticker(item: dict, resolved: dict[str, list[str]]) -> Optional[str]:
    """Belgeye yazılacak tek sembol.

    Korpus şeması belge başına TEK ticker taşıyor. Birden fazla şirkete
    dokunan bir haber ilkini saklar ve gerisi metinden bulunabilir kalır --
    "BIST 100 değer kaybetti" gibi bir başlık dört şirketi anabiliyor.
    """
    candidates = resolved.get(item.get("content_hash") or "") or item.get("related_symbols")
    return (candidates or [None])[0]

#: Bir bildirimin kaç ihraççıya kadar korpusa yazılacağı. Bunun üstü,
#: endeks geneli ya da idari bir duyurudur: kırk şirkete etiketlenmiş bir
#: belge hiçbiri hakkında değildir ve hepsinin arama sonuçlarını kirletir.
MAX_ISSUERS_FOR_CORPUS = 5


def fetch_news_coverage(client: httpx.Client) -> dict[str, dict]:
    """Per source: how much news is held, how recent, and the highest index.

    Never cached, and a failure returns `{}` — which reads as "nothing is
    covered" and makes the caller do the complete thing. Same shape and same
    failure direction as `fetch_candle_coverage`.
    """
    try:
        response = client.get(
            f"{config.backend_url()}/market/news/coverage",
            headers=_headers(),
            timeout=config.request_timeout(),
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("news coverage unavailable, assuming none: %s", exc)
        return {}


def fetch_news_archive(
    client: httpx.Client, source: str, limit: int, offset: int
) -> list[dict]:
    """Saklanan bildirimlerin bir sayfası, yeniden eskiye."""
    try:
        response = client.get(
            f"{config.backend_url()}/market/news/archive",
            params={"source": source, "limit": limit, "offset": offset},
            headers=_headers(),
            timeout=config.request_timeout(),
        )
        response.raise_for_status()
        return response.json().get("items") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("news archive page unavailable: %s", exc)
        return []


def fetch_embedded_urls(client: httpx.Client, urls: list[str]) -> set[str]:
    """Bu bildirimlerden hangilerinin GÖVDESİ derlemde zaten var.

    Backend'deki `known-hashes` ile aynı desen ama farklı soru: orada
    "bu bildirimi biliyor muyuz", burada "metni gömülü mü". Panoya düşmüş
    olmak, sohbetin onu bulabilmesi demek değil.

    Hata durumunda BOŞ küme dönüyor -- yani "hiçbiri gömülü değil". Burada
    güvenli yön bu: fazladan indirilen bir gövde `ON CONFLICT` ile eleniyor,
    atlanan bir gövde ise sessiz bir boşluk bırakırdı.
    """
    if not urls:
        return set()
    try:
        response = client.post(
            f"{config.rag_url()}/documents/known-urls",
            json={"urls": urls},
            timeout=config.request_timeout() * 2,
        )
        response.raise_for_status()
        return set(response.json().get("known") or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("embedded-url lookup failed, assuming none: %s", exc)
        return set()


def push_disclosures_to_rag(client: httpx.Client, documents: list[dict]) -> int:
    """Embed KAP disclosure bodies into the corpus.

    `document_type` is **FILING**, a value the MCP contract's `doc_types` enum
    already carries. Inventing a KAP-specific type would mean reopening a
    frozen contract to add a value the model could never filter on, because
    it would not be in the enum the tool documents. `category` and `source`
    give two more filters for free, both already in `ALLOWED_FILTERS`.

    **Adres `#ekler` ile bitiyor, ve bu taşıyıcı.** Canlı akış (`run_news`)
    aynı bildirimin GÖVDESİNİ dakikalar içinde `/tr/Bildirim/{index}`
    adresiyle korpusa yazıyor. Aynı adresi kullansaydık
    `documents/known-urls` "bende var" derdi ve arşiv işi ekleri bir daha hiç
    okumazdı -- yani ekli bilançolar, tam da onlar için yazılmış yolun
    üstünden sessizce silinirdi. Parça hâlâ doğru KAP sayfasına çözülüyor,
    dolayısıyla atıf bozulmuyor.
    """
    written = 0
    for document in documents:
        symbols = document.get("related_symbols") or []
        if len(symbols) > MAX_ISSUERS_FOR_CORPUS:
            continue
        text = (document.get("text") or "").strip()
        if not text:
            continue

        body = {
            "title": document["title"],
            "source": "KAP",
            "category": "kap-disclosure",
            "document_type": "FILING",
            "content": text,
            "source_url": f"{document['url']}#ekler" if document.get("url") else None,
            "language": "tr",
            # The corpus carries ONE ticker column, so the primary filer wins
            # the filterable slot. Every issuer is named in the first line of
            # the text instead, which keeps a two-company merger notice
            # findable for both by semantic search.
            "ticker": symbols[0] if symbols else None,
            "published_at": document["published_at"],
        }
        try:
            response = client.post(
                f"{config.rag_url()}/ingest",
                json=_serialise(body),
                timeout=config.request_timeout() * 3,
            )
            response.raise_for_status()
            if response.json().get("status") == "ingested":
                written += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("rag ingest failed for %r: %s", document["title"][:60], exc)
    return written

def trigger_interest_accrual(client: httpx.Client) -> dict:
    """Vadeli hesap faizlerini işletmesi için backend'i uyarır.

    Faizi burada HESAPLAMIYOR: para bankacılık modülünün işi ve bu servisin
    veritabanı kredensiyeli yok. Yapılan tek şey, günde bir kez zamanlayıcının
    ürettiği tetiği iletmek.
    """
    response = client.post(
        f"{config.backend_url()}/banking/interest/accrue",
        headers=_headers(),
        timeout=config.request_timeout(),
    )
    response.raise_for_status()
    return response.json()


def fetch_intraday_symbols(client: httpx.Client) -> set[str]:
    """Gün içi bar gereken semboller, backend'e sorularak.

    Burada yapılandırılmıyor: kimin neyi tuttuğu uygulamanın bilgisi ve bu
    servisin veritabanı kredensiyeli yok.
    """
    response = client.get(
        f"{config.backend_url()}/market/candles/intraday-symbols",
        headers=_headers(),
        timeout=config.request_timeout(),
    )
    response.raise_for_status()
    return set((response.json() or {}).get("symbols") or [])


def fetch_missing_fundamentals(client: httpx.Client) -> set[str]:
    """Temel verisi eksik semboller, backend'e sorularak.

    Hepsini her açılışta çekmek yerine yalnızca eksikleri: çeyreklik raporlarla
    değişen oranları durmadan yeniden yazmanın anlamı yok.
    """
    response = client.get(
        f"{config.backend_url()}/market/fundamentals/missing",
        headers=_headers(),
        timeout=config.request_timeout(),
    )
    response.raise_for_status()
    return set((response.json() or {}).get("symbols") or [])


def push_sessions(client: httpx.Client, markets: set[str]) -> Optional[dict]:
    """Hangi piyasaların açık olduğunu backend'e bildirir.

    Saatler BURADA (`config.MARKET_HOURS`) ve burada kalıyor; backend'e kural
    değil olgu gidiyor. İkinci bir saat listesi tutmak, iki listenin
    ayrışmasına açık olurdu.

    Başarısızlık turu DÜŞÜRMEZ: seans bilgisi fiyatın üstüne konan bir
    açıklama, fiyatın kendisi değil.
    """
    try:
        response = client.post(
            f"{config.backend_url()}/market/sessions",
            json={"open": sorted(markets)},
            headers=_headers(),
            timeout=config.request_timeout(),
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        log.warning("session state push failed: %s", exc)
        return None


# ── TEFAS fonları ───────────────────────────────────────────────────────────

#: Tek istekte gönderilen fon satırı. Evren 2.602 fon ve hepsini tek gövdede
#: yollamak, `NEWS_PUSH_CHUNK`in var olma sebebinin aynısıyla kötü fikir.
FUND_PUSH_CHUNK = 500


def fetch_fund_coverage(client: httpx.Client) -> dict[str, Any]:
    """Backend'de neyin eksik olduğunu sorar.

    Şemsiye türü ve NAV serisi fon BAŞINA birer istek; sormadan çekmek her
    turda 2.602 isteği yeniden yapmak olurdu.
    """
    try:
        response = client.get(
            f"{config.backend_url()}/market/funds/meta/coverage",
            headers=_headers(),
            timeout=config.request_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        log.warning("fund coverage unavailable: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def push_funds_to_backend(
    client: httpx.Client,
    funds: list[dict[str, Any]],
    prices: Optional[list[dict[str, Any]]] = None,
) -> dict[str, int]:
    """Fonları ve NAV satırlarını backend'e yazar.

    Fiyatlar fon satırlarıyla AYNI istekte gitmiyor: bir fonun bir yıllık
    serisi ~250 satır ve 500 fonluk bir parçayla birleştiğinde gövde
    yönetilemez olurdu.
    """
    written = {"funds_written": 0, "prices_written": 0}
    for start in range(0, len(funds), FUND_PUSH_CHUNK):
        batch = funds[start:start + FUND_PUSH_CHUNK]
        result = _push_fund_batch(client, {"funds": batch, "prices": []})
        written["funds_written"] += result.get("funds_written", 0)

    rows = prices or []
    for start in range(0, len(rows), FUND_PUSH_CHUNK):
        batch = rows[start:start + FUND_PUSH_CHUNK]
        result = _push_fund_batch(client, {"funds": [], "prices": batch})
        written["prices_written"] += result.get("prices_written", 0)
    return written


def _push_fund_batch(client: httpx.Client, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = client.post(
            f"{config.backend_url()}/market/funds/ingest",
            json=body,
            headers=_headers(),
            timeout=config.request_timeout() * 3,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        log.warning("fund push failed: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}
