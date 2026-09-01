"""KAP disclosures.

Every shape asserted here was measured against the live platform on
2026-09-01 (see `docs/` and the module docstring), not guessed from
documentation — KAP publishes none.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

from ingestor.sources import courtesy, kap_source

_RealClient = httpx.Client

CRITERIA = "/tr/api/disclosure/members/byCriteria"
UNIVERSE = {"THYAO", "TUPRS", "ASELS", "YKBNK"}


def client_for(handler):
    return _RealClient(transport=httpx.MockTransport(handler))


def row(**overrides):
    """A listing row with the field names KAP actually returns."""
    base = {
        "disclosureIndex": 1655982,
        "publishDate": "28.08.2026 23:15:00",
        "kapTitle": "TÜRK HAVA YOLLARI A.O.",
        "stockCodes": "THYAO",
        "relatedStocks": None,
        "subject": "Payların Geri Alınmasına İlişkin Bildirim",
        "summary": "Pay Geri Alım İşlemleri",
        "disclosureClass": "ODA",
        "attachmentCount": 0,
        "modifyStatus": None,
    }
    base.update(overrides)
    return base


def serving(rows, status=200, body=None):
    """Answers robots.txt as the live host does (a non-200 oddity) and the
    criteria endpoint with `rows`."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(666, text="")
        if body is not None:
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=rows)

    handler.calls = calls
    return handler


class TestContentHash:
    def test_the_key_is_the_disclosure_index_not_the_text(self):
        """Re-fetching must be free, and the hash must be computable from a
        listing alone so the backfill can skip before spending a request."""
        first = kap_source.normalise(row(summary="İlk hâli"), UNIVERSE)
        second = kap_source.normalise(row(summary="Düzeltilmiş metin"), UNIVERSE)
        assert first["content_hash"] == second["content_hash"]
        assert first["content_hash"] == kap_source.content_hash(1655982)

    def test_different_disclosures_do_not_collide(self):
        assert kap_source.content_hash(1) != kap_source.content_hash(2)

    def test_it_is_a_sha256_hex_digest(self):
        """`market.news_items.content_hash` is String(64) and the vector
        store CHECKs `^[0-9a-f]{64}$`."""
        value = kap_source.content_hash(1655982)
        assert len(value) == 64 and set(value) <= set("0123456789abcdef")


class TestIssuerCodes:
    def test_both_code_fields_are_read(self):
        """37% of matches come only through relatedStocks: a broker files
        under its own code while the subject company sits in the other field."""
        assert kap_source.issuer_codes(
            row(stockCodes="BLS, BLSMD", relatedStocks="TGSAS")
        ) == {"BLS", "BLSMD", "TGSAS"}

    def test_an_abbreviation_beside_the_ticker_is_kept_and_filtered_later(self):
        assert kap_source.issuer_codes(row(stockCodes="YKB, YKBNK")) == {"YKB", "YKBNK"}

    def test_semicolons_are_accepted_too(self):
        assert kap_source.issuer_codes(row(stockCodes="ASELS;TUPRS")) == {"ASELS", "TUPRS"}

    def test_nulls_and_junk_yield_nothing(self):
        assert kap_source.issuer_codes(row(stockCodes=None, relatedStocks=None)) == set()
        assert kap_source.issuer_codes(row(stockCodes="A, TOOLONGCODE, ,")) == set()


class TestPublishDate:
    def test_istanbul_local_time_becomes_utc(self):
        """KAP publishes in local time and says so nowhere in the payload."""
        assert kap_source._published("28.08.2026 23:15:00") == datetime(
            2026, 8, 28, 20, 15, tzinfo=timezone.utc
        )

    @pytest.mark.parametrize("raw", ["28.08.2026 23:15", "28.08.2026"])
    def test_shorter_forms_parse(self, raw):
        assert kap_source._published(raw).year == 2026

    @pytest.mark.parametrize("raw", [None, "", "not a date"])
    def test_unreadable_dates_are_refused_not_guessed(self, raw):
        """RSS may fall back to now() for an undated entry. A filing dated
        'now' would sit at the top of today's feed while being months old."""
        assert kap_source._published(raw) is None


class TestNormalise:
    def test_a_disclosure_becomes_a_news_item(self):
        item = kap_source.normalise(row(), UNIVERSE)
        assert item["title"] == "THYAO — Pay Geri Alım İşlemleri"
        assert item["source"] == "KAP"
        assert item["url"] == "https://www.kap.org.tr/tr/Bildirim/1655982"
        assert item["related_symbols"] == ["THYAO"]
        assert item["language"] == "tr"
        assert "TÜRK HAVA YOLLARI" in item["summary"]

    def test_it_emits_exactly_the_keys_the_sink_expects(self):
        """Same eight keys as rss_source, so the sink needs no branch."""
        assert set(kap_source.normalise(row(), UNIVERSE)) == {
            "content_hash", "title", "summary", "source", "url",
            "language", "related_symbols", "published_at",
        }

    def test_an_issuer_we_do_not_carry_is_dropped(self):
        assert kap_source.normalise(row(stockCodes="NOTOURS"), UNIVERSE) is None

    def test_a_disclosure_naming_no_issuer_is_dropped(self):
        assert kap_source.normalise(row(stockCodes=None), UNIVERSE) is None

    def test_only_symbols_we_carry_are_tagged(self):
        item = kap_source.normalise(
            row(stockCodes="THYAO, NOTOURS", relatedStocks="ASELS"), UNIVERSE
        )
        assert item["related_symbols"] == ["ASELS", "THYAO"]

    def test_the_form_name_is_used_when_there_is_no_summary(self):
        item = kap_source.normalise(row(summary=None), UNIVERSE)
        assert item["title"] == "THYAO — Payların Geri Alınmasına İlişkin Bildirim"

    def test_a_disclosure_with_no_text_at_all_is_dropped(self):
        assert kap_source.normalise(row(summary=None, subject=None), UNIVERSE) is None

    def test_an_amendment_says_so_in_the_text(self):
        """There is nowhere else to put it: the news table has no spare
        column and rag.documents has no metadata."""
        item = kap_source.normalise(row(modifyStatus="DUZENLENEN"), UNIVERSE)
        assert "Düzeltilmiş bildirim" in item["summary"]

    def test_an_amendment_with_no_context_still_says_so(self):
        item = kap_source.normalise(
            row(modifyStatus="DUZENLENEN", kapTitle=None, subject=None), UNIVERSE
        )
        assert item["summary"] == "Düzeltilmiş bildirim"

    @pytest.mark.parametrize("index", [None, ""])
    def test_a_row_without_an_index_is_dropped(self, index):
        assert kap_source.normalise(row(disclosureIndex=index), UNIVERSE) is None

    def test_an_unparseable_date_drops_the_row(self):
        assert kap_source.normalise(row(publishDate="tomorrow"), UNIVERSE) is None


class TestEnumeration:
    def test_a_short_window_is_returned_whole(self):
        handler = serving([row(), row(disclosureIndex=2)])
        out = kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 30),
                                          client_for(handler))
        assert len(out) == 2
        posted = next(c for c in handler.calls if c.url.path == CRITERIA)
        import json
        assert json.loads(posted.content) == {
            "fromDate": "2026-08-28", "toDate": "2026-08-30",
            "mkkMemberOidList": [], "subjectList": [],
        }

    def test_the_honest_user_agent_is_sent_and_no_referer(self, monkeypatch):
        """Measured: KAP answers identically with and without a spoofed
        referrer, so there is no reason to send one."""
        monkeypatch.setenv("INGESTOR_USER_AGENT", "MoneyFastBot/1.0 (+link)")
        handler = serving([])
        kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 28),
                                    client_for(handler))
        posted = next(c for c in handler.calls if c.url.path == CRITERIA)
        assert posted.headers["User-Agent"] == "MoneyFastBot/1.0 (+link)"
        assert "referer" not in {k.lower() for k in posted.headers}

    def test_a_capped_window_is_halved(self):
        """Exactly 2000 rows is indistinguishable from a truncated response,
        so it is treated as truncated."""
        seen = []

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            import json
            body = json.loads(request.content)
            seen.append((body["fromDate"], body["toDate"]))
            full = len(seen) == 1
            return httpx.Response(200, json=[row(disclosureIndex=i)
                                             for i in range(2000 if full else 3)])

        out = kap_source.enumerate_window(date(2026, 8, 1), date(2026, 8, 31),
                                          client_for(handler))
        assert len(seen) == 3, "the wide window should have been split in two"
        assert len(out) == 6

    def test_a_capped_single_day_stops_rather_than_recursing(self):
        handler = serving([row(disclosureIndex=i) for i in range(2000)])
        out = kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 28),
                                          client_for(handler))
        assert len(out) == 2000

    def test_bisection_has_a_depth_ceiling(self, monkeypatch):
        monkeypatch.setattr(kap_source, "MAX_BISECT_DEPTH", 0)
        handler = serving([row(disclosureIndex=i) for i in range(2000)])
        assert len(kap_source.enumerate_window(date(2026, 1, 1), date(2026, 12, 31),
                                               client_for(handler))) == 2000


class TestFailuresAreQuiet:
    """A dead source must not stop the run — the rule rss_source follows."""

    def test_an_unreachable_host_yields_nothing(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            raise httpx.ConnectError("boom")

        assert kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 28),
                                           client_for(handler)) == []

    def test_rate_limiting_backs_off_quietly(self):
        assert kap_source.enumerate_window(
            date(2026, 8, 28), date(2026, 8, 28),
            client_for(serving(None, status=429, body="slow down")),
        ) == []

    def test_a_server_error_yields_nothing(self):
        assert kap_source.enumerate_window(
            date(2026, 8, 28), date(2026, 8, 28),
            client_for(serving(None, status=503, body="down")),
        ) == []

    def test_unparseable_json_yields_nothing(self):
        assert kap_source.enumerate_window(
            date(2026, 8, 28), date(2026, 8, 28),
            client_for(serving(None, body="<html>not json</html>")),
        ) == []

    def test_a_non_list_payload_yields_nothing(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            return httpx.Response(200, json={"error": "unexpected"})

        assert kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 28),
                                           client_for(handler)) == []

    def test_non_object_elements_are_discarded(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            return httpx.Response(200, json=[row(), "junk", None])

        assert len(kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 28),
                                               client_for(handler))) == 1

    def test_robots_disallow_stops_the_fetch(self, monkeypatch):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            pytest.fail("robots.txt disallowed this host; nothing should be fetched")

        assert kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 28),
                                           client_for(handler)) == []


class TestFetchAll:
    def test_windows_are_walked_newest_first(self, monkeypatch):
        """An interrupted backfill should leave a contiguous RECENT archive,
        not a random scatter."""
        monkeypatch.setenv("INGESTOR_KAP_WINDOW_DAYS", "3")
        seen = []

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            import json
            body = json.loads(request.content)
            seen.append((body["fromDate"], body["toDate"]))
            return httpx.Response(200, json=[])

        kap_source.fetch_all(UNIVERSE, date(2026, 8, 20), date(2026, 8, 28),
                             client_for(handler))
        assert seen == [
            ("2026-08-26", "2026-08-28"),
            ("2026-08-23", "2026-08-25"),
            ("2026-08-20", "2026-08-22"),
        ]

    def test_the_first_window_never_starts_before_the_floor(self):
        seen = []

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            import json
            seen.append(json.loads(request.content)["fromDate"])
            return httpx.Response(200, json=[])

        kap_source.fetch_all(UNIVERSE, date(2026, 8, 27), date(2026, 8, 28),
                             client_for(handler), window_days=30)
        assert seen == ["2026-08-27"]

    def test_matching_disclosures_come_back_normalised(self):
        out = kap_source.fetch_all(
            UNIVERSE, date(2026, 8, 28), date(2026, 8, 28),
            client_for(serving([row(), row(disclosureIndex=99, stockCodes="NOTOURS")])),
        )
        assert [i["related_symbols"] for i in out] == [["THYAO"]]

    def test_a_disclosure_seen_in_two_windows_is_kept_once(self):
        out = kap_source.fetch_all(
            UNIVERSE, date(2026, 8, 20), date(2026, 8, 28),
            client_for(serving([row()])), window_days=3,
        )
        assert len(out) == 1

    def test_an_empty_universe_fetches_nothing(self):
        """Nothing could match, so spending requests to discover that would
        be rude for no reason."""
        def handler(request):
            pytest.fail("no universe means nothing to match; do not call KAP")

        assert kap_source.fetch_all(set(), date(2026, 8, 28), date(2026, 8, 28),
                                    client_for(handler)) == []


class TestCourtesy:
    def test_requests_to_kap_are_spaced(self, monkeypatch):
        slept = []
        monkeypatch.setattr(courtesy.time, "sleep", lambda s: slept.append(s))
        handler = serving([])
        client = client_for(handler)
        kap_source.enumerate_window(date(2026, 8, 28), date(2026, 8, 28), client)
        kap_source.enumerate_window(date(2026, 8, 27), date(2026, 8, 27), client)
        assert slept, "the second call to one host must wait"

    def test_permalink_follows_the_configured_base(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_BASE_URL", "https://example.test/")
        assert kap_source.permalink(7) == "https://example.test/tr/Bildirim/7"
