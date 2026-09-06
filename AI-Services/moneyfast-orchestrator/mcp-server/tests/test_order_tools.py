"""`get_open_orders` ve `cancel_order` birim testleri — sözleşme v2.20.

Bu iki araç emir akışının karşılığı: bir alım artık onaylandığı anda
gerçekleşmiyor, kullanıcının verdiği fiyata gelene kadar bekliyor ve o
sırada parası bloke duruyor.

Korunan iddialar:

* boş liste TAM bir cevap. "Bu kişinin emri yok" ölçülmüş bir sonuç ve
  "veriye ulaşamadım" ile karıştırılmamalı;
* `id` ve `status` ZORUNLU. Numarası olmayan bir emir iptal edilemez ve
  durumu bilinmeyen bir emir hakkında söylenebilecek doğru bir cümle yok;
* `limit_price` yokluğu SIFIR DEĞİL. Piyasa emrinin tetikleyici fiyatı
  yoktur; sıfır yazmak "sıfır liradan alım emri" demek olurdu;
* iptal onaylanmadan RAPOR EDİLMEZ. Alınmamış bir onayı bildirmek,
  kullanıcının hâlâ canlı bir emri izlemeyi bırakmasına yol açar.
"""

from __future__ import annotations

import pytest

import order_tools
from backend_client import (
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)

TOOL_KEYS = {"orders", "open_count"}
ROW_KEYS = {
    "id", "symbol", "status", "type", "quantity", "price", "total",
    "currency", "limit_price", "cancellable", "date",
}


def body():
    """Backend'in `GET /investment/agent/{user}/orders` yanıtı."""
    return [
        {
            "id": "PROP-1", "symbol": "THYAO", "status": "Fiyat bekliyor",
            "type": "Alış", "quantity": 10.0, "price": 290.0, "total": 2900.0,
            "currency": "TRY", "limitPrice": 290.0, "cancellable": True,
            "date": "2026-09-05T18:00:00+00:00",
        },
        {
            "id": "PROP-2", "symbol": "AAPL", "status": "Gerçekleşti",
            "type": "Alış", "quantity": 2.0, "price": 300.0, "total": 600.0,
            "currency": "USD", "limitPrice": None, "cancellable": False,
            "date": "2026-09-04T18:00:00+00:00",
        },
    ]


class TestListContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v220_exactly(self, fake_backend):
        fake_backend.json("orders", body())
        payload = await order_tools.get_open_orders("user-1")
        assert set(payload) == TOOL_KEYS

    @pytest.mark.asyncio
    async def test_row_keys_match_v220_exactly(self, fake_backend):
        fake_backend.json("orders", body())
        payload = await order_tools.get_open_orders("user-1")
        assert set(payload["orders"][0]) == ROW_KEYS

    @pytest.mark.asyncio
    async def test_only_unsettled_orders_are_counted_as_open(self, fake_backend):
        """Gerçekleşmiş bir emir "bekleyen" değil; ikisini toplamak
        kullanıcıya olmayan bir bekleyen emir gösterirdi."""
        fake_backend.json("orders", body())
        payload = await order_tools.get_open_orders("user-1")
        assert payload["open_count"] == 1

    @pytest.mark.asyncio
    async def test_an_empty_list_is_a_complete_answer(self, fake_backend):
        fake_backend.json("orders", [])
        payload = await order_tools.get_open_orders("user-1")
        assert payload == {"orders": [], "open_count": 0}

    @pytest.mark.asyncio
    async def test_the_user_is_named_in_the_path(self, fake_backend):
        fake_backend.json("orders", [])
        await order_tools.get_open_orders("user-42")
        assert fake_backend.last.url.path.endswith("/investment/agent/user-42/orders")

    @pytest.mark.asyncio
    async def test_a_market_order_has_no_trigger_price(self, fake_backend):
        fake_backend.json("orders", body())
        payload = await order_tools.get_open_orders("user-1")
        assert payload["orders"][1]["limit_price"] is None

    @pytest.mark.asyncio
    async def test_the_trigger_price_survives(self, fake_backend):
        fake_backend.json("orders", body())
        payload = await order_tools.get_open_orders("user-1")
        assert payload["orders"][0]["limit_price"] == 290.0


class TestListRefusals:
    @pytest.mark.asyncio
    async def test_a_row_that_is_not_an_object_is_refused(self, fake_backend):
        fake_backend.json("orders", ["PROP-1"])
        with pytest.raises(ContractViolationError):
            await order_tools.get_open_orders("user-1")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("missing", ["id", "status"])
    async def test_a_row_missing_a_load_bearing_field_is_refused(
        self, fake_backend, missing
    ):
        row = dict(body()[0])
        row.pop(missing)
        fake_backend.json("orders", [row])
        with pytest.raises(ContractViolationError):
            await order_tools.get_open_orders("user-1")

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_surfaces_rather_than_returning_empty(
        self, fake_backend
    ):
        """Boş liste dönmek, emri olan birine "emriniz yok" demek olurdu."""
        fake_backend.fail("orders")
        with pytest.raises(UpstreamUnavailableError):
            await order_tools.get_open_orders("user-1")

    @pytest.mark.asyncio
    async def test_missing_optional_fields_fall_back_without_inventing(
        self, fake_backend
    ):
        fake_backend.json("orders", [{"id": "PROP-9", "status": "Fiyat bekliyor"}])
        row = (await order_tools.get_open_orders("user-1"))["orders"][0]
        assert row["symbol"] == "-"
        assert row["quantity"] == 0.0
        assert row["currency"] == "TRY"
        assert row["cancellable"] is False
        assert row["limit_price"] is None


class TestCancel:
    @pytest.mark.asyncio
    async def test_a_cancellation_reports_the_order_it_withdrew(self, fake_backend):
        fake_backend.json("order_cancel", {"order_id": "PROP-1", "cancelled": True})
        assert await order_tools.cancel_order("user-1", "PROP-1") == {
            "order_id": "PROP-1", "cancelled": True,
        }

    @pytest.mark.asyncio
    async def test_the_order_and_user_are_named_in_the_path(self, fake_backend):
        fake_backend.json("order_cancel", {"order_id": "PROP-1", "cancelled": True})
        await order_tools.cancel_order("user-42", "  PROP-1  ")
        assert fake_backend.last.url.path.endswith(
            "/investment/agent/user-42/orders/PROP-1/cancel"
        )

    @pytest.mark.asyncio
    async def test_an_empty_order_id_is_refused_before_the_call(self, fake_backend):
        """Boş bir numarayla çağırmak, sunucuda başka bir yola çözülürdü."""
        with pytest.raises(ContractViolationError):
            await order_tools.cancel_order("user-1", "   ")
        assert fake_backend.attempts == 0

    @pytest.mark.asyncio
    async def test_an_unknown_order_is_an_input_error(self, fake_backend):
        fake_backend.status("order_cancel", 404, {"detail": "Böyle bir emir bulunamadı."})
        with pytest.raises(InvalidInputError):
            await order_tools.cancel_order("user-1", "PROP-X")

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_never_reports_a_cancellation(
        self, fake_backend
    ):
        """Alınmamış bir onayı bildirmek, kullanıcının hâlâ canlı bir emri
        izlemeyi bırakmasına yol açar."""
        fake_backend.fail("order_cancel")
        with pytest.raises(UpstreamUnavailableError):
            await order_tools.cancel_order("user-1", "PROP-1")


class TestRegistration:
    def test_both_tools_are_attached(self, mocker):
        mcp = mocker.MagicMock()
        order_tools.register(mcp)
        registered = [call.args[0] for call in mcp.tool.return_value.call_args_list]
        assert registered == [order_tools.get_open_orders, order_tools.cancel_order]
