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


class TestIncompleteRuns:
    """A window that failed is not a window with nothing in it.

    Measured once for real: a throttled pass returned 14.589 disclosures
    where an unthrottled one over the same six months returned 28.508 — and
    the log said "disclosures for instruments we hold" both times, with no
    hint that half the archive had been skipped.
    """

    def test_a_failed_window_is_recorded_not_read_as_empty(self):
        failures = []
        kap_source.enumerate_window(
            date(2026, 8, 28), date(2026, 8, 28),
            client_for(serving(None, status=429, body="slow down")),
            failures=failures,
        )
        assert failures == [(date(2026, 8, 28), date(2026, 8, 28))]

    def test_fetch_all_counts_unread_windows(self, monkeypatch):
        monkeypatch.setenv("INGESTOR_KAP_WINDOW_DAYS", "1")
        calls = {"n": 0}

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            calls["n"] += 1
            if calls["n"] == 2:
                return httpx.Response(503, text="down")
            return httpx.Response(200, json=[row()])

        kap_source.fetch_all(UNIVERSE, date(2026, 8, 26), date(2026, 8, 28),
                             client_for(handler))
        assert kap_source.last_run_failures == 1

    def test_a_clean_pass_reports_no_failures(self):
        kap_source.fetch_all(UNIVERSE, date(2026, 8, 28), date(2026, 8, 28),
                             client_for(serving([row()])))
        assert kap_source.last_run_failures == 0

    def test_a_bisected_window_propagates_its_failures(self, monkeypatch):
        """The recursive half must report upward, or a truncated-then-failed
        window looks clean."""
        calls = {"n": 0}

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json=[row(disclosureIndex=i) for i in range(2000)])
            return httpx.Response(503, text="down")

        failures = []
        kap_source.enumerate_window(date(2026, 8, 1), date(2026, 8, 31),
                                    client_for(handler), failures=failures)
        assert len(failures) == 2


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


DETAIL = {
    "disclosure": {"disclosureBasic": {"disclosureIndex": 1655988}},
    "disclosureBody": ["<p>Özet Bilgi</p>"],
    "attachments": [{"objId": "abc", "fileName": "Esas.pdf", "fileExtension": "pdf"}],
}


def detail_serving(payload, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(666, text="")
        if isinstance(payload, str):
            return httpx.Response(status, text=payload)
        return httpx.Response(status, json=payload)

    return handler


class TestHtmlToText:
    def test_cells_stay_on_one_line_separated_by_a_tab(self):
        """A disclosure body IS a table: label in one cell, number in the
        next. Losing the separator turns a balance sheet into a column of
        unlabelled numbers."""
        out = kap_source.html_to_text(
            ["<table><tr><td>Net Dönem Kârı</td><td>1.234.567,89</td></tr></table>"]
        )
        assert out.split("\n")[0] == "Net Dönem Kârı\t1.234.567,89"

    def test_rows_are_separated(self):
        out = kap_source.html_to_text(
            ["<table><tr><td>A</td></tr><tr><td>B</td></tr></table>"]
        )
        assert out.splitlines() == ["A", "B"]

    def test_script_and_style_content_is_dropped(self):
        """Markup, not prose — it would be read into the corpus as text."""
        out = kap_source.html_to_text(
            ["<p>Görünür</p><script>var gizli = 1;</script><style>.a{color:red}</style>"]
        )
        assert out == "Görünür"

    def test_inline_tags_do_not_split_a_line(self):
        """KAP wraps labels in <span>/<b>. Treating every closing tag as a
        break would put the label and its value on separate lines."""
        out = kap_source.html_to_text(
            ["<td><b>Net Kâr</b> <span>(TL)</span></td><td>1.234</td>"]
        )
        assert out == "Net Kâr (TL)\t1.234"

    def test_entities_are_decoded(self):
        assert kap_source.html_to_text(["<p>T&uuml;rkiye &amp; Co &#252;</p>"]) == (
            "Türkiye & Co ü"
        )

    def test_line_breaks_become_newlines(self):
        assert kap_source.html_to_text(["bir<br>iki"]).splitlines() == ["bir", "iki"]

    def test_the_body_is_a_list_of_fragments(self):
        """Measured: `disclosureBody` comes back as a LIST, not a string."""
        assert kap_source.html_to_text(["<p>bir</p>", "<p>iki</p>"]).splitlines() == [
            "bir", "iki",
        ]

    def test_a_bare_string_is_accepted_too(self):
        assert kap_source.html_to_text("<p>tek</p>") == "tek"

    @pytest.mark.parametrize("payload", [None, 42, [], [""], ["   "], [None]])
    def test_nothing_readable_yields_an_empty_string(self, payload):
        assert kap_source.html_to_text(payload) == ""

    def test_blank_lines_are_collapsed(self):
        out = kap_source.html_to_text(["<div><p></p><p>  bir  </p><p></p></div>"])
        assert out == "bir"

    def test_a_fragment_that_will_not_parse_does_not_lose_the_others(self, monkeypatch):
        calls = {"n": 0}
        real = kap_source._Text.feed

        def flaky(self, data):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("bozuk")
            return real(self, data)

        monkeypatch.setattr(kap_source._Text, "feed", flaky)
        assert kap_source.html_to_text(["<p>bozuk</p>", "<p>sağlam</p>"]) == "sağlam"


class TestFetchDetail:
    def test_the_single_element_array_is_unwrapped(self):
        """Measured shape: a one-element list, consistently."""
        got = kap_source.fetch_detail(1655988, client_for(detail_serving([DETAIL])))
        assert got["disclosureBody"] == ["<p>Özet Bilgi</p>"]

    def test_a_bare_object_is_accepted(self):
        assert kap_source.fetch_detail(1, client_for(detail_serving(DETAIL))) is not None

    def test_the_index_is_in_the_path(self):
        seen = []

        def handler(request):
            seen.append(request.url.path)
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            return httpx.Response(200, json=[DETAIL])

        kap_source.fetch_detail(1655988, client_for(handler))
        assert "/tr/api/notification/attachment-detail/1655988" in seen

    @pytest.mark.parametrize(
        "payload,status",
        [([], 200), ("not json", 200), ({"x": 1}, 404), (None, 500), (42, 200)],
    )
    def test_an_unreadable_disclosure_costs_the_body_not_the_cycle(self, payload, status):
        """The listing row is already stored, so the dashboard entry and its
        link survive a body we could not read."""
        assert kap_source.fetch_detail(1, client_for(detail_serving(payload, status))) is None

    def test_an_unreachable_host_yields_none(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            raise httpx.ConnectError("boom")

        assert kap_source.fetch_detail(1, client_for(handler)) is None

    def test_robots_disallow_stops_the_fetch(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            pytest.fail("robots.txt disallowed this host")

        assert kap_source.fetch_detail(1, client_for(handler)) is None


class TestBodyAndAttachments:
    def test_body_text_flattens_the_body(self):
        assert kap_source.body_text(DETAIL) == "Özet Bilgi"

    def test_a_detail_without_a_body_is_empty_not_an_error(self):
        assert kap_source.body_text({}) == ""

    def test_only_pdf_attachments_are_offered(self):
        """`fileExtension` is in the listing, so a non-PDF is skipped without
        spending a download on it."""
        detail = {"attachments": [
            {"objId": "a", "fileName": "rapor.pdf", "fileExtension": "pdf"},
            {"objId": "b", "fileName": "tablo.xlsx", "fileExtension": "xlsx"},
            {"objId": "c", "fileName": "EKRAN.PDF", "fileExtension": None},
        ]}
        assert [a["objId"] for a in kap_source.pdf_attachments(detail)] == ["a", "c"]

    @pytest.mark.parametrize("attachments", [None, [], [{}], [{"objId": ""}], ["junk"]])
    def test_nothing_downloadable_yields_nothing(self, attachments):
        assert kap_source.pdf_attachments({"attachments": attachments}) == []


def java_wrapped(pdf: bytes, junk: bytes = b"\x75\x72\x00\x02\x5b\x42") -> bytes:
    """The envelope KAP actually returns, byte for byte.

    Measured: ac ed 00 05 75 72 00 02 5b 42 ... 78 70 | 00 10 9a 07 | %PDF-1.4
    """
    return (
        kap_source.JAVA_MAGIC
        + junk
        + kap_source.ARRAY_MARKER
        + len(pdf).to_bytes(4, "big")
        + pdf
    )


@pytest.fixture(autouse=True)
def _counters():
    kap_source.reset_counters()
    yield
    kap_source.reset_counters()


class TestJavaUnwrap:
    def test_the_real_envelope_is_unwrapped(self):
        pdf = b"%PDF-1.4\nbody"
        assert kap_source.unwrap_java_bytes(java_wrapped(pdf)) == pdf

    def test_a_raw_pdf_passes_through(self):
        """If the provider ever stops wrapping, that must not look broken."""
        assert kap_source.unwrap_java_bytes(b"%PDF-1.7\nx") == b"%PDF-1.7\nx"

    def test_something_that_is_neither_is_refused_and_counted(self):
        assert kap_source.unwrap_java_bytes(b"<html>nope</html>") is None
        assert kap_source.unwrap_failures == 1

    def test_the_marker_missing_is_refused(self):
        assert kap_source.unwrap_java_bytes(kap_source.JAVA_MAGIC + b"no marker here") is None
        assert kap_source.unwrap_failures == 1

    def test_a_length_longer_than_the_buffer_is_refused(self):
        payload = kap_source.JAVA_MAGIC + kap_source.ARRAY_MARKER + (99999).to_bytes(4, "big") + b"%PDF-"
        assert kap_source.unwrap_java_bytes(payload) is None

    def test_a_zero_length_is_refused(self):
        payload = kap_source.JAVA_MAGIC + kap_source.ARRAY_MARKER + (0).to_bytes(4, "big") + b"%PDF-"
        assert kap_source.unwrap_java_bytes(payload) is None

    def test_bytes_that_unwrap_to_something_that_is_not_a_pdf_are_refused(self):
        """The magic check is what turns a wrong offset into None instead of
        garbage in the corpus."""
        assert kap_source.unwrap_java_bytes(java_wrapped(b"NOTAPDF-really")) is None
        assert kap_source.unwrap_failures == 1

    def test_a_marker_inside_a_class_descriptor_is_skipped_for_the_real_one(self):
        """0x7870 can occur inside a class name, so the first hit is not
        guaranteed to be the right one."""
        pdf = b"%PDF-1.4\nreal"
        decoy = kap_source.ARRAY_MARKER + (7).to_bytes(4, "big") + b"NOTPDF!"
        assert kap_source.unwrap_java_bytes(java_wrapped(pdf, junk=decoy)) == pdf
        assert kap_source.unwrap_failures == 0

    def test_the_retry_ceiling_is_bounded(self, monkeypatch):
        monkeypatch.setattr(kap_source, "MAX_MARKER_ATTEMPTS", 1)
        decoy = kap_source.ARRAY_MARKER + (7).to_bytes(4, "big") + b"NOTPDF!"
        assert kap_source.unwrap_java_bytes(java_wrapped(b"%PDF-1.4\nx", junk=decoy)) is None


class TestExtractableText:
    def test_ordinary_turkish_prose_is_kept(self):
        assert kap_source.looks_extractable(
            "Şirketimizin kayıtlı sermaye tavanının geçerlilik süresi uzatılmıştır."
        )

    def test_a_numeric_price_bulletin_is_kept(self):
        """Measured at 0.0000 junk: few words, but the text is sound. A
        word-frequency test would have thrown this away."""
        assert kap_source.looks_extractable(
            "KIYMET KODU VALÖR VADE EN DÜŞÜK EN YÜKSEK\n1,2345 2,3456 3,4567"
        )

    def test_mangled_font_output_is_refused(self):
        """pypdf does not raise on a subset font with no ToUnicode map; it
        returns plausible-looking nonsense. Searchable garbage in a shared
        corpus is worse than nothing."""
        assert not kap_source.looks_extractable(
            "()ııçııstııı $nlıoiıı.jii* §işlıııııi*ı, §ıın,'I'iı:.,,l.Ş. "
            "[{;\\ i}ü}. ö\" Şiıiıı,ı. il'K hiiki]iıultıiııt"
        )

    def test_empty_text_is_not_extractable(self):
        assert not kap_source.looks_extractable("")


class TestPdfText:
    def test_unreadable_pdf_bytes_yield_nothing(self):
        assert kap_source.pdf_text(b"not a pdf at all") == ""

    def test_mangled_extraction_is_dropped_and_counted(self, monkeypatch):
        class FakePage:
            def extract_text(self):
                return "§ıın,'I'iı: [{;\\ i}ü}. $nlıoiıı.jii* §işlıı*ı ~^`|<>@#"

        import sys, types
        module = types.ModuleType("pypdf")
        module.PdfReader = lambda _stream: types.SimpleNamespace(pages=[FakePage()])
        monkeypatch.setitem(sys.modules, "pypdf", module)
        assert kap_source.pdf_text(b"%PDF-1.4") == ""
        assert kap_source.unreadable_attachments == 1

    def test_readable_pages_are_joined_and_capped(self, monkeypatch):
        import sys, types

        class Page:
            def __init__(self, text):
                self._t = text

            def extract_text(self):
                return self._t

        module = types.ModuleType("pypdf")
        module.PdfReader = lambda _stream: types.SimpleNamespace(
            pages=[Page("  Şirket kararı  "), Page(""), Page("İkinci sayfa"), Page(None)]
        )
        monkeypatch.setitem(sys.modules, "pypdf", module)
        monkeypatch.setattr(kap_source, "MAX_PDF_CHARS", 20)
        assert kap_source.pdf_text(b"%PDF-1.4") == "Şirket kararı\nİkinci"


class TestFetchAttachment:
    def _serving(self, payload, status=200):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            return httpx.Response(status, content=payload)

        return handler

    def test_an_oversized_attachment_is_refused_without_parsing(self, monkeypatch):
        monkeypatch.setattr(kap_source, "MAX_ATTACHMENT_BYTES", 8)
        assert kap_source.fetch_attachment_text(
            "x", client_for(self._serving(java_wrapped(b"%PDF-1.4\nlong body")))
        ) == ""

    def test_a_wrapped_pdf_is_downloaded_unwrapped_and_read(self, monkeypatch):
        monkeypatch.setattr(kap_source, "pdf_text", lambda payload: f"okundu:{len(payload)}")
        got = kap_source.fetch_attachment_text(
            "x", client_for(self._serving(java_wrapped(b"%PDF-1.4\nbody")))
        )
        assert got == "okundu:13"

    def test_a_failed_download_yields_nothing(self):
        assert kap_source.fetch_attachment_text(
            "x", client_for(self._serving(b"", status=500))
        ) == ""

    def test_an_unwrappable_payload_yields_nothing(self):
        assert kap_source.fetch_attachment_text(
            "x", client_for(self._serving(b"<html>challenge</html>"))
        ) == ""

    def test_an_unreachable_host_yields_nothing(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(666, text="")
            raise httpx.ConnectError("boom")

        assert kap_source.fetch_attachment_text("x", client_for(handler)) == ""

    def test_robots_disallow_stops_the_download(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            pytest.fail("robots.txt disallowed this host")

        assert kap_source.fetch_attachment_text("x", client_for(handler)) == ""


class TestAttachmentText:
    def test_each_readable_pdf_is_labelled_with_its_filename(self, monkeypatch):
        monkeypatch.setattr(
            kap_source, "fetch_attachment_text", lambda obj_id, client: f"metin-{obj_id}"
        )
        detail = {"attachments": [
            {"objId": "a", "fileName": "Bilanço.pdf", "fileExtension": "pdf"},
            {"objId": "b", "fileName": "", "fileExtension": "pdf"},
        ]}
        out = kap_source.attachment_text(detail, None)
        assert out == "[Bilanço.pdf]\nmetin-a\n\nmetin-b"

    def test_attachments_are_capped(self, monkeypatch):
        monkeypatch.setattr(kap_source, "MAX_ATTACHMENTS", 1)
        monkeypatch.setattr(kap_source, "fetch_attachment_text", lambda o, c: "x")
        detail = {"attachments": [
            {"objId": str(i), "fileExtension": "pdf", "fileName": ""} for i in range(4)
        ]}
        assert kap_source.attachment_text(detail, None) == "x"

    def test_an_unreadable_attachment_is_simply_absent(self, monkeypatch):
        monkeypatch.setattr(kap_source, "fetch_attachment_text", lambda o, c: "")
        detail = {"attachments": [{"objId": "a", "fileExtension": "pdf", "fileName": "x.pdf"}]}
        assert kap_source.attachment_text(detail, None) == ""
