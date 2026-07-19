"""Headless wiring: DeviceManager -> EventBus -> MappingEngine -> ActionExecutor.

Lifecycle::

    app = App.start(profile)
    app.run_forever()        # blocks; signals tear it down
    app.stop()

Or use the higher-level :func:`run_profile` for a one-shot.
"""

from __future__ import annotations

import logging
import signal
import threading

from .actions import ActionExecutor
from .devices.manager import DeviceManager
from .event_bus import EventBus
from .events import NormalizedEvent
from .mapping.engine import MappingEngine
from .profile.schema import Profile

log = logging.getLogger(__name__)


class App:
    """The wired-together runtime."""

    def __init__(
        self,
        profile: Profile,
        *,
        dry_run: bool = False,
        auto_connect: bool = True,
        scripts_enabled: bool | None = None,
        confirm_risky: bool | None = None,
        confirm_callback=None,  # type: ignore[no-untyped-def]
    ) -> None:
        self.profile = profile
        self.dry_run = dry_run
        self.auto_connect = auto_connect
        # If the caller didn't pass these, use the profile's
        # global_settings (M3's typed accessors).
        if scripts_enabled is None:
            scripts_enabled = not profile.disable_scripts
        if confirm_risky is None:
            confirm_risky = profile.confirm_risky

        self.bus = EventBus()
        self.devices = DeviceManager()
        self.engine = MappingEngine(profile)
        self.executor = ActionExecutor(
            dry_run=dry_run,
            scripts_enabled=scripts_enabled,
            confirm_risky=confirm_risky,
            confirm_callback=confirm_callback,
        )
        self._stop = threading.Event()

        # bus.publish is called by DeviceManager on every NormalizedEvent
        # via subscribe(). The single subscriber below is the engine.
        self.devices.subscribe(self.bus.publish)
        self.bus.subscribe(self._dispatch, name="engine")

    def _dispatch(self, event: NormalizedEvent) -> None:
        action = self.engine.process(event)
        if action is not None:
            self.executor.execute(action)

    # ---- lifecycle ----

    def start(self) -> None:
        self.devices.start()
        if self.auto_connect:
            for d in self.devices.list_devices():
                if self.profile.matches_device(d):
                    try:
                        self.devices.connect(d["id"])
                    except Exception:
                        log.exception("failed to connect %s", d["id"])

    def stop(self) -> None:
        self._stop.set()
        self.devices.stop()
        self.executor.shutdown()
        self.bus.stop()

    def run_forever(self) -> None:
        """Block the calling thread until a SIGINT/SIGTERM is received."""
        self.start()
        try:
            if hasattr(signal, "pause"):
                # POSIX: signal.pause() wakes on signal handler.
                while not self._stop.is_set():
                    signal.pause()
            else:
                # Windows: spin-wait on the event so Ctrl-C / SIGINT works.
                while not self._stop.wait(timeout=0.5):
                    pass
        except KeyboardInterrupt:
            log.info("interrupted")
        finally:
            self.stop()

    def feed(self, event: NormalizedEvent) -> None:
        """Programmatically inject a NormalizedEvent. Useful for tests
        and the GUI's "test a single mapping" button."""
        self.bus.publish(event)

    def execute_action_now(self, action) -> None:  # type: ignore[no-untyped-def]
        """Run an action through the executor. Used by the GUI to test
        a single mapping without driving hardware."""
        self.executor.execute(action)


def run_profile(
    profile_path: str,
    *,
    dry_run: bool = False,
    auto_connect: bool = True,
    scripts_enabled: bool | None = None,
    confirm_risky: bool | None = None,
) -> int:
    """Convenience: load a profile, run the app until interrupted."""
    from .profile.store import load_profile

    profile = load_profile(profile_path)
    app = App(
        profile,
        dry_run=dry_run,
        auto_connect=auto_connect,
        scripts_enabled=scripts_enabled,
        confirm_risky=confirm_risky,
    )
    log.info("loaded profile %r with %d layers", profile.name, len(profile.layers))
    app.run_forever()
    return 0
