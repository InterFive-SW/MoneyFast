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
    def test_continuous_session_window(self, hour, expected):
        moment = datetime(2026, 8, 20, hour, 0, tzinfo=run.ISTANBUL)
        assert run.market_is_open(moment) is expected

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

    def test_quotes_are_skipped_when_the_market_is_closed(self, monkeypatch):
        """Polling a closed market rewrites the same closing price forever."""
        monkeypatch.setattr(run, "market_is_open", lambda: False)
        assert run.run_quotes(None) == {"skipped": True}

    def test_force_overrides_the_market_hours_check(self, monkeypatch):
        monkeypatch.setattr(run, "market_is_open", lambda: False)
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

    def test_candle_cycle_reports_new_bars(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: [1, 2, 3])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"candles_written": 2})
        assert run.run_candles(None) == {"fetched": 3, "candles_written": 2}

    def test_push_failure_leaves_the_cycle_reporting_what_it_fetched(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: [1])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: None)
        assert run.run_candles(None) == {"fetched": 1}


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
        monkeypatch.setattr(run_module, "run_news", lambda *a, **k: warmed.append("n"))

        run_module.start_scheduler()

        assert dict(added) == {
            "quotes": "interval", "news": "interval",
            "candles": "cron", "fundamentals": "cron",
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
        assert run.current_interval_seconds() == 10

    def test_a_rate_limit_widens_the_interval(self, monkeypatch):
        monkeypatch.setattr(run, "market_is_open", lambda: True)
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])

        def _rate_limited(_products):
            raise RuntimeError("HTTP Error 429: Too Many Requests")

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _rate_limited)
        result = run.run_quotes(None, force=True)
        assert result == {"rate_limited": True}
        assert run.current_interval_seconds() > 10

    def test_backoff_is_bounded(self, monkeypatch):
        for _ in range(10):
            run._note_rate_limit()
        assert run.current_interval_seconds() == 10 * run.config.BACKOFF_LADDER[-1]

    def test_a_clean_cycle_resets_the_interval(self, monkeypatch):
        run._note_rate_limit()
        monkeypatch.setattr(run, "market_is_open", lambda: True)
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda p: [])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        run.run_quotes(None, force=True)
        assert run.current_interval_seconds() == 10

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
        monkeypatch.setattr(run, "market_is_open", lambda: True)
        monkeypatch.setattr(run, "current_interval_seconds", lambda: 0)
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda products: [])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        with caplog.at_level("WARNING"):
            run.run_quotes(None)
        assert any("longer than its interval" in r.message for r in caplog.records)

    def test_a_cycle_inside_its_budget_says_nothing(self, monkeypatch, caplog):
        monkeypatch.setattr(run, "market_is_open", lambda: True)
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
