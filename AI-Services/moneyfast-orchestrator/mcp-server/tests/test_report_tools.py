"""`get_portfolio_report` — sözleşme v2.18.

Doküman raporu adıyla istiyor: "'Detaylı Rapor Oluştur' butonlarıyla tek tıkla
... kapsamlı analiz raporu alınır."

Bu dosyanın koruduğu iki şey:

CÜMLELER AKTARILIR, YENİDEN YAZILMAZ. Bölüm metinleri backend'de bir kez
kuruluyor ve ekran, PDF ile bu araç aynı metni okuyor; üç yüzeyin ayrışması
bu depoda defalarca ölçüldü.

SATIRLAR TAŞINMAZ. Risk turunun sentez gövdesi sağlayıcının 8.000 token'lık
istek sınırına zaten dayanmış durumda ve altı bölümün satırları birden onu
aşar.
"""

from __future__ import annotations

import pytest

import report_tools as rt
from backend_client import (
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)

pytestmark = pytest.mark.asyncio

FULL = {
    "generated_at": "2026-09-03T08:00:00Z",
    "currency_code": "TRY",
    "as_of": "2026-09-03T07:42:00Z",
    "is_delayed": True,
    "delay_minutes": 18,
    "sections": [
        {"key": "overview", "title": "Genel bakış",
         "summary": "Toplam varlığınız 24.404,97 TRY.",
         "lines": ["Toplam varlık: 24.404,97 TRY", "Nakit: 1.369,26 TRY"],
         "rows": [{"label": "Nakit", "amount": 1369.26}]},
        {"key": "cash_flow", "title": "Nakit akışı",
         "summary": "Bu hesap için bankacılık hareketi kaydı bulunmuyor.",
         "lines": [], "rows": []},
    ],
}


class TestRequest:
    async def test_it_reads_the_user_scoped_path(self, fake_backend):
        fake_backend.json("report", FULL)
        await rt.get_portfolio_report("u_123")
        assert fake_backend.last.method == "GET"
        assert "/analytics/report/u_123" in str(fake_backend.last.url)

    @pytest.mark.parametrize("bad", ["", "   ", None])
    async def test_a_missing_user_is_refused_before_the_network(self, fake_backend, bad):
        with pytest.raises(InvalidInputError):
            await rt.get_portfolio_report(bad)
        assert fake_backend.attempts == 0


class TestPayload:
    async def test_the_top_level_shape_is_exact(self, fake_backend):
        fake_backend.json("report", FULL)
        got = await rt.get_portfolio_report("u_123")
        assert set(got) == {
            "generated_at", "currency_code", "as_of", "is_delayed",
            "delay_minutes", "sections",
        }

    async def test_the_sentences_survive_verbatim(self, fake_backend):
        fake_backend.json("report", FULL)
        got = await rt.get_portfolio_report("u_123")
        assert got["sections"][0]["summary"] == "Toplam varlığınız 24.404,97 TRY."

    async def test_lines_and_rows_are_left_behind(self, fake_backend):
        """Ekranın ve PDF'in işi. Altı bölümün satırları birden sentez
        gövdesini sağlayıcı sınırının üstüne çıkarır -- ölçülmüş bir sınır."""
        fake_backend.json("report", FULL)
        got = await rt.get_portfolio_report("u_123")
        assert set(got["sections"][0]) == {"key", "title", "summary"}

    async def test_a_section_without_data_still_travels(self, fake_backend):
        """Düşen bir bölüm, ölçümün yokluğunu değil raporun bozukluğunu
        düşündürür. Ölçüldü: 23 kullanıcının 3'ünde bankacılık kaydı var."""
        fake_backend.json("report", FULL)
        got = await rt.get_portfolio_report("u_123")
        assert [s["key"] for s in got["sections"]] == ["overview", "cash_flow"]
        assert got["sections"][1]["summary"]

    async def test_section_order_is_preserved(self, fake_backend):
        fake_backend.json("report", {
            **FULL, "sections": list(reversed(FULL["sections"])),
        })
        got = await rt.get_portfolio_report("u_123")
        assert [s["key"] for s in got["sections"]] == ["cash_flow", "overview"]

    async def test_a_missing_summary_is_an_empty_string_not_a_crash(self, fake_backend):
        fake_backend.json("report", {
            **FULL, "sections": [{"key": "x", "title": "X"}],
        })
        got = await rt.get_portfolio_report("u_123")
        assert got["sections"][0]["summary"] == ""


class TestFreshness:
    """Belgenin üretildiği an ile içindeki fiyatların ait olduğu an FARKLI.

    Rapor, sistemin gecikmeyi söylemeyen tek yüzeyi olmamalı.
    """

    async def test_the_price_time_is_carried_separately(self, fake_backend):
        fake_backend.json("report", FULL)
        got = await rt.get_portfolio_report("u_123")
        assert got["as_of"] == "2026-09-03T07:42:00Z"
        assert got["generated_at"] == "2026-09-03T08:00:00Z"
        assert got["delay_minutes"] == 18

    async def test_a_backend_without_it_falls_back_to_the_build_time(
        self, fake_backend
    ):
        """Uydurmuyor: alan gelmezse belge zamanı taşınıyor ve gecikme
        sıfır -- bilinmeyen bir gecikmeyi bir sayıya çevirmek, olmayan bir
        tazelik iddiası olurdu."""
        fake_backend.json("report", {
            k: v for k, v in FULL.items()
            if k not in ("as_of", "is_delayed", "delay_minutes")
        })
        got = await rt.get_portfolio_report("u_123")
        assert got["as_of"] == FULL["generated_at"]
        assert got["is_delayed"] is False and got["delay_minutes"] == 0


class TestContractGuards:
    @pytest.mark.parametrize("missing", ["generated_at", "sections"])
    async def test_a_missing_top_level_key_is_a_violation(self, fake_backend, missing):
        fake_backend.json("report", {k: v for k, v in FULL.items() if k != missing})
        with pytest.raises(ContractViolationError):
            await rt.get_portfolio_report("u_123")

    async def test_a_non_object_section_is_a_violation(self, fake_backend):
        fake_backend.json("report", {**FULL, "sections": ["Genel bakış"]})
        with pytest.raises(ContractViolationError):
            await rt.get_portfolio_report("u_123")

    async def test_a_section_without_a_key_is_a_violation(self, fake_backend):
        fake_backend.json("report", {**FULL, "sections": [{"title": "X"}]})
        with pytest.raises(ContractViolationError):
            await rt.get_portfolio_report("u_123")

    async def test_an_unreachable_backend_raises(self, fake_backend):
        fake_backend.fail("report")
        with pytest.raises(UpstreamUnavailableError):
            await rt.get_portfolio_report("u_123")


class TestContractWording:
    def test_the_sentences_must_be_relayed_not_reworded(self):
        doc = " ".join(rt.get_portfolio_report.__doc__.split())
        assert "Relay them; do not reword, reorder or merge them" in doc

    def test_an_empty_section_must_not_be_dropped(self):
        doc = " ".join(rt.get_portfolio_report.__doc__.split())
        assert "a missing section reads as a broken report" in doc

    def test_the_build_time_must_not_be_used_to_date_the_prices(self):
        doc = " ".join(rt.get_portfolio_report.__doc__.split())
        assert "Do NOT date the figures with `generated_at`" in doc

    def test_the_score_direction_is_stated(self):
        """100 sakin. Ters okunursa en güvenli portföy en riskli görünür."""
        doc = " ".join(rt.get_portfolio_report.__doc__.split())
        assert "100 is CALM" in doc

    def test_the_report_describes_rather_than_advises(self):
        doc = " ".join(rt.get_portfolio_report.__doc__.split())
        assert "This report DESCRIBES; it does not advise" in doc


class TestRegistration:
    def test_the_tool_is_attached(self):
        attached = []

        class FakeMCP:
            def tool(self):
                return lambda fn: attached.append(fn.__name__) or fn

        rt.register(FakeMCP())
        assert attached == ["get_portfolio_report"]
