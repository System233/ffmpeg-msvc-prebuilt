#!/usr/bin/env python3
"""Bump the ``revision:`` field in a ffmpeg YAML config file.

Usage::

    python scripts/ci/bump_revision.py --yaml ffmpeg/8.1.1.yaml

The script reads the current ``revision:`` value, increments it by 1, and
writes the updated file back in place.  It is designed to replace the inline
``sed`` logic previously embedded in `.github/workflows/auto-heal.yml`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

RE_REVISION = re.compile(r"^(revision:\s*)(\d+)", re.MULTILINE)


def bump(yaml_path: Path) -> tuple[int, int]:
    """Increment the revision field in *yaml_path*.

    Returns a ``(before, after)`` tuple of revision numbers.
    """
    content = yaml_path.read_text(encoding="utf-8")

    m = RE_REVISION.search(content)
    if m is None:
        print(
            f"error: No 'revision:' field found in {yaml_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    old_rev = int(m.group(2))
    new_rev = old_rev + 1

    new_content = RE_REVISION.sub(
        lambda match: f"{match.group(1)}{new_rev}", content, count=1
    )
    yaml_path.write_text(new_content, encoding="utf-8")
    return old_rev, new_rev


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bump the revision field in a ffmpeg YAML config file."
    )
    parser.add_argument(
        "--yaml",
        required=True,
        type=Path,
        help="Path to the YAML file (e.g. ffmpeg/8.1.1.yaml)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    yaml_path: Path = args.yaml

    if not yaml_path.exists():
        print(f"error: File not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    old_rev, new_rev = bump(yaml_path)
    print(f"Bumped revision in {yaml_path}: {old_rev} -> {new_rev}")


if __name__ == "__main__":
    main()
