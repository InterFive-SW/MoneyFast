"""Configuration resolution."""

from __future__ import annotations

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
        monkeypatch.setenv("NEWS_FEEDS", " https://a.example/rss , https://b.example/rss ")
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
        assert config.quote_interval_seconds() == 10
        assert config.history_days() == 400

    def test_garbage_falls_back_instead_of_crashing_the_service(self, monkeypatch):
        """A typo in an env var should not stop data collection entirely."""
        monkeypatch.setenv("INGESTOR_TIMEOUT_SECONDS", "soon")
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "often")
        assert config.request_timeout() == 20.0
        assert config.quote_interval_seconds() == 10

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
    def test_ten_seconds_by_default(self):
        """Achievable because the universe is fetched in ONE batched request:
        measured 3.3-5.4s for ~95 symbols."""
        assert config.quote_interval_seconds() == 10

    def test_is_overridable(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "30")
        assert config.quote_interval_seconds() == 30

    def test_has_a_floor_against_a_config_typo(self, monkeypatch):
        """A stray 0 or 1 would turn this into a request flood aimed at a
        provider that will rate limit and then block us."""
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "0")
        assert config.quote_interval_seconds() == 5
