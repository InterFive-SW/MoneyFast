"""Configuration, read from the environment at call time.

Read at call time rather than import time so tests can monkeypatch without
reimporting the module, matching the pattern in the MCP server's
`backend_client`.
"""

import os
from typing import Optional

DEFAULT_BACKEND_URL = "http://backend:8000/api"
DEFAULT_RAG_URL = "http://rag:8100"

#: Turkish financial outlets that publish RSS. RSS exists to be read by
#: machines, so nothing here needs to look like a browser or work around a
#: bot check — see the README for why that matters.
DEFAULT_FEEDS = ",".join(
    [
        # Finance-only feeds. Every entry here was probed for status, item
        # count, publication date and URL section before being added.
        #
        # patronlardunyasi publishes four separate finance sections that are
        # genuinely distinct (unlike dunya.com, whose ?finans / ?borsa query
        # strings are ignored and return the homepage feed). `sirketler` is the
        # one that carries company-level news -- without it, "Akbank ile ilgili
        # haberler" had nothing to match, because the general economy feeds
        # only cover macro stories.
        "https://www.patronlardunyasi.com/rss/borsa",
        "https://www.patronlardunyasi.com/rss/finans",
        "https://www.patronlardunyasi.com/rss/sirketler",
        "https://www.patronlardunyasi.com/rss/ekonomi",
        # Anadolu Ajansı's economy category: every item is filed under
        # /tr/ekonomi/, so it needs no filtering.
        "https://www.aa.com.tr/tr/rss/default?cat=ekonomi",
        # Kept, but they are site-wide feeds -- the section filter in
        # rss_source.is_financial is what keeps football and exam results out.
        "https://www.dunya.com/rss?dunya",
        "https://www.ekonomim.com/rss",
        # BloombergHT was dropped: the content is financial but the feed is
        # frozen -- its newest item was two weeks old when checked. A stale
        # feed sitting beside live prices is worse than one fewer source.
    ]
)

#: Borsa İstanbul continuous session, Europe/Istanbul.
MARKET_OPEN_HOUR = 10
MARKET_CLOSE_HOUR = 18

#: Trading hours per market, as [open, close) in Europe/Istanbul, weekdays.
#:
#: One global BIST-hours gate used to decide the whole cycle. That was fine
#: while every instrument was Turkish; with US equities in the universe it
#: means their prices stop refreshing at 18:00 TRT, which is half an hour
#: BEFORE the US session even opens.
#:
#: FX and gold trade nearly around the clock; they are given the full weekday
#: rather than pretending they follow an exchange session.
MARKET_HOURS: dict[str, tuple[int, int]] = {
    "BIST": (MARKET_OPEN_HOUR, MARKET_CLOSE_HOUR),
    # 09:30-16:00 America/New_York is 16:30-23:00 TRT. Whole hours only, so
    # the window opens at 16:00 -- half an hour of pre-open quotes costs one
    # request per cycle and avoids modelling US daylight saving separately.
    "NASDAQ": (16, 23),
    "NYSE": (16, 23),
    "FX": (0, 24),
    "COMEX": (0, 24),
}


def backend_url() -> str:
    return os.getenv("BACKEND_API_BASE_URL", DEFAULT_BACKEND_URL).rstrip("/")


def rag_url() -> str:
    return os.getenv("RAG_API_BASE_URL", DEFAULT_RAG_URL).rstrip("/")


def service_token() -> Optional[str]:
    return os.getenv("BACKEND_API_KEY") or None


def feeds() -> list[str]:
    # `or`, not a getenv default: Compose renders `${NEWS_FEEDS:-}` as an
    # empty string, which IS set as far as getenv is concerned and would
    # silently disable news collection entirely.
    raw = os.getenv("NEWS_FEEDS") or DEFAULT_FEEDS
    return [url.strip() for url in raw.split(",") if url.strip()]


def user_agent() -> str:
    """Identifies the crawler honestly, with a contact route.

    An operator who wants to rate-limit or block us should be able to see who
    we are and get in touch. Disguising the client as a browser is the first
    step of the evasion approach this project deliberately does not take.
    """
    return os.getenv("INGESTOR_USER_AGENT") or (
        "MoneyFastBot/1.0 (+https://github.com/InterFive-SW/moneyfast; internship project)"
    )


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def request_timeout() -> float:
    return _float("INGESTOR_TIMEOUT_SECONDS", 20.0)


def per_host_delay() -> float:
    """Minimum gap between two requests to the same host."""
    return _float("INGESTOR_HOST_DELAY_SECONDS", 2.0)


#: Üst şeritteki enstrümanlar: kur, altın ve endeks. Küçük bir küme olduğu
#: için sık çekilebiliyor.
BAND_MARKETS: set[str] = {"FX", "COMEX"}

#: Şeride endeksler de giriyor; bunlar bir borsada işlem görüyor ama fiyatları
#: tek tek hisselerden bağımsız okunuyor.
BAND_PRODUCT_TYPES: set[str] = {"index"}


def band_interval_seconds() -> int:
    """Şerit ne sıklıkta tazelenir.

    Dört-beş sembol, dolayısıyla otuz saniye rahatça yetiyor: ekranın tepesinde
    sürekli değişen bir kur bandı, bütün evreni aynı sıklıkta çekmeyi
    gerektirmiyor.
    """
    return max(5, _int("INGESTOR_BAND_INTERVAL_SECONDS", 30))


def quote_interval_seconds() -> int:
    """Hisse fiyatları ne sıklıkta tazelenir.

    Beş dakika. Gün içi grafiğin bir işlem gününde 78 noktası olsun diye:
    5 dakikalık barlar bir seansa tam bu kadar sığıyor ve barlar sağlayıcıdan
    gerçek OHLC olarak geliyor.

    Bütçe dar ama ölçülebilir. Zorlanmış bir ısınma turu 1009 sembolü 272
    saniyede çekmişti; normal turlar yalnızca O AN AÇIK olan piyasalara
    süzülüyor (~493 BIST ya da ~517 ABD), yani kabaca yarısı. Tur bütçesini
    aşarsa `run_quotes` bunu uyarı olarak yazıyor ve mevcut geri çekilme
    merdiveni devreye giriyor; kalıcı olarak aşıyorsa değer 10 dakikaya
    çekilmeli.

    Önceden bu değer 30 SANİYEDİ ve bütün evreni kapsıyordu --
    `docker-compose.yml` `INGESTOR_QUOTE_INTERVAL_MINUTES: 15` diye bir değer
    veriyordu ama bu ada bakan hiçbir kod yoktu, dolayısıyla ayar hiçbir zaman
    işlemedi. Evren binlerce enstrümana çıkarken saniyelik bir tur, sağlayıcıya
    dakikada iki bin istek demek.

    Şerit ayrı ve hızlı (`band_interval_seconds`); sohbetin sorduğu tek bir
    sembol ise `/refresh` ile anında çekiliyor, dolayısıyla onbeş dakika
    hiçbir yerde "eski fiyat" anlamına gelmiyor.

    5 saniyelik taban, bir yazım hatasının bunu istek seline çevirmesine karşı.
    """
    minutes = _int("INGESTOR_QUOTE_INTERVAL_MINUTES", 5)
    return max(5, _int("INGESTOR_QUOTE_INTERVAL_SECONDS", minutes * 60))


def is_band_product(product: dict) -> bool:
    """Enstrüman hızlı (şerit) katmanına mı ait."""
    return (
        product.get("market") in BAND_MARKETS
        or product.get("product_type") in BAND_PRODUCT_TYPES
    )


def news_interval_minutes() -> int:
    return _int("INGESTOR_NEWS_INTERVAL_MINUTES", 15)


def history_days() -> int:
    """How much daily history to request on the nightly candle job."""
    return _int("INGESTOR_HISTORY_DAYS", 730)


#: Below this many daily bars, the start-up backfill treats an instrument as
#: needing history. Well under `history_days()` on purpose: the point is to
#: separate "has a usable series" from "has nothing", not to keep every symbol
#: topped up to the same bar count. Holidays, listing dates and provider gaps
#: all make a full 400 unreachable for some names, and a threshold near it
#: would re-fetch those every single start.
CANDLE_MIN_BARS = _int("INGESTOR_CANDLE_MIN_BARS", 60)


def respect_robots() -> bool:
    """Deliberately not a documented off switch.

    It exists so a test can bypass a network call, not so an operator can
    disable the check. Anything reachable only by ignoring robots.txt is out
    of scope for this project.
    """
    return os.getenv("INGESTOR_RESPECT_ROBOTS", "true").lower() != "false"


#: Successive interval multipliers applied after a rate-limit response. This
#: is what "without getting stopped" actually looks like: backing off when
#: asked, rather than pretending to be a browser.
BACKOFF_LADDER = (1, 3, 6)


def refresh_port() -> int:
    """Anlık fiyat tazeleme uç noktasının dinlediği port.

    Yalnızca `moneyfast-net` üzerinden erişilebilir; compose'da host'a
    açılmıyor.
    """
    return _int("INGESTOR_REFRESH_PORT", 8200)


def intraday_history_days() -> int:
    """Açılışta çekilecek gün içi geçmiş, gün olarak.

    Aylık grafik 5 dakikalık barların saatlik kovalarından çiziliyor, yani otuz
    günlük gün içi veriye ihtiyaç duyuyor. Sağlayıcı bu barları ~60 gün geriye
    veriyor; üstünü istemek boş döner.
    """
    return max(1, min(60, _int("INGESTOR_INTRADAY_HISTORY_DAYS", 30)))


def fundamentals_workers() -> int:
    """Temel veri turunda eşzamanlı istek sayısı.

    Sağlayıcı toplu bir uç sunmadığı için sembol başına bir istek gerekiyor;
    sırayla 1009 sembol saatler sürüyor.

    Altı, on iki değil: on iki iş parçacığıyla 828 sembol denendiğinde sağlayıcı
    "Too Many Requests" döndürmeye başladı ve tur boş veriyle geri geldi. `.info`
    uç noktası `download`'dan çok daha pahalı; amaç turu hızlandırmak,
    sağlayıcıyı zorlamak değil.
    """
    return max(1, min(16, _int("INGESTOR_FUNDAMENTALS_WORKERS", 6)))


# ── KAP ──────────────────────────────────────────────────────────────────────
# Kamuyu Aydınlatma Platformu. Ayrı bir kaynak, ayrı bir tempo: bildirimler
# haber akışından seyrek gelir ama fiyat etkisi daha yüksektir.


def kap_base_url() -> str:
    return os.getenv("INGESTOR_KAP_BASE_URL", "https://www.kap.org.tr").rstrip("/")


def kap_interval_minutes() -> int:
    """Bildirim yoklama aralığı.

    Piyasa saatlerine BAĞLANMIYOR: fiyata en çok etki eden bildirimler
    18:00 kapanışından sonra ve açılıştan önce yayımlanıyor. Seansa
    kısıtlamak, tam da beklenmesi gereken açıklamaları kaçırmak olurdu.
    """
    return max(1, _int("INGESTOR_KAP_INTERVAL_MINUTES", 20))


def kap_window_days() -> int:
    """Tek `byCriteria` çağrısının kapsadığı gün sayısı.

    Ölçüldü: bir haftada 1101, altmış günde tam 2000 (yani tavan). Üç gün
    ~470 satır demek, tavanın çok altında — dolayısıyla olağan durumda
    pencere hiç ikiye bölünmüyor.
    """
    return max(1, _int("INGESTOR_KAP_WINDOW_DAYS", 3))


def kap_backfill_days() -> int:
    """Geçmişe dönük tarama derinliği. 183 = altı ay."""
    return max(1, _int("INGESTOR_KAP_BACKFILL_DAYS", 183))


def kap_pdf_window_days() -> int:
    """Ekli PDF'lerin okunacağı geriye dönük pencere, gün.

    Ekler gövdeden pahalı: ek başına bir indirme daha, artı ayrıştırma.
    Altı aylık taramanın tamamında açık bırakmak, sürenin üçte birini
    kimsenin sormayacağı eski bilanço eklerine harcamak olurdu. Güncel
    bildirimlerde açık, derin taramada kapalı.
    """
    return max(0, _int("INGESTOR_KAP_PDF_WINDOW_DAYS", 30))


def kap_corpus_page() -> int:
    """Arşiv taramasında tek seferde okunan bildirim sayısı."""
    return max(1, _int("INGESTOR_KAP_CORPUS_PAGE", 300))


def kap_corpus_budget() -> int:
    """Tek turda kaç eksik gövde indirilir.

    Gövde başına bir istek ve host başına iki saniye var. Sınırsız
    bırakmak, 28.984 bildirimlik arşivde tek bir turun saatlerce sürmesi ve
    bu arada başka hiçbir işin sıra bulamaması demekti.
    """
    return max(0, _int("INGESTOR_KAP_CORPUS_BUDGET", 120))


# --------------------------------------------------------------------------
# GDELT — küresel haber. Türkçe tarafı RSS ve KAP karşılıyor; bu uç İNGİLİZCE
# bir tam metin indeksi ve dünyanın geri kalanını getiriyor.
# --------------------------------------------------------------------------

#: Varsayılan sorgular.
#:
#: Şirket adı DEĞİL, MEKANİZMA seçildi. Bir Türk yatırımcının portföyünü
#: yurt dışından etkileyen şey tek tek yabancı şirketler değil, fiyat
#: kanalları: petrol (havayolu ve ulaştırma maliyeti), faiz ve enflasyon
#: (değerleme ve kur), jeopolitik ve tedarik zinciri (girdi maliyeti),
#: çip ve savunma (BIST'te doğrudan karşılığı olan iki sektör).
#:
#: Sorgu başına bir istek ve istek başına beş saniye var, dolayısıyla bu
#: liste bir bütçe: sekiz sorgu ~40 saniye demek.
DEFAULT_GDELT_QUERIES = ",".join([
    '"oil prices"',
    '"crude oil" (OPEC OR sanctions OR strike)',
    '"Federal Reserve" (rates OR inflation)',
    '"supply chain" (disruption OR shortage)',
    '"semiconductor" (export OR restriction OR shortage)',
    '"natural gas" (price OR pipeline)',
    '"Turkish lira"',
    '"Borsa Istanbul" OR "Turkish stocks"',
])


def gdelt_base_url() -> str:
    return os.getenv("INGESTOR_GDELT_BASE_URL", "https://api.gdeltproject.org").rstrip("/")


def gdelt_queries() -> list[str]:
    # `or`, not a getenv default: Compose renders an unset variable as an
    # empty string, which IS set as far as getenv is concerned -- the same
    # trap `feeds()` documents.
    raw = os.getenv("INGESTOR_GDELT_QUERIES") or DEFAULT_GDELT_QUERIES
    return [query.strip() for query in raw.split(",") if query.strip()]


def gdelt_timespan_days() -> int:
    """Geriye dönük pencere, gün.

    Ölçüldü: `7d` "The TIMESPAN is too large" ile reddediliyor, `3d`
    çalışıyor. Kaynak modülü tavanı ayrıca uyguluyor.
    """
    return max(1, _int("INGESTOR_GDELT_TIMESPAN_DAYS", 1))


def gdelt_max_records() -> int:
    """Sorgu başına satır. Ölçüldü: 250 reddediliyor, tavan 200."""
    return max(1, _int("INGESTOR_GDELT_MAX_RECORDS", 60))


def gdelt_interval_minutes() -> int:
    """Küresel haber yoklama aralığı.

    RSS'ten (15 dk) seyrek: sekiz sorgu, sorgu başına beş saniye zorunlu
    gecikme demek ve pencere zaten bir gün. Daha sık yoklamak aynı
    haberleri yeniden indirip aynı `content_hash`lerde elenmeleri olurdu.
    """
    return max(1, _int("INGESTOR_GDELT_INTERVAL_MINUTES", 60))
