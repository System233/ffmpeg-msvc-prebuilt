#!/usr/bin/env python3
"""Determine which FFmpeg versions to build in CI.

Supports two operating modes:

``push``
    Run ``ci_detect_changes.py`` to discover versions that changed
    between two commits.  Outputs a JSON array of ``{"version": …}``
    objects for each changed version, or an empty array.

``all``
    Run ``ffport.py list`` to enumerate every available version YAML.
    Outputs a JSON array of ``{"version": …}`` objects.

Usage::

    # Push event — only changed versions
    python scripts/ci/scan_versions.py --mode push --base HEAD~1 --head HEAD

    # Schedule / workflow_dispatch — everything
    python scripts/ci/scan_versions.py --mode all
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_push(base: str, head: str) -> list[dict[str, str]]:
    """Run ci_detect_changes.py and return version objects for changed files."""
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "ops" / "ci_detect_changes.py"),
            "--base", base,
            "--head", head,
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print(f"error: ci_detect_changes.py failed:\n{result.stderr}", file=sys.stderr)
        raise SystemExit(result.returncode)

    data = json.loads(result.stdout)
    if not data.get("found"):
        return []

    return [{"version": c["version"]} for c in data["changed"]]


def run_all() -> list[dict[str, str]]:
    """Run ffport.py list and return a version object for every line of output."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ffport.py"), "list"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print(f"error: ffport.py list failed:\n{result.stderr}", file=sys.stderr)
        raise SystemExit(result.returncode)

    versions: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            versions.append({"version": stripped})
    return versions


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Determine which FFmpeg versions to build in CI.",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("push", "all"),
        help="Operating mode: push (changed versions) or all (every version)",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Base commit SHA (required when --mode push)",
    )
    parser.add_argument(
        "--head",
        default=None,
        help="Head commit SHA (required when --mode push)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.mode == "push":
        if not args.base or not args.head:
            print("error: --base and --head are required when --mode push", file=sys.stderr)
            raise SystemExit(2)
        result = run_push(args.base, args.head)
    else:
        result = run_all()

    print(json.dumps(result))


if __name__ == "__main__":
    main()
