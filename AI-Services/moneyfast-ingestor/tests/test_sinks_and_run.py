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

from ingestor import run, sinks
from ingestor.sources import x_source

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
            client_for(handler),
            [{"symbol": "X", "price": 1.0, "market_timestamp": NOW}],
            [],
        )
        assert "Authorization" not in handler.calls[0].headers


class TestSerialisation:
    def test_datetimes_become_iso_strings(self):
        """json.dumps cannot serialise a datetime, and httpx uses json."""
        payload = sinks._serialise({"at": NOW, "rows": [{"t": NOW}]})
        assert payload["at"] == NOW.isoformat()
        assert payload["rows"][0]["t"] == NOW.isoformat()

    def test_other_values_pass_through(self):
        assert sinks._serialise({"n": 1, "s": "x", "b": True}) == {
            "n": 1,
            "s": "x",
            "b": True,
        }


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
            client_for(handler),
            [{"symbol": "X", "price": 1.0, "market_timestamp": NOW}],
            [],
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
            {
                "content_hash": "a" * 64,
                "title": "T1",
                "summary": "S1",
                "source": "Dünya",
                "url": "u",
                "related_symbols": ["THYAO"],
                "published_at": NOW,
            },
            {
                "content_hash": "b" * 64,
                "title": "T2",
                "summary": "S2",
                "source": "Dünya",
                "url": "u",
                "related_symbols": [],
                "published_at": NOW,
            },
        ]
        assert sinks.push_news_to_rag(client_for(handler), items) == 2
        assert len(handler.calls) == 2

    def test_duplicates_reported_by_rag_are_not_counted(self):
        """Re-offering a feed must be a no-op, and the count is what proves
        it stayed one."""
        handler = recorder(body={"status": "duplicate"})
        items = [
            {
                "content_hash": "a" * 64,
                "title": "T",
                "summary": "S",
                "source": "D",
                "published_at": NOW,
            }
        ]
        assert sinks.push_news_to_rag(client_for(handler), items) == 0

    def test_first_ticker_is_carried_and_the_rest_are_dropped(self):
        """The corpus schema holds one ticker per document. Multi-tagged
        stories stay findable by text."""
        handler = recorder(body={"status": "ingested"})
        items = [
            {
                "content_hash": "a" * 64,
                "title": "T",
                "summary": "S",
                "source": "D",
                "related_symbols": ["THYAO", "ASELS"],
                "published_at": NOW,
            }
        ]
        sinks.push_news_to_rag(client_for(handler), items)
        body = json.loads(handler.calls[0].content)
        assert body["ticker"] == "THYAO"

    def test_article_without_a_summary_falls_back_to_its_title(self):
        handler = recorder(body={"status": "ingested"})
        items = [
            {
                "content_hash": "a" * 64,
                "title": "Sadece başlık",
                "summary": None,
                "source": "D",
                "published_at": NOW,
            }
        ]
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
            {
                "content_hash": "a" * 64,
                "title": "T1",
                "summary": "S",
                "source": "D",
                "published_at": NOW,
            },
            {
                "content_hash": "b" * 64,
                "title": "T2",
                "summary": "S",
                "source": "D",
                "published_at": NOW,
            },
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
    @pytest.mark.parametrize(
        "hour,expected", [(9, False), (10, True), (17, True), (18, False)]
    )
    def test_bist_continuous_session_window(self, hour, expected):
        moment = datetime(2026, 8, 20, hour, 0, tzinfo=run.ISTANBUL)
        assert ("BIST" in run.open_markets(moment)) is expected

    @pytest.mark.parametrize(
        "hour,expected", [(15, False), (16, True), (22, True), (23, False)]
    )
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
        assert (
            run.market_is_open(datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)) is True
        )


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
        monkeypatch.setattr(
            run.sinks,
            "fetch_products",
            lambda client: [
                {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST"},
                {"symbol": "AAPL", "data_symbol": "AAPL", "market": "NASDAQ"},
                {"symbol": "USDTRY", "data_symbol": "USDTRY=X", "market": "FX"},
            ],
        )

        def _capture(products):
            seen["symbols"] = [p["symbol"] for p in products]
            return [{"symbol": p["symbol"]} for p in products]

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _capture)
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": len(q)}
        )
        run.run_quotes(None)
        assert seen["symbols"] == ["THYAO", "USDTRY"]

    def test_an_unknown_venue_is_priced_rather_than_dropped(self, monkeypatch):
        """A venue missing from MARKET_HOURS is a gap in configuration. One
        extra request is far easier to notice than an instrument that silently
        never gets a price."""
        seen = {}
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(
            run.sinks,
            "fetch_products",
            lambda client: [
                {"symbol": "MYSTERY", "data_symbol": "MYST", "market": "XETRA"},
            ],
        )

        def _capture(products):
            seen["symbols"] = [p["symbol"] for p in products]
            return [{"symbol": "MYSTERY"}]

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _capture)
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 1}
        )
        run.run_quotes(None)
        assert seen["symbols"] == ["MYSTERY"]

    def test_force_overrides_the_market_hours_check(self, monkeypatch):
        monkeypatch.setattr(run, "open_markets", lambda: set())
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda products: [])
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0}
        )
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

    def test_x_job_can_be_selected_independently(self, monkeypatch):
        calls = []
        self._stub_jobs(monkeypatch, calls)
        monkeypatch.setattr(
            run, "run_x_social", lambda *a, **k: calls.append("run_x_social") or {}
        )
        run.main(["--once", "--x-social"])
        assert calls == ["run_x_social"]

    def test_without_once_the_scheduler_starts(self, monkeypatch):
        started = []
        monkeypatch.setattr(run, "start_scheduler", lambda: started.append(True))
        assert run.main([]) == 0
        assert started == [True]


class TestCycles:
    def test_news_cycle_reports_both_destinations(self, monkeypatch):
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [{"title": "x"}])
        monkeypatch.setattr(
            run.sinks, "push_news_to_backend", lambda c, i: {"news_written": 1}
        )
        monkeypatch.setattr(run.sinks, "push_news_to_rag", lambda c, i: 1)
        result = run.run_news(None)
        assert result == {"fetched": 1, "embedded": 1, "news_written": 1}

    def test_candle_cycle_reports_new_bars(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(
            run.yfinance_source, "fetch_candles", lambda p, days: [1, 2, 3]
        )
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"candles_written": 2}
        )
        assert run.run_candles(None) == {"fetched": 3, "candles_written": 2}

    def test_push_failure_leaves_the_cycle_reporting_what_it_fetched(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_candles", lambda p, days: [1])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: None)
        assert run.run_candles(None) == {"fetched": 1}


class TestBackendNewsPush:
    def test_articles_are_posted_to_the_backend(self):
        handler = recorder(body={"news_written": 2})
        items = [
            {"content_hash": "a" * 64, "title": "T", "source": "D", "published_at": NOW}
        ]
        assert sinks.push_news_to_backend(client_for(handler), items) == {
            "news_written": 2
        }
        assert handler.calls[0].url.path.endswith("/market/news/ingest")

    def test_backend_failure_is_swallowed(self):
        """News reaching the corpus but not the dashboard is degraded, not
        broken; raising here would also lose the corpus write."""
        handler = recorder(status=503)
        items = [
            {"content_hash": "a" * 64, "title": "T", "source": "D", "published_at": NOW}
        ]
        assert sinks.push_news_to_backend(client_for(handler), items) is None


class TestSocialPush:
    def test_social_batch_is_authenticated_and_uses_dedicated_endpoint(
        self, monkeypatch
    ):
        monkeypatch.setenv("BACKEND_API_KEY", "service-secret")
        handler = recorder(body={"posts_inserted": 1})
        result = sinks.push_social_to_backend(
            client_for(handler),
            [{"external_account_id": "100"}],
            [{"external_post_id": "200"}],
        )
        assert result == {"posts_inserted": 1}
        assert handler.calls[0].url.path.endswith("/market/social/ingest")
        assert handler.calls[0].headers["Authorization"] == "Bearer service-secret"

    def test_empty_social_batch_makes_no_request(self):
        handler = recorder()
        assert sinks.push_social_to_backend(client_for(handler), [], []) is None
        assert not handler.calls

    def test_backend_failure_is_nonfatal_and_does_not_log_secret(
        self, monkeypatch, caplog
    ):
        monkeypatch.setenv("BACKEND_API_KEY", "must-not-appear")
        with caplog.at_level("ERROR"):
            assert (
                sinks.push_social_to_backend(
                    client_for(recorder(status=503)),
                    [{"external_account_id": "100"}],
                    [],
                )
                is None
            )
        assert "must-not-appear" not in caplog.text


class TestBoundedSocialDelivery:
    @staticmethod
    def account(external_id):
        return {"external_account_id": external_id, "platform": "x"}

    @staticmethod
    def posts(external_id, count):
        return [
            {
                "account_external_id": external_id,
                "external_post_id": str(index),
            }
            for index in range(count)
        ]

    def test_exactly_one_thousand_posts_are_split_below_the_contract_limit(self):
        def handler(request):
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "accounts_duplicate": 1,
                    "posts_inserted": len(body["posts"]),
                },
            )

        client = client_for(handler)
        result = sinks.deliver_social_batches(
            client,
            [self.account("100")],
            self.posts("100", 1_000),
            post_batch_size=500,
        )
        assert result["requests_succeeded"] == 2
        assert result["posts_inserted"] == 1_000
        assert result["account_delivery"]["100"]["complete"] is True
        assert result["delivery_attempted"] is True
        assert result["delivery_complete"] is True
        assert result["delivery_partial"] is False

    def test_zero_resolved_accounts_means_no_delivery_attempted(self):
        result = sinks.deliver_social_batches(client_for(recorder()), [], [])
        assert result["delivery_attempted"] is False
        assert result["delivery_complete"] is False
        assert result["delivery_partial"] is False
        assert result["requests_succeeded"] == 0
        assert result["requests_failed"] == 0

    def test_account_only_delivery_is_attempted_and_complete(self):
        result = sinks.deliver_social_batches(
            client_for(
                lambda request: httpx.Response(200, json={"accounts_duplicate": 1})
            ),
            [self.account("100")],
            [],
        )
        assert result["delivery_attempted"] is True
        assert result["delivery_complete"] is True
        assert result["delivery_partial"] is False
        assert result["requests_succeeded"] == 1

    def test_more_than_one_thousand_never_creates_an_oversized_request(self):
        sizes = []

        def handler(request):
            body = json.loads(request.content)
            sizes.append(len(body["posts"]))
            return httpx.Response(200, json={"posts_inserted": len(body["posts"])})

        result = sinks.deliver_social_batches(
            client_for(handler),
            [self.account("100")],
            self.posts("100", 1_201),
            post_batch_size=500,
        )
        assert sizes == [500, 500, 201]
        assert result["posts_inserted"] == 1_201

    def test_middle_chunk_failure_isolated_from_an_independent_account(self):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            if calls == 2:
                return httpx.Response(503)
            body = json.loads(request.content)
            return httpx.Response(200, json={"posts_inserted": len(body["posts"])})

        result = sinks.deliver_social_batches(
            client_for(handler),
            [self.account("100"), self.account("200")],
            self.posts("100", 5) + self.posts("200", 2),
            post_batch_size=3,
        )
        assert result["account_delivery"]["100"]["complete"] is False
        assert result["account_delivery"]["200"]["complete"] is True
        assert result["requests_failed"] == 1
        assert result["posts_inserted"] == 5
        assert result["delivery_attempted"] is True
        assert result["delivery_complete"] is False
        assert result["delivery_partial"] is True

    def test_middle_chunk_failure_on_single_account_is_failed_not_partial(self):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            if calls == 2:
                return httpx.Response(503)
            return httpx.Response(200, json={"posts_inserted": 3})

        result = sinks.deliver_social_batches(
            client_for(handler),
            [self.account("100")],
            self.posts("100", 5),
            post_batch_size=3,
        )
        assert result["delivery_attempted"] is True
        assert result["delivery_complete"] is False
        assert result["delivery_partial"] is False
        assert result["account_delivery"]["100"]["complete"] is False

    def test_failed_chunk_can_replay_idempotently_and_aggregate_duplicates(self):
        first_calls = 0

        def first_handler(request):
            nonlocal first_calls
            first_calls += 1
            if first_calls == 2:
                return httpx.Response(500)
            return httpx.Response(200, json={"posts_inserted": 2})

        first = sinks.deliver_social_batches(
            client_for(first_handler),
            [self.account("100")],
            self.posts("100", 4),
            post_batch_size=2,
        )
        replay = sinks.deliver_social_batches(
            client_for(
                lambda request: httpx.Response(
                    200,
                    json={"posts_duplicate": len(json.loads(request.content)["posts"])},
                )
            ),
            [self.account("100")],
            self.posts("100", 4),
            post_batch_size=2,
        )
        assert first["account_delivery"]["100"]["complete"] is False
        assert replay["posts_duplicate"] == 4
        assert replay["account_delivery"]["100"]["complete"] is True

    @pytest.mark.parametrize("size", [0, 1_001])
    def test_invalid_delivery_sizes_fail_before_network(self, size):
        handler = recorder()
        with pytest.raises(ValueError, match="outside backend limits"):
            sinks.deliver_social_batches(
                client_for(handler),
                [self.account("100")],
                [],
                post_batch_size=size,
            )
        assert not handler.calls

    def test_posts_cannot_reference_an_absent_account(self):
        with pytest.raises(ValueError, match="absent"):
            sinks.deliver_social_batches(
                client_for(recorder()),
                [self.account("100")],
                self.posts("200", 1),
            )

    def test_direct_sink_refuses_oversized_payload_before_network(self):
        handler = recorder()
        with pytest.raises(ValueError, match="post batch"):
            sinks.push_social_to_backend(
                client_for(handler),
                [self.account("100")],
                self.posts("100", 1_001),
            )
        assert not handler.calls

    def test_direct_sink_refuses_too_many_accounts_before_network(self):
        handler = recorder()
        with pytest.raises(ValueError, match="account batch"):
            sinks.push_social_to_backend(
                client_for(handler),
                [self.account(str(index)) for index in range(101)],
                [],
            )
        assert not handler.calls

    def test_delivery_rejects_duplicate_account_ids(self):
        with pytest.raises(ValueError, match="unique external ids"):
            sinks.deliver_social_batches(
                client_for(recorder()),
                [self.account("100"), self.account("100")],
                [],
            )

    def test_malformed_unresolved_field_is_not_aggregated(self):
        result = sinks.deliver_social_batches(
            client_for(
                lambda request: httpx.Response(
                    200, json={"unresolved": {"unexpected": "object"}}
                )
            ),
            [self.account("100")],
            [],
        )
        assert result["unresolved"] == []


class TestXCycle:
    @staticmethod
    def enable(monkeypatch):
        monkeypatch.setenv("X_INGEST_ENABLED", "true")
        monkeypatch.setenv("X_BEARER_TOKEN", "secret")
        monkeypatch.setenv(
            "X_MONITORED_ACCOUNTS_JSON",
            '[{"handle":"test_media","source_type":"financial_media","trust_score":0.5}]',
        )

    def test_disabled_feature_performs_no_collection(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            run.x_source, "collect", lambda *a, **k: called.append(True)
        )
        assert run.run_x_social(None) == {"skipped": True, "reason": "disabled"}
        assert not called

    def test_missing_token_disables_only_x(self, monkeypatch):
        monkeypatch.setenv("X_INGEST_ENABLED", "true")
        monkeypatch.setenv(
            "X_MONITORED_ACCOUNTS_JSON",
            '[{"handle":"test_media","source_type":"financial_media","trust_score":0.5}]',
        )
        assert run.run_x_social(None) == {
            "disabled": True,
            "reason": "missing_token",
        }
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        monkeypatch.setattr(run.sinks, "push_news_to_rag", lambda c, i: 0)
        assert run.run_news(None)["fetched"] == 0

    def test_invalid_configuration_is_non_secret(self, monkeypatch, caplog):
        monkeypatch.setenv("X_INGEST_ENABLED", "true")
        monkeypatch.setenv("X_BEARER_TOKEN", "do-not-log")
        monkeypatch.setenv("X_MONITORED_ACCOUNTS_JSON", "{")
        with caplog.at_level("ERROR"):
            assert run.run_x_social(None) == {
                "disabled": True,
                "reason": "invalid_configuration",
            }
        assert "do-not-log" not in caplog.text

    def test_success_pushes_then_advances_cursor(self, monkeypatch):
        self.enable(monkeypatch)
        batch = x_source.CollectionBatch(
            accounts=[{"external_account_id": "100"}],
            posts=[{"account_external_id": "100", "external_post_id": "200"}],
            state_updates={"test_media": {"since_id": "200"}},
            account_statuses={
                "100": {
                    "configured_handle": "test_media",
                    "collection_complete": True,
                }
            },
            status={"accounts_resolved": 1, "posts_offered": 1},
        )
        monkeypatch.setattr(run.x_source, "load_state", lambda: {})
        monkeypatch.setattr(run.x_source, "collect", lambda *a, **k: batch)
        monkeypatch.setattr(
            run.sinks,
            "deliver_social_batches",
            lambda *a, **k: {
                "posts_inserted": 1,
                "posts_updated": 0,
                "requests_failed": 0,
                "account_delivery": {"100": {"complete": True}},
                "delivery_attempted": True,
                "delivery_complete": True,
                "delivery_partial": False,
            },
        )
        saved = []
        monkeypatch.setattr(
            run.x_source, "save_state", lambda state: saved.append(state) or True
        )
        result = run.run_x_social(None)
        assert result["backend_written"] is True
        assert result["delivery_attempted"] is True
        assert result["delivery_complete"] is True
        assert saved == [batch.state_updates]

    def test_backend_failure_does_not_advance_cursor(self, monkeypatch):
        self.enable(monkeypatch)
        batch = x_source.CollectionBatch(
            accounts=[{"external_account_id": "100"}],
            posts=[],
            state_updates={"test_media": {"since_id": "200"}},
            account_statuses={
                "100": {
                    "configured_handle": "test_media",
                    "collection_complete": True,
                }
            },
            status={"accounts_resolved": 1, "posts_offered": 0},
        )
        monkeypatch.setattr(run.x_source, "load_state", lambda: {})
        monkeypatch.setattr(run.x_source, "collect", lambda *a, **k: batch)
        monkeypatch.setattr(
            run.sinks,
            "deliver_social_batches",
            lambda *a, **k: {
                "requests_failed": 1,
                "account_delivery": {"100": {"complete": False}},
                "delivery_attempted": True,
                "delivery_complete": False,
                "delivery_partial": False,
            },
        )
        saved = []
        monkeypatch.setattr(
            run.x_source, "save_state", lambda state: saved.append(state)
        )
        result = run.run_x_social(None)
        assert result["backend_written"] is False
        assert result["delivery_complete"] is False
        assert not saved

    def test_active_provider_cooldown_makes_no_external_request(self, monkeypatch):
        self.enable(monkeypatch)
        now = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
        state = x_source.provider_cooldown_update(120, now)
        monkeypatch.setattr(run.x_source, "load_state", lambda: state)
        monkeypatch.setattr(run.x_source, "utc_now", lambda: now)
        called = []
        monkeypatch.setattr(
            run.x_source, "collect", lambda *a, **k: called.append(True)
        )
        result = run.run_x_social(None)
        assert result == {
            "skipped": True,
            "reason": "provider_cooldown",
            "retry_after_seconds": 120,
        }
        assert not called

    def test_expired_cooldown_allows_collection(self, monkeypatch):
        self.enable(monkeypatch)
        now = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
        state = x_source.provider_cooldown_update(60, now)
        monkeypatch.setattr(run.x_source, "load_state", lambda: state)
        monkeypatch.setattr(run.x_source, "utc_now", lambda: now.replace(minute=2))
        collected = []
        batch = x_source.CollectionBatch(
            accounts=[],
            posts=[],
            state_updates={},
            account_statuses={},
            status={"accounts_resolved": 0, "posts_offered": 0},
        )
        monkeypatch.setattr(
            run.x_source,
            "collect",
            lambda *a, **k: collected.append(True) or batch,
        )
        monkeypatch.setattr(
            run.sinks,
            "deliver_social_batches",
            lambda *a, **k: {
                "requests_failed": 0,
                "account_delivery": {},
                "delivery_attempted": False,
                "delivery_complete": False,
                "delivery_partial": False,
            },
        )
        result = run.run_x_social(None)
        assert result["backend_written"] is False
        assert result["delivery_attempted"] is False
        assert collected == [True]

    def test_only_fully_delivered_accounts_are_checkpointed(self, monkeypatch):
        self.enable(monkeypatch)
        batch = x_source.CollectionBatch(
            accounts=[
                {"external_account_id": "100"},
                {"external_account_id": "200"},
            ],
            posts=[],
            state_updates={
                "first": {"since_id": "10"},
                "second": {"since_id": "20"},
            },
            account_statuses={
                "100": {"configured_handle": "first"},
                "200": {"configured_handle": "second"},
            },
            status={"accounts_resolved": 2, "posts_offered": 0},
        )
        monkeypatch.setattr(run.x_source, "load_state", lambda: {})
        monkeypatch.setattr(run.x_source, "collect", lambda *a, **k: batch)
        monkeypatch.setattr(
            run.sinks,
            "deliver_social_batches",
            lambda *a, **k: {
                "requests_failed": 1,
                "account_delivery": {
                    "100": {"complete": False},
                    "200": {"complete": True},
                },
                "delivery_attempted": True,
                "delivery_complete": False,
                "delivery_partial": True,
            },
        )
        saved = []
        monkeypatch.setattr(
            run.x_source, "save_state", lambda value: saved.append(value) or True
        )
        result = run.run_x_social(None)
        assert result["backend_written"] is False
        assert result["delivery_partial"] is True
        assert saved == [{"second": {"since_id": "20"}}]

    def test_account_rate_limit_persists_cooldown_before_and_after_delivery(
        self, monkeypatch
    ):
        self.enable(monkeypatch)
        batch = x_source.CollectionBatch(
            accounts=[{"external_account_id": "100"}],
            posts=[],
            state_updates={"test_media": {"since_id": "199"}},
            account_statuses={
                "100": {
                    "configured_handle": "test_media",
                    "collection_complete": False,
                }
            },
            status={
                "accounts_resolved": 1,
                "posts_offered": 0,
                "rate_limited": True,
                "retry_after_seconds": 120,
            },
        )
        monkeypatch.setattr(run.x_source, "load_state", lambda: {})
        monkeypatch.setattr(run.x_source, "collect", lambda *a, **k: batch)
        monkeypatch.setattr(
            run.sinks,
            "deliver_social_batches",
            lambda *a, **k: {
                "requests_failed": 0,
                "account_delivery": {"100": {"complete": True}},
                "delivery_attempted": True,
                "delivery_complete": True,
                "delivery_partial": False,
            },
        )
        saved = []
        monkeypatch.setattr(
            run.x_source, "save_state", lambda value: saved.append(value) or True
        )
        result = run.run_x_social(None)
        assert result["cooldown_saved"] is True
        assert saved[0].keys() == {"_provider"}
        assert saved[1].keys() == {"test_media", "_provider"}

    @pytest.mark.parametrize(
        "error,expected",
        [
            (
                x_source.XRateLimited(30),
                {
                    "rate_limited": True,
                    "retry_after_seconds": 30,
                    "cooldown_saved": True,
                },
            ),
            (
                x_source.XRequestError("failed"),
                {"unavailable": True, "reason": "x_api_error"},
            ),
        ],
    )
    def test_top_level_x_failures_are_structured(self, monkeypatch, error, expected):
        monkeypatch.setenv("X_INGEST_ENABLED", "true")
        monkeypatch.setenv("X_BEARER_TOKEN", "secret")
        monkeypatch.setenv(
            "X_MONITORED_ACCOUNTS_JSON",
            '[{"handle":"test_media","source_type":"financial_media","trust_score":0.5}]',
        )
        monkeypatch.setattr(run.x_source, "load_state", lambda *a: {})
        monkeypatch.setattr(run.x_source, "save_state", lambda *a, **k: True)
        monkeypatch.setattr(
            run.x_source, "collect", lambda *a, **k: (_ for _ in ()).throw(error)
        )
        assert run.run_x_social(None) == expected


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
        monkeypatch.setattr(
            run_module, "run_quotes", lambda *a, **k: warmed.append("q")
        )
        monkeypatch.setattr(run_module, "run_news", lambda *a, **k: warmed.append("n"))

        run_module.start_scheduler()

        assert dict(added) == {
            "quotes": "interval",
            "news": "interval",
            "candles": "cron",
            "fundamentals": "cron",
            # A one-shot, not part of the warm start: `fetch_candles` is
            # per-symbol, so a cold-start backfill is ~190 sequential provider
            # calls. Handing it to the scheduler keeps boot from blocking on it.
            "candle-backfill": "date",
        }
        assert warmed == ["q", "n"]
        assert started == [True]

    def test_x_job_is_registered_only_when_enabled(self, monkeypatch):
        monkeypatch.setenv("X_INGEST_ENABLED", "true")
        added = []

        class FakeScheduler:
            def __init__(self, timezone=None):
                pass

            def add_job(self, fn, trigger, **kwargs):
                added.append((kwargs.get("id"), trigger, kwargs))

            def start(self):
                pass

        monkeypatch.setitem(
            __import__("sys").modules,
            "apscheduler.schedulers.blocking",
            type("m", (), {"BlockingScheduler": FakeScheduler}),
        )
        monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_for(recorder()))
        monkeypatch.setattr(run, "run_quotes", lambda *a, **k: {})
        monkeypatch.setattr(run, "run_news", lambda *a, **k: {})
        run.start_scheduler()
        x_job = next(item for item in added if item[0] == "x-social")
        assert x_job[1] == "interval"
        assert x_job[2]["max_instances"] == 1
        assert x_job[2]["coalesce"] is True


class TestEntrypoint:
    def test_module_runs_as_a_script(self, monkeypatch):
        """`python -m ingestor.run` is the container command."""
        monkeypatch.setattr(run, "start_scheduler", lambda: None)
        assert run.main([]) == 0


class TestRateLimitBackoff:
    """ "Without getting stopped" means backing off when asked, not pretending
    to be a browser."""

    def setup_method(self):
        run._backoff_step = 0

    def teardown_method(self):
        run._backoff_step = 0

    def test_interval_starts_at_the_configured_value(self):
        assert run.current_interval_seconds() == 30

    def test_a_rate_limit_widens_the_interval(self, monkeypatch):
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])

        def _rate_limited(_products):
            raise RuntimeError("HTTP Error 429: Too Many Requests")

        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", _rate_limited)
        result = run.run_quotes(None, force=True)
        assert result == {"rate_limited": True}
        assert run.current_interval_seconds() > 30

    def test_backoff_is_bounded(self, monkeypatch):
        for _ in range(10):
            run._note_rate_limit()
        assert run.current_interval_seconds() == 30 * run.config.BACKOFF_LADDER[-1]

    def test_a_clean_cycle_resets_the_interval(self, monkeypatch):
        run._note_rate_limit()
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda p: [])
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0}
        )
        run.run_quotes(None, force=True)
        assert run.current_interval_seconds() == 30

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
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0}
        )
        assert "seconds" in run.run_quotes(None, force=True)


class TestFundamentalsCycle:
    def test_rows_are_pushed(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(
            run.yfinance_source, "fetch_fundamentals", lambda p: [{"symbol": "THYAO"}]
        )
        monkeypatch.setattr(
            run.sinks, "push_fundamentals", lambda c, r: {"fundamentals_written": 1}
        )
        assert run.run_fundamentals(None) == {"fetched": 1, "fundamentals_written": 1}

    def test_push_failure_still_reports_what_was_fetched(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(
            run.yfinance_source, "fetch_fundamentals", lambda p: [{"symbol": "X"}]
        )
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
        monkeypatch.setattr(
            run.sinks,
            "fetch_products",
            lambda client: [
                {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST"}
            ],
        )
        monkeypatch.setattr(
            run.yfinance_source, "fetch_quotes", lambda products: [{"symbol": "THYAO"}]
        )
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0}
        )
        with caplog.at_level("WARNING"):
            run.run_quotes(None)
        assert any("longer than its interval" in r.message for r in caplog.records)

    def test_a_cycle_inside_its_budget_says_nothing(self, monkeypatch, caplog):
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run, "current_interval_seconds", lambda: 3600)
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda products: [])
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0}
        )
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
        monkeypatch.setattr(
            sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0}
        )

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
        handler = recorder()
        assert sinks.push_fundamentals(client_for(handler), []) is None
        assert not handler.calls


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
        monkeypatch.setattr(
            run.yfinance_source, "fetch_quotes", lambda p: [{"symbol": "S0"}] * 10
        )
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": len(q)}
        )

        run.run_quotes(None)

        assert run.current_interval_seconds() > 30

    def test_a_few_delisted_tickers_are_tolerated(self, monkeypatch):
        """Some symbols never have prices. That is normal, not a signal."""
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: self._products(100))
        monkeypatch.setattr(
            run.yfinance_source, "fetch_quotes", lambda p: [{"symbol": "S0"}] * 95
        )
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": len(q)}
        )

        run.run_quotes(None)

        assert run.current_interval_seconds() == 30

    def test_no_instruments_in_the_open_markets_is_a_skip(self, monkeypatch):
        monkeypatch.setattr(run, "open_markets", lambda: {"NASDAQ"})
        monkeypatch.setattr(
            run.sinks,
            "fetch_products",
            lambda c: [
                {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST"}
            ],
        )
        assert run.run_quotes(None) == {"skipped": True}
