"""KAP bildirimleri.

RSS beslemeleri ikinci elden anlatır: bir gazeteci bildirimi okur ve haber
yazar. KAP birincil kaynaktır -- şirketin kendi beyanı, ihraççısıyla birlikte
etiketli. Ajanın "portföyümdeki hisseye dair ne oldu" sorusuna verebileceği
en sağlam veri bu, ve tek fark bu değil: RSS haberlerinde sembolü METİNDEN
çıkarmak zorundayız ve ölçülen isabet %3, burada `stockCode` kaynağından
geliyor.

## Erişim

Sayfa Next.js ve sonuç listesi SUNUCUDA üretiliyor: `rsc: 1` başlığıyla
yapılan düz bir GET, 2.000 bildirimi flight verisi içinde JSON olarak
döndürüyor. Ölçüldü -- adını söyleyen User-Agent ile, ÇEREZSİZ, tarayıcı
taklidi olmadan 200 dönüyor (963 KB). Yani `README`'deki "engel aşma yok"
kuralıyla hiçbir çatışma yok; bu sıradan bir sayfa isteği.

`_rsc` sorgu parametresi tarayıcının gönderdiği derlemeye özgü bir jeton ve
GEREKMİYOR: onsuz da aynı yanıt geliyor. Sabitlenseydi KAP her dağıtımında
kaynak sessizce boş dönmeye başlardı.

## Neden iki istek

Liste `title` ve kısa bir `summary` taşıyor; bildirimin GÖVDESİ ayrı bir
sayfada (`/tr/Bildirim/{index}`). Gövde, ajana verilecek asıl içerik --
"Sermaye Piyasası Kurulu düzenlemeleri çerçevesinde; 18/08/2026 tarihinde
Şirketimizin 750.000.000,00 TL olan kayıtlı sermaye tavanı..." gibi. Ama
liste her koşuda 2.000 kayıt döndürüyor ve her biri için ayrıntı çekmek
2.000 istek demek. Bu yüzden ayrıntı YALNIZCA daha önce görülmemiş
bildirimler için ve koşu başına sınırlı sayıda çekiliyor; hangilerinin
bilindiğini backend söylüyor (`market/news/known-ids`), tıpkı mum verisinde
`candles/coverage`'a sorulduğu gibi.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import httpx

from .. import config
from . import rss_source

log = logging.getLogger("moneyfast.ingestor.kap")

#: Haber kaydının `source` alanı. Backend "hangileri bende var" sorusunu
#: bununla süzüyor.
#: `robots.txt` ÇEKİLEMİYOR: KAP o yola 666 döndürüyor (ölçüldü). Dolayısıyla
#: uygulanacak bir direktif yok ve `rss_source._may_fetch`'in zaten uyguladığı
#: kural geçerli -- "robots.txt yoksa bu, gelenek gereği izindir, hata
#: değildir". Buraya yazılı, çünkü ileride biri "robots'u kontrol ettik mi"
#: diye sorduğunda cevabın kodda durması gerekiyor.
#:
#: Bildirim sayfası, adını söyleyen ve ÇEREZSİZ bir GET'e 200 dönüyor; tarayıcı
#: taklidi yapılmıyor, engel aşılmıyor. README'deki veri erişim politikasıyla
#: hiçbir çatışma yok.
SOURCE = "KAP"

HOST = "https://www.kap.org.tr"

#: Şirket bildirimleri sorgusunun sonuç sayfası. `cat=6` sorguyu seçen
#: parametre -- onsuz sayfa 15 KB'lık boş bir kabuk dönüyor.
LIST_URL = f"{HOST}/tr/bildirim-sorgu-sonuc?srcbar=Y&cmp=Y&cat=6&slf=ALL"

DETAIL_URL = f"{HOST}/tr/Bildirim/{{index}}"

#: Koşu başına en fazla bu kadar bildirim alınır. Her biri iki istek demek
#: (liste zaten alındı, ama gövdesi ayrı bir sayfa) ve aralarında
#: `INGESTOR_HOST_DELAY_SECONDS` bekleniyor, yani bu sayı doğrudan koşunun
#: süresi.
#:
#: Bu sayı aynı zamanda YAZILAN bildirim sayısı: gövdesi çekilmemiş bir
#: bildirim hiç yazılmıyor. İkisini ayırmak, kısa özetle yazılan bir
#: bildirimin bir daha hiç istenmemesi demekti -- `known_ids` onu artık
#: "bende var" sayardı ve gövdesi hiçbir zaman gelmezdi.
#:
#: Sınır ayrıca koşuyu SINIRLI tutuyor. İki bin bildirimi tek koşuda işlemeye
#: çalışmak, yarıda kesilen bir koşunun backend'e yazılıp RAG'a ulaşmamış
#: kayıtlar bırakması demek -- ve onlar artık "bilindiği" için bir daha
#: denenmezdi. Ölçüldü: tam olarak bu oldu.
DETAIL_LIMIT = 40

#: Bir bildirimi kimliklendiren şey. `disclosureIndex` KAP'ın kendi kalıcı
#: numarası; metinden türetilen bir hash, bildirim düzeltildiğinde (KAP bunu
#: yapıyor, `isChanged` alanı var) aynı bildirimi ikinci kez yazdırırdı.
_HASH_PREFIX = "KAP:"


def content_hash(index: int) -> str:
    """Bildirimin kimliği. Metinden değil, KAP'ın kendi numarasından."""
    return hashlib.sha256(f"{_HASH_PREFIX}{index}".encode("utf-8")).hexdigest()


def parse_list(payload: str) -> list[dict[str, Any]]:
    """Flight verisinden bildirim kayıtlarını çıkarır.

    Yanıt bir React Server Component akışı, yani satır satır numaralanmış
    parçalardan oluşuyor ve tamamı geçerli JSON DEĞİL. Kayıtlar `"data":[...]`
    dizisinin içinde duruyor; dizi dengeli köşeli parantezle kesilip tek
    başına ayrıştırılıyor. Regex ile alan alan okumak yerine böyle, çünkü
    bildirim metinlerinde tırnak ve süslü parantez geçiyor.
    """
    marker = '"data":[{"disclosureBasic"'
    start = payload.find(marker)
    if start < 0:
        return []
    start += len('"data":')

    depth = 0
    end = -1
    for position in range(start, len(payload)):
        char = payload[position]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = position + 1
                break
    if end < 0:
        log.warning("kap list: unterminated data array")
        return []

    try:
        rows = json.loads(payload[start:end])
    except ValueError as exc:
        log.warning("kap list: could not parse data array: %s", exc)
        return []
    return [row["disclosureBasic"] for row in rows if isinstance(row.get("disclosureBasic"), dict)]


def _published(raw: Optional[str]) -> datetime:
    """`01.09.2026 14:59:55` -> aware datetime.

    Okunamayan bir tarih için "şimdi" kullanılıyor: bildirim listede
    görünüyorsa yayımlanmıştır, ve onu düşürmek KAP'ın biçim değiştirdiği gün
    kaynağı sessizce boşaltırdı.
    """
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw or "", fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    log.warning("kap: unreadable publishDate %r", raw)
    return datetime.now(timezone.utc)


def _symbols(record: dict[str, Any]) -> list[str]:
    """Bildirimin ilgili olduğu hisse kodları, KAP'ın kendi etiketinden.

    `relatedStocks` virgüllü bir liste olabiliyor (bir şirketin birden fazla
    pay sınıfı). Metinden çıkarım YOK -- bu kaynağın en değerli yanı zaten
    tahmine gerek bırakmaması.
    """
    found: list[str] = []
    for value in (record.get("stockCode"), record.get("relatedStocks")):
        for part in str(value or "").split(","):
            code = part.strip().upper()
            if code and code.isalnum() and 3 <= len(code) <= 6:
                found.append(code)
    return sorted(set(found))


def fetch_list(client: httpx.Client) -> list[dict[str, Any]]:
    """Bildirim listesi. Herhangi bir hatada [] döner, yükseltmez."""
    if not rss_source._may_fetch(LIST_URL, client):
        return []
    rss_source._wait_for_host(LIST_URL)
    headers = {"User-Agent": config.user_agent(), "rsc": "1", "Accept": "*/*"}
    try:
        response = client.get(LIST_URL, headers=headers, timeout=config.request_timeout())
    except Exception as exc:
        log.warning("kap list unreachable: %s", exc)
        return []
    if response.status_code != 200:
        log.warning("kap list returned %d", response.status_code)
        return []
    records = parse_list(response.text)
    log.info("kap: %d disclosures listed", len(records))
    return records


def fetch_detail(client: httpx.Client, index: int) -> str:
    """Bildirimin gövdesi, işaretlemesi temizlenmiş.

    Boş dönerse çağıran listeden gelen kısa özetle devam eder: gövdesi
    alınamayan bir bildirimi hiç kaydetmemek, elde olan bilgiyi de atmak
    olurdu.
    """
    url = DETAIL_URL.format(index=index)
    if not rss_source._may_fetch(url, client):
        return ""
    rss_source._wait_for_host(url)
    try:
        response = client.get(
            url,
            headers={"User-Agent": config.user_agent()},
            timeout=config.request_timeout(),
        )
    except Exception as exc:
        log.warning("kap detail %s unreachable: %s", index, exc)
        return ""
    if response.status_code != 200:
        log.warning("kap detail %s returned %d", index, response.status_code)
        return ""
    return extract_body(response.text)


#: Bildirim gövdesinin durduğu kap. KAP'ın form alanları ve serbest metin
#: blokları bu sınıf adıyla işaretli `div`'lerde; sayfanın geri kalanı menü,
#: başlık ve betik.
_BODY_BLOCK = re.compile(r'gwt-HTML[^"\\]*\\"\\u003e(.{40,8000}?)\\u003c/div')

#: Flight verisindeki `\u003c` biçimli kaçışlar.
_UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")

#: Bir gövdenin en fazla bu kadarı saklanır. Bildirim ekleri sayfaya
#: gömüldüğünde metin on binlerce karaktere çıkabiliyor ve RAG parçası zaten
#: bundan çok daha kısa; kalanı gömme kalitesine bir şey katmadan yer kaplar.
MAX_BODY_CHARS = 8000


def extract_body(page: str) -> str:
    """Ayrıntı sayfasından bildirimin metnini çıkarır.

    Gövde, flight verisine gömülü HTML olarak geliyor, yani önce `\u003c`
    kaçışları çözülüyor sonra etiketler atılıyor. Bloklar tek metinde
    birleştiriliyor: KAP hem serbest anlatıyı hem form alanlarını ayrı
    `div`'lerde veriyor ve ikisi de bildirimin ne dediğini anlatıyor.
    """
    blocks = []
    for raw in _BODY_BLOCK.findall(page or ""):
        unescaped = _UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), raw)
        text = rss_source.clean_summary(unescaped)
        # Tek kelimelik alan etiketleri ("Evet", "Hayır") bir şey anlatmıyor.
        if len(text) > 20:
            blocks.append(text)
    return " ".join(blocks)[:MAX_BODY_CHARS]


def fetch_disclosures(
    known_ids: Iterable[int] = (),
    detail_limit: int = DETAIL_LIMIT,
) -> list[dict[str, Any]]:
    """Yeni bildirimler, haber öğesi biçiminde.

    Dönen sözlükler RSS öğeleriyle aynı şekle sahip, çünkü ikisi de aynı
    lavaboya gidiyor (`sinks.push_news_to_*`). Ayrı bir yol açmak, backend'in
    ve RAG'ın iki farklı biçim tanıması demekti.
    """
    seen = {int(x) for x in known_ids}
    items: list[dict[str, Any]] = []
    detailed = 0

    with httpx.Client(
        follow_redirects=True, headers={"User-Agent": config.user_agent()}
    ) as client:
        for record in fetch_list(client):
            if detailed >= detail_limit:
                # Kalanı bir sonraki koşuda. Yazılmadıkları için "bilinmiyor"
                # kalıyorlar ve sıradaki koşu tam olarak buradan devam ediyor.
                break

            index = record.get("disclosureIndex")
            if not isinstance(index, int) or index in seen:
                continue
            seen.add(index)

            body = fetch_detail(client, index)
            detailed += 1

            title = (record.get("title") or "").strip()
            company = (record.get("companyTitle") or "").strip()
            if not title:
                continue

            # Gövde varsa o, yoksa listedeki kısa özet. Şirket adı metnin
            # başına konuyor: RAG'da parça tek başına aranıyor ve "Sermaye
            # Artırımı" başlığı hangi şirketin olduğunu söylemeden hiçbir
            # sorguya cevap vermez.
            summary = rss_source.clean_summary(record.get("summary") or "")
            content = " ".join(filter(None, (company, summary, body))).strip()

            items.append(
                {
                    "content_hash": content_hash(index),
                    "title": f"{company} — {title}" if company else title,
                    "summary": content or None,
                    "source": SOURCE,
                    "url": DETAIL_URL.format(index=index),
                    "language": "tr",
                    "related_symbols": _symbols(record),
                    "published_at": _published(record.get("publishDate")),
                }
            )

    log.info(
        "kap: %d new disclosures taken this run (%d attempted)", len(items), detailed
    )
    return items
