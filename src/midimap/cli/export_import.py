"""``midimap export`` / ``midimap import`` — copy profiles between formats.

- ``export <profile.json> <profile.yaml>`` — load source and write
  destination in the target format. The destination extension decides
  the format. Useful for migrating JSON profiles to YAML or vice
  versa.

- ``import <profile.yaml> <profile.json>`` — same, but the args are
  reversed for symmetry with export/import mental models in other
  CLIs. Both forms are equivalent.

The M5 toolchain is intentionally simple; richer conversions (e.g.
partial overrides, merge two profiles into one) are follow-ups.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..logging_setup import configure as configure_logging
from ..profile import load_profile, save_profile


def _export(src: Path, dst: Path) -> int:
    profile = load_profile(str(src))
    save_profile(profile, dst)
    print(f"wrote {dst}")
    return 0


def run_export(args: argparse.Namespace) -> int:
    configure_logging(args.log_level)
    return _export(Path(args.source), Path(args.destination))


def run_import(args: argparse.Namespace) -> int:
    # Import is the same operation as export; the semantic
    # difference is just user intent.
    configure_logging(args.log_level)
    return _export(Path(args.source), Path(args.destination))


def add_export_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "export",
        help="Convert a profile to a different format",
    )
    p.add_argument("source", help="Source profile path")
    p.add_argument("destination", help="Destination profile path (extension decides format)")
    p.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root log level (default: WARNING)",
    )
    p.set_defaults(func=run_export)


def add_import_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "import",
        help="Import (read) a profile and write it to a new location/format",
    )
    p.add_argument("source", help="Source profile path")
    p.add_argument("destination", help="Destination profile path")
    p.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root log level (default: WARNING)",
    )
    p.set_defaults(func=run_import)
