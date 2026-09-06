"""Configuration resolution."""

from __future__ import annotations

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
        assert config.quote_interval_seconds() == 300
        assert config.band_interval_seconds() == 30
        assert config.history_days() == 730

    def test_garbage_falls_back_instead_of_crashing_the_service(self, monkeypatch):
        """A typo in an env var should not stop data collection entirely."""
        monkeypatch.setenv("INGESTOR_TIMEOUT_SECONDS", "soon")
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "often")
        assert config.request_timeout() == 20.0
        assert config.quote_interval_seconds() == 300

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
    def test_five_minutes_by_default(self):
        """Beş dakika: bir işlem gününe tam 78 tane 5 dakikalık bar sığıyor ve
        gün içi grafik o kadar noktaya ihtiyaç duyuyor.

        Was 30 SECONDS, over the whole universe.

        `docker-compose.yml` set `INGESTOR_QUOTE_INTERVAL_MINUTES: 15`, but no
        code ever read that name -- the setting had never taken effect. At a
        universe of ~1000 instruments a per-30s sweep is two thousand provider
        requests a minute.

        The band (FX, gold, index) stays fast on its own job, and a symbol the
        chat asks about is refreshed on demand, so the bulk interval never
        means a stale answer where staleness would matter.
        """
        assert config.quote_interval_seconds() == 300

    def test_the_minutes_name_is_the_one_compose_sets(self, monkeypatch):
        """The name that had no effect for the whole life of the setting.

        10 dakika, çünkü bütçe aşılırsa gidilecek yer orası."""
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_MINUTES", "10")
        assert config.quote_interval_seconds() == 600

    def test_seconds_still_wins_when_given(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "30")
        assert config.quote_interval_seconds() == 30


class TestBandInterval:
    """Kur/altın/endeks şeridi: küçük küme, sık tur."""

    def test_thirty_seconds_by_default(self):
        assert config.band_interval_seconds() == 30

    def test_is_overridable(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_BAND_INTERVAL_SECONDS", "10")
        assert config.band_interval_seconds() == 10

    def test_has_the_same_floor(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_BAND_INTERVAL_SECONDS", "0")
        assert config.band_interval_seconds() == 5


class TestBandMembership:
    """Hangi enstrüman hızlı katmanda."""

    def test_fx_and_gold_are_band(self):
        assert config.is_band_product({"market": "FX"})
        assert config.is_band_product({"market": "COMEX"})

    def test_an_index_is_band_whatever_its_venue(self):
        """Endeks bir borsada işlem görüyor ama şeridin parçası."""
        assert config.is_band_product({"market": "BIST", "product_type": "index"})

    def test_a_stock_is_not(self):
        assert not config.is_band_product({"market": "BIST", "product_type": "stock"})
        assert not config.is_band_product({"market": "NASDAQ", "product_type": "stock"})

    def test_has_a_floor_against_a_config_typo(self, monkeypatch):
        """A stray 0 or 1 would turn this into a request flood aimed at a
        provider that will rate limit and then block us."""
        monkeypatch.setenv("INGESTOR_QUOTE_INTERVAL_SECONDS", "0")
        assert config.quote_interval_seconds() == 5


class TestKap:
    def test_defaults(self):
        assert config.kap_base_url() == "https://www.kap.org.tr"
        assert config.kap_interval_minutes() == 20
        # Ölçüldü: bir hafta 1101 satır, altmış gün tam 2000 (tavan). Üç gün
        # ~470 satır demek, yani olağan durumda pencere hiç bölünmüyor.
        assert config.kap_window_days() == 3
        assert config.kap_backfill_days() == 183

    def test_overrides_are_honoured_and_a_trailing_slash_is_dropped(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_BASE_URL", "https://example.test/")
        monkeypatch.setenv("INGESTOR_KAP_INTERVAL_MINUTES", "5")
        monkeypatch.setenv("INGESTOR_KAP_WINDOW_DAYS", "7")
        monkeypatch.setenv("INGESTOR_KAP_BACKFILL_DAYS", "30")
        assert config.kap_base_url() == "https://example.test"
        assert config.kap_interval_minutes() == 5
        assert config.kap_window_days() == 7
        assert config.kap_backfill_days() == 30

    def test_nonsense_values_fall_back_rather_than_crashing_the_service(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_INTERVAL_MINUTES", "soon")
        monkeypatch.setenv("INGESTOR_KAP_WINDOW_DAYS", "0")
        assert config.kap_interval_minutes() == 20
        assert config.kap_window_days() == 1


class TestTefasConfig:
    """TEFAS varsayılan olarak KAPALI.

    Bu kaynak sitenin `robots.txt`'inde belirttiği tercihi geçersiz kılıyor;
    klonlayan bir ekip arkadaşının farkında olmadan devreye sokması doğru
    olmaz -- açmak bilinçli bir adım olmalı.
    """

    def test_it_is_off_unless_asked_for(self, monkeypatch):
        monkeypatch.delenv("INGESTOR_TEFAS_ENABLED", raising=False)
        assert config.tefas_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", " Yes "])
    def test_it_turns_on_explicitly(self, monkeypatch, value):
        monkeypatch.setenv("INGESTOR_TEFAS_ENABLED", value)
        assert config.tefas_enabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "belki"])
    def test_anything_else_leaves_it_off(self, monkeypatch, value):
        monkeypatch.setenv("INGESTOR_TEFAS_ENABLED", value)
        assert config.tefas_enabled() is False

    def test_the_base_url_is_overridable_and_trimmed(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_TEFAS_BASE_URL", "https://x.invalid/")
        assert config.tefas_base_url() == "https://x.invalid"

    def test_budgets_default_and_never_go_negative(self, monkeypatch):
        """Bütçe fon BAŞINA bir istek demek; negatif bir bütçe dilimlemeyi
        tersine çevirirdi.

        Şemsiye bütçesi KALKTI: şemsiye eşlemesi artık fon başına değil,
        şemsiye başına bir istek (on iki istek, 2.602 değil), dolayısıyla
        dilimlenecek bir şey yok."""
        monkeypatch.delenv("INGESTOR_TEFAS_PRICE_BUDGET", raising=False)
        assert config.tefas_price_budget() == 150
        monkeypatch.setenv("INGESTOR_TEFAS_PRICE_BUDGET", "-5")
        assert config.tefas_price_budget() == 0
