"""The start-up candle backfill.

Daily bars were a 19:15 cron and nothing else, so a clone started in the
morning showed empty charts until that evening. The workaround was committing
7.5 MB of candles as seed data — history for a series this service produces on
its own.

The backfill replaces that, and the coverage check is what makes running it on
every start reasonable rather than wasteful: a first boot fetches the whole
universe, a restart an hour later fetches nothing.
"""

from __future__ import annotations

import httpx
import pytest

from ingestor import config, run, sinks

from test_sinks_and_run import client_for, recorder


class TestCoverageFetch:
    def test_coverage_comes_from_the_backend(self):
        handler = recorder(body={"TEST-THYAO": {"bars": 260, "last": "2026-08-22"}})
        coverage = sinks.fetch_candle_coverage(client_for(handler))

        assert coverage["TEST-THYAO"]["bars"] == 260
        assert handler.calls[0].url.path.endswith("/market/candles/coverage")

    def test_a_failure_reads_as_nothing_covered(self):
        """The safe direction. An unreachable backend must make the backfill
        do the complete thing, not conclude everything is already stored."""
        assert sinks.fetch_candle_coverage(client_for(recorder(status=500))) == {}


class TestBackfillGate:
    def _products(self, *symbols):
        return [{"symbol": s, "data_symbol": s} for s in symbols]

    def test_a_covered_universe_fetches_nothing(self, monkeypatch):
        """The restart case, and the reason this can run on every start."""
        monkeypatch.setattr(
            run.sinks, "fetch_candle_coverage",
            lambda c: {"TEST-A": {"bars": 400}, "TEST-B": {"bars": 120}},
        )
        monkeypatch.setattr(
            run.sinks, "fetch_products", lambda c: self._products("TEST-A", "TEST-B")
        )
        monkeypatch.setattr(
            run.yfinance_source, "fetch_candles",
            lambda *a, **k: pytest.fail("a covered universe must not hit the provider"),
        )

        assert run.backfill_candles(None) == {"fetched": 0, "candles_written": 0}

    def test_an_empty_database_fetches_everything(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_candle_coverage", lambda c: {})
        monkeypatch.setattr(
            run.sinks, "fetch_products", lambda c: self._products("TEST-A", "TEST-B")
        )
        asked = {}

        def _fetch(products, days):
            asked["symbols"] = {p["symbol"] for p in products}
            return [1, 2]

        monkeypatch.setattr(run.yfinance_source, "fetch_candles", _fetch)
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"candles_written": 2}
        )

        assert run.backfill_candles(None)["candles_written"] == 2
        assert asked["symbols"] == {"TEST-A", "TEST-B"}

    def test_only_the_thin_instruments_are_fetched(self, monkeypatch):
        """The migration case: a symbol added to the universe later gets its
        history without anyone remembering to ask for it, and the ones that
        already have a series are left alone."""
        monkeypatch.setattr(
            run.sinks, "fetch_candle_coverage",
            lambda c: {"TEST-OLD": {"bars": 400}, "TEST-NEW": {"bars": 0}},
        )
        monkeypatch.setattr(
            run.sinks, "fetch_products", lambda c: self._products("TEST-OLD", "TEST-NEW")
        )
        asked = {}

        def _fetch(products, days):
            asked["symbols"] = {p["symbol"] for p in products}
            return [1]

        monkeypatch.setattr(run.yfinance_source, "fetch_candles", _fetch)
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"candles_written": 1}
        )

        run.backfill_candles(None)
        assert asked["symbols"] == {"TEST-NEW"}

    def test_the_threshold_is_configurable(self, monkeypatch):
        assert config.CANDLE_MIN_BARS == 60


class TestBackfillScheduling:
    def test_the_backfill_cannot_be_dropped_as_a_misfire(self, monkeypatch):
        """The scheduler does not start until the inline warm start finishes --
        measured at ~80 seconds. APScheduler's default grace is one second, so
        without an explicit opt-out the backfill would be silently skipped and
        a first boot would keep its empty charts."""
        kwargs_seen = []

        class FakeScheduler:
            def __init__(self, **_k):
                pass

            def add_job(self, fn, trigger, **kwargs):
                kwargs_seen.append((kwargs.get("id"), kwargs))

            def start(self):
                pass

        import apscheduler.schedulers.blocking as blocking

        monkeypatch.setattr(blocking, "BlockingScheduler", FakeScheduler)
        monkeypatch.setattr(httpx, "Client", lambda **k: client_for(recorder()))
        monkeypatch.setattr(run, "_guard", lambda *a, **k: None)

        run.start_scheduler()

        backfill = dict(kwargs_seen)["candle-backfill"]
        assert backfill["misfire_grace_time"] is None


class TestSubsetRuns:
    def test_a_subset_narrows_the_provider_call(self, monkeypatch):
        monkeypatch.setattr(
            run.sinks, "fetch_products",
            lambda c: [{"symbol": "TEST-A"}, {"symbol": "TEST-B"}],
        )
        asked = {}

        def _fetch(products, days):
            asked["symbols"] = [p["symbol"] for p in products]
            return [1]

        monkeypatch.setattr(run.yfinance_source, "fetch_candles", _fetch)
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"candles_written": 1}
        )

        run.run_candles(None, symbols={"TEST-B"})
        assert asked["symbols"] == ["TEST-B"]

    def test_a_subset_matching_nothing_skips_the_provider(self, monkeypatch):
        """Guards the case where coverage names a symbol the product list no
        longer has: `yf.download` with an empty list is a wasted round trip."""
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [{"symbol": "TEST-A"}])
        monkeypatch.setattr(
            run.yfinance_source, "fetch_candles",
            lambda *a, **k: pytest.fail("must not call the provider"),
        )

        assert run.run_candles(None, symbols={"TEST-GONE"}) == {
            "fetched": 0, "candles_written": 0
        }

    def test_no_subset_still_means_every_instrument(self, monkeypatch):
        """The nightly cron keeps calling it with no argument."""
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [{"symbol": "TEST-A"}])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: [1, 2])
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"candles_written": 2}
        )

        assert run.run_candles(None) == {"fetched": 2, "candles_written": 2}
