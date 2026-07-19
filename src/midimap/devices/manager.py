"""DeviceManager — owns MIDI input ports and pumps events to subscribers.

This is the M1 version: MIDI only. HID support arrives in M6.

Threading model
---------------
- ``mido.open_input(callback=...)`` runs the callback in rtmidi's internal
  thread. We keep the callback body trivial: decode → emit. The actual
  work happens on each subscriber's queue worker.
- ``start()`` launches a daemon hot-plug poller; in M1 it's a stub.
- ``stop()`` closes every open port and stops all subscriber workers
  (the bus is owned by the caller; we just unhook).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import mido

from ..events import NormalizedEvent
from .midi_normalizer import midi_to_normalized

log = logging.getLogger(__name__)

EventCallback = Callable[[NormalizedEvent], None]


class DeviceManager:
    """Owns MIDI (and later HID) input ports and pumps events to subscribers."""

    def __init__(self, poll_interval_s: float = 2.0) -> None:
        self._poll_interval_s = poll_interval_s
        self._callbacks: list[EventCallback] = []
        self._open_ports: dict[str, mido.ports.BasePort] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._hotplug_thread: threading.Thread | None = None

    # ---- subscription ----

    def subscribe(self, cb: EventCallback) -> None:
        """Register a callback invoked for every NormalizedEvent from any device."""
        self._callbacks.append(cb)

    def _emit(self, event: NormalizedEvent) -> None:
        # Snapshot under no lock — append-only after startup. Defensive copy is overkill.
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                log.exception("event callback raised (continuing)")

    # ---- lifecycle ----

    def start(self) -> None:
        if self._hotplug_thread is not None:
            return
        self._stop.clear()
        self._hotplug_thread = threading.Thread(
            target=self._hotplug_loop, name="midimap-hotplug", daemon=True
        )
        self._hotplug_thread.start()
        log.info("DeviceManager started (poll_interval=%.1fs)", self._poll_interval_s)

    def stop(self) -> None:
        log.info("DeviceManager stopping")
        self._stop.set()
        if self._hotplug_thread is not None:
            self._hotplug_thread.join(timeout=self._poll_interval_s + 1.0)
            self._hotplug_thread = None
        with self._lock:
            for name, port in self._open_ports.items():
                try:
                    port.close()
                except Exception:
                    log.warning("error closing port %s", name, exc_info=True)
            self._open_ports.clear()

    # ---- device control ----

    def list_devices(self) -> list[dict[str, Any]]:
        """Snapshot of currently available MIDI input devices."""
        out: list[dict[str, Any]] = []
        for name in mido.get_input_names():
            out.append(
                {
                    "id": _device_id(name),
                    "name": name,
                    "kind": "midi",
                }
            )
        return out

    def connect(self, device_id: str) -> None:
        with self._lock:
            if device_id in self._open_ports:
                log.debug("already connected to %s", device_id)
                return
            port_name = _port_name_from_id(device_id)
            # Per-port callback closure so the emitted NormalizedEvent
            # carries the right device_id (not a generic "midi:active").
            callback = self._make_callback(device_id)
            try:
                port = mido.open_input(port_name, callback=callback)
            except OSError as e:
                log.error("cannot open %s: %s", device_id, e)
                raise
            self._open_ports[device_id] = port
            log.info("connected %s", device_id)

    def disconnect(self, device_id: str) -> None:
        with self._lock:
            port = self._open_ports.pop(device_id, None)
        if port is not None:
            try:
                port.close()
            except Exception:
                log.warning("error closing %s", device_id, exc_info=True)
            log.info("disconnected %s", device_id)

    def is_connected(self, device_id: str) -> bool:
        with self._lock:
            return device_id in self._open_ports

    # ---- internals ----

    def _make_callback(self, device_id: str) -> Callable[[mido.Message], None]:
        """Return a closure that decodes + emits a message tagged with ``device_id``."""

        def _cb(message: mido.Message) -> None:
            # Hot-plug callbacks may fire after stop(); bail safely.
            if self._stop.is_set():
                return
            ev = midi_to_normalized(message, device_id=device_id)
            if ev is not None:
                self._emit(ev)

        return _cb

    def _hotplug_loop(self) -> None:
        """Re-scan on a timer. In M1 this just logs; M2 will auto-connect."""
        while not self._stop.is_set():
            self._stop.wait(self._poll_interval_s)
            if self._stop.is_set():
                break
            # No-op for M1; M2 will compare to last scan and auto-connect
            # devices that the active profile declares.


# ---- helpers ----

_PREFIX = "midi:"


def _device_id(port_name: str) -> str:
    return f"{_PREFIX}{port_name}"


def _port_name_from_id(device_id: str) -> str:
    if device_id.startswith(_PREFIX):
        return device_id[len(_PREFIX) :]
    return device_id


def filter_devices(
    devices: list[dict[str, Any]], *, name_contains: str | None = None
) -> list[dict[str, Any]]:
    """Helper for the CLI: filter the device list by case-insensitive substring."""
    if not name_contains:
        return list(devices)
    needle = name_contains.lower()
    return [d for d in devices if needle in d["name"].lower()]


__all__ = ["DeviceManager", "EventCallback", "filter_devices"]
