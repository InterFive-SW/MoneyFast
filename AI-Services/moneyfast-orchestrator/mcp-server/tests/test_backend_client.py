"""Unit tests for backend_client.

Every tool call in the server passes through this module, so its retry policy
and its status-to-exception mapping are system behaviour rather than plumbing.
The orchestrator branches on the exception class: AuthorizationError means
"tell the user it is not accessible", UpstreamUnavailableError means "no
answer was obtained", ContractViolationError means "the answer was unusable".
Collapsing any two of those changes what a user sees.

No socket is opened: httpx.MockTransport serves every request, and the backoff
is recorded rather than slept through.
"""

from __future__ import annotations

import httpx
import pytest

import backend_client
from backend_client import (
    AuthorizationError,
    BackendError,
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)

TOOL = "test_tool"


async def call(**kwargs):
    """Issue a request through the module under test."""
    kwargs.setdefault("tool", TOOL)
    return await backend_client.request("GET", "/portfolio/u_1", **kwargs)


# ==========================================================================
# Configuration
# ==========================================================================
class TestConfiguration:
    def test_base_url_defaults_to_the_container_service_name(self):
        """Inside Docker, localhost is this container. The default must be the
        compose service name or the tools silently talk to themselves."""
        assert backend_client.base_url() == "http://backend:3000/api/v1"

    def test_base_url_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_BASE_URL", "http://other:9000/api/v2")
        assert backend_client.base_url() == "http://other:9000/api/v2"

    def test_base_url_trailing_slash_is_stripped(self, monkeypatch):
        """Otherwise every URL gains a double slash, which some gateways 404."""
        monkeypatch.setenv("BACKEND_API_BASE_URL", "http://other:9000/api/v2/")
        assert backend_client.base_url() == "http://other:9000/api/v2"

    def test_timeout_defaults(self):
        timeout = backend_client.timeout()
        assert timeout.read == 10.0
        assert timeout.connect == 5.0

    def test_timeout_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("BACKEND_TIMEOUT_SECONDS", "2.5")
        monkeypatch.setenv("BACKEND_CONNECT_TIMEOUT", "1.5")
        timeout = backend_client.timeout()
        assert timeout.read == 2.5
        assert timeout.connect == 1.5

    def test_malformed_timeout_falls_back_and_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("BACKEND_TIMEOUT_SECONDS", "ten seconds")
        with caplog.at_level("WARNING", logger="moneyfast.backend"):
            assert backend_client.timeout().read == 10.0
        assert any("is not a number" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize("value", ["0", "-5"])
    def test_non_positive_timeout_falls_back(self, monkeypatch, value):
        """A zero or negative timeout would mean no timeout at all in some
        stacks, which is the opposite of a strict policy."""
        monkeypatch.setenv("BACKEND_TIMEOUT_SECONDS", value)
        assert backend_client.timeout().read == 10.0

    def test_max_retries_default(self):
        assert backend_client.max_retries() == 1

    def test_max_retries_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "3")
        assert backend_client.max_retries() == 3

    def test_malformed_max_retries_falls_back_and_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "lots")
        with caplog.at_level("WARNING", logger="moneyfast.backend"):
            assert backend_client.max_retries() == 1
        assert any("is not an integer" in r.getMessage() for r in caplog.records)

    def test_negative_max_retries_clamps_to_zero(self, monkeypatch):
        """max(0, n). A negative budget must mean "no retries", not a skipped
        request loop."""
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "-4")
        assert backend_client.max_retries() == 0


class TestHeaders:
    @pytest.mark.asyncio
    async def test_default_headers_identify_the_client(self, fake_backend):
        await call()
        assert fake_backend.last.headers["accept"] == "application/json"
        assert fake_backend.last.headers["user-agent"] == "moneyfast-mcp/2.1"

    @pytest.mark.asyncio
    async def test_no_authorization_header_without_a_token(self, fake_backend):
        await call()
        assert "authorization" not in fake_backend.last.headers

    @pytest.mark.asyncio
    async def test_bearer_token_attached_when_configured(self, fake_backend, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "svc-secret")
        await call()
        assert fake_backend.last.headers["authorization"] == "Bearer svc-secret"

    @pytest.mark.asyncio
    async def test_extra_headers_are_merged(self, fake_backend):
        await call(headers={"Idempotency-Key": "idem_1"})
        assert fake_backend.last.headers["idempotency-key"] == "idem_1"
        assert fake_backend.last.headers["accept"] == "application/json"


class TestClean:
    def test_drops_none_values(self):
        """Omitting an argument and sending null mean different things, and
        the contracts treat None as "not specified"."""
        assert backend_client.clean({"a": 1, "b": None, "c": False}) == {"a": 1, "c": False}

    def test_keeps_falsy_non_none_values(self):
        """0, "" and False are values, not absences."""
        assert backend_client.clean({"a": 0, "b": "", "c": []}) == {"a": 0, "b": "", "c": []}

    def test_empty_mapping(self):
        assert backend_client.clean({}) == {}


# ==========================================================================
# Happy path
# ==========================================================================
class TestSuccessfulRequests:
    @pytest.mark.asyncio
    async def test_returns_the_decoded_json_object(self, fake_backend):
        fake_backend.json("portfolio", {"ok": True})
        assert await call() == {"ok": True}

    @pytest.mark.asyncio
    async def test_url_is_base_plus_path(self, fake_backend, monkeypatch):
        monkeypatch.setenv("BACKEND_API_BASE_URL", "http://backend:3000/api/v1")
        await call()
        assert str(fake_backend.last.url).startswith("http://backend:3000/api/v1/portfolio/u_1")

    @pytest.mark.asyncio
    async def test_query_parameters_are_sent_and_none_dropped(self, fake_backend):
        await call(params={"a": "1", "b": None, "flag": True})
        query = str(fake_backend.last.url)
        assert "a=1" in query
        assert "b=" not in query
        assert "flag=true" in query

    @pytest.mark.asyncio
    async def test_list_parameters_become_repeated_keys(self, fake_backend):
        await call(params={"account_ids": ["acc_1", "acc_2"]})
        query = str(fake_backend.last.url)
        assert "account_ids=acc_1" in query and "account_ids=acc_2" in query

    @pytest.mark.asyncio
    async def test_json_body_is_sent_and_none_dropped(self, fake_backend):
        await backend_client.request(
            "POST", "/compliance/validate", tool=TOOL,
            json_body={"draft_response": "d", "tools_used": None},
        )
        body = fake_backend.body()
        assert body == {"draft_response": "d"}

    @pytest.mark.asyncio
    async def test_empty_params_and_body_are_omitted(self, fake_backend):
        await call(params={}, json_body={})
        assert fake_backend.last.url.query == b""
        assert fake_backend.last.content in (b"", None)

    @pytest.mark.asyncio
    async def test_single_attempt_on_success(self, fake_backend):
        await call()
        assert fake_backend.attempts == 1


# ==========================================================================
# Status mapping
# ==========================================================================
class TestStatusMapping:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 403])
    async def test_auth_statuses_raise_authorization_error(self, fake_backend, status):
        fake_backend.status("portfolio", status)
        with pytest.raises(AuthorizationError):
            await call()

    @pytest.mark.asyncio
    async def test_authorization_error_is_not_retried(self, fake_backend, monkeypatch):
        """Retrying a refusal cannot change the answer and doubles the latency
        before the user is told."""
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "3")
        fake_backend.status("portfolio", 403)
        with pytest.raises(AuthorizationError):
            await call()
        assert fake_backend.attempts == 1

    @pytest.mark.asyncio
    async def test_authorization_error_does_not_echo_the_body(self, fake_backend):
        """Bodies can carry holdings or draft text; the message must not."""
        fake_backend.status("portfolio", 401, {"detail": "user u_secret has no entitlement"})
        with pytest.raises(AuthorizationError) as info:
            await call()
        assert "u_secret" not in str(info.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 404, 409, 422])
    async def test_deterministic_client_errors_raise_invalid_input(self, fake_backend, status):
        fake_backend.status("portfolio", status)
        with pytest.raises(InvalidInputError):
            await call()

    @pytest.mark.asyncio
    async def test_invalid_input_is_not_retried(self, fake_backend, monkeypatch):
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "3")
        fake_backend.status("portfolio", 422)
        with pytest.raises(InvalidInputError):
            await call()
        assert fake_backend.attempts == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
    async def test_retryable_statuses_raise_upstream_unavailable(self, fake_backend, status):
        fake_backend.status("portfolio", status)
        with pytest.raises(UpstreamUnavailableError):
            await call()

    @pytest.mark.asyncio
    async def test_error_excerpt_is_truncated(self, fake_backend):
        fake_backend.set("portfolio", httpx.Response(500, text="x" * 5000))
        with pytest.raises(UpstreamUnavailableError) as info:
            await call()
        assert len(str(info.value)) < 500


# ==========================================================================
# Retry policy
# ==========================================================================
class TestRetryPolicy:
    @pytest.mark.asyncio
    async def test_server_error_is_retried_then_raises(self, fake_backend):
        fake_backend.status("portfolio", 503)
        with pytest.raises(UpstreamUnavailableError):
            await call()
        assert fake_backend.attempts == 2, "one initial attempt plus one retry"

    @pytest.mark.asyncio
    async def test_transient_server_error_then_success(self, fake_backend):
        """The retry has to actually work, not just be counted."""
        fake_backend.set(
            "portfolio",
            httpx.Response(503, json={"error": "restarting"}),
            httpx.Response(200, json={"recovered": True}),
        )
        assert await call() == {"recovered": True}
        assert fake_backend.attempts == 2

    @pytest.mark.asyncio
    async def test_transport_error_is_retried(self, fake_backend):
        fake_backend.fail("portfolio", httpx.ConnectError("connection refused"))
        with pytest.raises(UpstreamUnavailableError):
            await call()
        assert fake_backend.attempts == 2

    @pytest.mark.asyncio
    async def test_transient_transport_error_then_success(self, fake_backend):
        fake_backend.set(
            "portfolio",
            httpx.ConnectError("first attempt dies"),
            httpx.Response(200, json={"recovered": True}),
        )
        assert await call() == {"recovered": True}

    @pytest.mark.asyncio
    async def test_zero_retry_budget_fails_on_the_first_attempt(self, fake_backend, monkeypatch):
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "0")
        fake_backend.status("portfolio", 503)
        with pytest.raises(UpstreamUnavailableError):
            await call()
        assert fake_backend.attempts == 1

    @pytest.mark.asyncio
    async def test_backoff_is_exponential(self, fake_backend, monkeypatch, no_sleep):
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "3")
        fake_backend.status("portfolio", 500)
        with pytest.raises(UpstreamUnavailableError):
            await call()
        assert no_sleep == [0.5, 1.0, 2.0]
        assert fake_backend.attempts == 4

    @pytest.mark.asyncio
    async def test_no_backoff_on_success(self, fake_backend, no_sleep):
        await call()
        assert no_sleep == []

    @pytest.mark.asyncio
    async def test_retry_is_logged_with_the_reason(self, fake_backend, caplog):
        fake_backend.status("portfolio", 502)
        with caplog.at_level("WARNING", logger="moneyfast.backend"):
            with pytest.raises(UpstreamUnavailableError):
                await call()
        assert any("retrying in" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_timeout_maps_to_upstream_unavailable(self, fake_backend):
        fake_backend.fail("portfolio", httpx.ReadTimeout("read timed out"))
        with pytest.raises(UpstreamUnavailableError, match="unreachable"):
            await call()

    @pytest.mark.asyncio
    async def test_connect_timeout_maps_to_upstream_unavailable(self, fake_backend):
        fake_backend.fail("portfolio", httpx.ConnectTimeout("connect timed out"))
        with pytest.raises(UpstreamUnavailableError):
            await call()

    @pytest.mark.asyncio
    async def test_error_names_the_url_for_diagnosis(self, fake_backend):
        """Operators need the URL: the usual cause is a Docker networking
        mistake, not a backend fault."""
        fake_backend.fail("portfolio", httpx.ConnectError("name resolution failed"))
        with pytest.raises(UpstreamUnavailableError) as info:
            await call()
        assert "backend:3000" in str(info.value)

    @pytest.mark.asyncio
    async def test_original_exception_is_chained(self, fake_backend):
        original = httpx.ConnectError("underlying cause")
        fake_backend.fail("portfolio", original)
        with pytest.raises(UpstreamUnavailableError) as info:
            await call()
        assert info.value.__cause__ is original


# ==========================================================================
# Body decoding
# ==========================================================================
class TestBodyDecoding:
    @pytest.mark.asyncio
    async def test_non_json_body_raises_upstream_unavailable(self, fake_backend):
        """A proxy error page returned with status 200. Not the backend's
        answer, so it must not be treated as one."""
        fake_backend.set("portfolio", httpx.Response(200, text="<html>gateway</html>"))
        with pytest.raises(UpstreamUnavailableError, match="non-JSON"):
            await call()

    @pytest.mark.asyncio
    async def test_non_json_body_is_not_retried_into_success(self, fake_backend):
        fake_backend.set("portfolio", httpx.Response(200, text="not json"))
        with pytest.raises(UpstreamUnavailableError):
            await call()
        assert fake_backend.attempts == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [[1, 2, 3], "a string", 42, True])
    async def test_non_object_json_raises_contract_violation(self, fake_backend, body):
        fake_backend.set("portfolio", httpx.Response(200, json=body))
        with pytest.raises(ContractViolationError, match="expected a JSON object"):
            await call()

    @pytest.mark.asyncio
    async def test_literal_null_body_raises_contract_violation(self, fake_backend):
        """A backend that answers `null` with a JSON content type. Valid JSON,
        but not an object, so it cannot be a tool payload.

        Note httpx.Response(json=None) sends an EMPTY body rather than the
        four bytes `null`, which is why the content is set explicitly here.
        """
        fake_backend.set(
            "portfolio",
            httpx.Response(200, content=b"null", headers={"content-type": "application/json"}),
        )
        with pytest.raises(ContractViolationError):
            await call()

    @pytest.mark.asyncio
    async def test_empty_object_is_a_valid_body(self, fake_backend):
        """{} is a well-formed object. The contract guards, not the transport,
        decide whether it is usable."""
        fake_backend.json("portfolio", {})
        assert await call() == {}


# ==========================================================================
# Defensive behaviour
# ==========================================================================
class TestNeverCrashesTheServer:
    @pytest.mark.asyncio
    async def test_unexpected_exception_is_wrapped(self, fake_backend, caplog):
        """An MCP tool that raises an arbitrary exception takes down the turn
        in a way the orchestrator cannot classify. Everything becomes a
        BackendError."""
        fake_backend.fail("portfolio", ValueError("something nobody predicted"))
        with caplog.at_level("ERROR", logger="moneyfast.backend"):
            with pytest.raises(UpstreamUnavailableError, match="unexpected failure"):
                await call()
        assert any("unexpected failure" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_unexpected_exception_is_not_retried(self, fake_backend, monkeypatch):
        monkeypatch.setenv("BACKEND_MAX_RETRIES", "3")
        fake_backend.fail("portfolio", ValueError("boom"))
        with pytest.raises(UpstreamUnavailableError):
            await call()
        assert fake_backend.attempts == 1

    @pytest.mark.asyncio
    async def test_backend_errors_pass_through_unwrapped(self, fake_backend, mocker):
        """A ContractViolationError raised inside the try block must not be
        re-wrapped as UpstreamUnavailableError; the classes mean different
        things to the caller."""
        fake_backend.set("portfolio", httpx.Response(200, json=[1]))
        with pytest.raises(ContractViolationError):
            await call()

    @pytest.mark.asyncio
    async def test_exhausted_loop_guard_raises_rather_than_returning_none(self, mocker):
        """Defensive branch.

        The retry loop always returns, continues or raises, so the trailing
        raise is unreachable with any real configuration. It is exercised here
        by forcing a zero-iteration loop, because a future refactor that makes
        it reachable must not be allowed to fall off the end and return None:
        a tool returning None would be rendered as an empty answer.
        """
        mocker.patch.object(backend_client, "max_retries", return_value=-1)
        with pytest.raises(UpstreamUnavailableError, match="unreachable"):
            await call()

    def test_error_classes_are_distinct_and_share_a_base(self):
        for cls in (AuthorizationError, InvalidInputError, UpstreamUnavailableError,
                    ContractViolationError):
            assert issubclass(cls, BackendError)
        assert not issubclass(AuthorizationError, UpstreamUnavailableError)
        assert not issubclass(ContractViolationError, InvalidInputError)
        assert issubclass(BackendError, RuntimeError)


# ==========================================================================
# Contract guards
# ==========================================================================
class TestContractGuards:
    def test_require_passes_when_every_key_is_present(self):
        backend_client.require({"a": 1, "b": 2}, ("a", "b"), TOOL)

    def test_require_lists_every_missing_key(self):
        with pytest.raises(ContractViolationError) as info:
            backend_client.require({"a": 1}, ("a", "b", "c"), TOOL)
        assert "b" in str(info.value) and "c" in str(info.value)

    def test_require_accepts_present_but_empty_values(self):
        """Present-and-empty is meaningful. Absent is not the same thing, and
        conflating them is how an empty portfolio becomes an invented one."""
        backend_client.require({"positions": [], "totals": {}}, ("positions", "totals"), TOOL)

    def test_require_accepts_a_none_value(self):
        backend_client.require({"recovery_date": None}, ("recovery_date",), TOOL)

    def test_require_list_returns_the_list(self):
        assert backend_client.require_list({"items": [1, 2]}, "items", TOOL) == [1, 2]

    def test_require_list_accepts_an_empty_list(self):
        assert backend_client.require_list({"items": []}, "items", TOOL) == []

    def test_require_list_rejects_a_missing_key(self):
        with pytest.raises(ContractViolationError):
            backend_client.require_list({}, "items", TOOL)

    @pytest.mark.parametrize("value", [{}, "abc", 5, None])
    def test_require_list_rejects_a_non_list(self, value):
        with pytest.raises(ContractViolationError, match="must be a list"):
            backend_client.require_list({"items": value}, "items", TOOL)

    def test_freshness_extracts_and_coerces(self):
        result = backend_client.freshness(
            {"as_of": "2026-08-19T15:10:00Z", "source": "FEED", "is_delayed": 1}, TOOL
        )
        assert result == {
            "as_of": "2026-08-19T15:10:00Z", "source": "FEED", "is_delayed": True
        }

    @pytest.mark.parametrize("missing", ["as_of", "source", "is_delayed"])
    def test_freshness_requires_all_three_fields(self, missing):
        """Every user-facing figure is attributed to these, so a missing one is
        a contract violation rather than something to default."""
        payload = {"as_of": "x", "source": "y", "is_delayed": False}
        del payload[missing]
        with pytest.raises(ContractViolationError):
            backend_client.freshness(payload, TOOL)


# ==========================================================================
# Transport seam
# ==========================================================================
class TestTransportSeam:
    def test_set_transport_installs_and_clears(self):
        sentinel = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        backend_client.set_transport(sentinel)
        assert backend_client._transport is sentinel
        backend_client.set_transport(None)
        assert backend_client._transport is None
