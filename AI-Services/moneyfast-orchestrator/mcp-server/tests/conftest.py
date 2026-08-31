"""Shared fixtures for the MoneyFast MCP tool suite.

The tools now speak HTTP to the core backend, so isolation works on two
levels and both are autouse:

1. ``fake_backend`` installs an ``httpx.MockTransport`` through
   ``backend_client.set_transport`` before every test and removes it after.
   Nothing reaches a real socket, and every request is recorded so tests can
   assert on method, URL, query string, headers and body.
2. ``block_network`` patches the socket layer itself. If a future change adds
   an HTTP client that bypasses ``backend_client``, the suite fails loudly
   instead of quietly dialling out from CI.

``no_sleep`` neutralises the retry backoff. The retry policy is asserted by
counting attempts and inspecting the delays passed to ``asyncio.sleep``, never
by waiting for them.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import pytest

# tests/ lives under mcp-server/; the tool modules sit one level up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend_client  # noqa: E402


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------
class NetworkAccessAttempted(RuntimeError):
    """Raised when a test tries to open a real socket."""


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second line of defence behind the MockTransport."""

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise NetworkAccessAttempted(
            "Real network access attempted. Route the call through "
            "backend_client and let fake_backend intercept it."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic configuration regardless of the developer's shell."""
    for name in (
        "BACKEND_API_BASE_URL",
        "RAG_API_BASE_URL",
        "BACKEND_TIMEOUT_SECONDS",
        "BACKEND_CONNECT_TIMEOUT",
        "BACKEND_MAX_RETRIES",
        "BACKEND_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record backoff delays instead of waiting them out.

    Returned so a test can assert the exponential schedule. Requesting the
    fixture by name is optional; it is applied either way.
    """
    delays: list[float] = []

    async def _sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(backend_client.asyncio, "sleep", _sleep)
    return delays


# --------------------------------------------------------------------------
# The backend double
# --------------------------------------------------------------------------
#: Path fragment -> route key. Keeps tests readable: backend.set("portfolio", ...)
ROUTES = {
    "/investment/portfolio/": "portfolio",
    "/investment/transactions/stage": "stage",
    "/risk/calculate": "risk",
    "/risk/profile/": "risk_summary",
    "/market/instruments": "instruments",
    "/market/technicals": "technicals",
    "/compliance/validate": "compliance",
    # v2.8 banking. `payments/stage` is listed BEFORE the investment stage
    # route would ever be consulted for it; the two paths do not overlap, but
    # naming both keeps the mapping explicit.
    "/banking/bills/lookup": "lookup",
    "/banking/payments/stage": "payment_stage",
    # Served by the rag service on its own base URL, matched on path alone.
    "/search": "search",
}


class FakeBackend:
    """An in-process stand-in for the core backend.

    Each route holds a queue of outcomes. When the queue has more than one
    entry the next call pops one, which is how retry behaviour is driven
    (fail, then succeed). The final entry repeats indefinitely.

    An outcome is either an ``httpx.Response``, a callable taking the request,
    or an exception instance, which is raised to simulate a transport failure.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[Any]] = {}
        self.requests: list[httpx.Request] = []

    # -- configuration ----------------------------------------------------
    def set(self, route: str, *outcomes: Any) -> None:
        self._queues[route] = list(outcomes)

    def json(self, route: str, payload: Any, status: int = 200) -> None:
        self.set(route, httpx.Response(status, json=payload))

    def status(self, route: str, status: int, payload: Any = None) -> None:
        self.set(route, httpx.Response(status, json=payload or {"error": "backend said no"}))

    def fail(self, route: str, exc: Optional[BaseException] = None) -> None:
        self.set(route, exc or httpx.ConnectError("connection refused"))

    # -- transport --------------------------------------------------------
    @property
    def attempts(self) -> int:
        """Total requests seen, including retries."""
        return len(self.requests)

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "no request was made"
        return self.requests[-1]

    def body(self, index: int = -1) -> dict:
        import json as _json

        return _json.loads(self.requests[index].content)

    def _route_for(self, path: str) -> Optional[str]:
        for fragment, key in ROUTES.items():
            if fragment in path:
                return key
        return None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self._route_for(request.url.path)
        queue = self._queues.get(route)
        if not queue:
            return httpx.Response(404, json={"error": f"no stub for {request.url.path}"})
        outcome = queue[0] if len(queue) == 1 else queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome(request)
        return outcome


@pytest.fixture(autouse=True)
def fake_backend(
    portfolio_payload, search_payload, risk_payload, risk_summary_payload,
    compliance_payload, stage_payload,
):
    """Install the transport double, preloaded with valid responses.

    Autouse so no test can accidentally run without it. Tests override a route
    with ``fake_backend.json(...)``, ``.status(...)`` or ``.fail(...)``.
    """
    backend = FakeBackend()
    backend.json("portfolio", portfolio_payload)
    backend.json("search", search_payload)
    backend.json("risk", risk_payload)
    backend.json("risk_summary", risk_summary_payload)
    backend.json("compliance", compliance_payload)
    backend.json("stage", stage_payload)

    backend_client.set_transport(httpx.MockTransport(backend.handler))
    yield backend
    backend_client.set_transport(None)


# --------------------------------------------------------------------------
# Backend response payloads (what a healthy backend returns)
# --------------------------------------------------------------------------
@pytest.fixture()
def portfolio_payload() -> dict[str, Any]:
    return {
        "as_of": "2026-08-19T15:10:00Z",
        "source": "CUSTODIAN_OF_RECORD",
        "is_delayed": True,
        "delay_minutes": 15,
        "base_currency": "TRY",
        "positions": [
            {
                "symbol": "THYAO",
                "isin": "TRATHYAO91M5",
                "name": "Türk Hava Yolları A.O.",
                "asset_class": "EQUITY",
                "exchange": "XIST",
                "quantity": 500.0,
                "avg_cost": 268.40,
                "instrument_currency": "TRY",
                "last_price": 291.75,
                "market_value": 145875.00,
                "cost_basis": 134200.00,
                "weight": 0.7537,
                "available_quantity": 400.0,
                "opened_at": "2025-11-04",
            },
            {
                "symbol": "ASELS",
                "isin": "TRAASELS91H2",
                "name": "Aselsan Elektronik Sanayi ve Ticaret A.Ş.",
                "asset_class": "EQUITY",
                "exchange": "XIST",
                "quantity": 300.0,
                "avg_cost": 142.10,
                "instrument_currency": "TRY",
                "last_price": 158.90,
                "market_value": 47670.00,
                "cost_basis": 42630.00,
                "weight": 0.2463,
                "available_quantity": 300.0,
                "opened_at": "2026-02-17",
            },
        ],
        "totals": {
            "total_market_value": 193545.00,
            "total_cost_basis": 176830.00,
            "total_unrealized_pnl": 16715.00,
            "position_count": 2,
        },
        "warnings": ["THYAO: 100 lot pledged against an open order."],
    }


@pytest.fixture()
def search_payload() -> dict[str, Any]:
    return {
        "as_of": "2026-08-19T15:10:00Z",
        "source": "VECTOR_STORE::market_corpus_v4",
        "is_delayed": False,
        "index_lag_minutes": 0,
        "query_echo": "THYAO 2Ç26 sonuçları",
        "results": [
            {
                "chunk_id": "chk_9f2a41c7",
                "doc_id": "doc_20260812_aa_thyao",
                "title": "THY ikinci çeyrek finansal sonuçlarını açıkladı",
                "snippet": "Şirket, ikinci çeyrekte yolcu sayısının arttığını bildirdi.",
                "publisher": "Anadolu Ajansı",
                "author": None,
                "published_at": "2026-08-12T07:45:00Z",
                "url": "https://example-wire.invalid/thyao-2q26",
                "tickers": ["THYAO"],
                "doc_type": "NEWS",
                "language": "tr",
                "score": 0.87,
                "is_opinion": False,
            }
        ],
    }


@pytest.fixture()
def risk_payload() -> dict[str, Any]:
    return {
        "as_of": "2026-08-18T18:10:00Z",
        "source": "BIST_EOD",
        "is_delayed": False,
        "window": {
            "start_date": "2025-08-19",
            "end_date": "2026-08-18",
            "observation_count": 249,
            "frequency": "DAILY",
        },
        "metrics": {
            "volatility_annualized": 0.3418,
            "max_drawdown": {"value": -0.2914, "recovery_date": None},
            "beta": 1.14,
            "correlation_to_benchmark": 0.81,
            "sharpe_ratio": 0.27,
            "concentration": {"hhi": 0.6288, "effective_n": 1.5903},
        },
        "assumptions": {
            "risk_free_rate": 0.42,
            "risk_free_rate_source": "DOMESTIC_POLICY_RATE",
            "annualization_factor": 252,
        },
        "data_quality": {
            "coverage": 1.0,
            "excluded_symbols": [],
            "gap_filled_days": 3,
            "is_statistically_reliable": True,
        },
    }


@pytest.fixture()
def risk_summary_payload() -> dict[str, Any]:
    """What GET /risk/profile/{user_id} returns for a measured portfolio.

    No source/is_delayed block: this payload is an interpretation computed
    from a price feed, not a reading of one, and stamping it with a provider
    name would attribute the score to something that never produced it.
    """
    return {
        "as_of": "2026-08-27T09:15:00Z",
        "score": 83.4,
        "level": "Düşük",
        "position_count": 14,
        "suitability": {
            "measured_level": "Düşük",
            "declared_tolerance": "Orta",
            "alignment": "PORTFOLIO_CALMER",
            "statement": "Ölçülen portföy riskiniz \"Düşük\" seviyesinde.",
        },
        "declared": {
            "tolerance_level": "Orta",
            "investment_horizon": "LONG",
            "assessed_at": "2026-08-26T11:02:00Z",
            "questionnaire_version": "v1",
        },
        "metrics": {
            "volatility_annualized": 0.1842,
            "max_drawdown": -0.1104,
            "hhi": 0.1601,
            "effective_n": 6.246,
            "top_3_weight": 0.4412,
            "largest_position": {"symbol": "TEST-THYAO", "weight": 0.19},
        },
        "findings": [
            {"label": "Yoğunlaşma", "detail": "Portföy 6 pozisyona denk dağılmış.",
             "severity": "INFO"},
        ],
        "data_quality": {
            "coverage": 1.0,
            "excluded_symbols": [],
            "gap_filled_days": 0,
            "is_statistically_reliable": True,
        },
        "warnings": [],
    }


@pytest.fixture()
def compliance_payload() -> dict[str, Any]:
    return {
        "verdict": "PASS",
        "rule_pack_version": "TR_RETAIL_2026.07",
        "violations": [],
        "required_disclosures": [],
        "remediated_response": None,
        "blocked_reason_user_facing": None,
        "audit_id": "aud_5c1e7b90",
    }


@pytest.fixture()
def stage_payload() -> dict[str, Any]:
    return {
        "proposal_id": "prp_8d31f04c",
        "status": "PENDING_USER_CONFIRMATION",
        "expires_at": "2026-08-19T15:25:00Z",
        "confirmation_required": True,
        "summary": {"transaction_type": "BUY", "quantity": 100.0},
        "estimate": {
            "indicative_price": 291.75,
            "indicative_price_timestamp": "2026-08-19T15:09:45Z",
            "indicative_price_basis": "LAST_TRADE",
            "gross_amount": 29175.00,
            "currency": "TRY",
            "fees": [{"name": "Aracı kurum komisyonu", "amount": 29.18}],
            "taxes": [{"name": "BSMV", "amount": 1.46}],
            "total_cost": 29205.64,
            "fx": None,
            "price_certainty": "INDICATIVE",
        },
        "impact": {"resulting_position_quantity": 600.0},
        "blockers": [],
        "warnings": [],
        "missing_fields": [],
        "disclosures": ["Emir, ekrandaki onay adımı tamamlanmadan iletilmez."],
        "audit_id": "aud_7a20be31",
    }


# --------------------------------------------------------------------------
# Contract fixtures: the exact key sets v2.1 promises
# --------------------------------------------------------------------------
MARKET_DATA_FIELDS = frozenset({"as_of", "source", "is_delayed"})


@pytest.fixture(scope="session")
def portfolio_top_level_keys() -> frozenset[str]:
    return frozenset(
        {
            "as_of", "source", "is_delayed", "delay_minutes", "base_currency",
            "positions", "totals", "warnings",
        }
    )


@pytest.fixture(scope="session")
def position_keys() -> frozenset[str]:
    return frozenset(
        {
            # v2.6 adds `sector` and `market`. Both additive. The risk engine
            # buckets exposure by sector and reported every portfolio as 100%
            # UNCLASSIFIED, not because sectors were unknown but because the
            # positions handed to it never carried the field.
            "symbol", "isin", "name", "asset_class", "sector", "market",
            "exchange", "quantity",
            "avg_cost", "instrument_currency", "last_price", "market_value",
            "cost_basis", "unrealized_pnl", "unrealized_pnl_pct", "weight",
            "available_quantity", "opened_at",
        }
    )


@pytest.fixture(scope="session")
def rag_top_level_keys() -> frozenset[str]:
    return frozenset(
        {"as_of", "source", "is_delayed", "index_lag_minutes", "results", "query_echo"}
    )


@pytest.fixture(scope="session")
def rag_result_keys() -> frozenset[str]:
    return frozenset(
        {
            "chunk_id", "doc_id", "title", "snippet", "publisher", "author",
            "published_at", "url", "tickers", "doc_type", "language", "score",
            "is_opinion",
        }
    )


@pytest.fixture(scope="session")
def risk_top_level_keys() -> frozenset[str]:
    return frozenset(
        {"as_of", "source", "is_delayed", "window", "metrics", "assumptions", "data_quality"}
    )


@pytest.fixture(scope="session")
def compliance_top_level_keys() -> frozenset[str]:
    return frozenset(
        {
            "verdict", "rule_pack_version", "violations", "required_disclosures",
            "remediated_response", "blocked_reason_user_facing", "audit_id",
        }
    )


@pytest.fixture(scope="session")
def routing_top_level_keys() -> frozenset[str]:
    return frozenset(
        {
            "primary_intent", "confidence", "target_agent", "secondary_intents",
            "is_compound", "sub_requests", "entities", "required_tools",
            "needs_clarification", "clarifying_question", "routing_rationale",
            "safety_flags",
            # Added when routing moved to the orchestrator: tells the caller
            # whether it may substitute its own decision. False means safety
            # decided, and safety is not delegable.
            "is_overridable",
        }
    )


@pytest.fixture(scope="session")
def proposal_top_level_keys() -> frozenset[str]:
    return frozenset(
        {
            "proposal_id", "status", "expires_at", "confirmation_required",
            "summary", "estimate", "impact", "blockers", "warnings",
            "missing_fields", "disclosures", "audit_id",
        }
    )


@pytest.fixture()
def sample_positions() -> list[dict[str, Any]]:
    """Minimum viable position payload accepted by the risk tool."""
    return [
        {"symbol": "THYAO", "quantity": 500.0, "market_value": 145875.0, "asset_class": "EQUITY"},
        {"symbol": "ASELS", "quantity": 300.0, "market_value": 47670.0, "asset_class": "EQUITY"},
    ]


@pytest.fixture()
def stage_args() -> dict[str, Any]:
    """The four mandatory arguments for prepare_transaction_proposal."""
    return {
        "user_id": "u_123",
        "transaction_type": "BUY",
        "source_account_id": "acc_998877",
        "idempotency_key": "idem_abc123",
    }


# --------------------------------------------------------------------------
# Shared assertion helpers
# --------------------------------------------------------------------------
def assert_iso8601_utc(value: str) -> None:
    """Every timestamp in the contract is ISO 8601 with a trailing Z."""
    assert isinstance(value, str), f"timestamp must be str, got {type(value)}"
    assert value.endswith("Z"), f"timestamp must be UTC with trailing Z: {value!r}"
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def assert_no_market_data_fields(payload: dict[str, Any]) -> None:
    """Tools 4, 5 and 6 must not carry as_of / source / is_delayed."""
    leaked = MARKET_DATA_FIELDS & set(payload)
    assert not leaked, f"non-data tool leaked market data fields: {sorted(leaked)}"


def without(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    """A copy of a backend payload with keys removed, for guard tests."""
    return {k: v for k, v in payload.items() if k not in keys}
