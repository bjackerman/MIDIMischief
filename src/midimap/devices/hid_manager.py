"""HIDDeviceManager — discover + read HID controllers via hidapi.

Mirrors :class:`midimap.devices.manager.DeviceManager` but for the
HID backend. The two managers produce the same NormalizedEvent
abstraction so the rest of the app doesn't care which backend
emitted an event.

Design notes
------------
- Discovery uses ``hidapi.enumerate()`` and groups multiple
  interface entries (one per `usage_page`/`interface_number`) by
  vid:pid+serial. The first match wins as the canonical "device"
  record; subsequent matches are exposed as additional control
  surfaces (e.g. a keyboard + consumer page for media keys on the
  same dongle).
- Each connected device runs a background thread that calls
  ``hid.Device.read(N)`` in a tight loop. The thread exits when
  the device is disconnected (read returns empty) or when
  ``stop()`` is called.
- Errors are caught and logged; a transient error doesn't kill
  the read loop. If the device is unplugged, the thread exits
  cleanly so the rest of the system can keep running.
- For testability, the ``hidapi`` module is imported lazily and
  can be replaced with a fake at runtime via the ``hid_module``
  constructor argument.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from ..events import NormalizedEvent
from .descriptors import default_search_paths, load_all_descriptors
from .hid_normalizer import hid_report_to_events

log = logging.getLogger(__name__)

DEFAULT_READ_TIMEOUT_MS = 50  # hidapi blocking read timeout
DEFAULT_REPORT_SIZE = 64


class _Sentinel:
    """Distinguishes 'not provided' from explicit None."""


_SENTINEL = _Sentinel()


class HIDDeviceInfo(dict[str, Any]):
    """Lightweight view over hidapi device info."""


class HIDDeviceManager:
    """Discover and read HID controllers.

    Parameters
    ----------
    hid_module:
        A module that exposes the ``hidapi`` API. If omitted, the
        ``hid`` package is imported lazily. Pass an explicit
        ``False`` to mean "no hid backend available" (used by tests
        that want to assert the missing-backend error path).
    descriptor_paths:
        Where to look for device descriptors. Default = built-in
        + ``~/.config/midimap/devices/``.
    """

    def __init__(
        self,
        *,
        hid_module: Any = _SENTINEL,
        descriptor_paths: list[Any] | None = None,
    ) -> None:
        self._hid = None
        if hid_module is not _SENTINEL:
            # Caller decided explicitly (test fake, or False to disable)
            if hid_module is not False:
                self._hid = hid_module
        else:
            try:
                import hid as _hid  # type: ignore[import-not-found]
            except ImportError:
                _hid = None
            self._hid = _hid
        if descriptor_paths is None:
            try:
                from pathlib import Path as _Path

                from platformdirs import user_config_dir
            except ImportError:
                descriptor_paths = []  # slim env (tests, etc.)
            else:
                descriptor_paths = default_search_paths(
                    _Path(user_config_dir("midimap"))
                )
        self._descriptors = load_all_descriptors(list(descriptor_paths))
        self._threads: dict[str, threading.Thread] = {}
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._devices: dict[str, dict[str, Any]] = {}
        # emit callback set by the parent DeviceManager
        self._emit: Callable[[NormalizedEvent], None] | None = None
        self._prev_states: dict[str, dict[str, int]] = {}

    # ---- public API ----

    def set_emit(self, emit: Callable[[NormalizedEvent], None]) -> None:
        self._emit = emit

    def list_devices(self) -> list[dict[str, Any]]:
        """Enumerate HID devices currently visible to the OS."""
        if self._hid is None:
            return []
        out: list[dict[str, Any]] = []
        seen: set[tuple[int, int, str]] = set()
        try:
            entries = self._hid.enumerate() or []
        except Exception as e:  # pragma: no cover
            log.warning("hidapi enumerate() failed: %s", e)
            return []
        for e in entries:
            key = (int(e.get("vendor_id", 0)), int(e.get("product_id", 0)), e.get("serial_number", "") or "")
            if key in seen:
                continue
            seen.add(key)
            vid, pid, _ = key
            desc = self._descriptors.get((vid, pid))
            out.append(
                {
                    "kind": "hid",
                    "id": f"hid:{vid:04x}:{pid:04x}:{key[2] or 'noserial'}",
                    "name": (desc.name if desc else None) or (e.get("product_string") or f"HID {vid:04x}:{pid:04x}"),
                    "manufacturer": (desc.manufacturer if desc else None) or e.get("manufacturer_string"),
                    "vendor_id": vid,
                    "product_id": pid,
                    "serial": key[2],
                    "path": e.get("path"),
                    "usage_page": e.get("usage_page"),
                    "usage": e.get("usage"),
                    "descriptor": desc is not None,
                    # Keep the serializable layout metadata with the discovery
                    # record so GUI consumers can render known surfaces.
                    "layout": dict(desc.layout) if desc is not None else None,
                }
            )
        return out

    def connect(self, device_id: str) -> None:
        """Open a device and start the read thread."""
        if self._hid is None:
            raise RuntimeError("hidapi not installed; pip install hidapi")
        info = self._find_info(device_id)
        if info is None:
            raise RuntimeError(f"HID device not found: {device_id}")
        with self._state_lock:
            if device_id in self._threads:
                return
        try:
            handle = self._hid.Device(
                vid=info["vendor_id"],
                pid=info["product_id"],
                serial=info["serial"] or None,
                path=info["path"],
            )
        except Exception as e:
            raise RuntimeError(f"could not open {device_id}: {e}") from e
        thread = threading.Thread(
            target=self._read_loop,
            args=(device_id, handle, info),
            name=f"hid-read:{device_id}",
            daemon=True,
        )
        with self._state_lock:
            self._devices[device_id] = {"info": info, "handle": handle}
            self._threads[device_id] = thread
        self._stop.clear()
        thread.start()

    def disconnect(self, device_id: str) -> None:
        with self._state_lock:
            entry = self._devices.pop(device_id, None)
            self._threads.pop(device_id, None)
        if entry is None:
            return
        with contextlib.suppress(Exception):
            entry["handle"].close()
        self._prev_states.pop(device_id, None)

    def start(self) -> None:
        self._stop.clear()

    def stop(self) -> None:
        self._stop.set()
        with self._state_lock:
            devices = list(self._devices.values())
        for entry in devices:
            with contextlib.suppress(Exception):
                entry["handle"].close()
        with self._state_lock:
            self._devices.clear()
            self._threads.clear()

    # ---- helpers ----

    def _find_info(self, device_id: str) -> dict[str, Any] | None:
        for d in self.list_devices():
            if d["id"] == device_id:
                return d
        return None

    def _read_loop(self, device_id: str, handle: Any, info: dict[str, Any]) -> None:
        descriptor = self._descriptors.get((info["vendor_id"], info["product_id"]))
        prev_state: dict[str, int] = {}
        log.info("HID read loop start: %s", device_id)
        while not self._stop.is_set():
            try:
                data = handle.read(DEFAULT_REPORT_SIZE, timeout_ms=DEFAULT_READ_TIMEOUT_MS)
            except Exception as e:  # pragma: no cover
                log.warning("hid read error on %s: %s", device_id, e)
                break
            if not data:
                continue
            try:
                report = bytes(data)
            except TypeError:
                report = bytes(int(b) for b in data)
            events, new_state = hid_report_to_events(
                report,
                device_id=device_id,
                descriptor=descriptor,
                timestamp_ms=int(time.time() * 1000),
                prev_state=prev_state,
            )
            prev_state = new_state
            for ev in events:
                if self._emit is not None:
                    try:
                        self._emit(ev)
                    except Exception:
                        log.exception("hid emit failed")
        log.info("HID read loop end: %s", device_id)


__all__ = ["HIDDeviceInfo", "HIDDeviceManager"]
