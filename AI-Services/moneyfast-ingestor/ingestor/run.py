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
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from . import config, sinks
from .sources import rss_source, yfinance_source

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("moneyfast.ingestor")

ISTANBUL = ZoneInfo("Europe/Istanbul")


def market_is_open(moment: datetime | None = None) -> bool:
    """Borsa İstanbul continuous session, weekdays only.

    Polling a closed market just rewrites the same closing price every cycle,
    which costs the provider requests and buys nobody anything. Holidays are
    not modelled — the cost of polling on one is a handful of unchanged rows.
    """
    moment = (moment or datetime.now(timezone.utc)).astimezone(ISTANBUL)
    if moment.weekday() >= 5:
        return False
    return config.MARKET_OPEN_HOUR <= moment.hour < config.MARKET_CLOSE_HOUR


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


def run_quotes(client: httpx.Client, force: bool = False) -> dict:
    if not force and not market_is_open():
        log.info("market closed, skipping quote cycle")
        return {"skipped": True}

    started = time.monotonic()
    products = sinks.fetch_products(client)
    try:
        quotes = yfinance_source.fetch_quotes(products)
    except Exception as exc:
        # A 429 from the provider is a request to slow down, not a reason to
        # try harder.
        if "429" in str(exc) or "rate" in str(exc).lower():
            _note_rate_limit()
            return {"rate_limited": True}
        raise

    result = sinks.push_market_data(client, quotes, []) or {}
    _note_success()
    elapsed = time.monotonic() - started
    log.info(
        "quote cycle: %d fetched, %s written, %.2fs (budget %ds)",
        len(quotes), result.get("quotes_written", 0), elapsed, current_interval_seconds(),
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


def run_candles(client: httpx.Client) -> dict:
    products = sinks.fetch_products(client)
    candles = yfinance_source.fetch_candles(products, days=config.history_days())
    result = sinks.push_market_data(client, [], candles) or {}
    log.info(
        "candle cycle: %d bars offered, %s new", len(candles), result.get("candles_written", 0)
    )
    return {"fetched": len(candles), **result}


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

    def _job(name, fn):
        def wrapper():
            with httpx.Client() as client:
                _guard(name, fn, client)

        return wrapper

    scheduler.add_job(
        _job("quotes", run_quotes),
        "interval",
        seconds=config.quote_interval_seconds(),
        id="quotes",
        # An overrunning job must not queue up behind itself; the next tick
        # would fetch the same prices anyway.
        max_instances=1,
        coalesce=True,
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
        "scheduler started: quotes every %ds (market hours), news every %dm, candles daily at %d:15",
        config.quote_interval_seconds(),
        config.news_interval_minutes(),
        config.MARKET_CLOSE_HOUR + 1,
    )

    # A cold start with an empty database would otherwise show an empty
    # dashboard until the first tick.
    with httpx.Client() as client:
        _guard("quotes", run_quotes, client, force=True)
        _guard("news", run_news, client)

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
