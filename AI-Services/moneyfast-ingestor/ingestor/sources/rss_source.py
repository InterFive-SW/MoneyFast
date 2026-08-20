"""News from RSS feeds.

RSS is published so that machines can read it. That is the whole reason this
project uses it instead of scraping rendered pages: there is no bot check to
get past, because there was never a wall.

Three courtesies are observed anyway, because being technically allowed to
fetch something is not the same as being a good citizen of someone else's
server:

* `robots.txt` is checked before the first fetch of a host and honoured.
* Requests to one host are spaced by a minimum delay.
* Conditional requests (`If-None-Match` / `If-Modified-Since`) mean an
  unchanged feed costs the publisher a 304 rather than a full response.

The `User-Agent` names the project and links to it. If an operator wants us
gone, they can see who we are and say so.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .. import config

log = logging.getLogger("moneyfast.ingestor.rss")

#: Last fetch time per host, for the courtesy delay.
_last_request: dict[str, float] = {}

#: ETag / Last-Modified per feed URL, for conditional requests.
_validators: dict[str, dict[str, str]] = {}

#: robots.txt verdicts, per host. Cached for the process lifetime: re-fetching
#: it for every poll would itself be impolite.
_robots: dict[str, Optional[RobotFileParser]] = {}


def reset_state() -> None:
    """Clear the caches. For tests."""
    _last_request.clear()
    _validators.clear()
    _robots.clear()


def _may_fetch(url: str, client: httpx.Client) -> bool:
    if not config.respect_robots():
        return True

    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host not in _robots:
        parser = RobotFileParser()
        try:
            response = client.get(f"{host}/robots.txt", timeout=config.request_timeout())
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                # No robots.txt is permission by convention, not an error.
                parser = None
        except Exception as exc:
            log.warning("could not read robots.txt for %s: %s", host, exc)
            parser = None
        _robots[host] = parser

    parser = _robots[host]
    if parser is None:
        return True
    allowed = parser.can_fetch(config.user_agent(), url)
    if not allowed:
        log.warning("robots.txt disallows %s, skipping", url)
    return allowed


def _wait_for_host(url: str) -> None:
    host = urlparse(url).netloc
    delay = config.per_host_delay()
    previous = _last_request.get(host)
    if previous is not None:
        elapsed = time.monotonic() - previous
        if elapsed < delay:
            time.sleep(delay - elapsed)
    _last_request[host] = time.monotonic()


def content_hash(title: str, summary: str) -> str:
    """Deduplication key, shared with the rag service.

    Hashing the text rather than the URL because the same wire story is
    republished under different links, and some feeds renumber their URLs on
    every rebuild — which would re-import the whole history each poll.
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
    """Symbols the FEED tagged. Never inferred from the headline.

    Guessing a ticker from text would put one company's news on another
    company's page, and the retrieval contract lets the model filter on these.
    """
    tags = getattr(entry, "tags", None) or []
    out = []
    for tag in tags:
        term = (tag.get("term") if hasattr(tag, "get") else None) or ""
        term = term.strip().upper()
        if term.isalpha() and 3 <= len(term) <= 6:
            out.append(term)
    return sorted(set(out))


def fetch_feed(url: str, client: httpx.Client) -> list[dict[str, Any]]:
    """One feed. Returns [] on any failure rather than raising.

    A single dead feed must not stop the run or blank the dashboard.
    """
    import feedparser

    if not _may_fetch(url, client):
        return []

    _wait_for_host(url)
    headers = {"User-Agent": config.user_agent()}
    headers.update(_validators.get(url, {}))

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
    _validators[url] = validators

    parsed = feedparser.parse(response.text)
    items = []
    for entry in parsed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        summary = (getattr(entry, "summary", "") or "").strip()
        if not title:
            continue
        items.append(
            {
                "content_hash": content_hash(title, summary),
                "title": title,
                "summary": summary or None,
                "source": (getattr(parsed.feed, "title", "") or urlparse(url).netloc).strip(),
                "url": getattr(entry, "link", None),
                "language": "tr",
                "related_symbols": _tickers(entry),
                "published_at": _published(entry),
            }
        )
    log.info("fetched %d items from %s", len(items), url)
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
