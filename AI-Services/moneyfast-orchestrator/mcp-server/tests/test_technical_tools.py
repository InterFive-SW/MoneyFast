"""Unit tests for technical_tools, added in contract v2.10.

The tool exists because "AKBNK'ı yorumlar mısın" had nowhere to go. It was
routed to the news search, found nothing, and the assistant reported
"Akbank hakkında veri bulunamadı" -- for an instrument with a live price,
published fundamentals and roughly seven hundred daily bars.

The assertions that matter most are about ABSENCE and about RELAY. A null
indicator means the history is too short to compute it, which is a different
claim from zero; and the Turkish sentence is passed through rather than
regenerated, because the conditional reading and its caveat are one sentence.
"""

from __future__ import annotations

import httpx
import pytest

import technical_tools
from backend_client import ContractViolationError, UpstreamUnavailableError

TOOL_KEYS = {"symbol", "currency", "signals", "narrative"}

SIGNAL_KEYS = {
    "observations", "last_close",
    "sma_20", "sma_50", "sma_200",
    "pct_from_sma_20", "pct_from_sma_50", "pct_from_sma_200",
    "rsi_14",
    "week52_high", "week52_low", "week52_position_pct",
    "up_days_recent", "recent_window", "volume_vs_average",
    "annualised_volatility", "max_drawdown_pct",
    "trend",
}

NARRATIVE = (
    "AKBNK, 50 günlük ortalamasının %8,2 üzerinde; teknik olarak yükseliş "
    "eğiliminde. Bu görünüm sürdüğü sürece yükseliş eğiliminin devamı "
    "beklenebilir — ancak geçmiş fiyat hareketi geleceği belirlemez."
)


def body(**overrides):
    payload = {
        "symbol": "AKBNK",
        "currency": "TRY",
        "signals": {
            "observations": 252, "last_close": 64.2,
            "sma_20": 62.0, "sma_50": 59.3, "sma_200": 55.1,
            "pct_from_sma_20": 3.5, "pct_from_sma_50": 8.2,
            "pct_from_sma_200": 16.5,
            "rsi_14": 61.4,
            "week52_high": 70.0, "week52_low": 40.0,
            "week52_position_pct": 80.6,
            "up_days_recent": 14, "recent_window": 20,
            "volume_vs_average": 1.4,
            "annualised_volatility": 0.31, "max_drawdown_pct": -18.2,
            "trend": "UPTREND",
        },
        "narrative": NARRATIVE,
    }
    payload.update(overrides)
    return payload


class TestContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v210_exactly(self, fake_backend):
        fake_backend.json("technicals", body())
        payload = await technical_tools.get_technical_signals("AKBNK")
        assert set(payload) == TOOL_KEYS

    @pytest.mark.asyncio
    async def test_signal_keys_match_v210_exactly(self, fake_backend):
        fake_backend.json("technicals", body())
        payload = await technical_tools.get_technical_signals("AKBNK")
        assert set(payload["signals"]) == SIGNAL_KEYS

    @pytest.mark.asyncio
    async def test_it_asks_the_backend_for_that_symbol(self, fake_backend):
        fake_backend.json("technicals", body())
        await technical_tools.get_technical_signals("akbnk")
        request = fake_backend.requests[-1]
        assert "/market/technicals" in str(request.url)
        assert "symbol=akbnk" in str(request.url)

    @pytest.mark.asyncio
    async def test_a_missing_signals_block_is_a_contract_violation(self, fake_backend):
        """Not defaulted to an empty reading: the tool would then report "no
        trend" for a backend that simply changed shape."""
        fake_backend.json("technicals", {"symbol": "AKBNK", "currency": "TRY"})
        with pytest.raises(ContractViolationError):
            await technical_tools.get_technical_signals("AKBNK")

    @pytest.mark.asyncio
    async def test_a_non_object_response_is_a_contract_violation(self, fake_backend):
        fake_backend.json("technicals", ["not", "an", "object"])
        with pytest.raises(ContractViolationError):
            await technical_tools.get_technical_signals("AKBNK")

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises_rather_than_inventing_a_trend(
        self, fake_backend, no_sleep
    ):
        fake_backend.fail("technicals")
        with pytest.raises(UpstreamUnavailableError):
            await technical_tools.get_technical_signals("AKBNK")


class TestAbsence:
    @pytest.mark.asyncio
    async def test_a_null_indicator_stays_null(self, fake_backend):
        """A 30-bar instrument has NO 200-day average. Zero would read as
        "the price sits exactly on it", which is the opposite claim."""
        payload = body()
        payload["signals"]["sma_200"] = None
        payload["signals"]["pct_from_sma_200"] = None
        fake_backend.json("technicals", payload)

        out = await technical_tools.get_technical_signals("YENI")

        assert out["signals"]["sma_200"] is None
        assert out["signals"]["pct_from_sma_200"] is None

    @pytest.mark.asyncio
    async def test_a_field_the_backend_omits_is_null_not_absent(self, fake_backend):
        """The key survives even when the backend drops it, so a consumer
        reading `signals["rsi_14"]` gets None rather than a KeyError."""
        payload = body()
        del payload["signals"]["rsi_14"]
        fake_backend.json("technicals", payload)

        out = await technical_tools.get_technical_signals("AKBNK")

        assert out["signals"]["rsi_14"] is None
        assert set(out["signals"]) == SIGNAL_KEYS

    @pytest.mark.asyncio
    async def test_no_narrative_is_null_not_an_empty_string(self, fake_backend):
        """"" would be relayed as an empty paragraph; None makes the agent
        say the history is insufficient."""
        fake_backend.json("technicals", body(narrative=""))
        out = await technical_tools.get_technical_signals("YENI")
        assert out["narrative"] is None

    @pytest.mark.asyncio
    async def test_a_missing_currency_falls_back_rather_than_vanishing(
        self, fake_backend
    ):
        """A price without its unit is the bug this project has already had."""
        payload = body()
        del payload["currency"]
        fake_backend.json("technicals", payload)
        out = await technical_tools.get_technical_signals("AKBNK")
        assert out["currency"] == "TRY"


class TestRelay:
    @pytest.mark.asyncio
    async def test_the_sentence_is_passed_through_untouched(self, fake_backend):
        """The wording is computed backend-side precisely so it is not
        re-derived per turn."""
        fake_backend.json("technicals", body())
        out = await technical_tools.get_technical_signals("AKBNK")
        assert out["narrative"] == NARRATIVE

    @pytest.mark.asyncio
    async def test_the_caveat_travels_with_the_conditional_reading(
        self, fake_backend
    ):
        """Half this sentence is a forecast. The tool must never deliver the
        first clause without the second."""
        fake_backend.json("technicals", body())
        out = await technical_tools.get_technical_signals("AKBNK")
        assert "beklenebilir" in out["narrative"]
        assert "geleceği belirlemez" in out["narrative"]


class TestDocstringIsTheContract:
    """The docstring ships as the tool description, so it IS the instruction
    the model reads. Asserting on it pins the rules that keep the relayed
    sentence intact."""

    @staticmethod
    def _doc() -> str:
        """Wraps collapsed: the docstring is hard-wrapped at 88 columns, so a
        rule to assert on is routinely split across two lines."""
        return " ".join(technical_tools.get_technical_signals.__doc__.split())

    def test_it_tells_the_agent_to_relay_not_rewrite(self):
        doc = self._doc()
        assert "RELAY `narrative` as given" in doc
        assert "do NOT drop its closing caveat" in doc

    def test_it_says_what_null_means(self):
        doc = self._doc()
        assert "Null means the history is too short" in doc

    def test_it_forbids_naming_the_field_keys(self):
        """`rsi_14` reaching a user is the leak `sanitize` exists to catch;
        the docstring is the first line of that defence."""
        doc = self._doc()
        assert "Do NOT name the indicators by their field keys" in doc
