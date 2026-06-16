#!/usr/bin/env python3
"""
find_closest_yaml.py - Find the closest existing YAML config for a target version.

Scans ``ffmpeg/`` for version YAML files sharing the same major version
as the target, and returns the newest one.  Falls back to the global
newest if no same-major YAML exists.

Usage:
    python scripts/find_closest_yaml.py --version 6.5
"""

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_DIR = REPO_ROOT / "ffmpeg"


def version_key(v: str):
    return tuple(int(x) for x in v.split("."))


def is_valid_version(stem: str) -> bool:
    return bool(re.match(r"^\d+(\.\d+){1,2}$", stem))


def find_closest_yaml(version: str) -> str | None:
    parts = version.split(".")
    major = parts[0]
    prefix = f"{major}."

    candidates: list[str] = []
    for f in YAML_DIR.glob("*.yaml"):
        stem = f.stem
        if not is_valid_version(stem):
            continue
        if stem.startswith(prefix):
            candidates.append(stem)

    if candidates:
        candidates.sort(key=version_key, reverse=True)
        return candidates[0]

    # Fallback: global latest
    all_vers: list[str] = []
    for f in YAML_DIR.glob("*.yaml"):
        stem = f.stem
        if is_valid_version(stem):
            all_vers.append(stem)

    if all_vers:
        all_vers.sort(key=version_key, reverse=True)
        return all_vers[0]

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Find the closest existing YAML for a target version."
    )
    parser.add_argument("--version", required=True, help="Target version (e.g. 6.5)")
    args = parser.parse_args()

    result = find_closest_yaml(args.version)
    if result:
        print(result)
    else:
        print("ERROR: no YAML files found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
