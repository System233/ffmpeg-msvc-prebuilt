#!/usr/bin/env python3
"""
scan_updates.py - Detect new FFmpeg upstream releases.

Uses ``git ls-remote --tags`` to list all upstream tags, keeps the newest
tag per major version for non-LTS releases, keeps every patch for LTS
releases (odd.minor.1 or 4.4), and reports those not yet present in
local ``ffmpeg/`` YAML files.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple

from lts import is_lts


REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_DIR = REPO_ROOT / "ffmpeg"
MIN_MAJOR = 4
UPSTREAM = "https://github.com/FFmpeg/FFmpeg.git"


def parse_tag(ref: str) -> Tuple[int, int, int] | None:
    """Parse refs/tags/n8.1.1 into (8, 1, 1)."""
    tag = ref.removeprefix("refs/tags/").removesuffix("^{}")
    if not tag.startswith("n"):
        return None
    parts = tag[1:].split(".")
    if len(parts) < 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) >= 3 else 0)
    except ValueError:
        return None


def fetch_upstream_tags() -> List[Tuple[int, int, int]]:
    """Fetch upstream tags and select versions to build.

    LTS minors (odd.1 or 4.4): keep ALL patches.
    Non-LTS: keep only the newest overall per major.
    """
    result = subprocess.run(
        ["git", "ls-remote", "--tags", UPSTREAM],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git ls-remote failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Parse all tags first
    all_tags: List[Tuple[int, int, int]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        parsed = parse_tag(parts[1])
        if parsed and parsed[0] >= MIN_MAJOR:
            all_tags.append(parsed)

    # Group by major
    by_major: dict[int, List[Tuple[int, int, int]]] = {}
    for v in all_tags:
        by_major.setdefault(v[0], []).append(v)

    selected: set[Tuple[int, int, int]] = set()
    for major, versions in by_major.items():
        # Latest patch per LTS minor
        lts_best: dict[Tuple[int, int], Tuple[int, int, int]] = {}
        for v in versions:
            if is_lts(v[0], v[1]):
                key = (v[0], v[1])
                if key not in lts_best or v > lts_best[key]:
                    lts_best[key] = v
        selected.update(lts_best.values())

        # Overall latest for this major (covers non-LTS)
        selected.add(max(versions))

    return sorted(selected, reverse=True)


def scan_local_yamls() -> Set[Tuple[int, int, int]]:
    """Scan ffmpeg/ for version YAML files."""
    versions: Set[Tuple[int, int, int]] = set()
    if not YAML_DIR.is_dir():
        return versions
    yaml_re = re.compile(r"^(\d+(?:\.\d+){1,2})\.yaml$")
    for entry in YAML_DIR.iterdir():
        if not entry.is_file():
            continue
        m = yaml_re.match(entry.name)
        if m:
            parts = m.group(1).split(".")
            v = (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) >= 3 else 0)
            versions.add(v)
    return versions


def main() -> None:
    upstream = fetch_upstream_tags()
    local = scan_local_yamls()

    # Backup check: also scan ports/
    port_re = re.compile(r"^ffmpeg-(\d+)-(\d+)(?:-(\d+))?$")
    ports_dir = REPO_ROOT / "ports"
    if ports_dir.is_dir():
        for entry in ports_dir.iterdir():
            if not entry.is_dir():
                continue
            m = port_re.match(entry.name)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                c = int(m.group(3)) if m.lastindex >= 3 and m.group(3) is not None else 0
                local.add((a, b, c))

    new_versions = [v for v in upstream if v not in local]

    for v in new_versions:
        major, minor, patch = v
        ver = f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"
        print(ver)

    if not new_versions:
        return


if __name__ == "__main__":
    main()
