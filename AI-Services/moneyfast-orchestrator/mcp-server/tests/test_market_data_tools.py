"""Unit tests for market_data_tools, added in contract v2.2.

The tool exists because v2.1 could not answer "THYAO kaç lira?" for an
instrument the user does not own.

The assertions that matter most are about ABSENCE. A null fundamental means
the provider does not publish it; rendering it as 0 would put a company with
no published earnings at the top of a "lowest P/E" list, and dropping the
instrument entirely would hide the gap instead of reporting it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

import market_data_tools
from backend_client import ContractViolationError, InvalidInputError

TOOL_KEYS = {
    "as_of", "source", "is_delayed", "delay_minutes",
    "instruments", "filters_echo", "warnings",
}
#: v2.6 adds `volume`. Additive: the field was stored on every quote row and
#: projected by nothing, so a screening table's turnover column was
#: structurally empty rather than occasionally unknown.
INSTRUMENT_KEYS = {
    "symbol", "name", "market", "currency", "price", "change", "change_percent",
    "volume", "pe_ratio", "pb_ratio", "market_cap", "dividend_yield", "sector",
    "week52_high", "week52_low", "as_of",
}

NOW = datetime.now(timezone.utc)


def instrument(**overrides):
    row = {
        "symbol": "THYAO",
        "name": "Türk Hava Yolları",
        "market": "BIST",
        "currency": "TRY",
        "price": 304.0,
        "change": 3.0,
        "change_percent": 1.0,
        "market_timestamp": NOW.isoformat(),
        "pe_ratio": None,
        "pb_ratio": 18.99,
        "market_cap": 414086529024,
        "dividend_yield": 2.29,
        "sector": "Industrials",
        "week52_high": 355.5,
        "week52_low": 210.0,
    }
    row.update(overrides)
    return row


class TestContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v22_exactly(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [instrument()]}))
        payload = await market_data_tools.get_market_data(symbols=["THYAO"])
        assert set(payload) == TOOL_KEYS

    @pytest.mark.asyncio
    async def test_instrument_keys_match_v22_exactly(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [instrument()]}))
        payload = await market_data_tools.get_market_data(symbols=["THYAO"])
        assert set(payload["instruments"][0]) == INSTRUMENT_KEYS

    @pytest.mark.asyncio
    async def test_hits_the_instruments_endpoint(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(symbols=["THYAO"])
        assert "/market/instruments" in str(fake_backend.last.url)


class TestMissingFundamentals:
    """The behaviour a valuation screen lives or dies on."""

    @pytest.mark.asyncio
    async def test_null_ratio_stays_null(self, fake_backend):
        """THYAO genuinely has no trailing P/E from this provider. Rendering
        that as 0 would make it the cheapest stock on any screen."""
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [instrument()]}))
        payload = await market_data_tools.get_market_data(symbols=["THYAO"])
        assert payload["instruments"][0]["pe_ratio"] is None

    @pytest.mark.asyncio
    async def test_instrument_with_no_fundamentals_is_still_returned(self, fake_backend):
        """Dropping it would hide the gap rather than report it."""
        bare = instrument(pb_ratio=None, market_cap=None, sector=None,
                          dividend_yield=None, week52_high=None, week52_low=None)
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [bare]}))
        payload = await market_data_tools.get_market_data(symbols=["THYAO"])
        assert len(payload["instruments"]) == 1
        assert payload["instruments"][0]["price"] == 304.0

    @pytest.mark.asyncio
    async def test_unknown_change_is_null_not_zero(self, fake_backend):
        """Zero change asserts the price did not move. Unknown is not that."""
        fake_backend.set(
            "instruments", httpx.Response(200, json={"instruments": [instrument(change=None, change_percent=None)]})
        )
        payload = await market_data_tools.get_market_data(symbols=["THYAO"])
        assert payload["instruments"][0]["change_percent"] is None

    @pytest.mark.asyncio
    async def test_a_fundamental_filter_warns_that_gaps_were_excluded(self, fake_backend):
        """"P/E below 10" must not silently mean "P/E below 10, or unknown",
        and the user should be told which reading they got."""
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        payload = await market_data_tools.get_market_data(filters={"max_pe": 10})
        assert any("bilinmeyen" in w for w in payload["warnings"])


class TestFreshness:
    @pytest.mark.asyncio
    async def test_as_of_is_the_oldest_quote_in_the_set(self, fake_backend):
        """A payload is only as current as its least current figure. Taking
        the newest would let one fresh instrument vouch for twenty stale ones."""
        old = (NOW - timedelta(minutes=45)).isoformat()
        fake_backend.set(
            "instruments",
            httpx.Response(200, json={"instruments": [instrument(), instrument(symbol="ASELS", market_timestamp=old)]}),
        )
        payload = await market_data_tools.get_market_data()
        assert payload["as_of"] == old
        assert payload["delay_minutes"] >= 44
        assert payload["is_delayed"] is True

    @pytest.mark.asyncio
    async def test_empty_result_does_not_claim_freshness(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        payload = await market_data_tools.get_market_data()
        assert payload["as_of"] == ""
        assert payload["instruments"] == []

    @pytest.mark.asyncio
    async def test_a_timestamp_without_a_zone_is_read_as_utc(self, fake_backend):
        """Postgres hands back naive timestamps when a column was declared
        without a zone. Reading one as local time would shift the reported
        delay by the machine's UTC offset — three hours, here."""
        naive = (NOW - timedelta(minutes=20)).replace(tzinfo=None).isoformat()
        fake_backend.set(
            "instruments",
            httpx.Response(200, json={"instruments": [instrument(market_timestamp=naive)]}),
        )
        payload = await market_data_tools.get_market_data()
        # 20 dakikalık gözlem yaşı + sağlayıcının 15 dakikalık kendi gecikmesi.
        expected = 20 + market_data_tools.PROVIDER_DELAY_FLOOR_MINUTES
        assert expected - 1 <= payload["delay_minutes"] <= expected + 1


class TestFilters:
    @pytest.mark.asyncio
    async def test_recognised_filters_are_forwarded(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(filters={"max_pe": 10, "sector": "Industrials"})
        query = str(fake_backend.last.url)
        assert "max_pe=10" in query and "sector=Industrials" in query

    @pytest.mark.asyncio
    async def test_unknown_filter_is_rejected_not_dropped(self, fake_backend):
        """The model believes the filter applied; ignoring it turns "no
        matches" into a false statement about the market."""
        with pytest.raises(InvalidInputError, match="pe_growth"):
            await market_data_tools.get_market_data(filters={"pe_growth": 1})

    @pytest.mark.asyncio
    async def test_unknown_sort_is_rejected(self, fake_backend):
        with pytest.raises(InvalidInputError, match="sort_by"):
            await market_data_tools.get_market_data(sort_by="attractiveness")

    @pytest.mark.asyncio
    async def test_filters_are_echoed_back(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        payload = await market_data_tools.get_market_data(filters={"sector": "Technology"})
        assert payload["filters_echo"] == {"sector": "Technology"}


class TestTopK:
    @pytest.mark.asyncio
    async def test_clamped_to_the_documented_window(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(top_k=9999)
        assert f"limit={market_data_tools.MAX_TOP_K}" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_negative_top_k_becomes_one(self, fake_backend):
        """A negative bound would come back empty, which the orchestrator
        would report as "no instruments matched"."""
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(top_k=-5)
        assert "limit=1" in str(fake_backend.last.url)


class TestUnresolvedSymbols:
    @pytest.mark.asyncio
    async def test_a_symbol_that_came_back_empty_is_named(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [instrument()]}))
        payload = await market_data_tools.get_market_data(symbols=["THYAO", "NOTREAL"])
        assert any("NOTREAL" in w for w in payload["warnings"])

    @pytest.mark.asyncio
    async def test_provider_suffix_is_not_reported_as_missing(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [instrument()]}))
        payload = await market_data_tools.get_market_data(symbols=["THYAO.IS"])
        assert payload["warnings"] == []


class TestContractViolations:
    @pytest.mark.asyncio
    async def test_missing_instruments_key_is_refused(self, fake_backend):
        """An absent key is not an empty result. Defaulting it would report
        "no instruments matched" for a backend that malfunctioned."""
        fake_backend.set("instruments", httpx.Response(200, json={"rows": []}))
        with pytest.raises(ContractViolationError, match="instruments"):
            await market_data_tools.get_market_data()

    @pytest.mark.asyncio
    async def test_instrument_without_a_price_is_refused(self, fake_backend):
        """An instrument with no price is a gap, not a screening result;
        rendering it invites the reader to treat the blank as a number."""
        broken = instrument()
        del broken["price"]
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [broken]}))
        with pytest.raises(ContractViolationError, match="price"):
            await market_data_tools.get_market_data()

    @pytest.mark.asyncio
    async def test_non_object_instrument_is_refused(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": ["THYAO"]}))
        with pytest.raises(ContractViolationError):
            await market_data_tools.get_market_data()

    @pytest.mark.asyncio
    async def test_an_unparseable_timestamp_still_reports_the_provider_delay(self, fake_backend):
        """Failing to read the stamp means we do not know how stale our own
        copy is — it does not mean the feed became real time. Falling back to
        0 would let the agent present a delayed price as live, which the
        contract forbids."""
        fake_backend.set(
            "instruments", httpx.Response(200, json={"instruments": [instrument(market_timestamp="yesterday")]})
        )
        payload = await market_data_tools.get_market_data()
        assert payload["delay_minutes"] == market_data_tools.PROVIDER_DELAY_FLOOR_MINUTES
        assert payload["is_delayed"] is True

    @pytest.mark.asyncio
    async def test_the_observation_time_is_preferred_over_the_bar_stamp(self, fake_backend):
        """Günlük barlar seans açılışında damgalanır; tazeliği ondan ölçmek
        şu an çekilmiş bir fiyatı 12 saat eski gösteriyordu."""
        from datetime import timezone

        bar_open = NOW.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        fake_backend.set(
            "instruments",
            httpx.Response(200, json={"instruments": [instrument(
                market_timestamp=bar_open.isoformat(),
                received_at=(NOW - timedelta(minutes=2)).isoformat(),
            )]}),
        )
        payload = await market_data_tools.get_market_data()
        assert payload["delay_minutes"] < 30, "bar damgasından ölçülseydi saatlerce olurdu"

    @pytest.mark.asyncio
    async def test_a_blank_timestamp_reports_the_provider_delay_not_zero(self, fake_backend):
        """`require` boş bir alanı kabul eder (boş liste anlamlı bir cevaptır),
        dolayısıyla damgası boş bir satır gelebilir. Kendi tazeliğimizi
        ölçemesek de sağlayıcının gecikmesi ortadan kalkmaz."""
        fake_backend.set(
            "instruments",
            httpx.Response(200, json={"instruments": [instrument(market_timestamp="")]}),
        )
        payload = await market_data_tools.get_market_data()
        assert payload["delay_minutes"] == market_data_tools.PROVIDER_DELAY_FLOOR_MINUTES
        assert payload["is_delayed"] is True


def test_register_attaches_the_tool(mocker):
    fake_mcp = mocker.MagicMock()
    market_data_tools.register(fake_mcp)
    fake_mcp.tool.assert_called_once_with()
    fake_mcp.tool.return_value.assert_called_once_with(market_data_tools.get_market_data)


class TestExplicitNulls:
    """An LLM routinely names every parameter and passes null for the ones it
    has no opinion about. A signature that only accepts an int rejects that as
    a validation error, and the agent then tells the user it could not reach
    the data — which is exactly how "THYAO kaç lira?" failed while the
    filter-based screen worked.
    """

    @pytest.mark.asyncio
    async def test_a_null_top_k_falls_back_to_the_default(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [instrument()]}))
        payload = await market_data_tools.get_market_data(symbols=["THYAO"], top_k=None)
        assert payload["instruments"][0]["symbol"] == "THYAO"
        assert fake_backend.last.url.params["limit"] == str(market_data_tools.DEFAULT_TOP_K)

    @pytest.mark.asyncio
    async def test_every_optional_argument_may_be_null_at_once(self, fake_backend):
        """The shape a model sends when it wants a plain lookup."""
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": [instrument()]}))
        payload = await market_data_tools.get_market_data(
            symbols=["THYAO"], filters=None, top_k=None, sort_by=None
        )
        assert payload["instruments"][0]["price"] == 304.0

    @pytest.mark.asyncio
    async def test_an_explicit_top_k_still_wins(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(top_k=5)
        assert fake_backend.last.url.params["limit"] == "5"


class TestSortVocabulary:
    """The enum that broke "en çok kazandıranlar".

    The planner is now told the legal values, but models still paraphrase. A
    synonym is folded onto its canonical key; anything genuinely unreadable
    still raises, naming the permitted set so the caller can correct itself.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "written,canonical",
        [
            ("gainers", "change_percent"),
            ("top_gainers", "change_percent"),
            ("change_percent_desc", "change_percent"),
            ("-change_percent", "change_percent"),
            ("losers", "change_percent_asc"),
            ("top_losers", "change_percent_asc"),
            ("CHANGE_PERCENT", "change_percent"),
            ("  change_percent_asc  ", "change_percent_asc"),
        ],
    )
    async def test_a_paraphrased_sort_is_folded_onto_its_canonical_key(
        self, fake_backend, written, canonical
    ):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(sort_by=written)
        assert fake_backend.last.url.params["sort_by"] == canonical

    @pytest.mark.asyncio
    async def test_the_descending_and_ascending_keys_are_distinct(self, fake_backend):
        """Folding "losers" onto the descending key would answer a losers
        question with gainers — the failure this whole change exists to fix."""
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(sort_by="losers")
        assert fake_backend.last.url.params["sort_by"] == "change_percent_asc"

    @pytest.mark.asyncio
    async def test_an_unreadable_sort_still_raises_and_names_the_options(self, fake_backend):
        with pytest.raises(InvalidInputError) as excinfo:
            await market_data_tools.get_market_data(sort_by="by_vibes")
        message = str(excinfo.value)
        assert "by_vibes" in message
        assert "change_percent_asc" in message, "the error must name the allowed set"

    @pytest.mark.asyncio
    async def test_no_sort_stays_unset(self, fake_backend):
        fake_backend.set("instruments", httpx.Response(200, json={"instruments": []}))
        await market_data_tools.get_market_data(sort_by=None)
        assert fake_backend.last.url.params.get("sort_by", "") == ""
