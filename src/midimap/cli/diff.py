"""``midimap diff`` — print a structural diff between two profiles."""

from __future__ import annotations

import argparse

from ..logging_setup import configure as configure_logging
from ..profile import diff, diff_to_dict, load_profile


def run(args: argparse.Namespace) -> int:
    configure_logging(args.log_level)
    try:
        a = load_profile(args.profile_a)
        b = load_profile(args.profile_b)
    except Exception as e:
        print(f"FAIL: {e}", flush=True)
        return 1
    d = diff(a, b)
    print(d.summary())
    if args.json:
        import json

        print(json.dumps(diff_to_dict(d), indent=2))
    return 0 if not d.is_empty() or args.no_changes_ok else 1


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "diff",
        help="Show a structural diff between two profiles",
    )
    p.add_argument("profile_a", help="First profile (the 'before')")
    p.add_argument("profile_b", help="Second profile (the 'after')")
    p.add_argument(
        "--json",
        action="store_true",
        help="Also print the diff as a JSON object",
    )
    p.add_argument(
        "--no-changes-ok",
        action="store_true",
        help="Exit 0 even when the profiles are identical (default: exit 1)",
    )
    p.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Root log level (default: WARNING)",
    )
    p.set_defaults(func=run)
