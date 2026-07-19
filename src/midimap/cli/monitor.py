"""``midimap monitor`` — listen for MIDI events and print them.

Examples
--------
::

    # list available MIDI devices and exit
    python -m midimap monitor --list

    # watch every device
    python -m midimap monitor

    # watch only devices whose name contains "Maschine"
    python -m midimap monitor --device "Maschine"
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading

from .. import __version__
from ..devices.manager import DeviceManager, filter_devices
from ..events import NormalizedEvent
from ..logging_setup import configure as configure_logging

# A simple "live monitor" view: clear the line per event so successive
# events overwrite each other. Cheap and useful.
_PRINT_LOCK = threading.Lock()
_STARTED = threading.Event()


def _print_event(ev: NormalizedEvent) -> None:
    with _PRINT_LOCK:
        chan = f" ch{ev.channel}" if ev.channel is not None else ""
        vel = f" vel={ev.velocity}" if ev.velocity is not None and ev.event_type.value == "press" else ""
        print(
            f"\r{ev.timestamp_ms:>10}  {ev.device_id:<32}  {ev.control_id:<10}  "
            f"{ev.event_type.value:<7}  val={ev.value:<5}{chan}{vel}    ",
            end="",
            flush=True,
        )


def run_monitor(args: argparse.Namespace) -> int:
    log = configure_logging("INFO")  # noqa: F841 — sets root logger
    manager = DeviceManager()

    devices = manager.list_devices()
    if args.list:
        print("Available MIDI inputs:")
        if not devices:
            print("  (none)")
        for d in devices:
            print(f"  - id={d['id']!s:<40}  name={d['name']}")
        return 0

    selected = filter_devices(devices, name_contains=args.device)
    if not selected:
        print(
            f"No MIDI devices match --device={args.device!r}. "
            f"Available: {[d['name'] for d in devices]}",
            file=sys.stderr,
        )
        return 1

    print(f"midimap v{__version__} — live monitor", file=sys.stderr)
    print(
        f"Watching {len(selected)} device(s). Press Ctrl-C to stop.",
        file=sys.stderr,
    )
    for d in selected:
        print(f"  • {d['name']}", file=sys.stderr)

    manager.subscribe(_print_event)
    manager.start()

    def _shutdown(_signo: int, _frame: object) -> None:
        print("\nshutting down…", file=sys.stderr)
        manager.stop()
        sys.exit(0)

    if sys.platform != "win32":
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    else:  # Windows: SIGINT handler works; SIGTERM is not delivered reliably
        signal.signal(signal.SIGINT, _shutdown)

    for d in selected:
        try:
            manager.connect(d["id"])
        except Exception as e:
            print(f"  ! failed to connect {d['name']}: {e}", file=sys.stderr)

    _STARTED.set()

    # Block the main thread. On Windows, signal handler fires; on Linux/macOS,
    # the signal handler exits via sys.exit so we never get past this point.
    if sys.platform == "win32":
        try:
            while True:
                signal.pause() if hasattr(signal, "pause") else threading.Event().wait(3600)
        except KeyboardInterrupt:
            _shutdown(0, None)
    else:
        try:
            threading.Event().wait()  # wait forever
        except KeyboardInterrupt:
            _shutdown(0, None)

    return 0


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "monitor",
        help="Live-monitor MIDI events from one or more devices",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List available MIDI input devices and exit",
    )
    p.add_argument(
        "--device",
        default=None,
        help="Substring filter on device name (case-insensitive). Omit for all.",
    )
    p.set_defaults(func=run_monitor)
