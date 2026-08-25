"""The two endpoints added for live data: screening and the SSE stream.

`/instruments` is what the chat's get_market_data tool reads, so the shape it
returns is a contract surface, not an internal detail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.investment import market_service
from app.modules.market import stream

NOW = datetime.now(timezone.utc)


def row(symbol="THYAO", pe=8.2):
    return {
        "symbol": symbol, "name": symbol, "market": "BIST", "currency": "TRY",
        "price": 304.0, "change": 3.0, "change_percent": 1.0,
        "market_timestamp": NOW, "pe_ratio": pe, "pb_ratio": 1.4,
        "market_cap": 1000, "dividend_yield": 2.29, "sector": "Industrials",
        "week52_high": 355.5, "week52_low": 210.0,
    }


@pytest.fixture
def api(mocker, rows):
    from fastapi.testclient import TestClient

    mocker.patch.object(market_service, "list_instruments", return_value=rows)
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def rows():
    return [row()]


class TestInstruments:
    def test_returns_an_object_not_a_bare_array(self, api):
        """The MCP client rejects a non-object body as a contract violation,
        and every other backend endpoint returns one."""
        body = api.get("/api/market/instruments").json()
        assert isinstance(body, dict)
        assert "instruments" in body

    def test_projects_price_and_fundamentals(self, api):
        body = api.get("/api/market/instruments?symbols=THYAO").json()
        assert body["instruments"][0]["symbol"] == "THYAO"
        assert body["instruments"][0]["pe_ratio"] == pytest.approx(8.2)

    @pytest.mark.parametrize("rows", [[row(pe=None)]])
    def test_a_missing_ratio_serialises_as_null(self, api):
        """Not 0. A company with no published earnings must not screen as the
        cheapest name on the list."""
        body = api.get("/api/market/instruments").json()
        assert body["instruments"][0]["pe_ratio"] is None

    def test_filters_reach_the_service(self, api, mocker):
        spy = mocker.spy(market_service, "list_instruments")
        api.get("/api/market/instruments?max_pe=10&sector=Industrials&limit=5")
        filters = spy.call_args.kwargs["filters"]
        assert filters["max_pe"] == 10
        assert filters["sector"] == "Industrials"

    def test_absent_filters_are_not_forwarded_as_none(self, api, mocker):
        """A None max_pe forwarded as a filter would be indistinguishable
        from an explicit one at the query layer."""
        spy = mocker.spy(market_service, "list_instruments")
        api.get("/api/market/instruments")
        assert spy.call_args.kwargs["filters"] == {}

    @pytest.mark.parametrize("rows", [[]])
    def test_no_matches_is_an_empty_list_not_an_error(self, api):
        assert api.get("/api/market/instruments?max_pe=1").json() == {"instruments": []}

    def test_limit_is_bounded(self, api):
        assert api.get("/api/market/instruments?limit=0").status_code == 422
        assert api.get("/api/market/instruments?limit=5000").status_code == 422


class TestStreamEndpoint:
    """Exercised through the endpoint's generator rather than TestClient.

    The stream is endless by design: iter_lines() on it never returns, and a
    test that reads from it hangs until the suite is killed.
    """

    @pytest.fixture(autouse=True)
    def clean(self):
        stream.reset()
        yield
        stream.reset()

    class FakeRequest:
        """A Request that reports the client gone after `alive` polls."""

        def __init__(self, alive=0):
            self.alive = alive

        async def is_disconnected(self):
            if self.alive <= 0:
                return True
            self.alive -= 1
            return False

    async def _collect(self, request):
        from app.modules.market.router import market_stream

        response = await market_stream(request)
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    @pytest.mark.asyncio
    async def test_emits_the_current_frame_immediately(self):
        """A page opening between two ticks should not be blank until the
        next one arrives."""
        stream.configure(lambda: None)
        stream.publish({"as_of": None, "delay_minutes": 15, "is_delayed": True,
                        "quotes": {"THYAO": {"price": 304.0}}})

        chunks = await self._collect(self.FakeRequest(alive=0))
        assert chunks[0].startswith("event: quotes")
        assert "THYAO" in chunks[0]

    @pytest.mark.asyncio
    async def test_no_snapshot_yet_still_opens_the_stream(self):
        chunks = await self._collect(self.FakeRequest(alive=0))
        assert chunks == []

    @pytest.mark.asyncio
    async def test_a_queued_frame_is_delivered(self):
        stream.configure(lambda: None)
        request = self.FakeRequest(alive=1)

        from app.modules.market.router import market_stream

        response = await market_stream(request)
        iterator = response.body_iterator
        stream.publish({"quotes": {"THYAO": {"price": 305.0}}})
        chunks = [chunk async for chunk in iterator]
        assert any("305.0" in chunk for chunk in chunks)

    @pytest.mark.asyncio
    async def test_a_quiet_stream_sends_a_heartbeat(self, monkeypatch):
        """Idle connections get closed by intermediaries; a comment line is
        valid SSE, ignored by EventSource, and enough traffic to keep it
        open."""
        monkeypatch.setattr(stream, "HEARTBEAT_SECONDS", 0.01)
        stream.configure(lambda: None)
        chunks = await self._collect(self.FakeRequest(alive=2))
        assert any(chunk.startswith(": keepalive") for chunk in chunks)

    @pytest.mark.asyncio
    async def test_the_subscriber_is_released_on_disconnect(self):
        """A stream that leaked its queue would keep the poller alive for a
        client that has gone."""
        stream.configure(lambda: None)
        await self._collect(self.FakeRequest(alive=0))
        assert stream._subscribers == set()

    def test_headers_disable_proxy_buffering(self, api):
        """Without this an nginx in front would hold the whole stream and
        deliver it at once when the connection closes."""
        import asyncio

        from app.modules.market.router import market_stream

        response = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            market_stream(self.FakeRequest(alive=0))
        )
        assert response.headers["x-accel-buffering"] == "no"
        assert response.headers["cache-control"] == "no-cache"
        assert response.media_type == "text/event-stream"


class TestFundamentalsIngest:
    def test_rows_are_written(self, client, mocker, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        spy = mocker.patch.object(market_service, "upsert_fundamentals", return_value=3)
        response = client.post(
            "/api/market/fundamentals/ingest",
            headers={"Authorization": "Bearer secret"},
            json={"items": [{"symbol": "THYAO", "pe_ratio": 8.2}]},
        )
        assert response.json()["fundamentals_written"] == 3
        assert spy.called

    def test_a_missing_ratio_reaches_the_store_as_none(self, client, mocker, monkeypatch):
        """The whole point: absent means unknown, all the way down."""
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        spy = mocker.patch.object(market_service, "upsert_fundamentals", return_value=1)
        client.post(
            "/api/market/fundamentals/ingest",
            headers={"Authorization": "Bearer secret"},
            json={"items": [{"symbol": "THYAO", "pb_ratio": 1.4}]},
        )
        assert spy.call_args.args[1][0]["pe_ratio"] is None

    def test_it_is_guarded_like_the_other_ingests(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        assert client.post("/api/market/fundamentals/ingest", json={"items": []}).status_code == 401


class TestSortRejection:
    def test_an_unknown_sort_is_a_400_not_a_500(self, client, mocker):
        """A malformed request is the caller's to fix, and the message names
        the valid values so it can."""
        mocker.patch(
            "app.modules.investment.market_service.list_instruments",
            side_effect=market_service.UnknownSortError("gainers", ["change_percent", "symbol"]),
        )
        response = client.get("/api/market/instruments?sort_by=gainers")
        assert response.status_code == 400
        assert "change_percent" in response.json()["detail"]


class TestCandlesEndpoint:
    """Real bars for the charts. Before this the comparison charts ran on a
    seeded PRNG — the data was in the database with no route to reach it."""

    def test_bars_are_returned_for_a_known_symbol(self, client, mocker):
        mocker.patch(
            "app.modules.investment.market_service.resolve_symbol",
            return_value=SimpleNamespace(symbol="THYAO", currency_code="TRY"),
        )
        mocker.patch(
            "app.modules.investment.market_service.candle_series",
            return_value=[{
                "timestamp": datetime(2026, 8, 20, tzinfo=timezone.utc),
                "open": 300.0, "high": 305.0, "low": 299.0, "close": 304.0,
                "volume": 1_000_000,
            }],
        )
        body = client.get("/api/market/candles?symbol=THYAO").json()
        assert body["symbol"] == "THYAO"
        assert body["interval"] == "1d"
        assert body["candles"][0]["close"] == 304.0

    def test_an_unknown_symbol_is_an_empty_series_not_an_error(self, client, mocker):
        """"This instrument has no history" is an answer; a chart can draw it
        as empty."""
        mocker.patch(
            "app.modules.investment.market_service.resolve_symbol", return_value=None
        )
        response = client.get("/api/market/candles?symbol=NOPE")
        assert response.status_code == 200
        assert response.json()["candles"] == []

    def test_the_symbol_is_resolved_not_taken_literally(self, client, mocker):
        """"thyao" and "THYAO.IS" name the same instrument."""
        resolve = mocker.patch(
            "app.modules.investment.market_service.resolve_symbol",
            return_value=SimpleNamespace(symbol="THYAO", currency_code="TRY"),
        )
        mocker.patch(
            "app.modules.investment.market_service.candle_series", return_value=[]
        )
        assert client.get("/api/market/candles?symbol=thyao").json()["symbol"] == "THYAO"
        assert resolve.called

    def test_the_limit_is_bounded(self, client):
        """An unbounded limit would let one request pull every bar we hold."""
        assert client.get("/api/market/candles?symbol=THYAO&limit=99999").status_code == 422

    def test_a_missing_symbol_is_refused(self, client):
        assert client.get("/api/market/candles").status_code == 422
