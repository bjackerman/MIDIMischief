"""ProfileWatcher: watch a profile file for changes and reload it.

Wraps ``QFileSystemWatcher`` so the rest of the app can connect to a
``profile_reloaded`` signal. The watcher:

- debounces change events (a single editor save often fires 2+ events);
- reloads + validates via ``load_profile``;
- emits a :class:`ReloadResult` describing success or error;
- on error, keeps the previous profile in place (never blocks the
  mapping engine).

M5 ships a Qt-only watcher because the GUI is the only thing that
needs hot-reload. A non-Qt poller fallback is a one-file follow-up.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from .store import ProfileLoadError, load_profile

if TYPE_CHECKING:
    from .schema import Profile

log = logging.getLogger(__name__)

DEFAULT_DEBOUNCE_MS = 200


@dataclass
class ReloadResult:
    """The outcome of a reload attempt.

    ``profile`` is the new (or old, on error) profile; ``error`` is
    the error message on failure (None on success); ``path`` is the
    file watched.
    """

    profile: Profile | None
    error: str | None
    path: Path
    changed: bool  # True iff the on-disk profile differs from the cached one


class ProfileWatcher(QObject):
    """Watch a profile file and emit ``profile_reloaded`` on each change."""

    profile_reloaded = Signal(object)  # ReloadResult

    def __init__(
        self,
        path: Path,
        *,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        parent: QObject | None = None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent)
        self._path = Path(path).resolve()
        self._fwatcher = QFileSystemWatcher(self)
        if self._path.exists():
            self._fwatcher.addPath(str(self._path))
        self._fwatcher.fileChanged.connect(self._on_changed)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self._reload)
        self._current: Profile | None = None
        # Try to load once at start
        self._reload(initial=True)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def current(self) -> Profile | None:
        return self._current

    def force_reload(self) -> ReloadResult:
        """Trigger a synchronous reload right now (skip debounce)."""
        return self._reload(initial=False)

    def _on_changed(self, _path: str) -> None:
        # Some editors (vim, notepad) delete the file and recreate it,
        # which causes the watcher to drop the path. Re-add on every
        # event so we keep watching.
        if not self._fwatcher.files():
            self._fwatcher.addPath(str(self._path))
        self._debounce.start()

    def _reload(self, initial: bool = False) -> ReloadResult:  # type: ignore[no-untyped-def]
        if not self._path.exists():
            err = f"profile file no longer exists: {self._path}"
            log.warning(err)
            res = ReloadResult(profile=self._current, error=err, path=self._path, changed=False)
            self.profile_reloaded.emit(res)
            return res
        try:
            new = load_profile(self._path)
        except ProfileLoadError as e:
            err = f"profile load failed: {e}"
            log.warning(err)
            res = ReloadResult(profile=self._current, error=err, path=self._path, changed=False)
            self.profile_reloaded.emit(res)
            return res
        except Exception as e:  # pragma: no cover - safety net
            err = f"profile reload crashed: {e}"
            log.exception(err)
            res = ReloadResult(profile=self._current, error=err, path=self._path, changed=False)
            self.profile_reloaded.emit(res)
            return res

        # Was there an actual change?
        changed = initial or _profiles_differ(self._current, new)
        self._current = new
        res = ReloadResult(profile=new, error=None, path=self._path, changed=changed)
        if not initial or self._current is not None:
            self.profile_reloaded.emit(res)
        return res


def _profiles_differ(a: Profile | None, b: Profile | None) -> bool:
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return a.model_dump() != b.model_dump()


# Re-export for callers that don't want to import the class directly
__all__ = ["DEFAULT_DEBOUNCE_MS", "ProfileWatcher", "ReloadResult"]


def make_callback(
    on_reload: Callable[[ReloadResult], None],
) -> Callable[[ReloadResult], None]:
    """Wrap a plain callable so it can be connected to the Qt signal.

    Qt's ``connect`` only accepts callables that look like Qt slots
    (or plain callables in PySide6 6.5+). This helper is a no-op
    identity function for clarity at the call site.
    """
    return on_reload
