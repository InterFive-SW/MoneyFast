"""Strict ResearchCitation validation at the backend public-response boundary."""

from __future__ import annotations

import pytest
from app.modules.ai_orchestrator.schemas import (
    ChatResponse,
    ResearchCitation,
    make_evidence_id,
)
from pydantic import ValidationError


def _valid(**overrides):
    body = {
        "platform": "x",
        "handle": "test_finans",
        "post_url": "https://x.com/test_finans/status/1",
        "verification_status": "unverified",
        "source_type": "financial_media",
        "excerpt": "THYAO note",
        "published_at": "2026-08-27T09:00:00+00:00",
        "matched_symbols": ["THYAO"],
    }
    body.update(overrides)
    if "evidence_id" not in body:
        body["evidence_id"] = make_evidence_id(
            body["platform"],
            body["handle"],
            body["post_url"],
            body.get("kap_url"),
        )
    return body


def test_chat_response_defaults_empty_citations():
    response = ChatResponse(final_output="ok")
    assert response.citations == []


def test_accepts_canonical_citation():
    cite = ResearchCitation(**_valid())
    assert cite.platform == "x"
    assert cite.handle == "test_finans"
    assert cite.evidence_id == make_evidence_id(
        "x", "test_finans", "https://x.com/test_finans/status/1", None
    )


@pytest.mark.parametrize(
    "post_url",
    [
        "http://x.com/test_finans/status/1",
        "https://x.com.evil.example/test_finans/status/1",
        "https://user:pass@x.com/test_finans/status/1",
        "https://x.com:8443/test_finans/status/1",
        "https://x.com/test_finans/status/1?utm=1",
        "https://x.com/test_finans/status/1#frag",
        "https://notx.com/test_finans/status/1",
    ],
)
def test_rejects_malicious_or_noncanonical_post_urls(post_url):
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(post_url=post_url))


@pytest.mark.parametrize(
    "kap_url",
    [
        "http://kap.org.tr/tr/Bildirim/1",
        "https://kap.org.tr.evil.example/x",
        "https://user:pass@kap.org.tr/x",
        "https://kap.org.tr:8443/x",
        "https://evil.kap.org.tr/x",
    ],
)
def test_rejects_invalid_kap_urls(kap_url):
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(kap_url=kap_url))


def test_accepts_exact_kap_hosts():
    a = ResearchCitation(
        **_valid(
            kap_url="https://kap.org.tr/tr/Bildirim/1",
            evidence_id=make_evidence_id(
                "x",
                "test_finans",
                "https://x.com/test_finans/status/1",
                "https://kap.org.tr/tr/Bildirim/1",
            ),
        )
    )
    b = ResearchCitation(
        **_valid(
            kap_url="https://www.kap.org.tr/tr/Bildirim/2",
            evidence_id=make_evidence_id(
                "x",
                "test_finans",
                "https://x.com/test_finans/status/1",
                "https://www.kap.org.tr/tr/Bildirim/2",
            ),
        )
    )
    assert a.kap_url.startswith("https://kap.org.tr/")
    assert b.kap_url.startswith("https://www.kap.org.tr/")


def test_rejects_bad_enums_handle_excerpt_timestamp_symbols():
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(platform="twitter"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(handle="bad handle!"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(verification_status="maybe"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(source_type="blog"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(excerpt=""))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(excerpt="has ``` fence"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(excerpt="has \x01 control"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(published_at="2026-08-27T09:00:00"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(published_at="not-a-date"))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(matched_symbols=["", "THYAO"]))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(matched_symbols=["A"] * 9))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(matched_symbols=["X" * 20]))


def test_normalizes_symbols_and_published_at():
    cite = ResearchCitation(
        **_valid(
            matched_symbols=["thyao", "THYAO", "ASELS"],
            published_at="2026-08-27T12:00:00+03:00",
        )
    )
    assert cite.matched_symbols == ["THYAO", "ASELS"]
    assert cite.published_at.endswith("+00:00") or cite.published_at.endswith("Z")


def test_chat_response_rejects_malformed_forwarded_citation():
    with pytest.raises(ValidationError):
        ChatResponse(
            final_output="x",
            citations=[_valid(post_url="https://evil.example/status/1")],
        )


def test_evidence_id_must_match_recomputed_identity():
    assert ResearchCitation(**_valid())
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(evidence_id="a" * 32))
    with pytest.raises(ValidationError):
        ResearchCitation(**_valid(handle="other", evidence_id=_valid()["evidence_id"]))
    with pytest.raises(ValidationError):
        ResearchCitation(
            **_valid(
                post_url="https://x.com/test_finans/status/2",
                evidence_id=_valid()["evidence_id"],
            )
        )
    with pytest.raises(ValidationError):
        ResearchCitation(
            **_valid(
                kap_url="https://kap.org.tr/tr/Bildirim/1",
                evidence_id=_valid()["evidence_id"],
            )
        )
    with pytest.raises(ValidationError):
        # platform mismatch is rejected by Literal before id check; still covered
        ResearchCitation(
            **_valid(platform="twitter", evidence_id=_valid()["evidence_id"])
        )
    # canonical no-KAP
    cite = ResearchCitation(**_valid(kap_url=None))
    assert cite.evidence_id == make_evidence_id(
        "x", "test_finans", "https://x.com/test_finans/status/1", None
    )


def test_validators_direct_edge_paths(monkeypatch):
    from urllib.parse import urlsplit as real_urlsplit

    import app.modules.ai_orchestrator.schemas as schemas

    def boom(value):
        raise ValueError("split failed")

    monkeypatch.setattr(schemas, "urlsplit", boom)
    with pytest.raises(ValueError, match="invalid post_url"):
        ResearchCitation._reject_deceptive_post_url("https://x.com/a/status/1")
    monkeypatch.setattr(schemas, "urlsplit", real_urlsplit)

    with pytest.raises(ValueError, match="invalid post_url"):
        ResearchCitation._reject_deceptive_post_url(
            "https://user:pass@x.com/a/status/1"
        )
    with pytest.raises(ValueError, match="invalid post_url host"):
        ResearchCitation._reject_deceptive_post_url("https://evil.com/a/status/1")

    assert ResearchCitation._validate_kap(None) is None
    assert ResearchCitation._validate_kap("") is None
    assert ResearchCitation._validate_excerpt(None) is None
    assert ResearchCitation._validate_published_at(None) is None
    assert ResearchCitation._validate_published_at("") is None


def test_url_identity_urlsplit_failure(monkeypatch):
    import app.modules.ai_orchestrator.schemas as schemas

    def boom(_value):
        raise ValueError("bad")

    monkeypatch.setattr(schemas, "urlsplit", boom)
    assert (
        schemas._url_identity("https://x.com/a/status/1") == "https://x.com/a/status/1"
    )
