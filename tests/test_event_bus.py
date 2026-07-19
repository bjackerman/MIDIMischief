"""Tests for EventBus."""

from __future__ import annotations

import time

from midimap.event_bus import EventBus
from midimap.events import EventType, NormalizedEvent, Value


def _ev(control: str = "note:60", value: int = 100) -> NormalizedEvent:
    return NormalizedEvent(
        device_id="midi:test",
        control_id=control,
        event_type=EventType.PRESS,
        value=Value(value),
    )


def test_subscriber_receives_event():
    bus = EventBus()
    received: list[NormalizedEvent] = []
    bus.subscribe(lambda e: received.append(e), name="t1")
    bus.publish(_ev())
    # worker thread is daemon, give it a moment
    time.sleep(0.05)
    assert len(received) == 1
    assert received[0].control_id == "note:60"


def test_multiple_subscribers_each_get_event():
    bus = EventBus()
    a: list[NormalizedEvent] = []
    b: list[NormalizedEvent] = []
    bus.subscribe(lambda e: a.append(e), name="a")
    bus.subscribe(lambda e: b.append(e), name="b")
    for i in range(5):
        bus.publish(_ev(value=i))
    time.sleep(0.1)
    assert [e.value for e in a] == [0, 1, 2, 3, 4]
    assert [e.value for e in b] == [0, 1, 2, 3, 4]


def test_slow_subscriber_does_not_block_publisher():
    """A slow subscriber must not delay the publisher, and the bus must
    keep delivering events to a *different* (fast) subscriber. Drop-oldest
    is acceptable for the slow one; the test only asserts publishing is
    non-blocking and the fast subscriber is reached."""
    bus = EventBus()
    a_times: list[float] = []
    b_times: list[float] = []

    def slow(ev):
        time.sleep(0.05)
        a_times.append(time.monotonic())

    def fast(ev):
        b_times.append(time.monotonic())

    # Give the slow subscriber a tiny queue so drop-oldest kicks in.
    bus.subscribe(slow, name="slow", qsize=4)
    # Generous queue + small workload for the fast one.
    bus.subscribe(fast, name="fast", qsize=1024)

    # Publish 10 events spaced out so the slow one can keep up.
    t0 = time.monotonic()
    for i in range(10):
        bus.publish(_ev(value=i))
        # Yield briefly so the slow worker can drain
        time.sleep(0.06)
    publish_elapsed = time.monotonic() - t0
    # 10 x 0.06s ~= 0.6s baseline; allow generous slack
    assert publish_elapsed < 1.0, f"publish loop took {publish_elapsed:.3f}s — blocked?"

    time.sleep(0.5)  # let everything drain
    # The slow subscriber received *some* events (possibly with drops)
    assert len(a_times) > 0
    # The fast subscriber received all 10
    assert len(b_times) == 10
    # Fast subscriber is faster than slow by a wide margin
    if len(a_times) >= 2 and len(b_times) >= 2:
        fast_total = b_times[-1] - b_times[0]
        slow_total = a_times[-1] - a_times[0]
        assert fast_total <= slow_total + 0.1


def test_subscriber_exception_does_not_kill_bus():
    bus = EventBus()
    good: list[NormalizedEvent] = []

    def bad(_ev):
        raise RuntimeError("boom")

    bus.subscribe(bad, name="bad")
    bus.subscribe(lambda e: good.append(e), name="good")

    for i in range(3):
        bus.publish(_ev(value=i))
    time.sleep(0.1)
    assert len(good) == 3


def test_overflow_drops_oldest():
    bus = EventBus()
    received: list[NormalizedEvent] = []

    def slow(ev):
        time.sleep(0.01)
        received.append(ev)

    bus.subscribe(slow, name="slow", qsize=4)

    # publish 20 events fast; the slow worker won't keep up
    for i in range(20):
        bus.publish(_ev(value=i))

    time.sleep(1.0)  # let it drain
    # We should have dropped some but kept the latest qsize worth
    assert 0 < len(received) <= 20
    # Last value seen should be among the latest
    assert received[-1].value >= 16


def test_stop_unblocks_worker():
    bus = EventBus()
    received: list[NormalizedEvent] = []
    bus.subscribe(lambda e: received.append(e), name="t")
    bus.stop()
    # After stop, worker should exit; further publishes do nothing but don't raise
    bus.publish(_ev())
    time.sleep(0.05)
    # Either 0 or 1 received depending on whether the publish raced the stop
    assert len(received) <= 1
