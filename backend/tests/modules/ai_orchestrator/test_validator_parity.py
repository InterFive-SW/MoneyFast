"""Cross-service validator parity using the shared fixture table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.modules.ai_orchestrator.schemas import ResearchCitation, make_evidence_id
from app.modules.market.kap import validated_kap_url
from pydantic import ValidationError

SHARED = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "social_validator_parity.json"
)
CASES = json.loads(SHARED.read_text())


def test_shared_fixture_is_authoritative():
    assert SHARED.is_file()
    local = Path(__file__).parent / "social_validator_parity.json"
    if local.exists():
        assert local.read_bytes() == SHARED.read_bytes()


def _base(**overrides):
    body = {
        "platform": "x",
        "handle": "test_finans",
        "post_url": "https://x.com/test_finans/status/1",
        "verification_status": "unverified",
        "source_type": "financial_media",
        "excerpt": "note",
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


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_parity_case(case):
    kind = case["kind"]
    expect = case["expect"]
    if kind == "kap_url":
        assert (validated_kap_url(case["value"]) is not None) is expect
        return
    if kind == "x_url":
        if expect:
            ResearchCitation(**_base(post_url=case["value"]))
        else:
            with pytest.raises(ValidationError):
                ResearchCitation(**_base(post_url=case["value"]))
        return
    if kind == "timestamp":
        if expect:
            ResearchCitation(**_base(published_at=case["value"]))
        else:
            with pytest.raises(ValidationError):
                ResearchCitation(**_base(published_at=case["value"]))
        return
    if kind == "handle":
        if expect:
            ResearchCitation(**_base(handle=case["value"]))
        else:
            with pytest.raises(ValidationError):
                ResearchCitation(**_base(handle=case["value"]))
        return
    if kind == "source_type":
        if expect:
            ResearchCitation(**_base(source_type=case["value"]))
        else:
            with pytest.raises(ValidationError):
                ResearchCitation(**_base(source_type=case["value"]))
        return
    if kind == "verification_status":
        if expect:
            ResearchCitation(**_base(verification_status=case["value"]))
        else:
            with pytest.raises(ValidationError):
                ResearchCitation(**_base(verification_status=case["value"]))
        return
    if kind == "evidence_block":
        # Evidence-block grammar is enforced in orchestrator/MCP; backend binds
        # citations via recomputed evidence_id instead.
        assert expect is False
        return
    if kind == "citation_mismatch":
        body = _base()
        body[case["field"]] = case["value"]
        if case.get("keep_evidence_id"):
            body["evidence_id"] = _base()["evidence_id"]
        elif case["field"] != "evidence_id":
            body["evidence_id"] = make_evidence_id(
                body["platform"],
                body["handle"],
                body["post_url"],
                body.get("kap_url"),
            )
        # Backend recomputes evidence_id from identity fields only. Content-field
        # mismatches are rejected at the orchestrator bind layer.
        identity_fields = {"evidence_id", "handle", "post_url", "kap_url", "platform"}
        if case["field"] in identity_fields:
            with pytest.raises(ValidationError):
                ResearchCitation(**body)
        else:
            ResearchCitation(**body)
        return
    raise AssertionError(case["kind"])
