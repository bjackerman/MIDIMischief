"""Lightweight in-process pub/sub.

- Subscribers each get a bounded ``queue.Queue`` and a worker thread that
  drains it, so a slow consumer never blocks the producer.
- Per-subscriber drop-oldest on overflow (configurable).
- Thread-safe ``publish`` from any thread.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

from .events import NormalizedEvent

log = logging.getLogger(__name__)

SubscriberCallback = Callable[[NormalizedEvent], None]


class _Subscription:
    __slots__ = ("_stop", "callback", "name", "queue", "worker")

    def __init__(self, name: str, callback: SubscriberCallback, qsize: int = 1024):
        self.name = name
        self.callback = callback
        self.queue: queue.Queue[NormalizedEvent] = queue.Queue(maxsize=qsize)
        self._stop = threading.Event()
        self.worker = threading.Thread(
            target=self._run, name=f"midimap-bus-{name}", daemon=True
        )

    def start(self) -> None:
        self.worker.start()

    def stop(self) -> None:
        self._stop.set()
        # unblock the worker
        with contextlib.suppress(queue.Full):  # pragma: no cover
            self.queue.put_nowait(_SENTINEL)  # type: ignore[arg-type]

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ev = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if ev is _SENTINEL:  # type: ignore[comparison-overlap]
                break
            try:
                self.callback(ev)
            except Exception:
                log.exception("subscriber %s raised", self.name)

    def submit(self, ev: NormalizedEvent) -> None:
        # Drop-oldest if the consumer can't keep up.
        if self.queue.full():
            try:
                self.queue.get_nowait()
                log.warning("subscriber %s queue full, dropping oldest", self.name)
            except queue.Empty:  # pragma: no cover
                pass
        try:
            self.queue.put_nowait(ev)
        except queue.Full:  # pragma: no cover
            log.error("subscriber %s still full after drop-oldest", self.name)


_SENTINEL: Any = object()


class EventBus:
    """Thread-safe pub/sub for NormalizedEvents."""

    def __init__(self) -> None:
        self._subs: list[_Subscription] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: SubscriberCallback, name: str = "sub", qsize: int = 1024) -> None:
        with self._lock:
            sub = _Subscription(name, callback, qsize=qsize)
            self._subs.append(sub)
            sub.start()

    def publish(self, event: NormalizedEvent) -> None:
        # No lock: each _Subscription has its own queue, and the list is
        # effectively immutable after startup. We snapshot under the lock
        # just to be safe.
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            sub.submit(event)

    def stop(self) -> None:
        with self._lock:
            subs = list(self._subs)
            self._subs.clear()
        for sub in subs:
            sub.stop()
