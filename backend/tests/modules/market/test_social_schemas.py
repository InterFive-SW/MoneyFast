from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.modules.market.schemas import (
    SocialAccountIn,
    SocialIngestRequest,
    SocialPostIn,
)

NOW = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)


def valid_post(**overrides):
    data = {
        "account_external_id": "100",
        "external_post_id": "200",
        "content_text": "signal",
        "post_url": "https://x.com/test/status/200",
        "published_at": NOW,
        "collected_at": NOW,
        "post_kind": "original",
    }
    data.update(overrides)
    return data


def valid_account(**overrides):
    data = {
        "external_account_id": "100",
        "handle": "test",
        "source_type": "analyst",
        "trust_score": 0.5,
    }
    data.update(overrides)
    return data


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValidationError, match="timezone"):
        SocialPostIn(**valid_post(published_at=NOW.replace(tzinfo=None)))


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"external_account_id": "not-numeric"}, "numeric X user id"),
        ({"handle": "bad-handle!"}, "valid X handle"),
    ],
)
def test_invalid_account_identity_is_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        SocialAccountIn(**valid_account(**overrides))


def test_optional_reference_none_is_accepted():
    assert (
        SocialPostIn(
            **valid_post(referenced_external_post_id=None)
        ).referenced_external_post_id
        is None
    )


def test_invalid_post_reference_id_is_rejected():
    with pytest.raises(ValidationError, match="numeric"):
        SocialPostIn(**valid_post(referenced_external_post_id="abc"))


def test_only_x_platform_is_accepted_for_accounts_and_posts():
    with pytest.raises(ValidationError, match="Input should be 'x'"):
        SocialAccountIn(**valid_account(platform="other"))
    with pytest.raises(ValidationError, match="Input should be 'x'"):
        SocialPostIn(**valid_post(platform="other"))


def test_instrument_references_are_trimmed_deduplicated_and_bounded():
    post = SocialPostIn(
        **valid_post(instrument_references=[" THYAO ", "", "THYAO", "ASELS"])
    )
    assert post.instrument_references == ["THYAO", "ASELS"]
    with pytest.raises(ValidationError, match="255"):
        SocialPostIn(**valid_post(instrument_references=["x" * 256]))


def test_raw_metadata_must_be_json_and_bounded():
    assert SocialPostIn(
        **valid_post(raw_metadata={"expanded_urls": ["https://example.test"]})
    ).raw_metadata
    with pytest.raises(ValidationError, match="JSON serializable"):
        SocialPostIn(**valid_post(raw_metadata={"bad": {1, 2}}))
    with pytest.raises(ValidationError, match="too large"):
        SocialPostIn(**valid_post(raw_metadata={"large": "x" * 17_000}))
    with pytest.raises(ValidationError, match="credential-like"):
        SocialPostIn(
            **valid_post(raw_metadata={"entities": [{"api_key": "must-reject"}]})
        )


def test_tombstone_may_have_empty_content():
    assert SocialPostIn(**valid_post(content_text="", is_tombstoned=True)).is_tombstoned


def test_duplicate_accounts_in_one_batch_are_rejected():
    account = valid_account()
    with pytest.raises(ValidationError, match="duplicate account"):
        SocialIngestRequest(accounts=[account, account], posts=[])


def test_duplicate_normalized_handles_are_rejected_before_database_access():
    with pytest.raises(ValidationError, match="normalized account handles"):
        SocialIngestRequest(
            accounts=[
                valid_account(external_account_id="100", handle="@Same_Handle"),
                valid_account(external_account_id="101", handle="same_handle"),
            ],
            posts=[],
        )


def test_backend_batch_limits_are_enforced():
    with pytest.raises(ValidationError, match="at most 100"):
        SocialIngestRequest(
            accounts=[
                valid_account(external_account_id=str(index + 1), handle=f"a{index}")
                for index in range(101)
            ],
            posts=[],
        )
    with pytest.raises(ValidationError, match="at most 1000"):
        SocialIngestRequest(
            accounts=[],
            posts=[
                valid_post(external_post_id=str(index + 1)) for index in range(1_001)
            ],
        )
