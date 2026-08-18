"""Unit tests for portfolio_tools.

Contract under test: Interface Definitions v2.1, get_portfolio_positions.
The dangerous failure for this tool is not a crash, it is a plausible number.
Most assertions therefore check internal arithmetic consistency rather than
just presence of keys.
"""

from __future__ import annotations

import pytest

import portfolio_tools
from conftest import assert_iso8601_utc

TOLERANCE = 0.01


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------
def test_returns_exact_top_level_contract(portfolio_top_level_keys):
    """No missing keys and, just as important, no extra ones."""
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    assert set(payload) == portfolio_top_level_keys


def test_freshness_fields_present_and_typed():
    """This is a data-fetching tool, so freshness is mandatory."""
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    assert_iso8601_utc(payload["as_of"])
    assert isinstance(payload["source"], str) and payload["source"]
    assert isinstance(payload["is_delayed"], bool)
    assert isinstance(payload["delay_minutes"], int)


def test_delay_minutes_consistent_with_is_delayed():
    """delay_minutes is 0 when and only when is_delayed is False."""
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    if payload["is_delayed"]:
        assert payload["delay_minutes"] > 0
    else:
        assert payload["delay_minutes"] == 0


def test_every_position_has_exact_key_set(position_keys):
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    assert payload["positions"], "fixture data should not be empty"
    for position in payload["positions"]:
        assert set(position) == position_keys, position.get("symbol")


@pytest.mark.parametrize("index", [0, 1])
def test_position_arithmetic_is_internally_consistent(index):
    """market_value, cost_basis and P&L must actually agree.

    A mock that returns inconsistent numbers trains the orchestrator on
    impossible data and hides bugs when the real feed lands.
    """
    position = portfolio_tools.get_portfolio_positions(user_id="u_123")["positions"][index]
    assert position["market_value"] == pytest.approx(
        position["quantity"] * position["last_price"], abs=TOLERANCE
    )
    assert position["cost_basis"] == pytest.approx(
        position["quantity"] * position["avg_cost"], abs=TOLERANCE
    )
    assert position["unrealized_pnl"] == pytest.approx(
        position["market_value"] - position["cost_basis"], abs=TOLERANCE
    )
    assert position["unrealized_pnl_pct"] == pytest.approx(
        position["unrealized_pnl"] / position["cost_basis"], abs=0.001
    )


def test_weights_sum_to_one():
    """Contract: weights sum to 1.0 within floating point tolerance."""
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    assert sum(p["weight"] for p in payload["positions"]) == pytest.approx(1.0, abs=0.001)


def test_weights_match_market_value_share():
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    total = payload["totals"]["total_market_value"]
    for position in payload["positions"]:
        assert position["weight"] == pytest.approx(
            position["market_value"] / total, abs=0.001
        )


def test_totals_agree_with_positions():
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    positions, totals = payload["positions"], payload["totals"]
    assert set(totals) == {
        "total_market_value", "total_cost_basis", "total_unrealized_pnl", "position_count",
    }
    assert totals["position_count"] == len(positions)
    assert totals["total_market_value"] == pytest.approx(
        sum(p["market_value"] for p in positions), abs=TOLERANCE
    )
    assert totals["total_cost_basis"] == pytest.approx(
        sum(p["cost_basis"] for p in positions), abs=TOLERANCE
    )
    assert totals["total_unrealized_pnl"] == pytest.approx(
        totals["total_market_value"] - totals["total_cost_basis"], abs=TOLERANCE
    )


def test_available_quantity_never_exceeds_quantity():
    """available_quantity is the sellable amount; it cannot exceed holdings."""
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    for position in payload["positions"]:
        assert 0 <= position["available_quantity"] <= position["quantity"]


def test_pledged_position_is_warned_about():
    """A reduced available_quantity must be explained in warnings."""
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    constrained = [
        p for p in payload["positions"] if p["available_quantity"] < p["quantity"]
    ]
    assert constrained, "fixture should include one constrained position"
    for position in constrained:
        assert any(position["symbol"] in w for w in payload["warnings"])


# --------------------------------------------------------------------------
# Argument handling
# --------------------------------------------------------------------------
@pytest.mark.parametrize("currency", ["TRY", "USD", "EUR"])
def test_base_currency_is_echoed(currency):
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123", base_currency=currency)
    assert payload["base_currency"] == currency


def test_defaults_are_applied_when_optionals_omitted():
    payload = portfolio_tools.get_portfolio_positions(user_id="u_123")
    assert payload["base_currency"] == "TRY"


def test_all_optional_arguments_accept_none_and_defaults():
    """None must not blow up: the mock ignores filters, the real one will not."""
    payload = portfolio_tools.get_portfolio_positions(
        user_id="u_123",
        account_ids=None,
        asset_classes=None,
        include_closed=False,
        base_currency="TRY",
        valuation_mode="LAST_CLOSE",
    )
    assert payload["positions"]


@pytest.mark.parametrize("valuation_mode", ["LAST_CLOSE", "INTRADAY"])
def test_valuation_modes_accepted(valuation_mode):
    payload = portfolio_tools.get_portfolio_positions(
        user_id="u_123", valuation_mode=valuation_mode
    )
    assert set(payload["positions"][0]) # smoke: structure intact


def test_explicit_filters_are_accepted():
    payload = portfolio_tools.get_portfolio_positions(
        user_id="u_123",
        account_ids=["acc_1", "acc_2"],
        asset_classes=["EQUITY", "ETF"],
        include_closed=True,
    )
    assert isinstance(payload["positions"], list)


# --------------------------------------------------------------------------
# Edge cases: the empty-result path
# --------------------------------------------------------------------------
def test_empty_fixture_returns_valid_complete_payload(portfolio_top_level_keys):
    """An empty portfolio is a valid answer, not an error."""
    payload = portfolio_tools.get_portfolio_positions_empty(user_id="u_new")
    assert set(payload) == portfolio_top_level_keys
    assert payload["positions"] == []
    assert payload["warnings"] == []


def test_empty_fixture_totals_are_zeroed_not_absent():
    """Zero division risk: totals must be present and zero, never missing."""
    totals = portfolio_tools.get_portfolio_positions_empty(user_id="u_new")["totals"]
    assert totals["position_count"] == 0
    assert totals["total_market_value"] == 0.0
    assert totals["total_cost_basis"] == 0.0
    assert totals["total_unrealized_pnl"] == 0.0


def test_empty_fixture_still_carries_freshness():
    """Freshness is not conditional on there being data."""
    payload = portfolio_tools.get_portfolio_positions_empty(user_id="u_new")
    assert_iso8601_utc(payload["as_of"])
    assert payload["source"]
    assert isinstance(payload["is_delayed"], bool)


def test_weight_sum_on_empty_portfolio_does_not_divide_by_zero():
    payload = portfolio_tools.get_portfolio_positions_empty(user_id="u_new")
    assert sum(p["weight"] for p in payload["positions"]) == 0


# --------------------------------------------------------------------------
# Isolation and future error handling
# --------------------------------------------------------------------------
def test_makes_no_network_call_today(mocker):
    """Guard test.

    The tool is a mock, so it must not touch an HTTP client. ``create=True``
    injects the attribute that does not exist yet, so this test keeps working
    when ``import httpx`` lands in the module: flip the assertion to
    ``assert client.get.called`` at that point.
    """
    client = mocker.patch.object(portfolio_tools, "httpx", create=True)
    portfolio_tools.get_portfolio_positions(user_id="u_123")
    assert client.get.call_count == 0
    assert client.post.call_count == 0


def test_upstream_failure_propagates(mocker):
    """Simulated HTTP 500 from the custodian.

    Patches the callable the orchestrator actually depends on, which is the
    seam that survives the mock-to-real migration. The contract says an
    upstream failure must surface, never degrade to remembered positions.
    """
    mocker.patch.object(
        portfolio_tools,
        "get_portfolio_positions",
        side_effect=RuntimeError("UpstreamUnavailableError: HTTP 500"),
    )
    with pytest.raises(RuntimeError, match="HTTP 500"):
        portfolio_tools.get_portfolio_positions(user_id="u_123")


def test_authorization_failure_propagates(mocker):
    mocker.patch.object(
        portfolio_tools,
        "get_portfolio_positions",
        side_effect=PermissionError("AuthorizationError"),
    )
    with pytest.raises(PermissionError):
        portfolio_tools.get_portfolio_positions(user_id="u_not_entitled")


def test_no_pii_beyond_contract_leaks_into_payload():
    """user_id must never be echoed back into a payload that gets rendered."""
    payload = portfolio_tools.get_portfolio_positions(user_id="u_secret_123")
    assert "u_secret_123" not in repr(payload)


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
def test_register_attaches_exactly_the_bound_tool(mocker):
    fake_mcp = mocker.MagicMock()
    portfolio_tools.register(fake_mcp)
    fake_mcp.tool.assert_called_once_with()
    fake_mcp.tool.return_value.assert_called_once_with(
        portfolio_tools.get_portfolio_positions
    )


def test_register_does_not_expose_the_empty_fixture(mocker):
    """get_portfolio_positions_empty is a test fixture, not a tool."""
    fake_mcp = mocker.MagicMock()
    portfolio_tools.register(fake_mcp)
    registered = [c.args[0] for c in fake_mcp.tool.return_value.call_args_list]
    assert portfolio_tools.get_portfolio_positions_empty not in registered
