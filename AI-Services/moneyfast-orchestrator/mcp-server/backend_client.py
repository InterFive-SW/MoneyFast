# filename: backend_client.py
"""HTTP transport to the MoneyFast core backend.

Every domain tool talks to the backend through this module rather than
constructing its own ``httpx.AsyncClient``. Five copies of the same retry,
timeout and error-mapping logic drift within a sprint, and the drift always
shows up in the tool that matters most.

Responsibilities:

* One base URL, one timeout policy, one retry policy, read from the
  environment at call time so tests can monkeypatch without reimporting.
* A single error taxonomy. Callers upstream (the LangGraph orchestrator)
  branch on these classes, so the mapping from HTTP status to exception is
  part of the system contract, not an implementation detail.
* Contract guards. The v2.1 interface definitions promise exact payload
  shapes. A backend that omits a key must fail loudly here rather than let a
  half-formed dict reach the model, which would then narrate the gap as fact.

Deliberately NOT here: a mock or offline fallback mode. A tool that silently
returns canned data when the backend is unreachable is a catastrophic default
for ``validate_compliance_rules``, where the canned answer is PASS. Every
failure raises.

Environment:
    BACKEND_API_BASE_URL      default http://backend:8000/api
    RAG_API_BASE_URL          default http://rag:8100
    BACKEND_TIMEOUT_SECONDS   default 10.0
    BACKEND_CONNECT_TIMEOUT   default 5.0
    BACKEND_MAX_RETRIES       default 1 (retries, so 2 attempts total)
    BACKEND_API_KEY           optional bearer token for service-to-service auth
"""

# from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Mapping, Optional

import httpx

log = logging.getLogger("moneyfast.backend")

#: The backend serves its routers under /api/<module> and listens on 8000
#: inside the container. The host-side port mapping is irrelevant here; see
#: docs/DOCKER_NETWORKING.md.
DEFAULT_BASE_URL = "http://backend:8000/api"

#: Semantic search lives in the rag service, which owns the vector database
#: and the embedding model. It is a second base URL rather than a path under
#: the backend because there is no proxy in between: mcp calls rag directly.
DEFAULT_RAG_BASE_URL = "http://rag:8100"
DEFAULT_TIMEOUT = 10.0
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 1

#: Statuses worth a second attempt. 4xx other than these are deterministic:
#: retrying a 400 just doubles the latency before the same failure.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

#: Response bodies can contain holdings or draft text, so error messages carry
#: only a short prefix. Never log or raise the full body.
_BODY_EXCERPT_CHARS = 200


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------
class BackendError(RuntimeError):
    """Base class for every failure reaching a tool caller."""


class AuthorizationError(BackendError):
    """401 or 403. The session may not read or write this resource.

    Never retried and never degraded to cached data. The orchestrator tells
    the user the data is not accessible.
    """


class InvalidInputError(BackendError):
    """400, 404, 422 and other deterministic client errors.

    The request was malformed or referenced something that does not exist.
    Retrying cannot help.
    """


class UpstreamUnavailableError(BackendError):
    """Transport failure, timeout, or a 5xx that survived the retry budget.

    Means: no answer was obtained. Callers must surface this as a failure and
    MUST NOT substitute estimated, remembered or illustrative data.
    """


class ContractViolationError(BackendError):
    """The backend answered, but not in the shape v2.1 promises.

    Treated as a hard failure rather than patched over. A payload missing
    ``positions`` is not an empty portfolio, and guessing which one it is
    would put invented figures in front of a user.
    """


# ---------------------------------------------------------------------------
# Configuration, read at call time
# ---------------------------------------------------------------------------
def base_url() -> str:
    return os.getenv("BACKEND_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def rag_base_url() -> str:
    """Base URL of the rag service, for tools that retrieve rather than read
    application state."""
    return os.getenv("RAG_API_BASE_URL", DEFAULT_RAG_BASE_URL).rstrip("/")


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        log.warning("%s=%r is not a number, using %s", name, raw, default)
        return default
    return value if value > 0 else default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("%s=%r is not an integer, using %s", name, raw, default)
        return default
    return max(0, value)


def timeout() -> httpx.Timeout:
    """Separate connect and read budgets.

    A dead host should fail in five seconds; a slow risk computation is
    allowed the full ten.
    """
    return httpx.Timeout(
        _float_env("BACKEND_TIMEOUT_SECONDS", DEFAULT_TIMEOUT),
        connect=_float_env("BACKEND_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT),
    )


def max_retries() -> int:
    return _int_env("BACKEND_MAX_RETRIES", DEFAULT_MAX_RETRIES)


def _headers(extra: Optional[Mapping[str, str]] = None) -> dict:
    headers = {"Accept": "application/json", "User-Agent": "moneyfast-mcp/2.1"}
    token = os.getenv("BACKEND_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


#: Test seam. Set to an ``httpx.MockTransport`` to exercise the tools without
#: a backend. Left as None in every deployed configuration.
_transport: Optional[httpx.BaseTransport] = None


def set_transport(transport: Optional[httpx.BaseTransport]) -> None:
    """Install a transport double. For tests only."""
    global _transport
    _transport = transport


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------
def clean(payload: Mapping[str, Any]) -> dict:
    """Drop keys whose value is None.

    Omitting an argument and sending ``null`` mean different things to most
    backends, and the tool contracts treat None as "not specified".
    """
    return {key: value for key, value in payload.items() if value is not None}


def _excerpt(response: httpx.Response) -> str:
    try:
        text = response.text
    except Exception:  # pragma: no cover - defensive, body already consumed
        return ""
    return text[:_BODY_EXCERPT_CHARS].replace("\n", " ")


def _map_status(tool: str, response: httpx.Response) -> BackendError:
    status = response.status_code
    excerpt = _excerpt(response)
    if status in (401, 403):
        return AuthorizationError(
            f"{tool}: backend refused the request ({status}). "
            "Session lacks entitlement for this resource."
        )
    if status in RETRYABLE_STATUS:
        return UpstreamUnavailableError(f"{tool}: backend returned {status}. {excerpt}")
    return InvalidInputError(f"{tool}: backend rejected the request ({status}). {excerpt}")


async def request(
    method: str,
    path: str,
    *,
    tool: str,
    base: Optional[str] = None,
    params: Optional[Mapping[str, Any]] = None,
    json_body: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    allow_list: bool = False,
) -> Any:
    """Call the backend and return the decoded JSON object.

    Args:
        method: HTTP verb, e.g. "GET" or "POST".
        path: Path relative to the base URL, e.g. "/investment/positions".
        tool: Name of the calling tool, used in log lines and error messages.
        base: Override the base URL for this call. Used by the market research
            tool, which talks to the rag service rather than the backend.
            Everything else about the call - timeout, retry budget, error
            mapping - is identical, which is the point of routing it through
            here instead of hand-rolling a second client.
        params: Query string parameters. None values are dropped.
        json_body: Request body. None values are dropped.
        headers: Extra headers merged over the defaults.

    Returns:
        The response body as a dict.

    Raises:
        AuthorizationError: 401 or 403.
        InvalidInputError: other deterministic 4xx.
        UpstreamUnavailableError: transport failure, timeout, or 5xx after the
            retry budget is spent.
        ContractViolationError: body is not a JSON object.

    No other exception type escapes: an unexpected error is wrapped as
    UpstreamUnavailableError so a tool call can never crash the MCP server.
    """
    url = f"{(base.rstrip('/') if base else base_url())}{path}"
    attempts = max_retries() + 1
    last: Optional[BackendError] = None

    for attempt in range(1, attempts + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout(), transport=_transport, follow_redirects=False
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params=clean(params) if params else None,
                    json=clean(json_body) if json_body else None,
                    headers=_headers(headers),
                )

            if response.status_code >= 400:
                error = _map_status(tool, response)
                if isinstance(error, UpstreamUnavailableError) and attempt < attempts:
                    last = error
                    await _backoff(tool, attempt, response.status_code)
                    continue
                raise error

            try:
                payload = response.json()
            except ValueError as exc:
                raise UpstreamUnavailableError(
                    f"{tool}: backend returned a non-JSON body. {_excerpt(response)}"
                ) from exc

            # Bir dizi varsayılan olarak sözleşme ihlali. Sebep: uçların
            # ezici çoğunluğu nesne döndürüyor ve bir gün liste döndürmeye
            # başlayan bir uç, `payload["..."]` yazan aracın elinde
            # anlaşılmaz bir `TypeError`a dönüşürdü.
            #
            # `allow_list` bunu ÇAĞRI BAŞINA gevşetiyor, genel olarak değil:
            # `/market/search` gerçekten bir dizi döndürüyor ve onu nesneye
            # sarmak arayüzü bozardı -- aynı ucu `InstrumentSuggestion[]`
            # olarak okuyan bir açılır liste var.
            if not isinstance(payload, list if allow_list else dict):
                expected = "a JSON array" if allow_list else "a JSON object"
                raise ContractViolationError(
                    f"{tool}: expected {expected}, got {type(payload).__name__}."
                )
            return payload

        except (httpx.TimeoutException, httpx.TransportError, httpx.RequestError) as exc:
            last = UpstreamUnavailableError(f"{tool}: {url} unreachable: {exc}")
            if attempt < attempts:
                await _backoff(tool, attempt, exc.__class__.__name__)
                continue
            raise last from exc
        except BackendError:
            raise
        except Exception as exc:  # never let an unexpected error escape a tool
            log.exception("%s: unexpected failure calling %s", tool, url)
            raise UpstreamUnavailableError(f"{tool}: unexpected failure: {exc}") from exc

    # Unreachable in practice; retries either return, continue or raise.
    raise last or UpstreamUnavailableError(f"{tool}: {url} unreachable.")


async def _backoff(tool: str, attempt: int, reason: Any) -> None:
    delay = 0.5 * (2 ** (attempt - 1))
    log.warning("%s: attempt %d failed (%s), retrying in %.1fs", tool, attempt, reason, delay)
    await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Contract guards
# ---------------------------------------------------------------------------
def require(payload: dict, keys: tuple, tool: str) -> None:
    """Assert that every load-bearing key is present.

    Present-and-empty is fine and meaningful: ``positions: []`` is a valid,
    complete answer. Absent is not, and must never be silently defaulted to an
    empty list, because the two say different things to the user.
    """
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ContractViolationError(
            f"{tool}: backend response is missing required field(s): {', '.join(missing)}."
        )


def require_list(payload: dict, key: str, tool: str) -> list:
    require(payload, (key,), tool)
    value = payload[key]
    if not isinstance(value, list):
        raise ContractViolationError(
            f"{tool}: '{key}' must be a list, got {type(value).__name__}."
        )
    return value


def freshness(payload: dict, tool: str) -> dict:
    """Extract and validate the three market-data fields.

    v2.1 requires as_of, source and is_delayed on every data-fetching tool.
    They are what every user-facing figure is attributed to, so a missing one
    is a contract violation rather than something to default.
    """
    require(payload, ("as_of", "source", "is_delayed"), tool)
    is_delayed = bool(payload["is_delayed"])
    return {
        "as_of": str(payload["as_of"]),
        "source": str(payload["source"]),
        "is_delayed": is_delayed,
    }
