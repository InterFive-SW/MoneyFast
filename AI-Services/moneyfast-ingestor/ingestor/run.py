"""Ingestor entrypoint: one-shot runs and the scheduler.

    python -m ingestor.run --once           everything, once, then exit
    python -m ingestor.run --once --quotes  just prices
    python -m ingestor.run                  scheduled, forever

Every job is written so that running it twice changes nothing the second time.
Quotes append (a price at a point in time is a fact, not a correction);
candles and news are deduplicated by the receiving service. That is what makes
a missed cycle self-healing instead of something to reconcile by hand.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from . import config, refresh_server, sinks
from .sources import (
    gdelt_source,
    news_api_source,
    tefas_source,
    kap_archive,
    kap_source,
    rss_source,
    yfinance_source,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("moneyfast.ingestor")

ISTANBUL = ZoneInfo("Europe/Istanbul")

#: Tek bir ingest isteğinde taşınacak azami bar. Geri doldurma on binlerce bar
#: üretiyor ve hepsini tek gövdede göndermek zaman aşımına açık tek bir adım
#: olurdu.
CANDLE_PUSH_CHUNK = 5_000

#: Aynı gerekçe temel veri için. Tek gövdede giden bir partide tek bir geçersiz
#: değer, 828 enstrümanın tamamını kaybettiriyordu.
FUNDAMENTALS_PUSH_CHUNK = 200


def open_markets(moment: datetime | None = None) -> set[str]:
    """Which markets are trading right now, weekdays only.

    Polling a closed market just rewrites the same closing price every cycle,
    which costs the provider requests and buys nobody anything. Holidays are
    not modelled — the cost of polling on one is a handful of unchanged rows.

    Per market rather than one global gate: BIST closes at 18:00 TRT and the
    US session runs to 23:00, so a single gate left every US price frozen for
    the whole American afternoon.
    """
    moment = (moment or datetime.now(timezone.utc)).astimezone(ISTANBUL)
    if moment.weekday() >= 5:
        return set()
    return {
        market
        for market, (opens, closes) in config.MARKET_HOURS.items()
        if opens <= moment.hour < closes
    }


def market_is_open(moment: datetime | None = None) -> bool:
    """Whether ANY market is trading. Kept for callers that only need a
    yes/no, and for the daily jobs that do not care which venue."""
    return bool(open_markets(moment))


#: The share of a batch that may come back empty before the cycle counts as
#: degraded. A handful of delisted tickers is normal; a third of the universe
#: missing means the provider is struggling and hammering it will not help.
MISSING_TOLERANCE = 0.25

#: Kaç sembolün eksik olması ORANI anlamlı kılar.
#:
#: Oran tek başına küçük katmanda saçmalıyor: bant katmanında dört sembol var
#: (üç kur + altın) ve BİRİ boş dönerse %25, ikisi %50 -- ikisi de toleransı
#: aşıyor. Ölçüldü, tek bir turda: "2/4 symbols came back empty" ve hemen
#: ardından "rate limited". Toleransın kendi gerekçesi büyük bir evren için
#: yazılmış ("a third of the universe"); dörtlük bir kümede o cümlenin
#: karşılığı yok.
#:
#: Üç, çünkü dörtlük katmanda dördün üçünün boş dönmesi gerçekten bir
#: sağlayıcı sorunudur; 487'lik katmanda oran zaten çok daha önce devreye
#: giriyor (122 sembol).
MISSING_FLOOR = 3

#: Index into config.BACKOFF_LADDER. Widened on a rate limit, reset on a
#: clean cycle.
#: KATMAN BAŞINA. Tek bir genel sayaçtı ve iki katman onu paylaşıyordu: bant
#: katmanındaki geçici bir eksik, 487 sembollük toplu katmanın aralığını da
#: genişletiyordu. İki katmanın ne büyüklüğü ne de ritmi aynı; sağlayıcının
#: biri hakkında söylediği şey diğeri hakkında bir şey söylemiyor.
_backoff_steps: dict[str, int] = {}


#: Katman adından o katmanın taban aralığına.
_TIER_BASE_SECONDS = {
    "band": config.band_interval_seconds,
    "bulk": config.quote_interval_seconds,
    "all": config.quote_interval_seconds,
}

#: Aralığı gerçekten değiştirmek için zamanlayıcı gerekiyor. `start_scheduler`
#: kuruyor; testler ve tek seferlik çalıştırmalar None bırakıyor ve o durumda
#: geri çekilme yalnızca kaydediliyor.
_scheduler = None
_JOB_FOR_TIER = {"band": "quotes_band", "bulk": "quotes_bulk"}


def current_interval_seconds(tier: str = "bulk") -> int:
    """The quote interval for a tier, widened while we are being rate limited."""
    ladder = config.BACKOFF_LADDER
    multiplier = ladder[min(_backoff_steps.get(tier, 0), len(ladder) - 1)]
    base = _TIER_BASE_SECONDS.get(tier, config.quote_interval_seconds)()
    return base * multiplier


def _apply_interval(tier: str) -> None:
    """Yeni aralığı ZAMANLAYICIYA uygular.

    Bunu yapmadan önce merdiven yalnızca bir log satırıydı: işler açılışta
    sabit aralıkla kuruluyor ve `current_interval_seconds` hiçbir yerde
    okunmuyordu. "widening the quote interval to 2700s" uyarısı, hiç
    gerçekleşmeyen bir eylemi bildiriyordu -- ve bu, fiyatların neden
    tazelenmediğini arayan birini yanlış yere bakmaya gönderirdi.
    """
    job_id = _JOB_FOR_TIER.get(tier)
    if _scheduler is None or job_id is None:
        return
    try:
        _scheduler.reschedule_job(
            job_id, trigger="interval", seconds=current_interval_seconds(tier)
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("could not reschedule %s: %s", job_id, exc)


def _note_rate_limit(tier: str = "bulk") -> None:
    step = _backoff_steps.get(tier, 0)
    if step < len(config.BACKOFF_LADDER) - 1:
        _backoff_steps[tier] = step + 1
    _apply_interval(tier)
    log.warning(
        "rate limited on %s; widening its interval to %ds",
        tier, current_interval_seconds(tier),
    )


def _note_success(tier: str = "bulk") -> None:
    if _backoff_steps.get(tier):
        _backoff_steps[tier] = 0
        _apply_interval(tier)
        log.info(
            "rate limit cleared on %s; back to %ds", tier, current_interval_seconds(tier)
        )


def run_quotes(
    client: httpx.Client, force: bool = False, tier: str = "all"
) -> dict:
    """Fiyat turu.

    `tier` katmanı seçer: `band` kur/altın/endeks (30 saniyede bir),
    `bulk` hisseler (15 dakikada bir), `all` ikisi birden -- tek seferlik
    çalıştırmalar ve testler için.

    Ayrım şu yüzden var: ekranın tepesindeki kur bandının sürekli oynaması
    isteniyor, ama aynı sıklıkta bin hisse çekmek sağlayıcıya dakikada
    binlerce istek demek.
    """
    started = time.monotonic()
    products = sinks.fetch_products(client)

    if tier in ("band", "bulk"):
        want_band = tier == "band"
        products = [p for p in products if config.is_band_product(p) is want_band]
        # Yalnızca katman süzgeci uygulandığında anlamlı: boş bir katman,
        # çekilecek bir şey olmadığını söyler. `tier="all"` bu kontrolden
        # geçmez, çünkü orada boş liste "evren boş" demektir ve o durumda
        # turun geri kalanı zaten hiçbir şey yapmaz.
        if not products:
            log.info("no instruments in tier %s", tier)
            return {"skipped": True}

    if not force:
        trading = open_markets()
        # Backend'e her turda bildiriliyor -- KAPALIYKEN DE, çünkü "hepsi
        # kapalı" da bir olgu ve bildirilmezse backend eski bir kaydı okumaya
        # devam ederdi.
        sinks.push_sessions(client, trading)
        if not trading:
            log.info("all markets closed, skipping quote cycle")
            return {"skipped": True}
        # An instrument whose market we do not recognise is polled rather than
        # dropped: an unknown venue is a gap in MARKET_HOURS, and silently
        # never pricing it would be much harder to notice than one extra
        # request.
        products = [
            p for p in products
            if p.get("market") in trading or p.get("market") not in config.MARKET_HOURS
        ]
        if not products:
            log.info("no instruments in the open markets %s", sorted(trading))
            return {"skipped": True}

    try:
        quotes = yfinance_source.fetch_quotes(products)
    except Exception as exc:
        # A 429 from the provider is a request to slow down, not a reason to
        # try harder.
        if "429" in str(exc) or "rate" in str(exc).lower():
            _note_rate_limit(tier)
            return {"rate_limited": True}
        raise

    # `yf.download` swallows per-symbol failures and still returns a frame, so
    # a stalled provider shows up as a SHORT batch rather than an exception.
    # Treating that as success is what let the cycle run 6x over budget
    # without the backoff ladder ever engaging.
    requested = sum(1 for p in products if p.get("data_symbol"))
    missing = requested - len(quotes)
    # İKİ KOŞUL BİRDEN. Oran tek başına dörtlük bant katmanında saçmalıyor:
    # bir sembol %25, iki sembol %50 eder ve ikisi de toleransı aşar.
    degraded = (
        requested > 0
        and missing >= MISSING_FLOOR
        and missing > requested * MISSING_TOLERANCE
    )

    result = sinks.push_market_data(client, quotes, []) or {}
    if degraded:
        log.warning("%d/%d symbols came back empty", missing, requested)
        _note_rate_limit(tier)
    else:
        _note_success(tier)
    elapsed = time.monotonic() - started
    log.info(
        "quote cycle [%s]: %d fetched, %s written, %.2fs",
        tier, len(quotes), result.get("quotes_written", 0), elapsed,
    )
    if elapsed > current_interval_seconds(tier):
        # Visible rather than silent: the scheduler will coalesce the overlap,
        # but a cycle that never fits its budget is a configuration problem.
        log.warning("quote cycle took longer than its interval")
    return {"fetched": len(quotes), "seconds": round(elapsed, 2), **result}


def run_fundamentals(client: httpx.Client) -> dict:
    """Valuation ratios. Daily, because the provider has no batch form."""
    products = sinks.fetch_products(client)
    rows = yfinance_source.fetch_fundamentals(products)
    result = sinks.push_fundamentals(client, rows) or {}
    log.info("fundamentals cycle: %d fetched, %s written",
             len(rows), result.get("fundamentals_written", 0))
    return {"fetched": len(rows), **result}


def run_quarterly(client: httpx.Client) -> dict:
    """Çeyreklik gelir tablosu. Temel veriden AYRI bir tur ve daha seyrek.

    Anlık görüntü her gün tazeleniyor çünkü fiyata bağlı oranlar (F/K, PD/DD)
    her gün değişiyor. Çeyreklik rakamlar ise üç ayda bir açıklanıyor;
    günde bir çekmek, doksan gün boyunca aynı satırı doksan kez yazmak olurdu.

    Ölçülen hız ~0,8 sn/sembol, dolayısıyla evrenin tamamı ~13 dakika.
    """
    products = sinks.fetch_products(client)
    rows = yfinance_source.fetch_quarterly_financials(products)
    result = sinks.push_quarterly(client, rows) or {}
    log.info("quarterly cycle: %d rows fetched, %s written",
             len(rows), result.get("quarterly_written", 0))
    return {"fetched": len(rows), **result}


def backfill_intraday(client: httpx.Client) -> dict:
    """Gün içi barların derin penceresi; açılışta bir kez.

    Haftalık ve aylık grafikler 5 dakikalık barların 15 dakikalık ve saatlik
    kovalarından çiziliyor, dolayısıyla bir günlük veri onlara yetmiyor.
    Sağlayıcı 5 dakikalık barları ~60 gün geriye veriyor; otuz gün hem ay
    görünümünü dolduruyor hem de tek seferlik bir maliyet.

    Periyodik iş bunu yapmıyor: otuz günü beş dakikada bir yeniden çekmek,
    değişmeyen barları durmadan yeniden yazmak olurdu.
    """
    return run_intraday_candles(client, days=config.intraday_history_days())


def backfill_fundamentals(client: httpx.Client) -> dict:
    """Temel verisi hiç olmayan enstrümanlar; açılışta bir kez.

    Isı haritası tayfını piyasa değerinden alıyor. Migration 0019 evreni
    190'dan 1009'a çıkardı ama günlük iş henüz üzerlerinden geçmedi: 1009
    hissenin 183'ünde piyasa değeri var, NYSE'de hiç yok. Gecelik işi beklemek,
    S&P sekmesinin bir gün boyunca boş kalması demek.

    Yalnızca EKSİK olanlar isteniyor; günlük iş zaten hepsini tazeliyor.
    """
    wanted = sinks.fetch_missing_fundamentals(client)
    if not wanted:
        log.info("fundamentals: nothing missing")
        return {"skipped": True}

    products = [p for p in sinks.fetch_products(client) if p.get("symbol") in wanted]
    rows = yfinance_source.fetch_fundamentals(products)

    # Parçalayarak itiliyor. Tek gövdede gönderildiğinde bir tek geçersiz değer
    # 828 satırın tamamını düşürüyordu; parçalar hâlinde en fazla bir parça
    # kaybedilir ve gerisi yazılır.
    written = 0
    for start in range(0, len(rows), FUNDAMENTALS_PUSH_CHUNK):
        chunk = rows[start:start + FUNDAMENTALS_PUSH_CHUNK]
        result = sinks.push_fundamentals(client, chunk) or {}
        written += result.get("fundamentals_written", 0)

    log.info("fundamentals backfill: %d of %d symbols returned data, %d written",
             len(rows), len(products), written)
    return {"fetched": len(rows), "fundamentals_written": written}


def run_intraday_candles(client: httpx.Client, days: int = 1) -> dict:
    """5 dakikalık barlar; yalnızca gereken enstrümanlar için.

    Portföy performansının "Gün" görünümü bunu okuyor: bir işlem gününe tam
    78 bar sığıyor. Daha kaba aralıklar (15 dakika, saat) bu seriden
    toplanarak üretiliyor, ikinci bir seri saklanmıyor. Barlar sağlayıcıdan
    GERÇEK OHLC olarak geliyor -- anlık fiyattan bar üretmek açılış, yüksek ve
    düşük değerlerini uydurmak olurdu.

    Evrenin tamamı çekilmiyor: hangi sembollerin gerektiğini backend söylüyor
    (tutulan, izlenen, kur ve endeks), çünkü kimin neyi tuttuğu uygulamanın
    bilgisi ve bu servis onu bilmiyor.
    """
    wanted = sinks.fetch_intraday_symbols(client)
    if not wanted:
        log.info("intraday: nothing to fetch")
        return {"skipped": True}

    products = [p for p in sinks.fetch_products(client) if p.get("symbol") in wanted]
    # Sağlayıcı gün içi barları yalnızca son ~60 gün için veriyor; bir günlük
    # pencere, gün görünümünün ihtiyacı olan tek şey.
    rows = yfinance_source.fetch_candles(products, days=days, interval="5m")

    # Parçalayarak itiliyor. Otuz günlük geri doldurma 26 sembol için ~94.000
    # bar demek; tek bir gövdede göndermek hem yaklaşık 10 MB'lık bir istek
    # hem de zaman aşımına açık tek bir "ya hep ya hiç" adımı olurdu.
    written = 0
    for start in range(0, len(rows), CANDLE_PUSH_CHUNK):
        chunk = rows[start:start + CANDLE_PUSH_CHUNK]
        result = sinks.push_market_data(client, [], chunk) or {}
        written += result.get("candles_written", 0)

    log.info("intraday cycle: %d bars for %d symbols, %d written",
             len(rows), len(products), written)
    return {"fetched": len(rows), "candles_written": written}


def run_interest(client: httpx.Client) -> dict:
    """Vadeli hesap faizini işletmesi için backend'i tetikler.

    Bu servisin veritabanı kredensiyeli yok ve olmamalı; yaptığı tek şey günlük
    tetiği iletmek. Uç nokta aynı gün ikinci kez çağrıldığında hiçbir şey
    ödemiyor, dolayısıyla tekrar zararsız.
    """
    result = sinks.trigger_interest_accrual(client) or {}
    log.info("interest cycle: %s account(s) accrued", result.get("accrued", 0))
    return result


def run_candles(
    client: httpx.Client,
    symbols: set[str] | None = None,
    days: Optional[int] = None,
) -> dict:
    """Daily bars. `symbols` narrows the run to a subset; None means all.

    The subset exists for the start-up backfill, which asks for only the
    instruments that are short of history.

    `days` narrows the WINDOW. Bir günlük boşluğu kapatmak için iki yıllık
    pencere istemek, sağlayıcıdan her sembol için gereksiz yüz kat veri
    çekmek olurdu; catch-up işi ne kadar geride kaldığını biliyor.
    """
    products = sinks.fetch_products(client)
    if symbols is not None:
        products = [p for p in products if p.get("symbol") in symbols]
        if not products:
            return {"fetched": 0, "candles_written": 0}
    candles = yfinance_source.fetch_candles(
        products, days=days or config.history_days()
    )

    # Gün içi yolla AYNI parçalama. Buraya eklenmemişti ve ilk açılış
    # ölçüldüğünde 1.011 enstrüman için 638.968 bar tek bir gövdede
    # gönderiliyordu: istek zaman aşımına uğruyor, sinks bir hata satırı yazıp
    # None dönüyor ve turun TAMAMI kayboluyordu. Yazılan günlük bar sayısı
    # sıfırdı, dolayısıyla risk ölçümü -- günlük kapanışları okuyan tek
    # tüketici -- herkes için "ölçülemedi" veriyordu.
    #
    # "Ya hep ya hiç" olmaması da ayrıca önemli: zaman aşımına uğrayan bir
    # parça yalnızca kendi barlarını götürür, bir sonraki açılışta kapsama
    # denetimi o sembolleri yine eksik bulur ve tekrar dener.
    written = 0
    for start in range(0, len(candles), CANDLE_PUSH_CHUNK):
        chunk = candles[start:start + CANDLE_PUSH_CHUNK]
        result = sinks.push_market_data(client, [], chunk) or {}
        written += result.get("candles_written", 0)

    log.info(
        "candle cycle: %d symbols, %d bars offered, %d new",
        len(products), len(candles), written,
    )
    return {"fetched": len(candles), "candles_written": written}


def backfill_candles(client: httpx.Client) -> dict:
    """Fetch history for instruments that do not have enough of it yet.

    Daily bars used to be a 19:15 cron and nothing else, so a clone started in
    the morning showed empty charts all day. That gap is why the seed data
    carried 7.5 MB of candles -- committed history for a series this service
    produces on its own.

    The coverage check is what makes running this on every start reasonable.
    A first boot back-fills the whole universe; a restart an hour later finds
    everything covered and costs one HTTP call; an instrument introduced by a
    later migration is picked up the next time the service comes up, with no
    one having to remember it.
    """
    coverage = sinks.fetch_candle_coverage(client)
    products = sinks.fetch_products(client)
    thin = {
        p["symbol"] for p in products
        if coverage.get(p["symbol"], {}).get("bars", 0) < config.CANDLE_MIN_BARS
    }
    if not thin:
        log.info("candle backfill: all %d instruments covered, nothing to fetch",
                 len(products))
        return {"fetched": 0, "candles_written": 0}

    log.info("candle backfill: %d of %d instruments below %d bars",
             len(thin), len(products), config.CANDLE_MIN_BARS)
    return run_candles(client, symbols=thin)


def topup_candles(client: httpx.Client) -> dict:
    """Geçmişi olan ama GÜNCEL olmayan enstrümanların aradaki barları.

    `backfill_candles` "hiç geçmişi yok" sorusunu cevaplıyor. Bu, ayrı bir
    soruyu: "geçmişi var ama eski mi". İkisi karışırsa commit'lenmiş taban
    verisiyle açılan bir klon her enstrümanı ~500 barla dolu bulur, geri
    doldurma haklı olarak atlar -- ve akşam 19:15 cron'una kadar hiçbir şey
    çalışmaz. Sabah 10'da açan biri, grafiği commit tarihinde biten bir
    uygulamayı bütün gün görürdü.

    `coverage` zaten sembol başına `{"bars": N, "last": "YYYY-MM-DD"}`
    döndürüyordu; `last` yarısı bugüne kadar hiç okunmuyordu.
    """
    coverage = sinks.fetch_candle_coverage(client)
    if not coverage:
        # Kapsama okunamadı. Geri doldurma zaten güvenli tarafa düşüyor;
        # burada tahminle iş yapmak, evrenin tamamını gereksiz çekmek olurdu.
        return {"skipped": True}

    cutoff = _last_trading_day()
    stale = {
        symbol
        for symbol, entry in coverage.items()
        # Barı hiç olmayanlar backfill'in işi; burada yalnızca ESKİ olanlar.
        if entry.get("bars") and (entry.get("last") or "") < cutoff
    }
    if not stale:
        log.info("candle top-up: every instrument is current as of %s", cutoff)
        return {"fetched": 0, "candles_written": 0}

    # Boşluk kadar pencere, artı bir tampon: sağlayıcı hafta sonlarını ve
    # tatilleri bar döndürmeyerek geçiyor, dolayısıyla takvim günü sayısı
    # işlem günü sayısından her zaman büyük.
    behind = (date.fromisoformat(cutoff) - min(
        date.fromisoformat(entry["last"]) for entry in coverage.values()
        if entry.get("bars") and entry.get("last")
    )).days
    window = min(config.history_days(), behind + TOPUP_MARGIN_DAYS)

    log.info(
        "candle top-up: %d instruments behind %s, fetching %d days",
        len(stale), cutoff, window,
    )
    return run_candles(client, symbols=stale, days=window)


#: Catch-up penceresine eklenen tampon. Sağlayıcı hafta sonu ve tatilde bar
#: döndürmüyor; boşluk takvim günüyle ölçüldüğü için birkaç gün fazladan
#: istemek, eksik istemekten ucuz.
TOPUP_MARGIN_DAYS = 5


def _last_trading_day(today: Optional[date] = None) -> str:
    """En son kapanmış işlem gününün tarihi, ISO.

    Hafta sonu geri sarılıyor: cumartesi sabahı "dün cumaydı" demek, cuma
    barını beklemek demek ve o bar zaten var. Tatil takvimi YOK -- bir resmi
    tatilde tek yapacağı, o gün için boş dönen bir istek atmak.
    """
    day = today or datetime.now(ISTANBUL).date()
    # Pazartesi 0 ... Pazar 6. Bugünün barı henüz kapanmadı, dünden başla.
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def run_news(client: httpx.Client) -> dict:
    items = rss_source.fetch_all()

    # KAP aynı lavaboya akıyor: bildirimler de haber öğesi biçiminde çıkıyor,
    # dolayısıyla backend ve RAG için ikinci bir yol yok. Fark kaynakta --
    # RSS haberlerinde sembolü metinden çıkarmak zorundayız (ölçülen isabet
    # %3), bildirimlerde ihraççı KAP'ın kendi etiketinden geliyor.
    known = sinks.fetch_known_news_ids(client, kap_source.SOURCE)
    disclosures = kap_source.fetch_disclosures(known)
    items = items + disclosures

    # Sıra önemli: backend ÖNCE yazılıyor, çünkü sembolleri o çözüyor
    # (enstrüman evreni orada, bu serviste değil) ve RAG'a giden kopya o
    # etiketleri taşımalı. Ters sırada korpus etiketsiz kalırdı -- ölçüldü,
    # sonuç geri alınmadığı için 1.970 RSS belgesinin sıfırında ticker vardı.
    backend_result = sinks.push_news_to_backend(client, items) or {}
    symbols = backend_result.pop("news_symbols", None) or {}
    embedded = sinks.push_news_to_rag(client, items, symbols)
    log.info(
        "news cycle: %d fetched (%d KAP), %s stored, %d embedded, %d symbol-tagged",
        len(items), len(disclosures), backend_result.get("news_written", 0),
        embedded, len(symbols),
    )
    return {
        "fetched": len(items),
        "kap": len(disclosures),
        "embedded": embedded,
        "tagged": len(symbols),
        **backend_result,
    }


def run_global_news(client: httpx.Client) -> dict:
    """Küresel haber turu. `run_news`ten AYRI, üç sebeple.

    Tempo: sekiz sorgu var ve GDELT istek başına beş saniye istiyor, yani tur
    ~40 saniye sürüyor. Bunu on beş dakikalık RSS döngüsüne katmak, Türkçe
    haberi bir dış servisin temposuna bağlamak olurdu.

    Yalıtım: GDELT ulaşılamazsa Türkçe haber akışı etkilenmemeli. Ayrı iş,
    ayrı hata.

    Aynılık: lavabo AYNI. Öğeler `rss_source`in ürettiği sözlük biçiminde
    çıkıyor, dolayısıyla backend'e ve korpusa giden yol tek -- ikinci bir
    yazma yolu, iki farklı tekilleştirme davranışı demek olurdu.

    Sembol çözümü yine backend'de: `symbol_match` küresel bir haberde de
    BIST adı arıyor ("Turkish Airlines" gibi), ve enstrüman evreni orada.
    """
    # Üç kaynak, tek lavabo: GDELT makro tarafı, Finnhub ve Marketaux şirket
    # seviyesini karşılıyor. Anahtarı olmayan sağlayıcı sessizce atlanıyor,
    # dolayısıyla hiçbir anahtar kurulmamışsa tur yalnızca GDELT ile döner.
    items = gdelt_source.fetch_all()
    seen = {item["content_hash"] for item in items}
    for item in news_api_source.fetch_all():
        # Aynı haber hem GDELT'ten hem bir sağlayıcıdan gelebiliyor.
        if item["content_hash"] in seen:
            continue
        seen.add(item["content_hash"])
        items.append(item)

    if not items:
        log.info("global news cycle: nothing fetched")
        return {"fetched": 0, "embedded": 0, "tagged": 0}

    backend_result = sinks.push_news_to_backend(client, items) or {}
    symbols = backend_result.pop("news_symbols", None) or {}
    embedded = sinks.push_news_to_rag(client, items, symbols)
    log.info(
        "global news cycle: %d fetched, %s stored, %d embedded, %d symbol-tagged",
        len(items), backend_result.get("news_written", 0), embedded, len(symbols),
    )
    return {
        "fetched": len(items),
        "embedded": embedded,
        "tagged": len(symbols),
        **backend_result,
    }


def run_tefas(client: httpx.Client) -> dict:
    """TEFAS turu — günde bir.

    Kapalıysa hiçbir şey yapmıyor. Varsayılan KAPALI, çünkü bu kaynak sitenin
    `robots.txt`'inde belirttiği tercihi geçersiz kılıyor (bkz.
    `courtesy.ROBOTS_EXEMPT_HOSTS` ve `docs/TEFAS_INTEGRATION.md`) ve
    klonlayan bir ekip arkadaşının farkında olmadan devreye sokması doğru
    olmaz.

    Üç adım, üçü de bütçeli:

    1. Evren + günlük anlık görüntü. Toplamda ~10 istek: iki tanesi evren,
       gerisi sayfalama.
    2. Şemsiye türü — fon başına bir istek, bu yüzden yalnızca EKSİK
       olanlar ve tur başına bir bütçe kadar.
    3. NAV serisi — aynı gerekçe, aynı desen. `kap_corpus_budget`in
       yaptığının aynısı.
    """
    if not config.tefas_enabled():
        log.info("tefas: disabled (INGESTOR_TEFAS_ENABLED not set)")
        return {"skipped": True}

    with httpx.Client(
        follow_redirects=True, headers={"User-Agent": config.user_agent()}
    ) as tefas:
        universe = tefas_source.fetch_universe(tefas)
        daily = tefas_source.fetch_daily(tefas)

        # Günlük satır fon adını da taşıyor ama evren turu kurucuyu taşıyor;
        # ikisi AYRI alanlar dolduruyor ve backend kısmi güncelleme yapıyor,
        # dolayısıyla biri diğerini ezmiyor.
        written = sinks.push_funds_to_backend(client, universe + daily)

        coverage = sinks.fetch_fund_coverage(client)
        # Şemsiye türü artık FON BAŞINA değil, ŞEMSİYE BAŞINA bir istek:
        # şemsiye listesi alınıp günlük uç `sfonTurKod` ile süzülüyor.
        # Bütçeye ihtiyaç kalmadı -- tur başına on iki şemsiye, 1.054 fon
        # değil -- ama eksik yoksa hiç yapılmıyor.
        profiles: list[dict] = []
        if coverage.get("missing_umbrella"):
            profiles = tefas_source.fetch_umbrellas(tefas)
        if profiles:
            written["funds_written"] += sinks.push_funds_to_backend(
                client, profiles,
            )["funds_written"]

        missing_prices = (coverage.get("missing_prices") or [])[
            : config.tefas_price_budget()
        ]
        prices: list[dict] = []
        category_metrics: list[dict] = []
        for code in missing_prices:
            series, category = tefas_source.fetch_prices(code, tefas)
            prices.extend(series)
            if category is not None:
                category_metrics.append(category)
        if prices or category_metrics:
            written["prices_written"] += sinks.push_funds_to_backend(
                client, category_metrics, prices,
            )["prices_written"]

    log.info(
        "tefas cycle: %d funds, %d price rows, %d profiles, %d series",
        written["funds_written"], written["prices_written"],
        len(profiles), len(missing_prices),
    )
    return {
        "funds": written["funds_written"],
        "prices": written["prices_written"],
        "profiles": len(profiles),
    }


def _disclosure_index(url: Optional[str]) -> Optional[int]:
    """Kalıcı bağlantının sonundaki bildirim numarası.

    Numara ayrı bir sütunda saklanmıyor: bağlantı zaten atıf için tutuluyor
    ve aynı bilgiyi ikinci bir yerde saklamak, ikisinin ayrışabileceği bir
    yer açardı. Backend `known-ids` ucunda aynı okumayı yapıyor.
    """
    tail = (url or "").rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def bist_universe(client: httpx.Client) -> set:
    """Symbols a KAP disclosure could usefully be about.

    Read from the backend rather than configured here, for the reason
    `fetch_products` already gives: adding an instrument should be one row in
    the database, not a redeploy. It also means the filter widens by itself
    when the universe grows.
    """
    return {
        product["symbol"]
        for product in sinks.fetch_products(client)
        if product.get("market") == "BIST"
    }


#: Bir turda kaç yeni bildirimin gövdesi çekilir. Gövde başına bir istek ve
#: host başına iki saniye var; sınırsız bırakmak, ilk turun saatlerce
#: sürmesi ve bu arada başka hiçbir bildirimin panoya düşmemesi demekti.
KAP_BODY_BUDGET = 60


def run_kap(client: httpx.Client, since=None, until=None, bodies: bool = True) -> dict:
    """Poll KAP for disclosures naming an instrument we carry.

    Two passes, and the order matters. The listing is one request for a whole
    window, so every matched disclosure reaches the dashboard immediately. Only
    then do we ask the backend which of them are NEW and spend a request each
    on their bodies — in steady state a handful, not four hundred.

    Pushed through the same news sink as RSS: a disclosure IS market news, it
    just arrives with an issuer attached and a permanent link.
    """
    today = datetime.now(ISTANBUL).date()
    until = until or today
    # A window rather than a point: a disclosure filed while the previous
    # cycle was mid-flight would otherwise fall between two polls, and
    # re-offering a stored one costs nothing (`ON CONFLICT DO NOTHING`).
    since = since or (until - timedelta(days=config.kap_window_days() - 1))

    items = kap_archive.fetch_all(bist_universe(client), since, until, client)

    # Which bodies to read is decided BEFORE the listing is stored, because
    # storing it is what would make them all look already-known.
    fresh = []
    if bodies and items:
        # Tek bir "elimizde ne var" ucu. Numara kalıcı bağlantının içinde,
        # dolayısıyla ayrı bir hash sorgusu ikinci bir cevap kaynağı olurdu.
        known = sinks.fetch_known_news_ids(client, kap_source.SOURCE)
        fresh = [
            item for item in items
            if _disclosure_index(item.get("url")) not in known
        ][:KAP_BODY_BUDGET]

    backend_result = sinks.push_news_to_backend(client, items) or {}
    embedded = sinks.push_disclosures_to_rag(client, _with_bodies(fresh, client))

    unread = kap_archive.last_run_failures
    log.info(
        "kap cycle %s..%s: %d matched, %s stored, %d bodies embedded%s",
        since, until, len(items), backend_result.get("news_written", 0), embedded,
        f" -- INCOMPLETE, {unread} windows unread" if unread else "",
    )
    result = {"fetched": len(items), "embedded": embedded, **backend_result}
    if unread:
        # Yüzeye çıkıyor, çünkü bir sonraki turun aynı pencereyi yeniden
        # sunması yalnızca yoklama penceresi için doğru; geri doldurmada
        # kaçırılan pencere, kimsenin fark etmediği bir boşluk demek.
        result["windows_unread"] = unread
    return result


#: Su seviyesinin gerisine ne kadar bakılacağı. Örtüşme bedava
#: (`ON CONFLICT DO NOTHING`), boşluk değil.
KAP_TOPUP_MARGIN_DAYS = 3


def backfill_kap_corpus(client: httpx.Client) -> dict:
    """Panoya düşmüş ama derlemde METNİ olmayan bildirimlerin gövdesini çek.

    Bu iş, listeleme ile gövde arasındaki açığı kapatıyor ve o açık ölçüldü:
    panoda 28.984 KAP bildirimi varken derlemde 147 gövde vardı. Sohbete
    "THYAO'da son gelişmeler neler" diye sorulduğunda arşivde o şirketin 47
    bildirimi duruyor, derlemde sıfır -- yani pano dolu, asistan boş.

    Sebebi tasarımdı: gövde yalnızca YENİ gelen bildirimler için çekiliyor
    (`run_kap`), çünkü tur başına bütçe var. Geriye dönük arşivin gövdesini
    kimse çekmiyordu.

    Yeniden eskiye ilerliyor ve tur başına bütçeli: birkaç turda kapanıyor,
    tek bir tur saatlerce sürmüyor, ve yarıda kesilirse bitişik ve güncel
    bir derlem bırakıyor.
    """
    budget = config.kap_corpus_budget()
    if budget <= 0:
        return {"skipped": True}

    page_size = config.kap_corpus_page()
    missing: list[dict] = []
    offset = 0
    while len(missing) < budget:
        page = sinks.fetch_news_archive(client, "KAP", page_size, offset)
        if not page:
            break
        offset += len(page)
        urls = [row["url"] for row in page if row.get("url")]
        embedded = sinks.fetch_embedded_urls(client, urls)
        missing.extend(row for row in page if row.get("url") not in embedded)

    if not missing:
        log.info("kap corpus: every stored disclosure already has its text")
        return {"fetched": 0, "embedded": 0}

    documents = _with_bodies(missing[:budget], client)
    embedded = sinks.push_disclosures_to_rag(client, documents)
    log.info(
        "kap corpus backfill: %d disclosures without text, %d bodies embedded",
        len(missing), embedded,
    )
    return {"fetched": len(documents), "embedded": embedded}


def topup_kap(client: httpx.Client) -> dict:
    """Kapalı kalınan aralığı kapat.

    `topup_candles` ile aynı soru, aynı ayrım: geri doldurma "hiç yok"u,
    bu "var ama eski"yi cevaplıyor. Yoklama üç günlük bir pencereye
    bakıyor; on gün kapalı kalmış bir kurulumda o pencere yetmez.
    """
    coverage = sinks.fetch_news_coverage(client).get("KAP") or {}
    if not coverage.get("items") or not coverage.get("last"):
        # Hiçbir şey yoksa bu geri doldurmanın sorusu, bunun değil.
        return {"skipped": True}

    last = date.fromisoformat(coverage["last"])
    since = last - timedelta(days=KAP_TOPUP_MARGIN_DAYS)
    until = datetime.now(ISTANBUL).date()
    if since >= until:
        return {"fetched": 0}
    log.info("kap top-up: newest held is %s, catching up from %s", last, since)
    return run_kap(client, since=since, until=until)


def backfill_kap(client: httpx.Client) -> dict:
    """Altı aylık arşivi, yeniden başlatmalar boyunca doldur.

    Üç şey bunu makul kılıyor:

    * **Yeniden başlatılabilir.** Listeleme ucuz (pencere başına tek istek)
      ve `known-hashes` elde olanı gövde harcamadan eliyor, dolayısıyla
      yeniden başlayan bir süreç kaldığı yerden devam ediyor. Bu olmasaydı
      her açılış sıfırdan başlar ve arşiv hiç tamamlanmazdı.
    * **Yeniden en yeniden.** `fetch_all` pencereleri bugünden geriye
      yürüyor, yani yarıda kesilen bir tarama rastgele bir serpinti değil,
      BİTİŞİK ve GÜNCEL bir arşiv bırakıyor.
    * **Tur başına bütçeli.** Tek bir açılışın sınırlı bir dilim alması,
      "on beş saatlik bir iş başlat ve dua et"ten iyi.
    """
    until = datetime.now(ISTANBUL).date()
    since = until - timedelta(days=config.kap_backfill_days())
    return run_kap(client, since=since, until=until)


def _within_pdf_window(published_at) -> bool:
    """Ekleri yalnızca güncel bildirimler için oku.

    Bir bildirimin gövdesi tek istek; ekleri her biri bir istek daha.
    Altı aylık taramada hepsini açmak, süreyi katlayıp bunu eski
    eklere harcamak demek.
    """
    window = config.kap_pdf_window_days()
    if window <= 0:
        return False
    age = datetime.now(timezone.utc) - published_at
    return age <= timedelta(days=window)


def _as_datetime(value):
    """Arşiv ucu ISO metin döndürüyor, yoklama ise datetime taşıyor."""
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _with_bodies(items: list, client: httpx.Client) -> list:
    """Read each disclosure's body and prepend the issuers it names.

    The issuer line exists because `rag.documents.ticker` is a single column:
    a merger notice naming two companies can only be FILTERED by one of them,
    so naming both in the text is what keeps it findable for the other.
    """
    documents = []
    for item in items:
        # Bildirim numarası kalıcı bağlantının içinde. Bağlantısı olmayan bir
        # satırın numarası da yok, dolayısıyla gövdesi çekilemez.
        url = item.get("url") or ""
        if "/" not in url:
            continue
        index = url.rsplit("/", 1)[-1]
        detail = kap_archive.fetch_detail(index, client)
        if detail is None:
            continue
        text = kap_archive.body_text(detail)
        if not text:
            continue
        published = _as_datetime(item["published_at"])
        if _within_pdf_window(published):
            attachments = kap_archive.attachment_text(detail, client)
            if attachments:
                text = f"{text}\n\n{attachments}"
        symbols = item.get("related_symbols") or []
        header = f"İlgili şirketler: {', '.join(symbols)}" if symbols else ""
        documents.append({
            "title": item["title"],
            "url": item["url"],
            "published_at": published,
            "related_symbols": symbols,
            "text": f"{header}\n{item['title']}\n\n{text}".strip(),
        })
    return documents




def run_once(quotes: bool, candles: bool, news: bool, fundamentals: bool = False) -> dict:
    results = {}
    with httpx.Client() as client:
        # Each job is guarded separately: a dead RSS host must not cost us the
        # price cycle, and a provider outage must not cost us the news.
        if quotes:
            results["quotes"] = _guard("quotes", run_quotes, client, force=True)
        if candles:
            results["candles"] = _guard("candles", run_candles, client)
        if news:
            results["news"] = _guard("news", run_news, client)
        if fundamentals:
            results["fundamentals"] = _guard("fundamentals", run_fundamentals, client)
    return results


def _guard(name: str, job, *args, **kwargs) -> dict:
    try:
        return job(*args, **kwargs)
    except Exception as exc:
        log.error("%s cycle failed: %s", name, exc)
        return {"error": str(exc)}


def start_scheduler() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone=ISTANBUL)
    # Geri çekilme merdiveninin aralığı GERÇEKTEN değiştirebilmesi için.
    # Bunsuz merdiven yalnızca bir log satırıydı.
    global _scheduler
    _scheduler = scheduler

    # Sohbetin anlık fiyat sorabilmesi için. Arka planda, kendi iş parçacığında;
    # zamanlayıcı ana iş parçacığında bloklamaya devam ediyor.
    refresh_server.serve_in_background()

    def _job(name, fn):
        def wrapper():
            with httpx.Client() as client:
                _guard(name, fn, client)

        return wrapper

    # İki katman. Şerit küçük ve sık; hisseler kalabalık ve seyrek.
    scheduler.add_job(
        _job("quotes_band", lambda client: run_quotes(client, tier="band")),
        "interval",
        seconds=config.band_interval_seconds(),
        id="quotes_band",
        # An overrunning job must not queue up behind itself; the next tick
        # would fetch the same prices anyway.
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _job("quotes_bulk", lambda client: run_quotes(client, tier="bulk")),
        "interval",
        seconds=config.quote_interval_seconds(),
        id="quotes_bulk",
        max_instances=1,
        coalesce=True,
    )
    # Gün içi barlar, toplu turla aynı ritimde: "Gün" görünümü 15 dakikalık
    # noktalardan oluşuyor ve o noktaları üreten şey bu.
    scheduler.add_job(
        _job("candles_intraday", run_intraday_candles),
        "interval",
        seconds=config.quote_interval_seconds(),
        id="candles_intraday",
        max_instances=1,
        coalesce=True,
    )
    # Vadeli hesap faizi. Günde bir, gün dönümünden hemen sonra; uç nokta aynı
    # gün ikinci kez çağrıldığında hiçbir şey ödemiyor, dolayısıyla kaçan bir
    # çalıştırma ertesi gün telafi edilebiliyor.
    scheduler.add_job(
        _job("interest", run_interest),
        "cron",
        hour=0,
        minute=5,
        id="interest",
        max_instances=1,
    )
    scheduler.add_job(
        _job("news", run_news),
        "interval",
        minutes=config.news_interval_minutes(),
        id="news",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _job("global-news", run_global_news),
        "interval",
        minutes=config.gdelt_interval_minutes(),
        id="global-news",
        max_instances=1,
        coalesce=True,
    )
    # TEFAS günde bir: NAV günde bir yayımlanıyor ve daha sık yoklamanın
    # getirisi yok, maliyeti var. Kapalıysa iş çalışıyor ve hemen dönüyor.
    scheduler.add_job(
        _job("tefas", run_tefas),
        "cron",
        hour=20,
        minute=30,
        id="tefas",
        max_instances=1,
    )
    # Canlı KAP akışı `run_news`'in içinde: `kap_source` her haber turunda
    # listeyi çekiyor. Buraya ikinci bir aralıklı iş koymak, iki fetcher'ın
    # aynı pencere için birbirinden habersiz KAP'a gitmesi demekti --
    # `courtesy` istekleri aralar ama işi tekrarlamayı engelleyemez.
    # Aynı ikili, aynı gerekçe: `kap-topup` "elimizdeki en yeni bildirim
    # eski mi", `kap-backfill` "hiç arşiv var mı" sorusunu cevaplıyor.
    # `misfire_grace_time=None` zorunlu: run_date scheduler başlamadan
    # hesaplanıyor ve satır içi ısınma ~80 saniye sürüyor.
    scheduler.add_job(
        _job("kap-topup", topup_kap),
        "date",
        run_date=datetime.now(ISTANBUL),
        id="kap-topup",
        misfire_grace_time=None,
    )
    scheduler.add_job(
        _job("kap-backfill", backfill_kap),
        "date",
        run_date=datetime.now(ISTANBUL),
        id="kap-backfill",
        max_instances=1,
        misfire_grace_time=None,
    )
    # Listeleme ile gövde arasındaki açığı kapatıyor. Ayrı bir iş, çünkü
    # ayrı bir soruyu cevaplıyor: `kap-backfill` "bu bildirimi biliyor
    # muyuz", bu "metnini okuduk mu".
    scheduler.add_job(
        _job("kap-corpus", backfill_kap_corpus),
        "interval",
        minutes=config.kap_interval_minutes() * 3,
        id="kap-corpus",
        max_instances=1,
        coalesce=True,
    )
    # After the close, so the day's final bar is settled.
    scheduler.add_job(
        _job("candles", run_candles),
        "cron",
        hour=config.MARKET_CLOSE_HOUR + 1,
        minute=15,
        id="candles",
        max_instances=1,
    )
    # Ratios move on quarterly reports, not by the second.
    scheduler.add_job(
        _job("fundamentals", run_fundamentals),
        "cron",
        hour=config.MARKET_CLOSE_HOUR + 1,
        minute=45,
        id="fundamentals",
        max_instances=1,
    )

    log.info(
        "scheduler started: band every %ds, quotes every %ds (market hours), "
        "news every %dm, kap every %dm, candles daily at %d:15",
        config.band_interval_seconds(),
        config.quote_interval_seconds(),
        config.news_interval_minutes(),
        config.kap_interval_minutes(),
        config.MARKET_CLOSE_HOUR + 1,
    )

    # A cold start with an empty database would otherwise show an empty
    # dashboard until the first tick. Quotes and news are one batched request
    # each, so they run inline.
    with httpx.Client() as client:
        _guard("quotes", run_quotes, client, force=True)
        _guard("news", run_news, client)

    # The candle backfill is NOT inline. `fetch_candles` is per-symbol, so a
    # cold start is ~190 sequential provider calls: 93 symbols measured at 36
    # seconds, and that is a healthy provider. Giving it to the scheduler with
    # a run_date of now means the service is up and pricing while the history
    # fills in behind it.
    scheduler.add_job(
        _job("fundamentals-backfill", backfill_fundamentals),
        "date",
        run_date=datetime.now(ISTANBUL),
        id="fundamentals-backfill",
        misfire_grace_time=None,
    )
    scheduler.add_job(
        _job("intraday-backfill", backfill_intraday),
        "date",
        run_date=datetime.now(ISTANBUL),
        id="intraday-backfill",
        misfire_grace_time=None,
    )
    scheduler.add_job(
        _job("candle-topup", topup_candles),
        "date",
        run_date=datetime.now(ISTANBUL),
        id="candle-topup",
        misfire_grace_time=None,
    )
    scheduler.add_job(
        _job("candle-backfill", backfill_candles),
        "date",
        run_date=datetime.now(ISTANBUL),
        id="candle-backfill",
        # The run date is fixed here, but the scheduler does not start until
        # the inline warm start above finishes -- measured at ~80 seconds, and
        # longer if a news feed is slow. APScheduler's default grace is one
        # second, so without this the backfill would be dropped as a misfire
        # and a first boot would silently keep its empty charts.
        misfire_grace_time=None,
    )

    scheduler.start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MoneyFast data ingestor")
    parser.add_argument("--once", action="store_true", help="run each job once and exit")
    parser.add_argument("--quotes", action="store_true", help="quotes only")
    parser.add_argument("--candles", action="store_true", help="candles only")
    parser.add_argument("--news", action="store_true", help="news only")
    parser.add_argument("--fundamentals", action="store_true", help="fundamentals only")
    args = parser.parse_args(argv)

    selected = args.quotes or args.candles or args.news or args.fundamentals
    quotes = args.quotes or not selected
    candles = args.candles or not selected
    news = args.news or not selected
    fundamentals = args.fundamentals or not selected

    if args.once:
        results = run_once(quotes, candles, news, fundamentals)
        log.info("one-shot run complete: %s", results)
        return 0

    start_scheduler()
    return 0


if __name__ == "__main__":
    sys.exit(main())
