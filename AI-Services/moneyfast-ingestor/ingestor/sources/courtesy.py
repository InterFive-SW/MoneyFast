"""Courtesies observed before fetching anything from someone else's server.

Extracted from `rss_source` when KAP became a second source. The alternative
was a second robots.txt cache and a second per-host timer, which would mean two
sources could each independently decide they had waited long enough — the delay
is per HOST, and a host does not care which module is calling it.

Three courtesies, all of them cheap:

* `robots.txt` is checked before the first fetch of a host and honoured.
* Requests to one host are spaced by a minimum delay.
* Conditional requests (`If-None-Match` / `If-Modified-Since`) mean an
  unchanged resource costs the publisher a 304 rather than a full response.

The `User-Agent` names the project and links to it. If an operator wants us
gone, they can see who we are and say so.
"""

from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .. import config

log = logging.getLogger("moneyfast.ingestor.courtesy")

#: Last fetch time per host, for the courtesy delay.
_last_request: dict[str, float] = {}

#: ETag / Last-Modified per resource URL, for conditional requests.
validators: dict[str, dict[str, str]] = {}

#: robots.txt verdicts, per host. Cached for the process lifetime: re-fetching
#: it for every poll would itself be impolite.
_robots: dict[str, Optional[RobotFileParser]] = {}


def reset_state() -> None:
    """Clear the caches. For tests."""
    _last_request.clear()
    validators.clear()
    _robots.clear()


def may_fetch(url: str, client: httpx.Client) -> bool:
    if not config.respect_robots():
        return True

    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host not in _robots:
        parser = RobotFileParser()
        try:
            response = client.get(f"{host}/robots.txt", timeout=config.request_timeout())
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                # No robots.txt is permission by convention, not an error.
                parser = None
        except Exception as exc:
            log.warning("could not read robots.txt for %s: %s", host, exc)
            parser = None
        _robots[host] = parser

    parser = _robots[host]
    if parser is None:
        return True
    allowed = parser.can_fetch(config.user_agent(), url)
    if not allowed:
        log.warning("robots.txt disallows %s, skipping", url)
    return allowed


def wait_for_host(url: str, minimum: float = 0.0) -> None:
    """Space requests to one host.

    `minimum` raises the floor for a host that has ASKED for more room. GDELT
    says so in its own 429 body -- "Please limit requests to one every 5
    seconds" -- and the project-wide default is 2. Taking the larger of the
    two means a stated request always wins, and lowering the global default
    can never quietly start violating it.
    """
    host = urlparse(url).netloc
    delay = max(config.per_host_delay(), minimum)
    previous = _last_request.get(host)
    if previous is not None:
        elapsed = time.monotonic() - previous
        if elapsed < delay:
            time.sleep(delay - elapsed)
    _last_request[host] = time.monotonic()
