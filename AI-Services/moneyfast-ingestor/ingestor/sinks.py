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

# Mirrored wire-contract limits from backend SocialIngestRequest. Delivery uses
# the smaller configured post size below; these hard stops prevent a future
# caller from creating a permanently rejected oversized request.
BACKEND_SOCIAL_MAX_ACCOUNTS = 100
BACKEND_SOCIAL_MAX_POSTS = 1_000
SOCIAL_RESULT_COUNTERS = (
    "accounts_inserted",
    "accounts_updated",
    "accounts_duplicate",
    "posts_inserted",
    "posts_updated",
    "posts_duplicate",
    "posts_tombstoned",
    "instruments_matched",
    "instruments_unresolved",
    "instrument_links_removed",
)


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


def push_news_to_backend(client: httpx.Client, items: list[dict]) -> Optional[dict]:
    if not items:
        return None
    try:
        response = client.post(
            f"{config.backend_url()}/market/news/ingest",
            json=_serialise({"items": items}),
            headers=_headers(),
            timeout=config.request_timeout() * 3,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        log.error("news ingest failed: %s", exc)
        return None


def push_social_to_backend(
    client: httpx.Client, accounts: list[dict], posts: list[dict]
) -> Optional[dict]:
    """Offer normalized public social data to the authenticated Core DB API."""

    if not accounts and not posts:
        return None
    if len(accounts) > BACKEND_SOCIAL_MAX_ACCOUNTS:
        raise ValueError("social account batch exceeds the backend contract")
    if len(posts) > BACKEND_SOCIAL_MAX_POSTS:
        raise ValueError("social post batch exceeds the backend contract")
    try:
        response = client.post(
            f"{config.backend_url()}/market/social/ingest",
            json=_serialise({"accounts": accounts, "posts": posts}),
            headers=_headers(),
            timeout=config.request_timeout() * 3,
        )
        response.raise_for_status()
        result = response.json()
        return result if isinstance(result, dict) else None
    except Exception as exc:
        # Never include request headers or bodies here: the same client also
        # carries the ingestor's service credential.
        log.error("social ingest failed: %s", type(exc).__name__)
        return None


def deliver_social_batches(
    client: httpx.Client,
    accounts: list[dict],
    posts: list[dict],
    *,
    post_batch_size: int | None = None,
) -> dict[str, Any]:
    """Deliver each account independently in bounded, atomic chunks.

    Repeating the account in every request keeps each request self-contained.
    An account is complete only after every one of its post chunks is accepted,
    allowing the caller to checkpoint successful accounts independently.
    """

    size = config.x_backend_batch_size() if post_batch_size is None else post_batch_size
    if not 1 <= size <= BACKEND_SOCIAL_MAX_POSTS:
        raise ValueError("social post delivery size is outside backend limits")

    account_by_id: dict[str, dict] = {}
    for account in accounts:
        external_id = str(account.get("external_account_id") or "")
        if not external_id or external_id in account_by_id:
            raise ValueError("social delivery accounts require unique external ids")
        account_by_id[external_id] = account

    grouped: dict[str, list[dict]] = {external_id: [] for external_id in account_by_id}
    for post in posts:
        external_id = str(post.get("account_external_id") or "")
        if external_id not in grouped:
            raise ValueError("social post references an account absent from delivery")
        grouped[external_id].append(post)

    result: dict[str, Any] = {key: 0 for key in SOCIAL_RESULT_COUNTERS}
    result.update(
        {
            "unresolved": [],
            "requests_succeeded": 0,
            "requests_failed": 0,
            "account_delivery": {},
            "delivery_attempted": False,
            "delivery_complete": False,
            "delivery_partial": False,
        }
    )

    if not account_by_id:
        return result

    for external_id, account in account_by_id.items():
        account_posts = grouped[external_id]
        chunks = [
            account_posts[index : index + size]
            for index in range(0, len(account_posts), size)
        ] or [[]]
        delivered = True
        accepted_chunks = 0
        for chunk in chunks:
            response = push_social_to_backend(client, [account], chunk)
            if response is None:
                result["requests_failed"] += 1
                delivered = False
                break
            result["requests_succeeded"] += 1
            accepted_chunks += 1
            for key in SOCIAL_RESULT_COUNTERS:
                result[key] += int(response.get(key, 0))
            unresolved = response.get("unresolved") or []
            if isinstance(unresolved, list):
                result["unresolved"].extend(unresolved)
        result["account_delivery"][external_id] = {
            "complete": delivered,
            "chunks_accepted": accepted_chunks,
            "chunks_required": len(chunks),
        }

    attempted = result["requests_succeeded"] + result["requests_failed"] > 0
    completed = sum(
        1 for item in result["account_delivery"].values() if item["complete"]
    )
    failed = sum(
        1 for item in result["account_delivery"].values() if not item["complete"]
    )
    result["delivery_attempted"] = attempted
    result["delivery_complete"] = attempted and failed == 0
    result["delivery_partial"] = attempted and completed > 0 and failed > 0
    return result


def push_news_to_rag(client: httpx.Client, items: list[dict]) -> int:
    """Chunk and embed each article into the vector store.

    One request per article because `rag /ingest` splits and embeds a single
    document; the service reports `duplicate` for content it already holds, so
    re-offering the same feed is a no-op rather than a second copy.

    Failures are counted, not raised. News that reaches the dashboard but not
    the corpus is a degraded state, not a broken one — the chatbot will simply
    say it found no sources, which is true.
    """
    written = 0
    for item in items:
        body = {
            "title": item["title"],
            "source": item["source"],
            "category": "market-news",
            "document_type": "NEWS",
            "content": item.get("summary") or item["title"],
            "source_url": item.get("url"),
            "language": item.get("language", "tr"),
            # One ticker per document; the corpus schema carries a single
            # ticker column. Multi-tagged stories keep their first symbol and
            # remain findable by text.
            "ticker": (item.get("related_symbols") or [None])[0],
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
