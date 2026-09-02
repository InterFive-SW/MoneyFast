"""KAP bildirim kaynağı.

Fixture'lar KAP'ın GERÇEK yanıtlarından kırpıldı, elle yazılmadı: bu kaynağın
zor kısmı tam olarak yanıtın biçimi -- React Server Component akışı, gövdesi
flight verisine gömülü kaçışlı HTML. Uydurulmuş bir örnek üzerinde çalışan
bir ayrıştırıcı hiçbir şey kanıtlamaz.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from ingestor.sources import kap_source

FIXTURES = Path(__file__).parent / "fixtures"
LIST_PAYLOAD = (FIXTURES / "kap_list.rsc").read_text(encoding="utf-8")
DETAIL_PAGE = (FIXTURES / "kap_detail.html").read_text(encoding="utf-8")

_RealClient = httpx.Client


@pytest.fixture(autouse=True)
def no_robots(monkeypatch):
    monkeypatch.setattr(kap_source.rss_source, "_may_fetch", lambda url, client: True)
    monkeypatch.setattr(kap_source.rss_source, "_wait_for_host", lambda url: None)


def client_for(handler):
    return _RealClient(transport=httpx.MockTransport(handler))


def responder(status=200, text=LIST_PAYLOAD):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, text=text)

    handler.calls = calls
    return handler


class TestParseList:
    def test_records_come_out_of_the_flight_payload(self):
        """Yanıt satır satır numaralanmış parçalardan oluşuyor ve TAMAMI
        geçerli JSON değil; kayıtlar `"data":[...]` dizisinin içinde."""
        records = kap_source.parse_list(LIST_PAYLOAD)
        assert len(records) == 3
        assert records[0]["stockCode"] == "EGEGY"
        assert records[0]["disclosureIndex"] == 1656735

    def test_a_payload_without_disclosures_yields_nothing(self):
        """`cat` parametresi olmadan KAP 15 KB'lık boş bir kabuk döndürüyor."""
        assert kap_source.parse_list('1:"$Sreact.fragment"\n2:{"menu":[]}') == []

    def test_an_unterminated_array_is_refused_not_guessed(self):
        payload = '4:{"data":[{"disclosureBasic":{"disclosureIndex":1'
        assert kap_source.parse_list(payload) == []

    def test_malformed_json_is_refused(self):
        payload = '4:{"data":[{"disclosureBasic":{"a":,}}],"x":1}'
        assert kap_source.parse_list(payload) == []

    def test_an_entry_without_the_wrapper_is_skipped(self):
        payload = '4:{"data":[{"disclosureBasic":{"disclosureIndex":1}},{"other":2}]}'
        assert len(kap_source.parse_list(payload)) == 1

    def test_a_nested_array_does_not_end_the_scan_early(self):
        """`relatedStocks` bir dizi olabiliyor. İlk `]`'te durulsaydı kayıt
        listesi ortasından kesilir ve geri kalan bildirimler sessizce
        kaybolurdu."""
        payload = (
            '4:{"data":[{"disclosureBasic":{"disclosureIndex":1,"tags":["a","b"]}},'
            '{"disclosureBasic":{"disclosureIndex":2}}],"more":false}'
        )
        assert [r["disclosureIndex"] for r in kap_source.parse_list(payload)] == [1, 2]

    def test_empty_input_is_safe(self):
        assert kap_source.parse_list("") == []


class TestSymbols:
    def test_the_ticker_comes_from_the_source(self):
        """Bu kaynağın en değerli yanı: RSS haberlerinde sembolü metinden
        çıkarmak zorundayız ve ölçülen isabet %3; burada KAP söylüyor."""
        assert kap_source._symbols({"stockCode": "THYAO"}) == ["THYAO"]

    def test_multiple_share_classes_are_split(self):
        """Bir şirketin birden fazla pay sınıfı olabiliyor."""
        assert kap_source._symbols(
            {"stockCode": "ISCTR", "relatedStocks": "ISATR, ISBTR"}
        ) == ["ISATR", "ISBTR", "ISCTR"]

    def test_a_missing_code_yields_nothing(self):
        """Bildirimlerin üçte biri borsada işlem görmeyen üyelerden geliyor."""
        assert kap_source._symbols({"stockCode": None, "relatedStocks": None}) == []

    def test_a_code_of_the_wrong_shape_is_dropped(self):
        assert kap_source._symbols({"stockCode": "-"}) == []
        assert kap_source._symbols({"stockCode": "TOOLONGCODE"}) == []


class TestPublishedAt:
    def test_the_kap_format_is_read(self):
        assert kap_source._published("01.09.2026 14:59:55") == datetime(
            2026, 9, 1, 14, 59, 55, tzinfo=timezone.utc
        )

    @pytest.mark.parametrize("raw", ["01.09.2026 14:59", "01.09.2026"])
    def test_shorter_forms_are_read_too(self, raw):
        assert kap_source._published(raw).date() == datetime(2026, 9, 1).date()

    def test_an_unreadable_date_falls_back_to_now(self):
        """Bildirim listede görünüyorsa yayımlanmıştır. Onu düşürmek, KAP'ın
        biçim değiştirdiği gün kaynağı sessizce boşaltırdı."""
        before = datetime.now(timezone.utc)
        assert kap_source._published("dün") >= before
        assert kap_source._published(None) >= before


class TestContentHash:
    def test_identity_comes_from_kaps_own_number(self):
        """Metinden türetilen bir hash, bildirim düzeltildiğinde (KAP bunu
        yapıyor, `isChanged` alanı var) aynı bildirimi ikinci kez yazdırırdı."""
        assert kap_source.content_hash(1656735) == kap_source.content_hash(1656735)
        assert kap_source.content_hash(1656735) != kap_source.content_hash(1656736)


class TestExtractBody:
    def test_the_narrative_survives_the_flight_escaping(self):
        """Gövde flight verisine gömülü HTML olarak geliyor (`\\u003cp\\u003e`)."""
        body = kap_source.extract_body(DETAIL_PAGE)
        assert "Esas Sözleşmesinin verdiği yetkiye istinaden" in body
        assert "<" not in body and "\\u003c" not in body

    def test_field_labels_are_kept_as_content(self):
        """KAP hem serbest anlatıyı hem form alanlarını veriyor ve ikisi de
        bildirimin ne dediğini anlatıyor."""
        body = kap_source.extract_body(DETAIL_PAGE)
        assert "Kayıtlı Sermaye Tavanı" in body

    def test_one_word_labels_are_dropped(self):
        """"Evet"/"Hayır" tek başına bir şey anlatmıyor."""
        assert kap_source.extract_body('gwt-HTML\\"\\u003eEvet\\u003c/div') == ""

    def test_a_page_without_the_block_yields_nothing(self):
        assert kap_source.extract_body("<html>menü</html>") == ""

    def test_the_body_is_capped(self):
        long_text = "a" * 20000
        page = f'gwt-HTML\\"\\u003e{long_text}\\u003c/div'
        assert len(kap_source.extract_body(page)) <= kap_source.MAX_BODY_CHARS


class TestFetchList:
    def test_the_rsc_header_is_sent(self):
        """Bu başlık olmadan sayfa HTML kabuğu döndürüyor, veri değil."""
        handler = responder()
        kap_source.fetch_list(client_for(handler))
        assert handler.calls[0].headers["rsc"] == "1"

    def test_the_user_agent_names_the_project(self):
        """README'nin kuralı: bizi istemeyen bir operatör kim olduğumuzu
        görebilmeli."""
        handler = responder()
        kap_source.fetch_list(client_for(handler))
        assert "MoneyFast" in handler.calls[0].headers["User-Agent"]

    def test_the_url_carries_no_build_specific_token(self):
        """Tarayıcının gönderdiği `_rsc` jetonu derlemeye özgü ve gerekmiyor.
        Sabitlenseydi KAP her dağıtımında kaynak sessizce boşalırdı."""
        assert "_rsc" not in kap_source.LIST_URL

    def test_robots_denial_stops_the_fetch(self, monkeypatch):
        monkeypatch.setattr(kap_source.rss_source, "_may_fetch", lambda url, client: False)
        handler = responder()
        assert kap_source.fetch_list(client_for(handler)) == []
        assert handler.calls == []

    def test_a_bad_status_yields_nothing_rather_than_raising(self):
        assert kap_source.fetch_list(client_for(responder(status=503))) == []

    def test_an_unreachable_host_yields_nothing(self):
        def boom(request):
            raise httpx.ConnectError("down")

        assert kap_source.fetch_list(client_for(boom)) == []


class TestFetchDetail:
    def test_the_body_is_returned_cleaned(self):
        body = kap_source.fetch_detail(client_for(responder(text=DETAIL_PAGE)), 1656735)
        assert "Esas Sözleşmesinin" in body

    def test_the_index_is_in_the_url(self):
        handler = responder(text=DETAIL_PAGE)
        kap_source.fetch_detail(client_for(handler), 1656735)
        assert str(handler.calls[0].url).endswith("/Bildirim/1656735")

    def test_robots_denial_stops_the_fetch(self, monkeypatch):
        monkeypatch.setattr(kap_source.rss_source, "_may_fetch", lambda url, client: False)
        assert kap_source.fetch_detail(client_for(responder()), 1) == ""

    def test_a_bad_status_yields_an_empty_body(self):
        """Çağıran listeden gelen kısa özetle devam eder: gövdesi alınamayan
        bir bildirimi hiç kaydetmemek, elde olan bilgiyi de atmak olurdu."""
        assert kap_source.fetch_detail(client_for(responder(status=500)), 1) == ""

    def test_an_unreachable_host_yields_an_empty_body(self):
        def boom(request):
            raise httpx.ReadTimeout("slow")

        assert kap_source.fetch_detail(client_for(boom), 1) == ""


class TestFetchDisclosures:
    def _install(self, monkeypatch, detail=DETAIL_PAGE):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if "/Bildirim/" in str(request.url):
                return httpx.Response(200, text=detail)
            return httpx.Response(200, text=LIST_PAYLOAD)

        handler.calls = calls
        monkeypatch.setattr(
            kap_source.httpx, "Client", lambda **kw: client_for(handler)
        )
        return handler

    def test_items_have_the_same_shape_as_rss_items(self, monkeypatch):
        """İkisi de aynı lavaboya gidiyor. Ayrı bir yol açmak, backend'in ve
        RAG'ın iki farklı biçim tanıması demekti."""
        self._install(monkeypatch)
        items = kap_source.fetch_disclosures()
        assert set(items[0]) == {
            "content_hash", "title", "summary", "source", "url",
            "language", "related_symbols", "published_at",
        }
        assert items[0]["source"] == kap_source.SOURCE

    def test_the_company_name_leads_the_text(self, monkeypatch):
        """RAG'da parça tek başına aranıyor; "Sermaye Artırımı" başlığı hangi
        şirketin olduğunu söylemeden hiçbir sorguya cevap vermez."""
        self._install(monkeypatch)
        items = kap_source.fetch_disclosures()
        assert items[0]["summary"].startswith("EGEYAPI")
        assert "EGEYAPI" in items[0]["title"]

    def test_known_disclosures_are_skipped_entirely(self, monkeypatch):
        """Sormadan çekmek, aynı iki bin sayfayı on beş dakikada bir yeniden
        istemek olurdu."""
        handler = self._install(monkeypatch)
        items = kap_source.fetch_disclosures(known_ids=[1656735])
        assert all(i["url"].split("/")[-1] != "1656735" for i in items)
        assert not any("/Bildirim/1656735" in str(c.url) for c in handler.calls)

    def test_the_detail_budget_is_respected(self, monkeypatch):
        """Her ayrıntı ayrı bir istek ve aralarında bekleniyor; bu sayı
        doğrudan koşunun süresi."""
        handler = self._install(monkeypatch)
        kap_source.fetch_disclosures(detail_limit=1)
        detail_calls = [c for c in handler.calls if "/Bildirim/" in str(c.url)]
        assert len(detail_calls) == 1

    def test_a_disclosure_past_the_budget_is_not_taken_at_all(self):
        """Gövdesi çekilmemiş bir bildirim HİÇ yazılmıyor.

        Kısa özetle yazmak, `known_ids`'in onu "bende var" sayması ve
        gövdesinin bir daha hiç istenmemesi demekti. Yazılmadığı için
        bilinmiyor kalıyor ve sıradaki koşu tam buradan devam ediyor.
        """
        assert kap_source.fetch_disclosures(detail_limit=0) == []

    def test_the_run_is_bounded_by_the_budget(self, monkeypatch):
        """İki bin bildirimi tek koşuda işlemek, yarıda kesilen bir koşunun
        backend'e yazılıp RAG'a ulaşmamış kayıtlar bırakması demekti -- ve
        onlar artık "bilindiği" için bir daha denenmezdi. Ölçüldü: tam olarak
        bu oldu."""
        self._install(monkeypatch)
        assert len(kap_source.fetch_disclosures(detail_limit=2)) == 2

    def test_a_record_without_a_title_is_dropped(self, monkeypatch):
        payload = '4:{"data":[{"disclosureBasic":{"disclosureIndex":9,"title":"  "}}]}'
        self._install(monkeypatch)
        monkeypatch.setattr(kap_source, "fetch_list", lambda c: kap_source.parse_list(payload))
        assert kap_source.fetch_disclosures() == []

    def test_a_record_without_a_number_is_dropped(self, monkeypatch):
        """Numara kimlik; onsuz aynı bildirim her koşuda yeniden yazılırdı."""
        self._install(monkeypatch)
        monkeypatch.setattr(
            kap_source, "fetch_list",
            lambda c: [{"disclosureIndex": None, "title": "x"}],
        )
        assert kap_source.fetch_disclosures() == []

    def test_the_same_number_twice_is_taken_once(self, monkeypatch):
        self._install(monkeypatch)
        monkeypatch.setattr(
            kap_source, "fetch_list",
            lambda c: [{"disclosureIndex": 5, "title": "a"},
                       {"disclosureIndex": 5, "title": "b"}],
        )
        assert len(kap_source.fetch_disclosures(detail_limit=5)) == 1
