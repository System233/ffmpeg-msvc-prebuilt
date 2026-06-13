#!/usr/bin/env python3
"""
update_catalog.py - Update the repository catalog.json manifest.

Adds or updates a build entry for a given FFmpeg version. Designed to be
called from CI after a new release has been published.

The catalog lives at the repository root (``catalog.json``) and provides a
machine-readable index of all available pre-built FFmpeg binaries.

Usage
-----
    python scripts/update_catalog.py \\
        --version 8.1.1 \\
        --arch x64 \\
        --triplet x64-windows-mixed \\
        --license gpl \\
        --linkage shared \\
        --size 45200000 \\
        --digest sha256:abc123def456... \\
        --release-url "https://github.com/.../releases/tag/ffmpeg-8-1-1" \\
        --download-url "https://github.com/.../download/.../ffmpeg-8.1.1-x64-windows-mixed-shared-gpl.zip"

Invocation is idempotent: calling it multiple times with the same arguments
is safe and will overwrite any existing build entry for the same
(arch, linkage, license) combination.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "catalog.json"

# Default catalog template
EMPTY_CATALOG: Dict[str, Any] = {
    "updated": "",
    "versions": [],
}


# ---------------------------------------------------------------------------
# Catalog I/O
# ---------------------------------------------------------------------------

def read_catalog(path: Path) -> Dict[str, Any]:
    """Read an existing catalog JSON file, or return the empty template."""
    if not path.is_file():
        return dict(EMPTY_CATALOG)  # shallow copy

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: Failed to parse {path}: {exc}", file=sys.stderr)
        print("WARNING: Starting with an empty catalog.", file=sys.stderr)
        return dict(EMPTY_CATALOG)

    # Ensure top-level structure
    if "versions" not in data:
        data["versions"] = []
    if "updated" not in data:
        data["updated"] = ""
    return data


def write_catalog(path: Path, catalog: Dict[str, Any]) -> None:
    """Write the catalog JSON file with 2-space indentation."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(catalog, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Port name helper
# ---------------------------------------------------------------------------

def version_to_port_name(version: str) -> str:
    """Convert a dotted version string to a dashed port name.

    Examples::

        "8.1.1"  -> "ffmpeg-8-1-1"
        "8.1"    -> "ffmpeg-8-1"
        "7.0.2"  -> "ffmpeg-7-0-2"
        "7.0"    -> "ffmpeg-7-0"
    """
    parts = version.split(".")
    return "ffmpeg-" + "-".join(parts)


# ---------------------------------------------------------------------------
# Build-key helper (for deduplication)
# ---------------------------------------------------------------------------

def build_key(build: Dict[str, Any]) -> str:
    """Return a deduplication key for a build entry.

    Two builds are considered equivalent if they share the same
    ``arch``, ``linkage``, and ``license``.
    """
    return f"{build.get('arch','')}|{build.get('linkage','')}|{build.get('license','')}"


# ---------------------------------------------------------------------------
# Catalog update logic
# ---------------------------------------------------------------------------

def upsert_version(
    versions: List[Dict[str, Any]],
    version: str,
    port_name: str,
    release_date: str,
    release_url: str,
    new_build: Dict[str, Any],
) -> None:
    """Insert or update a version entry and its build in the versions list.

    * If the version already exists, its ``builds`` list is updated
      (existing build with same arch+linkage+license is overwritten).
    * If the version does not exist, a new entry is appended.
    """
    # Look for existing version entry
    for entry in versions:
        if entry.get("version") == version:
            # Version exists — update its builds list
            builds: List[Dict[str, Any]] = entry.setdefault("builds", [])
            new_key = build_key(new_build)
            replaced = False
            for i, b in enumerate(builds):
                if build_key(b) == new_key:
                    builds[i] = dict(new_build)
                    replaced = True
                    break
            if not replaced:
                builds.append(dict(new_build))

            # Update metadata fields (may have changed)
            if release_date:
                entry["release_date"] = release_date
            if release_url:
                entry["release_url"] = release_url
            return

    # Version does not exist — create new entry
    new_entry: Dict[str, Any] = {
        "version": version,
        "port_name": port_name,
        "release_date": release_date,
        "release_url": release_url,
        "builds": [dict(new_build)],
    }
    versions.append(new_entry)


def sort_versions(versions: List[Dict[str, Any]]) -> None:
    """Sort a list of version entries in descending version order.

    Sorting is done in-place by parsing each version string into a
    ``(major, minor, patch)`` tuple.
    """

    def _sort_key(entry: Dict[str, Any]) -> tuple:
        ver = entry.get("version", "0")
        parts = ver.split(".")
        major = int(parts[0]) if len(parts) >= 1 else 0
        minor = int(parts[1]) if len(parts) >= 2 else 0
        patch = int(parts[2]) if len(parts) >= 3 else 0
        # Negate for descending sort
        return (-major, -minor, -patch)

    versions.sort(key=_sort_key)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update the repository catalog.json manifest.",
    )
    parser.add_argument("--version", required=True, help="FFmpeg version, e.g. 8.1.1")
    parser.add_argument("--arch", required=True, help="Target architecture, e.g. x64")
    parser.add_argument("--triplet", required=True, help="Vcpkg triplet, e.g. x64-windows-mixed")
    parser.add_argument("--license", required=True, choices=["lgpl", "gpl", "nonfree"],
                        help="License variant")
    parser.add_argument("--linkage", required=True, choices=["shared", "static"],
                        help="Library linkage type")
    parser.add_argument("--size", type=int, required=True,
                        help="Size of the archive in bytes")
    parser.add_argument("--digest", default="",
                        help="GitHub asset digest (e.g. sha256:abc123..., default: empty)")
    parser.add_argument("--release-url", default="",
                        help="URL to the GitHub release tag page")
    parser.add_argument("--download-url", default="",
                        help="Direct download URL for the archive")
    parser.add_argument("--release-date", default="",
                        help="Release date (YYYY-MM-DD). Defaults to today if not provided.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    # ---- Step 1: Derive port name ----
    port_name = version_to_port_name(args.version)

    # ---- Step 2: Resolve release date ----
    release_date = args.release_date
    if not release_date:
        release_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ---- Step 3: Build the new build entry ----
    new_build: Dict[str, Any] = {
        "arch": args.arch,
        "triplet": args.triplet,
        "linkage": args.linkage,
        "license": args.license,
        "size": args.size,
        "download_url": args.download_url,
        "digest": args.digest,
    }

    # ---- Step 4: Read existing catalog ----
    catalog = read_catalog(CATALOG_PATH)

    # ---- Step 5: Upsert version ----
    upsert_version(
        versions=catalog["versions"],
        version=args.version,
        port_name=port_name,
        release_date=release_date,
        release_url=args.release_url,
        new_build=new_build,
    )

    # ---- Step 6: Update timestamp ----
    catalog["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- Step 7: Sort versions descending ----
    sort_versions(catalog["versions"])

    # ---- Step 8: Write back ----
    write_catalog(CATALOG_PATH, catalog)

    print(f"Updated {CATALOG_PATH}")
    print(f"  version:  {args.version}")
    print(f"  arch:     {args.arch}")
    print(f"  triplet:  {args.triplet}")
    print(f"  linkage:  {args.linkage}")
    print(f"  license:  {args.license}")
    print(f"  size:     {args.size}")
    print(f"  digest:   {args.digest[:48]}...")
    print(f"  versions: {len(catalog['versions'])} total")


if __name__ == "__main__":
    main()
