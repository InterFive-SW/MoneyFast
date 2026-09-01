"""Delivery and orchestration.

The ingestor holds no database credential; everything it collects leaves over
HTTP. These tests pin two things: the credential actually travels, and no
single failing destination can take the run down with it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from ingestor import config, run, sinks

NOW = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
_RealClient = httpx.Client


def client_for(handler):
    return _RealClient(transport=httpx.MockTransport(handler))


def recorder(status=200, body=None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=body if body is not None else {})

    handler.calls = calls
    return handler


class TestServiceCredential:
    def test_token_is_sent_when_configured(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        handler = recorder(body={"quotes_written": 1})
        sinks.push_market_data(
            client_for(handler),
            [{"symbol": "TEST-THYAO", "price": 1.0, "market_timestamp": NOW}],
            [],
        )
        assert handler.calls[0].headers["Authorization"] == "Bearer s3cret"

    def test_no_header_when_unconfigured(self):
        """The backend refuses unauthenticated ingest anyway; sending an empty
        `Bearer ` would just make the failure harder to read."""
        handler = recorder(body={})
        sinks.push_market_data(
            client_for(handler), [{"symbol": "X", "price": 1.0, "market_timestamp": NOW}], []
        )
        assert "Authorization" not in handler.calls[0].headers


class TestSerialisation:
    def test_datetimes_become_iso_strings(self):
        """json.dumps cannot serialise a datetime, and httpx uses json."""
        payload = sinks._serialise({"at": NOW, "rows": [{"t": NOW}]})
        assert payload["at"] == NOW.isoformat()
        assert payload["rows"][0]["t"] == NOW.isoformat()

    def test_other_values_pass_through(self):
        assert sinks._serialise({"n": 1, "s": "x", "b": True}) == {"n": 1, "s": "x", "b": True}


class TestMarketPush:
    def test_empty_payload_makes_no_request(self):
        handler = recorder()
        assert sinks.push_market_data(client_for(handler), [], []) is None
        assert handler.calls == []

    def test_backend_failure_is_logged_not_raised(self):
        """A failed push must not kill the scheduler thread; the next cycle
        re-offers the data."""
        handler = recorder(status=500)
        result = sinks.push_market_data(
            client_for(handler), [{"symbol": "X", "price": 1.0, "market_timestamp": NOW}], []
        )
        assert result is None


class TestNewsPush:
    def test_empty_batch_makes_no_request(self):
        handler = recorder()
        assert sinks.push_news_to_backend(client_for(handler), []) is None
        assert handler.calls == []

    def test_rag_receives_one_document_per_article(self):
        handler = recorder(body={"status": "ingested"})
        items = [
            {"content_hash": "a" * 64, "title": "T1", "summary": "S1", "source": "Dünya",
             "url": "u", "related_symbols": ["THYAO"], "published_at": NOW},
            {"content_hash": "b" * 64, "title": "T2", "summary": "S2", "source": "Dünya",
             "url": "u", "related_symbols": [], "published_at": NOW},
        ]
        assert sinks.push_news_to_rag(client_for(handler), items) == 2
        assert len(handler.calls) == 2

    def test_duplicates_reported_by_rag_are_not_counted(self):
        """Re-offering a feed must be a no-op, and the count is what proves
        it stayed one."""
        handler = recorder(body={"status": "duplicate"})
        items = [{"content_hash": "a" * 64, "title": "T", "summary": "S",
                  "source": "D", "published_at": NOW}]
        assert sinks.push_news_to_rag(client_for(handler), items) == 0

    def test_first_ticker_is_carried_and_the_rest_are_dropped(self):
        """The corpus schema holds one ticker per document. Multi-tagged
        stories stay findable by text."""
        handler = recorder(body={"status": "ingested"})
        items = [{"content_hash": "a" * 64, "title": "T", "summary": "S", "source": "D",
                  "related_symbols": ["THYAO", "ASELS"], "published_at": NOW}]
        sinks.push_news_to_rag(client_for(handler), items)
        body = json.loads(handler.calls[0].content)
        assert body["ticker"] == "THYAO"

    def test_article_without_a_summary_falls_back_to_its_title(self):
        handler = recorder(body={"status": "ingested"})
        items = [{"content_hash": "a" * 64, "title": "Sadece başlık", "summary": None,
                  "source": "D", "published_at": NOW}]
        sinks.push_news_to_rag(client_for(handler), items)
        assert json.loads(handler.calls[0].content)["content"] == "Sadece başlık"

    def test_one_failed_document_does_not_stop_the_rest(self):
        seen = []

        def handler(request):
            seen.append(request)
            if len(seen) == 1:
                return httpx.Response(500)
            return httpx.Response(200, json={"status": "ingested"})

        items = [
            {"content_hash": "a" * 64, "title": "T1", "summary": "S", "source": "D", "published_at": NOW},
            {"content_hash": "b" * 64, "title": "T2", "summary": "S", "source": "D", "published_at": NOW},
        ]
        assert sinks.push_news_to_rag(client_for(handler), items) == 1


class TestProductFetch:
    def test_symbol_map_comes_from_the_backend(self):
        """Asked for rather than configured here, so adding an instrument is a
        database row instead of a redeploy of this service."""
        handler = recorder(body=[{"symbol": "TEST-THYAO", "data_symbol": "THYAO.IS"}])
        products = sinks.fetch_products(client_for(handler))
        assert products[0]["data_symbol"] == "THYAO.IS"
        assert handler.calls[0].url.path.endswith("/investment/products")


class TestMarketHours:
    @pytest.mark.parametrize("hour,expected", [(9, False), (10, True), (17, True), (18, False)])
    def test_bist_continuous_session_window(self, hour, expected):
        moment = datetime(2026, 8, 20, hour, 0, tzinfo=run.ISTANBUL)
        assert ("BIST" in run.open_markets(moment)) is expected

    @pytest.mark.parametrize("hour,expected", [(15, False), (16, True), (22, True), (23, False)])
    def test_us_session_is_tracked_separately(self, hour, expected):
        """A single BIST-hours gate froze every US price at 18:00 TRT, half an
        hour before the US session even opens."""
        moment = datetime(2026, 8, 20, hour, 0, tzinfo=run.ISTANBUL)
        assert ("NASDAQ" in run.open_markets(moment)) is expected

    def test_fx_and_gold_trade_around_the_clock(self):
        night = datetime(2026, 8, 20, 3, 0, tzinfo=run.ISTANBUL)
        assert run.open_markets(night) == {"FX", "COMEX"}

    def test_market_is_open_means_any_market(self):
        """09:00 TRT: BIST shut, FX trading. The old gate called this closed
        and skipped the cycle."""
        nine = datetime(2026, 8, 20, 9, 0, tzinfo=run.ISTANBUL)
        assert run.market_is_open(nine) is True
        assert "BIST" not in run.open_markets(nine)

    def test_weekend_is_closed(self):
        saturday = datetime(2026, 8, 22, 12, 0, tzinfo=run.ISTANBUL)
        assert run.market_is_open(saturday) is False

    def test_utc_input_is_converted_to_istanbul(self):
        """08:00 UTC is 11:00 in Istanbul, inside the session. Comparing UTC
        hours directly would poll three hours off."""
        assert run.market_is_open(datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)) is True


class TestJobGuards:
    def test_a_failing_job_is_caught_and_reported(self):
        """One dead source must not take the whole cycle down."""
        def boom(_client):
            raise RuntimeError("provider down")

        assert "error" in run._guard("quotes", boom, None)

    def test_quotes_are_skipped_when_every_market_is_closed(self, monkeypatch):
        """Polling a closed market rewrites the same closing price forever."""
        monkeypatch.setattr(run, "open_markets", lambda: set())
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        assert run.run_quotes(None) == {"skipped": True}

    def test_only_the_open_markets_are_priced(self, monkeypatch):
        """The whole point of the split: at 12:00 TRT the US is shut, so its
        96 symbols must not cost a request."""
        seen = {}
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST", "FX"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [
            {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST"},
            {"symbol": "AAPL", "data_symbol": "AAPL", "market": "NASDAQ"},
            {"symbol": "USDTRY", "data_symbol": "USDTRY=X", "market": "FX"},
        ])

        def _capture(products):
            seen["symbols"] = [p["symbol"] for p in products]
            return [{"symbol": p["symbol"]} for p in products]

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _capture)
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": len(q)})
        run.run_quotes(None)
        assert seen["symbols"] == ["THYAO", "USDTRY"]

    def test_an_unknown_venue_is_priced_rather_than_dropped(self, monkeypatch):
        """A venue missing from MARKET_HOURS is a gap in configuration. One
        extra request is far easier to notice than an instrument that silently
        never gets a price."""
        seen = {}
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [
            {"symbol": "MYSTERY", "data_symbol": "MYST", "market": "XETRA"},
        ])

        def _capture(products):
            seen["symbols"] = [p["symbol"] for p in products]
            return [{"symbol": "MYSTERY"}]

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _capture)
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 1})
        run.run_quotes(None)
        assert seen["symbols"] == ["MYSTERY"]

    def test_force_overrides_the_market_hours_check(self, monkeypatch):
        monkeypatch.setattr(run, "open_markets", lambda: set())
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda products: [])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        assert run.run_quotes(None, force=True)["fetched"] == 0


class TestCli:
    def _stub_jobs(self, monkeypatch, calls):
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_for(recorder()))
        for name in ("run_quotes", "run_candles", "run_news"):
            monkeypatch.setattr(
                run, name, (lambda n: lambda *a, **k: calls.append(n) or {})(name)
            )

    def test_once_runs_every_job_by_default(self, monkeypatch):
        calls = []
        self._stub_jobs(monkeypatch, calls)
        assert run.main(["--once"]) == 0
        assert calls == ["run_quotes", "run_candles", "run_news"]

    def test_a_selected_job_runs_alone(self, monkeypatch):
        calls = []
        self._stub_jobs(monkeypatch, calls)
        run.main(["--once", "--news"])
        assert calls == ["run_news"]

    def test_several_jobs_can_be_selected(self, monkeypatch):
        calls = []
        self._stub_jobs(monkeypatch, calls)
        run.main(["--once", "--quotes", "--candles"])
        assert calls == ["run_quotes", "run_candles"]

    def test_without_once_the_scheduler_starts(self, monkeypatch):
        started = []
        monkeypatch.setattr(run, "start_scheduler", lambda: started.append(True))
        assert run.main([]) == 0
        assert started == [True]


class TestCycles:
    def test_news_cycle_reports_both_destinations(self, monkeypatch):
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [{"title": "x"}])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {"news_written": 1})
        monkeypatch.setattr(run.sinks, "push_news_to_rag", lambda c, i: 1)
        result = run.run_news(None)
        assert result == {"fetched": 1, "embedded": 1, "news_written": 1}

    def test_kap_cycle_pushes_matched_disclosures_to_the_backend(self, monkeypatch):
        """Same sink as RSS: a disclosure IS market news, it just arrives with
        an issuer attached and a permanent link."""
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "THYAO", "market": "BIST"},
            {"symbol": "AAPL", "market": "NASDAQ"},
        ])
        seen = {}

        def fake_fetch(universe, since, until, client):
            seen["universe"] = universe
            seen["span"] = (since, until)
            return [{"title": "THYAO — bir şey"}]

        monkeypatch.setattr(run.kap_source, "fetch_all", fake_fetch)
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {"news_written": 1})

        assert run.run_kap(None) == {"fetched": 1, "news_written": 1}
        assert seen["universe"] == {"THYAO"}, "only BIST instruments can appear on KAP"

    def test_the_kap_poll_looks_back_over_a_window_not_a_point(self, monkeypatch):
        """A disclosure filed while the previous cycle was mid-flight would
        otherwise fall between two polls. Re-offering a stored one is free."""
        monkeypatch.setenv("INGESTOR_KAP_WINDOW_DAYS", "3")
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        span = {}

        def fake_fetch(universe, since, until, client):
            span["days"] = (until - since).days
            return []

        monkeypatch.setattr(run.kap_source, "fetch_all", fake_fetch)
        run.run_kap(None)
        assert span["days"] == 2

    def test_an_explicit_range_overrides_the_window(self, monkeypatch):
        from datetime import date

        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        span = {}

        def fake_fetch(universe, since, until, client):
            span["range"] = (since, until)
            return []

        monkeypatch.setattr(run.kap_source, "fetch_all", fake_fetch)
        run.run_kap(None, since=date(2026, 3, 1), until=date(2026, 3, 10))
        assert span["range"] == (date(2026, 3, 1), date(2026, 3, 10))

    def test_a_kap_push_failure_still_reports_what_was_fetched(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.kap_source, "fetch_all", lambda *a, **k: [{"title": "x"}])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: None)
        assert run.run_kap(None) == {"fetched": 1}

    def test_candle_cycle_reports_new_bars(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: [1, 2, 3])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"candles_written": 2})
        assert run.run_candles(None) == {"fetched": 3, "candles_written": 2}

    def test_push_failure_leaves_the_cycle_reporting_what_it_fetched(self, monkeypatch):
        """Bir de: yazılan sayısı sıfır olarak BİLDİRİLİR, hiç bildirilmez değil.

        Anahtarın düşmesi, çağıranın `.get("candles_written", 0)` ile aynı
        sıfıra ulaşmasını sağlıyordu ama "sıfır bar yazıldı" ile "bu turda bar
        yazma adımı hiç olmadı" arasındaki farkı siliyordu.
        """
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: [1])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: None)
        assert run.run_candles(None) == {"fetched": 1, "candles_written": 0}

    def test_daily_bars_are_pushed_in_chunks(self, monkeypatch):
        """Ölçülen hata: 1.011 enstrüman için 638.968 bar tek gövdede gitti,
        istek zaman aşımına uğradı ve turun tamamı kayboldu -- günlük kapanış
        okuyan tek tüketici olan risk ölçümü herkes için boş kaldı."""
        rows = list(range(run.CANDLE_PUSH_CHUNK * 2 + 7))
        sizes = []

        def _push(client, quotes, candles):
            sizes.append(len(candles))
            return {"candles_written": len(candles)}

        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: rows)
        monkeypatch.setattr(run.sinks, "push_market_data", _push)

        result = run.run_candles(None)
        assert sizes == [run.CANDLE_PUSH_CHUNK, run.CANDLE_PUSH_CHUNK, 7]
        assert result == {"fetched": len(rows), "candles_written": len(rows)}

    def test_one_failing_chunk_does_not_cost_the_others(self, monkeypatch):
        """Parçalamanın asıl kazancı: zaman aşımına uğrayan parça yalnızca
        kendi barlarını götürür. Kapsama denetimi o sembolleri bir sonraki
        açılışta yine eksik bulur ve tekrar dener."""
        rows = list(range(run.CANDLE_PUSH_CHUNK + 3))
        calls = []

        def _push(client, quotes, candles):
            calls.append(len(candles))
            return None if len(calls) == 1 else {"candles_written": len(candles)}

        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: rows)
        monkeypatch.setattr(run.sinks, "push_market_data", _push)

        assert run.run_candles(None) == {"fetched": len(rows), "candles_written": 3}


class TestBackendNewsPush:
    def test_articles_are_posted_to_the_backend(self):
        handler = recorder(body={"news_written": 2})
        items = [{"content_hash": "a" * 64, "title": "T", "source": "D", "published_at": NOW}]
        assert sinks.push_news_to_backend(client_for(handler), items) == {"news_written": 2}
        assert handler.calls[0].url.path.endswith("/market/news/ingest")

    def test_backend_failure_is_swallowed(self):
        """News reaching the corpus but not the dashboard is degraded, not
        broken; raising here would also lose the corpus write."""
        handler = recorder(status=503)
        items = [{"content_hash": "a" * 64, "title": "T", "source": "D", "published_at": NOW}]
        assert sinks.push_news_to_backend(client_for(handler), items) is None


class TestScheduler:
    def test_jobs_are_registered_and_a_warm_start_runs_first(self, monkeypatch):
        """A cold start with an empty database would otherwise show nothing
        until the first tick, which on the news job is fifteen minutes."""
        added, started, warmed = [], [], []

        class FakeScheduler:
            def __init__(self, timezone=None):
                pass

            def add_job(self, fn, trigger, **kwargs):
                added.append((kwargs.get("id"), trigger))

            def start(self):
                started.append(True)

        import ingestor.run as run_module

        monkeypatch.setitem(
            __import__("sys").modules,
            "apscheduler.schedulers.blocking",
            type("m", (), {"BlockingScheduler": FakeScheduler}),
        )
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_for(recorder()))
        monkeypatch.setattr(run_module, "run_quotes", lambda *a, **k: warmed.append("q"))
        # Sohbetin anlık fiyat sorduğu uç nokta; testte gerçek soket açılmasın.
        monkeypatch.setattr(
            run_module.refresh_server, "serve_in_background", lambda *a, **k: None
        )
        monkeypatch.setattr(run_module, "run_news", lambda *a, **k: warmed.append("n"))

        run_module.start_scheduler()

        assert dict(added) == {
            # İki katman: şerit sık (30s), hisseler seyrek (15dk). Tek bir
            # `quotes` işi vardı ve bütün evreni 30 saniyede bir çekiyordu.
            "quotes_band": "interval", "quotes_bulk": "interval",
            "news": "interval",
            # Gün içi barlar, toplu turla aynı ritimde.
            "candles_intraday": "interval",
            "candles": "cron", "fundamentals": "cron",
            # Vadeli hesap faizi, gün dönümünden hemen sonra.
            "interest": "cron",
            # A one-shot, not part of the warm start: `fetch_candles` is
            # per-symbol, so a cold-start backfill is ~190 sequential provider
            # calls. Handing it to the scheduler keeps boot from blocking on it.
            "candle-backfill": "date",
            # Aynı gerekçe: haftalık ve aylık grafikler bir günlük gün içi
            # veriyle çizilemiyor, otuz günlük pencere de tek seferlik.
            "intraday-backfill": "date",
            # Isı haritası piyasa değerine göre boyutlanıyor; gecelik işi
            # beklemek S&P sekmesinin bir gün boş kalması demek.
            "fundamentals-backfill": "date",
            # Geri doldurmadan AYRI: o "hiç geçmişi yok"u, bu "geçmişi var
            # ama eski"yi cevaplıyor. Commit'lenmiş taban verisiyle açılan
            # bir klonda geri doldurma haklı olarak atlıyor ve bu iş
            # olmasaydı 19:15 cron'una kadar hiçbir şey çalışmazdı.
            "candle-topup": "date",
            # Piyasa saatlerine bağlı DEĞİL: fiyatı en çok etkileyen
            # bildirimler kapanıştan sonra ve açılıştan önce yayımlanıyor.
            "kap": "interval",
        }
        assert warmed == ["q", "n"]
        assert started == [True]


class TestEntrypoint:
    def test_module_runs_as_a_script(self, monkeypatch):
        """`python -m ingestor.run` is the container command."""
        monkeypatch.setattr(run, "start_scheduler", lambda: None)
        assert run.main([]) == 0


class TestRateLimitBackoff:
    """"Without getting stopped" means backing off when asked, not pretending
    to be a browser."""

    def setup_method(self):
        run._backoff_step = 0

    def teardown_method(self):
        run._backoff_step = 0

    def test_interval_starts_at_the_configured_value(self):
        """Onbeş dakika: geri çekilme merdiveninin tabanı toplu turun kendisi.
        Şerit ayrı bir işte ve bu merdivenden etkilenmiyor."""
        assert run.current_interval_seconds() == 300

    def test_a_rate_limit_widens_the_interval(self, monkeypatch):
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])

        def _rate_limited(_products):
            raise RuntimeError("HTTP Error 429: Too Many Requests")

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _rate_limited)
        result = run.run_quotes(None, force=True)
        assert result == {"rate_limited": True}
        assert run.current_interval_seconds() > 300

    def test_backoff_is_bounded(self, monkeypatch):
        for _ in range(10):
            run._note_rate_limit()
        assert run.current_interval_seconds() == 300 * run.config.BACKOFF_LADDER[-1]

    def test_a_clean_cycle_resets_the_interval(self, monkeypatch):
        run._note_rate_limit()
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda p: [])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        run.run_quotes(None, force=True)
        assert run.current_interval_seconds() == 300

    def test_a_non_rate_limit_error_still_propagates(self, monkeypatch):
        """Only a 429 means "slow down". Everything else is a real fault and
        must not be silently converted into a backoff."""
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])

        def _boom(_products):
            raise RuntimeError("connection reset")

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _boom)
        with pytest.raises(RuntimeError, match="connection reset"):
            run.run_quotes(None, force=True)

    def test_cycle_reports_its_duration(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda p: [])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        assert "seconds" in run.run_quotes(None, force=True)


class TestFundamentalsCycle:
    def test_rows_are_pushed(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_fundamentals", lambda p: [{"symbol": "THYAO"}])
        monkeypatch.setattr(run.sinks, "push_fundamentals",
                            lambda c, r: {"fundamentals_written": 1})
        assert run.run_fundamentals(None) == {"fetched": 1, "fundamentals_written": 1}

    def test_push_failure_still_reports_what_was_fetched(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_fundamentals", lambda p: [{"symbol": "X"}])
        monkeypatch.setattr(run.sinks, "push_fundamentals", lambda c, r: None)
        assert run.run_fundamentals(None) == {"fetched": 1}

    def test_empty_batch_makes_no_request(self):
        handler = recorder()
        assert sinks.push_fundamentals(client_for(handler), []) is None
        assert handler.calls == []

    def test_ingest_failure_is_swallowed(self):
        handler = recorder(status=500)
        assert sinks.push_fundamentals(client_for(handler), [{"symbol": "X"}]) is None


class TestProductCache:
    """At six cycles a minute, an uncached symbol map is six backend round
    trips a minute for a table that changes almost never."""

    def setup_method(self):
        sinks.reset_products_cache()

    def teardown_method(self):
        sinks.reset_products_cache()

    def test_second_call_within_the_ttl_does_not_hit_the_backend(self):
        handler = recorder(body=[{"symbol": "THYAO", "data_symbol": "THYAO.IS"}])
        client = client_for(handler)
        sinks.fetch_products(client)
        sinks.fetch_products(client)
        assert len(handler.calls) == 1

    def test_force_refetches(self):
        handler = recorder(body=[{"symbol": "THYAO", "data_symbol": "THYAO.IS"}])
        client = client_for(handler)
        sinks.fetch_products(client)
        sinks.fetch_products(client, force=True)
        assert len(handler.calls) == 2

    def test_an_expired_cache_refetches(self, monkeypatch):
        handler = recorder(body=[{"symbol": "THYAO", "data_symbol": "THYAO.IS"}])
        client = client_for(handler)
        sinks.fetch_products(client)
        monkeypatch.setattr(sinks, "_products_fetched_at", -10_000.0)
        sinks.fetch_products(client)
        assert len(handler.calls) == 2

    def test_the_cached_value_is_returned_unchanged(self):
        rows = [{"symbol": "THYAO", "data_symbol": "THYAO.IS"}]
        client = client_for(recorder(body=rows))
        assert sinks.fetch_products(client) == rows
        assert sinks.fetch_products(client) == rows


class TestCycleBudget:
    """A cycle that never fits its interval is a configuration problem. The
    scheduler coalesces the overlap, which makes it silent unless it is said
    out loud."""

    def test_an_overrunning_cycle_is_logged(self, monkeypatch, caplog):
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run, "current_interval_seconds", lambda: 0)
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [
            {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST"}])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda products: [{"symbol": "THYAO"}])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        with caplog.at_level("WARNING"):
            run.run_quotes(None)
        assert any("longer than its interval" in r.message for r in caplog.records)

    def test_a_cycle_inside_its_budget_says_nothing(self, monkeypatch, caplog):
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run, "current_interval_seconds", lambda: 3600)
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda products: [])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        with caplog.at_level("WARNING"):
            run.run_quotes(None)
        assert not any("longer than its interval" in r.message for r in caplog.records)


class TestSchedulerJobs:
    """The wrapper APScheduler actually invokes.

    A job that raises on its first tick surfaces hours later as "the ingestor
    stopped", so the body is exercised rather than trusted.
    """

    def test_the_registered_job_opens_a_client_and_runs_the_work(self, monkeypatch):
        registered = []

        class FakeScheduler:
            def __init__(self, **kwargs):
                pass

            def add_job(self, fn, *args, **kwargs):
                registered.append(fn)

            def start(self):
                pass

        import apscheduler.schedulers.blocking as blocking

        monkeypatch.setattr(blocking, "BlockingScheduler", FakeScheduler)
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_for(recorder()))
        monkeypatch.setattr(
            run.refresh_server, "serve_in_background", lambda *a, **k: None
        )
        ran = []
        monkeypatch.setattr(
            run, "_guard", lambda name, fn, client, **kwargs: ran.append(name)
        )

        run.start_scheduler()
        assert registered, "no job was registered"
        registered[0]()
        assert ran, "the registered wrapper never ran its work"


class TestEntryPoint:
    def test_running_as_a_module_exits_with_mains_status(self, monkeypatch):
        """`python -m ingestor.run` is how the container starts it, so the
        guard is the real entry point, not dead code.

        `runpy` executes the module in a FRESH namespace, so patching the
        already-imported `run` has no effect on it. The stubs therefore go on
        the modules it imports, which are shared, and `sys.argv` supplies the
        one-shot flags so nothing schedules or sleeps.
        """
        import runpy
        import sys

        monkeypatch.setattr(sys, "argv", ["ingestor.run", "--once", "--quotes"])
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_for(recorder()))
        monkeypatch.setattr(sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(
            "ingestor.sources.yfinance_source.fetch_quotes", lambda products: []
        )
        monkeypatch.setattr(sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})

        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("ingestor.run", run_name="__main__")
        assert excinfo.value.code == 0


class TestFundamentalsDelivery:
    def test_a_successful_push_returns_the_backend_reply(self, monkeypatch):
        """Only the failure path was covered, so a working push was never
        exercised end to end."""
        def handler(request):
            return httpx.Response(200, json={"fundamentals_written": 3})

        result = sinks.push_fundamentals(client_for(handler), [{"symbol": "THYAO"}])
        assert result == {"fundamentals_written": 3}

    def test_an_empty_batch_makes_no_request(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={})

        assert sinks.push_fundamentals(client_for(handler), []) is None
        assert not calls


class TestPartialBatches:
    """`yf.download` swallows per-symbol failures and still returns a frame,
    so a struggling provider shows up as a SHORT batch, never an exception.
    Counting that as success is what let the cycle run six times over budget
    while the backoff ladder sat at step zero."""

    def setup_method(self):
        run._backoff_step = 0

    def teardown_method(self):
        run._backoff_step = 0

    def _products(self, count):
        return [
            {"symbol": f"S{i}", "data_symbol": f"S{i}.IS", "market": "BIST"}
            for i in range(count)
        ]

    def test_a_mostly_empty_batch_widens_the_interval(self, monkeypatch):
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: self._products(100))
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes",
                            lambda p: [{"symbol": "S0"}] * 10)
        monkeypatch.setattr(run.sinks, "push_market_data",
                            lambda c, q, k: {"quotes_written": len(q)})

        run.run_quotes(None)

        assert run.current_interval_seconds() > 30

    def test_a_few_delisted_tickers_are_tolerated(self, monkeypatch):
        """Some symbols never have prices. That is normal, not a signal."""
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: self._products(100))
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes",
                            lambda p: [{"symbol": "S0"}] * 95)
        monkeypatch.setattr(run.sinks, "push_market_data",
                            lambda c, q, k: {"quotes_written": len(q)})

        run.run_quotes(None)

        assert run.current_interval_seconds() == 300

    def test_no_instruments_in_the_open_markets_is_a_skip(self, monkeypatch):
        monkeypatch.setattr(run, "open_markets", lambda: {"NASDAQ"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST"}])
        assert run.run_quotes(None) == {"skipped": True}


class TestQuoteTiers:
    """İki katman: şerit sık, hisseler seyrek.

    Tek bir iş vardı ve bütün evreni 30 saniyede bir çekiyordu. Evren binlerce
    enstrümana çıkarken bu, sağlayıcıya dakikada binlerce istek demek -- ve
    ekranın tepesindeki kur bandının sürekli oynaması için gereken şey bu değil.
    """

    PRODUCTS = [
        {"symbol": "USDTRY", "data_symbol": "USDTRY=X", "market": "FX",
         "product_type": "fx"},
        {"symbol": "XU100", "data_symbol": "XU100.IS", "market": "BIST",
         "product_type": "index"},
        {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST",
         "product_type": "stock"},
    ]

    def _wire(self, monkeypatch):
        seen = []
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: list(self.PRODUCTS))
        monkeypatch.setattr(
            run.yfinance_source, "fetch_quotes",
            lambda p: seen.append([x["symbol"] for x in p]) or [],
        )
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0}
        )
        return seen

    def test_the_band_tier_takes_fx_and_the_index_only(self, monkeypatch):
        seen = self._wire(monkeypatch)
        run.run_quotes(None, force=True, tier="band")
        assert seen == [["USDTRY", "XU100"]]

    def test_the_bulk_tier_takes_the_stocks(self, monkeypatch):
        seen = self._wire(monkeypatch)
        run.run_quotes(None, force=True, tier="bulk")
        assert seen == [["THYAO"]]

    def test_all_is_still_everything(self, monkeypatch):
        """Tek seferlik çalıştırmalar (`--once`) bölmeden çeker."""
        seen = self._wire(monkeypatch)
        run.run_quotes(None, force=True, tier="all")
        assert seen == [["USDTRY", "XU100", "THYAO"]]

    def test_an_empty_tier_is_a_skip(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST",
             "product_type": "stock"},
        ])
        assert run.run_quotes(None, force=True, tier="band") == {"skipped": True}


class TestInterestJob:
    """Vadeli hesap faizini backend'e işletir.

    Faizi burada HESAPLAMIYOR: para bankacılık modülünün işi ve bu servisin
    veritabanı kredensiyeli yok.
    """

    def test_it_forwards_the_trigger_and_reports(self, monkeypatch):
        monkeypatch.setattr(
            run.sinks, "trigger_interest_accrual", lambda c: {"accrued": 2},
        )
        assert run.run_interest(None) == {"accrued": 2}

    def test_an_empty_reply_is_tolerated(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "trigger_interest_accrual", lambda c: None)
        assert run.run_interest(None) == {}

    def test_the_sink_posts_to_the_backend(self):
        handler = recorder(body={"accrued": 1})
        assert sinks.trigger_interest_accrual(client_for(handler)) == {"accrued": 1}
        assert handler.calls[0].url.path.endswith("/banking/interest/accrue")


class TestIntradayCandles:
    """5 dakikalık barlar; portföy performansının "Gün" görünümü bunu okuyor.

    Barlar sağlayıcıdan GERÇEK OHLC olarak geliyor -- anlık fiyattan bar
    üretmek açılış, yüksek ve düşük değerlerini uydurmak olurdu ve mum grafiği
    o uydurma fitilleri gerçekmiş gibi çizerdi.
    """

    def test_nothing_wanted_is_a_skip(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_intraday_symbols", lambda c: set())
        assert run.run_intraday_candles(None) == {"skipped": True}

    def test_only_the_wanted_symbols_are_fetched(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            run.sinks, "fetch_intraday_symbols", lambda c: {"THYAO"},
        )
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "THYAO", "data_symbol": "THYAO.IS"},
            {"symbol": "GARAN", "data_symbol": "GARAN.IS"},
        ])

        def _fetch(products, days=400, interval="1d"):
            seen["symbols"] = [p["symbol"] for p in products]
            seen["interval"] = interval
            seen["days"] = days
            return [{"symbol": "THYAO"}]

        monkeypatch.setattr(run.yfinance_source, "fetch_candles", _fetch)
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"candles_written": len(k)},
        )
        result = run.run_intraday_candles(None)
        assert seen == {"symbols": ["THYAO"], "interval": "5m", "days": 1}
        assert result == {"fetched": 1, "candles_written": 1}

    def test_the_sink_asks_the_backend_which_symbols(self):
        """Kimin neyi tuttuğu uygulamanın bilgisi; bu servis onu bilmiyor."""
        handler = recorder(body={"symbols": ["THYAO", "USDTRY"]})
        got = sinks.fetch_intraday_symbols(client_for(handler))
        assert got == {"THYAO", "USDTRY"}
        assert handler.calls[0].url.path.endswith("/candles/intraday-symbols")

    def test_an_empty_reply_is_an_empty_set(self):
        handler = recorder(body={})
        assert sinks.fetch_intraday_symbols(client_for(handler)) == set()


class TestIntradayBackfill:
    """Derin gün içi pencere: açılışta bir kez.

    Haftalık ve aylık grafikler 5 dakikalık barların 15 dakikalık ve saatlik
    kovalarından çiziliyor; bir günlük veri onlara yetmiyor. Periyodik iş bunu
    yapmıyor -- otuz günü beş dakikada bir yeniden çekmek, değişmeyen barları
    durmadan yeniden yazmak olurdu.
    """

    def test_it_asks_for_the_configured_window(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(run.sinks, "fetch_intraday_symbols", lambda c: {"THYAO"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "THYAO", "data_symbol": "THYAO.IS"},
        ])

        def _fetch(products, days=400, interval="1d"):
            seen["days"] = days
            seen["interval"] = interval
            return []

        monkeypatch.setattr(run.yfinance_source, "fetch_candles", _fetch)
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {})
        run.backfill_intraday(None)
        assert seen == {"days": config.intraday_history_days(), "interval": "5m"}

    def test_bars_are_pushed_in_chunks(self, monkeypatch):
        """Otuz günlük geri doldurma 26 sembol için ~94.000 bar; tek gövdede
        göndermek zaman aşımına açık tek bir adım olurdu."""
        pushed = []
        monkeypatch.setattr(run.sinks, "fetch_intraday_symbols", lambda c: {"THYAO"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "THYAO", "data_symbol": "THYAO.IS"},
        ])
        rows = [{"symbol": "THYAO", "n": n} for n in range(run.CANDLE_PUSH_CHUNK + 25)]
        monkeypatch.setattr(
            run.yfinance_source, "fetch_candles", lambda *a, **k: rows,
        )
        monkeypatch.setattr(
            run.sinks, "push_market_data",
            lambda c, q, k: pushed.append(len(k)) or {"candles_written": len(k)},
        )
        result = run.backfill_intraday(None)
        assert pushed == [run.CANDLE_PUSH_CHUNK, 25]
        assert result["candles_written"] == len(rows)


class TestIntradayHistoryDays:
    def test_thirty_days_by_default(self):
        assert config.intraday_history_days() == 30

    def test_it_is_capped_at_the_providers_window(self, monkeypatch):
        """Sağlayıcı gün içi barları ~60 gün geriye veriyor; üstünü istemek
        boş döner."""
        monkeypatch.setenv("INGESTOR_INTRADAY_HISTORY_DAYS", "900")
        assert config.intraday_history_days() == 60

    def test_it_has_a_floor(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_INTRADAY_HISTORY_DAYS", "0")
        assert config.intraday_history_days() == 1


class TestFundamentalsBackfill:
    """Temel verisi hiç olmayan enstrümanlar; açılışta bir kez.

    Isı haritasının kutu boyutu piyasa değerinden geliyor. Migration 0019
    evreni 190'dan 1009'a çıkardı ama gecelik iş henüz üzerlerinden geçmedi:
    S&P sekmesi o gün boyunca boş kalırdı.
    """

    def test_nothing_missing_is_a_skip(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_missing_fundamentals", lambda c: set())
        assert run.backfill_fundamentals(None) == {"skipped": True}

    def test_only_the_missing_symbols_are_fetched(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            run.sinks, "fetch_missing_fundamentals", lambda c: {"AAPL"},
        )
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "AAPL", "data_symbol": "AAPL"},
            {"symbol": "MSFT", "data_symbol": "MSFT"},
        ])
        monkeypatch.setattr(
            run.yfinance_source, "fetch_fundamentals",
            lambda products: seen.setdefault(
                "symbols", [p["symbol"] for p in products]
            ) and [] or [{"symbol": "AAPL"}],
        )
        monkeypatch.setattr(
            run.sinks, "push_fundamentals", lambda c, rows: {"fundamentals_written": len(rows)},
        )
        result = run.backfill_fundamentals(None)
        assert seen["symbols"] == ["AAPL"]
        assert result == {"fetched": 1, "fundamentals_written": 1}

    def test_rows_are_pushed_in_chunks(self, monkeypatch):
        """Tek gövdede gönderildiğinde bir tek geçersiz değer 828 satırın
        tamamını düşürüyordu."""
        pushed = []
        monkeypatch.setattr(
            run.sinks, "fetch_missing_fundamentals", lambda c: {"A"},
        )
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "A", "data_symbol": "A"},
        ])
        rows = [{"symbol": f"S{i}"} for i in range(run.FUNDAMENTALS_PUSH_CHUNK + 7)]
        monkeypatch.setattr(run.yfinance_source, "fetch_fundamentals", lambda p: rows)
        monkeypatch.setattr(
            run.sinks, "push_fundamentals",
            lambda c, chunk: pushed.append(len(chunk)) or {"fundamentals_written": len(chunk)},
        )
        result = run.backfill_fundamentals(None)
        assert pushed == [run.FUNDAMENTALS_PUSH_CHUNK, 7]
        assert result["fundamentals_written"] == len(rows)

    def test_the_sink_asks_the_backend_which_are_missing(self):
        handler = recorder(body={"symbols": ["AAPL", "MSFT"]})
        got = sinks.fetch_missing_fundamentals(client_for(handler))
        assert got == {"AAPL", "MSFT"}
        assert handler.calls[0].url.path.endswith("/market/fundamentals/missing")

    def test_an_empty_reply_is_an_empty_set(self):
        assert sinks.fetch_missing_fundamentals(client_for(recorder(body={}))) == set()
