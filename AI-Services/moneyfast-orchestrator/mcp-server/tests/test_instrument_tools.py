"""`resolve_instruments` birim testleri — sözleşme v2.19.

Bu araç ölçülmüş bir hatanın karşılığı: kullanıcı "türk hava yolları ne
durumda yeni haberler var mı gündemde?" diye sordu ve cevapta kaynak olarak
ÜÇ EKGYO bildirimi listelendi. Yönlendirici `entities.company_names`
çıkarıyordu ama orkestratörde o alanı okuyan tek satır yoktu; adı sembole
çeviren hiçbir şey olmadığı için arama süzgeçsiz çalıştı.

Korunan iddialar:

* boş liste TAM bir cevap. "Bu sistemde böyle bir enstrüman yok" ölçülmüş bir
  sonuç, "böyle bir şirket yok" ise başka bir iddia -- evren BIST artı S&P 500
  ve Nasdaq-100, ve dışındaki bir şirket var olmayan bir şirket değil;
* sembolü OLMAYAN satır geçmez. Koda dönüşmeyen bir öneri başka hiçbir araca
  verilemiyor, ve boş dize verilse sessizce hiçbir şeyle eşleşirdi;
* fiyat YOK. `get_market_data` fiyatın tek kaynağı ve iki araçtan iki farklı
  fiyat çıkması mümkün olmamalı.
"""

from __future__ import annotations

import pytest

import instrument_tools
from backend_client import ContractViolationError, UpstreamUnavailableError

TOOL_KEYS = {"query", "instruments"}
ROW_KEYS = {"symbol", "name", "market", "currency"}


def body():
    """Backend'in `GET /market/search` yanıtı."""
    return [
        {
            "symbol": "THYAO",
            "name": "TÜRK HAVA YOLLARI A.O.",
            "market": "BIST",
            "currency": "TRY",
        }
    ]


class TestContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v219_exactly(self, fake_backend):
        fake_backend.json("instrument_search", body())
        payload = await instrument_tools.resolve_instruments("türk hava yolları")
        assert set(payload) == TOOL_KEYS

    @pytest.mark.asyncio
    async def test_row_keys_match_v219_exactly(self, fake_backend):
        fake_backend.json("instrument_search", body())
        payload = await instrument_tools.resolve_instruments("türk hava yolları")
        assert set(payload["instruments"][0]) == ROW_KEYS

    @pytest.mark.asyncio
    async def test_the_name_resolves_to_the_symbol(self, fake_backend):
        """Bu turun tamamı bu satır için var."""
        fake_backend.json("instrument_search", body())
        payload = await instrument_tools.resolve_instruments("türk hava yolları")
        assert payload["instruments"][0]["symbol"] == "THYAO"

    @pytest.mark.asyncio
    async def test_the_query_is_echoed_so_the_answer_can_name_it(self, fake_backend):
        fake_backend.json("instrument_search", body())
        payload = await instrument_tools.resolve_instruments("  şişe cam  ")
        assert payload["query"] == "şişe cam"

    @pytest.mark.asyncio
    async def test_it_carries_no_price(self, fake_backend):
        """`get_market_data` fiyatın tek kaynağı; iki araçtan iki farklı fiyat
        çıkması mümkün olmamalı."""
        fake_backend.json("instrument_search", [{**body()[0], "price": 294.5}])
        payload = await instrument_tools.resolve_instruments("thy")
        assert "price" not in payload["instruments"][0]


class TestRequest:
    @pytest.mark.asyncio
    async def test_the_query_travels_as_q(self, fake_backend):
        fake_backend.json("instrument_search", body())
        await instrument_tools.resolve_instruments("garanti")
        assert "q=garanti" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_the_default_limit_is_sent(self, fake_backend):
        fake_backend.json("instrument_search", body())
        await instrument_tools.resolve_instruments("garanti")
        assert f"limit={instrument_tools.DEFAULT_LIMIT}" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "asked,sent", [(0, 1), (1, 1), (7, 7), (99, 10)],
    )
    async def test_the_limit_is_clamped(self, fake_backend, asked, sent):
        """Backend 25'te kesiyor ve bu araç 10'da: bir açılır liste değil, bir
        çözümleme -- on aday zaten belirsizlik demek."""
        fake_backend.json("instrument_search", body())
        await instrument_tools.resolve_instruments("a" * 3, limit=asked)
        assert f"limit={sent}" in str(fake_backend.last.url)


class TestRefusals:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", ["", " ", "a", "  x  "])
    async def test_a_query_too_short_to_mean_anything_is_refused(self, fake_backend, query):
        """Tek harf her şeye benziyor; backend de reddederdi ve buradaki
        reddetme bir gidiş-dönüşü önlüyor."""
        with pytest.raises(ContractViolationError):
            await instrument_tools.resolve_instruments(query)
        assert fake_backend.attempts == 0

    @pytest.mark.asyncio
    async def test_an_object_body_is_a_contract_violation(self, fake_backend):
        """Uç bir DİZİ döndürüyor; nesneye dönerse sözleşme değişmiş demektir
        ve sessizce boş liste vermek "bu sistemde yok" diye okunurdu."""
        fake_backend.json("instrument_search", {"instruments": []})
        with pytest.raises(ContractViolationError):
            await instrument_tools.resolve_instruments("garanti")

    @pytest.mark.asyncio
    async def test_a_non_object_row_is_a_contract_violation(self, fake_backend):
        fake_backend.json("instrument_search", ["THYAO"])
        with pytest.raises(ContractViolationError):
            await instrument_tools.resolve_instruments("garanti")

    @pytest.mark.asyncio
    async def test_a_row_without_a_symbol_is_a_contract_violation(self, fake_backend):
        """Koda dönüşmeyen bir öneri başka hiçbir araca verilemiyor."""
        fake_backend.json("instrument_search", [{"name": "TÜRK HAVA YOLLARI A.O."}])
        with pytest.raises(ContractViolationError):
            await instrument_tools.resolve_instruments("türk hava yolları")

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises_rather_than_returning_empty(
        self, fake_backend,
    ):
        """Boş liste "bu sistemde yok" demek. Ulaşılamayan bir uç hiçbir şey
        demiyor, ve ikisini aynı cevaba indirmek modele olmayan bir yokluğu
        bildirmek olurdu."""
        fake_backend.fail("instrument_search")
        with pytest.raises(UpstreamUnavailableError):
            await instrument_tools.resolve_instruments("türk hava yolları")


class TestMissingFields:
    @pytest.mark.asyncio
    async def test_a_missing_name_falls_back_to_the_symbol(self, fake_backend):
        """Adı olmayan enstrüman DÜŞÜRÜLMÜYOR: aranan şey zaten sembol."""
        fake_backend.json("instrument_search", [{"symbol": "THYAO"}])
        payload = await instrument_tools.resolve_instruments("thy")
        assert payload["instruments"][0]["name"] == "THYAO"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["market", "currency"])
    async def test_a_missing_venue_or_currency_stays_null_not_guessed(
        self, fake_backend, field,
    ):
        """Para birimi bu depoda asla varsayılmıyor: AAPL dolar, THYAO lira."""
        row = {k: v for k, v in body()[0].items() if k != field}
        fake_backend.json("instrument_search", [row])
        payload = await instrument_tools.resolve_instruments("thy")
        assert payload["instruments"][0][field] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["market", "currency"])
    async def test_an_empty_venue_or_currency_is_null_not_an_empty_string(
        self, fake_backend, field,
    ):
        fake_backend.json("instrument_search", [{**body()[0], field: ""}])
        payload = await instrument_tools.resolve_instruments("thy")
        assert payload["instruments"][0][field] is None

    @pytest.mark.asyncio
    async def test_nothing_found_is_a_complete_answer(self, fake_backend):
        fake_backend.json("instrument_search", [])
        payload = await instrument_tools.resolve_instruments("olmayan şirket")
        assert payload["instruments"] == []


class TestRegistration:
    def test_the_tool_registers(self):
        recorded = []

        class FakeMCP:
            def tool(self):
                def decorate(fn):
                    recorded.append(fn.__name__)
                    return fn
                return decorate

        instrument_tools.register(FakeMCP())
        assert recorded == ["resolve_instruments"]
