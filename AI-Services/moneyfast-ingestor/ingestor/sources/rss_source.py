"""News from RSS feeds.

RSS is published so that machines can read it. That is the whole reason this
project uses it instead of scraping rendered pages: there is no bot check to
get past, because there was never a wall.

Courtesies (robots.txt, per-host delay, conditional requests) live in
`courtesy`, shared with the KAP source: the delay is per HOST, so two modules
keeping their own timers could each decide they had waited long enough.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from .. import config
from . import courtesy

log = logging.getLogger("moneyfast.ingestor.rss")

#: Kept as an alias so the shared caches can be cleared through either
#: module; the suite reaches for this one.
reset_state = courtesy.reset_state


#: HTML etiketleri. RSS özetleri işaretlemeyi olduğu gibi taşıyor -- ölçülen
#: örnek: `<img align="right" src="..." style="border: navy 1px solid;" />`.
_HTML_TAG = re.compile(r"<[^>]*>")


def clean_summary(raw: str) -> str:
    """Özetten işaretlemeyi atar, varlıkları çözer.

    İki yeri birden düzeltiyor. Sembol eşleştirmesi: temizlenmemiş metinde
    `<img align="right">` özniteliği Align Technology'ye (ALGN) bağlanıyordu.
    Ve daha önemlisi RAG: ingestor özeti korpusa `content` olarak gönderiyor,
    yani gömme vektörleri haberin metni yerine HTML gürültüsünü de taşıyordu
    -- ölçüldü, korpustaki 876 parça işaretleme içeriyor.

    Etiketin İÇİ değil KENDİSİ atılıyor: öznitelik adları ve URL'ler haberin
    metni değil. `&#039;` gibi varlıklar ise SİLİNMİYOR, çözülüyor: "Türkiye
    &#039;nin" -> "Türkiye'nin", yani metin okunur kalıyor.
    """
    text = _HTML_TAG.sub(" ", raw or "")
    # İki geçiş, çünkü beslemeler ÇİFT kaçışlı gönderiyor: ölçülen veride
    # `LPG&amp;#039;nin` var, tek geçiş bunu `&#039;`de bırakıyor. Kararlı
    # hâle gelince duruyor, sonsuz döngü yok.
    for _ in range(2):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return re.sub(r"\s+", " ", text).strip()


def content_hash(title: str, summary: str) -> str:
    """Deduplication key, shared with the rag service.

    Hashing the text rather than the URL because the same wire story is
    republished under different links, and some feeds renumber their URLs on
    every rebuild — which would re-import the whole history each poll.

    Beslemenin verdiği HAM özet üzerinden hesaplanıyor, temizlenmiş hâli
    üzerinden değil. Temizliğe geçerken hash tanımını da değiştirmek, daha
    önce alınmış her haberin kimliğini değiştirir ve arşivin tamamı "yeni"
    sayılıp yeniden yazılırdı.
    """
    return hashlib.sha256(f"{title}\n{summary}".strip().encode("utf-8")).hexdigest()


def _published(entry: Any) -> datetime:
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None) or (
            entry.get(field) if hasattr(entry, "get") else None
        )
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    # An undated article cannot be filtered by recency, and the retrieval
    # contract leans on published_at for "latest" queries. Stamping it now is
    # the least-wrong option and is at least monotonic with ingestion.
    return datetime.now(timezone.utc)


def _tickers(entry: Any) -> list[str]:
    """Ticker CANDIDATES the feed tagged. Never inferred from the headline.

    Guessing a ticker from prose would put one company's news on another
    company's page. These are candidates, not conclusions: the backend checks
    each one against the instrument universe before storing it, because the
    universe lives there and this process holds no database credentials.

    That check is what makes the loose shape test below safe. Turkish finance
    feeds file articles under sections like `BORSA` and `FINANS`, both of
    which pass "3-6 letters" and would otherwise be recorded as though they
    were listed companies. Neither is an instrument, so neither survives.
    """
    tags = getattr(entry, "tags", None) or []
    out = []
    for tag in tags:
        term = (tag.get("term") if hasattr(tag, "get") else None) or ""
        term = term.strip().upper()
        if term.isalpha() and 3 <= len(term) <= 6:
            out.append(term)
    return sorted(set(out))


#: Sections, taken from the article URL's first path segment, that a finance
#: app has no business storing.
#:
#: Turkish news feeds mix sections: `dunya.com/rss?dunya` and
#: `ekonomim.com/rss` are the SITE-WIDE feeds, so ingesting them brought in
#: football transfers, exam results and earthquake bulletins alongside the
#: economy stories. The section-specific query strings those sites appear to
#: offer (`?finans`, `?borsa`) are ignored by the server -- all return the same
#: homepage feed -- so the URL path is the only per-item section marker there
#: is.
#:
#: A DENYLIST rather than an allowlist, deliberately. This is the publisher's
#: own classification, and we can only name the sections we have seen; an
#: allowlist would silently discard any publisher that files finance news under
#: a name we did not think of (`/haber/`, `/analiz/`), and a missing news item
#: is invisible in a way a football headline is not. So: drop what is
#: positively identifiable as off-topic, keep everything else.
NON_FINANCIAL_SECTIONS = frozenset(
    {
        "spor",
        "gundem",
        "magazin",
        "saglik",
        "egitim",
        "yasam",
        "kultur-sanat",
        "kultur",
        "sanat",
        "otomobil",
        "seyahat",
        "astroloji",
        # Bir gazetenin hafta sonu eki: futbol, seyahat, portre. Ölçüldü --
        # bu bölümden gelen dört haberin dördü de finans dışıydı (Süper Lig,
        # Düzce gezisi, genç piyanist, Bodrum). Kullanıcının şikâyet ettiği
        # "Fenerbahçe" içeriği buradan geliyordu.
        "dunya-plus",
        "foto-galeri",
        "video-galeri",
        "galeri",
        "video",
    }
)


def _section(url: Optional[str]) -> Optional[str]:
    """The publisher's section for an article, from its URL path.

    Some sites nest under a language prefix (`aa.com.tr/tr/ekonomi/...`), so a
    two-letter first segment is skipped.
    """
    if not url:
        return None
    parts = [segment for segment in urlparse(url).path.split("/") if segment]
    if not parts:
        return None
    if len(parts[0]) == 2 and parts[0].isalpha():
        parts = parts[1:]
    return parts[0].lower() if parts else None


def is_financial(url: Optional[str]) -> bool:
    """Whether an article is something other than positively-identified noise.

    An unknown or missing section is KEPT -- see NON_FINANCIAL_SECTIONS for why
    the filter is shaped as a denylist.
    """
    section = _section(url)
    if section is None:
        return True
    return section not in NON_FINANCIAL_SECTIONS


def fetch_feed(url: str, client: httpx.Client) -> list[dict[str, Any]]:
    """One feed. Returns [] on any failure rather than raising.

    A single dead feed must not stop the run or blank the dashboard.
    """
    import feedparser

    if not courtesy.may_fetch(url, client):
        return []

    courtesy.wait_for_host(url)
    headers = {"User-Agent": config.user_agent()}
    headers.update(courtesy.validators.get(url, {}))

    try:
        response = client.get(url, headers=headers, timeout=config.request_timeout())
    except Exception as exc:
        log.warning("feed unreachable %s: %s", url, exc)
        return []

    if response.status_code == 304:
        log.info("feed unchanged since last poll: %s", url)
        return []
    if response.status_code == 429:
        log.warning("rate limited by %s, backing off until next cycle", url)
        return []
    if response.status_code >= 400:
        log.warning("feed %s returned %s", url, response.status_code)
        return []

    validators = {}
    if response.headers.get("ETag"):
        validators["If-None-Match"] = response.headers["ETag"]
    if response.headers.get("Last-Modified"):
        validators["If-Modified-Since"] = response.headers["Last-Modified"]
    courtesy.validators[url] = validators

    parsed = feedparser.parse(response.text)
    items = []
    skipped = 0
    for entry in parsed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        summary = (getattr(entry, "summary", "") or "").strip()
        if not title:
            continue
        link = getattr(entry, "link", None)
        if not is_financial(link):
            skipped += 1
            continue
        items.append(
            {
                # Hash HAM özetten, saklanan metin TEMİZ. İkisini ayırmak,
                # temizliğe geçerken arşivin kimliğini korumanın tek yolu.
                "content_hash": content_hash(title, summary),
                "title": title,
                "summary": clean_summary(summary) or None,
                "source": (getattr(parsed.feed, "title", "") or urlparse(url).netloc).strip(),
                "url": link,
                "language": "tr",
                "related_symbols": _tickers(entry),
                "published_at": _published(entry),
            }
        )
    log.info(
        "fetched %d items from %s (%d skipped as non-financial)", len(items), url, skipped
    )
    return items


def fetch_all(urls: Optional[list[str]] = None) -> list[dict[str, Any]]:
    urls = urls if urls is not None else config.feeds()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    with httpx.Client(follow_redirects=True, headers={"User-Agent": config.user_agent()}) as client:
        for url in urls:
            for item in fetch_feed(url, client):
                # Same story syndicated to two feeds: keep one.
                if item["content_hash"] in seen:
                    continue
                seen.add(item["content_hash"])
                items.append(item)
    return items
