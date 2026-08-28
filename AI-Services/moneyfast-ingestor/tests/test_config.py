"""Configuration resolution."""

from __future__ import annotations

import json

import pytest

from ingestor import config


class TestDefaults:
    def test_service_urls_are_container_names(self):
        """localhost inside a container is the container itself."""
        assert config.backend_url() == "http://backend:8000/api"
        assert config.rag_url() == "http://rag:8100"

    def test_trailing_slash_is_stripped(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_BASE_URL", "http://backend:8000/api/")
        assert config.backend_url() == "http://backend:8000/api"

    def test_missing_token_is_none_not_empty_string(self):
        """An empty string would build the header `Bearer `, which reads as a
        malformed credential rather than an absent one."""
        assert config.service_token() is None

    def test_feeds_are_split_and_trimmed(self, monkeypatch):
        monkeypatch.setenv(
            "NEWS_FEEDS", " https://a.example/rss , https://b.example/rss "
        )
        assert config.feeds() == ["https://a.example/rss", "https://b.example/rss"]

    def test_empty_feed_entries_are_dropped(self, monkeypatch):
        monkeypatch.setenv("NEWS_FEEDS", "https://a.example/rss,,  ,")
        assert config.feeds() == ["https://a.example/rss"]

    def test_default_feeds_are_configured(self):
        assert len(config.feeds()) >= 1


class TestUserAgent:
    def test_identifies_the_project_and_offers_contact(self):
        """Disguising the client as a browser is the first step of the
        evasion approach this project does not take. An operator who wants to
        block us should be able to see who we are."""
        agent = config.user_agent()
        assert "MoneyFastBot" in agent
        assert "http" in agent
        assert "Mozilla" not in agent

    def test_is_overridable(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_USER_AGENT", "Custom/1.0")
        assert config.user_agent() == "Custom/1.0"


class TestNumericSettings:
    def test_defaults(self):
        assert config.request_timeout() == 20.0
        assert config.per_host_delay() == 2.0
        assert config.quote_interval_seconds() == 30
        assert config.history_days() == 400

    def test_garbage_falls_back_instead_of_crashing_the_service(self, monkeypatch):
        """A typo in an env var should not stop data collection entirely."""
        monkeypatch.setenv("INGESTOR_TIMEOUT_SECONDS", "soon")
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "often")
        assert config.request_timeout() == 20.0
        assert config.quote_interval_seconds() == 30

    def test_valid_overrides_are_honoured(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_HOST_DELAY_SECONDS", "5.5")
        monkeypatch.setenv("INGESTOR_NEWS_INTERVAL_MINUTES", "30")
        assert config.per_host_delay() == 5.5
        assert config.news_interval_minutes() == 30


class TestRobots:
    def test_respected_by_default(self):
        assert config.respect_robots() is True

    def test_only_the_exact_string_false_disables_it(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_RESPECT_ROBOTS", "false")
        assert config.respect_robots() is False
        monkeypatch.setenv("INGESTOR_RESPECT_ROBOTS", "0")
        assert config.respect_robots() is True


class TestEmptyEnvironmentOverrides:
    """Compose renders `${VAR:-}` as an empty string, which getenv reports as
    SET. Using it as a value silently disabled news collection in the first
    live run of this service."""

    def test_empty_news_feeds_falls_back_to_the_defaults(self, monkeypatch):
        monkeypatch.setenv("NEWS_FEEDS", "")
        assert config.feeds() == config.DEFAULT_FEEDS.split(",")

    def test_empty_user_agent_falls_back(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_USER_AGENT", "")
        assert "MoneyFastBot" in config.user_agent()


class TestQuoteInterval:
    def test_thirty_seconds_by_default(self):
        """Raised from 10s when the universe doubled to ~190 symbols across
        two markets. A clean cycle is a few seconds, but one chunk that has to
        time out pushes it past ten, and every overrun was logged as a skipped
        run. A budget the cycle can meet beats a number that looks live."""
        assert config.quote_interval_seconds() == 30

    def test_is_overridable(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "30")
        assert config.quote_interval_seconds() == 30

    def test_has_a_floor_against_a_config_typo(self, monkeypatch):
        """A stray 0 or 1 would turn this into a request flood aimed at a
        provider that will rate limit and then block us."""
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "0")
        assert config.quote_interval_seconds() == 5


class TestXConfiguration:
    def test_disabled_safe_defaults(self):
        assert config.x_ingest_enabled() is False
        assert config.x_bearer_token() is None
        assert config.x_include_replies() is False
        assert config.x_include_reposts() is False
        assert config.x_poll_interval_minutes() == 10
        assert config.x_max_pages_per_account() == 3
        assert config.x_backend_batch_size() == 500
        assert config.x_identity_refresh_hours() == 24
        assert config.x_max_retries() == 1
        assert config.x_state_file() == "/app/state/x-cursors.json"

    def test_boolean_and_numeric_overrides_are_bounded(self, monkeypatch):
        monkeypatch.setenv("X_INGEST_ENABLED", "yes")
        monkeypatch.setenv("X_INCLUDE_REPLIES", "1")
        monkeypatch.setenv("X_INCLUDE_REPOSTS", "on")
        monkeypatch.setenv("X_POLL_INTERVAL_MINUTES", "1")
        monkeypatch.setenv("X_MAX_PAGES_PER_ACCOUNT", "99")
        monkeypatch.setenv("X_BACKEND_BATCH_SIZE", "5000")
        monkeypatch.setenv("X_IDENTITY_REFRESH_HOURS", "0")
        monkeypatch.setenv("X_MAX_RETRIES", "-2")
        monkeypatch.setenv("X_STATE_FILE", "")
        assert config.x_ingest_enabled() is True
        assert config.x_include_replies() is True
        assert config.x_include_reposts() is True
        assert config.x_poll_interval_minutes() == 5
        assert config.x_max_pages_per_account() == 10
        assert config.x_backend_batch_size() == 1_000
        assert config.x_identity_refresh_hours() == 1
        assert config.x_max_retries() == 0
        assert config.x_state_file() == "/app/state/x-cursors.json"

    def test_environment_token_fallback(self, monkeypatch):
        monkeypatch.setenv("X_BEARER_TOKEN", "development-token")
        assert config.x_bearer_token() == "development-token"

    def test_file_token_takes_precedence(self, monkeypatch, tmp_path):
        token_file = tmp_path / "token"
        token_file.write_text("file-token\n", encoding="utf-8")
        monkeypatch.setenv("X_BEARER_TOKEN_FILE", str(token_file))
        monkeypatch.setenv("X_BEARER_TOKEN", "environment-token")
        assert config.x_bearer_token() == "file-token"

    def test_configured_bad_token_file_fails_closed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("X_BEARER_TOKEN_FILE", str(tmp_path / "missing"))
        monkeypatch.setenv("X_BEARER_TOKEN", "must-not-fallback")
        with pytest.raises(config.XConfigurationError, match="unreadable"):
            config.x_bearer_token()

    def test_empty_token_file_is_invalid(self, monkeypatch, tmp_path):
        token_file = tmp_path / "token"
        token_file.write_text(" \n", encoding="utf-8")
        monkeypatch.setenv("X_BEARER_TOKEN_FILE", str(token_file))
        with pytest.raises(config.XConfigurationError, match="empty"):
            config.x_bearer_token()

    def test_allowlist_is_normalized(self, monkeypatch):
        monkeypatch.setenv(
            "X_MONITORED_ACCOUNTS_JSON",
            '[{"handle":"@TEST_MEDIA","source_type":"financial_media",'
            '"trust_score":0.75}]',
        )
        assert config.x_monitored_accounts() == [
            {
                "handle": "test_media",
                "source_type": "financial_media",
                "trust_score": 0.75,
                "is_active": True,
            }
        ]

    def test_allowlist_is_bounded_to_the_api_lookup_limit(self, monkeypatch):
        entries = [
            {
                "handle": f"test{i}",
                "source_type": "analyst",
                "trust_score": 0.5,
            }
            for i in range(101)
        ]
        monkeypatch.setenv("X_MONITORED_ACCOUNTS_JSON", json.dumps(entries))
        with pytest.raises(config.XConfigurationError, match="at most 100"):
            config.x_monitored_accounts()

    @pytest.mark.parametrize(
        "raw,message",
        [
            ("", "empty"),
            ("{", "valid JSON"),
            ("{}", "non-empty array"),
            ("[]", "non-empty array"),
            ('["x"]', "object"),
            (
                '[{"handle":"bad-handle!","source_type":"analyst","trust_score":1}]',
                "handle",
            ),
            (
                '[{"handle":"same","source_type":"analyst","trust_score":1},'
                '{"handle":"same","source_type":"analyst","trust_score":1}]',
                "unique",
            ),
            (
                '[{"handle":"test","source_type":"blogger","trust_score":1}]',
                "unsupported",
            ),
            ('[{"handle":"test","source_type":"analyst","trust_score":2}]', "between"),
            ('[{"handle":"test","source_type":"analyst"}]', "numeric"),
        ],
    )
    def test_invalid_allowlists_fail_closed(self, monkeypatch, raw, message):
        monkeypatch.setenv("X_MONITORED_ACCOUNTS_JSON", raw)
        with pytest.raises(config.XConfigurationError, match=message):
            config.x_monitored_accounts()
