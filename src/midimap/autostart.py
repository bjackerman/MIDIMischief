"""Auto-start helper — start midimap when the user logs in.

Per-OS backends:

- **Windows**: write/delete a value in ``HKCU\\Software\\Microsoft\\
  Windows\\CurrentVersion\\Run`` (no admin needed; the user's
  Run key is enough for per-user auto-start).
- **macOS**: create/delete a ``~/Library/LaunchAgents/
  com.midimap.gui.plist`` file and ``launchctl load/unload`` it.
- **Linux**: create/delete a ``~/.config/autostart/
  midimap.desktop`` file. Most desktop environments honour the
  XDG autostart spec.

The M6 implementation is intentionally conservative: it writes a
single, minimal file/value and never invokes additional config
tools. The Settings tab's "Start with the OS" checkbox calls these
helpers and reflects the current state.
"""

from __future__ import annotations

import contextlib
import logging
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Return True if midimap is configured to start at login."""
    backend, _config = _backend()
    if backend is None:
        return False
    return backend.is_enabled()


def enable() -> bool:
    """Turn on auto-start. Returns True on success."""
    backend, _config = _backend()
    if backend is None:
        log.warning("auto-start: unsupported OS or no GUI")
        return False
    return backend.enable()


def disable() -> bool:
    """Turn off auto-start. Returns True on success."""
    backend, _config = _backend()
    if backend is None:
        return False
    return backend.disable()


# ---- Backends ----


class _Backend:
    is_enabled: Any  # callable
    enable: Any  # callable
    disable: Any  # callable


class _WindowsBackend:
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    VALUE_NAME = "midimap"

    def is_enabled(self) -> bool:
        try:
            import winreg
        except ImportError:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_PATH) as key:
                value, _ = winreg.QueryValueEx(key, self.VALUE_NAME)
                return bool(value)
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def enable(self) -> bool:
        try:
            import winreg
        except ImportError:
            return False
        cmd = _start_command()
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.REG_PATH) as key:
                winreg.SetValueEx(key, self.VALUE_NAME, 0, winreg.REG_SZ, cmd)
            return True
        except OSError as e:
            log.warning("auto-start enable failed: %s", e)
            return False

    def disable(self) -> bool:
        try:
            import winreg
        except ImportError:
            return False
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.REG_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, self.VALUE_NAME)
            return True
        except FileNotFoundError:
            return True  # already disabled
        except OSError as e:
            log.warning("auto-start disable failed: %s", e)
            return False


class _MacBackend:
    PLIST = "com.midimap.gui.plist"

    @property
    def _path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / self.PLIST

    def is_enabled(self) -> bool:
        return self._path.exists()

    def enable(self) -> bool:
        cmd = _start_command()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            f"  <key>Label</key><string>com.midimap.gui</string>\n"
            f"  <key>ProgramArguments</key>\n"
            f"  <array><string>{_plist_str(cmd.split()[0])}</string>"
            + "".join(f"<string>{_plist_str(a)}</string>" for a in cmd.split()[1:])
            + "</array>\n"
            "  <key>RunAtLoad</key><true/>\n"
            "</dict></plist>\n"
        )
        try:
            self._path.write_text(body, encoding="utf-8")
        except OSError as e:
            log.warning("auto-start enable failed: %s", e)
            return False
        return _run_launchctl(["load", str(self._path)])

    def disable(self) -> bool:
        if self._path.exists():
            _run_launchctl(["unload", str(self._path)])
            with contextlib.suppress(OSError):
                self._path.unlink()
        return True


class _LinuxBackend:
    DESKTOP = "midimap.desktop"

    @property
    def _path(self) -> Path:
        xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        return Path(xdg) / "autostart" / self.DESKTOP

    def is_enabled(self) -> bool:
        return self._path.exists()

    def enable(self) -> bool:
        cmd = _start_command()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=midimap\n"
            "Comment=Cross-platform MIDI/HID controller mapper\n"
            f"Exec={cmd}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        try:
            self._path.write_text(body, encoding="utf-8")
            return True
        except OSError as e:
            log.warning("auto-start enable failed: %s", e)
            return False

    def disable(self) -> bool:
        if self._path.exists():
            with contextlib.suppress(OSError):
                self._path.unlink()
        return True


def _start_command() -> str:
    """The command to launch midimap GUI on login.

    Uses the absolute path to the running Python executable and
    ``-m midimap gui`` so the auto-start doesn't depend on PATH
    being set up correctly.
    """
    py = Path(sys.executable)
    # In a real install this would be `midimap` (the entry-point
    # console script), but that's not always present. Fall back to
    # the Python -m form, which is always available.
    return f'"{py}" -m midimap gui'


def _plist_str(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _run_launchctl(args: list[str]) -> bool:
    if shutil.which("launchctl") is None:
        return True  # file is in place; load will happen on next login
    try:
        import subprocess

        subprocess.run(["launchctl", *args], check=True, capture_output=True)
    except Exception as e:  # pragma: no cover
        log.warning("launchctl failed: %s", e)
        return False
    return True


def _backend() -> tuple[Any, Any]:
    """Pick a backend for the current OS. Returns (backend, None)."""
    system = platform.system().lower()
    if system == "windows":
        return _WindowsBackend(), None
    if system == "darwin":
        return _MacBackend(), None
    if system == "linux":
        return _LinuxBackend(), None
    return None, None


__all__ = ["disable", "enable", "is_enabled"]
