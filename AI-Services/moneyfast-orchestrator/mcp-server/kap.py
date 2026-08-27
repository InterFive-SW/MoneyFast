"""Strict KAP provenance URL validation for MCP-side citation safety.

Mirrors ``backend.app.modules.market.kap.validated_kap_url``. Packages cannot
import across containers, so the rule is duplicated here rather than reaching
into the backend or making a network request. No KAP page is fetched.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

ALLOWED_KAP_HOSTS = frozenset({"kap.org.tr", "www.kap.org.tr"})


def validated_kap_url(raw: str | None) -> tuple[str, str] | None:
    """Return a fragment-free trusted KAP URL and host, or ``None``.

    Rejects HTTP downgrade, userinfo, non-443 ports, look-alike hosts, and
    anything that is not an exact allowed hostname.
    """

    if not raw or raw.startswith("//"):
        return None
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or hostname.lower() not in ALLOWED_KAP_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return None
    host = hostname.lower()
    netloc = host if port is None else f"{host}:{port}"
    clean = urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))
    return clean, host
