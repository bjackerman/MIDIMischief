"""Builtin actions — cross-platform launch + volume + media controls.

The :func:`run_builtin` dispatcher is the only public entry point. It
resolves a builtin name + params to a per-OS implementation. Each
backend is a tiny module-level function with a uniform signature
``(params: dict, dry_run: bool) -> bool``.

Cross-platform rules
--------------------
- ``launch_app`` / ``open_url``: ``os.startfile`` on Windows;
  ``subprocess.Popen(["open", ...])`` on macOS;
  ``subprocess.Popen(["xdg-open", ...])`` on Linux. Path is passed as
  a single argv element (no shell interpolation).
- ``volume_up`` / ``volume_down`` / ``volume_mute``: synthesise the
  Windows media keys via SendInput (Windows), shell out to ``osascript``
  (macOS), shell out to ``pactl`` (Linux PulseAudio, preferred) or
  ``amixer`` (Linux ALSA, fallback).
- ``volume_set``: requires ``pycaw`` on Windows (graceful no-op with a
  clear log if not installed). macOS: ``osascript``. Linux: ``pactl``
  or ``amixer``.
- ``quit_app`` is deliberately not a builtin. Terminating another
  application is inherently target-specific and needs an explicit,
  user-reviewed script action instead.

If a builtin is not supported on the current OS, we log and return
False. The user can either switch OS or use a ScriptAction as a
workaround.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shlex
import subprocess
import sys
from collections.abc import Callable
from ctypes import POINTER, c_ulong, cast, wintypes
from ctypes import wintypes as _wt  # re-export for type-checkers
from shutil import which

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def run_builtin(name: str, params: dict, *, dry_run: bool = False) -> bool:
    """Dispatch a builtin by name to a per-OS backend.

    Returns True if the backend reported success, False otherwise.
    """
    handler = _BUILTINS.get(name)
    if handler is None:
        log.error("unknown builtin: %r", name)
        return False
    try:
        return handler(params, dry_run=dry_run)
    except Exception:
        log.exception("builtin %r failed", name)
        return False


# ---------------------------------------------------------------------------
# Per-builtin handlers
# ---------------------------------------------------------------------------


def _launch_app(params: dict, *, dry_run: bool) -> bool:
    path = params.get("path") or params.get("uri")
    if not path:
        log.error("launch_app: missing 'path' or 'uri'")
        return False
    if dry_run:
        log.info("[DRY-RUN] launch_app: %s", path)
        return True
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
        return True
    if sys.platform == "darwin":
        return _run_argv(["open", path])
    return _run_argv(["xdg-open", path])


def _open_url(params: dict, *, dry_run: bool) -> bool:
    url = params.get("url")
    if not url:
        log.error("open_url: missing 'url'")
        return False
    if dry_run:
        log.info("[DRY-RUN] open_url: %s", url)
        return True
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
        return True
    if sys.platform == "darwin":
        return _run_argv(["open", url])
    return _run_argv(["xdg-open", url])


def _volume_up(params: dict, *, dry_run: bool) -> bool:
    if dry_run:
        log.info("[DRY-RUN] volume_up (step=%s)", params.get("step", 5))
        return True
    return _volume_change("up", step=int(params.get("step", 5)))


def _volume_down(params: dict, *, dry_run: bool) -> bool:
    if dry_run:
        log.info("[DRY-RUN] volume_down (step=%s)", params.get("step", 5))
        return True
    return _volume_change("down", step=int(params.get("step", 5)))


def _volume_mute(params: dict, *, dry_run: bool) -> bool:
    if dry_run:
        log.info("[DRY-RUN] volume_mute")
        return True
    return _volume_mute_toggle(toggle=bool(params.get("toggle", False)))


def _volume_set(params: dict, *, dry_run: bool) -> bool:
    """Set volume to a percentage. ``value`` is 0..100."""
    if dry_run:
        log.info("[DRY-RUN] volume_set: %s%%", params.get("value"))
        return True
    raw = params.get("value")
    try:
        pct = int(raw)
    except (TypeError, ValueError):
        log.error("volume_set: value must be an integer 0..100, got %r", raw)
        return False
    pct = max(0, min(100, pct))
    return _volume_set_pct(pct)


def _noop(params: dict, *, dry_run: bool) -> bool:
    """Useful for testing the pipeline without side effects."""
    log.debug("noop: %s", params)
    return True


_BUILTINS: dict[str, Callable[..., bool]] = {
    "launch_app": _launch_app,
    "open_url": _open_url,
    "volume_up": _volume_up,
    "volume_down": _volume_down,
    "volume_mute": _volume_mute,
    "volume_set": _volume_set,
    "noop": _noop,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_argv(argv: list[str], timeout: float = 5.0) -> bool:
    """Spawn argv with shell=False, log non-zero exits, return success bool."""
    try:
        proc = subprocess.Popen(argv, shell=False)
    except FileNotFoundError:
        log.error("command not found: %s", shlex.join(argv))
        return False
    except OSError as e:
        log.error("failed to spawn %s: %s", shlex.join(argv), e)
        return False
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        log.error("command timed out: %s", shlex.join(argv))
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        return False
    if rc != 0:
        log.warning("command exited %d: %s", rc, shlex.join(argv))
    return rc == 0


# ---------------------------------------------------------------------------
# Per-OS volume backends
# ---------------------------------------------------------------------------


def _volume_change(direction: str, *, step: int) -> bool:
    if sys.platform == "win32":
        vk = 0xAF if direction == "up" else 0xAE  # VK_VOLUME_UP / VK_VOLUME_DOWN
        return _win_send_media_key(vk)
    if sys.platform == "darwin":
        delta = step if direction == "up" else -step
        return _run_argv(
            [
                "osascript",
                "-e",
                f"set volume output volume (output volume of (get volume settings) + ({delta}))",
            ]
        )
    if which("pactl"):
        return _run_argv(
            [
                "pactl",
                "set-sink-volume",
                "@DEFAULT_SINK@",
                f"+{step}%" if direction == "up" else f"-{step}%",
            ]
        )
    if which("amixer"):
        return _run_argv(
            [
                "amixer",
                "-q",
                "-D",
                "pulse",
                "sset",
                "Master",
                f"{step}%+" if direction == "up" else f"{step}%-",
            ]
        )
    log.error("volume change: no backend available (install pactl or amixer)")
    return False


def _volume_mute_toggle(*, toggle: bool) -> bool:
    if sys.platform == "win32":
        # VK_VOLUME_MUTE = 0xAD
        return _win_send_media_key(0xAD)
    if sys.platform == "darwin":
        return _run_argv(
            [
                "osascript",
                "-e",
                "set volume output muted (not (output muted of (get volume settings)))",
            ]
        )
    if which("pactl"):
        return _run_argv(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
    if which("amixer"):
        return _run_argv(["amixer", "-q", "-D", "pulse", "sset", "Master", "toggle"])
    log.error("volume mute: no backend available")
    return False


def _volume_set_pct(pct: int) -> bool:
    if sys.platform == "win32":
        return _win_volume_set_pct(pct)
    if sys.platform == "darwin":
        return _run_argv(["osascript", "-e", f"set volume output volume {pct}"])
    if which("pactl"):
        return _run_argv(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"])
    if which("amixer"):
        return _run_argv(["amixer", "-q", "-D", "pulse", "sset", "Master", f"{pct}%"])
    log.error("volume set: no backend available")
    return False


# ---- Windows: media keys via SendInput, volume_set via pycaw ----


def _win_send_media_key(vk: int) -> bool:
    """Synthesise a single media key press via SendInput."""
    try:
        import ctypes

        PUL = POINTER(c_ulong)

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", PUL),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.DWORD),
                ("ki", KEYBDINPUT),
                ("padding", ctypes.c_byte * 8),
            ]

        SendInput = ctypes.windll.user32.SendInput
        SendInput.argtypes = [_wt.UINT, POINTER(INPUT), ctypes.c_int]
        SendInput.restype = _wt.UINT

        down = INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None))
        up = INPUT(
            type=1,
            ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=2, time=0, dwExtraInfo=None),  # KEYEVENTF_KEYUP=2
        )
        return bool(
            SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
            and SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        )
    except Exception:
        log.exception("SendInput media key failed")
        return False


def _win_volume_set_pct(pct: int) -> bool:
    """Set the master volume to ``pct`` (0..100) on Windows.

    Requires ``pycaw`` (which itself requires ``comtypes``). If either
    is not installed, we log a clear message and return False. Users
    on Windows can ``pip install pycaw comtypes`` to enable this.
    """
    try:
        from pycaw.pycaw import (  # type: ignore[import-not-found]
            AudioUtilities,
            IAudioEndpointVolume,
        )
    except ImportError:
        log.error(
            "volume_set on Windows requires pycaw + comtypes. "
            "Install with: pip install pycaw comtypes"
        )
        return False
    try:
        devices = AudioUtilities.GetAllSessions()
        # Find the default speaker endpoint and set its master volume.
        for session in devices:
            try:
                vol = cast(POINTER(IAudioEndpointVolume), session._ctl.QueryInterface(IAudioEndpointVolume))  # type: ignore[attr-defined]
                vol.SetMasterVolumeLevelScalar(pct / 100.0, None)
                return True
            except Exception:
                continue
        log.error("no audio endpoint available for volume_set")
        return False
    except Exception:
        log.exception("pycaw SetMasterVolumeLevelScalar failed")
        return False
