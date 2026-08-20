"""RSS collection.

The behaviours worth pinning are the courtesies, not the parsing. A crawler
that ignores robots.txt, hammers one host, or re-downloads an unchanged feed
every fifteen minutes is the reason publishers put up bot walls in the first
place.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from ingestor import config
from ingestor.sources import rss_source
from conftest import FEED_XML

FEED_URL = "https://news.example/rss"


#: Captured before any test monkeypatches httpx.Client, so building a stub
#: client inside a patched context does not recurse into itself.
_RealClient = httpx.Client


def client_for(handler) -> httpx.Client:
    return _RealClient(transport=httpx.MockTransport(handler))


def feed_handler(body=FEED_XML, status=200, headers=None, robots="User-agent: *\nAllow: /"):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(status, text=body, headers=headers or {})

    handler.calls = calls
    return handler


class TestParsing:
    def test_entries_become_news_items(self, no_robots):
        handler = feed_handler()
        items = rss_source.fetch_feed(FEED_URL, client_for(handler))
        assert len(items) == 2
        assert items[0]["title"] == "THYAO kargo gelirlerini açıkladı"
        assert items[0]["source"] == "Test Ekonomi"
        assert items[0]["url"] == "https://example.com/haber/1"

    def test_published_at_comes_from_the_feed(self, no_robots):
        items = rss_source.fetch_feed(FEED_URL, client_for(feed_handler()))
        assert items[0]["published_at"] == datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)

    def test_only_feed_supplied_tickers_are_tagged(self, no_robots):
        """Inferring a ticker from headline text would put one company's news
        on another company's page, and the retrieval contract lets the model
        filter on these tags."""
        items = rss_source.fetch_feed(FEED_URL, client_for(feed_handler()))
        assert items[0]["related_symbols"] == ["THYAO"]
        # The second article names the central bank but tags nothing.
        assert items[1]["related_symbols"] == []

    def test_untitled_entries_are_skipped(self, no_robots):
        xml = FEED_XML.replace("<title>THYAO kargo gelirlerini açıkladı</title>", "<title></title>")
        items = rss_source.fetch_feed(FEED_URL, client_for(feed_handler(body=xml)))
        assert len(items) == 1

    def test_undated_entry_falls_back_to_now(self, no_robots):
        xml = FEED_XML.replace("<pubDate>Wed, 20 Aug 2026 08:00:00 GMT</pubDate>", "")
        items = rss_source.fetch_feed(FEED_URL, client_for(feed_handler(body=xml)))
        assert items[0]["published_at"].tzinfo is not None


class TestDeduplication:
    def test_hash_is_over_the_text_not_the_url(self):
        """The same wire story is republished under different links, and some
        feeds renumber URLs on every rebuild."""
        first = rss_source.content_hash("Başlık", "Özet")
        second = rss_source.content_hash("Başlık", "Özet")
        assert first == second
        assert len(first) == 64

    def test_different_text_yields_a_different_hash(self):
        assert rss_source.content_hash("A", "x") != rss_source.content_hash("B", "x")

    def test_syndicated_duplicates_are_collapsed_across_feeds(self, no_robots, monkeypatch):
        handler = feed_handler()
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_for(handler))
        items = rss_source.fetch_all(["https://a.example/rss", "https://b.example/rss"])
        # Two feeds, identical content: four entries in, two out.
        assert len(items) == 2


class TestRobots:
    def test_disallowed_path_is_not_fetched(self):
        handler = feed_handler(robots="User-agent: *\nDisallow: /")
        assert rss_source.fetch_feed(FEED_URL, client_for(handler)) == []
        # robots.txt was read; the feed itself was not.
        assert all(call.url.path == "/robots.txt" for call in handler.calls)

    def test_allowed_path_is_fetched(self):
        handler = feed_handler(robots="User-agent: *\nDisallow: /private")
        assert len(rss_source.fetch_feed(FEED_URL, client_for(handler))) == 2

    def test_missing_robots_txt_is_treated_as_permission(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text=FEED_XML)

        assert len(rss_source.fetch_feed(FEED_URL, client_for(handler))) == 2

    def test_unreachable_robots_txt_does_not_block_the_feed(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                raise httpx.ConnectError("dns")
            return httpx.Response(200, text=FEED_XML)

        assert len(rss_source.fetch_feed(FEED_URL, client_for(handler))) == 2

    def test_robots_is_read_once_per_host(self):
        handler = feed_handler()
        client = client_for(handler)
        rss_source.fetch_feed(FEED_URL, client)
        rss_source.fetch_feed(FEED_URL, client)
        robots_calls = [c for c in handler.calls if c.url.path == "/robots.txt"]
        assert len(robots_calls) == 1, "re-reading robots.txt every poll is itself impolite"


class TestConditionalRequests:
    def test_etag_is_echoed_on_the_next_poll(self, no_robots):
        handler = feed_handler(headers={"ETag": '"abc123"'})
        client = client_for(handler)
        rss_source.fetch_feed(FEED_URL, client)
        rss_source.fetch_feed(FEED_URL, client)
        assert handler.calls[-1].headers.get("If-None-Match") == '"abc123"'

    def test_last_modified_is_echoed(self, no_robots):
        stamp = "Wed, 20 Aug 2026 08:00:00 GMT"
        handler = feed_handler(headers={"Last-Modified": stamp})
        client = client_for(handler)
        rss_source.fetch_feed(FEED_URL, client)
        rss_source.fetch_feed(FEED_URL, client)
        assert handler.calls[-1].headers.get("If-Modified-Since") == stamp

    def test_304_yields_nothing_without_an_error(self, no_robots):
        """An unchanged feed should cost the publisher a 304, not a full
        response, and cost us no reprocessing."""
        assert rss_source.fetch_feed(FEED_URL, client_for(feed_handler(status=304, body=""))) == []


class TestFailureHandling:
    def test_rate_limit_backs_off_quietly(self, no_robots):
        assert rss_source.fetch_feed(FEED_URL, client_for(feed_handler(status=429, body=""))) == []

    def test_server_error_yields_nothing(self, no_robots):
        assert rss_source.fetch_feed(FEED_URL, client_for(feed_handler(status=500, body=""))) == []

    def test_unreachable_host_yields_nothing(self, no_robots):
        def handler(request):
            raise httpx.ConnectError("no route to host")

        assert rss_source.fetch_feed(FEED_URL, client_for(handler)) == []

    def test_one_dead_feed_does_not_stop_the_others(self, no_robots, monkeypatch):
        """A publisher outage must not blank the whole news surface."""
        def handler(request):
            if "dead" in str(request.url):
                raise httpx.ConnectError("down")
            return httpx.Response(200, text=FEED_XML)

        monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_for(handler))
        items = rss_source.fetch_all(["https://dead.example/rss", "https://ok.example/rss"])
        assert len(items) == 2


class TestRateLimiting:
    def test_requests_to_one_host_are_spaced(self, no_robots, monkeypatch):
        slept = []
        monkeypatch.setattr(rss_source.time, "sleep", lambda seconds: slept.append(seconds))
        client = client_for(feed_handler())
        rss_source.fetch_feed(FEED_URL, client)
        rss_source.fetch_feed(FEED_URL, client)
        assert slept, "the second request to a host must wait out the courtesy delay"

    def test_first_request_to_a_host_does_not_wait(self, no_robots, monkeypatch):
        slept = []
        monkeypatch.setattr(rss_source.time, "sleep", lambda seconds: slept.append(seconds))
        rss_source.fetch_feed(FEED_URL, client_for(feed_handler()))
        assert slept == []

    def test_user_agent_is_sent(self, no_robots):
        handler = feed_handler()
        rss_source.fetch_feed(FEED_URL, client_for(handler))
        assert "MoneyFastBot" in handler.calls[-1].headers["User-Agent"]
