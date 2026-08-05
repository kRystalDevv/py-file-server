#!/usr/bin/env python3
"""Bump the __version__ string in fileshare_app/__init__.py.

Prints the new version (bare, e.g. "1.3.1") to stdout and nothing else, so
callers can capture it directly: NEW_VERSION=$(python bump_version.py patch)
All human-readable diagnostics go to stderr.
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_VERSION_FILE = Path(__file__).resolve().parent.parent / "fileshare_app" / "__init__.py"

VERSION_LINE_RE = re.compile(
    r"^__version__[ \t]*=[ \t]*(?P<quote>['\"])(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?P=quote)[ \t]*$",
    re.MULTILINE,
)


def compute_next_version(current: str, bump: str) -> str:
    major, minor, patch = (int(part) for part in current.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump type: {bump!r}")


def bump_file(path: Path, bump: str, dry_run: bool) -> str:
    text = path.read_text(encoding="utf-8")
    matches = list(VERSION_LINE_RE.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one __version__ line in {path}, found {len(matches)}"
        )

    match = matches[0]
    current = f"{match.group('major')}.{match.group('minor')}.{match.group('patch')}"
    new_version = compute_next_version(current, bump)

    print(f"{current} -> {new_version}", file=sys.stderr)

    if not dry_run:
        quote = match.group("quote")
        new_line = f"__version__ = {quote}{new_version}{quote}"
        text = text[: match.start()] + new_line + text[match.end() :]
        path.write_text(text, encoding="utf-8")
        print(f"[written] {path}", file=sys.stderr)
    else:
        print(f"[dry-run] {path} not modified", file=sys.stderr)

    return new_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bump", choices=("patch", "minor", "major"))
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_VERSION_FILE,
        help="path to the file containing the __version__ line",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print the new version without writing it",
    )
    args = parser.parse_args(argv)

    if not args.path.is_file():
        print(f"error: version file not found: {args.path}", file=sys.stderr)
        return 1

    try:
        new_version = bump_file(args.path, args.bump, args.dry_run)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
