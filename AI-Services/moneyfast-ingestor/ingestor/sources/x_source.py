"""Official X API v2 collection for configured public accounts.

This module never scrapes X pages. It requests only user identity, timeline,
reference and URL-entity fields from the API and emits normalized public data
for the authenticated Core DB endpoint.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .. import config

log = logging.getLogger("moneyfast.ingestor.x")

API_BASE_URL = "https://api.x.com/2"
ALLOWED_KAP_HOSTS = frozenset({"kap.org.tr", "www.kap.org.tr"})
TRANSIENT_STATUSES = frozenset({408, 425, 500, 502, 503, 504})
PROVIDER_STATE_KEY = "_provider"
MIN_COOLDOWN_SECONDS = 60
MAX_COOLDOWN_SECONDS = 6 * 60 * 60


class XRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        super().__init__("X API rate limited")
        self.retry_after_seconds = retry_after_seconds


class XRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class CollectionBatch:
    accounts: list[dict[str, Any]]
    posts: list[dict[str, Any]]
    state_updates: dict[str, dict[str, Any]]
    account_statuses: dict[str, dict[str, Any]]
    status: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def cooldown_remaining(
    state: dict[str, dict[str, Any]], now: datetime | None = None
) -> int:
    """Seconds left in the persisted provider cooldown, rounded up."""

    now = (now or utc_now()).astimezone(timezone.utc)
    blocked_until = _parse_utc(
        (state.get(PROVIDER_STATE_KEY) or {}).get("blocked_until")
    )
    if blocked_until is None:
        return 0
    return max(0, math.ceil((blocked_until - now).total_seconds()))


def provider_cooldown_update(
    retry_after_seconds: int, now: datetime | None = None
) -> dict[str, dict[str, str]]:
    now = (now or utc_now()).astimezone(timezone.utc)
    bounded = max(
        MIN_COOLDOWN_SECONDS,
        min(MAX_COOLDOWN_SECONDS, int(retry_after_seconds)),
    )
    blocked_until = now + timedelta(seconds=bounded)
    return {PROVIDER_STATE_KEY: {"blocked_until": blocked_until.isoformat()}}


def validated_kap_url(raw: str | None) -> tuple[str, str] | None:
    if not raw or raw.startswith("//"):
        return None
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in ALLOWED_KAP_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return None
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, "")), host


def _retry_after(response: httpx.Response) -> int:
    now = int(time.time())
    reset = response.headers.get("x-rate-limit-reset")
    if reset:
        try:
            delay = int(reset) - now
        except ValueError:
            delay = 0
        if delay > 0:
            return max(MIN_COOLDOWN_SECONDS, min(MAX_COOLDOWN_SECONDS, delay))
    retry = response.headers.get("retry-after")
    try:
        delay = int(float(retry)) if retry else 0
    except ValueError:
        delay = 0
    if delay <= 0:
        delay = config.x_poll_interval_minutes() * 60
    return max(MIN_COOLDOWN_SECONDS, min(MAX_COOLDOWN_SECONDS, delay))


def _request_json(
    client: httpx.Client,
    path: str,
    *,
    token: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    attempts = config.x_max_retries() + 1
    for attempt in range(attempts):
        try:
            response = client.get(
                f"{API_BASE_URL}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": config.user_agent(),
                },
                timeout=config.request_timeout(),
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt + 1 >= attempts:
                raise XRequestError("X API request failed") from exc
            time.sleep(min(2.0, 0.25 * (2**attempt)))
            continue
        if response.status_code == 429:
            raise XRateLimited(_retry_after(response))
        if response.status_code in TRANSIENT_STATUSES and attempt + 1 < attempts:
            time.sleep(min(2.0, 0.25 * (2**attempt)))
            continue
        if response.status_code >= 400:
            raise XRequestError(
                f"X API returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise XRequestError("X API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise XRequestError("X API returned an invalid response shape")
        return payload
    raise AssertionError("request loop must execute at least once")  # pragma: no cover


def load_state(path: str | None = None) -> dict[str, dict[str, Any]]:
    target = Path(path or config.x_state_file())
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        log.warning("X cursor state is unreadable; refetching an overlap")
        return {}
    if not isinstance(value, dict):
        log.warning("X cursor state has an invalid shape; refetching an overlap")
        return {}
    return {
        str(handle): entry for handle, entry in value.items() if isinstance(entry, dict)
    }


def save_state(updates: dict[str, dict[str, Any]], path: str | None = None) -> bool:
    """Atomically merge account checkpoints or provider cooldown state."""

    target = Path(path or config.x_state_file())
    state = load_state(str(target))
    state.update(updates)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except OSError:
        log.warning("X cursor state could not be saved; next cycle will refetch")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def _resolve_accounts(
    client: httpx.Client,
    token: str,
    configured: list[dict[str, Any]],
    state: dict[str, dict[str, Any]],
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve new handles once, then pin and refresh the stable X user ID.

    A configured handle is a bootstrap locator. After the first resolution the
    state entry is bound to that stable user ID; periodic refreshes query by ID,
    so reassignment of the old handle cannot silently switch the monitored
    account.
    """

    resolved: list[dict[str, Any]] = []

    def cached_id(item: dict[str, Any]) -> str | None:
        value = str(state.get(item["handle"], {}).get("user_id") or "")
        return value if value.isdigit() else None

    refresh_before = now - timedelta(hours=config.x_identity_refresh_hours())
    new_items = [item for item in configured if cached_id(item) is None]
    stale_items = [
        item
        for item in configured
        if cached_id(item) is not None
        and (
            (
                checked := _parse_utc(
                    state.get(item["handle"], {}).get("identity_checked_at")
                )
            )
            is None
            or checked <= refresh_before
        )
    ]

    handle_lookup: dict[str, dict[str, Any]] = {}
    if new_items:
        payload = _request_json(
            client,
            "/users/by",
            token=token,
            params={
                "usernames": ",".join(item["handle"] for item in new_items),
                "user.fields": "id,name,username",
            },
        )
        handle_lookup = {
            str(item.get("username") or "").lower(): item
            for item in payload.get("data") or []
            if isinstance(item, dict)
        }

    id_lookup: dict[str, dict[str, Any]] = {}
    if stale_items:
        payload = _request_json(
            client,
            "/users",
            token=token,
            params={
                "ids": ",".join(cached_id(item) or "" for item in stale_items),
                "user.fields": "id,name,username",
            },
        )
        id_lookup = {
            str(item.get("id") or ""): item
            for item in payload.get("data") or []
            if isinstance(item, dict) and str(item.get("id") or "").isdigit()
        }

    errors: list[dict[str, Any]] = []
    for item in configured:
        cached = state.get(item["handle"]) or {}
        user_id = cached_id(item)
        since_id = str(cached.get("since_id") or "")
        since_id = since_id if since_id.isdigit() else None
        checked_at = _parse_utc(cached.get("identity_checked_at"))
        if user_id and item in stale_items:
            source = id_lookup.get(user_id)
            if source is None:
                errors.append(
                    {"handle": item["handle"], "code": "stable_user_not_found"}
                )
                continue
            checked_at = now
        elif user_id:
            source = {
                "id": user_id,
                "username": cached.get("handle") or item["handle"],
                "name": cached.get("display_name"),
            }
        else:
            source = handle_lookup.get(item["handle"])
            checked_at = now if source else None
        if not source or not source.get("id"):
            errors.append({"handle": item["handle"], "code": "user_not_found"})
            continue
        resolved.append(
            {
                **item,
                "external_account_id": str(source["id"]),
                "handle": str(source.get("username") or item["handle"]).lower(),
                "display_name": source.get("name"),
                "configured_handle": item["handle"],
                "since_id": since_id,
                "resume_token": cached.get("resume_token"),
                "pending_since_id": cached.get("pending_since_id"),
                "identity_checked_at": (
                    checked_at.isoformat()
                    if checked_at is not None
                    else now.isoformat()
                ),
            }
        )
    return resolved, errors


def _kind(tweet: dict[str, Any]) -> tuple[str, str | None]:
    references = tweet.get("referenced_tweets") or []
    by_type = {
        str(item.get("type")): str(item.get("id"))
        for item in references
        if isinstance(item, dict) and item.get("id")
    }
    for api_type, kind in (
        ("retweeted", "repost"),
        ("replied_to", "reply"),
        ("quoted", "quote"),
    ):
        if api_type in by_type:
            return kind, by_type[api_type]
    return "original", None


def _expanded_urls(tweet: dict[str, Any]) -> list[str]:
    urls = (tweet.get("entities") or {}).get("urls") or []
    out: list[str] = []
    for item in urls:
        if not isinstance(item, dict):
            continue
        value = item.get("unwound_url") or item.get("expanded_url")
        if value and value not in out:
            out.append(str(value))
    return out


def _normalize(
    tweet: dict[str, Any], account: dict[str, Any], collected_at: datetime
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(post, None)`` or ``(None, rejection_reason)``.

    Intentionally filtered replies/reposts are reported separately from
    malformed provider records. A completed provider page may still advance
    ``since_id`` after local rejections; those counts remain visible in status.
    """

    kind, referenced_id = _kind(tweet)
    if kind == "reply" and not config.x_include_replies():
        return None, "filtered_reply"
    if kind == "repost" and not config.x_include_reposts():
        return None, "filtered_repost"
    external_id = str(tweet.get("id") or "")
    if not external_id.isdigit():
        return None, "invalid_post_id"
    try:
        published = datetime.fromisoformat(
            str(tweet["created_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        return None, "invalid_timestamp"
    if published.tzinfo is None or published.utcoffset() is None:
        return None, "invalid_timestamp"
    published = published.astimezone(timezone.utc)
    urls = _expanded_urls(tweet)
    kap = next(
        (validated for url in urls if (validated := validated_kap_url(url))),
        None,
    )
    cashtags = [
        str(item.get("tag") or "").upper()
        for item in (tweet.get("entities") or {}).get("cashtags") or []
        if isinstance(item, dict) and item.get("tag")
    ]
    return {
        "platform": "x",
        "account_external_id": account["external_account_id"],
        "external_post_id": external_id,
        "content_text": str(tweet.get("text") or ""),
        "post_url": f"https://x.com/{account['handle']}/status/{external_id}",
        "language": tweet.get("lang"),
        "published_at": published,
        "collected_at": collected_at,
        "post_kind": kind,
        "referenced_external_post_id": referenced_id,
        "conversation_id": (
            str(tweet["conversation_id"]) if tweet.get("conversation_id") else None
        ),
        "is_tombstoned": False,
        "raw_metadata": {
            "expanded_urls": urls[:20],
            "reference_types": [
                str(item.get("type"))
                for item in tweet.get("referenced_tweets") or []
                if isinstance(item, dict) and item.get("type")
            ],
        },
        "underlying_source_url": kap[0] if kap else None,
        "instrument_references": list(dict.fromkeys(cashtags)),
    }, None


def _account_state(
    account: dict[str, Any],
    *,
    since_id: str | None,
    resume_token: str | None = None,
    pending_since_id: str | None = None,
) -> dict[str, Any]:
    entry = {
        "user_id": account["external_account_id"],
        "handle": account["handle"],
        "display_name": account.get("display_name"),
        "identity_checked_at": account["identity_checked_at"],
        "since_id": since_id,
    }
    if resume_token:
        entry["resume_token"] = resume_token
    if pending_since_id:
        entry["pending_since_id"] = pending_since_id
    return entry


def collect(
    client: httpx.Client,
    *,
    token: str,
    configured: list[dict[str, Any]],
    state: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> CollectionBatch:
    state = state if state is not None else load_state()
    collected_at = (now or utc_now()).astimezone(timezone.utc)
    accounts, errors = _resolve_accounts(client, token, configured, state, collected_at)
    account_payloads: list[dict[str, Any]] = []
    posts: list[dict[str, Any]] = []
    updates: dict[str, dict[str, Any]] = {}
    account_statuses: dict[str, dict[str, Any]] = {}
    seen_provider_ids: set[str] = set()
    rate_limited_for = 0
    normalization_rejections: dict[str, int] = {}

    def note_rejection(reason: str) -> None:
        normalization_rejections[reason] = normalization_rejections.get(reason, 0) + 1

    for account in accounts:
        configured_handle = account["configured_handle"]
        external_account_id = account["external_account_id"]
        previous_since_id = account.get("since_id")
        previous_resume_token = account.get("resume_token")
        previous_pending_since_id = str(account.get("pending_since_id") or "")
        if not previous_pending_since_id.isdigit():
            previous_pending_since_id = None
        account_payloads.append(
            {
                "platform": "x",
                "external_account_id": external_account_id,
                "handle": account["handle"],
                "display_name": account.get("display_name"),
                "source_type": account["source_type"],
                "trust_score": account["trust_score"],
                "is_active": account["is_active"],
            }
        )
        if not account["is_active"]:
            updates[configured_handle] = _account_state(
                account,
                since_id=previous_since_id,
                resume_token=previous_resume_token,
                pending_since_id=previous_pending_since_id,
            )
            account_statuses[external_account_id] = {
                "configured_handle": configured_handle,
                "collection_complete": False,
                "api_phase_success": True,
                "failure_reason": "inactive",
                "cursor_advanced": False,
            }
            continue
        params: dict[str, Any] = {
            "max_results": 100,
            "tweet.fields": "created_at,conversation_id,entities,lang,referenced_tweets",
            "expansions": "referenced_tweets.id",
        }
        excluded = []
        if not config.x_include_replies():
            excluded.append("replies")
        if not config.x_include_reposts():
            excluded.append("retweets")
        if excluded:
            params["exclude"] = ",".join(excluded)
        if previous_since_id:
            params["since_id"] = previous_since_id
        if previous_resume_token:
            params["pagination_token"] = previous_resume_token

        next_token = previous_resume_token
        newest = previous_pending_since_id or previous_since_id
        pagination_complete = False
        api_phase_success = True
        failure_reason: str | None = None
        pages_fetched = 0
        try:
            for page in range(config.x_max_pages_per_account()):
                if page > 0 and next_token:
                    params["pagination_token"] = next_token
                payload = _request_json(
                    client,
                    f"/users/{external_account_id}/tweets",
                    token=token,
                    params=params,
                )
                page_data = payload.get("data") or []
                meta = payload.get("meta") or {}
                if not isinstance(page_data, list) or not isinstance(meta, dict):
                    raise XRequestError("X API returned an invalid timeline shape")
                pages_fetched += 1
                for tweet in page_data:
                    if not isinstance(tweet, dict):
                        note_rejection("invalid_shape")
                        continue
                    external_id = str(tweet.get("id") or "")
                    if not external_id.isdigit():
                        note_rejection("invalid_post_id")
                        continue
                    if external_id in seen_provider_ids:
                        continue
                    seen_provider_ids.add(external_id)
                    if newest is None or int(external_id) > int(newest):
                        newest = external_id
                    normalized, rejection = _normalize(tweet, account, collected_at)
                    if normalized is None:
                        note_rejection(rejection or "invalid_shape")
                        continue
                    posts.append(normalized)
                next_token = meta.get("next_token")
                if not next_token:
                    pagination_complete = True
                    break
        except XRateLimited as exc:
            api_phase_success = False
            failure_reason = "rate_limited"
            rate_limited_for = max(rate_limited_for, exc.retry_after_seconds)
            errors.append({"handle": configured_handle, "code": failure_reason})
        except XRequestError as exc:
            api_phase_success = False
            failure_reason = (
                "invalid_pagination_token"
                if exc.status_code == 400 and previous_resume_token
                else "request_failed"
            )
            errors.append({"handle": configured_handle, "code": failure_reason})

        page_cap_reached = (
            api_phase_success and not pagination_complete and bool(next_token)
        )
        if page_cap_reached:
            failure_reason = "page_cap_reached"
            errors.append({"handle": configured_handle, "code": failure_reason})

        if pagination_complete:
            state_update = _account_state(account, since_id=newest)
        elif page_cap_reached:
            state_update = _account_state(
                account,
                since_id=previous_since_id,
                resume_token=str(next_token),
                pending_since_id=newest,
            )
        elif failure_reason == "invalid_pagination_token":
            # Restart from the unchanged since_id next cycle. The stable cursor
            # prevents data loss; already delivered pages replay idempotently.
            state_update = _account_state(account, since_id=previous_since_id)
        else:
            state_update = _account_state(
                account,
                since_id=previous_since_id,
                resume_token=previous_resume_token,
                pending_since_id=previous_pending_since_id,
            )
        updates[configured_handle] = state_update
        account_statuses[external_account_id] = {
            "configured_handle": configured_handle,
            "collection_complete": pagination_complete,
            "api_phase_success": api_phase_success,
            "failure_reason": failure_reason,
            "pages_fetched": pages_fetched,
            "cursor_advanced": (
                pagination_complete
                and newest is not None
                and newest != previous_since_id
            ),
        }

    status = {
        "accounts_requested": len(configured),
        "accounts_resolved": len(accounts),
        "posts_fetched": len(seen_provider_ids),
        "posts_offered": len(posts),
        "normalization_rejected": sum(normalization_rejections.values()),
        "normalization_rejections": dict(sorted(normalization_rejections.items())),
        "accounts_complete": sum(
            item["collection_complete"] for item in account_statuses.values()
        ),
        "accounts_incomplete": sum(
            not item["collection_complete"] for item in account_statuses.values()
        ),
        "account_statuses": account_statuses,
        "errors": errors,
    }
    if normalization_rejections:
        log.info(
            "X normalization rejected %d provider posts: %s",
            sum(normalization_rejections.values()),
            dict(sorted(normalization_rejections.items())),
        )
    if rate_limited_for:
        status.update(
            {
                "rate_limited": True,
                "retry_after_seconds": rate_limited_for,
            }
        )
    return CollectionBatch(
        account_payloads,
        posts,
        updates,
        account_statuses,
        status,
    )
