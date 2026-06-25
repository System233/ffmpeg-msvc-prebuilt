#!/usr/bin/env python3
"""Check that a commit range only modifies files within allowed scope.

Ported from the inline JS in ``.github/workflows/auto-heal.yml``.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Sequence

from _allowed import find_violations


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that changed files are within allowed scope."
    )
    parser.add_argument("--base", required=True, help="Base commit SHA")
    parser.add_argument("--head", required=True, help="Head commit SHA")
    parser.add_argument("--yaml", default=None, help="YAML config name to scope allowed files (e.g. 8.1.1)")
    return parser.parse_args(argv)


def _get_changed_files(base: str, head: str) -> list[str]:
    """Fetch the list of filenames changed between *base* and *head* via the
    GitHub Compare API."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo or "/" not in repo:
        print(
            "ERROR: GITHUB_REPOSITORY env var is not set or invalid",
            file=sys.stderr,
        )
        sys.exit(1)

    endpoint = f"/repos/{repo}/compare/{base}...{head}"
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        print(f"gh api failed with exit code {result.returncode}:", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)

    data = json.loads(result.stdout)
    return [f["filename"] for f in data.get("files", [])]


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    files = _get_changed_files(args.base, args.head)

    violations = find_violations(files, yaml=args.yaml)

    if violations:
        print("PR modifies files outside allowed scope:")
        for f in violations:
            print(f"  {f}")
        sys.exit(1)

    print("All changed files are within allowed scope.")


if __name__ == "__main__":
    main()
