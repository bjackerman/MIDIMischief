"""``midimap gui`` — launch the Qt main window.

Examples
--------
::

    # bare GUI (no profile loaded)
    python -m midimap gui

    # open a profile on launch
    python -m midimap gui --profile sample_profile.json
"""

from __future__ import annotations

import argparse

from ..app import App
from ..logging_setup import configure as configure_logging
from ..profile.store import ProfileLoadError, load_profile


def run(args: argparse.Namespace) -> int:
    configure_logging(args.log_level)
    # Lazy import so that ``midimap monitor`` and ``midimap run`` still
    # work without PySide6 installed.
    from ..gui.app import make_application
    from ..gui.main_window import MainWindow

    app = make_application([])

    runtime: App | None = None
    if args.profile:
        try:
            profile = load_profile(args.profile)
        except ProfileLoadError as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(None, "Profile error", str(e))
            return 2
        runtime = App(
            profile,
            dry_run=args.dry_run,
            auto_connect=not args.no_auto_connect,
        )
        runtime.start()
        win = MainWindow(app=runtime)
    else:
        win = MainWindow(app=None)

    win.show()
    rc = app.exec()
    if runtime is not None:
        runtime.stop()
    return int(rc)


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "gui",
        help="Launch the Qt main window",
    )
    p.add_argument(
        "--profile",
        "-p",
        default=None,
        help="Path to a profile file (.json or .yaml) to load on launch",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions but do not send keys or run scripts",
    )
    p.add_argument(
        "--no-auto-connect",
        action="store_true",
        help="Don't auto-connect devices matching the profile",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root log level (default: INFO)",
    )
    p.set_defaults(func=run)
