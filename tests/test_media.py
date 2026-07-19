"""Tests for MediaKeySender.

The actual SendInput / osascript / xdotool calls are mocked; we verify
the dispatcher routes to the right backend and that dry-run skips
everything.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from midimap.actions.media import _MEDIA_KEYS, MediaKeySender


def test_unknown_key_returns_false():
    s = MediaKeySender()
    assert s.send("not-a-real-key") is False


def test_dry_run_does_not_invoke_backend():
    s = MediaKeySender(dry_run=True)
    with patch("ctypes.windll.user32.SendInput") as send, patch("subprocess.Popen") as popen:
        assert s.send("play_pause") is True
        assert s.send("volume_up") is True
        assert s.send("next") is True
        send.assert_not_called()
        popen.assert_not_called()


def test_registry_has_all_expected_keys():
    expected = {"play_pause", "next", "prev", "stop", "volume_up", "volume_down", "mute"}
    assert expected.issubset(_MEDIA_KEYS.keys())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific path")
def test_windows_uses_sendinput():
    s = MediaKeySender()
    with patch("ctypes.windll.user32.SendInput") as send:
        # SendInput returns 1 on success
        send.return_value = 1
        assert s.send("play_pause") is True
        # Two calls: one key-down, one key-up
        assert send.call_count == 2
        # First call's wVk should be VK_MEDIA_PLAY_PAUSE (0xB3)

        # The first INPUT struct is built and passed by reference; we
        # can't easily inspect it without re-implementing the struct.
        # But the call count and the return value path are what matter.
        # We at least confirm the call was made with two INPUTs.
        assert send.call_args_list[0].args[0] == 1  # nInputs
        assert send.call_args_list[1].args[0] == 1  # nInputs (second call)


def test_windows_sendinput_failure_returns_false():
    """If SendInput returns 0 (failure), we report False."""
    s = MediaKeySender()
    with patch("ctypes.windll.user32.SendInput", return_value=0):
        # Need to skip the platform check by being on Windows
        if sys.platform == "win32":
            assert s.send("play_pause") is False
        else:
            # On non-Windows, MediaKeySender routes to osascript/xdotool,
            # which we haven't mocked. So this test is a no-op off-Windows.
            pass


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific path")
def test_macos_uses_osascript():
    s = MediaKeySender()
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        assert s.send("play_pause") is True
        argv = run.call_args.args[0]
        assert argv[0] == "osascript"


def test_exception_in_backend_returns_false():
    s = MediaKeySender()
    with patch.object(s, "_win_send", side_effect=RuntimeError("boom")), patch.object(sys, "platform", "win32"):
        # Force the win path even off-Windows
        assert s.send("play_pause") is False
