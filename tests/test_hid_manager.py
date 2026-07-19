"""Tests for HIDDeviceManager using a fake hidapi module."""

from __future__ import annotations

import time

import pytest

from midimap.devices.hid_manager import HIDDeviceManager
from midimap.events import NormalizedEvent


class _FakeHidDevice:
    def __init__(self, reports: list[bytes], vid: int, pid: int) -> None:
        self._reports = list(reports)
        self.vid = vid
        self.pid = pid
        self.closed = False
        self._idx = 0

    def read(self, n: int, timeout_ms: int = 0):
        if self._idx >= len(self._reports):
            time.sleep(0.01)  # simulate blocking
            return []
        r = self._reports[self._idx]
        self._idx += 1
        # pad/truncate to n bytes
        return list(r)[:n] + [0] * max(0, n - len(r))

    def close(self) -> None:
        self.closed = True


class _FakeHid:
    def __init__(self, devices: list[dict]) -> None:
        self._devices = devices
        self._opened: list[_FakeHidDevice] = []

    def enumerate(self):
        return self._devices

    def Device(self, vid=None, pid=None, serial=None, path=None):
        for d in self._devices:
            if d.get("vendor_id") == vid and d.get("product_id") == pid:
                # If the descriptor specified reports, use them
                reports = d.get("__reports__", [])
                fake = _FakeHidDevice(reports, vid, pid)
                self._opened.append(fake)
                return fake
        raise OSError("device not found")


def _info(vid: int, pid: int, *, product: str = "Test", reports: list[bytes] | None = None) -> dict:
    d = {
        "vendor_id": vid,
        "product_id": pid,
        "serial_number": "abc",
        "manufacturer_string": "Acme",
        "product_string": product,
        "usage_page": 1,
        "usage": 6,
        "interface_number": -1,
        "path": b"\\\\?\\HID#test",
    }
    if reports is not None:
        d["__reports__"] = reports
    return d


def test_list_devices_returns_one_per_unique_serial():
    fake = _FakeHid([_info(0x046D, 0xB38F, product="POP_Icon_Keys")])
    mgr = HIDDeviceManager(hid_module=fake)
    devs = mgr.list_devices()
    assert len(devs) == 1
    d = devs[0]
    assert d["kind"] == "hid"
    assert d["vendor_id"] == 0x046D
    assert d["product_id"] == 0xB38F
    assert d["name"] == "POP_Icon_Keys"


def test_list_devices_falls_back_to_product_string_when_no_descriptor():
    fake = _FakeHid([_info(0x1234, 0x5678, product="Unknown")])
    mgr = HIDDeviceManager(hid_module=fake)
    devs = mgr.list_devices()
    assert devs[0]["name"] == "Unknown"
    assert devs[0]["descriptor"] is False


def test_connect_emits_normalized_events():
    # boot protocol: mod ctrl (bit0) + key 0x04 ('a')
    report = bytes([0b00000001, 0, 0x04, 0, 0, 0, 0, 0])
    fake = _FakeHid([_info(0x046D, 0xB38F, reports=[report])])
    # Provide a real descriptor so the normalizer uses boot protocol.
    from midimap.devices.descriptors import DeviceDescriptor
    desc = DeviceDescriptor(
        vendor_id=0x046D, product_id=0xB38F, name="POP_Icon_Keys", layout={"type": "boot"}
    )
    mgr = HIDDeviceManager(hid_module=fake, descriptor_paths=[])
    mgr._descriptors = {(0x046D, 0xB38F): desc}  # bypass load_all_descriptors
    received: list[NormalizedEvent] = []
    mgr.set_emit(received.append)
    devs = mgr.list_devices()
    mgr.connect(devs[0]["id"])
    # Wait for the read thread to deliver
    deadline = time.monotonic() + 2.0
    while not received and time.monotonic() < deadline:
        time.sleep(0.02)
    mgr.stop()
    assert any(e.control_id == "mod:ctrl" for e in received), received
    assert any(e.control_id == "key:4" for e in received), received
    assert all(e.device_id.startswith("hid:") for e in received)


def test_connect_raises_when_hidapi_missing():
    mgr = HIDDeviceManager(hid_module=None)
    # Even with hidapi unavailable, list_devices should return []
    assert mgr.list_devices() == []
    # connect must raise (not silently swallow)
    with pytest.raises(RuntimeError):
        mgr.connect("hid:0:0:0")


def test_disconnect_closes_handle_and_stops_thread():
    fake = _FakeHid([_info(0x1, 0x1, reports=[])])
    mgr = HIDDeviceManager(hid_module=fake)
    mgr.set_emit(lambda e: None)
    devs = mgr.list_devices()
    mgr.connect(devs[0]["id"])
    # Let the read thread start
    time.sleep(0.1)
    mgr.disconnect(devs[0]["id"])
    time.sleep(0.1)
    # The opened fake device should be closed
    assert fake._opened[0].closed


def test_stop_terminates_all_read_loops():
    fake = _FakeHid([_info(0x1, 0x1, reports=[])])
    mgr = HIDDeviceManager(hid_module=fake)
    mgr.set_emit(lambda e: None)
    devs = mgr.list_devices()
    mgr.connect(devs[0]["id"])
    mgr.start()
    mgr.stop()
    # No more threads, no raises
    assert mgr._threads == {}


def test_list_devices_handles_enumerate_exception():
    class _BrokenHid:
        def enumerate(self):
            raise RuntimeError("hidapi crashed")

    mgr = HIDDeviceManager(hid_module=_BrokenHid())
    assert mgr.list_devices() == []


def test_connect_then_stop_is_idempotent():
    fake = _FakeHid([_info(0x1, 0x1, reports=[])])
    mgr = HIDDeviceManager(hid_module=fake)
    mgr.set_emit(lambda e: None)
    devs = mgr.list_devices()
    mgr.connect(devs[0]["id"])
    mgr.stop()
    mgr.stop()  # second stop is a no-op
    assert fake._opened[0].closed
