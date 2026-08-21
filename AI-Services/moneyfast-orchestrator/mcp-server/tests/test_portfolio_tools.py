"""Unit tests for portfolio_tools.

Contract under test: Interface Definitions v2.1, get_portfolio_positions,
now backed by GET /investment/portfolio/{user_id}/positions.

The dangerous failure here is not a crash, it is a plausible number. The
normalizer sits between an unverified backend and a model that will narrate
whatever it receives, so most assertions check that it refuses bad input
rather than smoothing it over.
"""

from __future__ import annotations

import pytest

import portfolio_tools
from backend_client import (
    AuthorizationError,
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)
from conftest import assert_iso8601_utc, without

TOLERANCE = 0.01
pytestmark = pytest.mark.asyncio


# ==========================================================================
# Request construction
# ==========================================================================
class TestRequest:
    async def test_uses_get_on_the_user_scoped_path(self, fake_backend):
        await portfolio_tools.get_portfolio_positions("u_123")
        assert fake_backend.last.method == "GET"
        assert "/investment/portfolio/u_123/positions" in str(fake_backend.last.url)

    async def test_default_query_parameters(self, fake_backend):
        await portfolio_tools.get_portfolio_positions("u_123")
        query = str(fake_backend.last.url)
        assert "include_closed=false" in query
        assert "base_currency=TRY" in query
        assert "valuation_mode=LAST_CLOSE" in query

    async def test_optional_filters_are_forwarded(self, fake_backend):
        await portfolio_tools.get_portfolio_positions(
            "u_123",
            account_ids=["acc_1", "acc_2"],
            asset_classes=["EQUITY", "ETF"],
            include_closed=True,
            base_currency="USD",
            valuation_mode="INTRADAY",
        )
        query = str(fake_backend.last.url)
        assert "account_ids=acc_1" in query and "account_ids=acc_2" in query
        assert "asset_classes=EQUITY" in query and "asset_classes=ETF" in query
        assert "include_closed=true" in query
        assert "base_currency=USD" in query
        assert "valuation_mode=INTRADAY" in query

    async def test_none_filters_are_omitted_not_sent_as_null(self, fake_backend):
        await portfolio_tools.get_portfolio_positions(
            "u_123", account_ids=None, asset_classes=None
        )
        query = str(fake_backend.last.url)
        assert "account_ids" not in query
        assert "asset_classes" not in query

    async def test_one_request_per_call(self, fake_backend):
        await portfolio_tools.get_portfolio_positions("u_123")
        assert fake_backend.attempts == 1


# ==========================================================================
# Happy path
# ==========================================================================
class TestHappyPath:
    async def test_exact_top_level_contract(self, portfolio_top_level_keys):
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert set(payload) == portfolio_top_level_keys

    async def test_every_position_has_the_exact_key_set(self, position_keys):
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert payload["positions"]
        for position in payload["positions"]:
            assert set(position) == position_keys, position["symbol"]

    async def test_unknown_backend_fields_are_dropped(self, fake_backend, portfolio_payload):
        """The contract promises an exact key set. An extra field is a figure
        the model has no instructions for, and it would narrate it anyway."""
        portfolio_payload["positions"][0]["internal_ledger_id"] = "LEDGER-42"
        portfolio_payload["experimental_score"] = 0.9
        fake_backend.json("portfolio", portfolio_payload)
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert "experimental_score" not in payload
        assert "internal_ledger_id" not in payload["positions"][0]

    async def test_freshness_is_propagated(self):
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert_iso8601_utc(payload["as_of"])
        assert payload["source"] == "CUSTODIAN_OF_RECORD"
        assert payload["is_delayed"] is True
        assert payload["delay_minutes"] == 15

    async def test_pnl_is_derived_not_trusted(self, fake_backend, portfolio_payload):
        """The backend does not send unrealized_pnl; deriving it locally means
        the three numbers on screen always agree with each other."""
        portfolio_payload["positions"] = [portfolio_payload["positions"][0]]
        fake_backend.json("portfolio", portfolio_payload)
        position = (await portfolio_tools.get_portfolio_positions("u_123"))["positions"][0]
        assert position["unrealized_pnl"] == pytest.approx(11675.0, abs=TOLERANCE)
        assert position["unrealized_pnl_pct"] == pytest.approx(11675.0 / 134200.0, abs=0.0001)

    async def test_available_quantity_is_preserved(self):
        """available_quantity, not quantity, is the sellable amount."""
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert payload["positions"][0]["available_quantity"] == 400.0
        assert payload["positions"][0]["quantity"] == 500.0

    async def test_available_quantity_defaults_to_full_quantity(
        self, fake_backend, portfolio_payload
    ):
        """A backend that does not model settlement holds means the whole
        position is sellable. This is the one safe numeric default."""
        del portfolio_payload["positions"][0]["available_quantity"]
        fake_backend.json("portfolio", portfolio_payload)
        position = (await portfolio_tools.get_portfolio_positions("u_123"))["positions"][0]
        assert position["available_quantity"] == position["quantity"]

    async def test_optional_descriptive_fields_default_without_raising(
        self, fake_backend, portfolio_payload
    ):
        """Cosmetic fields may be absent; numeric ones may not."""
        minimal = {
            "symbol": "GARAN", "quantity": 10.0, "avg_cost": 100.0,
            "last_price": 110.0, "market_value": 1100.0, "cost_basis": 1000.0,
        }
        portfolio_payload["positions"] = [minimal]
        fake_backend.json("portfolio", portfolio_payload)
        position = (await portfolio_tools.get_portfolio_positions("u_123"))["positions"][0]
        assert position["name"] == "GARAN"
        assert position["asset_class"] == "EQUITY"
        assert position["exchange"] == "XIST"
        assert position["instrument_currency"] == "TRY"
        assert position["isin"] is None
        assert position["opened_at"] == ""
        assert position["weight"] == 0.0

    async def test_totals_are_carried_through(self):
        totals = (await portfolio_tools.get_portfolio_positions("u_123"))["totals"]
        assert set(totals) == {
            "total_market_value", "total_cost_basis", "total_unrealized_pnl",
            "position_count",
            # v2.3: cash, so "bakiyem ne kadar" has an answer.
            "cash_balance", "total_value",
        }
        assert totals["position_count"] == 2

    async def test_position_count_defaults_to_the_row_count(
        self, fake_backend, portfolio_payload
    ):
        del portfolio_payload["totals"]["position_count"]
        fake_backend.json("portfolio", portfolio_payload)
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert payload["totals"]["position_count"] == len(payload["positions"])

    async def test_warnings_default_to_empty(self, fake_backend, portfolio_payload):
        fake_backend.json("portfolio", without(portfolio_payload, "warnings"))
        assert (await portfolio_tools.get_portfolio_positions("u_123"))["warnings"] == []


# ==========================================================================
# base_currency
# ==========================================================================
class TestBaseCurrency:
    async def test_backend_value_is_used_when_present(self):
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert payload["base_currency"] == "TRY"

    async def test_falls_back_to_the_requested_currency(self, fake_backend, portfolio_payload):
        """The contract defines this field as the requested normalization
        currency, so a silent backend must not leave it undefined."""
        fake_backend.json("portfolio", without(portfolio_payload, "base_currency"))
        payload = await portfolio_tools.get_portfolio_positions("u_123", base_currency="EUR")
        assert payload["base_currency"] == "EUR"


# ==========================================================================
# delay_minutes
# ==========================================================================
class TestDelayMinutes:
    async def test_absent_delay_on_a_live_feed_becomes_zero(
        self, fake_backend, portfolio_payload
    ):
        portfolio_payload["is_delayed"] = False
        fake_backend.json("portfolio", without(portfolio_payload, "delay_minutes"))
        payload = await portfolio_tools.get_portfolio_positions("u_123")
        assert payload["delay_minutes"] == 0

    async def test_absent_delay_on_a_delayed_feed_is_a_violation(
        self, fake_backend, portfolio_payload
    ):
        """Only inferable in one direction. A delayed feed that will not state
        its lag cannot have one guessed for it: the answer is attributed to a
        timestamp the user is told is current."""
        portfolio_payload["is_delayed"] = True
        fake_backend.json("portfolio", without(portfolio_payload, "delay_minutes"))
        with pytest.raises(ContractViolationError, match="delay_minutes"):
            await portfolio_tools.get_portfolio_positions("u_123")

    async def test_explicit_null_delay_behaves_like_absent(
        self, fake_backend, portfolio_payload
    ):
        portfolio_payload["is_delayed"] = False
        portfolio_payload["delay_minutes"] = None
        fake_backend.json("portfolio", portfolio_payload)
        assert (await portfolio_tools.get_portfolio_positions("u_123"))["delay_minutes"] == 0


# ==========================================================================
# The empty portfolio
# ==========================================================================
class TestEmptyPortfolio:
    async def test_empty_positions_is_a_valid_complete_answer(
        self, fake_backend, portfolio_payload, portfolio_top_level_keys
    ):
        """positions == [] means the user holds nothing. It is not an error,
        not a retry signal, and never a licence to substitute examples."""
        portfolio_payload["positions"] = []
        portfolio_payload["totals"] = {
            "total_market_value": 0.0, "total_cost_basis": 0.0,
            "total_unrealized_pnl": 0.0, "position_count": 0,
        }
        fake_backend.json("portfolio", portfolio_payload)
        payload = await portfolio_tools.get_portfolio_positions("u_new")
        assert set(payload) == portfolio_top_level_keys
        assert payload["positions"] == []
        assert payload["totals"]["position_count"] == 0

    async def test_empty_portfolio_still_carries_freshness(
        self, fake_backend, portfolio_payload
    ):
        portfolio_payload["positions"] = []
        fake_backend.json("portfolio", portfolio_payload)
        payload = await portfolio_tools.get_portfolio_positions("u_new")
        assert_iso8601_utc(payload["as_of"])
        assert payload["source"]

    async def test_missing_positions_key_is_not_an_empty_portfolio(
        self, fake_backend, portfolio_payload
    ):
        """The distinction the whole data-integrity rule rests on. Absent means
        the backend did not answer the question; empty means it answered
        'nothing'. Defaulting the first to the second would tell a user with
        holdings that they have none."""
        fake_backend.json("portfolio", without(portfolio_payload, "positions"))
        with pytest.raises(ContractViolationError, match="positions"):
            await portfolio_tools.get_portfolio_positions("u_123")


# ==========================================================================
# Contract guards
# ==========================================================================
class TestContractGuards:
    @pytest.mark.parametrize("missing", ["as_of", "source", "is_delayed"])
    async def test_missing_freshness_field_is_a_violation(
        self, fake_backend, portfolio_payload, missing
    ):
        fake_backend.json("portfolio", without(portfolio_payload, missing))
        with pytest.raises(ContractViolationError):
            await portfolio_tools.get_portfolio_positions("u_123")

    async def test_missing_totals_is_a_violation(self, fake_backend, portfolio_payload):
        fake_backend.json("portfolio", without(portfolio_payload, "totals"))
        with pytest.raises(ContractViolationError, match="totals"):
            await portfolio_tools.get_portfolio_positions("u_123")

    @pytest.mark.parametrize("bad", [[], "totals", 5])
    async def test_non_object_totals_is_a_violation(
        self, fake_backend, portfolio_payload, bad
    ):
        portfolio_payload["totals"] = bad
        fake_backend.json("portfolio", portfolio_payload)
        with pytest.raises(ContractViolationError, match="must be an object"):
            await portfolio_tools.get_portfolio_positions("u_123")

    @pytest.mark.parametrize(
        "missing", ["total_market_value", "total_cost_basis", "total_unrealized_pnl"]
    )
    async def test_missing_total_is_a_violation(
        self, fake_backend, portfolio_payload, missing
    ):
        """Zero is a real total and cannot be the default for an absent one."""
        del portfolio_payload["totals"][missing]
        fake_backend.json("portfolio", portfolio_payload)
        with pytest.raises(ContractViolationError, match=missing):
            await portfolio_tools.get_portfolio_positions("u_123")

    @pytest.mark.parametrize("bad", ["THYAO", 42, None, ["THYAO"]])
    async def test_non_object_position_is_a_violation(
        self, fake_backend, portfolio_payload, bad
    ):
        portfolio_payload["positions"] = [bad]
        fake_backend.json("portfolio", portfolio_payload)
        with pytest.raises(ContractViolationError, match="must be an object"):
            await portfolio_tools.get_portfolio_positions("u_123")

    @pytest.mark.parametrize(
        "missing",
        ["symbol", "quantity", "avg_cost", "last_price", "market_value", "cost_basis"],
    )
    async def test_missing_numeric_position_field_is_a_violation(
        self, fake_backend, portfolio_payload, missing
    ):
        """Defaulting a missing quantity or price to zero renders as a real
        holding worth nothing, which is worse than an error."""
        del portfolio_payload["positions"][0][missing]
        fake_backend.json("portfolio", portfolio_payload)
        with pytest.raises(ContractViolationError, match=missing):
            await portfolio_tools.get_portfolio_positions("u_123")

    async def test_positions_must_be_a_list(self, fake_backend, portfolio_payload):
        portfolio_payload["positions"] = {"THYAO": {}}
        fake_backend.json("portfolio", portfolio_payload)
        with pytest.raises(ContractViolationError, match="must be a list"):
            await portfolio_tools.get_portfolio_positions("u_123")


# ==========================================================================
# Zero-cost edge case
# ==========================================================================
class TestZeroCostBasis:
    async def test_zero_cost_basis_yields_zero_pct_not_infinity(
        self, fake_backend, portfolio_payload
    ):
        """A gifted or fully written-down position has cost_basis 0. Returning
        0.0 beats propagating inf into a table a user reads."""
        portfolio_payload["positions"] = [{
            "symbol": "FREE", "quantity": 100.0, "avg_cost": 0.0,
            "last_price": 10.0, "market_value": 1000.0, "cost_basis": 0.0,
        }]
        fake_backend.json("portfolio", portfolio_payload)
        position = (await portfolio_tools.get_portfolio_positions("u_123"))["positions"][0]
        assert position["unrealized_pnl_pct"] == 0.0
        assert position["unrealized_pnl"] == 1000.0

    async def test_negative_pnl_is_reported_as_negative(
        self, fake_backend, portfolio_payload
    ):
        portfolio_payload["positions"] = [{
            "symbol": "LOSS", "quantity": 100.0, "avg_cost": 200.0,
            "last_price": 150.0, "market_value": 15000.0, "cost_basis": 20000.0,
        }]
        fake_backend.json("portfolio", portfolio_payload)
        position = (await portfolio_tools.get_portfolio_positions("u_123"))["positions"][0]
        assert position["unrealized_pnl"] == -5000.0
        assert position["unrealized_pnl_pct"] == pytest.approx(-0.25)


# ==========================================================================
# Failure propagation
# ==========================================================================
class TestFailures:
    async def test_unauthorized_raises_and_does_not_degrade(self, fake_backend):
        """Never retry, never fall back to cached data."""
        fake_backend.status("portfolio", 403)
        with pytest.raises(AuthorizationError):
            await portfolio_tools.get_portfolio_positions("u_not_entitled")
        assert fake_backend.attempts == 1

    async def test_custodian_outage_raises_after_the_retry(self, fake_backend):
        fake_backend.status("portfolio", 503)
        with pytest.raises(UpstreamUnavailableError):
            await portfolio_tools.get_portfolio_positions("u_123")
        assert fake_backend.attempts == 2

    async def test_unknown_user_raises_invalid_input(self, fake_backend):
        fake_backend.status("portfolio", 404)
        with pytest.raises(InvalidInputError):
            await portfolio_tools.get_portfolio_positions("u_ghost")

    async def test_timeout_raises_upstream_unavailable(self, fake_backend):
        import httpx

        fake_backend.fail("portfolio", httpx.ReadTimeout("slow custodian"))
        with pytest.raises(UpstreamUnavailableError):
            await portfolio_tools.get_portfolio_positions("u_123")


# ==========================================================================
# Registration
# ==========================================================================
class TestRegistration:
    async def test_register_attaches_the_tool(self, mocker):
        fake_mcp = mocker.MagicMock()
        portfolio_tools.register(fake_mcp)
        fake_mcp.tool.assert_called_once_with()
        fake_mcp.tool.return_value.assert_called_once_with(
            portfolio_tools.get_portfolio_positions
        )

    async def test_the_tool_is_a_coroutine_function(self):
        """FastMCP awaits it; a sync function here would block the event loop
        for the duration of every custodian call."""
        import inspect

        assert inspect.iscoroutinefunction(portfolio_tools.get_portfolio_positions)


class TestCashInTotals:
    """Contract v2.3. Before it, the portfolio tool exposed only position
    values, so the assistant answered "how much money do I have" with the
    market value of the holdings — or said the figure was not in its data."""

    @pytest.mark.asyncio
    async def test_cash_and_total_value_are_carried(self, fake_backend, portfolio_payload):
        portfolio_payload["totals"]["cash_balance"] = 22142.58
        portfolio_payload["totals"]["total_value"] = 1088042.52
        fake_backend.json("portfolio", portfolio_payload)
        totals = (await portfolio_tools.get_portfolio_positions("u_123"))["totals"]
        assert totals["cash_balance"] == pytest.approx(22142.58)
        assert totals["total_value"] == pytest.approx(1088042.52)

    @pytest.mark.asyncio
    async def test_an_unknown_balance_stays_none_rather_than_zero(
        self, fake_backend, portfolio_payload
    ):
        """A zero balance is a claim, and the wrong one: it tells the user
        they have no money when the truth is that we could not look."""
        portfolio_payload["totals"]["cash_balance"] = None
        fake_backend.json("portfolio", portfolio_payload)
        totals = (await portfolio_tools.get_portfolio_positions("u_123"))["totals"]
        assert totals["cash_balance"] is None

    @pytest.mark.asyncio
    async def test_an_absent_balance_is_not_a_contract_violation(
        self, fake_backend, portfolio_payload
    ):
        """Unlike the position totals, cash may legitimately be missing."""
        portfolio_payload["totals"].pop("cash_balance", None)
        fake_backend.json("portfolio", portfolio_payload)
        totals = (await portfolio_tools.get_portfolio_positions("u_123"))["totals"]
        assert totals["cash_balance"] is None

    @pytest.mark.asyncio
    async def test_a_missing_position_total_is_still_a_violation(
        self, fake_backend, portfolio_payload
    ):
        """The relaxation applies to cash only."""
        from backend_client import ContractViolationError

        portfolio_payload["totals"].pop("total_market_value")
        fake_backend.json("portfolio", portfolio_payload)
        with pytest.raises(ContractViolationError):
            await portfolio_tools.get_portfolio_positions("u_123")


class TestNullDefaults:
    """A model that emits `null` for an optional parameter must not kill the call.

    Observed in production: the planner sent `valuation_mode: null` for an
    ordinary "portföyümü göstersene", the bare `str` annotation rejected it
    before the tool ran, and the user was told
    "portföy verilerinize ulaşamadım" — as though the backend were down.
    A null means "no preference", which is exactly what the default is for.
    """

    async def test_null_valuation_mode_falls_back_to_the_default(self, fake_backend, portfolio_payload):
        fake_backend.json("portfolio", portfolio_payload)
        payload = await portfolio_tools.get_portfolio_positions("u_123", valuation_mode=None)
        assert payload["positions"]
        assert "valuation_mode=LAST_CLOSE" in str(fake_backend.last.url)

    async def test_null_base_currency_falls_back_to_the_default(self, fake_backend, portfolio_payload):
        fake_backend.json("portfolio", portfolio_payload)
        await portfolio_tools.get_portfolio_positions("u_123", base_currency=None)
        assert "base_currency=TRY" in str(fake_backend.last.url)
