"""Shared pytest fixtures for the MoneyFast MCP tool suite.

Three jobs:

1. Put the tool modules on ``sys.path`` so ``import portfolio_tools`` works
   from inside ``tests/`` without packaging the server.
2. Guarantee isolation. ``block_network`` is autouse: any test that opens a
   real socket fails loudly. Today the tools return hardcoded mocks, so
   nothing tries. The day someone drops a live ``httpx`` or ``yfinance`` call
   into a tool, the unit suite fails instead of silently going to the network
   in CI.
3. Hold the contract fixtures (expected key sets) that every test asserts
   against, so a schema change breaks in one obvious place rather than in
   thirty scattered literals.
"""

from __future__ import annotations

import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

# --- 1. import path -------------------------------------------------------
# tests/ lives under mcp-server/; the tool modules sit one level up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# --- 2. isolation ---------------------------------------------------------
class NetworkAccessAttempted(RuntimeError):
    """Raised when a unit test tries to open a real socket."""


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that attempts real network I/O.

    Autouse, so it protects the whole suite including future tests. When a
    tool starts making real calls, mock the client in the test; do not
    disable this fixture.
    """

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise NetworkAccessAttempted(
            "Real network access attempted in a unit test. Mock the HTTP "
            "client (e.g. mocker.patch('portfolio_tools.httpx.get')) instead."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture()
def fake_http_client(mocker):
    """A stand-in for the HTTP client a real implementation will use.

    Usage once a tool actually calls out::

        def test_upstream_500(fake_http_client, mocker):
            mocker.patch.object(portfolio_tools, "httpx", fake_http_client)
            fake_http_client.get.side_effect = RuntimeError("HTTP 500")
            with pytest.raises(RuntimeError):
                portfolio_tools.get_portfolio_positions("u_1")
    """
    client = mocker.MagicMock(name="httpx_like_client")
    client.get.return_value = mocker.MagicMock(status_code=200, json=lambda: {})
    client.post.return_value = mocker.MagicMock(status_code=200, json=lambda: {})
    return client


# --- 3. contract fixtures -------------------------------------------------
# Interface Definitions v2.1: only the three data-fetching tools carry
# freshness fields at the top level. The other three must NOT, so that a
# calling model never learns to expect (or hallucinate) them.
MARKET_DATA_FIELDS = frozenset({"as_of", "source", "is_delayed"})


@pytest.fixture(scope="session")
def market_data_fields() -> frozenset[str]:
    return MARKET_DATA_FIELDS


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
            "symbol", "isin", "name", "asset_class", "exchange", "quantity",
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
    """Minimum viable position payload for the risk tool.

    Deliberately only the four keys the contract calls mandatory, to prove the
    tool does not secretly depend on extras.
    """
    return [
        {"symbol": "THYAO", "quantity": 500.0, "market_value": 145875.0, "asset_class": "EQUITY"},
        {"symbol": "ASELS", "quantity": 300.0, "market_value": 47670.0, "asset_class": "EQUITY"},
    ]


# --- shared assertion helpers --------------------------------------------
def assert_iso8601_utc(value: str) -> None:
    """Every timestamp in the contract is ISO 8601 with a trailing Z."""
    assert isinstance(value, str), f"timestamp must be str, got {type(value)}"
    assert value.endswith("Z"), f"timestamp must be UTC with trailing Z: {value!r}"
    # Raises ValueError if malformed, which is the assertion we want.
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def assert_no_market_data_fields(payload: dict[str, Any]) -> None:
    """Tools 4, 5 and 6 must not carry as_of / source / is_delayed."""
    leaked = MARKET_DATA_FIELDS & set(payload)
    assert not leaked, f"non-data tool leaked market data fields: {sorted(leaked)}"


@pytest.fixture(scope="session")
def helpers():
    """Expose the helpers as a fixture for tests that prefer injection."""

    class _Helpers:
        assert_iso8601_utc = staticmethod(assert_iso8601_utc)
        assert_no_market_data_fields = staticmethod(assert_no_market_data_fields)

    return _Helpers
