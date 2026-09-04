"""Küresel haber toplama — GDELT Context 2.0.

Buradaki iddiaların çoğu NEZAKET ve SINIRLAR hakkında, ayrıştırma hakkında
değil. Uç noktanın sınırları ölçüldü ve hepsi 200 DIŞI bir cevapla değil, düz
metin gövdeyle geliyor:

* "Please limit requests to one every 5 seconds" (429),
* "The TIMESPAN is too large." (200, JSON değil),
* "A maximum of 200 records can be returned." (200, JSON değil).

Yani JSON çözümlemesini denemeden geçen bir istemci bu üç durumu sessizce
"haber yok" diye okurdu.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from ingestor import config
from ingestor.sources import courtesy, gdelt_source

BASE = "https://api.gdeltproject.org"

_RealClient = httpx.Client


def client_for(handler) -> httpx.Client:
    return _RealClient(transport=httpx.MockTransport(handler))


def article(**overrides):
    row = {
        "url": "https://example.invalid/oil",
        "title": "Oil prices climb after strikes on refinery",
        "seendate": "20260904T121735Z",
        "domain": "example.invalid",
        "language": "ENGLISH",
        "sentence": "Oil prices rose 4% after the strikes.",
        "context": (
            "Traders reacted quickly. Oil prices rose 4% after the strikes. "
            "Analysts said airlines would feel the fuel cost first."
        ),
    }
    row.update(overrides)
    return row


def handler_for(payload, status=200, text=None, robots=None):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            if robots is None:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, text=robots)
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, text=json.dumps(payload))

    handler.calls = calls
    return handler


class TestNormalise:
    def test_a_row_becomes_a_news_item(self):
        item = gdelt_source.normalise(article())
        assert item["title"] == "Oil prices climb after strikes on refinery"
        assert item["source"] == "example.invalid"
        assert item["url"] == "https://example.invalid/oil"
        assert item["language"] == "en"
        assert item["published_at"] == datetime(2026, 9, 4, 12, 17, 35, tzinfo=timezone.utc)

    def test_the_paragraph_is_what_gets_stored(self):
        """Korpusa yalnızca başlık yazmak, "ABD'nin saldırısı petrolü nasıl
        etkiler" sorusuna cevap veremeyen bir kayıt üretirdi -- gömme
        vektörü on kelimeden çıkarılamaz."""
        item = gdelt_source.normalise(article())
        assert "airlines would feel the fuel cost" in item["summary"]

    def test_the_sentence_is_not_repeated_when_the_paragraph_contains_it(self):
        """`context` `sentence`i içeriyor; ikisini birleştirmek aynı cümleyi
        gömme vektöründe olduğundan ağır gösterirdi."""
        item = gdelt_source.normalise(article())
        assert item["summary"].count("Oil prices rose 4% after the strikes.") == 1

    def test_the_sentence_is_used_when_there_is_no_paragraph(self):
        item = gdelt_source.normalise(article(context=""))
        assert item["summary"] == "Oil prices rose 4% after the strikes."

    def test_a_row_with_no_text_is_dropped(self):
        """Metin olmadan kayıt bir bağlantıdan ibaret kalır ve korpusa
        yazılmasının bütün sebebi metindi."""
        assert gdelt_source.normalise(article(context="", sentence="")) is None

    def test_a_row_with_no_title_is_dropped(self):
        assert gdelt_source.normalise(article(title="  ")) is None

    def test_no_symbols_are_guessed_here(self):
        """Evren backend'de; bu süreçte veritabanı kredensiyeli yok."""
        assert gdelt_source.normalise(article())["related_symbols"] == []

    def test_a_missing_domain_falls_back_without_claiming_authorship(self):
        item = gdelt_source.normalise(article(domain=""))
        assert item["source"] == "GDELT"

    def test_a_missing_url_is_null_not_an_empty_string(self):
        assert gdelt_source.normalise(article(url=""))["url"] is None

    @pytest.mark.parametrize(
        "raw,expected",
        [("ENGLISH", "en"), ("TURKISH", "tr"), ("GERMAN", "de"), ("", "en")],
    )
    def test_languages_map_to_codes(self, raw, expected):
        assert gdelt_source.normalise(article(language=raw))["language"] == expected

    def test_an_unmapped_language_is_kept_rather_than_dropping_the_article(self):
        """Tanınmayan bir dil, haberin kendisini atmak için sebep değil."""
        assert gdelt_source.normalise(article(language="SWAHILI"))["language"] == "swahili"

    def test_an_unparsable_date_is_stamped_now_not_dropped(self):
        item = gdelt_source.normalise(article(seendate="dün"))
        assert item["published_at"].tzinfo is timezone.utc


class TestContentHash:
    def test_the_same_story_hashes_the_same(self):
        assert gdelt_source.content_hash("a", "b") == gdelt_source.content_hash("a", "b")

    def test_it_matches_the_rss_scheme_so_a_syndicated_story_is_one_row(self):
        """Önek YOK: aynı haber hem bir RSS beslemesinden hem buradan
        gelirse iki satır değil bir satır olmalı."""
        from ingestor.sources import rss_source

        assert gdelt_source.content_hash("t", "s") == rss_source.content_hash("t", "s")


class TestFetchQuery:
    def test_articles_come_back(self, no_robots):
        handler = handler_for({"articles": [article(), article(url="https://x.invalid/2")]})
        items = gdelt_source.fetch_query('"oil prices"', client_for(handler))
        assert len(items) == 2

    def test_the_query_and_limits_travel(self, no_robots):
        handler = handler_for({"articles": []})
        gdelt_source.fetch_query('"oil prices"', client_for(handler))
        url = handler.calls[-1].url
        assert url.params["query"] == '"oil prices"'
        assert url.params["mode"] == "artlist"
        assert url.params["format"] == "json"

    def test_the_measured_ceilings_are_enforced_here_not_trusted(
        self, no_robots, monkeypatch,
    ):
        """`timespan=7d` "The TIMESPAN is too large" ile, `maxrecords=250`
        "A maximum of 200 records" ile reddediliyor. Yapılandırma yanlış
        ayarlanırsa her tur boşa gitmesin diye tavan burada da var."""
        monkeypatch.setenv("INGESTOR_GDELT_TIMESPAN_DAYS", "30")
        monkeypatch.setenv("INGESTOR_GDELT_MAX_RECORDS", "9000")
        handler = handler_for({"articles": []})
        gdelt_source.fetch_query("q", client_for(handler))
        url = handler.calls[-1].url
        assert url.params["timespan"] == f"{gdelt_source.MAX_TIMESPAN_DAYS}d"
        assert url.params["maxrecords"] == str(gdelt_source.MAX_RECORDS)

    def test_no_matches_is_an_empty_object_not_an_error(self, no_robots):
        """Eşleşme yoksa uç `{}` dönüyor."""
        assert gdelt_source.fetch_query("q", client_for(handler_for({}))) == []

    def test_a_rate_limit_backs_off_rather_than_retrying(self, no_robots, caplog):
        """Gövde sınırı SÖYLÜYOR; loglanıyor ki okuyan sayıyı koddan değil
        kaynağından öğrensin."""
        handler = handler_for(
            None, status=429,
            text="Please limit requests to one every 5 seconds",
        )
        with caplog.at_level("WARNING"):
            assert gdelt_source.fetch_query("q", client_for(handler)) == []
        assert "one every 5 seconds" in caplog.text

    def test_a_plain_text_limit_reply_is_not_read_as_no_news(self, no_robots, caplog):
        """Sınır ihlalleri 200 ile ve JSON OLMAYAN gövdeyle geliyor. Sessizce
        boş geçmek, sorgunun yanlış kurulduğunu gizlerdi."""
        handler = handler_for(None, text="The TIMESPAN is too large.")
        with caplog.at_level("WARNING"):
            assert gdelt_source.fetch_query("q", client_for(handler)) == []
        assert "TIMESPAN" in caplog.text

    def test_a_server_error_does_not_raise(self, no_robots):
        handler = handler_for(None, status=503, text="down")
        assert gdelt_source.fetch_query("q", client_for(handler)) == []

    def test_an_unreachable_host_does_not_raise(self, no_robots):
        def handler(request):
            raise httpx.ConnectError("refused")

        assert gdelt_source.fetch_query("q", client_for(handler)) == []

    def test_a_non_list_articles_field_is_refused(self, no_robots):
        assert gdelt_source.fetch_query("q", client_for(handler_for({"articles": "x"}))) == []

    def test_non_object_rows_are_skipped(self, no_robots):
        handler = handler_for({"articles": ["oops", article()]})
        assert len(gdelt_source.fetch_query("q", client_for(handler))) == 1


class TestCourtesy:
    def test_robots_is_honoured(self, monkeypatch):
        handler = handler_for({"articles": [article()]},
                              robots="User-agent: *\nDisallow: /")
        assert gdelt_source.fetch_query("q", client_for(handler)) == []

    def test_a_missing_robots_is_permission_by_convention(self, monkeypatch):
        """`api.gdeltproject.org` robots.txt yayımlamıyor -- ölçüldü, 404."""
        handler = handler_for({"articles": [article()]})
        assert len(gdelt_source.fetch_query("q", client_for(handler))) == 1

    def test_the_endpoints_own_five_second_floor_is_applied(self, monkeypatch):
        """Uç noktanın 429 gövdesi bunu yazıyor: operatörün açık isteği.
        Projenin varsayılanı 2 saniye ve daha KISA olanı seçmek, yazılı bir
        isteği sessizce çiğnemek olurdu."""
        seen = {}

        def fake_wait(url, minimum=0.0):
            seen["minimum"] = minimum

        monkeypatch.setattr(courtesy, "wait_for_host", fake_wait)
        monkeypatch.setenv("INGESTOR_RESPECT_ROBOTS", "false")
        gdelt_source.fetch_query("q", client_for(handler_for({"articles": []})))
        assert seen["minimum"] == gdelt_source.MIN_HOST_DELAY_SECONDS

    def test_the_user_agent_names_the_project(self, no_robots):
        handler = handler_for({"articles": []})
        gdelt_source.fetch_query("q", client_for(handler))
        assert "MoneyFast" in handler.calls[-1].headers["User-Agent"]


class TestFetchAll:
    def test_every_query_is_asked(self, no_robots, monkeypatch):
        asked = []

        def fake(query, client):
            asked.append(query)
            return []

        monkeypatch.setattr(gdelt_source, "fetch_query", fake)
        gdelt_source.fetch_all(["a", "b", "c"])
        assert asked == ["a", "b", "c"]

    def test_the_same_story_from_two_queries_is_one_row(self, no_robots, monkeypatch):
        """Petrol sorgusu ile jeopolitik sorgusu aynı yazıyı getirebiliyor."""
        monkeypatch.setattr(
            gdelt_source, "fetch_query",
            lambda query, client: [gdelt_source.normalise(article())],
        )
        assert len(gdelt_source.fetch_all(["a", "b"])) == 1

    def test_it_falls_back_to_the_configured_queries(self, no_robots, monkeypatch):
        asked = []
        monkeypatch.setattr(
            gdelt_source, "fetch_query",
            lambda query, client: asked.append(query) or [],
        )
        gdelt_source.fetch_all()
        assert asked == config.gdelt_queries()
