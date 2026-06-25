#!/usr/bin/env python3
"""Delete GitHub Releases and git tags listed in a cleanup output file.

The cleanup output file is produced by ``scripts/ops/retention_policy.py`` and
contains lines prefixed with ``DELETE_RELEASE:`` and ``DELETE_TAG:`` followed by
the tag/release name.

For GitHub Releases the ``gh`` CLI is used; for git tags ``git push --delete``
is used.  Both commands operate in best-effort mode — errors (e.g. release
already deleted) are logged but do not cause the script to fail.

Extracted from ``.github/workflows/retention-cleanup.yml`` (ll. 69-98).

Usage::

    # Delete GitHub Releases listed in cleanup_output.txt
    python scripts/ci/cleanup_releases.py releases --file cleanup_output.txt

    # Delete git tags listed in cleanup_output.txt
    python scripts/ci/cleanup_releases.py tags --file cleanup_output.txt

    # Delete git tags with an explicit working directory for git
    python scripts/ci/cleanup_releases.py tags --file cleanup_output.txt \\
        --directory ./data
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


# ── Helpers ─────────────────────────────────────────────────────────────────


def _parse_lines(file_path: Path, prefix: str) -> list[str]:
    """Return tag names for every line in *file_path* starting with *prefix*."""
    tags: list[str] = []
    with open(file_path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.startswith(prefix):
                tag = stripped[len(prefix):]
                if tag:
                    tags.append(tag)
    return tags


def _run_releases(tags: list[str]) -> None:
    """Delete GitHub Releases via ``gh release delete {tag} --yes``.

    Best-effort: a missing release prints a warning and continues.
    """
    for tag in tags:
        print(f"Deleting release: {tag}")
        result = subprocess.run(
            ["gh", "release", "delete", tag, "--yes"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  (skipped — release may not exist)")
        else:
            if result.stdout:
                print(result.stdout.rstrip())


def _run_tags(tags: list[str], directory: Path | None) -> None:
    """Delete git tags via ``git push origin --delete {tag}``.

    Best-effort: a missing tag prints a warning and continues.
    """
    cwd = str(directory) if directory else None
    for tag in tags:
        print(f"Deleting tag: {tag}")
        result = subprocess.run(
            ["git", "push", "origin", "--delete", tag],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            print(f"  (skipped — tag may not exist)")
        else:
            if result.stdout:
                print(result.stdout.rstrip())


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete GitHub Releases and git tags from a cleanup output file.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- releases ---
    p_releases = sub.add_parser(
        "releases",
        help="Delete GitHub Releases listed in the cleanup file.",
    )
    p_releases.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to the cleanup output file (produced by retention_policy.py).",
    )

    # --- tags ---
    p_tags = sub.add_parser(
        "tags",
        help="Delete git tags listed in the cleanup file.",
    )
    p_tags.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Path to the cleanup output file (produced by retention_policy.py).",
    )
    p_tags.add_argument(
        "--directory",
        default=None,
        type=Path,
        help="Working directory for git operations (default: current directory).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.file.exists():
        print(f"No cleanup output found at {args.file} — nothing to delete.")
        return

    if args.command == "releases":
        tags = _parse_lines(args.file, "DELETE_RELEASE:")
        if not tags:
            print("No DELETE_RELEASE entries found — nothing to do.")
            return
        _run_releases(tags)

    elif args.command == "tags":
        tags = _parse_lines(args.file, "DELETE_TAG:")
        if not tags:
            print("No DELETE_TAG entries found — nothing to do.")
            return
        _run_tags(tags, args.directory)


if __name__ == "__main__":
    main()
