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
from .sources import rss_source, yfinance_source

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

#: Index into config.BACKOFF_LADDER. Widened on a rate limit, reset on a
#: clean cycle.
_backoff_step = 0


def current_interval_seconds() -> int:
    """The quote interval, widened while we are being rate limited."""
    ladder = config.BACKOFF_LADDER
    multiplier = ladder[min(_backoff_step, len(ladder) - 1)]
    return config.quote_interval_seconds() * multiplier


def _note_rate_limit() -> None:
    global _backoff_step
    if _backoff_step < len(config.BACKOFF_LADDER) - 1:
        _backoff_step += 1
    log.warning(
        "rate limited; widening the quote interval to %ds", current_interval_seconds()
    )


def _note_success() -> None:
    global _backoff_step
    if _backoff_step:
        log.info("rate limit cleared; back to %ds", config.quote_interval_seconds())
    _backoff_step = 0


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
            _note_rate_limit()
            return {"rate_limited": True}
        raise

    # `yf.download` swallows per-symbol failures and still returns a frame, so
    # a stalled provider shows up as a SHORT batch rather than an exception.
    # Treating that as success is what let the cycle run 6x over budget
    # without the backoff ladder ever engaging.
    requested = sum(1 for p in products if p.get("data_symbol"))
    missing = requested - len(quotes)
    degraded = requested > 0 and missing > requested * MISSING_TOLERANCE

    result = sinks.push_market_data(client, quotes, []) or {}
    if degraded:
        log.warning("%d/%d symbols came back empty", missing, requested)
        _note_rate_limit()
    else:
        _note_success()
    elapsed = time.monotonic() - started
    log.info(
        "quote cycle [%s]: %d fetched, %s written, %.2fs",
        tier, len(quotes), result.get("quotes_written", 0), elapsed,
    )
    if elapsed > current_interval_seconds():
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
    backend_result = sinks.push_news_to_backend(client, items) or {}
    embedded = sinks.push_news_to_rag(client, items)
    log.info(
        "news cycle: %d fetched, %s stored, %d embedded",
        len(items), backend_result.get("news_written", 0), embedded,
    )
    return {"fetched": len(items), "embedded": embedded, **backend_result}


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
        "news every %dm, candles daily at %d:15",
        config.band_interval_seconds(),
        config.quote_interval_seconds(),
        config.news_interval_minutes(),
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
