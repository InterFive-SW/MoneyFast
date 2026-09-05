"""Anahtarlı haber sağlayıcıları — Finnhub ve Marketaux.

Korunan iddialar:

* **anahtarı olmayan sağlayıcı sessizce atlanıyor.** Compose `${VAR:-}` boş
  DİZE üretiyor ve `getenv` için boş dize "set" demek; `or None` olmasaydı
  her tur boş bir anahtarla istek atıp 401 alırdı;
* **tarihsiz haber atılıyor, bugüne damgalanmıyor.** Sağlayıcı için tarih
  zorunlu bir alan ve gelmemesi biçim değişikliği demek; sessizce bugüne
  damgalamak eski bir haberi yeni gibi gösterirdi;
* **çıkan sözlük diğer kaynaklarınkiyle aynı**, `content_hash` öneksiz:
  aynı haber iki sağlayıcıdan gelirse tek satır.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from ingestor.sources import courtesy, news_api_source
from ingestor.sources.gdelt_source import content_hash

_RealClient = httpx.Client

NEWS_KEYS = {
    "content_hash", "title", "summary", "source", "url",
    "language", "related_symbols", "published_at",
}


def client_for(handler) -> httpx.Client:
    return _RealClient(transport=httpx.MockTransport(handler))


def handler_for(payload, status=200, text=None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="nope")
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, text=json.dumps(payload))

    handler.calls = calls
    return handler


def finnhub_row(**over):
    row = {
        "headline": "Oil climbs after refinery strike",
        "summary": "Crude rose 4% as traders priced in supply risk.",
        "source": "Reuters",
        "url": "https://example.invalid/oil",
        "datetime": 1788160500,
    }
    row.update(over)
    return row


def marketaux_row(**over):
    row = {
        "title": "Fed signals caution on rate path",
        "description": "Policymakers flagged inflation risk.",
        "source": "bloomberg.com",
        "url": "https://example.invalid/fed",
        "language": "en",
        "published_at": "2026-09-05T09:12:00.000000Z",
    }
    row.update(over)
    return row


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "fh-key")
    monkeypatch.setenv("MARKETAUX_API_KEY", "mx-key")


class TestSkippedWithoutAKey:
    def test_no_key_means_no_request(self, monkeypatch):
        handler = handler_for([finnhub_row()])
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []
        assert handler.calls == []

    def test_an_empty_string_key_counts_as_absent(self, monkeypatch):
        """Compose `${FINNHUB_API_KEY:-}` boş DİZE üretiyor ve `getenv` için
        bu "set" demek -- `or None` olmasaydı her tur 401 alırdı."""
        handler = handler_for([finnhub_row()])
        monkeypatch.setenv("FINNHUB_API_KEY", "")
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []
        assert handler.calls == []


class TestFinnhub:
    def test_a_row_becomes_a_news_item(self, keys):
        handler = handler_for([finnhub_row()])
        items = news_api_source.fetch_provider("finnhub", client_for(handler))
        assert len(items) == 1
        assert set(items[0]) == NEWS_KEYS
        assert items[0]["title"] == "Oil climbs after refinery strike"
        assert items[0]["source"] == "Reuters"
        assert items[0]["published_at"] == datetime(
            2026, 8, 31, 7, 15, tzinfo=timezone.utc,
        )

    def test_the_key_travels_as_token(self, keys):
        handler = handler_for([])
        news_api_source.fetch_provider("finnhub", client_for(handler))
        assert handler.calls[-1].url.params["token"] == "fh-key"

    def test_a_row_without_a_headline_is_dropped(self, keys):
        handler = handler_for([finnhub_row(headline="  ")])
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []

    @pytest.mark.parametrize("stamp", [None, 0, -5, "dün"])
    def test_an_undatable_row_is_dropped_not_stamped_now(self, keys, stamp):
        """Sessizce bugüne damgalamak, eski bir haberi yeni gibi gösterirdi."""
        handler = handler_for([finnhub_row(datetime=stamp)])
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []

    def test_a_missing_publisher_does_not_claim_authorship(self, keys):
        handler = handler_for([finnhub_row(source="")])
        assert news_api_source.fetch_provider(
            "finnhub", client_for(handler))[0]["source"] == "Finnhub"

    def test_a_missing_url_is_null(self, keys):
        handler = handler_for([finnhub_row(url="")])
        assert news_api_source.fetch_provider(
            "finnhub", client_for(handler))[0]["url"] is None

    def test_an_empty_summary_is_null_not_an_empty_string(self, keys):
        handler = handler_for([finnhub_row(summary="")])
        assert news_api_source.fetch_provider(
            "finnhub", client_for(handler))[0]["summary"] is None

    def test_a_non_list_body_yields_nothing(self, keys):
        handler = handler_for({"error": "nope"})
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []

    def test_non_object_rows_are_skipped(self, keys):
        handler = handler_for(["oops", finnhub_row()])
        assert len(news_api_source.fetch_provider("finnhub", client_for(handler))) == 1


class TestMarketaux:
    def test_a_row_becomes_a_news_item(self, keys):
        handler = handler_for({"data": [marketaux_row()]})
        items = news_api_source.fetch_provider("marketaux", client_for(handler))
        assert len(items) == 1
        assert set(items[0]) == NEWS_KEYS
        assert items[0]["published_at"] == datetime(
            2026, 9, 5, 9, 12, tzinfo=timezone.utc,
        )

    def test_the_key_travels_as_api_token(self, keys):
        handler = handler_for({"data": []})
        news_api_source.fetch_provider("marketaux", client_for(handler))
        assert handler.calls[-1].url.params["api_token"] == "mx-key"

    def test_the_snippet_is_used_when_there_is_no_description(self, keys):
        handler = handler_for({"data": [marketaux_row(description="", snippet="kısa")]})
        assert news_api_source.fetch_provider(
            "marketaux", client_for(handler))[0]["summary"] == "kısa"

    def test_entities_are_not_read_here(self, keys):
        """Sembol çözümü tek bir yerde, backend'de. İki yerde çözmek iki
        farklı evren demek."""
        handler = handler_for({"data": [marketaux_row(entities=[{"symbol": "AAPL"}])]})
        assert news_api_source.fetch_provider(
            "marketaux", client_for(handler))[0]["related_symbols"] == []

    @pytest.mark.parametrize("stamp", ["", None, "dün", "2026-13-45"])
    def test_an_unparsable_date_drops_the_row(self, keys, stamp):
        handler = handler_for({"data": [marketaux_row(published_at=stamp)]})
        assert news_api_source.fetch_provider("marketaux", client_for(handler)) == []

    def test_a_naive_timestamp_is_read_as_utc(self, keys):
        handler = handler_for({"data": [marketaux_row(published_at="2026-09-05T09:12:00")]})
        item = news_api_source.fetch_provider("marketaux", client_for(handler))[0]
        assert item["published_at"].tzinfo is timezone.utc

    def test_a_row_without_a_title_is_dropped(self, keys):
        handler = handler_for({"data": [marketaux_row(title="")]})
        assert news_api_source.fetch_provider("marketaux", client_for(handler)) == []

    def test_a_missing_language_defaults_to_english(self, keys):
        handler = handler_for({"data": [marketaux_row(language="")]})
        assert news_api_source.fetch_provider(
            "marketaux", client_for(handler))[0]["language"] == "en"

    def test_a_bodyless_reply_yields_nothing(self, keys):
        handler = handler_for({"meta": {}})
        assert news_api_source.fetch_provider("marketaux", client_for(handler)) == []

    def test_a_non_object_body_yields_nothing(self, keys):
        handler = handler_for(["oops"])
        assert news_api_source.fetch_provider("marketaux", client_for(handler)) == []

    def test_non_object_rows_are_skipped(self, keys):
        handler = handler_for({"data": ["oops", marketaux_row()]})
        assert len(news_api_source.fetch_provider("marketaux", client_for(handler))) == 1


class TestFailures:
    @pytest.mark.parametrize("status", [401, 403])
    def test_a_rejected_key_is_logged_apart_from_a_missing_one(
        self, keys, caplog, status,
    ):
        """"Anahtar yok" ile "anahtar kabul edilmedi" farklı tamir
        talimatları."""
        handler = handler_for(None, status=status, text="denied")
        with caplog.at_level("WARNING"):
            assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []
        assert "rejected the API key" in caplog.text

    def test_a_rate_limit_backs_off(self, keys, caplog):
        handler = handler_for(None, status=429, text="slow down")
        with caplog.at_level("WARNING"):
            assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []
        assert "rate limited" in caplog.text

    def test_a_server_error_does_not_raise(self, keys):
        handler = handler_for(None, status=503, text="down")
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []

    def test_a_non_json_body_does_not_raise(self, keys):
        handler = handler_for(None, text="<html>error</html>")
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []

    def test_an_unreachable_host_does_not_raise(self, keys):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            raise httpx.ConnectError("refused")

        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []

    def test_robots_is_honoured(self, keys, monkeypatch):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            return httpx.Response(200, text=json.dumps([finnhub_row()]))

        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []


class TestRelevanceIsApplied:
    def test_a_sport_headline_never_reaches_the_corpus(self, keys):
        handler = handler_for([finnhub_row(
            headline="Premier League club signs striker", summary="Record fee.")])
        assert news_api_source.fetch_provider("finnhub", client_for(handler)) == []

    def test_a_war_headline_does(self, keys):
        """Bir savaş ekonomik bir olaydır."""
        handler = handler_for([finnhub_row(
            headline="US strikes halt shipping through the strait",
            summary="Oil price jumped on the news.")])
        assert len(news_api_source.fetch_provider("finnhub", client_for(handler))) == 1


class TestCourtesy:
    def test_each_provider_gets_its_own_floor(self, keys, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            courtesy, "wait_for_host",
            lambda url, minimum=0.0: seen.__setitem__(url.split('/')[2], minimum),
        )
        news_api_source.fetch_provider("finnhub", client_for(handler_for([])))
        news_api_source.fetch_provider("marketaux", client_for(handler_for({"data": []})))
        assert seen["finnhub.io"] == news_api_source.PROVIDERS["finnhub"].min_delay
        assert seen["api.marketaux.com"] == news_api_source.PROVIDERS["marketaux"].min_delay

    def test_the_user_agent_names_the_project(self, keys):
        handler = handler_for([])
        news_api_source.fetch_provider("finnhub", client_for(handler))
        assert "MoneyFast" in handler.calls[-1].headers["User-Agent"]


class TestFetchAll:
    def test_every_provider_is_asked(self, monkeypatch):
        asked = []
        monkeypatch.setattr(
            news_api_source, "fetch_provider",
            lambda name, client: asked.append(name) or [],
        )
        news_api_source.fetch_all()
        assert asked == list(news_api_source.PROVIDERS)

    def test_the_same_story_from_two_providers_is_one_row(self, monkeypatch):
        """`content_hash` öneksiz: aynı haber iki sağlayıcıdan gelirse iki
        satır değil bir satır olmalı."""
        row = {"content_hash": content_hash("t", "s"), "title": "t"}
        monkeypatch.setattr(news_api_source, "fetch_provider",
                            lambda name, client: [dict(row)])
        assert len(news_api_source.fetch_all(["finnhub", "marketaux"])) == 1

    def test_an_explicit_list_is_honoured(self, monkeypatch):
        asked = []
        monkeypatch.setattr(
            news_api_source, "fetch_provider",
            lambda name, client: asked.append(name) or [],
        )
        news_api_source.fetch_all(["marketaux"])
        assert asked == ["marketaux"]
