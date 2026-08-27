"""Configuration, read from the environment at call time.

Read at call time rather than import time so tests can monkeypatch without
reimporting the module, matching the pattern in the MCP server's
`backend_client`.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

DEFAULT_BACKEND_URL = "http://backend:8000/api"
DEFAULT_RAG_URL = "http://rag:8100"

#: Turkish financial outlets that publish RSS. RSS exists to be read by
#: machines, so nothing here needs to look like a browser or work around a
#: bot check — see the README for why that matters.
DEFAULT_FEEDS = ",".join(
    [
        # Finance-only feeds. Every entry here was probed for status, item
        # count, publication date and URL section before being added.
        #
        # patronlardunyasi publishes four separate finance sections that are
        # genuinely distinct (unlike dunya.com, whose ?finans / ?borsa query
        # strings are ignored and return the homepage feed). `sirketler` is the
        # one that carries company-level news -- without it, "Akbank ile ilgili
        # haberler" had nothing to match, because the general economy feeds
        # only cover macro stories.
        "https://www.patronlardunyasi.com/rss/borsa",
        "https://www.patronlardunyasi.com/rss/finans",
        "https://www.patronlardunyasi.com/rss/sirketler",
        "https://www.patronlardunyasi.com/rss/ekonomi",
        # Anadolu Ajansı's economy category: every item is filed under
        # /tr/ekonomi/, so it needs no filtering.
        "https://www.aa.com.tr/tr/rss/default?cat=ekonomi",
        # Kept, but they are site-wide feeds -- the section filter in
        # rss_source.is_financial is what keeps football and exam results out.
        "https://www.dunya.com/rss?dunya",
        "https://www.ekonomim.com/rss",
        # BloombergHT was dropped: the content is financial but the feed is
        # frozen -- its newest item was two weeks old when checked. A stale
        # feed sitting beside live prices is worse than one fewer source.
    ]
)

#: Borsa İstanbul continuous session, Europe/Istanbul.
MARKET_OPEN_HOUR = 10
MARKET_CLOSE_HOUR = 18

#: Trading hours per market, as [open, close) in Europe/Istanbul, weekdays.
#:
#: One global BIST-hours gate used to decide the whole cycle. That was fine
#: while every instrument was Turkish; with US equities in the universe it
#: means their prices stop refreshing at 18:00 TRT, which is half an hour
#: BEFORE the US session even opens.
#:
#: FX and gold trade nearly around the clock; they are given the full weekday
#: rather than pretending they follow an exchange session.
MARKET_HOURS: dict[str, tuple[int, int]] = {
    "BIST": (MARKET_OPEN_HOUR, MARKET_CLOSE_HOUR),
    # 09:30-16:00 America/New_York is 16:30-23:00 TRT. Whole hours only, so
    # the window opens at 16:00 -- half an hour of pre-open quotes costs one
    # request per cycle and avoids modelling US daylight saving separately.
    "NASDAQ": (16, 23),
    "NYSE": (16, 23),
    "FX": (0, 24),
    "COMEX": (0, 24),
}


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
    # 30s, not 10s. Measured with ~190 symbols across two markets: a clean
    # cycle is a handful of seconds, but a chunk that has to time out pushes
    # it past ten, and every overrun was logged as a skipped run. A budget the
    # cycle can actually meet is worth more than a number that looks live.
    return max(5, _int("INGESTOR_QUOTE_INTERVAL_SECONDS", 30))


def news_interval_minutes() -> int:
    return _int("INGESTOR_NEWS_INTERVAL_MINUTES", 15)


def history_days() -> int:
    """How much daily history to request on the nightly candle job."""
    return _int("INGESTOR_HISTORY_DAYS", 400)


#: Below this many daily bars, the start-up backfill treats an instrument as
#: needing history. Well under `history_days()` on purpose: the point is to
#: separate "has a usable series" from "has nothing", not to keep every symbol
#: topped up to the same bar count. Holidays, listing dates and provider gaps
#: all make a full 400 unreachable for some names, and a threshold near it
#: would re-fetch those every single start.
CANDLE_MIN_BARS = _int("INGESTOR_CANDLE_MIN_BARS", 60)


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


class XConfigurationError(ValueError):
    """Non-secret X configuration is invalid."""


X_SOURCE_TYPES = frozenset(
    {
        "official_company",
        "official_disclosure",
        "disclosure_aggregator",
        "news_agency",
        "financial_media",
        "analyst",
    }
)
_X_HANDLE = re.compile(r"^[a-z0-9_]{1,15}$")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def x_ingest_enabled() -> bool:
    return _bool("X_INGEST_ENABLED")


def x_bearer_token() -> Optional[str]:
    """Load the ingestor-only credential without logging or returning its path."""

    path = os.getenv("X_BEARER_TOKEN_FILE", "").strip()
    if path:
        try:
            token = Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise XConfigurationError("configured X token file is unreadable") from exc
        if not token:
            raise XConfigurationError("configured X token file is empty")
        return token
    return os.getenv("X_BEARER_TOKEN", "").strip() or None


def x_monitored_accounts() -> list[dict]:
    raw = os.getenv("X_MONITORED_ACCOUNTS_JSON", "").strip()
    if not raw:
        raise XConfigurationError("X monitored account allowlist is empty")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise XConfigurationError(
            "X monitored account allowlist is not valid JSON"
        ) from exc
    if not isinstance(value, list) or not value:
        raise XConfigurationError(
            "X monitored account allowlist must be a non-empty array"
        )
    if len(value) > 100:
        raise XConfigurationError(
            "X monitored account allowlist may contain at most 100 entries"
        )

    accounts: list[dict] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise XConfigurationError("each X account entry must be an object")
        handle = str(entry.get("handle") or "").strip().removeprefix("@").lower()
        source_type = str(entry.get("source_type") or "")
        try:
            trust_score = float(entry["trust_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise XConfigurationError(
                "each X account needs a numeric trust_score"
            ) from exc
        if not _X_HANDLE.fullmatch(handle):
            raise XConfigurationError("X account handle is invalid")
        if handle in seen:
            raise XConfigurationError("X account handles must be unique")
        if source_type not in X_SOURCE_TYPES:
            raise XConfigurationError("X account source_type is unsupported")
        if not 0.0 <= trust_score <= 1.0:
            raise XConfigurationError("X account trust_score must be between 0 and 1")
        seen.add(handle)
        accounts.append(
            {
                "handle": handle,
                "source_type": source_type,
                "trust_score": trust_score,
                "is_active": bool(entry.get("is_active", True)),
            }
        )
    return accounts


def x_include_replies() -> bool:
    return _bool("X_INCLUDE_REPLIES")


def x_include_reposts() -> bool:
    return _bool("X_INCLUDE_REPOSTS")


def x_poll_interval_minutes() -> int:
    return max(5, _int("X_POLL_INTERVAL_MINUTES", 10))


def x_max_pages_per_account() -> int:
    return max(1, min(10, _int("X_MAX_PAGES_PER_ACCOUNT", 3)))


def x_backend_batch_size() -> int:
    """Posts per atomic backend request; bounded by the backend contract."""

    return max(1, min(1_000, _int("X_BACKEND_BATCH_SIZE", 500)))


def x_identity_refresh_hours() -> int:
    """How often cached account names are refreshed by stable X user ID."""

    return max(1, min(168, _int("X_IDENTITY_REFRESH_HOURS", 24)))


def x_state_file() -> str:
    return os.getenv("X_STATE_FILE", "/app/state/x-cursors.json").strip() or (
        "/app/state/x-cursors.json"
    )


def x_max_retries() -> int:
    return max(0, min(3, _int("X_MAX_RETRIES", 1)))
