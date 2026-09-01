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
import logging
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
    from_date: date, to_date: date, client: httpx.Client, depth: int = 0
) -> list[dict[str, Any]]:
    """Every disclosure in a date range, halving the range when truncated.

    A response of exactly `DISCLOSURE_CAP` rows is indistinguishable from a
    truncated one, so it is treated as truncated. The common case never
    bisects: the default window is sized well under the cap.
    """
    rows = _post_criteria(from_date, to_date, client)
    if rows is None:
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
    return enumerate_window(from_date, midpoint, client, depth + 1) + enumerate_window(
        midpoint + timedelta(days=1), to_date, client, depth + 1
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

    upper = until
    while upper >= since:
        lower = max(since, upper - timedelta(days=span - 1))
        for row in enumerate_window(lower, upper, client):
            item = normalise(row, universe)
            if item is None:
                dropped += 1
                continue
            if item["content_hash"] in seen:
                continue
            seen.add(item["content_hash"])
            items.append(item)
        upper = lower - timedelta(days=1)

    log.info(
        "KAP %s..%s: %d disclosures for instruments we hold (%d not ours)",
        since, until, len(items), dropped,
    )
    return items
