"""SSE fan-out for live prices.

The properties that matter are the ones a naive implementation gets wrong:
one poller regardless of client count, a slow client that cannot grow a queue
without bound, and a database hiccup that does not take the stream down for
everyone.
"""

from __future__ import annotations

import asyncio

import pytest

from app.modules.market import stream


@pytest.fixture(autouse=True)
def clean_stream():
    stream.reset()
    yield
    stream.reset()


def frame(price=304.0):
    return {"as_of": "2026-08-20T11:00:00Z", "delay_minutes": 15,
            "is_delayed": True, "quotes": {"THYAO": {"price": price}}}


class TestFanOut:
    @pytest.mark.asyncio
    async def test_every_subscriber_receives_a_frame(self):
        first, second = await stream.subscribe(), await stream.subscribe()
        stream.publish(frame())
        assert first.get_nowait()["quotes"]["THYAO"]["price"] == 304.0
        assert second.get_nowait()["quotes"]["THYAO"]["price"] == 304.0

    @pytest.mark.asyncio
    async def test_one_poller_regardless_of_client_count(self):
        """Ten open dashboards must not become ten times the database load."""
        stream.configure(frame)
        await stream.subscribe()
        first_task = stream._poller
        for _ in range(5):
            await stream.subscribe()
        assert stream._poller is first_task

    @pytest.mark.asyncio
    async def test_the_poller_stops_when_the_last_client_leaves(self):
        """An idle deployment should not query in a loop forever."""
        stream.configure(frame)
        queue = await stream.subscribe()
        assert stream._poller is not None
        stream.unsubscribe(queue)
        assert stream._poller is None

    @pytest.mark.asyncio
    async def test_the_poller_survives_a_partial_audience(self):
        stream.configure(frame)
        first, second = await stream.subscribe(), await stream.subscribe()
        stream.unsubscribe(first)
        assert stream._poller is not None
        stream.unsubscribe(second)

    @pytest.mark.asyncio
    async def test_unsubscribing_twice_is_harmless(self):
        queue = await stream.subscribe()
        stream.unsubscribe(queue)
        stream.unsubscribe(queue)


class TestSlowClient:
    @pytest.mark.asyncio
    async def test_a_full_queue_drops_the_oldest_frame(self):
        """A throttled background tab must not grow a queue until the process
        runs out of memory. For prices the newest frame supersedes the old
        one, so dropping the stale one is strictly better than blocking."""
        queue = await stream.subscribe()
        for price in range(stream.QUEUE_SIZE + 3):
            stream.publish(frame(float(price)))

        assert queue.qsize() == stream.QUEUE_SIZE
        prices = []
        while not queue.empty():
            prices.append(queue.get_nowait()["quotes"]["THYAO"]["price"])
        # The most recent frame survived; the earliest were discarded.
        assert prices[-1] == float(stream.QUEUE_SIZE + 2)
        assert 0.0 not in prices

    @pytest.mark.asyncio
    async def test_a_slow_client_does_not_starve_a_fast_one(self):
        slow, fast = await stream.subscribe(), await stream.subscribe()
        for price in range(stream.QUEUE_SIZE + 2):
            stream.publish(frame(float(price)))
            # The fast client keeps up.
            fast.get_nowait()
        assert fast.empty()
        assert slow.qsize() == stream.QUEUE_SIZE


class TestLatestFrame:
    @pytest.mark.asyncio
    async def test_the_current_frame_is_available_immediately(self):
        """A page opening between two ticks should not be blank until the
        next one."""
        stream.publish(frame())
        assert stream.latest_frame()["quotes"]["THYAO"]["price"] == 304.0

    def test_no_frame_before_the_first_publish(self):
        assert stream.latest_frame() is None


class TestPolling:
    @pytest.mark.asyncio
    async def test_unchanged_data_is_not_republished(self, monkeypatch):
        """A closed market produces identical rows every tick. Sending them
        would be pure noise on the wire and in the UI."""
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        stream.configure(frame)
        queue = await stream.subscribe()
        await asyncio.sleep(0.06)
        assert queue.qsize() == 1, "the identical frame should be sent once"

    @pytest.mark.asyncio
    async def test_a_changed_frame_is_published(self, monkeypatch):
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        prices = iter([304.0, 305.0, 305.0])

        def reader():
            try:
                return frame(next(prices))
            except StopIteration:
                return frame(305.0)

        stream.configure(reader)
        queue = await stream.subscribe()
        await asyncio.sleep(0.06)
        assert queue.qsize() >= 2

    @pytest.mark.asyncio
    async def test_a_database_hiccup_does_not_kill_the_stream(self, monkeypatch):
        """The next tick retries; raising would end the stream for everyone."""
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("connection reset")
            return frame()

        stream.configure(flaky)
        queue = await stream.subscribe()
        await asyncio.sleep(0.08)
        assert len(calls) >= 3
        assert queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_a_reader_returning_nothing_is_tolerated(self, monkeypatch):
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        stream.configure(lambda: None)
        queue = await stream.subscribe()
        await asyncio.sleep(0.04)
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_no_reader_configured_is_tolerated(self, monkeypatch):
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        stream.configure(None)
        queue = await stream.subscribe()
        await asyncio.sleep(0.04)
        assert queue.empty()


class TestPublishToASlowSubscriber:
    @pytest.mark.asyncio
    async def test_publishing_with_no_subscribers_is_harmless(self):
        """The latest frame is still recorded, so a client connecting a
        moment later gets it immediately."""
        stream.publish(frame())
        assert stream.latest_frame() is not None

    @pytest.mark.asyncio
    async def test_a_queue_emptied_between_the_full_check_and_the_put(self):
        """Narrow race: the consumer drains the queue after full() returned
        True. The put must still succeed rather than raising."""
        queue = await stream.subscribe()
        for index in range(stream.QUEUE_SIZE):
            queue.put_nowait(frame(float(index)))
        while not queue.empty():
            queue.get_nowait()
        stream.publish(frame(999.0))
        assert queue.get_nowait()["quotes"]["THYAO"]["price"] == 999.0


class TestPollerExit:
    @pytest.mark.asyncio
    async def test_the_loop_ends_when_the_audience_leaves_mid_cycle(self, monkeypatch):
        """The poller checks its audience each iteration, so a client leaving
        between ticks ends the loop without needing a cancellation."""
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        stream.configure(frame)
        queue = await stream.subscribe()
        task = stream._poller

        # Drop the subscriber without cancelling, mimicking the loop losing
        # its audience between iterations.
        stream._subscribers.discard(queue)
        await asyncio.sleep(0.05)
        assert task.done()


class TestFrameSize:
    """Kare boyutu.

    Evren 190 enstrümandan 1010'a çıkınca her tam kare 88 KB oldu ve fiyat her
    değiştiğinde açık olan her sekmeye gidiyordu -- menülerde hissedilen
    takılmanın bir parçası buydu.
    """

    @pytest.mark.asyncio
    async def test_an_unchanged_market_sends_metadata_only(self, monkeypatch):
        """Hiçbir fiyat kıpırdamadığında da tarayıcının gösterdiği yaş
        ilerlemeli -- ama bunun için 1011 kotasyonu yeniden yollamak
        gerekmiyor."""
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        monkeypatch.setattr(stream, "FRESHNESS_REFRESH_SECONDS", 0.0)
        monkeypatch.setattr(stream, "FULL_RESYNC_SECONDS", 1_000.0)
        stream.configure(frame)

        queue = await stream.subscribe()
        await asyncio.sleep(0.05)

        first = queue.get_nowait()
        assert first["partial"] is False
        assert first["quotes"], "the first frame must carry the whole snapshot"

        later = queue.get_nowait()
        assert later["partial"] is True
        assert later["quotes"] == {}

    @pytest.mark.asyncio
    async def test_only_changed_quotes_are_sent(self, monkeypatch):
        monkeypatch.setattr(stream, "POLL_SECONDS", 0.01)
        monkeypatch.setattr(stream, "FULL_RESYNC_SECONDS", 1_000.0)
        prices = iter([300.0, 300.0, 311.0])

        def moving():
            payload = frame()
            payload["quotes"] = {
                "THYAO": {"price": next(prices, 311.0)},
                "ASELS": {"price": 90.0},
            }
            return payload

        stream.configure(moving)
        queue = await stream.subscribe()
        await asyncio.sleep(0.06)

        queue.get_nowait()  # ilk tam kare
        delta = queue.get_nowait()
        assert delta["partial"] is True
        # Kıpırdamayan sembol karede yok.
        assert set(delta["quotes"]) == {"THYAO"}

    def test_a_first_frame_is_never_a_delta(self):
        """Akışa ortadan katılan bir istemci yalnızca farkları alsaydı, hiç
        görmediği sembollerde boşluk kalırdı."""
        quotes = {"THYAO": {"price": 300.0}}
        assert stream._changed_quotes(quotes, None) == quotes

    def test_nothing_changed_is_an_empty_delta(self):
        quotes = {"THYAO": {"price": 300.0}}
        assert stream._changed_quotes(quotes, dict(quotes)) == {}
