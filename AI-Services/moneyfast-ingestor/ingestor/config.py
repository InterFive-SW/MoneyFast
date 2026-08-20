"""Configuration, read from the environment at call time.

Read at call time rather than import time so tests can monkeypatch without
reimporting the module, matching the pattern in the MCP server's
`backend_client`.
"""

import os
from typing import Optional

DEFAULT_BACKEND_URL = "http://backend:8000/api"
DEFAULT_RAG_URL = "http://rag:8100"

#: Turkish financial outlets that publish RSS. RSS exists to be read by
#: machines, so nothing here needs to look like a browser or work around a
#: bot check — see the README for why that matters.
DEFAULT_FEEDS = ",".join(
    [
        "https://www.dunya.com/rss?dunya",
        "https://www.ekonomim.com/rss",
        "https://www.aa.com.tr/tr/rss/default?cat=ekonomi",
        # Bigpara planlanmıştı ama RSS uç noktası yok — denenen her yol 404
        # döndü; site JS ile render ediliyor ve okunabilmesi için tarayıcı
        # taklidi gerekirdi. BloombergHT aynı boşluğu dolduruyor: robots.txt
        # yalnızca "User-agent: *" içeriyor, hiçbir kısıt tanımlamıyor.
        "https://www.bloomberght.com/rss",
    ]
)

#: Borsa İstanbul continuous session, Europe/Istanbul.
MARKET_OPEN_HOUR = 10
MARKET_CLOSE_HOUR = 18


def backend_url() -> str:
    return os.getenv("BACKEND_API_BASE_URL", DEFAULT_BACKEND_URL).rstrip("/")


def rag_url() -> str:
    return os.getenv("RAG_API_BASE_URL", DEFAULT_RAG_URL).rstrip("/")


def service_token() -> Optional[str]:
    return os.getenv("BACKEND_API_KEY") or None


def feeds() -> list[str]:
    # `or`, not a getenv default: Compose renders `${NEWS_FEEDS:-}` as an
    # empty string, which IS set as far as getenv is concerned and would
    # silently disable news collection entirely.
    raw = os.getenv("NEWS_FEEDS") or DEFAULT_FEEDS
    return [url.strip() for url in raw.split(",") if url.strip()]


def user_agent() -> str:
    """Identifies the crawler honestly, with a contact route.

    An operator who wants to rate-limit or block us should be able to see who
    we are and get in touch. Disguising the client as a browser is the first
    step of the evasion approach this project deliberately does not take.
    """
    return os.getenv("INGESTOR_USER_AGENT") or (
        "MoneyFastBot/1.0 (+https://github.com/InterFive-SW/moneyfast; internship project)"
    )


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def request_timeout() -> float:
    return _float("INGESTOR_TIMEOUT_SECONDS", 20.0)


def per_host_delay() -> float:
    """Minimum gap between two requests to the same host."""
    return _float("INGESTOR_HOST_DELAY_SECONDS", 2.0)


def quote_interval_seconds() -> int:
    """How often to refresh prices.

    Ten seconds is achievable because the whole universe is fetched in ONE
    batched request (measured 3.3-5.4s for ~95 symbols). The floor of 5s is a
    guard against a config typo turning this into a request flood.
    """
    return max(5, _int("INGESTOR_QUOTE_INTERVAL_SECONDS", 10))


def news_interval_minutes() -> int:
    return _int("INGESTOR_NEWS_INTERVAL_MINUTES", 15)


def history_days() -> int:
    """How much daily history to request on the nightly candle job."""
    return _int("INGESTOR_HISTORY_DAYS", 400)


def respect_robots() -> bool:
    """Deliberately not a documented off switch.

    It exists so a test can bypass a network call, not so an operator can
    disable the check. Anything reachable only by ignoring robots.txt is out
    of scope for this project.
    """
    return os.getenv("INGESTOR_RESPECT_ROBOTS", "true").lower() != "false"


#: Successive interval multipliers applied after a rate-limit response. This
#: is what "without getting stopped" actually looks like: backing off when
#: asked, rather than pretending to be a browser.
BACKOFF_LADDER = (1, 3, 6)
