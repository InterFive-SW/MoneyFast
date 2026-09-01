"""KAP — Kamuyu Aydınlatma Platformu.

Every company traded on BIST is legally required to file its material events
here, so this is the one source in the project where a headline has an
authoritative issuer attached to it. The RSS feeds carry no reliable ticker at
all: `rss_source._tickers` can only read feed categories, and in practice
almost every item arrives with an empty `related_symbols`. A KAP disclosure
names its filer in a machine-readable field.

**Why this is not scraping.** KAP fronts a JSON API and serves it to an honest
`User-Agent` with no `Referer`, no session warm-up and no challenge — measured
2026-09-01, byte-identical responses with and without a spoofed referrer. The
courtesies in `courtesy` apply here exactly as they do to the feeds.

**Filtering is an allowlist, and that is deliberately the opposite of
`rss_source`.** There, a denylist is right because a missed news item is
invisible in a way a stray football headline is not. Here the target set is
enumerable and authoritative: we know precisely which symbols exist in
`investment_products`, and a disclosure naming none of them has nowhere in this
product to appear. Measured over one week, 592 of 1.101 disclosures map to a
symbol we hold; the rest are brokers, unlisted issuers and intermediaries.

**`relatedStocks` is not optional.** 218 of those 592 — 37% — match ONLY
through it: a broker files an insider-trading notice under its own
`stockCodes` while the company the notice is *about* sits in `relatedStocks`.
Reading `stockCodes` alone silently loses more than a third of the coverage.
"""

from __future__ import annotations

import hashlib
import html
import logging
from html.parser import HTMLParser
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from .. import config
from . import courtesy

log = logging.getLogger("moneyfast.ingestor.kap")

#: KAP publishes in Istanbul local time and says so nowhere in the payload.
ISTANBUL = ZoneInfo("Europe/Istanbul")

#: `byCriteria` truncates at this many elements and offers no pagination
#: token, so a response of exactly this length may be hiding more. Measured:
#: a 60-day window returned exactly 2000, a 7-day window returned 1101.
DISCLOSURE_CAP = 2000

#: How far a truncated window may be halved before we stop. A single day
#: holding more than the cap would be extraordinary against a measured ~157
#: disclosures/day, but a malformed date range must not recurse forever.
MAX_BISECT_DEPTH = 8

#: An issuer code is 3-6 alphanumerics. `stockCodes` mixes the traded ticker
#: with an issuer abbreviation ("YKB, YKBNK"); the universe intersection drops
#: the abbreviation without needing to know which is which.
_CODE_MIN, _CODE_MAX = 2, 6


def content_hash(disclosure_index: int | str) -> str:
    """Deduplication key, derived from KAP's own identifier.

    `rss_source.content_hash` hashes the text because a wire story has no
    stable id. A disclosure does: `disclosureIndex` is assigned by KAP and
    never changes. Hashing it rather than the text means re-fetching is free
    forever, and — the part that matters for the backfill — the hash is
    computable from the listing alone, so we can ask the backend which
    disclosures it already holds *before* spending a request on each body.

    An amendment is filed under its own index and therefore hashes to its own
    row. That is correct: it is a separate public act with its own timestamp,
    and collapsing it into the original would be rewriting a filings archive.
    """
    return hashlib.sha256(f"kap:{disclosure_index}".encode("utf-8")).hexdigest()


def permalink(disclosure_index: int | str) -> str:
    return f"{config.kap_base_url()}/tr/Bildirim/{disclosure_index}"


def _published(raw: Optional[str]) -> Optional[datetime]:
    """`"28.08.2026 23:15:00"` in Istanbul local time, to an aware UTC value.

    Returns None rather than guessing: `rss_source` may fall back to "now" for
    an undated feed entry, but a disclosure whose timestamp we cannot read is
    a parsing failure, and dating it now would place an old filing at the top
    of today's feed.
    """
    if not raw:
        return None
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            naive = datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=ISTANBUL).astimezone(timezone.utc)
    log.warning("unparseable publishDate %r", raw)
    return None


def issuer_codes(row: dict[str, Any]) -> set[str]:
    """Every issuer code the row names, from BOTH code fields."""
    out: set[str] = set()
    for field in ("stockCodes", "relatedStocks"):
        raw = row.get(field) or ""
        for token in raw.replace(";", ",").split(","):
            token = token.strip().upper()
            if _CODE_MIN <= len(token) <= _CODE_MAX and token.isalnum():
                out.add(token)
    return out


def _post_criteria(
    from_date: date, to_date: date, client: httpx.Client
) -> Optional[list[dict[str, Any]]]:
    """One `byCriteria` call. None means the call failed; [] means no rows."""
    url = f"{config.kap_base_url()}/tr/api/disclosure/members/byCriteria"
    if not courtesy.may_fetch(url, client):
        return None

    courtesy.wait_for_host(url)
    try:
        response = client.post(
            url,
            json={
                "fromDate": from_date.isoformat(),
                "toDate": to_date.isoformat(),
                # Empty means every member. Asking per issuer would be ~550
                # requests per window instead of one, which is the least
                # polite thing this module could do.
                "mkkMemberOidList": [],
                "subjectList": [],
            },
            headers={"User-Agent": config.user_agent()},
            timeout=config.request_timeout(),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("KAP unreachable for %s..%s: %s", from_date, to_date, exc)
        return None

    if response.status_code == 429:
        log.warning("rate limited by KAP, backing off until next cycle")
        return None
    if response.status_code >= 400:
        log.warning("KAP returned %s for %s..%s", response.status_code, from_date, to_date)
        return None

    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("KAP returned unparseable JSON: %s", exc)
        return None

    if not isinstance(payload, list):
        log.warning("KAP returned %s, expected a list", type(payload).__name__)
        return None
    return [row for row in payload if isinstance(row, dict)]


def enumerate_window(
    from_date: date, to_date: date, client: httpx.Client, depth: int = 0,
    failures: Optional[list] = None,
) -> list[dict[str, Any]]:
    """Every disclosure in a date range, halving the range when truncated.

    A response of exactly `DISCLOSURE_CAP` rows is indistinguishable from a
    truncated one, so it is treated as truncated. The common case never
    bisects: the default window is sized well under the cap.
    """
    rows = _post_criteria(from_date, to_date, client)
    if rows is None:
        # A window that failed is NOT a window with nothing in it. Recording
        # it is what stops a rate-limited run from reporting a smaller number
        # as though it were the whole answer -- measured once: a throttled
        # pass returned 14.589 where an unthrottled one returned 28.508, and
        # the log said "disclosures for instruments we hold" both times.
        if failures is not None:
            failures.append((from_date, to_date))
        return []
    if len(rows) < DISCLOSURE_CAP:
        return rows

    if from_date >= to_date or depth >= MAX_BISECT_DEPTH:
        log.warning(
            "KAP window %s..%s is at the %d cap and cannot be narrowed further; "
            "keeping what came back",
            from_date, to_date, DISCLOSURE_CAP,
        )
        return rows

    midpoint = from_date + (to_date - from_date) / 2
    log.info("KAP window %s..%s hit the cap, halving at %s", from_date, to_date, midpoint)
    return enumerate_window(
        from_date, midpoint, client, depth + 1, failures
    ) + enumerate_window(
        midpoint + timedelta(days=1), to_date, client, depth + 1, failures
    )


def normalise(row: dict[str, Any], universe: set[str]) -> Optional[dict[str, Any]]:
    """One listing row to the shape `sinks` already knows, or None to drop it.

    The same eight keys `rss_source` emits, so both sources push through the
    same sink with no branching there.
    """
    index = row.get("disclosureIndex")
    if index in (None, ""):
        return None

    symbols = sorted(issuer_codes(row) & universe)
    if not symbols:
        return None

    published = _published(row.get("publishDate"))
    if published is None:
        return None

    # `summary` is the specific thing that happened ("Pay Geri Alım
    # İşlemleri"); `subject` is the form it was filed on ("Payların Geri
    # Alınmasına İlişkin Bildirim"). Prefer the specific one, and prefix the
    # issuer so the headline stands on its own in a mixed feed.
    headline = (row.get("summary") or "").strip() or (row.get("subject") or "").strip()
    if not headline:
        return None
    company = (row.get("kapTitle") or "").strip()
    form = (row.get("subject") or "").strip()

    context = " · ".join(part for part in (company, form) if part)
    if row.get("modifyStatus") == "DUZENLENEN":
        # Visible in the text because there is nowhere else to put it: the
        # news table has no spare column and `rag.documents` has no metadata.
        context = f"{context} · Düzeltilmiş bildirim" if context else "Düzeltilmiş bildirim"

    return {
        "content_hash": content_hash(index),
        "title": f"{symbols[0]} — {headline}",
        "summary": context or None,
        "source": "KAP",
        "url": permalink(index),
        "language": "tr",
        "related_symbols": symbols,
        "published_at": published,
    }


class _Text(HTMLParser):
    """HTML to plain text, with the standard library and nothing else.

    KAP bodies are machine-generated, template-driven label/value tables —
    not arbitrary pages. There is no malformed-markup recovery problem here,
    which is the entire reason a parser like BeautifulSoup exists, so pulling
    one in (plus a C extension) to strip tags off a known template would be
    weight for a problem this module does not have. If the markup ever turns
    hostile, that is a reason to reconsider the source, not to escalate the
    parser.

    **Cells are separated by a tab, and that is load-bearing.** A disclosure's
    body IS a table: "Net Dönem Kârı" in one cell and the number in the next.
    Dropping the separator runs the label into the value and a balance sheet
    becomes a column of unlabelled numbers inside one chunk.
    """

    #: Their content is markup, not prose, and would otherwise be read out
    #: into the corpus as if it were text.
    _SILENT = {"script", "style"}

    #: Anything that ends a line when a human looks at the rendered page.
    _BREAKS = {
        "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "section", "article",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._muted = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SILENT:
            self._muted += 1
        elif tag == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SILENT:
            self._muted = max(0, self._muted - 1)
        elif tag in ("td", "th"):
            self._parts.append("\t")
        elif tag in self._BREAKS:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._muted:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = []
        for line in raw.split("\n"):
            # Tabs survive inside a line; runs of spaces around them do not.
            cleaned = "\t".join(cell.strip() for cell in line.split("\t")).strip("\t ")
            if cleaned:
                lines.append(" ".join(cleaned.split(" ")).strip())
        return "\n".join(lines).strip()


def html_to_text(fragments) -> str:
    """Join a disclosure body and flatten it.

    `disclosureBody` comes back as a LIST of HTML strings, not one string.
    """
    if isinstance(fragments, str):
        fragments = [fragments]
    if not isinstance(fragments, list):
        return ""

    parser = _Text()
    for fragment in fragments:
        if isinstance(fragment, str) and fragment.strip():
            try:
                parser.feed(fragment)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not parse a disclosure body fragment: %s", exc)
    return html.unescape(parser.text())


def fetch_detail(disclosure_index, client: httpx.Client) -> Optional[dict[str, Any]]:
    """One disclosure's body and attachment list, or None.

    None on any failure rather than raising: a single unreadable disclosure
    must not cost the cycle, and the listing row is already stored — the
    dashboard entry and its link survive a body we could not read.
    """
    url = f"{config.kap_base_url()}/tr/api/notification/attachment-detail/{disclosure_index}"
    if not courtesy.may_fetch(url, client):
        return None

    courtesy.wait_for_host(url)
    try:
        response = client.get(
            url,
            headers={"User-Agent": config.user_agent()},
            timeout=config.request_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read disclosure %s: %s", disclosure_index, exc)
        return None

    # A single-element array, consistently. Measured, not documented.
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    if not isinstance(payload, dict):
        log.warning("disclosure %s came back in an unexpected shape", disclosure_index)
        return None
    return payload


def body_text(detail: dict[str, Any]) -> str:
    return html_to_text(detail.get("disclosureBody"))


def pdf_attachments(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Attachments worth downloading.

    The listing carries `fileExtension`, so a non-PDF is skipped without
    spending a request on it.
    """
    out = []
    for attachment in detail.get("attachments") or []:
        if not isinstance(attachment, dict) or not attachment.get("objId"):
            continue
        extension = (attachment.get("fileExtension") or "").strip().lower()
        name = (attachment.get("fileName") or "").strip().lower()
        if extension == "pdf" or name.endswith(".pdf"):
            out.append(attachment)
    return out


#: Java `ObjectOutputStream` başlığı. Uç nokta `Content-Type: application/pdf`
#: diyor ve BU YALAN: gövde serileştirilmiş bir Java bayt dizisi.
JAVA_MAGIC = b"\xac\xed\x00\x05"

#: `TC_ENDBLOCKDATA TC_NULL` -- dizi verisinin başladığı yerin işareti.
ARRAY_MARKER = b"\x78\x70"

PDF_MAGIC = b"%PDF-"

#: `78 70` bir sınıf tanımının adının içinde de geçebilir, yani ilk eşleşme
#: doğru olan olmak zorunda değil. Birkaç kez denenip bırakılıyor.
MAX_MARKER_ATTEMPTS = 5

#: Sınırsız indirme yok. Ekli bir dosya ne kadar büyük olabileceğini
#: söylemiyor ve bir bildirim yüzünden belleği tüketmenin anlamı yok.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

#: Bir bildirimden en fazla kaç ek okunur.
MAX_ATTACHMENTS = 3

#: Ekten çıkarılan metnin üst sınırı. Backend'in kullanıcı yüklemeleri için
#: kullandığı 400.000'in bir mertebe altında, ve bu bilerek: orada belge tek
#: bir sohbete giriyor, burada PAYLAŞILAN korpusa. Parçalama 1.200 karakter,
#: yani 400.000 karakterlik bir faaliyet raporu ~330 parça demek ve o tek
#: bildirim, ilgili hissenin bütün arama yuvalarını kalıcı olarak sahiplenir.
MAX_PDF_CHARS = 40_000

#: Çözülemeyen ek sayısı. Bu, sürüm numarası olmadan değişebilecek,
#: belgelenmemiş bir uca dayanıyor: sayaç, bozulmayı görünür kılan tek şey.
unwrap_failures = 0

#: Çözülüp de okunamayan (yazı tipi eşlemesi olmayan) ek sayısı. Ayrı
#: tutuluyor: bu bir bozulma değil, kaynaktaki bir kalite sorunu.
unreadable_attachments = 0

#: Son `fetch_all` çağrısında okunamayan pencere sayısı. Sıfır değilse o tur
#: EKSİKTİR ve raporladığı sayı gerçeğin altındadır.
last_run_failures = 0


def reset_counters() -> None:
    """For tests."""
    global unwrap_failures, unreadable_attachments, last_run_failures
    unwrap_failures = 0
    unreadable_attachments = 0
    last_run_failures = 0


def unwrap_java_bytes(payload: bytes) -> Optional[bytes]:
    """Serileştirilmiş Java bayt dizisinden PDF'i çıkar.

    İki koruma bütün işi yapıyor ve ikisi de testte değil KODDA olmalı:

    1. **Çözdükten sonra `%PDF-` doğrulanır.** İşaret baytları bir sınıf
       tanımının adının içinde de geçebileceği için ilk eşleşme yanlış
       olabilir; sihirli sayı kontrolü, yanlış bir konumu korpusa çöp
       yazmak yerine `None`'a çeviren şey.
    2. **Uzunluk kalan tampona karşı denetlenir**, yoksa bozuk bir uzunluk
       gelişigüzel dilimler.
    """
    global unwrap_failures

    if payload.startswith(PDF_MAGIC):
        # Sağlayıcı fikrini değiştirirse diye: ham PDF de kabul.
        return payload
    if not payload.startswith(JAVA_MAGIC):
        unwrap_failures += 1
        return None

    marker = payload.find(ARRAY_MARKER)
    for _ in range(MAX_MARKER_ATTEMPTS):
        if marker < 0:
            break
        start = marker + 6
        length = int.from_bytes(payload[marker + 2 : start], "big")
        if 0 < length <= len(payload) - start:
            body = payload[start : start + length]
            if body.startswith(PDF_MAGIC):
                return body
        marker = payload.find(ARRAY_MARKER, marker + 1)

    unwrap_failures += 1
    log.warning("could not unwrap an attachment; KAP's envelope may have changed")
    return None


#: Düz Türkçe metinde pratikte hiç görünmeyen, ama gömülü alt-küme
#: yazı tipleri yanlış çözüldüğünde her yere serpilen karakterler.
_JUNK_CHARS = frozenset("{}[]\\|~^`§$*<>@#±¶©®™«»†‡•")

#: Bunun üstü, metnin çözülmüş değil bozulmuş olduğu anlamına gelir.
#: ÖLÇÜLDÜ: bozuk bir ek 0,0617; okunabilen beş ekin hepsi 0,0000-0,0001 --
#: aralarında, kelimesi az ama metni sağlam olan sayısal fiyat bültenleri de
#: var. İki mertebe fark, eşiğe geniş bir pay bırakıyor.
MAX_JUNK_RATIO = 0.01


def looks_extractable(text: str) -> bool:
    """Çıkarılan metin okunabilir mi, yoksa yazı tipi mi çözülememiş?

    KAP eklerinin bir kısmı, `ToUnicode` eşlemesi olmayan gömülü alt-küme
    yazı tipleriyle üretiliyor. `pypdf` bunlarda HATA VERMİYOR: geçerli
    görünen ama anlamsız bir metin döndürüyor
    (`§işlıııııi*ı, §ıın,'I'iı:.,,l.Ş.`). Korpusa böyle bir metin yazmak,
    hiç yazmamaktan kötü: aranabilir çöp, cevapsız kalmaktan daha zararlı.
    """
    if not text:
        return False
    return sum(1 for ch in text if ch in _JUNK_CHARS) / len(text) <= MAX_JUNK_RATIO


def pdf_text(payload: bytes) -> str:
    """PDF baytlarından metin. Aynı biçim `backend/.../documents.py:_read_pdf`.

    Kopyalandı, paylaşılmadı: backend ile ingestor arasında ortak bir paket
    yok ve on iki satır için beşinci bir dağıtılabilir birim yaratmak,
    çözdüğünden fazla sorun açardı.
    """
    from io import BytesIO

    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(payload))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read an attachment PDF: %s", exc)
        return ""
    text = "\n".join(part.strip() for part in pages if part.strip())
    if not looks_extractable(text):
        global unreadable_attachments
        unreadable_attachments += 1
        log.info("an attachment's fonts could not be decoded; skipping its text")
        return ""
    return text[:MAX_PDF_CHARS]


def fetch_attachment_text(obj_id: str, client: httpx.Client) -> str:
    """One attachment, downloaded, unwrapped and flattened. "" on any failure."""
    url = f"{config.kap_base_url()}/tr/api/file/download/{obj_id}"
    if not courtesy.may_fetch(url, client):
        return ""

    courtesy.wait_for_host(url)
    try:
        response = client.get(
            url,
            headers={"User-Agent": config.user_agent()},
            timeout=config.request_timeout() * 3,
        )
        response.raise_for_status()
        payload = response.content
    except Exception as exc:  # noqa: BLE001
        log.warning("attachment %s unreachable: %s", obj_id, exc)
        return ""

    if len(payload) > MAX_ATTACHMENT_BYTES:
        log.warning("attachment %s is %d bytes, over the cap; skipped", obj_id, len(payload))
        return ""

    unwrapped = unwrap_java_bytes(payload)
    if unwrapped is None:
        return ""
    return pdf_text(unwrapped)


def attachment_text(detail: dict[str, Any], client: httpx.Client) -> str:
    """Every readable PDF attached to one disclosure, joined."""
    parts = []
    for attachment in pdf_attachments(detail)[:MAX_ATTACHMENTS]:
        text = fetch_attachment_text(attachment["objId"], client)
        if text:
            name = (attachment.get("fileName") or "").strip()
            parts.append(f"[{name}]\n{text}" if name else text)
    return "\n\n".join(parts)


def fetch_all(
    universe: set[str],
    since: date,
    until: date,
    client: httpx.Client,
    window_days: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Disclosures between two dates that name an instrument we carry.

    Windows are walked NEWEST FIRST. An interrupted backfill then leaves a
    contiguous recent archive rather than a random scatter, and the half
    anyone will actually ask about lands in the first pass.
    """
    if not universe:
        log.warning("KAP: empty instrument universe, nothing could match; skipping")
        return []

    span = window_days or config.kap_window_days()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    dropped = 0

    failures: list = []
    upper = until
    while upper >= since:
        lower = max(since, upper - timedelta(days=span - 1))
        for row in enumerate_window(lower, upper, client, failures=failures):
            item = normalise(row, universe)
            if item is None:
                dropped += 1
                continue
            if item["content_hash"] in seen:
                continue
            seen.add(item["content_hash"])
            items.append(item)
        upper = lower - timedelta(days=1)

    if failures:
        log.warning(
            "KAP %s..%s: %d of the date windows could not be read (%s ...); "
            "this pass is INCOMPLETE and the counts below understate it",
            since, until, len(failures), failures[0][0],
        )
    log.info(
        "KAP %s..%s: %d disclosures for instruments we hold (%d not ours%s)",
        since, until, len(items), dropped,
        f", {len(failures)} windows unread" if failures else "",
    )
    last_run_failures = len(failures)
    globals()["last_run_failures"] = last_run_failures
    return items
