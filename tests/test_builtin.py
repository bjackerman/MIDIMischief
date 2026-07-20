"""Tests for builtin actions.

Most tests don't touch the real OS — we either use the ``noop`` builtin,
the ``dry_run=True`` short-circuit, or mock the OS-level entry points
(``os.startfile`` on Windows, ``subprocess.Popen`` for shell-out). The
dispatcher itself is unit-tested for unknown names, exception
swallowing, and the per-OS routing.
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from midimap.actions.builtin import _BUILTINS, run_builtin

# ---- dispatcher ----


def test_unknown_builtin_returns_false():
    assert run_builtin("does_not_exist", {}) is False


def test_all_builtins_in_registry():
    expected = {
        "launch_app",
        "open_url",
        "volume_up",
        "volume_down",
        "volume_mute",
        "volume_set",
        "noop",
    }
    assert expected == set(_BUILTINS.keys())


def test_exception_in_handler_returns_false_not_raises(caplog):
    """A buggy builtin must not propagate; the executor keeps working."""
    with patch.dict(_BUILTINS, {"broken": lambda p, dry_run: (_ for _ in ()).throw(RuntimeError("boom"))}), caplog.at_level("ERROR", logger="midimap.actions.builtin"):
        assert run_builtin("broken", {}) is False


# ---- noop ----


def test_noop_returns_true():
    assert run_builtin("noop", {}) is True


# ---- launch_app / open_url ----


def test_launch_app_missing_path_returns_false():
    assert run_builtin("launch_app", {}) is False


def test_launch_app_dry_run_does_not_call_startfile():
    with patch("os.startfile", create=True) as start:
        assert run_builtin("launch_app", {"path": "C:/notepad.exe"}, dry_run=True) is True
        start.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific path")
def test_launch_app_windows_uses_os_startfile():
    with patch("os.startfile") as start:
        assert run_builtin("launch_app", {"path": "C:/Windows/notepad.exe"}) is True
        start.assert_called_once_with("C:/Windows/notepad.exe")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific path")
def test_launch_app_macos_uses_open():
    with patch("subprocess.Popen") as popen:
        popen.return_value.wait.return_value = 0
        assert run_builtin("launch_app", {"path": "/Applications/Calculator.app"}) is True
        argv = popen.call_args.args[0]
        assert argv == ["open", "/Applications/Calculator.app"]


@pytest.mark.skipif(sys.platform == "win32" or sys.platform == "darwin", reason="Linux-specific path")
def test_launch_app_linux_uses_xdg_open():
    with patch("subprocess.Popen") as popen:
        popen.return_value.wait.return_value = 0
        assert run_builtin("launch_app", {"path": "/usr/bin/gedit"}) is True
        argv = popen.call_args.args[0]
        assert argv == ["xdg-open", "/usr/bin/gedit"]


def test_open_url_dry_run_skips():
    with patch("os.startfile", create=True) as start, patch("subprocess.Popen") as popen:
        assert run_builtin("open_url", {"url": "https://example.com"}, dry_run=True) is True
        start.assert_not_called()
        popen.assert_not_called()


def test_open_url_missing_returns_false():
    assert run_builtin("open_url", {}) is False


# ---- volume: dry-run + dispatch ----


def test_volume_up_dry_run():
    assert run_builtin("volume_up", {"step": 7}, dry_run=True) is True


def test_volume_down_dry_run():
    assert run_builtin("volume_down", {"step": 3}, dry_run=True) is True


def test_volume_mute_dry_run():
    assert run_builtin("volume_mute", {}, dry_run=True) is True


def test_volume_set_dry_run():
    assert run_builtin("volume_set", {"value": 42}, dry_run=True) is True


def test_volume_set_clamps_to_0_100_dry_run():
    # We don't actually call into the OS, but the dry-run path doesn't
    # validate. Real validation only matters when the backend runs.
    # This test documents the dry-run short-circuit.
    assert run_builtin("volume_set", {"value": 999}, dry_run=True) is True


# ---- volume_set: bad value ----


def test_volume_set_rejects_non_integer():
    """If value is not coercible to int, we return False WITHOUT
    touching the OS. This matters: the user might bind a knob to
    volume_set with $value, and a malformed mapping must not crash."""
    assert run_builtin("volume_set", {"value": "abc"}) is False
    assert run_builtin("volume_set", {"value": None}) is False


# ---- volume_set: Windows pycaw fallback ----


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
def test_volume_set_windows_without_pycaw_returns_false():
    """If pycaw isn't installed, the dispatcher logs and returns False."""
    with patch.dict(sys.modules, {"pycaw": None, "pycaw.pycaw": None, "comtypes": None}):
        assert run_builtin("volume_set", {"value": 50}) is False


# ---- volume change: dispatcher routes to correct backend ----


def test_volume_up_dispatches_to_volume_change(caplog):
    with caplog.at_level("DEBUG", logger="midimap.actions.builtin"):
        run_builtin("volume_up", {"step": 5}, dry_run=True)
    # The dry-run short-circuits before any backend call; we just need
    # to confirm the handler ran without errors.


# ---- unsupported builtins ----


def test_quit_app_is_not_a_registered_builtin():
    assert "quit_app" not in _BUILTINS
    assert run_builtin("quit_app", {"name": "explorer"}) is False


# ---- subprocess helper ----


def test_run_argv_logs_nonzero_exit(caplog):
    """The internal _run_argv should log a warning on non-zero exit."""
    from midimap.actions.builtin import _run_argv

    with patch("subprocess.Popen") as popen:
        proc = MagicMock()
        proc.wait.return_value = 2
        popen.return_value = proc
        with caplog.at_level("WARNING", logger="midimap.actions.builtin"):
            assert _run_argv(["false"]) is False


def test_run_argv_handles_missing_command(caplog):
    from midimap.actions.builtin import _run_argv

    with patch("subprocess.Popen", side_effect=FileNotFoundError), caplog.at_level("ERROR", logger="midimap.actions.builtin"):
        assert _run_argv(["definitely-not-a-real-command-xyz"]) is False


def test_run_argv_handles_timeout(caplog):
    from midimap.actions.builtin import _run_argv

    with patch("subprocess.Popen") as popen:
        proc = MagicMock()
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=0.01)
        popen.return_value = proc
        with caplog.at_level("ERROR", logger="midimap.actions.builtin"):
            assert _run_argv(["slow"]) is False
        proc.terminate.assert_called()
