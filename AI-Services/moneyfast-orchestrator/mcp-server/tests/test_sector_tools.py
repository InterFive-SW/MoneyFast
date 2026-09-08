"""`get_sector_map` — sözleşme v2.25.

Bu aracın kapattığı boşluk şuydu: sektör backend'de ölçülü duruyordu ama
ajana hiç ulaşmıyordu, dolayısıyla bir sektör sorusuna verilen cevap ya
yoktu ya da modelin kendi bildiğinden geliyordu. İkincisi ölçülmüş sektörle
uydurulmuş sektörü ayırt edilemez yapar.

Sabitlenen iki şey: **eksik sektör doldurulmuyor** (ölçülmüş bir boşluk) ve
**bin satırlık düz harita yazara gitmiyor** (okumadığı bir yük).
"""

from __future__ import annotations

import pytest

import sector_tools
from backend_client import ContractViolationError, UpstreamUnavailableError

pytestmark = pytest.mark.asyncio

BODY = {
    "symbols": {"AKBNK": "Financial Services", "THYAO": "Industrials"},
    "sectors": [
        {"sector": "Financial Services", "symbols": ["AKBNK", "GARAN"]},
        {"sector": "Industrials", "symbols": ["THYAO"]},
    ],
    "unclassified": 14,
}


class TestContract:
    async def test_top_level_keys_match_v225_exactly(self, fake_backend):
        fake_backend.json("sectors", BODY)
        payload = await sector_tools.get_sector_map()
        assert set(payload) == {"sectors", "unclassified"}

    async def test_the_flat_symbol_map_never_reaches_the_writer(self, fake_backend):
        """Bin satırlık bir eşleme, yazarın hiç okumadığı bir token yükü."""
        fake_backend.json("sectors", BODY)
        payload = await sector_tools.get_sector_map()
        assert "symbols" not in payload

    async def test_the_unclassified_count_is_carried(self, fake_backend):
        """Neyi kaçırdığını söylemeyen bir harita, tam bir harita gibi
        okunur."""
        fake_backend.json("sectors", BODY)
        assert (await sector_tools.get_sector_map())["unclassified"] == 14

    async def test_a_sector_filter_travels(self, fake_backend):
        fake_backend.json("sectors", BODY)
        await sector_tools.get_sector_map("Financial Services")
        assert "sector=Financial" in str(fake_backend.last.url)

    async def test_no_filter_sends_no_parameter(self, fake_backend):
        fake_backend.json("sectors", BODY)
        await sector_tools.get_sector_map()
        assert "sector=" not in str(fake_backend.last.url)

    async def test_a_body_without_the_count_is_refused(self, fake_backend):
        """Sayısı olmayan bir gövde, kapsamanın hiç ölçülmediği bir
        gövdeden ayırt edilemez."""
        fake_backend.json("sectors", {"sectors": []})
        with pytest.raises(ContractViolationError):
            await sector_tools.get_sector_map()

    async def test_a_non_object_sector_is_refused(self, fake_backend):
        fake_backend.json("sectors", {"sectors": ["Bankacılık"], "unclassified": 0})
        with pytest.raises(ContractViolationError):
            await sector_tools.get_sector_map()

    async def test_a_large_sector_is_capped_and_says_how_many_were_left(
        self, fake_backend
    ):
        """Ölçüldü: süzgeçsiz yanıt 31 KB ve en kalabalık sektörde 170 sembol
        var; tek bir sohbet turu dakikalık token sınırını aşıyor ve kullanıcı
        "veri tek seferde işleyebileceğimden büyük çıktı" cevabı alıyordu."""
        big = [f"S{index}" for index in range(170)]
        fake_backend.json("sectors", {
            "sectors": [{"sector": "Industrials", "symbols": big}],
            "unclassified": 0,
        })
        row = (await sector_tools.get_sector_map())["sectors"][0]
        assert len(row["symbols"]) == sector_tools.MAX_SYMBOLS_PER_SECTOR
        assert row["truncated"] == 170 - sector_tools.MAX_SYMBOLS_PER_SECTOR

    async def test_an_uncapped_sector_reports_zero_truncated(self, fake_backend):
        """Alanın yokluğu ile sıfır olması aynı şey değil: ilki "kırpılmadı
        mı, yoksa sayılmadı mı" sorusunu açık bırakırdı."""
        fake_backend.json("sectors", BODY)
        assert (await sector_tools.get_sector_map())["sectors"][0]["truncated"] == 0

    async def test_a_sector_without_symbols_is_refused(self, fake_backend):
        fake_backend.json(
            "sectors", {"sectors": [{"sector": "X"}], "unclassified": 0}
        )
        with pytest.raises(ContractViolationError):
            await sector_tools.get_sector_map()

    async def test_an_unreachable_backend_raises(self, fake_backend):
        """Hangi şirketin hangi sektörde olduğu, tam olarak bir modelin yanlış
        hatırladığı türden bir olgu."""
        fake_backend.fail("sectors")
        with pytest.raises(UpstreamUnavailableError):
            await sector_tools.get_sector_map()

    async def test_an_empty_map_is_a_valid_answer(self, fake_backend):
        fake_backend.json("sectors", {"sectors": [], "unclassified": 1011})
        payload = await sector_tools.get_sector_map()
        assert payload["sectors"] == [] and payload["unclassified"] == 1011


class TestDocstring:
    async def test_the_membership_is_not_the_models(self):
        doc = " ".join(sector_tools.get_sector_map.__doc__.split())
        assert "The membership here is the provider's, not yours" in doc
        assert "a silently shortened membership" in doc
        assert "NEVER add a company to a sector because you believe" in doc

    async def test_an_absent_instrument_is_a_measured_gap(self):
        doc = " ".join(sector_tools.get_sector_map.__doc__.split())
        assert "That is a measured gap; do not fill it" in doc

    async def test_a_sector_is_not_a_reason_to_expect_anything(self):
        doc = " ".join(sector_tools.get_sector_map.__doc__.split())
        assert "A sector membership is not a reason to expect anything" in doc
        assert "Do NOT rank sectors" in doc


class TestRegistration:
    async def test_register_attaches_the_tool(self):
        registered = []
        sector_tools.register(
            type("FakeMCP", (), {"tool": lambda self: registered.append})()
        )
        assert registered == [sector_tools.get_sector_map]
