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


# ==========================================================================
# get_portfolio_technicals — contract v2.12
# ==========================================================================
"""Aynı okuma, her POZİSYON için, artı tek bir toplam cümlesi.

Korunan asıl ayrım SAYI ile DEĞER. Üç pozisyonun ikisinin ortalamasının
altında olması ile portföy değerinin %95'inin altında olması farklı iddialar
ve zıt yönü gösterebilirler; ölçülen test portföyünde tam olarak öyle. Tek bir
yüzde vermek hangisinin kastedildiğini okunamaz yapardı, toplamı modele
hesaplatmak ise her turda başka bir sayı üretirdi.
"""

PORTFOLIO_KEYS = {"base_currency", "positions", "summary", "unconvertible"}
ROW_KEYS = {"symbol", "name", "currency", "trend", "signals", "narrative"}
SUMMARY_KEYS = {
    "position_count", "measured_count", "unmeasured_symbols", "by_trend",
    "below_sma_50", "above_sma_50", "weight_below_sma_50", "statement",
}

AGGREGATE_TR = (
    "3 pozisyonunuzun 2'si 50 günlük ortalamasının altında "
    "(portföy değerinin %95,1'i); 1'i yükseliş eğiliminde, 2'si düşüş eğiliminde."
)


def portfolio_body(**overrides):
    payload = {
        "base_currency": "TRY",
        "positions": [
            {"symbol": "AKBNK", "name": "Akbank T.A.Ş.", "currency": "TRY",
             "signals": body()["signals"], "narrative": NARRATIVE},
        ],
        "summary": {
            "position_count": 3, "measured_count": 3,
            "unmeasured_symbols": [],
            "by_trend": {"UPTREND": 1, "DOWNTREND": 2, "SIDEWAYS": 0},
            "below_sma_50": 2, "above_sma_50": 1,
            "weight_below_sma_50": 0.9508728745384665,
            "statement": AGGREGATE_TR,
        },
        "unconvertible": [],
    }
    payload.update(overrides)
    return payload


class TestPortfolioContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v212_exactly(self, fake_backend):
        fake_backend.json("portfolio_technical", portfolio_body())
        out = await technical_tools.get_portfolio_technicals("u_1")
        assert set(out) == PORTFOLIO_KEYS

    @pytest.mark.asyncio
    async def test_row_and_summary_keys_match_v212_exactly(self, fake_backend):
        fake_backend.json("portfolio_technical", portfolio_body())
        out = await technical_tools.get_portfolio_technicals("u_1")
        assert set(out["positions"][0]) == ROW_KEYS
        assert set(out["summary"]) == SUMMARY_KEYS
        assert set(out["positions"][0]["signals"]) == SIGNAL_KEYS

    @pytest.mark.asyncio
    async def test_the_user_travels_in_the_path(self, fake_backend):
        fake_backend.json("portfolio_technical", portfolio_body())
        await technical_tools.get_portfolio_technicals("u_42")
        assert "/market/portfolio/technical/u_42" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_count_and_weight_both_survive_and_are_not_merged(self, fake_backend):
        fake_backend.json("portfolio_technical", portfolio_body())
        summary = (await technical_tools.get_portfolio_technicals("u_1"))["summary"]
        assert (summary["below_sma_50"], summary["above_sma_50"]) == (2, 1)
        assert summary["weight_below_sma_50"] == pytest.approx(0.9509, abs=1e-4)

    @pytest.mark.asyncio
    async def test_a_missing_summary_is_a_contract_violation(self, fake_backend):
        """Boş bir özete düşürülmezdi: ajan o zaman ölçülmüş bir portföy için
        "eğilim çıkarılamadı" derdi."""
        fake_backend.json("portfolio_technical", {"positions": []})
        with pytest.raises(ContractViolationError):
            await technical_tools.get_portfolio_technicals("u_1")

    @pytest.mark.asyncio
    async def test_a_non_object_summary_is_refused(self, fake_backend):
        fake_backend.json("portfolio_technical", portfolio_body(summary=["2", "1"]))
        with pytest.raises(ContractViolationError):
            await technical_tools.get_portfolio_technicals("u_1")

    @pytest.mark.asyncio
    async def test_a_non_object_position_is_refused(self, fake_backend):
        fake_backend.json("portfolio_technical", portfolio_body(positions=["AKBNK"]))
        with pytest.raises(ContractViolationError):
            await technical_tools.get_portfolio_technicals("u_1")

    @pytest.mark.asyncio
    async def test_a_position_without_signals_is_refused(self, fake_backend):
        fake_backend.json(
            "portfolio_technical", portfolio_body(positions=[{"symbol": "AKBNK"}])
        )
        with pytest.raises(ContractViolationError):
            await technical_tools.get_portfolio_technicals("u_1")

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises_rather_than_inventing_a_posture(
        self, fake_backend, no_sleep
    ):
        fake_backend.fail("portfolio_technical")
        with pytest.raises(UpstreamUnavailableError):
            await technical_tools.get_portfolio_technicals("u_1")


class TestPortfolioAbsence:
    @pytest.mark.asyncio
    async def test_an_unknown_weight_stays_null_rather_than_zero(self, fake_backend):
        """0.0, "hiçbiri ortalamasının altında değil" diye okunur -- ağırlığın
        hesaplanamamış olmasının tam tersi."""
        summary = portfolio_body()["summary"]
        summary["weight_below_sma_50"] = None
        fake_backend.json("portfolio_technical", portfolio_body(summary=summary))
        out = await technical_tools.get_portfolio_technicals("u_1")
        assert out["summary"]["weight_below_sma_50"] is None

    @pytest.mark.asyncio
    async def test_an_unmeasured_holding_is_named_and_has_no_trend(self, fake_backend):
        summary = portfolio_body()["summary"]
        summary["unmeasured_symbols"] = ["YENI"]
        row = {"symbol": "YENI", "signals": {"trend": None}, "narrative": None}
        fake_backend.json(
            "portfolio_technical", portfolio_body(summary=summary, positions=[row])
        )
        out = await technical_tools.get_portfolio_technicals("u_1")
        assert out["summary"]["unmeasured_symbols"] == ["YENI"]
        assert out["positions"][0]["trend"] == "UNKNOWN"
        assert out["positions"][0]["narrative"] is None

    @pytest.mark.asyncio
    async def test_an_unconvertible_holding_is_carried_not_dropped(self, fake_backend):
        """Ölçülüyor, yalnızca ağırlığı bilinmiyor. Sessizce düşürmek,
        portföyün bir kısmını yok saymak olurdu."""
        fake_backend.json("portfolio_technical", portfolio_body(unconvertible=["AAPL"]))
        out = await technical_tools.get_portfolio_technicals("u_1")
        assert out["unconvertible"] == ["AAPL"]

    @pytest.mark.asyncio
    async def test_a_row_without_a_name_falls_back_to_its_symbol(self, fake_backend):
        row = {"symbol": "AKBNK", "signals": body()["signals"]}
        fake_backend.json("portfolio_technical", portfolio_body(positions=[row]))
        out = await technical_tools.get_portfolio_technicals("u_1")
        assert out["positions"][0]["name"] == "AKBNK"
        assert out["positions"][0]["currency"] == "TRY"

    @pytest.mark.asyncio
    async def test_an_empty_portfolio_is_a_body_not_an_error(self, fake_backend):
        summary = portfolio_body()["summary"]
        summary.update({"position_count": 0, "measured_count": 0, "statement": None,
                        "by_trend": {}, "below_sma_50": 0, "above_sma_50": 0})
        fake_backend.json(
            "portfolio_technical", portfolio_body(positions=[], summary=summary)
        )
        out = await technical_tools.get_portfolio_technicals("u_1")
        assert out["positions"] == []
        assert out["summary"]["statement"] is None

    @pytest.mark.asyncio
    async def test_missing_counts_default_to_the_measured_shape(self, fake_backend):
        """Backend bir alanı düşürürse anahtar hayatta kalır: `summary["..."]`
        okuyan bir tüketici KeyError yerine sayı görür."""
        fake_backend.json("portfolio_technical", portfolio_body(summary={}))
        summary = (await technical_tools.get_portfolio_technicals("u_1"))["summary"]
        assert summary["position_count"] == 1
        assert summary["by_trend"] == {}
        assert summary["statement"] is None


class TestPortfolioRegistration:
    def test_both_technical_tools_are_attached(self):
        registered = []
        technical_tools.register(
            type("FakeMCP", (), {"tool": lambda self: registered.append})()
        )
        assert registered == [
            technical_tools.get_technical_signals,
            technical_tools.get_portfolio_technicals,
        ]
