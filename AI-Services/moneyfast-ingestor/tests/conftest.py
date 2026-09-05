"""Shared fixtures for the ingestor suite.

Real sockets are blocked. This service exists to make outbound requests, so a
test that forgets a stub would otherwise quietly hit a live news site or the
Yahoo API — slow, flaky, and rude to the operators. Same fixture idea as the
MCP server's suite.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestor import config  # noqa: E402
from ingestor.sources import courtesy, rss_source  # noqa: E402


class NetworkAccessAttempted(RuntimeError):
    """A test tried to open a real socket."""


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise NetworkAccessAttempted(
            "The ingestor suite must stub HTTP. Use httpx.MockTransport."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "BACKEND_API_BASE_URL", "RAG_API_BASE_URL", "BACKEND_API_KEY", "NEWS_FEEDS",
        "INGESTOR_USER_AGENT", "INGESTOR_TIMEOUT_SECONDS", "INGESTOR_HOST_DELAY_SECONDS",
        "INGESTOR_QUOTE_INTERVAL_MINUTES", "INGESTOR_NEWS_INTERVAL_MINUTES",
        "INGESTOR_HISTORY_DAYS", "INGESTOR_RESPECT_ROBOTS",
        "INGESTOR_GDELT_BASE_URL", "INGESTOR_GDELT_QUERIES",
        "INGESTOR_GDELT_TIMESPAN_DAYS", "INGESTOR_GDELT_MAX_RECORDS",
        "INGESTOR_GDELT_INTERVAL_MINUTES",
        # Anahtarlı sağlayıcılar. Silinmezse geliştiricinin GERÇEK anahtarı
        # test koşusuna sızar ve suite dış dünyaya istek atmayı dener.
        "FINNHUB_API_KEY", "MARKETAUX_API_KEY",
        "INGESTOR_TEFAS_BASE_URL", "INGESTOR_TEFAS_ENABLED",
        "INGESTOR_TEFAS_PROFILE_BUDGET", "INGESTOR_TEFAS_PRICE_BUDGET",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def fresh_rss_state(monkeypatch):
    """Per-test isolation for the robots/ETag/rate-limit caches, and no real
    sleeping for the courtesy delay."""
    rss_source.reset_state()
    monkeypatch.setattr(courtesy.time, "sleep", lambda _seconds: None)
    yield
    rss_source.reset_state()


@pytest.fixture
def no_robots(monkeypatch):
    """Skip the robots.txt round trip for tests about something else."""
    monkeypatch.setenv("INGESTOR_RESPECT_ROBOTS", "false")


FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Test Ekonomi</title>
  <item>
    <title>THYAO kargo gelirlerini açıkladı</title>
    <description>Havayolu şirketi kargo segmentinde büyüme bildirdi.</description>
    <link>https://example.com/haber/1</link>
    <pubDate>Wed, 20 Aug 2026 08:00:00 GMT</pubDate>
    <category>THYAO</category>
  </item>
  <item>
    <title>Merkez Bankası faiz kararını açıkladı</title>
    <description>Politika faizi sabit tutuldu.</description>
    <link>https://example.com/haber/2</link>
    <pubDate>Wed, 20 Aug 2026 07:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""
