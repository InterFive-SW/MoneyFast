from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.market import social_service

NOW = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)


def payload(**post_overrides):
    post = {
        "platform": "x",
        "account_external_id": "100",
        "external_post_id": "200",
        "content_text": "THYAO açıklaması",
        "post_url": "https://x.com/test_finans/status/200",
        "language": "tr",
        "published_at": NOW.isoformat(),
        "collected_at": NOW.isoformat(),
        "post_kind": "original",
        "raw_metadata": {},
        "instrument_references": ["THYAO"],
    }
    post.update(post_overrides)
    return {
        "accounts": [
            {
                "platform": "x",
                "external_account_id": "100",
                "handle": "Test_Finans",
                "display_name": "Test Finans",
                "source_type": "financial_media",
                "trust_score": 0.75,
            }
        ],
        "posts": [post],
    }


EMPTY_RESULT = {
    "accounts_inserted": 0,
    "accounts_updated": 0,
    "accounts_duplicate": 1,
    "posts_inserted": 0,
    "posts_updated": 0,
    "posts_duplicate": 1,
    "posts_tombstoned": 0,
    "instruments_matched": 1,
    "instruments_unresolved": 0,
    "unresolved": [],
}


class TestSocialIngest:
    def test_service_token_is_required(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        assert (
            client.post("/api/market/social/ingest", json=payload()).status_code == 401
        )

    def test_unconfigured_guard_fails_closed(self, client, monkeypatch):
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer anything"},
            json=payload(),
        )
        assert response.status_code == 503

    def test_valid_batch_is_forwarded_and_normalized(self, client, monkeypatch, mocker):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        ingest = mocker.patch.object(
            social_service, "ingest_batch", return_value=EMPTY_RESULT
        )
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer secret"},
            json=payload(),
        )
        assert response.status_code == 200
        assert response.json()["posts_duplicate"] == 1
        assert ingest.call_args.args[1][0]["handle"] == "test_finans"

    def test_semantic_batch_error_is_422_and_rolls_back_in_service(
        self, client, monkeypatch, mocker
    ):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        mocker.patch.object(
            social_service,
            "ingest_batch",
            side_effect=social_service.SocialBatchError("bad post"),
        )
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer secret"},
            json=payload(),
        )
        assert response.status_code == 422

    def test_predictable_integrity_conflict_is_409(self, client, monkeypatch, mocker):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        mocker.patch.object(
            social_service,
            "ingest_batch",
            side_effect=social_service.SocialBatchConflict("identity conflict"),
        )
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer secret"},
            json=payload(),
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "identity conflict"

    def test_unexpected_integrity_failure_is_not_converted_to_409(
        self, client, monkeypatch, mocker
    ):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        mocker.patch.object(
            social_service,
            "ingest_batch",
            side_effect=IntegrityError("INSERT", {}, Exception("fk")),
        )
        with pytest.raises(IntegrityError):
            client.post(
                "/api/market/social/ingest",
                headers={"Authorization": "Bearer secret"},
                json=payload(),
            )

    def test_active_empty_post_rejects_entire_request(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer secret"},
            json=payload(content_text=" "),
        )
        assert response.status_code == 422

    def test_duplicate_external_ids_are_rejected(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        body = payload()
        body["posts"].append(dict(body["posts"][0]))
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer secret"},
            json=body,
        )
        assert response.status_code == 422

    def test_duplicate_normalized_handles_are_rejected(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        body = payload()
        body["accounts"].append(
            {
                **body["accounts"][0],
                "external_account_id": "101",
                "handle": "@test_finans",
            }
        )
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer secret"},
            json=body,
        )
        assert response.status_code == 422

    def test_credential_like_raw_metadata_is_rejected(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        response = client.post(
            "/api/market/social/ingest",
            headers={"Authorization": "Bearer secret"},
            json=payload(raw_metadata={"authorization": "secret"}),
        )
        assert response.status_code == 422


class TestSocialRead:
    def test_public_read_returns_explicit_trust_labels(self, client, mocker):
        mocker.patch.object(
            social_service,
            "list_signals",
            return_value=[
                {
                    "platform": "x",
                    "handle": "test_finans",
                    "displayName": "Test Finans",
                    "sourceType": "disclosure_aggregator",
                    "trustScore": 0.85,
                    "verificationStatus": "unverified",
                    "publishedAt": NOW,
                    "collectedAt": NOW,
                    "text": "KAP bağlantısı",
                    "postUrl": "https://x.com/test_finans/status/200",
                    "underlyingSourceUrl": "https://kap.org.tr/tr/Bildirim/1",
                    "underlyingSourceType": "kap_disclosure",
                    "matchedSymbols": ["THYAO", "ASELS"],
                    "postKind": "original",
                }
            ],
        )
        response = client.get(
            "/api/market/social-signals",
            params={
                "symbol": "Türk Hava Yolları",
                "since_hours": 48,
                "limit": 10,
                "minimum_trust_score": 0.8,
                "verification_status": "unverified",
                "source_type": "disclosure_aggregator",
            },
        )
        assert response.status_code == 200
        assert response.json()[0]["verificationStatus"] == "unverified"
        assert "raw_metadata" not in response.json()[0]

    def test_empty_result_is_valid(self, client, mocker):
        mocker.patch.object(social_service, "list_signals", return_value=[])
        assert client.get("/api/market/social-signals").json() == []

    def test_query_bounds_and_enums_are_validated(self, client):
        invalid = [
            "?limit=0",
            "?limit=101",
            "?since_hours=0",
            "?since_hours=169",
            "?minimum_trust_score=1.1",
            "?verification_status=trusted",
            "?source_type=blogger",
        ]
        assert all(
            client.get(f"/api/market/social-signals{query}").status_code == 422
            for query in invalid
        )
