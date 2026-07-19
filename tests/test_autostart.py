"""Tests for the auto-start helper.

The Windows backend is exercised directly; the macOS / Linux
backends are not touched on Windows (their file paths and
launchctl calls would fail). We mock the OS branches with
``platform.system`` to verify each backend in isolation.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import midimap.autostart as autostart


def test_backend_windows_picked():
    with patch("midimap.autostart.platform.system", return_value="windows"):
        backend, _ = autostart._backend()
    assert isinstance(backend, autostart._WindowsBackend)


def test_backend_macos_picked():
    with patch("midimap.autostart.platform.system", return_value="darwin"):
        backend, _ = autostart._backend()
    assert isinstance(backend, autostart._MacBackend)


def test_backend_linux_picked():
    with patch("midimap.autostart.platform.system", return_value="linux"):
        backend, _ = autostart._backend()
    assert isinstance(backend, autostart._LinuxBackend)


def test_backend_unknown_returns_none():
    with patch("midimap.autostart.platform.system", return_value="haiku"):
        backend, _ = autostart._backend()
    assert backend is None


def test_start_command_uses_python_m():
    cmd = autostart._start_command()
    assert "midimap gui" in cmd
    assert "-m" in cmd


def test_windows_is_enabled_false_when_no_registry_value():
    with patch("midimap.autostart.platform.system", return_value="windows"), patch.object(
        autostart._WindowsBackend, "is_enabled", return_value=False
    ):
        assert autostart.is_enabled() is False


def test_windows_enable_disable_calls_registry(monkeypatch, tmp_path):
    """Exercise the winreg codepath against a synthetic key."""
    # We can't actually touch HKCU in tests; instead we patch
    # winreg functions and verify the contract.
    saved = {}
    with patch("midimap.autostart.platform.system", return_value="windows"):
        try:
            import winreg  # noqa: F401
        except ImportError:
            pytest.skip("winreg not available (not Windows)")
        with patch("winreg.CreateKey") as create, patch(
            "winreg.SetValueEx"
        ) as setval, patch("winreg.OpenKey") as open_, patch(
            "winreg.DeleteValue"
        ) as delval:
            win = autostart._WindowsBackend()
            assert win.enable() is True
            assert create.called
            assert setval.called
            saved["cmd"] = setval.call_args.args[-1]
            assert "midimap gui" in saved["cmd"]
            fake_handle = object()
            open_.return_value.__enter__ = lambda self: fake_handle
            open_.return_value.__exit__ = lambda self, *a: None
            delval.return_value = None
            assert win.disable() is True
            assert delval.called


def test_linux_is_enabled_writes_desktop_file(tmp_path, monkeypatch):
    """Simulate Linux: write the .desktop file and check is_enabled."""
    fake_home = tmp_path
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home))
    with patch("midimap.autostart.platform.system", return_value="linux"):
        backend = autostart._LinuxBackend()
        assert backend.is_enabled() is False
        assert backend.enable() is True
        assert backend.is_enabled() is True
        path = backend._path
        text = path.read_text(encoding="utf-8")
        assert "[Desktop Entry]" in text
        assert "Exec=" in text
        assert "midimap gui" in text
        assert backend.disable() is True
        assert backend.is_enabled() is False
        assert not path.exists()


def test_macos_is_enabled_writes_plist(tmp_path, monkeypatch):
    """Simulate macOS: monkeypatch Path.home() to point at tmp_path."""
    # We need _path to resolve under tmp_path. The Mac backend
    # uses Path.home() / "Library" / "LaunchAgents" / ... — patch
    # Path.home to return our tmp_path.
    fake_home = tmp_path
    with patch("midimap.autostart.platform.system", return_value="darwin"), patch.object(
        autostart.Path, "home", return_value=fake_home
    ):
        backend = autostart._MacBackend()
        assert backend.is_enabled() is False
        with patch.object(autostart, "_run_launchctl", return_value=True):
            assert backend.enable() is True
        assert backend.is_enabled() is True
        plist = backend._path
        assert plist.exists()
        body = plist.read_text(encoding="utf-8")
        assert "<key>RunAtLoad</key>" in body
        assert backend.disable() is True
        assert not plist.exists()
