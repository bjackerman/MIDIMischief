"""``midimap run`` — load a profile and dispatch events to actions.

Examples
--------
::

    # normal mode
    python -m midimap run --profile sample_profile.json

    # dry-run (log actions but don't send keys / run scripts)
    python -m midimap run --profile sample_profile.json --dry-run

    # don't auto-connect to matching devices (manual connect later)
    python -m midimap run --profile sample_profile.json --no-auto-connect

    # hard-disable all script actions (defence-in-depth)
    python -m midimap run --profile sample_profile.json --no-scripts

    # disable the "risky" confirmation prompt (use with care!)
    python -m midimap run --profile sample_profile.json --no-confirm-risky
"""

from __future__ import annotations

import argparse

from ..app import run_profile
from ..logging_setup import configure as configure_logging
from ..profile.store import ProfileLoadError


def run(args: argparse.Namespace) -> int:
    configure_logging(args.log_level)
    try:
        return run_profile(
            args.profile,
            dry_run=args.dry_run,
            auto_connect=not args.no_auto_connect,
            scripts_enabled=not args.no_scripts,
            confirm_risky=not args.no_confirm_risky,
        )
    except ProfileLoadError as e:
        print(f"profile error: {e}", flush=True)
        return 2
    except FileNotFoundError as e:
        print(f"file not found: {e}", flush=True)
        return 2
    except KeyboardInterrupt:
        return 0


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "run",
        help="Load a profile and dispatch events to actions",
    )
    p.add_argument(
        "--profile",
        "-p",
        required=True,
        help="Path to a profile file (.json or .yaml)",
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
        "--no-scripts",
        action="store_true",
        help="Hard-disable all script actions (overrides profile)",
    )
    p.add_argument(
        "--no-confirm-risky",
        action="store_true",
        help="Skip the risky-script confirmation prompt (use with care)",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root log level (default: INFO)",
    )
    p.set_defaults(func=run)
