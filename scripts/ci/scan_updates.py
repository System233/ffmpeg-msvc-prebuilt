#!/usr/bin/env python3
"""
scan_updates.py - Detect new FFmpeg upstream releases.

Scans the local ``ports/`` directory for already-supported FFmpeg versions,
queries the FFmpeg GitHub repository for all version tags, and reports any
new upstream releases that do not yet have a corresponding port.

Usage
-----
    python scripts/ci/scan_updates.py
    python scripts/ci/scan_updates.py --check-vcpkg   # also compare against vcpkg registry
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
PORTS_DIR = REPO_ROOT / "ports"
YAML_DIR = REPO_ROOT / "ffmpeg"

# Regex for port directory names.  Matches both:
#   ffmpeg-7-0       (X.Y,  two digit groups)
#   ffmpeg-8-1-1     (X.Y.Z, three digit groups)
PORT_DIR_RE = re.compile(r"^ffmpeg-(\d+)-(\d+)(?:-(\d+))?$")

# Regex for YAML version files in ffmpeg/ (e.g. 8.1.yaml, 8.1.1.yaml)
YAML_FILE_RE = re.compile(r"^(\d+(?:\.\d+){1,2})\.yaml$")

# Regex for FFmpeg upstream tags (e.g. n8.1.1, n7.0.2)
TAG_RE = re.compile(r"^n(\d+)\.(\d+)\.(\d+)$")

# GitHub API endpoint
FFMPEG_API_TAGS = "https://api.github.com/repos/ffmpeg/ffmpeg/tags?per_page=50"

# Default proxy (used if HTTPS_PROXY env var is not set)
DEFAULT_PROXY = "http://127.0.0.1:5808"

# vcpkg registry path (only used with --check-vcpkg)
VCPKG_FFMPEG_JSON = Path(r"D:\Repos\vcpkg\versions\f-\ffmpeg.json")


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def normalize_version(ver: str) -> Tuple[int, int, int]:
    """Convert a version string to a (major, minor, patch) tuple.

    Supports ``X.Y`` and ``X.Y.Z`` formats.
    """
    parts = ver.split(".")
    major = int(parts[0])
    minor = int(parts[1])
    patch = int(parts[2]) if len(parts) >= 3 else 0
    return (major, minor, patch)


def format_version(triple: Tuple[int, int, int]) -> str:
    """Format a (major, minor, patch) triple back to a version string.

    Drops the trailing ``.0`` when patch is zero so that ``7.0`` is
    displayed instead of ``7.0.0``.
    """
    major, minor, patch = triple
    if patch == 0:
        return f"{major}.{minor}"
    return f"{major}.{minor}.{patch}"


# ---------------------------------------------------------------------------
# Proxy / URL opener
# ---------------------------------------------------------------------------

def build_opener() -> urllib.request.OpenerDirector:
    """Return a URL opener configured with an HTTPS proxy if available."""
    proxy_url = os.environ.get("HTTPS_PROXY") or DEFAULT_PROXY
    proxy_handler = urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url})
    return urllib.request.build_opener(proxy_handler)


# ---------------------------------------------------------------------------
# Fetch upstream tags
# ---------------------------------------------------------------------------

def fetch_upstream_tags() -> List[Tuple[int, int, int]]:
    """Fetch FFmpeg version tags from the GitHub API.

    Returns a sorted list of (major, minor, patch) tuples for tags that
    match the ``nX.Y.Z`` pattern, newest first.

    On network errors, prints a warning and returns an empty list.
    """
    opener = build_opener()
    try:
        with opener.open(FFMPEG_API_TAGS, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            json.JSONDecodeError) as exc:
        print(f"WARNING: Failed to fetch tags from {FFMPEG_API_TAGS}: {exc}",
              file=sys.stderr)
        return []

    versions: List[Tuple[int, int, int]] = []
    for item in data:
        tag_name = item.get("name", "")
        m = TAG_RE.match(tag_name)
        if m:
            versions.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))

    # Remove duplicates while preserving order
    seen: set[Tuple[int, int, int]] = set()
    unique: List[Tuple[int, int, int]] = []
    for v in versions:
        if v not in seen:
            seen.add(v)
            unique.append(v)

    unique.sort(reverse=True)
    return unique


# ---------------------------------------------------------------------------
# Scan local ports
# ---------------------------------------------------------------------------

def scan_local_ports() -> List[Tuple[int, int, int]]:
    """Scan the ``ports/`` directory for supported FFmpeg versions.

    Returns a sorted list of (major, minor, patch) tuples, newest first.
    """
    versions: set[Tuple[int, int, int]] = set()
    for entry in PORTS_DIR.iterdir():
        if not entry.is_dir():
            continue
        m = PORT_DIR_RE.match(entry.name)
        if m:
            major = int(m.group(1))
            minor = int(m.group(2))
            patch = int(m.group(3)) if m.lastindex >= 3 and m.group(3) is not None else 0
            versions.add((major, minor, patch))

    return sorted(versions, reverse=True)


# ---------------------------------------------------------------------------
# Scan local YAML files
# ---------------------------------------------------------------------------

def scan_local_yamls() -> List[Tuple[int, int, int]]:
    """Scan the ``ffmpeg/`` directory for version YAML files.

    Returns a sorted list of (major, minor, patch) tuples, newest first.
    """
    versions: set[Tuple[int, int, int]] = set()
    if not YAML_DIR.is_dir():
        return []
    for entry in YAML_DIR.iterdir():
        if not entry.is_file():
            continue
        m = YAML_FILE_RE.match(entry.name)
        if m:
            versions.add(normalize_version(m.group(1)))
    return sorted(versions, reverse=True)


# ---------------------------------------------------------------------------
# Vcpkg registry scan
# ---------------------------------------------------------------------------

def scan_vcpkg_registry() -> List[Tuple[int, int, int]]:
    """Parse vcpkg's ffmpeg.json registry for known versions.

    Returns a sorted list of (major, minor, patch) tuples, newest first.
    Returns an empty list if the file cannot be read.
    """
    if not VCPKG_FFMPEG_JSON.is_file():
        print(f"WARNING: vcpkg registry not found at {VCPKG_FFMPEG_JSON}",
              file=sys.stderr)
        return []

    try:
        with open(VCPKG_FFMPEG_JSON, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARNING: Failed to read vcpkg registry: {exc}",
              file=sys.stderr)
        return []

    versions: set[Tuple[int, int, int]] = set()
    for entry in data.get("versions", []):
        ver = entry.get("version") or entry.get("version-string")
        if ver is None:
            continue
        # Some entries may be version ranges; skip non-dotted forms
        if not re.match(r"^\d+(\.\d+){1,2}$", ver):
            continue
        versions.add(normalize_version(ver))

    return sorted(versions, reverse=True)


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def diff_versions(
    upstream: List[Tuple[int, int, int]],
    local: set[Tuple[int, int, int]],
) -> List[Tuple[int, int, int]]:
    """Return upstream versions that are not in the local set, newest first."""
    new_versions = [v for v in upstream if v not in local]
    return new_versions


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_version_list(versions: List[Tuple[int, int, int]]) -> str:
    """Format a list of version tuples as a comma-separated string."""
    return ", ".join(format_version(v) for v in versions)


def print_results(
    local: List[Tuple[int, int, int]],
    upstream: List[Tuple[int, int, int]],
    new_versions: List[Tuple[int, int, int]],
) -> None:
    """Print a formatted summary of supported and new versions."""
    print(f"Supported versions ({len(local)}):")
    print(f"  {format_version_list(local)}")
    print()

    if not new_versions:
        print("No new upstream releases. You are up to date!")
        return

    print(f"New upstream releases ({len(new_versions)}):")
    for v in new_versions:
        ver_str = format_version(v)
        print(f"  {ver_str} [NEW] -- needs port generation")
    print()

    print("To add new ports:")
    for v in new_versions:
        ver_str = format_version(v)
        print(f"  python scripts/generate.py --version {ver_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan for new FFmpeg upstream releases.",
    )
    parser.add_argument(
        "--check-vcpkg",
        action="store_true",
        help="Also compare against known versions in the local vcpkg registry",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    # ---- Step 1: Scan local ports ----
    local = scan_local_ports()
    local_set = set(local)

    # ---- Step 2: Scan local YAML files ----
    yaml_versions = scan_local_yamls()
    local_set |= set(yaml_versions)

    # ---- Step 3 (optional): Scan vcpkg registry ----
    if args.check_vcpkg:
        vcpkg_versions = scan_vcpkg_registry()
        print(f"Vcpkg registry versions ({len(vcpkg_versions)}):")
        print(f"  {format_version_list(vcpkg_versions)}")
        print()
        # Merge vcpkg into the "already supported" set
        local_set |= set(vcpkg_versions)

    # ---- Step 4: Fetch upstream tags ----
    upstream = fetch_upstream_tags()
    if not upstream:
        # Warning already printed by fetch_upstream_tags
        sys.exit(1)

    print(f"Upstream releases ({len(upstream)}):")
    print(f"  {format_version_list(upstream)}")
    print()

    # ---- Step 5: Diff ----
    new_versions = diff_versions(upstream, local_set)

    # ---- Step 6: Output ----
    if args.json:
        output = {
            "supported_versions": [format_version(v) for v in sorted(local_set, reverse=True)],
            "upstream_versions": [format_version(v) for v in upstream],
            "new_versions": [format_version(v) for v in new_versions],
        }
        json.dump(output, sys.stdout, indent=2)
        print()  # trailing newline
    else:
        print_results(sorted(local_set, reverse=True), upstream, new_versions)


if __name__ == "__main__":
    main()
