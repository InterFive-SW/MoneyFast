"""TEFAS toplama.

İki şey burada korunuyor.

**robots.txt istisnası dar.** Yalnızca `www.tefas.gov.tr` muaf ve bu
`courtesy.ROBOTS_EXEMPT_HOSTS` içinde ADIYLA duruyor. Başka hiçbir host
etkilenmiyor; listeyi genişletmek yeni bir karar demek.

**403 durmak için sinyaldir.** Yeniden denemiyoruz, başlık değiştirmiyoruz,
vekil sunucu kullanmıyoruz. Kararın koşulu bu.

Uç noktalar tarayıcıdan alınan bir HAR kaydından çıkarıldı; kütüphanelerin
belgelediği GET biçimi ölü (`ERR-006 "Method not found or disabled!"`).
"""

from __future__ import annotations

import json

import httpx
import pytest

from ingestor.sources import courtesy, tefas_source

_RealClient = httpx.Client


def client_for(handler) -> httpx.Client:
    return _RealClient(transport=httpx.MockTransport(handler))


def route_handler(routes, status=200):
    """Yol sonuna göre yanıt veren bir taklit."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /api/")
        name = request.url.path.rstrip("/").split("/")[-1]
        if name not in routes:
            return httpx.Response(404, text="unknown")
        body = routes[name]
        if isinstance(body, int):
            return httpx.Response(body, text="error")
        return httpx.Response(status, text=json.dumps(body))

    handler.calls = calls
    return handler


def ok(rows):
    return {"errorCode": None, "errorMessage": None, "resultList": rows}


class TestRobotsExemption:
    def test_only_tefas_is_exempt(self):
        """Liste DAR ve adıyla yazılı; genişletmek yeni bir karar."""
        assert courtesy.ROBOTS_EXEMPT_HOSTS == frozenset({"www.tefas.gov.tr"})

    def test_the_disallow_is_bypassed_for_tefas(self, monkeypatch):
        """`Disallow: /api/` olmasına rağmen istek gidiyor -- kararın kendisi
        bu ve `docs/TEFAS_INTEGRATION.md`de kayıtlı."""
        handler = route_handler({"fonUnvanAra": ok([
            {"fonKodu": "AAL", "fonUnvan": "ATA PORTFÖY PARA PİYASASI (TL) FONU"},
        ]), "getFplFonList": {"data": []}})
        assert tefas_source.fetch_universe(client_for(handler))

    def test_other_hosts_still_obey_robots(self, monkeypatch):
        """Varsayılan davranış değişmedi."""
        monkeypatch.setenv("INGESTOR_TEFAS_BASE_URL", "https://başka.invalid")

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            return httpx.Response(200, text=json.dumps(ok([])))

        assert tefas_source.fetch_universe(client_for(handler)) == []


class TestUniverse:
    def test_two_endpoints_are_merged(self):
        """Hiçbiri tek başına yetmiyor: biri bütün fonları veriyor ama
        kurucusuz, diğeri kurucuyu."""
        handler = route_handler({
            "fonUnvanAra": ok([{"fonKodu": "aal", "fonUnvan": "ATA PORTFÖY"}]),
            "getFplFonList": {"data": [
                {"fonKod": "AAL", "kurucuAd": "ATA PORTFÖY YÖNETİMİ A.Ş.",
                 "oprAd": "ATA YATIRIM", "durum": "AKTİF"},
            ]},
        })
        rows = tefas_source.fetch_universe(client_for(handler))
        assert rows == [{
            "code": "AAL", "title": "ATA PORTFÖY",
            "founder": "ATA PORTFÖY YÖNETİMİ A.Ş.",
            "operator": "ATA YATIRIM", "active": True,
        }]

    def test_a_fund_without_a_founder_is_kept(self):
        """Adı ve kodu var; yalnızca bir süzgeç değeri eksik."""
        handler = route_handler({
            "fonUnvanAra": ok([{"fonKodu": "XYZ", "fonUnvan": "BİR FON"}]),
            "getFplFonList": {"data": []},
        })
        rows = tefas_source.fetch_universe(client_for(handler))
        assert rows[0]["founder"] is None

    def test_a_passive_fund_is_flagged_not_dropped(self):
        """Geçmişi olan bir fonu silmek, onu tutmuş kullanıcının geçmişini de
        silmek olurdu."""
        handler = route_handler({
            "fonUnvanAra": ok([{"fonKodu": "OLD", "fonUnvan": "ESKİ FON"}]),
            "getFplFonList": {"data": [{"fonKod": "OLD", "durum": "PASİF"}]},
        })
        assert tefas_source.fetch_universe(client_for(handler))[0]["active"] is False

    @pytest.mark.parametrize("row", [
        {"fonKodu": "", "fonUnvan": "AD"}, {"fonKodu": "X", "fonUnvan": "  "},
    ])
    def test_an_unusable_row_is_dropped(self, row):
        handler = route_handler({"fonUnvanAra": ok([row]), "getFplFonList": {"data": []}})
        assert tefas_source.fetch_universe(client_for(handler)) == []


class TestDaily:
    def _rows(self, n, prefix="F"):
        return [{
            "fonKodu": f"{prefix}{i:03d}", "fonUnvan": "FON", "tarih": "2026-09-05",
            "fiyat": 3.35, "tedPaySayisi": 100.0, "kisiSayisi": 42,
            "portfoyBuyukluk": 2470539665.41,
        } for i in range(n)]

    def test_a_row_becomes_a_snapshot(self):
        handler = route_handler({"fonGnlBlgSiraliGetir": ok(self._rows(1))})
        rows = tefas_source.fetch_daily(client_for(handler))
        assert rows[0]["code"] == "F000"
        assert rows[0]["price"] == 3.35
        assert rows[0]["investors"] == 42
        assert rows[0]["as_of"] == "2026-09-05"

    def test_a_single_day_is_requested(self):
        """Aralık verilince uç fon x gün kadar satır döndürüyor (ölçüldü:
        bir aylık aralıkta `toplamSayi` 46.285) ve bize gereken o değil."""
        handler = route_handler({"fonGnlBlgSiraliGetir": ok([])})
        tefas_source.fetch_daily(client_for(handler))
        body = json.loads(handler.calls[-1].content)
        assert body["basTarih"] == body["bitTarih"]

    def test_every_fund_type_is_asked(self):
        handler = route_handler({"fonGnlBlgSiraliGetir": ok([])})
        tefas_source.fetch_daily(client_for(handler))
        asked = {json.loads(c.content)["fonTipi"] for c in handler.calls
                 if c.url.path.endswith("fonGnlBlgSiraliGetir")}
        assert asked == set(tefas_source.FUND_TYPES)

    def test_a_full_page_asks_for_the_next(self):
        pages = [ok(self._rows(tefas_source.PAGE_SIZE)), ok([])]

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text=json.dumps(pages.pop(0) if pages else ok([])))

        rows = tefas_source.fetch_daily(client_for(handler))
        assert len(rows) == tefas_source.PAGE_SIZE

    def test_a_day_with_no_nav_walks_back(self):
        """NAV yalnızca iş günlerinde yayımlanıyor. ÖLÇÜLDÜ: cumartesi
        çalıştırıldığında uç `{"errorMessage": "Index 0 out of bounds for
        length 0"}` döndürdü ve tur sıfır satırla bitti."""
        seen = []

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            body = json.loads(request.content)
            seen.append(body["basTarih"])
            # İlk gün boş, ikinci gün dolu.
            if len(set(seen)) == 1:
                return httpx.Response(200, text=json.dumps(
                    {"errorMessage": "Index 0 out of bounds for length 0",
                     "resultList": None}))
            return httpx.Response(200, text=json.dumps(ok(self._rows(1))))

        rows = tefas_source.fetch_daily(client_for(handler),
                                        on=__import__("datetime").date(2026, 9, 5))
        # Üç fon tipi de sorulduğu için satır sayısı tipe göre çarpılıyor;
        # önemli olan boş DÖNMEMESİ ve bir gün geriye gidilmiş olması.
        assert rows
        assert seen[0] == "20260905" and "20260904" in seen

    def test_it_gives_up_after_the_lookback_window(self):
        """Sonsuza kadar geriye yürümüyor: yayımlanmayan bir seri bir
        hatadır, sessizce yıllarca aranacak bir şey değil."""
        handler = route_handler({"fonGnlBlgSiraliGetir": ok([])})
        assert tefas_source.fetch_daily(client_for(handler)) == []
        days = {json.loads(c.content)["basTarih"] for c in handler.calls
                if c.url.path.endswith("fonGnlBlgSiraliGetir")}
        assert len(days) == tefas_source.MAX_LOOKBACK_DAYS + 1

    def test_a_priceless_row_is_dropped(self):
        """Fiyatı olmayan bir fon anlık görüntüde yok."""
        handler = route_handler({"fonGnlBlgSiraliGetir": ok([
            {"fonKodu": "X", "fiyat": None, "tarih": "2026-09-05"},
        ])})
        assert tefas_source.fetch_daily(client_for(handler)) == []

    def test_a_missing_size_is_null_not_zero(self):
        """Büyüklüğü bilinmeyen bir fonu sıfırla yazmak, onu listenin en
        altına gerçek bir ölçüm gibi yerleştirirdi."""
        handler = route_handler({"fonGnlBlgSiraliGetir": ok([
            {"fonKodu": "X", "fiyat": 1.0, "tarih": "2026-09-05",
             "portfoyBuyukluk": None},
        ])})
        assert tefas_source.fetch_daily(client_for(handler))[0]["size"] is None


class TestPricesAndProfile:
    def test_a_nav_series_comes_back(self):
        handler = route_handler({"fonFiyatBilgiGetir": ok([
            {"fonKodu": "AAL", "tarih": "2025-09-04", "fiyat": 2.474397},
            {"fonKodu": "AAL", "tarih": "2025-09-05", "fiyat": 2.476952},
        ])})
        rows, _ = tefas_source.fetch_prices("AAL", client_for(handler))
        assert [row["as_of"] for row in rows] == ["2025-09-04", "2025-09-05"]

    def test_returns_are_not_computed_here(self):
        """Seri saklanıyor, yüzde backend'de türetiliyor. Aynı sayıyı iki
        yerde hesaplamak, iki farklı cevap üretebileceği bir yer açardı."""
        handler = route_handler({"fonFiyatBilgiGetir": ok([
            {"tarih": "2025-09-04", "fiyat": 1.0},
        ])})
        rows, _ = tefas_source.fetch_prices("AAL", client_for(handler))
        assert set(rows[0]) == {"code", "as_of", "price"}

    @pytest.mark.parametrize("row", [
        {"tarih": "dün", "fiyat": 1.0}, {"tarih": "2025-09-04", "fiyat": None},
        {"tarih": "", "fiyat": 1.0},
    ])
    def test_an_unusable_price_row_is_dropped(self, row):
        handler = route_handler({"fonFiyatBilgiGetir": ok([row])})
        assert tefas_source.fetch_prices("AAL", client_for(handler))[0] == []

    def test_the_umbrella_comes_from_the_profile(self):
        handler = route_handler({"fonProfilDtyGetir": ok([
            {"fonKodu": "AAL", "fonTuru": "Para Piyasası Şemsiye Fonu",
             "fonTurGetiri": 0.429986},
        ])})
        assert tefas_source.fetch_profile("AAL", client_for(handler)) == {
            "code": "AAL", "umbrella": "Para Piyasası Şemsiye Fonu",
            "category_return": 0.429986,
        }

    def test_the_category_rank_rides_the_same_price_response(self):
        """Ayrıca istemek 2.602 isteği ikinci kez yapmak olurdu."""
        handler = route_handler({"fonFiyatBilgiGetir": ok([
            {"tarih": "2025-09-04", "fiyat": 1.0,
             "kategoriDerece": 71, "kategoriFonSay": 86},
        ])})
        _, metrics = tefas_source.fetch_prices("AAL", client_for(handler))
        assert metrics == {"code": "AAL", "category_rank": 71, "category_size": 86}

    def test_a_missing_rank_is_absent_not_zero(self):
        """Sıfır "kategorisinde birinci" demek olurdu."""
        handler = route_handler({"fonFiyatBilgiGetir": ok([
            {"tarih": "2025-09-04", "fiyat": 1.0},
        ])})
        assert tefas_source.fetch_prices("AAL", client_for(handler))[1] is None

    def test_a_profile_without_an_umbrella_is_none(self):
        handler = route_handler({"fonProfilDtyGetir": ok([{"fonTuru": ""}])})
        assert tefas_source.fetch_profile("AAL", client_for(handler)) is None


class TestFailures:
    def test_a_403_stops_rather_than_working_around_it(self, caplog):
        """Kararın koşulu: yeniden deneme yok, başlık değiştirme yok."""
        handler = route_handler({"fonUnvanAra": 403, "getFplFonList": 403})
        with caplog.at_level("ERROR"):
            assert tefas_source.fetch_universe(client_for(handler)) == []
        assert "not working around it" in caplog.text

    def test_an_error_in_a_200_body_is_not_read_as_empty(self, caplog):
        """Ağ geçidi hatayı 200 ile ve gövdede döndürüyor -- ölçüldü:
        `{"errorMessage": "Index 0 out of bounds for length 0"}`. Durum
        koduna bakıp geçmek, boş bir sonucu başarı sanmak olurdu."""
        handler = route_handler({
            "fonUnvanAra": {"errorMessage": "Index 0 out of bounds for length 0",
                            "resultList": None},
            "getFplFonList": {"data": []},
        })
        with caplog.at_level("WARNING"):
            assert tefas_source.fetch_universe(client_for(handler)) == []
        assert "Index 0 out of bounds" in caplog.text

    def test_an_upstream_failure_is_named_as_such(self, caplog):
        """Ağ geçidi ayakta ama arkasındaki servis değil. ÖLÇÜLDÜ: 5 Eylül
        2026'da her uç `{"error":"Proxy request failed"}` döndürdü -- tarayıcı
        başlıklarıyla da, sitenin kendi sayfası 200 dönerken. Bu bir engelleme
        değil; öyle loglanması teşhisi bir günde bitiriyor."""
        handler = route_handler({"fonUnvanAra": 500, "getFplFonList": 500})
        with caplog.at_level("WARNING"):
            assert tefas_source.fetch_universe(client_for(handler)) == []
        assert "upstream unavailable" in caplog.text

    def test_a_client_error_does_not_raise(self):
        handler = route_handler({"fonUnvanAra": 404, "getFplFonList": 404})
        assert tefas_source.fetch_universe(client_for(handler)) == []

    def test_the_correlation_id_travels(self):
        """Ağ geçidinin istediği kimlik; HAR'daki her istekte var."""
        handler = route_handler({"fonUnvanAra": ok([]), "getFplFonList": {"data": []}})
        tefas_source.fetch_universe(client_for(handler))
        assert handler.calls[-1].headers.get("x-request-id")

    def test_no_referer_or_origin_is_sent(self):
        """İkisi de "bu istek sizin sitenizdeki bir sayfadan geldi" iddiası
        ve bu doğru değil. Ölçüldü, zaten fark etmiyorlar."""
        handler = route_handler({"fonUnvanAra": ok([]), "getFplFonList": {"data": []}})
        tefas_source.fetch_universe(client_for(handler))
        sent = handler.calls[-1].headers
        assert "referer" not in sent and "origin" not in sent

    def test_a_non_json_body_does_not_raise(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text="<html>")

        assert tefas_source.fetch_universe(client_for(handler)) == []

    def test_a_non_object_body_does_not_raise(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(200, text="[]")

        assert tefas_source.fetch_universe(client_for(handler)) == []

    def test_an_unreachable_host_does_not_raise(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            raise httpx.ConnectError("refused")

        assert tefas_source.fetch_universe(client_for(handler)) == []


class TestDayParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("2026-07-02", "2026-07-02"),
        ("2026-07-02T00:00:00", "2026-07-02"),
        ("2026-13-45", None),
        ("kısa", None), ("", None), (None, None),
    ])
    def test_days(self, raw, expected):
        """Çözülemeyen tarih None: bugüne damgalamak eski bir fiyatı bugünkü
        gibi gösterirdi."""
        assert tefas_source._day(raw) == expected


class TestNumberParsing:
    @pytest.mark.parametrize("raw,expected", [
        (1.5, 1.5), (2, 2.0), ("3,5", 3.5), ("4.5", 4.5),
        (None, None), ("", None), ("abc", None), (True, None),
    ])
    def test_numbers(self, raw, expected):
        """`True` sayı DEĞİL: `bool` Python'da `int`in alt sınıfı ve bir
        bayrak fiyat olarak yazılırsa 1,00 TL diye görünürdü."""
        assert tefas_source._number(raw) == expected
