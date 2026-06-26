#!/usr/bin/env python3
"""Scan FFmpeg MSVC prebuilt variants and output which ones need building.

Replaces the inline bash scan loop in ``.github/workflows/build-release.yml``
(lines 125-164).  The script produces a JSON object on stdout that can be
captured directly in a YAML workflow step::

    matrix=$(python scripts/ci/scan_variants.py --ver "$ver" --rev "$rev")

Output format::

    {
      "matrix": [
        {"triplet": "x64-windows", "license": "gpl", "linkage": "shared"},
        ...
      ],
      "triplets": ["arm-windows", "arm64-windows", "x86-windows", "x64-windows"]
    }

All status / progress messages are written to *stderr* so stdout remains
machine-parseable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ops.naming import build_data_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Return the repository root directory (two levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent


def _env_list(name: str, default: str) -> list[str]:
    """Read a space-separated environment variable and return it as a list."""
    return os.environ.get(name, default).split()


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def scan_variants(
    ver: str,
    rev: str,
    target_arch: str = "",
    target_license: str = "",
) -> dict:
    """Scan all triplet x license x linkage combinations.

    Returns a dict with keys ``matrix`` (variants that still need building)
    and ``triplets`` (the active triplet list).
    """
    repo_root = _repo_root()

    triplets = _env_list("TRIPLETS", "arm-windows arm64-windows x86-windows x64-windows")
    licenses = _env_list("LICENSES", "lgpl gpl")
    linkages = _env_list("LINKAGES", "shared static")

    # Ensure the data branch is available for checking existing variants.
    # This is best-effort — a missing branch simply means every variant
    # will be treated as unbuilt, which is the safe default.
    result = subprocess.run(
        ["git", "fetch", "origin", "data"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            "WARNING: git fetch origin/data failed; all variants will be "
            "treated as unbuilt",
            file=sys.stderr,
        )

    matrix: list[dict[str, str]] = []

    for triplet in triplets:
        if target_arch and triplet != target_arch:
            continue
        for license_ in licenses:
            if target_license and license_ != target_license:
                continue
            for linkage in linkages:
                variant_key = f"{triplet}-{linkage}-{license_}"

                # Determine the data branch path via the shared naming module
                path = build_data_path(
                    version=ver, revision=int(rev),
                    triplet=triplet, linkage=linkage, license=license_,
                )

                # Check whether this variant already exists on the data branch
                check = subprocess.run(
                    ["git", "show", f"origin/data:{path}"],
                    cwd=repo_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if check.returncode == 0:
                    print(f"SKIP: {variant_key} already built", file=sys.stderr)
                else:
                    print(f"NEED: {variant_key}", file=sys.stderr)
                    matrix.append(
                        {"triplet": triplet, "license": license_, "linkage": linkage}
                    )

    print(
        f"Build matrix: {len(matrix)} variant(s) to build",
        file=sys.stderr,
    )

    return {"matrix": matrix, "triplets": triplets}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan FFmpeg MSVC prebuilt variants and output which ones need building."
    )
    parser.add_argument(
        "--ver",
        required=True,
        help="Version string (e.g. '8.1.1' or ref like 'n8.0-1234-gabc')",
    )
    parser.add_argument(
        "--rev",
        required=True,
        help="Revision number",
    )
    parser.add_argument(
        "--target-arch",
        default="",
        help="Optional: filter to a single triplet (e.g. x64-windows)",
    )
    parser.add_argument(
        "--target-license",
        default="",
        help="Optional: filter to a single license (e.g. gpl)",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        default=False,
        help="Write matrix=<JSON> and triplets=<JSON> lines to $GITHUB_OUTPUT "
        "instead of printing JSON to stdout",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    output = scan_variants(
        ver=args.ver,
        rev=args.rev,
        target_arch=args.target_arch,
        target_license=args.target_license,
    )

    if args.github_output:
        gh_output = os.environ.get("GITHUB_OUTPUT")
        if not gh_output:
            print(
                "ERROR: GITHUB_OUTPUT environment variable is not set",
                file=sys.stderr,
            )
            sys.exit(1)
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"matrix={json.dumps(output['matrix'])}\n")
            f.write(f"triplets={json.dumps(output['triplets'])}\n")
    else:
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
