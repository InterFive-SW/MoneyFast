"""Delivery and orchestration.

The ingestor holds no database credential; everything it collects leaves over
HTTP. These tests pin two things: the credential actually travels, and no
single failing destination can take the run down with it.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta

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


class TestKnownNewsIds:
    """`ingestor` backend'e "bunlardan hangileri sende var" diye soruyor.

    KAP listesi her koşuda iki bin bildirim döndürüyor ve her birinin gövdesi
    ayrı bir sayfada. Sormadan çekmek, aynı iki bin sayfayı on beş dakikada
    bir yeniden istemek olurdu.
    """

    def test_ids_come_back_as_a_set_of_numbers(self):
        handler = recorder(body={"source": "KAP", "ids": [1, 2, 3]})
        assert sinks.fetch_known_news_ids(client_for(handler), "KAP") == {1, 2, 3}

    def test_the_source_is_passed_as_a_filter(self):
        handler = recorder(body={"ids": []})
        sinks.fetch_known_news_ids(client_for(handler), "KAP")
        assert "source=KAP" in str(handler.calls[0].url)
        assert handler.calls[0].url.path.endswith("/market/news/known-ids")

    def test_a_failure_reads_as_nothing_stored(self):
        """Boş küme "hiçbiri bende yok" demek ve koşu başına ayrıntı sınırı
        bunun bir akına dönüşmesini engelliyor."""
        assert sinks.fetch_known_news_ids(client_for(recorder(status=500)), "KAP") == set()

    def test_a_missing_key_is_not_a_crash(self):
        handler = recorder(body={"source": "KAP"})
        assert sinks.fetch_known_news_ids(client_for(handler), "KAP") == set()


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


class TestNewsChunking:
    def test_a_large_batch_is_split(self):
        """Measured once already on candles: a single oversized POST timed
        out, the sink returned None, and the cycle reported '0 written' with
        no error anywhere. A six-month KAP backfill is ~15.000 rows."""
        sizes = []

        def handler(request: httpx.Request) -> httpx.Response:
            sizes.append(len(json.loads(request.content)["items"]))
            return httpx.Response(200, json={"news_written": 1})

        items = [
            {"content_hash": str(i) * 64, "title": "t", "source": "KAP", "published_at": NOW}
            for i in range(1100)
        ]
        result = sinks.push_news_to_backend(client_for(handler), items)
        assert sizes == [500, 500, 100]
        assert result["news_written"] == 3

    def test_one_failed_batch_does_not_lose_the_others(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503, json={})
            return httpx.Response(200, json={"news_written": 2})

        items = [
            {"content_hash": str(i) * 64, "title": "t", "source": "KAP", "published_at": NOW}
            for i in range(600)
        ]
        assert sinks.push_news_to_backend(client_for(handler), items)["news_written"] == 2

    def test_every_batch_failing_reports_nothing_delivered(self):
        items = [{"content_hash": "a" * 64, "title": "t", "source": "s", "published_at": NOW}]
        assert sinks.push_news_to_backend(client_for(recorder(status=503)), items) is None


class TestCorpusBackfill:
    """Panoya düşmek, sohbetin bulabilmesi demek değil.

    Ölçüldü: panoda 28.984 KAP bildirimi varken derlemde 147 gövde vardı ve
    THYAO'nun 47 bildiriminin sıfırı gömülüydü. Sebebi tasarımdı -- gövde
    yalnızca YENİ gelenler için çekiliyordu, geriye dönük arşivin gövdesini
    kimse çekmiyordu.
    """

    def _archive_row(self, i):
        return {"content_hash": str(i) * 64, "title": f"THYAO — bildirim {i}",
                "url": f"https://www.kap.org.tr/tr/Bildirim/{i}",
                "related_symbols": ["THYAO"], "published_at": "2026-08-28T20:15:00+00:00"}

    def test_only_disclosures_without_text_are_fetched(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_CORPUS_BUDGET", "10")
        pages = [[self._archive_row(1), self._archive_row(2)], []]
        monkeypatch.setattr(run.sinks, "fetch_news_archive",
                            lambda c, s, l, o: pages.pop(0) if pages else [])
        monkeypatch.setattr(
            run.sinks, "fetch_embedded_urls",
            lambda c, urls: {"https://www.kap.org.tr/tr/Bildirim/1"},
        )
        read = []
        monkeypatch.setattr(run.kap_archive, "fetch_detail",
                            lambda i, c: read.append(i) or {"disclosureBody": ["<p>x</p>"]})
        monkeypatch.setattr(run.sinks, "push_disclosures_to_rag", lambda c, d: len(d))
        assert run.backfill_kap_corpus(None)["embedded"] == 1
        assert read == ["2"], "the one already embedded must not be re-read"

    def test_the_pass_is_budgeted(self, monkeypatch):
        """Gövde başına bir istek, host başına iki saniye. Sınırsız bırakmak
        tek turun saatlerce sürmesi demekti."""
        monkeypatch.setenv("INGESTOR_KAP_CORPUS_BUDGET", "2")
        pages = [[self._archive_row(i) for i in range(5)], []]
        monkeypatch.setattr(run.sinks, "fetch_news_archive",
                            lambda c, s, l, o: pages.pop(0) if pages else [])
        monkeypatch.setattr(run.sinks, "fetch_embedded_urls", lambda c, urls: set())
        monkeypatch.setattr(run.kap_archive, "fetch_detail",
                            lambda i, c: {"disclosureBody": ["<p>x</p>"]})
        monkeypatch.setattr(run.sinks, "push_disclosures_to_rag", lambda c, d: len(d))
        assert run.backfill_kap_corpus(None)["embedded"] == 2

    def test_a_complete_corpus_fetches_nothing(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_news_archive",
                            lambda c, s, l, o: [self._archive_row(1)] if o == 0 else [])
        monkeypatch.setattr(
            run.sinks, "fetch_embedded_urls",
            lambda c, urls: {"https://www.kap.org.tr/tr/Bildirim/1"},
        )

        def refuse(*a, **k):
            pytest.fail("nothing is missing; no body should be fetched")

        monkeypatch.setattr(run.kap_archive, "fetch_detail", refuse)
        assert run.backfill_kap_corpus(None) == {"fetched": 0, "embedded": 0}

    def test_a_zero_budget_switches_the_job_off(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_CORPUS_BUDGET", "0")

        def refuse(*a, **k):
            pytest.fail("the job is switched off")

        monkeypatch.setattr(run.sinks, "fetch_news_archive", refuse)
        assert run.backfill_kap_corpus(None) == {"skipped": True}

    def test_an_archive_row_without_a_link_is_not_asked_about(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_CORPUS_BUDGET", "5")
        row = {**self._archive_row(1), "url": None}
        pages = [[row], []]
        asked = []
        monkeypatch.setattr(run.sinks, "fetch_news_archive",
                            lambda c, s, l, o: pages.pop(0) if pages else [])
        monkeypatch.setattr(run.sinks, "fetch_embedded_urls",
                            lambda c, urls: asked.append(urls) or set())
        monkeypatch.setattr(run.kap_archive, "fetch_detail", lambda i, c: None)
        monkeypatch.setattr(run.sinks, "push_disclosures_to_rag", lambda c, d: len(d))
        run.backfill_kap_corpus(None)
        assert asked == [[]]

    def test_a_row_whose_link_carries_no_index_is_skipped(self, monkeypatch):
        """Bildirim numarası kalıcı bağlantının içinde; bağlantısı olmayan
        bir satırın gövdesi çekilemez."""
        def refuse(*a, **k):
            pytest.fail("there is no disclosure index to fetch")

        monkeypatch.setattr(run.kap_archive, "fetch_detail", refuse)
        assert run._with_bodies([{"url": None, "title": "t", "related_symbols": [],
                                  "published_at": NOW}], None) == []

    def test_an_iso_publish_date_is_parsed_back(self, monkeypatch):
        """Arşiv ucu ISO metin döndürüyor, yoklama ise datetime taşıyor. Ek
        penceresi tarih aritmetiği yapıyor ve metinle çalışmıyor."""
        monkeypatch.setenv("INGESTOR_KAP_PDF_WINDOW_DAYS", "30")
        monkeypatch.setattr(run.kap_archive, "fetch_detail",
                            lambda i, c: {"disclosureBody": ["<p>gövde</p>"]})
        monkeypatch.setattr(run.kap_archive, "attachment_text", lambda d, c: "")
        docs = run._with_bodies([{
            "url": ".../1", "title": "t", "related_symbols": [],
            "published_at": datetime.now(timezone.utc).isoformat(),
        }], None)
        assert docs and isinstance(docs[0]["published_at"], datetime)


class TestArchiveAndCorpusLookups:
    def test_the_archive_page_is_read_from_the_backend(self):
        handler = recorder(body={"items": [{"content_hash": "a" * 64}]})
        rows = sinks.fetch_news_archive(client_for(handler), "KAP", 200, 0)
        assert len(rows) == 1
        assert handler.calls[0].url.path.endswith("/market/news/archive")

    def test_an_unavailable_archive_page_yields_nothing(self):
        assert sinks.fetch_news_archive(client_for(recorder(status=503)), "KAP", 10, 0) == []

    def test_the_corpus_is_asked_which_texts_it_holds(self):
        handler = recorder(body={"known": ["https://x/1"]})
        got = sinks.fetch_embedded_urls(client_for(handler), ["https://x/1", "https://x/2"])
        assert got == {"https://x/1"}
        assert handler.calls[0].url.path.endswith("/documents/known-urls")

    def test_an_empty_list_asks_nothing(self):
        def handler(request):
            pytest.fail("nothing to ask about")

        assert sinks.fetch_embedded_urls(client_for(handler), []) == set()

    def test_a_failed_lookup_assumes_nothing_is_embedded(self):
        """Güvenli yön: fazladan indirilen bir gövde `ON CONFLICT` ile
        eleniyor, atlanan bir gövde sessiz bir boşluk bırakırdı."""
        assert sinks.fetch_embedded_urls(client_for(recorder(status=503)), ["https://x/1"]) == set()


class TestKapCatchUp:
    def test_coverage_is_read_from_the_backend(self):
        handler = recorder(body={"KAP": {"items": 5, "last": "2026-08-20", "last_index": 99}})
        got = sinks.fetch_news_coverage(client_for(handler))
        assert got["KAP"]["last_index"] == 99
        assert handler.calls[0].url.path.endswith("/market/news/coverage")

    def test_unavailable_coverage_reads_as_nothing_covered(self):
        """The safe direction: the caller then does the complete thing."""
        assert sinks.fetch_news_coverage(client_for(recorder(status=503))) == {}

    def test_top_up_catches_the_gap_since_the_newest_held(self, monkeypatch):
        monkeypatch.setattr(
            run.sinks, "fetch_news_coverage",
            lambda c: {"KAP": {"items": 10, "last": "2026-08-20", "last_index": 5}},
        )
        span = {}
        monkeypatch.setattr(
            run, "run_kap",
            lambda client, since=None, until=None: span.update(since=since, until=until) or {},
        )
        run.topup_kap(None)
        # A margin behind the watermark: overlap is free, a gap is not.
        assert span["since"] == date(2026, 8, 20) - timedelta(days=run.KAP_TOPUP_MARGIN_DAYS)

    def test_an_empty_store_is_the_backfill_s_question_not_the_top_up_s(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_news_coverage", lambda c: {})
        assert run.topup_kap(None) == {"skipped": True}

    def test_coverage_without_a_date_is_skipped(self, monkeypatch):
        monkeypatch.setattr(
            run.sinks, "fetch_news_coverage", lambda c: {"KAP": {"items": 3, "last": None}}
        )
        assert run.topup_kap(None) == {"skipped": True}

    def test_an_already_current_store_fetches_nothing(self, monkeypatch):
        today = datetime.now(run.ISTANBUL).date()
        monkeypatch.setattr(
            run.sinks, "fetch_news_coverage",
            lambda c: {"KAP": {"items": 10, "last": (today + timedelta(days=5)).isoformat()}},
        )

        def refuse(*a, **k):
            pytest.fail("nothing to catch up on")

        monkeypatch.setattr(run, "run_kap", refuse)
        assert run.topup_kap(None) == {"fetched": 0}

    def test_the_backfill_reaches_back_the_configured_depth(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_BACKFILL_DAYS", "183")
        span = {}
        monkeypatch.setattr(
            run, "run_kap",
            lambda client, since=None, until=None: span.update(days=(until - since).days) or {},
        )
        run.backfill_kap(None)
        assert span["days"] == 183


class TestDisclosureCorpusPush:
    def _doc(self, **over):
        doc = {
            "title": "THYAO — Bir şey",
            "url": "https://www.kap.org.tr/tr/Bildirim/1",
            "published_at": NOW,
            "related_symbols": ["THYAO"],
            "text": "İlgili şirketler: THYAO\nGövde metni",
        }
        doc.update(over)
        return doc

    def test_a_disclosure_is_filed_under_the_contract_s_own_enum(self):
        """FILING is already in the frozen doc_types enum, so the model can
        filter on it without the contract being reopened."""
        handler = recorder(body={"status": "ingested"})
        assert sinks.push_disclosures_to_rag(client_for(handler), [self._doc()]) == 1
        body = json.loads(handler.calls[0].content)
        assert body["document_type"] == "FILING"
        assert body["category"] == "kap-disclosure"
        assert body["source"] == "KAP"
        assert body["ticker"] == "THYAO"
        # `#ekler`: canlı akış aynı bildirimin GÖVDESİNİ dakikalar içinde
        # çıplak adresle korpusa yazıyor. Aynı adresi kullansaydık
        # `documents/known-urls` "bende var" der ve ekli bilançolar bir daha
        # hiç okunmazdı. Parça hâlâ doğru KAP sayfasına çözülüyor.
        assert body["source_url"] == "https://www.kap.org.tr/tr/Bildirim/1#ekler"

    def test_a_duplicate_is_not_counted_as_written(self):
        handler = recorder(body={"status": "duplicate"})
        assert sinks.push_disclosures_to_rag(client_for(handler), [self._doc()]) == 0

    def test_the_primary_filer_takes_the_single_ticker_column(self):
        handler = recorder(body={"status": "ingested"})
        sinks.push_disclosures_to_rag(
            client_for(handler), [self._doc(related_symbols=["ASELS", "TUPRS"])]
        )
        assert json.loads(handler.calls[0].content)["ticker"] == "ASELS"

    def test_an_index_wide_notice_is_kept_out_of_the_corpus(self):
        """A document tagged to forty companies is about none of them, and
        would compete for every one of their retrieval slots."""
        def handler(request):
            pytest.fail("too many issuers; this must not be embedded")

        assert sinks.push_disclosures_to_rag(
            client_for(handler), [self._doc(related_symbols=[f"S{i}" for i in range(9)])]
        ) == 0

    def test_a_disclosure_with_no_body_is_not_embedded(self):
        def handler(request):
            pytest.fail("nothing to embed")

        assert sinks.push_disclosures_to_rag(client_for(handler), [self._doc(text="  ")]) == 0

    def test_a_rag_outage_is_degraded_not_broken(self):
        """The disclosure still reached the dashboard; the chatbot will
        simply say it found no sources, which is true."""
        assert sinks.push_disclosures_to_rag(client_for(recorder(status=503)), [self._doc()]) == 0

    def test_a_disclosure_naming_no_issuer_still_embeds(self):
        handler = recorder(body={"status": "ingested"})
        assert sinks.push_disclosures_to_rag(
            client_for(handler), [self._doc(related_symbols=[])]
        ) == 1
        assert json.loads(handler.calls[0].content)["ticker"] is None


class TestCycles:
    def test_news_cycle_reports_both_destinations(self, monkeypatch):
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [{"title": "x"}])
        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", lambda c, s: set())
        monkeypatch.setattr(run.kap_source, "fetch_disclosures", lambda known: [])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {"news_written": 1})
        monkeypatch.setattr(run.sinks, "push_news_to_rag", lambda c, i, s=None: 1)
        result = run.run_news(None)
        assert result == {"fetched": 1, "kap": 0, "embedded": 1, "tagged": 0,
                          "news_written": 1}

    def test_disclosures_ride_the_same_pipeline_as_news(self, monkeypatch):
        """KAP için ikinci bir yol açılmadı: bildirimler de haber öğesi
        biçiminde çıkıyor ve aynı lavaboya akıyor. Ayrı bir yol, backend'in
        ve RAG'ın iki farklı biçim tanıması demekti."""
        pushed = {}
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [{"title": "haber"}])
        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", lambda c, s: {1, 2})
        monkeypatch.setattr(
            run.kap_source, "fetch_disclosures", lambda known: [{"title": "bildirim"}]
        )
        monkeypatch.setattr(
            run.sinks, "push_news_to_backend",
            lambda c, i: pushed.update(backend=list(i)) or {"news_written": 2},
        )
        monkeypatch.setattr(
            run.sinks, "push_news_to_rag",
            lambda c, i, s=None: pushed.update(rag=list(i), symbols=s) or 2,
        )
        result = run.run_news(None)
        assert result["kap"] == 1
        assert [x["title"] for x in pushed["backend"]] == ["haber", "bildirim"]
        # Aynı liste ikisine de gidiyor.
        assert pushed["rag"] == pushed["backend"]

    def test_the_backend_is_asked_what_it_already_has(self, monkeypatch):
        """Sormadan çekmek, aynı iki bin sayfayı on beş dakikada bir yeniden
        istemek olurdu."""
        seen = {}
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [])
        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", lambda c, s: {7, 8})
        monkeypatch.setattr(
            run.kap_source, "fetch_disclosures",
            lambda known: seen.update(known=known) or [],
        )
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        monkeypatch.setattr(run.sinks, "push_news_to_rag", lambda c, i, s=None: 0)
        run.run_news(None)
        assert seen["known"] == {7, 8}

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

        monkeypatch.setattr(run.kap_archive, "fetch_all", fake_fetch)
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {"news_written": 1})

        assert run.run_kap(None, bodies=False) == {
            "fetched": 1, "embedded": 0, "news_written": 1
        }
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

        monkeypatch.setattr(run.kap_archive, "fetch_all", fake_fetch)
        run.run_kap(None, bodies=False)
        assert span["days"] == 2

    def test_an_explicit_range_overrides_the_window(self, monkeypatch):
        from datetime import date

        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        span = {}

        def fake_fetch(universe, since, until, client):
            span["range"] = (since, until)
            return []

        monkeypatch.setattr(run.kap_archive, "fetch_all", fake_fetch)
        run.run_kap(None, since=date(2026, 3, 1), until=date(2026, 3, 10), bodies=False)
        assert span["range"] == (date(2026, 3, 1), date(2026, 3, 10))

    def test_a_kap_push_failure_still_reports_what_was_fetched(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.kap_archive, "fetch_all", lambda *a, **k: [{"title": "x"}])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: None)
        assert run.run_kap(None, bodies=False) == {"fetched": 1, "embedded": 0}

    def test_only_disclosures_the_backend_lacks_get_their_body_read(self, monkeypatch):
        """The expensive pass is per-disclosure; in steady state almost
        everything in the window is already held."""
        items = [
            {"content_hash": "a" * 64, "url": ".../1", "title": "t",
             "published_at": NOW, "related_symbols": ["THYAO"]},
            {"content_hash": "b" * 64, "url": ".../2", "title": "t",
             "published_at": NOW, "related_symbols": ["THYAO"]},
        ]
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.kap_archive, "fetch_all", lambda *a, **k: items)
        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", lambda c, src: {1})
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {"news_written": 1})
        read = []
        monkeypatch.setattr(
            run.kap_archive, "fetch_detail",
            lambda index, client: read.append(index) or {"disclosureBody": ["<p>x</p>"]},
        )
        monkeypatch.setattr(run.sinks, "push_disclosures_to_rag", lambda c, d: len(d))

        assert run.run_kap(None)["embedded"] == 1
        assert read == ["2"], "the already-held disclosure must not be re-read"

    def test_an_incomplete_pass_says_so_in_its_result(self, monkeypatch):
        """A throttled enumeration returns fewer disclosures and no error.
        Without this the cycle reports a smaller number as if it were the
        whole answer — measured for real at 14.589 against 28.508."""
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.kap_archive, "fetch_all", lambda *a, **k: [])
        monkeypatch.setattr(run.kap_archive, "last_run_failures", 7)
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        monkeypatch.setattr(run.sinks, "push_disclosures_to_rag", lambda c, d: 0)
        assert run.run_kap(None, bodies=False)["windows_unread"] == 7

    def test_the_body_pass_is_budgeted(self, monkeypatch):
        """One request per body at two seconds a host. Unbounded, a first run
        would spend hours before anything else got a turn."""
        monkeypatch.setattr(run, "KAP_BODY_BUDGET", 2)
        items = [
            {"content_hash": str(i) * 64, "url": f".../{i}", "title": "t",
             "published_at": NOW, "related_symbols": []}
            for i in range(5)
        ]
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.kap_archive, "fetch_all", lambda *a, **k: items)
        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", lambda c, src: set())
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        monkeypatch.setattr(
            run.kap_archive, "fetch_detail", lambda index, client: {"disclosureBody": ["<p>x</p>"]}
        )
        monkeypatch.setattr(run.sinks, "push_disclosures_to_rag", lambda c, d: len(d))
        assert run.run_kap(None)["embedded"] == 2

    def test_bodies_can_be_switched_off_for_a_listing_only_pass(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.kap_archive, "fetch_all", lambda *a, **k: [
            {"content_hash": "a" * 64, "url": ".../1", "title": "t",
             "published_at": NOW, "related_symbols": []}])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {})
        monkeypatch.setattr(run.sinks, "push_disclosures_to_rag", lambda c, d: len(d))

        def refuse(*a, **k):
            pytest.fail("bodies were switched off")

        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", refuse)
        assert run.run_kap(None, bodies=False)["embedded"] == 0

    def test_every_issuer_is_named_in_the_text(self, monkeypatch):
        """rag.documents.ticker is one column, so a two-company notice can
        only be FILTERED by one of them. Naming both keeps it findable."""
        monkeypatch.setattr(
            run.kap_archive, "fetch_detail", lambda index, client: {"disclosureBody": ["<p>gövde</p>"]}
        )
        docs = run._with_bodies(
            [{"url": ".../7", "title": "ASELS — birleşme", "published_at": NOW,
              "related_symbols": ["ASELS", "TUPRS"]}],
            None,
        )
        assert docs[0]["text"].startswith("İlgili şirketler: ASELS, TUPRS")
        assert "gövde" in docs[0]["text"]

    def test_a_recent_disclosure_gets_its_attachments_read(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_PDF_WINDOW_DAYS", "30")
        monkeypatch.setattr(
            run.kap_archive, "fetch_detail", lambda index, client: {"disclosureBody": ["<p>gövde</p>"]}
        )
        monkeypatch.setattr(run.kap_archive, "attachment_text", lambda d, c: "[Rapor.pdf]\nek metni")
        docs = run._with_bodies(
            [{"url": ".../1", "title": "t", "published_at": datetime.now(timezone.utc),
              "related_symbols": []}],
            None,
        )
        assert "ek metni" in docs[0]["text"]

    def test_an_old_disclosure_does_not_pay_for_its_attachments(self, monkeypatch):
        """One request per attachment. Over a six-month backfill that would
        be a third of the wall clock spent on filings nobody will ask about."""
        monkeypatch.setenv("INGESTOR_KAP_PDF_WINDOW_DAYS", "30")
        monkeypatch.setattr(
            run.kap_archive, "fetch_detail", lambda index, client: {"disclosureBody": ["<p>gövde</p>"]}
        )

        def refuse(detail, client):
            pytest.fail("an old disclosure must not download attachments")

        monkeypatch.setattr(run.kap_archive, "attachment_text", refuse)
        old = datetime.now(timezone.utc) - timedelta(days=200)
        docs = run._with_bodies(
            [{"url": ".../1", "title": "t", "published_at": old, "related_symbols": []}], None
        )
        assert docs[0]["text"].endswith("gövde")

    def test_attachments_can_be_switched_off_entirely(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_PDF_WINDOW_DAYS", "0")
        monkeypatch.setattr(
            run.kap_archive, "fetch_detail", lambda index, client: {"disclosureBody": ["<p>g</p>"]}
        )

        def refuse(detail, client):
            pytest.fail("the window is closed")

        monkeypatch.setattr(run.kap_archive, "attachment_text", refuse)
        assert run._with_bodies(
            [{"url": ".../1", "title": "t", "published_at": datetime.now(timezone.utc),
              "related_symbols": []}], None
        )

    def test_a_disclosure_with_no_readable_attachment_keeps_its_body(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_PDF_WINDOW_DAYS", "30")
        monkeypatch.setattr(
            run.kap_archive, "fetch_detail", lambda index, client: {"disclosureBody": ["<p>gövde</p>"]}
        )
        monkeypatch.setattr(run.kap_archive, "attachment_text", lambda d, c: "")
        docs = run._with_bodies(
            [{"url": ".../1", "title": "t", "published_at": datetime.now(timezone.utc),
              "related_symbols": []}], None
        )
        assert docs[0]["text"].endswith("gövde")

    def test_a_disclosure_whose_body_is_unreadable_is_skipped(self, monkeypatch):
        monkeypatch.setattr(run.kap_archive, "fetch_detail", lambda index, client: None)
        assert run._with_bodies(
            [{"url": ".../1", "title": "t", "published_at": NOW, "related_symbols": []}], None
        ) == []

    def test_an_empty_body_is_skipped(self, monkeypatch):
        monkeypatch.setattr(run.kap_archive, "fetch_detail", lambda index, client: {})
        assert run._with_bodies(
            [{"url": ".../1", "title": "t", "published_at": NOW, "related_symbols": []}], None
        ) == []

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
        assert sinks.push_news_to_backend(client_for(handler), items) == {
            "quotes_written": 0, "candles_written": 0, "news_written": 2,
            # Backend'in çözdüğü sembol haritası, parçalar boyunca birikerek.
            # Onsuz `run_news` RAG'a boş harita iletiyor ve korpustaki her
            # RSS belgesi tickersız kalıyor.
            "news_symbols": {},
        }
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
            # Mum ikilisiyle aynı ayrım: biri "hiç arşiv var mı", diğeri
            # "elimizdeki en yeni bildirim eski mi" sorusunu cevaplıyor.
            "kap-topup": "date",
            "kap-backfill": "date",
            # Listeleme ile gövde arasındaki açığı kapatıyor: ayrı bir soru,
            # ayrı bir iş.
            "kap-corpus": "interval",
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
        run._backoff_steps.clear()

    def teardown_method(self):
        run._backoff_steps.clear()

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
        # Katman başına: `run_quotes` varsayılan olarak "all" turu.
        assert run.current_interval_seconds("all") > 300

    def test_backoff_is_bounded(self, monkeypatch):
        for _ in range(10):
            run._note_rate_limit("bulk")
        assert run.current_interval_seconds("bulk") == 300 * run.config.BACKOFF_LADDER[-1]

    def test_one_tier_does_not_slow_the_other(self, monkeypatch):
        """Bant katmanında dört sembol var ve geçici bir eksik onda sık.
        487 sembollük toplu katmanın aralığını onun yüzünden genişletmek,
        çalışan bir turu bozardı."""
        run._note_rate_limit("band")
        assert run.current_interval_seconds("band") > run.config.band_interval_seconds()
        assert run.current_interval_seconds("bulk") == run.config.quote_interval_seconds()

    def test_the_ladder_reaches_the_scheduler(self, monkeypatch):
        """Merdiven bir dönem YALNIZCA bir log satırıydı: işler açılışta sabit
        aralıkla kuruluyor ve `current_interval_seconds` hiçbir yerde
        okunmuyordu. "widening the quote interval" uyarısı, hiç gerçekleşmeyen
        bir eylemi bildiriyordu."""
        calls = []

        class Sched:
            def reschedule_job(self, job_id, trigger, seconds):
                calls.append((job_id, trigger, seconds))

        monkeypatch.setattr(run, "_scheduler", Sched())
        run._note_rate_limit("bulk")
        assert calls and calls[0][0] == "quotes_bulk"
        assert calls[0][2] == run.current_interval_seconds("bulk")

    def test_a_reset_reschedules_too(self, monkeypatch):
        calls = []

        class Sched:
            def reschedule_job(self, job_id, trigger, seconds):
                calls.append(seconds)

        monkeypatch.setattr(run, "_scheduler", Sched())
        run._note_rate_limit("bulk")
        run._note_success("bulk")
        assert calls[-1] == run.config.quote_interval_seconds()

    def test_no_scheduler_only_records(self, monkeypatch):
        """Testler ve tek seferlik çalıştırmalar zamanlayıcısız: geri çekilme
        yine kaydediliyor, yalnızca uygulanamıyor."""
        monkeypatch.setattr(run, "_scheduler", None)
        run._note_rate_limit("bulk")
        assert run.current_interval_seconds("bulk") > run.config.quote_interval_seconds()

    def test_a_clean_cycle_resets_the_interval(self, monkeypatch):
        run._note_rate_limit("all")
        monkeypatch.setattr(run, "open_markets", lambda: {"BIST"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda client: [])
        monkeypatch.setattr(run.yfinance_source, "fetch_quotes", lambda p: [])
        monkeypatch.setattr(run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": 0})
        run.run_quotes(None, force=True)
        assert run.current_interval_seconds("all") == 300

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
        monkeypatch.setattr(run, "current_interval_seconds", lambda tier="bulk": 0)
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
        run._backoff_steps.clear()

    def teardown_method(self):
        run._backoff_steps.clear()

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

        assert run.current_interval_seconds("all") == 300

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


class TestSymbolsReachTheCorpus:
    """RSS haberlerinin korpustaki kopyası bir dönem ETİKETSİZ yazılıyordu.

    Sebep akış sırası değil, sonucun geri alınmamasıydı: eşleştirme enstrüman
    evreninin bulunduğu yerde -- backend'de -- yapılıyor, bu servisin evreni
    yok ve olmamalı (veritabanı kredensiyeli taşımıyor). Backend çözüyordu,
    dönüyordu, ve RAG'a giden kopya beslemenin kendi boş etiketini taşıyordu.
    Ölçüldü: korpustaki 1.970 RSS belgesinin SIFIRINDA ticker vardı ve ajanın
    `tickers` filtresi yalnızca KAP bildirimlerinde çalışıyordu -- onlar
    etiketi kaynağından getirdiği için.
    """

    ITEM = {"content_hash": "a" * 64, "title": "Akbank'tan rekor", "source": "Dünya",
            "published_at": "2026-09-01T10:00:00Z", "related_symbols": []}

    def test_the_backend_resolution_reaches_the_document(self):
        seen = {}

        def handler(request):
            seen["ticker"] = json.loads(request.content)["ticker"]
            return httpx.Response(200, json={"status": "ingested"})

        sinks.push_news_to_rag(
            client_for(handler), [dict(self.ITEM)], {"a" * 64: ["AKBNK"]}
        )
        assert seen["ticker"] == "AKBNK"

    def test_without_a_resolution_the_feeds_own_tag_is_used(self):
        """KAP bildirimi etiketini kaynağından getiriyor ve backend onu aynen
        geri veriyor; harita gelmese de kaybolmamalı."""
        seen = {}

        def handler(request):
            seen["ticker"] = json.loads(request.content)["ticker"]
            return httpx.Response(200, json={"status": "ingested"})

        item = {**self.ITEM, "related_symbols": ["EMVAR"]}
        sinks.push_news_to_rag(client_for(handler), [item], None)
        assert seen["ticker"] == "EMVAR"

    def test_a_story_matching_nothing_is_written_without_a_ticker(self):
        """Uydurma bir etiket, bir şirketin haberini başkasının sayfasına
        koyardı. Etiketsiz belge metinden bulunabilir kalıyor."""
        seen = {}

        def handler(request):
            seen["ticker"] = json.loads(request.content)["ticker"]
            return httpx.Response(200, json={"status": "ingested"})

        sinks.push_news_to_rag(client_for(handler), [dict(self.ITEM)], {})
        assert seen["ticker"] is None

    def test_a_multi_tagged_story_keeps_its_first_symbol(self):
        """Korpus şeması belge başına tek ticker taşıyor; gerisi metinden
        bulunabilir kalıyor."""
        seen = {}

        def handler(request):
            seen["ticker"] = json.loads(request.content)["ticker"]
            return httpx.Response(200, json={"status": "ingested"})

        sinks.push_news_to_rag(
            client_for(handler), [dict(self.ITEM)], {"a" * 64: ["AKBNK", "THYAO"]}
        )
        assert seen["ticker"] == "AKBNK"

    def test_the_cycle_hands_the_backend_answer_to_the_corpus(self, monkeypatch):
        """Turun kendisi: backend ne çözdüyse RAG'a o gidiyor, ve `news_symbols`
        sonuç sözlüğüne SIZMIYOR -- o bir taşıma detayı, bir sayaç değil."""
        pushed = {}
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [dict(self.ITEM)])
        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", lambda c, s: set())
        monkeypatch.setattr(run.kap_source, "fetch_disclosures", lambda known: [])
        monkeypatch.setattr(
            run.sinks, "push_news_to_backend",
            lambda c, i: {"news_written": 1, "news_symbols": {"a" * 64: ["AKBNK"]}},
        )
        monkeypatch.setattr(
            run.sinks, "push_news_to_rag",
            lambda c, i, s=None: pushed.update(symbols=s) or 1,
        )
        result = run.run_news(None)
        assert pushed["symbols"] == {"a" * 64: ["AKBNK"]}
        assert result["tagged"] == 1
        assert "news_symbols" not in result

    def test_an_older_backend_without_the_field_still_works(self, monkeypatch):
        """Alan eklenmeden önce yazılmış bir backend'e karşı tur düşmemeli."""
        pushed = {}
        monkeypatch.setattr(run.rss_source, "fetch_all", lambda: [dict(self.ITEM)])
        monkeypatch.setattr(run.sinks, "fetch_known_news_ids", lambda c, s: set())
        monkeypatch.setattr(run.kap_source, "fetch_disclosures", lambda known: [])
        monkeypatch.setattr(run.sinks, "push_news_to_backend", lambda c, i: {"news_written": 1})
        monkeypatch.setattr(
            run.sinks, "push_news_to_rag",
            lambda c, i, s=None: pushed.update(symbols=s) or 1,
        )
        result = run.run_news(None)
        assert pushed["symbols"] == {}
        assert result["tagged"] == 0


class TestDisclosuresAreTypedAsFilings:
    """KAP bildirimi bir HABER değil, ihraççının kendi beyanı.

    Ayrım ajanın işine yarıyor ve korpus şeması onu zaten taşıyor: arama
    `doc_types` ile süzebiliyor ve sözleşmenin donuk kümesinde `FILING`
    hazır duruyordu -- yeni bir tür icat etmek, dondurulmuş bir alana
    belgelenmemiş bir değer koymak olurdu.

    Ölçülen durum: korpustaki 858 KAP belgesinin tamamı `NEWS` yazıyordu, yani
    "şirket şunu bildirdi" ile "bir gazete şunu yazdı" ayırt edilemiyordu.
    """

    def _typed(self, item):
        seen = {}

        def handler(request):
            seen["type"] = json.loads(request.content)["document_type"]
            return httpx.Response(200, json={"status": "ingested"})

        sinks.push_news_to_rag(client_for(handler), [item])
        return seen["type"]

    BASE = {"content_hash": "a" * 64, "title": "Başlık",
            "published_at": "2026-09-01T10:00:00Z", "related_symbols": []}

    def test_a_kap_disclosure_is_a_filing(self):
        assert self._typed({**self.BASE, "source": "KAP"}) == "FILING"

    def test_a_press_article_stays_news(self):
        assert self._typed({**self.BASE, "source": "Patronlar Dünyası"}) == "NEWS"

    def test_a_source_that_is_missing_does_not_become_a_filing(self):
        """Kaynağı bilinmeyen bir öğeyi birincil kaynak saymak, ona
        hak etmediği bir güvenilirlik vermek olurdu."""
        item = dict(self.BASE)
        item["source"] = None
        assert self._typed(item) == "NEWS"

    def test_the_filing_sources_are_named_not_guessed(self):
        assert "KAP" in sinks.FILING_SOURCES


class TestQuarterly:
    """Çeyreklik gelir tablosu turu — Faz B.

    Anlık görüntüden ayrı ve daha seyrek: oranlar fiyata bağlı olduğu için
    her gün değişiyor, çeyreklik rakamlar üç ayda bir açıklanıyor.
    """

    def test_nothing_to_push_is_not_a_request(self):
        assert sinks.push_quarterly(client_for(recorder()), []) is None

    def test_rows_reach_the_ingest_endpoint(self):
        handler = recorder(body={"quarterly_written": 2})
        got = sinks.push_quarterly(client_for(handler), [
            {"symbol": "AKBNK", "period_end": "2026-06-30", "net_income": 15},
            {"symbol": "AKBNK", "period_end": "2026-03-31", "net_income": 19},
        ])
        assert got == {"quarterly_written": 2}
        assert handler.calls[0].url.path.endswith("/market/quarterly/ingest")

    def test_rows_are_chunked(self, monkeypatch):
        """Parçalanarak: bir parça düşerse diğerleri yazılmış kalıyor."""
        monkeypatch.setattr(sinks, "QUARTERLY_CHUNK", 3)
        handler = recorder(body={"quarterly_written": 1})
        sinks.push_quarterly(client_for(handler), [
            {"symbol": f"S{i}"} for i in range(7)
        ])
        assert [len(json.loads(call.content)["items"]) for call in handler.calls] == [3, 3, 1]

    def test_a_failed_chunk_does_not_lose_the_others(self, monkeypatch):
        """Seri birikimli: eksik parça bir sonraki turda tamamlanıyor. Anlık
        görüntüden farkı bu -- orada eksik tur eksik veri demekti."""
        monkeypatch.setattr(sinks, "QUARTERLY_CHUNK", 2)
        seen = {"n": 0}

        def handler(request):
            seen["n"] += 1
            if seen["n"] == 1:
                return httpx.Response(500, json={})
            return httpx.Response(200, json={"quarterly_written": 2})

        got = sinks.push_quarterly(client_for(handler), [
            {"symbol": f"S{i}"} for i in range(4)
        ])
        assert got == {"quarterly_written": 2}

    def test_the_cycle_fetches_then_pushes(self, monkeypatch):
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [
            {"symbol": "AKBNK", "data_symbol": "AKBNK.IS"},
        ])
        monkeypatch.setattr(
            run.yfinance_source, "fetch_quarterly_financials",
            lambda products: [{"symbol": "AKBNK", "period_end": "2026-06-30"}],
        )
        monkeypatch.setattr(
            run.sinks, "push_quarterly", lambda c, rows: {"quarterly_written": len(rows)},
        )
        assert run.run_quarterly(None) == {"fetched": 1, "quarterly_written": 1}

    def test_an_empty_fetch_still_reports(self, monkeypatch):
        """Hiç satır yoksa sink None döndürüyor; tur yine bir sonuç yazmalı."""
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(
            run.yfinance_source, "fetch_quarterly_financials", lambda products: [],
        )
        monkeypatch.setattr(run.sinks, "push_quarterly", lambda c, rows: None)
        assert run.run_quarterly(None) == {"fetched": 0}


class TestSmallTierTolerance:
    """Oran tek başına dörtlük katmanda saçmalıyor.

    Bant katmanında üç kur + altın var. BİRİ boş dönerse %25, ikisi %50 --
    ikisi de `MISSING_TOLERANCE`'ı aşıyor ve tur "degraded" sayılıyordu.
    Ölçüldü, canlı bir turda: "2/4 symbols came back empty" ve hemen
    ardından "rate limited".

    Toleransın kendi gerekçesi büyük bir evren için yazılmış ("a third of the
    universe"); dörtlük bir kümede o cümlenin karşılığı yok.
    """

    def setup_method(self):
        run._backoff_steps.clear()

    def teardown_method(self):
        run._backoff_steps.clear()

    def _cycle(self, monkeypatch, total, returned, tier="band"):
        products = [
            {"symbol": f"S{i}", "data_symbol": f"S{i}", "market": "FX"}
            for i in range(total)
        ]
        monkeypatch.setattr(run, "open_markets", lambda: {"FX"})
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: products)
        monkeypatch.setattr(run.config, "is_band_product", lambda p: tier == "band")
        monkeypatch.setattr(
            run.yfinance_source, "fetch_quotes",
            lambda p: [{"symbol": f"S{i}"} for i in range(returned)],
        )
        monkeypatch.setattr(
            run.sinks, "push_market_data", lambda c, q, k: {"quotes_written": len(q)}
        )
        run.run_quotes(None, tier=tier)

    def test_one_missing_of_four_is_not_a_provider_problem(self, monkeypatch):
        self._cycle(monkeypatch, total=4, returned=3)
        assert run.current_interval_seconds("band") == run.config.band_interval_seconds()

    def test_two_missing_of_four_is_not_either(self, monkeypatch):
        """Ölçülen tam durum: 2/4 boş döndü ve tur geri çekilmeye girdi."""
        self._cycle(monkeypatch, total=4, returned=2)
        assert run.current_interval_seconds("band") == run.config.band_interval_seconds()

    def test_three_missing_of_four_still_counts(self, monkeypatch):
        """Dördün üçü gerçekten bir sağlayıcı sorunudur."""
        self._cycle(monkeypatch, total=4, returned=1)
        assert run.current_interval_seconds("band") > run.config.band_interval_seconds()

    def test_a_large_tier_is_unaffected_by_the_floor(self, monkeypatch):
        """487'lik katmanda oran zaten çok daha önce devreye giriyor; taban
        oradaki davranışı değiştirmemeli."""
        self._cycle(monkeypatch, total=400, returned=200, tier="bulk")
        assert run.current_interval_seconds("bulk") > run.config.quote_interval_seconds()

    def test_a_handful_missing_from_a_large_tier_is_still_tolerated(self, monkeypatch):
        self._cycle(monkeypatch, total=400, returned=395, tier="bulk")
        assert run.current_interval_seconds("bulk") == run.config.quote_interval_seconds()


class TestSessionState:
    """Saatler burada kalıyor, backend'e OLGU gidiyor.

    Backend eski bir fiyatın "piyasa kapalı" mı yoksa "veri akışı durdu" mu
    olduğunu tek başına ayırt edemiyordu ve kullanıcıya sebebi söylemeyen bir
    cümle kurmak zorundaydı.
    """

    def test_the_open_set_is_pushed(self):
        handler = recorder(body={"markets": 5})
        got = sinks.push_sessions(client_for(handler), {"BIST", "FX"})
        assert got == {"markets": 5}
        assert handler.calls[0].url.path.endswith("/market/sessions")
        assert json.loads(handler.calls[0].content) == {"open": ["BIST", "FX"]}

    def test_an_empty_set_is_still_reported(self):
        """"Hepsi kapalı" da bir olgu. Bildirilmezse backend eski bir kaydı
        okumaya devam ederdi."""
        handler = recorder(body={"markets": 5})
        sinks.push_sessions(client_for(handler), set())
        assert json.loads(handler.calls[0].content) == {"open": []}

    def test_a_failure_does_not_raise(self):
        """Seans bilgisi fiyatın üstüne konan bir açıklama, fiyatın kendisi
        değil: yazamamak turu düşürmemeli."""
        def handler(request):
            return httpx.Response(500, json={})

        assert sinks.push_sessions(client_for(handler), {"BIST"}) is None

    def test_the_cycle_reports_before_deciding_to_skip(self, monkeypatch):
        """Kapalıyken tur atlanıyor ama bildirim ondan ÖNCE gidiyor."""
        pushed = []
        monkeypatch.setattr(run, "open_markets", lambda: set())
        monkeypatch.setattr(run.sinks, "fetch_products", lambda c: [])
        monkeypatch.setattr(run.sinks, "push_sessions",
                            lambda c, m: pushed.append(set(m)))
        run.run_quotes(None)
        assert pushed == [set()]
