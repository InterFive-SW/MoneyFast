"""TEFAS — Türk yatırım fonları.

`Fonlar` ekranı `MOCK_FUNDS` üzerinden çiziliyordu ve ekranda "Örnek veri"
uyarısı vardı. Bu modül onu gerçek veriyle değiştiriyor.

## robots.txt istisnası

`tefas.gov.tr/robots.txt` `Disallow: /api/` diyor ve `anthropic-ai`i ayrıca
adlandırıyor. Fon verisi YALNIZCA `/api/` altından geliyor -- sayfalar
istemcide çizilen bir Next.js kabuğu -- dolayısıyla izin verilen bir yol
üzerinden aynı veriye ulaşmak mümkün değil.

Bu istisna ürün sahibinin AÇIK kararı ve `courtesy.ROBOTS_EXEMPT_HOSTS`
içinde ADIYLA duruyor; gerekçesi ve koşulları `docs/TEFAS_INTEGRATION.md`de.
Koşullar: dürüst `User-Agent`, GÜNDE BİR tur (NAV günde bir yayımlanıyor,
daha sık yoklamanın getirisi yok), ve istekler arası bekleme. 403 ya da bir
doğrulama ekranı gelirse bu DURMAK için sinyaldir.

## Uçlar

Hepsi POST. Kütüphanelerin belgelediği GET biçimi ölü -- denendi,
`ERR-006 "Method not found or disabled!"` döndü. Aşağıdakiler tarayıcıdan
alınan bir HAR kaydından çıkarıldı, tahmin değil:

| uç | gövde | verdiği |
|---|---|---|
| `funds/fonUnvanAra` | `{dil, aramaMetni:"", fonTip:null}` | 2.602 fonun kodu ve unvanı, TEK istekte |
| `statistics/tefas/getFplFonList` | `{}` | kurucu (`kurucuAd`) ve durum |
| `funds/fonGnlBlgSiraliGetir` | `{fonTipi, basTarih, bitTarih, basSira, bitSira, dil}` | fiyat, portföy büyüklüğü, kişi sayısı |
| `funds/fonFiyatBilgiGetir` | `{fonKodu, dil, periyod}` | NAV serisi ve kategori derecesi |
| `funds/fonProfilDtyGetir` | `{dil, fonKodu, periyod}` | şemsiye türü (`fonTuru`) |

## Arayüzün istediği ama TEFAS'ın VERMEDİĞİ alanlar

HAR'daki her yanıtın alan adları tarandı (85 ayrı alan). Şunlar yok:
**yönetim ücreti, stopaj, risk değeri, ve hisse bazında portföy dağılımı.**
`dagilimSiraliGetirT` varlık SINIFI yüzdeleri veriyor (`dt`, `fb`, `kkstl`,
`osks`...) ama sütun etiketleri HAR'da yok, dolayısıyla hangi kodun hangi
varlık sınıfı olduğu tahmine kalıyor -- ve tahmin edilmedi.

Bu alanlar UYDURULMUYOR. Deponun kendi kuralı: *"aracın hiç döndürmediği bir
alan için `veri yok` kullanılmaz, o sütun hiç yazılmaz."* Karşılığı olmayan
sütunlar arayüzden kaldırılıyor, `null` ile doldurulmuyor.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from .. import config
from . import courtesy

log = logging.getLogger("moneyfast.ingestor.tefas")

#: Fon tipi kodları. `YAT` menkul kıymet yatırım fonları -- ekranın
#: gösterdiği küme ve TEFAS'ın kendi "2.041 sonuç" ifadesinin karşılığı.
FUND_TYPES = ("YAT", "EMK", "BYF")

#: Tek sayfada istenen satır. HAR'da 25 görüldü ama `basSira`/`bitSira`
#: serbest bir aralık; 1.000 ile bir fon tipi iki istekte iniyor. Sayfa ne
#: kadar büyükse o kadar az istek, o kadar az 429 riski.
PAGE_SIZE = 1000

#: NAV yayımlanmayan günlerde kaç gün geriye bakılır. Hafta sonu iki gün,
#: araya bir tatil girerse birkaç gün daha.
MAX_LOOKBACK_DAYS = 7

#: İstekler arası en az bekleme.
#:
#: İlan edilmiş bir sınır yok ama ÖLÇÜLDÜ: iki saniyeyle koşulan bir turda
#: `fonGnlBlgSiraliGetir` üç kez 429 döndürdü ve o sayfalar kayboldu. 429
#: almak, nezaket katmanının tam da önlemesi gereken şey. Günde bir çalışan
#: bir iş için beklemenin maliyeti yok; kaybolan sayfanın maliyeti var.
MIN_HOST_DELAY_SECONDS = 5.0


def _post(path: str, body: dict[str, Any], client: httpx.Client) -> Optional[Any]:
    """Tek istek. Hata hâlinde `None` döner, YÜKSELMEZ."""
    url = f"{config.tefas_base_url()}/api/{path}"
    if not courtesy.may_fetch(url, client):
        return None
    courtesy.wait_for_host(url, minimum=MIN_HOST_DELAY_SECONDS)

    try:
        response = client.post(
            url,
            json=body,
            headers={
                "User-Agent": config.user_agent(),
                "Content-Type": "application/json",
                # Ağ geçidinin ilişkilendirme kimliği; HAR'daki her istekte
                # var. Kendi UUID'mizi üretmek olağan istemci davranışı.
                #
                # `Origin` ve `Referer` BİLEREK yok: ikisi de "bu istek
                # sizin sitenizdeki bir sayfadan geldi" iddiası ve bu doğru
                # değil. Ölçüldü, zaten fark etmiyorlar -- onlarla da
                # olmadan da aynı cevap dönüyor.
                "x-request-id": str(uuid.uuid4()),
            },
            timeout=config.request_timeout(),
        )
    except Exception as exc:
        log.warning("tefas unreachable (%s): %s", path, exc)
        return None

    if response.status_code >= 500:
        # Ağ geçidi ayakta ama arkasındaki servis değil: gövdesi
        # `{"error":"Proxy request failed"}`. Bizimle ilgili bir engelleme
        # DEĞİL -- ölçüldü, tarayıcı başlıklarıyla da aynı cevap geliyor ve
        # sitenin kendi sayfası 200 dönüyor. Tekrar denemiyoruz: tur günde
        # bir ve yarınki tur zaten yeniden deneyecek.
        log.warning("tefas %s: upstream unavailable (%s) %s",
                    path, response.status_code, response.text[:120])
        return None
    if response.status_code == 403:
        # Kararın koşulu: bu DURMAK için sinyal. Yeniden denemiyoruz,
        # başlık değiştirmiyoruz, vekil sunucu kullanmıyoruz.
        log.error("tefas returned 403 for %s -- stopping, not working around it", path)
        return None
    if response.status_code >= 400:
        log.warning("tefas %s returned %s", path, response.status_code)
        return None

    try:
        payload = response.json()
    except ValueError:
        log.warning("tefas %s replied with non-JSON: %s", path, response.text[:200])
        return None

    if not isinstance(payload, dict):
        return None
    # Ağ geçidi hatayı 200 ile ve gövdede döndürüyor: ölçüldü,
    # `{"errorCode": null, "errorMessage": "Index 0 out of bounds..."}`.
    # Durum koduna bakıp geçmek, boş bir sonucu başarı sanmak olurdu.
    if payload.get("errorMessage"):
        log.warning("tefas %s reported: %s", path, payload["errorMessage"])
        return None
    return payload


def _rows(payload: Optional[Any]) -> list[dict[str, Any]]:
    """`resultList` ya da `data` -- uçlar iki adı da kullanıyor."""
    if not isinstance(payload, dict):
        return []
    rows = payload.get("resultList")
    if rows is None:
        rows = payload.get("data")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def fetch_universe(client: httpx.Client) -> list[dict[str, Any]]:
    """Fon evreni: kod, unvan ve KURUCU.

    İki uç birleştiriliyor çünkü hiçbiri tek başına yetmiyor:
    `fonUnvanAra` bütün fonları veriyor ama kurucusuz, `getFplFonList`
    kurucuyu veriyor. Kurucu, ekrandaki "Kurucu / PYŞ" süzgecinin tamamı.

    Kurucusu bilinmeyen fon DÜŞÜRÜLMÜYOR: adı ve kodu var, yalnızca bir
    süzgeç değeri eksik.
    """
    titles = _rows(_post("funds/fonUnvanAra", {"dil": "TR", "aramaMetni": "", "fonTip": None}, client))
    founders = {
        str(row.get("fonKod") or "").strip().upper(): row
        for row in _rows(_post("statistics/tefas/getFplFonList", {}, client))
    }

    out: list[dict[str, Any]] = []
    for row in titles:
        code = str(row.get("fonKodu") or "").strip().upper()
        title = str(row.get("fonUnvan") or "").strip()
        if not code or not title:
            continue
        extra = founders.get(code) or {}
        out.append({
            "code": code,
            "title": title,
            "founder": str(extra.get("kurucuAd") or "").strip() or None,
            "operator": str(extra.get("oprAd") or "").strip() or None,
            # `durum` "AKTİF" / başka bir şey. Pasif fon SAKLANIYOR ama
            # işaretleniyor: geçmişi olan bir fonu silmek, o fonu tutan
            # kullanıcının geçmişini de silmek olurdu.
            "active": str(extra.get("durum") or "").strip().upper() == "AKTİF",
        })
    log.info("tefas: %d funds in the universe, %d with a founder",
             len(out), sum(1 for f in out if f["founder"]))
    return out


def fetch_daily(client: httpx.Client, on: Optional[date] = None) -> list[dict[str, Any]]:
    """Bir günün fiyat ve büyüklük anlık görüntüsü, her fon tipi için.

    `basTarih == bitTarih`: tek gün istendiğinde uç fon başına TEK satır
    döndürüyor. Aralık verilince fon x gün kadar satır dönüyor (ölçüldü:
    bir aylık aralıkta `toplamSayi` 46.285) ve bize gereken o değil.
    """
    day = on or datetime.now(timezone.utc).date()
    # NAV yalnızca iş günlerinde yayımlanıyor. Cumartesi çalıştırıldığında uç
    # `{"errorMessage": "Index 0 out of bounds for length 0"}` döndürüyor --
    # ölçüldü. En son yayımlanan güne kadar geriye yürüyoruz; tatiller de
    # aynı kapıdan geçiyor, "iş günü" listesi tutmadan.
    for back in range(MAX_LOOKBACK_DAYS + 1):
        rows = _daily_for(day - timedelta(days=back), client)
        if rows:
            return rows
    log.info("tefas: no daily rows in the last %d days", MAX_LOOKBACK_DAYS)
    return []


def _daily_for(day: date, client: httpx.Client) -> list[dict[str, Any]]:
    """Tek bir günün anlık görüntüsü, her fon tipi için."""
    stamp = day.strftime("%Y%m%d")
    out: list[dict[str, Any]] = []
    for fund_type in FUND_TYPES:
        start = 1
        while True:
            payload = _post("funds/fonGnlBlgSiraliGetir", {
                "fonTipi": fund_type, "fonKodu": None, "aramaMetni": None,
                "fonTurKod": None, "fonGrubu": None, "sfonTurKod": None,
                "basTarih": stamp, "bitTarih": stamp,
                "basSira": start, "bitSira": start + PAGE_SIZE - 1,
                "fonTurAciklama": None, "dil": "TR", "kurucuKod": None,
            }, client)
            rows = _rows(payload)
            if not rows:
                break
            out.extend(_normalise_daily(row, fund_type) for row in rows)
            # Sayfa dolmadıysa son sayfadayız. `toplamSayi`ya güvenmiyoruz:
            # tek günlük sorguda o alan `null` gelebiliyor.
            if len(rows) < PAGE_SIZE:
                break
            start += PAGE_SIZE
    kept = [row for row in out if row is not None]
    log.info("tefas: %d daily rows for %s", len(kept), stamp)
    return kept


def _normalise_daily(row: dict[str, Any], fund_type: str) -> Optional[dict[str, Any]]:
    code = str(row.get("fonKodu") or "").strip().upper()
    price = _number(row.get("fiyat"))
    if not code or price is None:
        return None
    return {
        "code": code,
        "title": str(row.get("fonUnvan") or "").strip() or None,
        "fund_type": fund_type,
        "as_of": _day(row.get("tarih")),
        "price": price,
        "shares": _number(row.get("tedPaySayisi")),
        "investors": _number(row.get("kisiSayisi")),
        "size": _number(row.get("portfoyBuyukluk")),
    }


def fetch_prices(
    code: str, client: httpx.Client, months: int = 12,
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    """Bir fonun NAV serisi VE aynı çağrının taşıdığı kategori ölçüleri.

    Getiriler burada HESAPLANMIYOR: seri saklanıyor, yüzdeler backend'de
    ondan türetiliyor. Aynı sayıyı iki yerde hesaplamak, iki farklı cevap
    üretebileceği bir yer açardı.

    Ama `kategoriDerece` / `kategoriFonSay` hesaplanmış bir şey değil,
    TEFAS'ın kendi ölçümü ("86 para piyasası fonu içinde 71.") ve AYNI
    yanıtta geliyor. Bir dönem atılıyorlardı; onları ayrıca istemek 2.602
    isteği ikinci kez yapmak olurdu.
    """
    rows = _rows(_post("funds/fonFiyatBilgiGetir",
                       {"fonKodu": code, "dil": "TR", "periyod": months}, client))
    out = []
    for row in rows:
        day = _day(row.get("tarih"))
        price = _number(row.get("fiyat"))
        if day is None or price is None:
            continue
        out.append({"code": code, "as_of": day, "price": price})

    # Sıra her satırda tekrar ediyor; en yenisi geçerli olan.
    metrics: Optional[dict[str, Any]] = None
    for row in reversed(rows):
        rank = _number(row.get("kategoriDerece"))
        size = _number(row.get("kategoriFonSay"))
        if rank is not None and size is not None:
            metrics = {
                "code": code,
                "category_rank": int(rank),
                "category_size": int(size),
            }
            break
    return out, metrics


def fetch_profile(code: str, client: httpx.Client) -> Optional[dict[str, Any]]:
    """Şemsiye türü. Ekrandaki "Şemsiye Türü" süzgecinin tamamı."""
    rows = _rows(_post("funds/fonProfilDtyGetir",
                       {"dil": "TR", "fonKodu": code, "periyod": "12"}, client))
    for row in rows:
        umbrella = str(row.get("fonTuru") or "").strip()
        if umbrella:
            return {
                "code": code,
                "umbrella": umbrella,
                # Kategorinin ortalama getirisi. Fonun kendi getirisinin
                # yanında ANLAMLI bir karşılaştırma: %38 iyi mi kötü mü,
                # ancak kategorisi %41 yaptıysa cevaplanabiliyor.
                "category_return": _number(row.get("fonTurGetiri")),
            }
    return None


def _number(value: Any) -> Optional[float]:
    """Sayı ya da None. Boş bir alan SIFIR DEĞİLDİR.

    Portföy büyüklüğü bilinmeyen bir fonu sıfır büyüklükle yazmak, onu
    listenin en altına gerçek bir ölçüm gibi yerleştirirdi.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _day(value: Any) -> Optional[str]:
    """`2026-07-02` biçimine indirger; çözülemezse None."""
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    try:
        datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return text[:10]
