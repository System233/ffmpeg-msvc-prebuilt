#!/usr/bin/env python3
"""
find_closest_yaml.py - Find the closest existing YAML for a target version.

Scans ``ffmpeg/*.yaml`` (excluding ``base.yaml``) and returns the stem
(filename without extension) of the YAML that best matches the requested
version.  The algorithm is:

  1. If any YAMLs share the same major version as the target, return the
     one with the highest (minor, patch) version.
  2. Otherwise, return the globally highest (major, minor, patch) YAML.
  3. If no YAMLs exist at all, exit with code 1 and no output.

Usage
-----
    python scripts/find_closest_yaml.py --version 6.5
    python scripts/find_closest_yaml.py --version 7.1.2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_version(version: str) -> tuple[int, ...]:
    """Convert a dotted version string into a tuple of integers."""
    return tuple(int(x) for x in version.split("."))


def find_closest_yaml(version: str) -> str | None:
    """
    Find the closest existing YAML for *version*.

    Returns the stem (filename without extension) of the best-matching YAML,
    or ``None`` if no YAML files exist.
    """
    parts = version.split(".")
    major = parts[0]

    # List all non-base YAML files in ffmpeg/
    yaml_dir = Path("ffmpeg")
    yaml_files = [f.stem for f in yaml_dir.glob("*.yaml") if f.stem != "base"]

    if not yaml_files:
        return None

    # Try same major first
    same_major = [f for f in yaml_files if f.startswith(f"{major}.")]
    if same_major:
        # Sort by (minor, patch) descending, return highest
        same_major.sort(key=_parse_version, reverse=True)
        return same_major[0]

    # No same major — return global latest
    all_versions = sorted(yaml_files, key=_parse_version, reverse=True)
    return all_versions[0] if all_versions else None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find the closest existing YAML for a target version."
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Target version string (e.g. 6.5 or 7.1.2).",
    )
    args = parser.parse_args()

    result = find_closest_yaml(args.version)
    if result is None:
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
