"""Market endpoints.

These used to serve `mock_data.py`. They now read `investment.market_quotes`
and `market.news_items` — the same tables the chatbot reads, so the dashboard
and the assistant cannot quote different prices for the same instrument.

The most important assertion here is a negative one: when nothing has been
ingested, these return an empty list rather than falling back to mock data.
A user cannot tell a fabricated price from a real one.
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
from app.modules.market import router as market_router
from app.modules.market import service as market_module_service

NOW = datetime.now(timezone.utc)


@pytest.fixture
def market_client(mocker, quotes, news):
    from fastapi.testclient import TestClient

    mocker.patch.object(market_service, "latest_quotes", return_value=quotes)
    mocker.patch.object(market_module_service, "latest_news", return_value=news)
    app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def quotes():
    return {}


@pytest.fixture
def news():
    return []


def quote(price, change, pct):
    return {
        "price": price, "change_amount": change, "change_percent": pct,
        "previous_close": price - change if change is not None else None,
        "volume": 1000, "currency": "TRY",
        "market_timestamp": NOW - timedelta(minutes=15), "source": "yfinance",
    }


class TestTickers:
    @pytest.mark.parametrize(
        "quotes",
        [{"USDTRY": quote(41.2, 0.15, 0.36), "XU100": quote(10540.2, -120.4, -1.13)}],
    )
    def test_returns_live_quotes_in_strip_order(self, market_client):
        body = market_client.get("/api/market/tickers").json()
        assert [row["symbol"] for row in body] == ["XU100", "USDTRY"]
        # Strip order is the configured display order, not the dict order.
        assert body[0]["price"] == pytest.approx(10540.2)
        assert body[0]["changePercent"] == pytest.approx(-1.13)
        assert body[1]["price"] == pytest.approx(41.2)

    def test_no_ingested_data_yields_an_empty_strip_not_mock_prices(self, market_client):
        """A fabricated price is indistinguishable from a real one on screen.
        An empty strip is the honest answer before the first ingest."""
        assert market_client.get("/api/market/tickers").json() == []

    @pytest.mark.parametrize("quotes", [{"USDTRY": quote(41.2, None, None)}])
    def test_missing_change_becomes_zero_not_null(self, market_client):
        """The response model types these as float; null would fail
        validation and take down the whole strip for one incomplete row."""
        body = market_client.get("/api/market/tickers").json()
        assert body[0]["change"] == 0.0
        assert body[0]["changePercent"] == 0.0


def article(**overrides):
    row = SimpleNamespace(
        id="news-1",
        source="Dünya",
        title="THYAO kargo gelirlerini açıkladı",
        url="https://example.com/haber/1",
        published_at=NOW - timedelta(minutes=5),
        related_symbols=["THYAO"],
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


class TestNews:
    @pytest.mark.parametrize("news", [[article()]])
    def test_returns_stored_articles(self, market_client):
        body = market_client.get("/api/market/news").json()
        assert body[0]["title"] == "THYAO kargo gelirlerini açıkladı"
        assert body[0]["source"] == "Dünya"
        assert body[0]["relatedSymbols"] == ["THYAO"]

    @pytest.mark.parametrize("news", [[article()]])
    def test_sentiment_is_never_asserted(self, market_client):
        """Calling a headline positive or negative is a market view, and this
        system is not permitted to hold one."""
        assert market_client.get("/api/market/news").json()[0]["sentiment"] == "neutral"

    @pytest.mark.parametrize("news", [[article(url=None)]])
    def test_missing_url_falls_back_to_a_placeholder(self, market_client):
        assert market_client.get("/api/market/news").json()[0]["url"] == "#"

    def test_no_news_yields_an_empty_feed_not_invented_headlines(self, market_client):
        assert market_client.get("/api/market/news").json() == []

    def test_limit_is_bounded(self, market_client):
        assert market_client.get("/api/market/news?limit=0").status_code == 422
        assert market_client.get("/api/market/news?limit=500").status_code == 422


class TestRelativeTime:
    @pytest.mark.parametrize(
        "minutes,expected",
        [(0, "az önce"), (5, "5 dk önce"), (90, "1 saat önce"), (60 * 30, "1 gün önce")],
    )
    def test_turkish_relative_labels(self, minutes, expected):
        moment = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        assert market_router._relative_time(moment) == expected

    def test_naive_timestamp_is_treated_as_utc(self):
        """A driver handing back a naive datetime would otherwise raise
        TypeError and take out the whole feed."""
        naive = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(tzinfo=None)
        assert market_router._relative_time(naive) == "5 dk önce"


class TestIngestAuth:
    def test_ingest_without_a_token_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        assert client.post("/api/market/ingest", json={"quotes": [], "candles": []}).status_code == 401

    def test_ingest_with_a_wrong_token_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        response = client.post(
            "/api/market/ingest",
            json={"quotes": [], "candles": []},
            headers={"Authorization": "Bearer wrong"},
        )
        assert response.status_code == 401

    def test_unconfigured_key_refuses_rather_than_opening_the_endpoint(self, client, monkeypatch):
        """A write endpoint that silently became public because an env var was
        missing is exactly the failure nobody notices."""
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        response = client.post(
            "/api/market/ingest",
            json={"quotes": [], "candles": []},
            headers={"Authorization": "Bearer anything"},
        )
        assert response.status_code == 503

    def test_news_ingest_is_guarded_too(self, client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        assert client.post("/api/market/news/ingest", json={"items": []}).status_code == 401


class TestIngestWrites:
    def test_quotes_and_candles_are_forwarded_to_the_store(self, client, mocker, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        quotes = mocker.patch.object(market_service, "upsert_quotes", return_value=2)
        candles = mocker.patch.object(market_service, "upsert_candles", return_value=5)

        response = client.post(
            "/api/market/ingest",
            headers={"Authorization": "Bearer secret"},
            json={
                "quotes": [
                    {
                        "symbol": "TEST-THYAO", "price": 295.5,
                        "market_timestamp": NOW.isoformat(),
                    }
                ],
                "candles": [
                    {
                        "symbol": "TEST-THYAO", "timestamp": NOW.isoformat(),
                        "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                    }
                ],
            },
        )
        assert response.status_code == 200
        assert response.json() | {"quotes_written": 2, "candles_written": 5} == response.json()
        assert quotes.called and candles.called

    def test_news_ingest_reports_only_new_rows(self, client, mocker, monkeypatch):
        """Re-running a feed must be a no-op. The count is what proves it."""
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        mocker.patch.object(market_module_service, "upsert_news", return_value=0)
        response = client.post(
            "/api/market/news/ingest",
            headers={"Authorization": "Bearer secret"},
            json={
                "items": [
                    {
                        "content_hash": "a" * 64,
                        "title": "Aynı haber",
                        "source": "Dünya",
                        "published_at": NOW.isoformat(),
                    }
                ]
            },
        )
        assert response.json()["news_written"] == 0

    def test_short_content_hash_is_rejected(self, client, monkeypatch):
        """The hash is the deduplication key shared with the rag service; a
        truncated one would silently stop matching."""
        monkeypatch.setenv("BACKEND_API_KEY", "secret")
        response = client.post(
            "/api/market/news/ingest",
            headers={"Authorization": "Bearer secret"},
            json={
                "items": [
                    {"content_hash": "abc", "title": "t", "source": "s",
                     "published_at": NOW.isoformat()}
                ]
            },
        )
        assert response.status_code == 422


def test_market_health_reports_module_name(client):
    assert client.get("/api/market/health").json() == {"status": "ok", "module": "market"}


class TestInstrumentSearch:
    """Yazdıkça öneri: evren binin üzerinde enstrüman, açılır liste taşımaz."""

    URL = "/api/market/search"

    def test_it_returns_the_service_rows(self, market_client, mocker):
        mocker.patch.object(
            market_service, "search_instruments",
            return_value=[{"symbol": "THYAO", "name": "Türk Hava Yolları",
                           "market": "BIST", "currency": "TRY"}],
        )
        body = market_client.get(f"{self.URL}?q=thy").json()
        assert body[0]["symbol"] == "THYAO"

    def test_an_empty_query_is_rejected(self, market_client):
        """Boş arama bütün evreni dökmemeli."""
        assert market_client.get(f"{self.URL}?q=").status_code == 422

    def test_the_limit_is_capped(self, market_client):
        assert market_client.get(f"{self.URL}?q=a&limit=999").status_code == 422


class TestIntradaySymbols:
    """Gün içi bar gereken küme; evrenin tamamı değil."""

    URL = "/api/market/candles/intraday-symbols"

    def test_it_needs_the_service_key(self, market_client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        assert market_client.get(self.URL).status_code == 401

    def test_it_reports_the_symbols(self, market_client, mocker, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        mocker.patch.object(
            market_service, "intraday_symbols", return_value=["THYAO", "USDTRY"],
        )
        body = market_client.get(
            self.URL, headers={"Authorization": "Bearer s3cret"},
        ).json()
        assert body == {"symbols": ["THYAO", "USDTRY"]}


class TestNamedLookupRefreshesFirst:
    """Adı verilen bir enstrüman sorulduğunda fiyat önce tazelenir.

    Toplu tur on beş dakikada bir dönüyor; "THYAO kaç TL" sorusuna on beş
    dakika önceki fiyatla cevap vermek, kullanıcının karar verdiği anda yanlış
    sayı göstermek olurdu.
    """

    def test_a_named_symbol_triggers_a_refresh(self, market_client, mocker):
        refresh = mocker.patch.object(market_module_service, "refresh_quotes")
        mocker.patch.object(market_service, "list_instruments", return_value=[])
        market_client.get("/api/market/instruments?symbols=THYAO")
        refresh.assert_called_once()

    def test_a_screen_does_not(self, market_client, mocker):
        """Tarama yüzlerce satır okur ve hiçbiri tek bir anlık fiyata bağlı
        karar değildir."""
        refresh = mocker.patch.object(market_module_service, "refresh_quotes")
        mocker.patch.object(market_service, "list_instruments", return_value=[])
        market_client.get("/api/market/instruments?market=BIST")
        refresh.assert_not_called()


class TestMarketHeatmapEndpoint:
    """Piyasanın ısı haritası; portföyünkiyle karıştırılmamalı."""

    URL = "/api/market/heatmap"

    def test_it_returns_tiles_and_the_missing_count(self, market_client, mocker):
        mocker.patch.object(
            market_service, "market_heatmap",
            return_value={
                "items": [{
                    "symbol": "THYAO", "name": "Türk Hava Yolları",
                    "marketCap": 1_000_000.0, "changePercent": 1.5,
                    "sector": "Taşımacılık", "price": 300.0, "currency": "TRY",
                }],
                "missing": 4,
            },
        )
        body = market_client.get(f"{self.URL}?market=BIST").json()
        assert body["items"][0]["symbol"] == "THYAO"
        # Kaç enstrümanın çizilemediği söylenir: sessizce düşen kutular,
        # haritayı olduğundan küçük gösterir.
        assert body["missing"] == 4

    def test_the_limit_is_capped(self, market_client):
        assert market_client.get(f"{self.URL}?limit=5000").status_code == 422

    def test_no_market_means_every_market(self, market_client, mocker):
        heatmap = mocker.patch.object(
            market_service, "market_heatmap", return_value={"items": [], "missing": 0},
        )
        market_client.get(self.URL)
        assert heatmap.call_args.kwargs["market"] is None


class TestMissingFundamentalsEndpoint:
    URL = "/api/market/fundamentals/missing"

    def test_it_needs_the_service_key(self, market_client, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        assert market_client.get(self.URL).status_code == 401

    def test_it_reports_what_is_missing(self, market_client, mocker, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        mocker.patch.object(
            market_service, "symbols_without_fundamentals", return_value=["AAPL"],
        )
        body = market_client.get(
            self.URL, headers={"Authorization": "Bearer s3cret"},
        ).json()
        assert body == {"symbols": ["AAPL"]}
