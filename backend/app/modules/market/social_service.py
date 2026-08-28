"""Persistence and read queries for public social-media signals."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.investment import market_service

from .kap import validated_kap_url
from .models import SocialAccount, SocialPost, SocialPostInstrument


class SocialBatchError(ValueError):
    """A batch is semantically invalid and must be rejected atomically."""


class SocialBatchConflict(ValueError):
    """A predictable database identity conflict in a client-supplied batch."""


KNOWN_SOCIAL_IDENTITY_CONSTRAINTS = frozenset(
    {
        "uq_social_accounts_platform_external",
        "uq_social_accounts_platform_handle",
        "uq_social_posts_platform_external",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    """Return a structured constraint name when the driver exposes one.

    PostgreSQL surfaces ``orig.diag.constraint_name``. Unit tests may set the
    same attribute on a mock driver error. Free-form exception text is never
    treated as authoritative so schema defects cannot hide as identity conflicts.
    """

    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None) if orig is not None else None
    name = getattr(diag, "constraint_name", None) if diag is not None else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _raise_integrity_as_batch_conflict(exc: IntegrityError) -> None:
    """Translate only known social identity uniqueness conflicts."""

    name = _integrity_constraint_name(exc)
    if name in KNOWN_SOCIAL_IDENTITY_CONSTRAINTS:
        raise SocialBatchConflict(
            "social batch conflicts with an existing account or post identity"
        ) from exc
    raise exc


def _canonical_post_url(raw: str, handle: str, external_post_id: str) -> str:
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise SocialBatchError("post_url is malformed") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() not in {"x.com", "www.x.com"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise SocialBatchError("post_url must be an HTTPS x.com status URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3 or parts[1].lower() != "status" or parts[2] != external_post_id:
        raise SocialBatchError("post_url does not match the external post id")
    if parts[0].casefold() != handle.casefold():
        raise SocialBatchError("post_url handle does not match the social account")
    return f"https://x.com/{handle}/status/{external_post_id}"


def _changed(row: Any, values: dict[str, Any]) -> bool:
    changed = False
    for key, value in values.items():
        current = getattr(row, key)
        if key == "trust_score" and current is not None:
            current = float(current)
        if current != value:
            setattr(row, key, value)
            changed = True
    return changed


def _upsert_account(
    db: Session, item: dict[str, Any], counters: dict[str, Any]
) -> SocialAccount:
    row = (
        db.query(SocialAccount)
        .filter(
            SocialAccount.platform == item["platform"],
            SocialAccount.external_account_id == item["external_account_id"],
        )
        .one_or_none()
    )
    values = {
        "handle": item["handle"],
        "display_name": item.get("display_name"),
        "source_type": item["source_type"],
        "trust_score": item["trust_score"],
        "is_active": item.get("is_active", True),
    }
    if row is None:
        row = SocialAccount(
            platform=item["platform"],
            external_account_id=item["external_account_id"],
            **values,
        )
        db.add(row)
        db.flush()
        counters["accounts_inserted"] += 1
    elif _changed(row, values):
        row.updated_at = _now()
        db.flush()
        counters["accounts_updated"] += 1
    else:
        counters["accounts_duplicate"] += 1
    return row


def _find_account(db: Session, platform: str, external_id: str) -> SocialAccount | None:
    return (
        db.query(SocialAccount)
        .filter(
            SocialAccount.platform == platform,
            SocialAccount.external_account_id == external_id,
        )
        .one_or_none()
    )


def _upsert_post(
    db: Session,
    item: dict[str, Any],
    account: SocialAccount,
    counters: dict[str, Any],
) -> SocialPost:
    row = (
        db.query(SocialPost)
        .filter(
            SocialPost.platform == item["platform"],
            SocialPost.external_post_id == item["external_post_id"],
        )
        .one_or_none()
    )
    trusted_underlying = validated_kap_url(item.get("underlying_source_url"))
    if row is not None and row.account_id != account.id:
        raise SocialBatchError(
            "an existing post cannot be reassigned to another account"
        )
    values = {
        "account_id": account.id,
        "content_text": item["content_text"],
        "post_url": _canonical_post_url(
            item["post_url"], account.handle, item["external_post_id"]
        ),
        "language": item.get("language"),
        "published_at": item["published_at"],
        "post_kind": item["post_kind"],
        "referenced_external_post_id": item.get("referenced_external_post_id"),
        "conversation_id": item.get("conversation_id"),
        "is_tombstoned": item.get("is_tombstoned", False),
        "raw_metadata": item.get("raw_metadata") or {},
        "underlying_source_url": None,
        "underlying_source_type": None,
        "underlying_source_domain": None,
    }
    if trusted_underlying is not None:
        values.update(
            {
                "underlying_source_url": trusted_underlying[0],
                "underlying_source_type": "kap_disclosure",
                "underlying_source_domain": trusted_underlying[1],
            }
        )

    if row is None:
        row = SocialPost(
            platform=item["platform"],
            external_post_id=item["external_post_id"],
            collected_at=item["collected_at"],
            verification_status="unverified",
            **values,
        )
        db.add(row)
        db.flush()
        counters["posts_inserted"] += 1
        if row.is_tombstoned:
            counters["posts_tombstoned"] += 1
    else:
        was_tombstoned = row.is_tombstoned
        if _changed(row, values):
            row.updated_at = _now()
            db.flush()
            counters["posts_updated"] += 1
            if not was_tombstoned and row.is_tombstoned:
                counters["posts_tombstoned"] += 1
        else:
            counters["posts_duplicate"] += 1
    return row


def _attach_instruments(
    db: Session,
    post: SocialPost,
    references: list[str],
    counters: dict[str, Any],
) -> None:
    """Reconcile instrument links for the latest accepted references.

    An empty ``instrument_references`` list is authoritative and means the post
    currently has no instrument associations, so existing links are removed.
    When any supplied reference is unknown or ambiguous, reconciliation is not
    authoritative: newly resolved products are still added, but existing links
    are preserved because a temporary resolver miss is not proof that a prior
    valid relation disappeared. Ambiguous symbols are never guessed.
    """

    existing_rows = (
        db.query(SocialPostInstrument)
        .filter(SocialPostInstrument.post_id == post.id)
        .all()
    )
    existing = {row.product_id: row for row in existing_rows}
    resolved_ids: set[str] = set()
    uncertain = False
    for reference in references:
        candidates = market_service.resolve_candidates(db, reference, strict=True)
        if len(candidates) != 1:
            uncertain = True
            counters["instruments_unresolved"] += 1
            counters["unresolved"].append(
                {
                    "external_post_id": post.external_post_id,
                    "reference": reference,
                    "candidates": [candidate.symbol for candidate in candidates],
                }
            )
            continue
        product = candidates[0]
        if product.id in resolved_ids:
            continue
        resolved_ids.add(product.id)
        counters["instruments_matched"] += 1
        if product.id not in existing:
            db.add(
                SocialPostInstrument(
                    post_id=post.id,
                    product_id=product.id,
                    canonical_symbol=product.symbol,
                    match_method="backend_resolver",
                    match_confidence=None,
                )
            )
    # Empty list: authoritative "no references". Non-empty with any unresolved
    # or ambiguous item: preserve existing links that were not positively
    # contradicted by a successful resolution set.
    if uncertain:
        return
    for product_id, relation in existing.items():
        if product_id not in resolved_ids:
            db.delete(relation)
            counters["instrument_links_removed"] += 1


def ingest_batch(
    db: Session, accounts: list[dict[str, Any]], posts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Atomically upsert one normalized batch.

    Invalid account references or post URLs roll back the complete batch.
    Unknown or ambiguous instrument references are evidence gaps rather than
    invalid posts, so the post is retained and the unresolved item is returned.
    Instrument links are reconciled only when the accepted reference list is
    authoritative (empty, or every supplied reference resolved uniquely).
    Verification status is intentionally absent from the ingest contract:
    ordinary collection can neither elevate nor downgrade an existing record.
    """

    counters: dict[str, Any] = {
        "accounts_inserted": 0,
        "accounts_updated": 0,
        "accounts_duplicate": 0,
        "posts_inserted": 0,
        "posts_updated": 0,
        "posts_duplicate": 0,
        "posts_tombstoned": 0,
        "instruments_matched": 0,
        "instruments_unresolved": 0,
        "instrument_links_removed": 0,
        "unresolved": [],
    }
    account_rows: dict[tuple[str, str], SocialAccount] = {}
    try:
        for item in accounts:
            row = _upsert_account(db, item, counters)
            account_rows[(item["platform"], item["external_account_id"])] = row
        for item in posts:
            key = (item["platform"], item["account_external_id"])
            account = account_rows.get(key) or _find_account(db, *key)
            if account is None:
                raise SocialBatchError(
                    f"post {item['external_post_id']} references an unknown account"
                )
            if account.platform != item["platform"]:
                raise SocialBatchError(
                    "post platform does not match its social account"
                )
            post = _upsert_post(db, item, account, counters)
            _attach_instruments(
                db, post, item.get("instrument_references") or [], counters
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_integrity_as_batch_conflict(exc)
    except Exception:
        db.rollback()
        raise
    return counters


def list_signals(
    db: Session,
    *,
    symbol: str | None,
    since_hours: int,
    limit: int,
    minimum_trust_score: float | None,
    verification_status: str | None,
    source_type: str | None,
) -> list[dict[str, Any]]:
    product = None
    if symbol:
        product = market_service.resolve_symbol(db, symbol)
        if product is None:
            return []

    query = (
        db.query(SocialPost, SocialAccount)
        .join(SocialAccount, SocialAccount.id == SocialPost.account_id)
        .filter(
            SocialPost.is_tombstoned.is_(False),
            SocialPost.published_at >= _now() - timedelta(hours=since_hours),
            SocialAccount.is_active.is_(True),
        )
    )
    if product is not None:
        query = query.join(
            SocialPostInstrument,
            SocialPostInstrument.post_id == SocialPost.id,
        ).filter(SocialPostInstrument.product_id == product.id)
    if minimum_trust_score is not None:
        query = query.filter(SocialAccount.trust_score >= minimum_trust_score)
    if verification_status is not None:
        query = query.filter(SocialPost.verification_status == verification_status)
    if source_type is not None:
        query = query.filter(SocialAccount.source_type == source_type)

    rows = (
        query.order_by(SocialPost.published_at.desc(), SocialPost.id.desc())
        .limit(limit)
        .all()
    )
    post_ids = [post.id for post, _account in rows]
    symbols: dict[str, list[str]] = defaultdict(list)
    if post_ids:
        for relation in (
            db.query(SocialPostInstrument)
            .filter(SocialPostInstrument.post_id.in_(post_ids))
            .order_by(SocialPostInstrument.canonical_symbol)
            .all()
        ):
            symbols[relation.post_id].append(relation.canonical_symbol)

    return [
        {
            "platform": post.platform,
            "handle": account.handle,
            "displayName": account.display_name,
            "sourceType": account.source_type,
            "trustScore": float(account.trust_score),
            "verificationStatus": post.verification_status,
            "publishedAt": post.published_at,
            "collectedAt": post.collected_at,
            "text": post.content_text,
            "postUrl": post.post_url,
            "underlyingSourceUrl": post.underlying_source_url,
            "underlyingSourceType": post.underlying_source_type,
            "matchedSymbols": symbols[post.id],
            "postKind": post.post_kind,
        }
        for post, account in rows
    ]
