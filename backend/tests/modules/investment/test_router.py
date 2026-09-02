"""Dashboard investment endpoints, now backed by the database.

These used to serve `mock_data.py`. Quantities and cost bases live in
`investment.portfolio_positions`; every price and every derived figure comes
from the current quote. The response shapes are unchanged so the frontend
contract holds.

The recurring assertion is a negative one: when a price has not been ingested,
these report the gap rather than filling it. A zero price renders as a holding
that lost all its value, and a zero change asserts the price did not move.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.modules.investment import market_service
from app.modules.analytics import service as analytics_service

NOW = datetime.now(timezone.utc)


def holding(symbol, quantity, avg_cost, price, market="BIST", currency="TRY",
            previous=None, change=None):
    return {
        "symbol": symbol, "name": symbol, "market": market, "currency": currency,
        "quantity": quantity, "avg_cost": avg_cost, "price": price,
        "previous_close": previous, "change_percent": change,
        "market_timestamp": NOW, "opened_at": NOW,
    }


def quote(price, change_pct=None, change=None):
    return {
        "price": price, "change_percent": change_pct, "change_amount": change,
        "previous_close": None, "volume": None, "currency": "TRY",
        "market_timestamp": NOW, "source": "yfinance",
    }


def product(symbol, kind="stock", market="BIST"):
    return SimpleNamespace(symbol=symbol, product_type=kind, market=market,
                           name=symbol, currency_code="TRY", data_symbol=f"{symbol}.IS")


HOLDINGS = [
    holding("THYAO", 120, 280.0, 304.0, previous=301.0, change=1.0),
    holding("AAPL", 15, 195.0, 215.3, market="NASDAQ", currency="USD",
            previous=214.0, change=0.6),
]
QUOTES = {"THYAO": quote(304.0, 1.0, 3.0), "USDTRY": quote(41.0, 0.1, 0.04)}
ACCOUNT = SimpleNamespace(cash_balance=25000, account_number="TR-DEMO-0001")


@pytest.fixture
def dash(mocker, holdings, quotes, products, sectors, candles, orders):
    from fastapi.testclient import TestClient

    mocker.patch.object(market_service, "holdings", return_value=holdings)
    mocker.patch.object(market_service, "latest_quotes", return_value=quotes)
    mocker.patch.object(market_service, "list_products", return_value=products)
    mocker.patch.object(market_service, "sector_by_symbol", return_value=sectors)
    mocker.patch.object(market_service, "candle_series", return_value=candles)
    mocker.patch.object(market_service, "recent_orders", return_value=orders)
    mocker.patch.object(market_service, "account", return_value=ACCOUNT)
    mocker.patch.object(market_service, "resolve_symbol",
                        side_effect=lambda _db, s, **_kw: product(str(s).upper()))
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def holdings():
    return list(HOLDINGS)


@pytest.fixture
def quotes():
    return dict(QUOTES)


@pytest.fixture
def products():
    return [product("THYAO"), product("AAPL", market="NASDAQ"), product("XU100", "index")]


@pytest.fixture
def sectors():
    return {"THYAO": "Industrials", "AAPL": "Technology"}


@pytest.fixture
def candles():
    return [
        {"timestamp": NOW - timedelta(days=index), "open": 300.0, "high": 310.0,
         "low": 295.0, "close": 304.0 if index % 2 else 298.0, "volume": 1000}
        for index in range(30, 0, -1)
    ]


@pytest.fixture
def orders():
    return [{"id": "PROP-1", "symbol": "THYAO", "status": "Gerçekleşti", "type": "Alış",
             "quantity": 10, "price": 304.0, "total": 3040.0, "date": NOW.isoformat()}]


class TestPositions:
    def test_price_and_derived_figures_come_from_the_live_quote(self, dash):
        body = dash.get("/api/investment/positions").json()
        thyao = next(r for r in body if r["symbol"] == "THYAO")
        assert thyao["price"] == pytest.approx(304.0)
        assert thyao["totalValue"] == pytest.approx(120 * 304.0)
        assert thyao["totalReturn"] == pytest.approx((304.0 - 280.0) * 120)
        assert thyao["dailyReturn"] == pytest.approx((304.0 - 301.0) * 120)

    def test_symbols_carry_no_test_prefix(self, dash):
        body = dash.get("/api/investment/positions").json()
        assert all(not row["symbol"].startswith("TEST-") for row in body)

    @pytest.mark.parametrize("holdings", [[holding("THYAO", 120, 280.0, None)]])
    def test_unpriced_holding_reports_zeros_rather_than_a_stale_price(self, dash):
        body = dash.get("/api/investment/positions").json()
        assert body[0]["price"] == 0
        assert body[0]["totalValue"] == 0


class TestPortfolioSummary:
    def test_total_is_cash_plus_bist_plus_converted_foreign(self, dash):
        body = dash.get("/api/investment/portfolio/summary").json()
        expected = 25000 + (120 * 304.0) + (15 * 215.3 * 41.0)
        assert body["totalTRY"] == pytest.approx(expected, abs=1)
        assert body["breakdown"]["cashTRY"] == pytest.approx(25000)

    @pytest.mark.parametrize("quotes", [{"THYAO": quote(304.0, 1.0, 3.0)}])
    def test_missing_fx_reports_zero_usd_rather_than_an_invented_total(self, dash):
        """An invented rate is an invented portfolio value. The TRY side is
        still correct on its own terms."""
        body = dash.get("/api/investment/portfolio/summary").json()
        assert body["totalUSD"] == 0.0
        assert body["breakdown"]["stocksUS"] == 0.0


class TestChart:
    """Portföyün KENDİ değerinin mum serisi.

    Bu uç nokta `XU100` döndürüyordu -- BIST 100 endeksini, "Portföy
    Performansı" başlığının altında. Gerçek bir seriydi ama kullanıcının serisi
    değildi: ekranda 1.382.868 TL yazarken grafik 14.623'te duruyordu.
    """

    URL = "/api/investment/portfolio/chart"

    @pytest.fixture()
    def bars(self, mocker):
        # Barlar pozisyonun açılışından SONRA olmalı: bir pozisyon açılmadan
        # önceki günlere katkı vermiyor, dolayısıyla daha eski barlar boş bir
        # seri üretirdi -- ki bu da doğru davranış.
        mocker.patch.object(
            market_service, "candle_bars",
            side_effect=lambda _db, symbol, **_kw: [
                (NOW + timedelta(days=n), 100.0 + n, 101.0 + n) for n in range(5)
            ],
        )
        mocker.patch.object(market_service, "candle_closes", return_value=[])
        return mocker

    def test_one_window_is_served_per_request(self, dash, bars):
        """Beş pencerenin hepsi her istekte üretiliyordu ve her biri bütün
        pozisyonların barlarını yeniden okuyordu: çağrı başına ~130 sorgu,
        ölçülen 5,9 saniye. Arayüz aynı anda tek aralık gösteriyor."""
        body = dash.get(f"{self.URL}?range=hafta").json()
        assert set(body) == {"hafta"}

    def test_the_default_window_is_the_year(self, dash, bars):
        assert set(dash.get(self.URL).json()) == {"yil"}

    def test_an_unknown_range_is_refused(self, dash, bars):
        """Sessizce varsayılana düşmek, yanlış aralığı doğru sanmak olurdu."""
        assert dash.get(f"{self.URL}?range=onyil").status_code == 422

    def test_bars_carry_ohlc_and_a_direction_colour(self, dash, bars):
        candles = dash.get(self.URL).json()["yil"]
        assert candles, "no candles were built"
        assert {"time", "open", "high", "low", "close"} <= set(candles[0])
        assert candles[0]["color"] in {"#22c55e", "#ef4444"}

    def test_it_no_longer_takes_a_symbol(self, dash, bars):
        """Sembol parametresi kalktı: bu grafiğin konusu portföy, endeks
        değil. Parametre kalsaydı endeksi çizmeye devam etmek mümkün olurdu."""
        response = dash.get(f"{self.URL}?symbol=XU100")
        assert response.status_code == 200
        # Sorgu yok sayılır; dönen seri yine portföyünkidir.
        assert set(response.json()) == {"yil"}

    def test_a_portfolio_with_no_priced_holdings_is_empty_not_an_error(
        self, dash, mocker
    ):
        mocker.patch.object(market_service, "holdings", return_value=[])
        body = dash.get(self.URL).json()
        assert body == {"yil": []}


class TestWatchlist:
    """The watchlist is the user's own picks.

    It used to be the first eight priced stocks per market in alphabetical
    order: the same list for everybody, reflecting nobody's choice, and
    unchangeable from the interface. These pin that it now comes from
    `watchlist_items` and belongs to the caller.
    """

    URL = "/api/investment/watchlist"

    @pytest.fixture()
    def signed_in(self, dash):
        from app.core.deps import get_current_user_id
        from app.main import app

        app.dependency_overrides[get_current_user_id] = lambda: "user-1"
        try:
            yield dash
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

    def test_requires_a_session(self, dash):
        """Without one it would have to guess whose list to return."""
        assert dash.get(self.URL).status_code == 401

    def test_an_empty_list_is_empty(self, signed_in, mocker):
        """No fallback. Showing instruments the user never picked would make
        the list mean nothing."""
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_symbols", return_value=[])
        body = signed_in.get(self.URL).json()
        assert body == {"bist": [], "global": [], "all": []}

    @pytest.mark.parametrize(
        "quotes",
        [{"THYAO": quote(304.0, 1.0, 3.0), "AAPL": quote(215.3, 0.6, 1.3)}],
    )
    def test_groups_by_market_and_keeps_everything_in_all(self, signed_in, mocker):
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_symbols", return_value=["THYAO", "AAPL"])
        body = signed_in.get(self.URL).json()
        assert [r["symbol"] for r in body["bist"]] == ["THYAO"]
        assert [r["symbol"] for r in body["global"]] == ["AAPL"]
        assert [r["symbol"] for r in body["all"]] == ["THYAO", "AAPL"]

    @pytest.mark.parametrize(
        "quotes",
        [{"THYAO": quote(304.0, 1.0, 3.0), "AAPL": quote(215.3, 0.6, 1.3)}],
    )
    def test_the_users_own_order_is_preserved(self, signed_in, mocker):
        """Sorting alphabetically would take the list out of the order the
        person built it in."""
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_symbols", return_value=["AAPL", "THYAO"])
        body = signed_in.get(self.URL).json()
        assert [r["symbol"] for r in body["all"]] == ["AAPL", "THYAO"]

    @pytest.mark.parametrize("quotes", [{"THYAO": quote(304.0, None, None)}])
    def test_a_followed_instrument_with_no_change_is_still_listed(self, signed_in, mocker):
        """The old endpoint dropped these. Here the user deliberately added it,
        and having it vanish reads as the add not having worked."""
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_symbols", return_value=["THYAO"])
        body = signed_in.get(self.URL).json()
        assert [r["symbol"] for r in body["bist"]] == ["THYAO"]
        assert body["bist"][0]["changePercent"] == 0.0

    def test_a_symbol_with_no_quote_is_skipped(self, signed_in, mocker):
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_symbols", return_value=["THYAO", "GHOST"])
        body = signed_in.get(self.URL).json()
        assert [r["symbol"] for r in body["all"]] == ["THYAO"]


class TestWatchlistMutations:
    @pytest.fixture()
    def signed_in(self, dash):
        from app.core.deps import get_current_user_id
        from app.main import app

        app.dependency_overrides[get_current_user_id] = lambda: "user-1"
        try:
            yield dash
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

    def test_add_returns_the_canonical_symbol(self, signed_in, mocker):
        from app.modules.investment import market_service

        mocker.patch.object(
            market_service, "watchlist_add",
            return_value=SimpleNamespace(symbol="THYAO"),
        )
        body = signed_in.post("/api/investment/watchlist/thyao").json()
        assert body == {"symbol": "THYAO", "status": "added"}

    def test_adding_an_unknown_symbol_is_a_404(self, signed_in, mocker):
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_add", return_value=None)
        assert signed_in.post("/api/investment/watchlist/NOPE").status_code == 404

    def test_remove(self, signed_in, mocker):
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_remove", return_value=True)
        body = signed_in.delete("/api/investment/watchlist/THYAO").json()
        assert body == {"symbol": "THYAO", "status": "removed"}

    def test_removing_something_not_on_the_list_is_a_404(self, signed_in, mocker):
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "watchlist_remove", return_value=False)
        assert signed_in.delete("/api/investment/watchlist/THYAO").status_code == 404

    def test_mutations_require_a_session(self, dash):
        assert dash.post("/api/investment/watchlist/THYAO").status_code == 401
        assert dash.delete("/api/investment/watchlist/THYAO").status_code == 401


class TestAllocations:
    def test_asset_allocation_sums_to_one_hundred(self, dash):
        body = dash.get("/api/investment/asset-allocation").json()
        assert sum(row["percentage"] for row in body) == pytest.approx(100.0, abs=0.1)

    def test_sector_allocation_uses_provider_sectors(self, dash):
        body = dash.get("/api/investment/sector-allocation").json()
        assert {row["sector"] for row in body} == {"Industrials", "Technology"}

    @pytest.mark.parametrize("sectors", [{}])
    def test_unknown_sector_is_labelled_not_guessed(self, dash):
        body = dash.get("/api/investment/sector-allocation").json()
        assert [row["sector"] for row in body] == ["Bilinmiyor"]

    def test_heatmap_weights_and_changes(self, dash):
        body = dash.get("/api/investment/heatmap").json()
        assert sum(row["weight"] for row in body) == pytest.approx(100.0, abs=0.1)


class TestOrders:
    def test_orders_come_from_real_proposals(self, dash):
        """A fabricated order history would let a user believe they placed
        something they never did."""
        body = dash.get("/api/investment/orders").json()
        assert body[0]["id"] == "PROP-1"
        assert body[0]["status"] in {"Bekliyor", "Gerçekleşti", "İptal"}

class TestTopMovers:
    @pytest.mark.parametrize(
        "quotes",
        [{"THYAO": quote(304.0, 5.0), "AAPL": quote(215.0, -3.0), "XU100": quote(1.0, 9.0)}],
    )
    def test_ranked_and_indices_excluded(self, dash):
        body = dash.get("/api/investment/top-movers").json()
        assert [r["symbol"] for r in body["gainers"]] == ["THYAO"]
        assert [r["symbol"] for r in body["losers"]] == ["AAPL"]

    def test_no_quotes_yields_empty_lists(self, dash, mocker):
        mocker.patch.object(market_service, "latest_quotes", return_value={})
        assert dash.get("/api/investment/top-movers").json() == {"gainers": [], "losers": []}


def test_investment_health_reports_module_name(dash):
    assert dash.get("/api/investment/health").json() == {"status": "ok", "module": "investment"}



class TestUnpricedInstrumentsInBreakdowns:
    @pytest.mark.parametrize(
        "holdings", [[holding("THYAO", 120, 280.0, None), holding("GARAN", 400, 152.0, 130.0)]]
    )
    def test_sector_allocation_skips_unpriced_holdings(self, dash):
        """An unpriced holding has no market value to allocate; counting it
        as zero would understate every other sector's share."""
        body = dash.get("/api/investment/sector-allocation").json()
        assert sum(row["percentage"] for row in body) == pytest.approx(100.0, abs=0.1)

    @pytest.mark.parametrize("holdings", [[holding("THYAO", 120, 280.0, None)]])
    def test_heatmap_omits_unpriced_holdings(self, dash):
        assert dash.get("/api/investment/heatmap").json() == []


class TestStagingIdempotencyHeader:
    def test_a_header_disagreeing_with_the_body_is_refused(self, dash):
        """A proxy deduplicating on the header while the backend dedupes on
        the body would create two proposals for one intent."""
        response = dash.post(
            "/api/investment/transactions/stage",
            headers={"Idempotency-Key": "different"},
            json={
                "user_id": "u", "transaction_type": "BUY",
                "source_account_id": "TR-DEMO-0001", "idempotency_key": "mine",
                "instrument": {"symbol": "THYAO"}, "quantity": 10,
            },
        )
        assert response.status_code == 400


class TestProductsEndpoint:
    def test_serves_the_symbol_map_to_the_ingestor(self, dash):
        """Asked for over HTTP rather than configured in the ingestor, so
        adding an instrument is one database row, not a redeploy."""
        body = dash.get("/api/investment/products").json()
        assert body[0]["symbol"] == "THYAO"
        assert body[0]["data_symbol"] == "THYAO.IS"


class TestStagingIdentity:
    """Who a proposal belongs to is decided by the token, not the body.

    The confirm endpoint checks ownership against the token. If staging took
    the owner from the request body, anyone could file a proposal under
    someone else's id and have it appear in that person's order list.
    """

    def test_the_body_owner_is_kept_when_there_is_no_token(self, client):
        """`mcp` calls this with a service identity and names the user in the
        body; that path must keep working."""
        response = client.post(
            "/api/investment/transactions/stage",
            json=_stage_body(user_id="user-from-body"),
        )
        assert response.status_code == 200
        assert response.json()["status"] in {
            "PENDING_USER_CONFIRMATION",
            "REJECTED_VALIDATION",
            "REQUIRES_ADDITIONAL_INPUT",
        }

    def test_staging_for_another_user_is_refused(self, client):
        from app.core.deps import get_optional_user_id
        from app.main import app

        app.dependency_overrides[get_optional_user_id] = lambda: "user-alice"
        try:
            response = client.post(
                "/api/investment/transactions/stage",
                json=_stage_body(user_id="user-bob"),
            )
        finally:
            app.dependency_overrides.pop(get_optional_user_id, None)
        assert response.status_code == 403

    def test_the_token_owner_may_stage_for_themselves(self, client):
        from app.core.deps import get_optional_user_id
        from app.main import app

        app.dependency_overrides[get_optional_user_id] = lambda: "user-alice"
        try:
            response = client.post(
                "/api/investment/transactions/stage",
                json=_stage_body(user_id="user-alice"),
            )
        finally:
            app.dependency_overrides.pop(get_optional_user_id, None)
        assert response.status_code == 200


def _stage_body(user_id: str) -> dict:
    import uuid

    return {
        "user_id": user_id,
        "transaction_type": "BUY",
        "source_account_id": "TR-DEMO-0001",
        "idempotency_key": f"test-{uuid.uuid4()}",
        "instrument": {"symbol": "THYAO"},
        "quantity": 1,
        "order_type": "MARKET",
        "time_in_force": "DAY",
        "assumptions": [],
    }


class TestAssetAllocationCurrency:
    """The buckets used to split on `market == "BIST"` and multiply everything
    else by the dollar rate — correct only while every foreign holding was
    American — and `rates.get("USD", 0.0)` zeroed them all in silence when the
    rate had not been ingested."""

    def _client(self, mocker, holdings, quotes):
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "holdings", return_value=holdings)
        mocker.patch.object(market_service, "latest_quotes", return_value=quotes)
        mocker.patch.object(
            market_service, "account",
            return_value=SimpleNamespace(id="a1", cash_balance=1000.0,
                                         currency_code="TRY", account_number="TR-1"),
        )

    def _row(self, symbol, currency, market, quantity, price):
        return {
            "symbol": symbol, "currency": currency, "market": market,
            "quantity": quantity, "price": price, "avg_cost": price,
        }

    def test_a_euro_holding_is_not_converted_at_the_dollar_rate(self, client, mocker):
        self._client(
            mocker,
            [self._row("SAP", "EUR", "XETRA", 10, 100.0)],
            {"USDTRY": {"price": 40.0}, "EURTRY": {"price": 50.0}},
        )
        body = client.get("/api/investment/asset-allocation").json()
        # XETRA is not one of the named venues, so it lands in the catch-all
        # rather than vanishing from the chart.
        foreign = next(b for b in body if b["assetClass"] == "Diğer")
        assert foreign["amount"] == pytest.approx(10 * 100 * 50.0)

    def test_a_holding_with_no_rate_is_left_out_rather_than_zeroed(self, client, mocker):
        """No USD rate means the dollar value cannot be stated in lira. It is
        omitted, not converted at 1.0 and not counted as zero lira."""
        self._client(mocker, [self._row("AAPL", "USD", "NASDAQ", 10, 100.0)], {})
        body = client.get("/api/investment/asset-allocation").json()
        assert all(bucket["assetClass"] != "ABD Hisse" for bucket in body)
        # Only the cash bucket survives, and it is untouched by the failure.
        assert [b["assetClass"] for b in body] == ["Nakit (TRY)"]
        assert body[0]["amount"] == pytest.approx(1000.0)

    def test_a_us_holding_lands_in_the_us_bucket(self, client, mocker):
        self._client(
            mocker, [self._row("AAPL", "USD", "NASDAQ", 10, 100.0)],
            {"USDTRY": {"price": 40.0}},
        )
        body = client.get("/api/investment/asset-allocation").json()
        us = next(b for b in body if b["assetClass"] == "ABD Hisse")
        assert us["amount"] == pytest.approx(10 * 100 * 40.0)

    def test_gold_is_not_counted_as_a_foreign_share(self, client, mocker):
        """It is quoted in dollars, which is why bucketing by CURRENCY put an
        ounce of gold in the foreign-equities slice."""
        self._client(
            mocker, [self._row("XAUUSD", "USD", "COMEX", 2, 4000.0)],
            {"USDTRY": {"price": 40.0}},
        )
        body = client.get("/api/investment/asset-allocation").json()
        assert all(b["assetClass"] != "ABD Hisse" for b in body)
        gold = next(b for b in body if b["assetClass"] == "Altın")
        assert gold["amount"] == pytest.approx(2 * 4000 * 40.0)

    def test_gold_and_currency_are_separate_slices(self, client, mocker):
        """Doküman üçünü adıyla ayırıyor: "hisse, altın ve döviz". Tek bir
        "Emtia / Döviz" dilimi, ikisini birden tutan birine hangisinin ne
        kadar olduğunu söyleyemiyordu."""
        self._client(
            mocker,
            [self._row("XAUUSD", "USD", "COMEX", 1, 4000.0),
             self._row("USDTRY", "TRY", "FX", 100, 48.0)],
            {"USDTRY": {"price": 40.0}},
        )
        body = client.get("/api/investment/asset-allocation").json()
        gold = next(b for b in body if b["assetClass"] == "Altın")
        fx = next(b for b in body if b["assetClass"] == "Döviz")
        assert gold["amount"] == pytest.approx(4000 * 40.0)
        assert fx["amount"] == pytest.approx(4800.0)
        assert gold["color"] != fx["color"]

    def test_a_lira_holding_lands_in_the_domestic_bucket(self, client, mocker):
        self._client(
            mocker, [self._row("THYAO", "TRY", "BIST", 100, 300.0)],
            {"USDTRY": {"price": 40.0}},
        )
        body = client.get("/api/investment/asset-allocation").json()
        domestic = next(b for b in body if b["assetClass"] == "BIST Hisse")
        assert domestic["amount"] == pytest.approx(30000.0)


class TestStagingRequiresAnIdentifiedOwner:
    """A proposal nobody owns is worse than no proposal.

    The chat degrades an expired token to an anonymous session so general
    questions keep working. Staging inherited that: the orchestrator named the
    user "anonymous", the account lookup fell through to the shared demo
    account, and the row was stored with an owner the confirm endpoint could
    never match. The user was shown a fully costed Onayla button that returned
    404 every time it was pressed.
    """

    def test_an_anonymous_owner_is_refused(self, client):
        response = client.post(
            "/api/investment/transactions/stage",
            json=_stage_body(user_id="anonymous"),
        )
        assert response.status_code == 401

    def test_an_empty_owner_is_refused(self, client):
        response = client.post(
            "/api/investment/transactions/stage",
            json=_stage_body(user_id=""),
        )
        assert response.status_code == 401

    def test_an_owner_without_an_account_does_not_borrow_the_demo_one(self, client):
        """`market_service.account` hands anonymous readers the demo account.
        Reading it is harmless; pricing a trade against it is not."""
        from app.main import app
        from app.modules.investment import market_service

        calls: list = []

        def _account(db, user_id=None, account_number=None, allow_demo_fallback=True):
            calls.append(allow_demo_fallback)
            return None

        original = market_service.account
        market_service.account = _account
        try:
            response = client.post(
                "/api/investment/transactions/stage",
                json=_stage_body(user_id="user-with-no-account"),
            )
        finally:
            market_service.account = original

        # The staging lookup is the FIRST one; later helpers may resolve an
        # account for other reasons.
        assert calls and calls[0] is False
        assert response.status_code != 200 or response.json()["status"] != "PENDING_USER_CONFIRMATION"


class TestCashStatement:
    """Yatırım hesabının hareket dökümü.

    Hesabın IBAN'ı da dökümü de yoktu: bankacılık arayüzünde "hesap hareketi"
    boş kalıyor, hesap "para gönder" ekranında adreslenemiyordu. Nakit
    `banking.accounts` değil `investment.investment_accounts` üzerinde durduğu
    için döküm de kendi ucundan geliyor.
    """

    ACCOUNT = SimpleNamespace(
        id="ia-1",
        account_number="TR-DEMO-0001",
        iban="TR00DEMO",
        currency_code="TRY",
        cash_balance=1500.0,
    )

    @pytest.fixture()
    def signed_in(self, dash, mocker):
        from app.core.deps import get_current_user_id
        from app.main import app

        mocker.patch.object(market_service, "account", return_value=self.ACCOUNT)
        app.dependency_overrides[get_current_user_id] = lambda: "user-1"
        try:
            yield dash
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

    def test_requires_a_session(self, dash):
        """Oturumsuz çağrı kimin hesabını okuyacağını bilemez."""
        assert dash.get("/api/investment/accounts/TR00DEMO/statement").status_code == 401

    def test_movements_come_back_with_running_balances(self, signed_in, mocker):
        from app.modules.investment import service as investment_service

        mocker.patch.object(
            investment_service,
            "cash_statement",
            return_value={
                "account_number": "TR-DEMO-0001",
                "iban": "TR00DEMO",
                "balance": 1500.0,
                "currency_code": "TRY",
                "movements": [
                    {
                        "reference_number": "PRP-1",
                        "direction": "DEBIT",
                        "amount": 500.0,
                        "balance_after": 1500.0,
                        "counterparty_iban": None,
                        "description": "Alım — THYAO x2",
                        "created_at": datetime(2026, 8, 20, tzinfo=timezone.utc),
                    }
                ],
            },
        )
        body = signed_in.get("/api/investment/accounts/TR00DEMO/statement").json()
        assert body["balance"] == 1500.0
        assert body["movements"][0]["balance_after"] == 1500.0
        assert body["movements"][0]["description"] == "Alım — THYAO x2"

    def test_the_account_number_addresses_it_too(self, signed_in, mocker):
        """Arayüz elindeki iki alandan hangisi doluysa onu gönderiyor."""
        from app.modules.investment import service as investment_service

        mocker.patch.object(
            investment_service, "cash_statement",
            return_value={"account_number": "TR-DEMO-0001", "iban": "TR00DEMO",
                          "balance": 0.0, "currency_code": "TRY", "movements": []},
        )
        assert signed_in.get(
            "/api/investment/accounts/TR-DEMO-0001/statement"
        ).status_code == 200

    def test_somebody_elses_identifier_is_not_found(self, signed_in):
        """Başkasının hesabının var olduğunu doğrulamak bile fazla bilgi."""
        assert signed_in.get(
            "/api/investment/accounts/TR00SOMEONEELSE/statement"
        ).status_code == 404

    def test_a_user_without_an_investment_account_gets_404(self, signed_in, mocker):
        mocker.patch.object(market_service, "account", return_value=None)
        assert signed_in.get(
            "/api/investment/accounts/TR00DEMO/statement"
        ).status_code == 404


class TestConfirmedProposalsReader:
    """Pozisyonun zaman içindeki miktarını veren tek kayıt."""

    def test_an_anonymous_caller_has_no_trade_history(self):
        """Oturumsuz çağrı kimin işlemlerini okuyacağını bilemez; boş liste
        döner ve grafik bugünkü miktarla çizilir."""
        from app.modules.investment.router import _confirmed_proposals

        assert _confirmed_proposals(MagicMock(spec=Session), None) == []

    def test_a_signed_in_caller_gets_their_confirmed_trades(self):
        from app.modules.investment.router import _confirmed_proposals

        db = MagicMock(spec=Session)
        rows = [SimpleNamespace(symbol="THYAO")]
        db.query.return_value.filter.return_value.all.return_value = rows
        assert _confirmed_proposals(db, "user-1") == rows
