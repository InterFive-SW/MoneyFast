from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ingestor.sources import x_source

NOW = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
RESET = str(int(NOW.timestamp()) + 120)


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def configured():
    return [
        {
            "handle": "test_media",
            "source_type": "financial_media",
            "trust_score": 0.75,
            "is_active": True,
        }
    ]


def tweet(post_id="200", *, reference=None, urls=None, cashtags=None):
    data = {
        "id": post_id,
        "text": "Test social signal",
        "created_at": "2026-08-27T09:00:00Z",
        "lang": "tr",
        "conversation_id": post_id,
        "entities": {},
    }
    if reference:
        data["referenced_tweets"] = [{"type": reference, "id": "100"}]
    if urls:
        data["entities"]["urls"] = urls
    if cashtags:
        data["entities"]["cashtags"] = [{"tag": tag} for tag in cashtags]
    return data


def api_handler(tweets, *, pages=None, calls=None):
    page_payloads = list(pages or [{"data": tweets, "meta": {}}])
    seen = calls if calls is not None else []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/users/by"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "1000", "username": "test_media", "name": "Test Media"}
                    ]
                },
            )
        if request.url.path.endswith("/users"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "1000", "username": "test_media", "name": "Test Media"}
                    ]
                },
            )
        if "/tweets" in request.url.path:
            return httpx.Response(200, json=page_payloads.pop(0))
        raise AssertionError(request.url)

    return handler


class TestKapUrls:
    def test_exact_allowed_hosts_are_normalized(self):
        assert x_source.validated_kap_url(
            "https://www.kap.org.tr/tr/Bildirim/1?q=2#fragment"
        ) == (
            "https://www.kap.org.tr/tr/Bildirim/1?q=2",
            "www.kap.org.tr",
        )
        assert x_source.validated_kap_url("https://kap.org.tr") == (
            "https://kap.org.tr/",
            "kap.org.tr",
        )

    @pytest.mark.parametrize(
        "url",
        [
            None,
            "",
            "//kap.org.tr/x",
            "http://kap.org.tr/x",
            "ftp://kap.org.tr/x",
            "https://kap.org.tr.attacker.example/x",
            "https://evil.example/kap.org.tr",
            "https://evil.example/?url=kap.org.tr",
            "https://user@kap.org.tr/x",
            "https://kap.org.tr:444/x",
            "https://kap.org.tr:bad/x",
        ],
    )
    def test_rejects_substring_malformed_and_non_https_urls(self, url):
        assert x_source.validated_kap_url(url) is None


class TestHttpPolicy:
    def test_bearer_is_in_header_not_url(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"data": []})

        x_source._request_json(
            client_for(handler),
            "/users/by",
            token="top-secret",
            params={"usernames": "x"},
        )
        assert calls[0].headers["Authorization"] == "Bearer top-secret"
        assert "top-secret" not in str(calls[0].url)

    def test_429_is_not_retried_and_uses_reset_header(self, monkeypatch):
        monkeypatch.setattr(x_source.time, "time", lambda: 100)
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={"x-rate-limit-reset": "130"})

        with pytest.raises(x_source.XRateLimited) as exc:
            x_source._request_json(
                client_for(handler), "/users/by", token="secret", params={}
            )
        assert exc.value.retry_after_seconds == 60
        assert len(calls) == 1

    def test_retry_after_and_poll_interval_fallbacks(self, monkeypatch):
        monkeypatch.setattr(x_source.time, "time", lambda: 100)
        assert (
            x_source._retry_after(
                httpx.Response(
                    429, headers={"x-rate-limit-reset": "bad", "retry-after": "2.5"}
                )
            )
            == 60
        )
        monkeypatch.setenv("X_POLL_INTERVAL_MINUTES", "7")
        assert (
            x_source._retry_after(httpx.Response(429, headers={"retry-after": "bad"}))
            == 420
        )
        assert x_source._retry_after(httpx.Response(429)) == 420

    def test_transient_status_retries_once(self, monkeypatch):
        monkeypatch.setattr(x_source.time, "sleep", lambda _seconds: None)
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(503 if len(calls) == 1 else 200, json={"data": []})

        assert x_source._request_json(
            client_for(handler), "/users/by", token="secret", params={}
        ) == {"data": []}
        assert len(calls) == 2

    def test_timeout_retries_then_fails_without_secret_in_error(self, monkeypatch):
        monkeypatch.setattr(x_source.time, "sleep", lambda _seconds: None)

        def handler(request):
            raise httpx.ReadTimeout("token=top-secret")

        with pytest.raises(x_source.XRequestError) as exc:
            x_source._request_json(
                client_for(handler), "/users/by", token="top-secret", params={}
            )
        assert "top-secret" not in str(exc.value)

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(401, json={"detail": "secret rejected"}),
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, json=[]),
        ],
    )
    def test_nonretryable_and_invalid_responses_fail_safely(self, response):
        with pytest.raises(x_source.XRequestError):
            x_source._request_json(
                client_for(lambda request: response),
                "/users/by",
                token="secret",
                params={},
            )


class TestNormalization:
    @pytest.mark.parametrize(
        "reference,expected",
        [
            (None, ("original", None)),
            ("replied_to", ("reply", "100")),
            ("retweeted", ("repost", "100")),
            ("quoted", ("quote", "100")),
        ],
    )
    def test_post_kind(self, reference, expected):
        assert x_source._kind(tweet(reference=reference)) == expected

    def test_expanded_url_prefers_unwound_and_deduplicates(self):
        item = tweet(
            urls=[
                {
                    "expanded_url": "https://short",
                    "unwound_url": "https://kap.org.tr/x",
                },
                {"expanded_url": "https://kap.org.tr/x"},
                "bad",
            ]
        )
        assert x_source._expanded_urls(item) == ["https://kap.org.tr/x"]

    def test_normalizes_utc_kap_cashtags_and_public_metadata(self):
        row, rejection = x_source._normalize(
            tweet(
                urls=[
                    {"expanded_url": "https://evil.example/kap.org.tr"},
                    {"expanded_url": "https://kap.org.tr/tr/Bildirim/1#x"},
                ],
                cashtags=["thyao", "thyao", "asels"],
            ),
            {**configured()[0], "external_account_id": "1000"},
            datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        )
        assert rejection is None
        assert row["post_url"] == "https://x.com/test_media/status/200"
        assert row["underlying_source_url"] == "https://kap.org.tr/tr/Bildirim/1"
        assert row["instrument_references"] == ["THYAO", "ASELS"]
        assert row["published_at"].tzinfo == timezone.utc
        assert "Authorization" not in json.dumps(row["raw_metadata"])

    def test_invalid_tweet_shapes_are_skipped(self):
        account = {**configured()[0], "external_account_id": "1000"}
        assert x_source._normalize(
            {"id": "not-numeric"}, account, datetime.now(timezone.utc)
        ) == (None, "invalid_post_id")
        assert x_source._normalize(
            {"id": "1", "created_at": "bad"}, account, datetime.now(timezone.utc)
        ) == (None, "invalid_timestamp")
        assert x_source._normalize(
            {"id": "1", "created_at": "2026-08-27T09:00:00"},
            account,
            datetime.now(timezone.utc),
        ) == (None, "invalid_timestamp")

    def test_reply_and_repost_default_to_excluded(self):
        account = {**configured()[0], "external_account_id": "1000"}
        now = datetime.now(timezone.utc)
        assert x_source._normalize(tweet(reference="replied_to"), account, now) == (
            None,
            "filtered_reply",
        )
        assert x_source._normalize(tweet(reference="retweeted"), account, now) == (
            None,
            "filtered_repost",
        )

    def test_reply_and_repost_can_be_enabled(self, monkeypatch):
        monkeypatch.setenv("X_INCLUDE_REPLIES", "true")
        monkeypatch.setenv("X_INCLUDE_REPOSTS", "true")
        account = {**configured()[0], "external_account_id": "1000"}
        now = datetime.now(timezone.utc)
        reply, _ = x_source._normalize(tweet(reference="replied_to"), account, now)
        repost, _ = x_source._normalize(tweet(reference="retweeted"), account, now)
        assert reply["post_kind"] == "reply"
        assert repost["post_kind"] == "repost"


class TestCollection:
    def test_resolves_handle_paginates_deduplicates_and_builds_cursor(self):
        calls = []
        pages = [
            {"data": [tweet("200"), tweet("201")], "meta": {"next_token": "next"}},
            {"data": [tweet("201"), tweet("202", reference="quoted")], "meta": {}},
        ]
        batch = x_source.collect(
            client_for(api_handler([], pages=pages, calls=calls)),
            token="secret",
            configured=configured(),
            state={},
        )
        assert len(batch.accounts) == 1
        assert [row["external_post_id"] for row in batch.posts] == ["200", "201", "202"]
        assert batch.state_updates["test_media"]["since_id"] == "202"
        assert batch.status["posts_offered"] == 3
        assert any(call.url.params.get("pagination_token") == "next" for call in calls)
        assert calls[-1].url.params["exclude"] == "replies,retweets"

    def test_cached_stable_user_id_skips_handle_lookup(self):
        calls = []
        state = {
            "test_media": {
                "user_id": "1000",
                "handle": "renamed_media",
                "display_name": "Renamed",
                "since_id": "199",
                "identity_checked_at": NOW.isoformat(),
            }
        }
        batch = x_source.collect(
            client_for(api_handler([tweet("200")], calls=calls)),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert not any(call.url.path.endswith("/users/by") for call in calls)
        assert calls[0].url.params["since_id"] == "199"
        assert batch.accounts[0]["handle"] == "renamed_media"

    def test_corrupt_cached_ids_trigger_safe_overlap_and_handle_lookup(self):
        calls = []
        batch = x_source.collect(
            client_for(api_handler([tweet("200")], calls=calls)),
            token="secret",
            configured=configured(),
            state={
                "test_media": {
                    "user_id": "../not-an-id",
                    "since_id": "not-an-id",
                }
            },
        )
        assert any(call.url.path.endswith("/users/by") for call in calls)
        timeline = next(call for call in calls if "/tweets" in call.url.path)
        assert "since_id" not in timeline.url.params
        assert batch.state_updates["test_media"]["since_id"] == "200"

    def test_included_replies_reposts_and_filtered_rows_cover_local_policy(
        self, monkeypatch
    ):
        monkeypatch.setenv("X_INCLUDE_REPLIES", "true")
        monkeypatch.setenv("X_INCLUDE_REPOSTS", "true")
        state = {
            "test_media": {
                "user_id": "1000",
                "handle": "test_media",
                "since_id": "999",
                "identity_checked_at": NOW.isoformat(),
            }
        }
        rows = [
            "not-an-object",
            tweet("200", reference="replied_to"),
            {"id": "bad", "created_at": "2026-08-27T09:00:00Z"},
        ]
        calls = []
        batch = x_source.collect(
            client_for(api_handler(rows, calls=calls)),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert "exclude" not in calls[0].url.params
        assert batch.state_updates["test_media"]["since_id"] == "999"
        assert [row["post_kind"] for row in batch.posts] == ["reply"]

    def test_page_cap_stops_unbounded_pagination(self, monkeypatch):
        monkeypatch.setenv("X_MAX_PAGES_PER_ACCOUNT", "1")
        calls = []
        batch = x_source.collect(
            client_for(
                api_handler(
                    [],
                    pages=[
                        {
                            "data": [tweet("200")],
                            "meta": {"next_token": "more"},
                        }
                    ],
                    calls=calls,
                )
            ),
            token="secret",
            configured=configured(),
            state={},
        )
        assert batch.status["posts_offered"] == 1
        assert sum("/tweets" in call.url.path for call in calls) == 1
        assert batch.state_updates["test_media"]["since_id"] is None
        assert batch.state_updates["test_media"]["resume_token"] == "more"
        assert batch.state_updates["test_media"]["pending_since_id"] == "200"
        assert batch.account_statuses["1000"]["failure_reason"] == "page_cap_reached"

    def test_unknown_account_is_reported_without_timeline_request(self):
        def handler(request):
            return httpx.Response(200, json={"data": []})

        batch = x_source.collect(
            client_for(handler), token="secret", configured=configured(), state={}
        )
        assert batch.posts == []
        assert batch.status["errors"] == [
            {"handle": "test_media", "code": "user_not_found"}
        ]

    def test_inactive_account_is_upserted_but_not_polled(self):
        calls = []
        inactive = [{**configured()[0], "is_active": False}]
        batch = x_source.collect(
            client_for(api_handler([], calls=calls)),
            token="secret",
            configured=inactive,
            state={},
        )
        assert batch.accounts[0]["is_active"] is False
        assert not any("/tweets" in call.url.path for call in calls)
        assert batch.state_updates["test_media"]["user_id"] == "1000"

    def test_account_rate_limit_is_structured_and_other_data_survives(
        self, monkeypatch
    ):
        monkeypatch.setattr(x_source.time, "time", lambda: 100)

        def handler(request):
            if request.url.path.endswith("/users/by"):
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "1000", "username": "test_media", "name": "T"}]
                    },
                )
            return httpx.Response(429, headers={"x-rate-limit-reset": "120"})

        batch = x_source.collect(
            client_for(handler), token="secret", configured=configured(), state={}
        )
        assert batch.status["rate_limited"] is True
        assert batch.status["retry_after_seconds"] == 60
        assert batch.accounts

    def test_account_request_failure_is_isolated(self):
        def handler(request):
            if request.url.path.endswith("/users/by"):
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "1000", "username": "test_media", "name": "T"}]
                    },
                )
            return httpx.Response(403)

        batch = x_source.collect(
            client_for(handler), token="secret", configured=configured(), state={}
        )
        assert batch.status["errors"][0]["code"] == "request_failed"


class TestAccountCompletionContract:
    @staticmethod
    def cached(handle="test_media", user_id="1000", since_id="199"):
        return {
            handle: {
                "user_id": user_id,
                "handle": handle,
                "display_name": handle,
                "since_id": since_id,
                "identity_checked_at": NOW.isoformat(),
            }
        }

    def test_first_page_success_second_page_failure_preserves_cursor(self, monkeypatch):
        monkeypatch.setenv("X_MAX_RETRIES", "0")
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    json={"data": [tweet("200")], "meta": {"next_token": "next"}},
                )
            return httpx.Response(503)

        batch = x_source.collect(
            client_for(handler),
            token="secret",
            configured=configured(),
            state=self.cached(),
            now=NOW,
        )
        assert [post["external_post_id"] for post in batch.posts] == ["200"]
        assert batch.state_updates["test_media"]["since_id"] == "199"
        assert "resume_token" not in batch.state_updates["test_media"]
        assert batch.account_statuses["1000"]["collection_complete"] is False
        assert batch.account_statuses["1000"]["failure_reason"] == "request_failed"

    def test_first_page_success_second_page_rate_limit_preserves_cursor(
        self, monkeypatch
    ):
        monkeypatch.setattr(x_source.time, "time", lambda: int(NOW.timestamp()))
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    json={"data": [tweet("200")], "meta": {"next_token": "next"}},
                )
            return httpx.Response(
                429,
                headers={"x-rate-limit-reset": str(int(NOW.timestamp()) + 120)},
            )

        batch = x_source.collect(
            client_for(handler),
            token="secret",
            configured=configured(),
            state=self.cached(),
            now=NOW,
        )
        assert batch.state_updates["test_media"]["since_id"] == "199"
        assert batch.account_statuses["1000"]["failure_reason"] == "rate_limited"
        assert batch.status["retry_after_seconds"] == 120

    def test_accounts_complete_independently(self, monkeypatch):
        monkeypatch.setenv("X_MAX_RETRIES", "0")
        configured_accounts = [
            configured()[0],
            {
                **configured()[0],
                "handle": "second_media",
            },
        ]
        state = {
            **self.cached(),
            **self.cached("second_media", "2000"),
        }
        second_calls = 0

        def handler(request):
            nonlocal second_calls
            if "/users/1000/tweets" in request.url.path:
                return httpx.Response(200, json={"data": [tweet("200")], "meta": {}})
            second_calls += 1
            if second_calls == 1:
                return httpx.Response(
                    200,
                    json={"data": [tweet("300")], "meta": {"next_token": "next"}},
                )
            return httpx.Response(403)

        batch = x_source.collect(
            client_for(handler),
            token="secret",
            configured=configured_accounts,
            state=state,
            now=NOW,
        )
        assert batch.state_updates["test_media"]["since_id"] == "200"
        assert batch.state_updates["second_media"]["since_id"] == "199"
        assert batch.account_statuses["1000"]["collection_complete"] is True
        assert batch.account_statuses["2000"]["collection_complete"] is False

    def test_page_cap_resumes_then_promotes_high_watermark(self, monkeypatch):
        monkeypatch.setenv("X_MAX_PAGES_PER_ACCOUNT", "1")
        first = x_source.collect(
            client_for(
                lambda request: httpx.Response(
                    200,
                    json={"data": [tweet("200")], "meta": {"next_token": "resume"}},
                )
            ),
            token="secret",
            configured=configured(),
            state=self.cached(),
            now=NOW,
        )
        checkpoint = first.state_updates
        assert checkpoint["test_media"]["since_id"] == "199"
        assert checkpoint["test_media"]["pending_since_id"] == "200"

        calls = []

        def final_page(request):
            calls.append(request)
            return httpx.Response(200, json={"data": [tweet("199")], "meta": {}})

        second = x_source.collect(
            client_for(final_page),
            token="secret",
            configured=configured(),
            state=checkpoint,
            now=NOW + timedelta(minutes=10),
        )
        assert calls[0].url.params["pagination_token"] == "resume"
        assert second.state_updates["test_media"]["since_id"] == "200"
        assert "resume_token" not in second.state_updates["test_media"]
        assert second.account_statuses["1000"]["collection_complete"] is True


class TestIdentityRefresh:
    def test_renamed_account_and_stale_display_name_refresh_by_stable_id(self):
        calls = []
        state = {
            "test_media": {
                "user_id": "1000",
                "handle": "old_name",
                "display_name": "Stale",
                "since_id": "199",
                "identity_checked_at": (NOW - timedelta(hours=25)).isoformat(),
            }
        }

        def handler(request):
            calls.append(request)
            if request.url.path.endswith("/users"):
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": "1000",
                                "username": "renamed_media",
                                "name": "Current Name",
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"data": [], "meta": {}})

        batch = x_source.collect(
            client_for(handler),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert batch.accounts[0]["external_account_id"] == "1000"
        assert batch.accounts[0]["handle"] == "renamed_media"
        assert batch.accounts[0]["display_name"] == "Current Name"
        assert any(call.url.params.get("ids") == "1000" for call in calls)

    def test_handle_reassignment_cannot_rebind_pinned_identity(self):
        paths = []
        state = {
            "test_media": {
                "user_id": "1000",
                "handle": "old_name",
                "identity_checked_at": (NOW - timedelta(hours=25)).isoformat(),
            }
        }

        def handler(request):
            paths.append(request.url.path)
            if request.url.path.endswith("/users/by"):
                return httpx.Response(
                    200,
                    json={"data": [{"id": "9999", "username": "test_media"}]},
                )
            if request.url.path.endswith("/users"):
                return httpx.Response(
                    200,
                    json={"data": [{"id": "1000", "username": "renamed_media"}]},
                )
            assert "/users/1000/tweets" in request.url.path
            return httpx.Response(200, json={"data": [], "meta": {}})

        batch = x_source.collect(
            client_for(handler),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert not any(path.endswith("/users/by") for path in paths)
        assert batch.accounts[0]["external_account_id"] == "1000"


class TestProviderCooldown:
    def test_creation_expiry_and_persistence(self, tmp_path):
        target = tmp_path / "state.json"
        update = x_source.provider_cooldown_update(120, NOW)
        assert x_source.save_state(update, str(target))
        loaded = x_source.load_state(str(target))
        assert x_source.cooldown_remaining(loaded, NOW) == 120
        assert x_source.cooldown_remaining(loaded, NOW + timedelta(seconds=121)) == 0

    def test_retry_values_are_bounded_and_malformed_values_fall_back(self, monkeypatch):
        monkeypatch.setattr(x_source.time, "time", lambda: int(NOW.timestamp()))
        monkeypatch.setenv("X_POLL_INTERVAL_MINUTES", "7")
        malformed = httpx.Response(
            429,
            headers={"x-rate-limit-reset": "bad", "retry-after": "not-a-number"},
        )
        huge = httpx.Response(429, headers={"retry-after": "999999999"})
        assert x_source._retry_after(malformed) == 7 * 60
        assert x_source._retry_after(huge) == x_source.MAX_COOLDOWN_SECONDS
        assert (
            x_source.provider_cooldown_update(1, NOW)["_provider"]["blocked_until"]
            == (NOW + timedelta(seconds=x_source.MIN_COOLDOWN_SECONDS)).isoformat()
        )

    def test_invalid_or_naive_cooldown_timestamps_are_inactive(self):
        assert x_source._parse_utc("not-a-time") is None
        assert x_source._parse_utc("2026-08-27T09:00:00") is None
        assert (
            x_source.cooldown_remaining(
                {"_provider": {"blocked_until": "not-a-time"}}, NOW
            )
            == 0
        )


class TestFailedRefreshAndPaginationRecovery:
    def test_missing_stable_user_is_not_rebound_or_polled(self):
        calls = []
        state = {
            "test_media": {
                "user_id": "1000",
                "handle": "old",
                "identity_checked_at": (NOW - timedelta(days=2)).isoformat(),
            }
        }

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"data": []})

        batch = x_source.collect(
            client_for(handler),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert batch.accounts == []
        assert batch.status["errors"] == [
            {"handle": "test_media", "code": "stable_user_not_found"}
        ]
        assert not any("/tweets" in call.url.path for call in calls)

    def test_invalid_timeline_shape_preserves_cursor(self):
        state = TestAccountCompletionContract.cached()
        batch = x_source.collect(
            client_for(
                lambda request: httpx.Response(
                    200, json={"data": {"unexpected": "object"}}
                )
            ),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert batch.state_updates["test_media"]["since_id"] == "199"
        assert batch.account_statuses["1000"]["failure_reason"] == "request_failed"

    def test_locally_invalid_post_still_advances_completed_provider_cursor(self):
        state = TestAccountCompletionContract.cached()
        batch = x_source.collect(
            client_for(
                lambda request: httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": "200",
                                "created_at": "invalid",
                            }
                        ],
                        "meta": {},
                    },
                )
            ),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert batch.posts == []
        assert batch.state_updates["test_media"]["since_id"] == "200"
        assert batch.status["normalization_rejected"] == 1
        assert batch.status["normalization_rejections"] == {"invalid_timestamp": 1}

    def test_expired_pagination_token_is_cleared_without_cursor_advance(self):
        state = TestAccountCompletionContract.cached()
        state["test_media"].update(
            {"resume_token": "expired", "pending_since_id": "250"}
        )
        batch = x_source.collect(
            client_for(lambda request: httpx.Response(400)),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        update = batch.state_updates["test_media"]
        assert update["since_id"] == "199"
        assert "resume_token" not in update
        assert "pending_since_id" not in update
        assert (
            batch.account_statuses["1000"]["failure_reason"]
            == "invalid_pagination_token"
        )


class TestNormalizationObservability:
    def test_collect_exposes_filtered_and_malformed_rejection_counts(self, monkeypatch):
        monkeypatch.setenv("X_INCLUDE_REPLIES", "false")
        monkeypatch.setenv("X_INCLUDE_REPOSTS", "false")
        state = TestAccountCompletionContract.cached()
        rows = [
            "not-an-object",
            {"id": "bad-id", "created_at": "2026-08-27T09:00:00Z"},
            tweet("200", reference="replied_to"),
            tweet("201", reference="retweeted"),
            {"id": "202", "created_at": "not-a-timestamp", "text": "x"},
            tweet("203"),
        ]
        batch = x_source.collect(
            client_for(api_handler(rows)),
            token="secret",
            configured=configured(),
            state=state,
            now=NOW,
        )
        assert [row["external_post_id"] for row in batch.posts] == ["203"]
        assert batch.status["normalization_rejections"] == {
            "filtered_reply": 1,
            "filtered_repost": 1,
            "invalid_post_id": 1,
            "invalid_shape": 1,
            "invalid_timestamp": 1,
        }
        assert batch.status["normalization_rejected"] == 5
        # Completed provider cursor still advances despite local rejections.
        assert batch.state_updates["test_media"]["since_id"] == "203"


class TestCursorState:
    def test_missing_invalid_and_wrong_shape_state_refetches(self, tmp_path):
        target = tmp_path / "state.json"
        assert x_source.load_state(str(target)) == {}
        target.write_text("{", encoding="utf-8")
        assert x_source.load_state(str(target)) == {}
        target.write_text("[]", encoding="utf-8")
        assert x_source.load_state(str(target)) == {}

    def test_save_merges_and_round_trips(self, tmp_path):
        target = tmp_path / "state.json"
        target.write_text('{"old":{"user_id":"1"}}', encoding="utf-8")
        assert x_source.save_state(
            {"new": {"user_id": "2", "since_id": "3"}}, str(target)
        )
        assert x_source.load_state(str(target)) == {
            "old": {"user_id": "1"},
            "new": {"user_id": "2", "since_id": "3"},
        }

    def test_save_failure_is_nonfatal(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            x_source.os, "replace", lambda *args: (_ for _ in ()).throw(OSError())
        )
        assert (
            x_source.save_state({"x": {"user_id": "1"}}, str(tmp_path / "s")) is False
        )

    def test_cleanup_failure_after_save_error_is_nonfatal(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            x_source.os, "replace", lambda *args: (_ for _ in ()).throw(OSError())
        )
        monkeypatch.setattr(
            x_source.Path,
            "unlink",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError()),
        )
        assert not x_source.save_state({"x": {"user_id": "1"}}, str(tmp_path / "s"))


def test_api_test_handler_rejects_an_unexpected_path():
    with pytest.raises(AssertionError):
        api_handler([])(httpx.Request("GET", "https://api.x.com/2/unexpected"))


def test_network_guard_blocks_real_socket_access():
    import socket

    with socket.socket() as sock, pytest.raises(RuntimeError, match="stub HTTP"):
        sock.connect(("127.0.0.1", 1))
