"""MediaKeySender — synthesise OS media keys (play/pause, next, vol+...).

Per-OS backends
---------------
- **Windows**: ``ctypes`` + ``SendInput`` with ``VK_MEDIA_*`` virtual
  key codes. The media keys are intercepted by Windows itself and
  routed to the active media session.
- **macOS**: shell out to ``osascript`` with a small AppleScript that
  sends a media key via System Events. We deliberately avoid the
  private ``MediaRemote.framework`` because App Store / Gatekeeper
  don't like it.
- **Linux**: shell out to ``playerctl`` (preferred, supports MPRIS) or
  fall back to ``xdotool key XF86AudioPlay`` etc. on X11. On Wayland
  the X11 path won't work; we log a warning and return False. The
  user can fall back to a ScriptAction with ``playerctl`` directly.

Dry-run prints the would-be key without invoking the backend.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


# (display name, Windows VK, Linux XF86 keysym name)
_MEDIA_KEYS: dict[str, tuple[int | None, str | None]] = {
    # name          VK         XF86 keysym (lowercased, for xdotool)
    "play_pause":   (0xB3, "xf86audioplay"),   # VK_MEDIA_PLAY_PAUSE
    "next":         (0xB0, "xf86audionext"),   # VK_MEDIA_NEXT_TRACK
    "prev":         (0xB1, "xf86audioprev"),   # VK_MEDIA_PREV_TRACK
    "stop":         (0xB2, "xf86audiostop"),   # VK_MEDIA_STOP
    "volume_up":    (0xAF, "xf86audioRaiseVolume"),
    "volume_down":  (0xAE, "xf86audioLowerVolume"),
    "mute":         (0xAD, "xf86audiomute"),
}


class MediaKeySender:
    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._init_error: Exception | None = None
        self._setup()

    def _setup(self) -> None:
        # On Windows we need ctypes; on macOS/Linux we use subprocess.
        # We only fail-fast on Windows if ctypes itself is missing,
        # which would mean we're on a stripped Python (rare).
        if sys.platform == "win32":
            try:
                import ctypes  # noqa: F401
            except Exception as e:  # pragma: no cover — environment
                self._init_error = e

    # ---- public ----

    def send(self, name: str) -> bool:
        if name not in _MEDIA_KEYS:
            log.error("unknown media key: %r", name)
            return False
        if self._init_error is not None:
            log.error("media key backend unavailable: %s", self._init_error)
            return False
        if self.dry_run:
            log.info("[DRY-RUN] media key: %s", name)
            return True
        try:
            if sys.platform == "win32":
                return self._win_send(_MEDIA_KEYS[name][0])
            if sys.platform == "darwin":
                return self._macos_send(name)
            return self._linux_send(name, _MEDIA_KEYS[name][1])
        except Exception:
            log.exception("media key %r failed", name)
            return False

    def close(self) -> None:
        # No persistent resources to release.
        pass

    # ---- Windows ----

    def _win_send(self, vk: int | None) -> bool:
        if vk is None:
            return False
        try:
            import ctypes
            from ctypes import wintypes

            PUL = ctypes.POINTER(ctypes.c_ulong)

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
            SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
            SendInput.restype = wintypes.UINT

            down = INPUT(
                type=1, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
            )
            up = INPUT(
                type=1,
                ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=2, time=0, dwExtraInfo=None),  # KEYEVENTF_KEYUP=2
            )
            return bool(
                SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
                and SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
            )
        except Exception:
            log.exception("Windows SendInput media key failed")
            return False

    # ---- macOS ----

    def _macos_send(self, name: str) -> bool:
        # Map our key name to the AppleScript key code string. The
        # standard media key codes (NX_KEYTYPE_PLAY, etc.) are 16/19/etc.
        # We just use System Events' "key code" approach.
        code_map = {
            "play_pause": 16,    # NX_KEYTYPE_PLAY
            "next": 17,           # NX_KEYTYPE_NEXT
            "prev": 18,           # NX_KEYTYPE_PREVIOUS
            "stop": 20,           # NX_KEYTYPE_STOP (not always mapped)
            "volume_up": 72,      # kVK_VolumeUp
            "volume_down": 73,    # kVK_VolumeDown
            "mute": 74,           # kVK_Mute
        }
        code = code_map.get(name)
        if code is None:
            return False
        import subprocess

        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "System Events" to key code {code}',
                ],
                check=False,
                timeout=2.0,
                shell=False,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            log.error("osascript failed for media key %r: %s", name, e)
            return False

    # ---- Linux ----

    def _linux_send(self, name: str, keysym: str | None) -> bool:
        from shutil import which

        # Prefer playerctl (MPRIS) for transport controls.
        if name in {"play_pause", "next", "prev", "stop"}:
            cmd_map = {
                "play_pause": "play-pause",
                "next": "next",
                "prev": "previous",
                "stop": "stop",
            }
            if which("playerctl"):
                return _run([which("playerctl") or "playerctl", cmd_map[name]])
        # Fall back to xdotool for media keys via X11 keysyms.
        if keysym and which("xdotool"):
            return _run([which("xdotool") or "xdotool", "key", keysym])
        # Last resort: pactl + playerctl per key.
        if name in {"volume_up", "volume_down", "mute"} and which("pactl"):
            if name == "mute":
                return _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
            delta = "+5%" if name == "volume_up" else "-5%"
            return _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", delta])
        log.warning(
            "media key %r on Linux: no backend available (install playerctl, "
            "xdotool, or pactl). Wayland sessions need playerctl or a "
            "Portal-aware alternative.",
            name,
        )
        return False


def _run(argv: list[str], timeout: float = 2.0) -> bool:
    import subprocess

    try:
        proc = subprocess.Popen(argv, shell=False)
    except FileNotFoundError:
        log.error("command not found: %s", argv[0])
        return False
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        log.error("media key command timed out: %s", argv)
        return False
    if rc != 0:
        log.warning("media key command exited %d: %s", rc, argv)
    return rc == 0
