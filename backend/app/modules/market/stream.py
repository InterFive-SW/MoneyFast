"""Server-Sent Events fan-out for live prices.

One background task reads the quotes table and pushes each frame to every
subscriber. The alternative — a poller per connection — would make ten open
dashboards ten times the database load for identical data.

Design notes worth keeping:

* Subscribers get a **bounded** queue. A browser tab that stops reading (a
  laptop lid closing, a throttled background tab) must not grow a queue until
  the process runs out of memory. When the queue is full the oldest frame is
  dropped, because for prices the newest frame supersedes the old one anyway.
* The poller only starts when someone subscribes and stops when the last one
  leaves, so an idle deployment does not query in a loop forever.
* Frames are only emitted when something actually changed. A market that is
  closed produces identical rows every tick, and sending them would be pure
  noise on the wire and in the UI.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

log = logging.getLogger("moneyfast.market.stream")

#: How often the shared poller reads the quotes table. Deliberately faster than
#: the ingest cycle (INGESTOR_QUOTE_INTERVAL_SECONDS, 30s) so a new price
#: reaches subscribers within one tick of being written, at the cost of
#: re-reading unchanged rows in between. The comment previously claimed the
#: ingest ran every 10s; it did not even then.
POLL_SECONDS = 5.0

#: Comment frames keep intermediaries from closing an idle connection.
HEARTBEAT_SECONDS = 20.0

#: Frames buffered per subscriber before the oldest is dropped.
QUEUE_SIZE = 8

#: Republish at least this often, so the age the browser displays keeps
#: growing while the market is closed. Bu kare artık YALNIZCA tazelik bilgisini
#: taşıyor: 1011 kotasyonu yeniden yollamak, değişmemiş fiyatlar için dakikada
#: 88 KB demekti.
FRESHNESS_REFRESH_SECONDS = 60.0

#: Tam kare aralığı. Fark kareleri kaçan bir istemcinin sürüklenmemesi için
#: ara sıra her şey yeniden yollanıyor; dakikada bir değil, seyrek olarak.
FULL_RESYNC_SECONDS = 600.0

_subscribers: set[asyncio.Queue] = set()
_poller: Optional[asyncio.Task] = None
_latest: Optional[dict[str, Any]] = None

#: Injected by the app at startup so this module needs no database import and
#: stays testable without a session.
_reader = None


def configure(reader) -> None:
    """Install the callable that returns the current frame."""
    global _reader
    _reader = reader


def latest_frame() -> Optional[dict[str, Any]]:
    return _latest


async def subscribe() -> asyncio.Queue:
    global _poller
    queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
    _subscribers.add(queue)
    if _poller is None or _poller.done():
        _poller = asyncio.create_task(_poll_forever())
        log.info("market stream poller started")
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    global _poller
    _subscribers.discard(queue)
    if not _subscribers and _poller is not None:
        _poller.cancel()
        # Cleared here rather than left to the task's own `finally`, which
        # only runs on the next loop turn. Module state should be consistent
        # the moment the call returns.
        _poller = None
        log.info("market stream poller stopped, no subscribers")


def publish(frame: dict[str, Any]) -> None:
    """Push a frame to every subscriber, dropping the oldest when one is full."""
    global _latest
    _latest = frame
    for queue in list(_subscribers):
        if queue.full():
            # For prices the newest frame supersedes the old one, so dropping
            # the stale one is strictly better than blocking the poller.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover - see below
                # Unreachable under asyncio's single-threaded scheduling: no
                # consumer can drain the queue between full() and this line.
                # Kept, with its sibling below, so this stays correct if the
                # fan-out ever moves to a thread pool.
                pass
        try:
            queue.put_nowait(frame)
        except asyncio.QueueFull:  # pragma: no cover - guarded above
            pass


def _changed_quotes(
    quotes: dict, previous: Optional[dict]
) -> dict:
    """Yalnızca DEĞİŞEN kotasyonlar.

    Evren 190 enstrümandan 1010'a çıkınca her kare 88 KB oldu ve fiyat her
    değiştiğinde açık olan her sekmeye gidiyordu: o boyutta bir JSON'u
    ayrıştırmak ve React'e yaymak, menülerde hissedilen takılmanın bir
    parçasıydı.

    Fiyatların çoğu bir turdan diğerine kıpırdamıyor -- borsa kapalıyken
    hiçbiri kıpırdamıyor -- dolayısıyla kare, gerçekten değişenler kadar
    küçülüyor.
    """
    if previous is None:
        return quotes
    return {
        symbol: value
        for symbol, value in quotes.items()
        if previous.get(symbol) != value
    }


async def _poll_forever() -> None:
    global _poller
    current = asyncio.current_task()
    previous_quotes: Optional[dict] = None
    last_full = 0.0
    last_published = 0.0
    try:
        while _subscribers:
            try:
                frame = _reader() if _reader else None
                if frame:
                    quotes = frame.get("quotes", {}) or {}
                    now = asyncio.get_running_loop().time()
                    # Prices unchanged is the normal state outside session
                    # hours, and suppressing every frame then meant `as_of`
                    # and `delay_minutes` froze in the browser: the UI claimed
                    # "15 dk gecikmeli" all weekend while the data aged for
                    # days. A periodic frame refreshes the age even when no
                    # price moved.
                    delta = _changed_quotes(quotes, previous_quotes)
                    needs_resync = (now - last_full) >= FULL_RESYNC_SECONDS

                    if previous_quotes is None or needs_resync:
                        # Tam kare: bağlantının başında ve seyrek aralıklarla.
                        # Akışa ortadan katılan bir istemci yalnızca farkları
                        # alsaydı, hiç görmediği sembollerde boşluk kalırdı.
                        previous_quotes = quotes
                        last_full = now
                        last_published = now
                        publish({**frame, "quotes": quotes, "partial": False})
                    elif delta:
                        previous_quotes = quotes
                        last_published = now
                        publish({**frame, "quotes": delta, "partial": True})
                    elif (now - last_published) >= FRESHNESS_REFRESH_SECONDS:
                        # Hiçbir fiyat kıpırdamadı ama tarayıcının gösterdiği
                        # yaş ilerlemeli. Bunun için 1011 kotasyonu yeniden
                        # yollamak gerekmiyor -- kare yalnızca tazelik
                        # bilgisini taşıyor.
                        last_published = now
                        publish({**frame, "quotes": {}, "partial": True})
            except Exception as exc:
                # A database hiccup must not kill the stream for everyone; the
                # next tick retries.
                log.warning("market stream poll failed: %s", exc)
            await asyncio.sleep(POLL_SECONDS)
    except asyncio.CancelledError:
        pass
    finally:
        # Only clear if this task is still the current poller. A subscriber
        # arriving between cancel() and this line starts a replacement, and
        # blindly nulling here would orphan it — the stream would then look
        # alive while nothing was polling.
        if _poller is current:
            _poller = None


def reset() -> None:
    """Drop all state. For tests."""
    global _poller, _latest
    _subscribers.clear()
    if _poller is not None:
        _poller.cancel()
    _poller = None
    _latest = None
