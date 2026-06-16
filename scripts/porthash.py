#!/usr/bin/env python3
"""
Compute a composite SHA-256 hash for a port package and all its transitive
dependencies that exist in the local ``./ports/`` directory.

The hash covers every file inside each port directory (path + content) and
is intended for use as a cache key: any change to any file in the transitive
dependency tree yields a different hash.

Usage
-----
    python scripts/porthash.py ffmpeg-8-1-1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Set


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_ports_root() -> Path:
    cwd = Path.cwd()
    for candidate in [cwd, cwd.parent]:
        ports_dir = candidate / "ports"
        if ports_dir.is_dir():
            return ports_dir
    print("ERROR: Cannot find ports/ directory", file=sys.stderr)
    sys.exit(1)


def read_vcpkg_json(ports_dir: Path, package: str) -> dict:
    path = ports_dir / package / "vcpkg.json"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def extract_dep_names(deps: list) -> List[str]:
    names: List[str] = []
    for dep in deps:
        if isinstance(dep, str):
            names.append(dep)
        elif isinstance(dep, dict):
            name = dep.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def collect_all_dep_names(data: dict) -> Set[str]:
    names: Set[str] = set()
    names.update(extract_dep_names(data.get("dependencies", [])))
    for feature_data in data.get("features", {}).values():
        if isinstance(feature_data, dict):
            names.update(extract_dep_names(feature_data.get("dependencies", [])))
    return names


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------

def resolve_local_deps(
    ports_dir: Path,
    package: str,
    visited: Set[str] | None = None,
) -> Set[str]:
    if visited is None:
        visited = set()

    if package in visited:
        return visited
    visited.add(package)

    data = read_vcpkg_json(ports_dir, package)
    if not data:
        return visited

    for dep in collect_all_dep_names(data):
        if dep not in visited and (ports_dir / dep).is_dir():
            resolve_local_deps(ports_dir, dep, visited)

    return visited


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def hash_port_dir(ports_dir: Path, package: str) -> str:
    hasher = hashlib.sha256()
    pkg_dir = ports_dir / package
    if not pkg_dir.is_dir():
        return hasher.hexdigest()

    files = sorted(
        (p for p in pkg_dir.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(pkg_dir),
    )

    for fp in files:
        rel = fp.relative_to(pkg_dir)
        hasher.update(str(rel).encode("utf-8"))
        hasher.update(fp.read_bytes())

    return hasher.hexdigest()


def compute_composite_hash(ports_dir: Path, package: str) -> str:
    deps = resolve_local_deps(ports_dir, package)
    sorted_deps = sorted(deps)

    hashes = {d: hash_port_dir(ports_dir, d) for d in sorted_deps}

    combined = hashlib.sha256()
    for d in sorted_deps:
        combined.update(f"{d}:{hashes[d]}".encode("utf-8"))

    return combined.hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute composite hash for a port and its transitive local deps",
    )
    parser.add_argument("package", help="Package name, e.g. ffmpeg-8-1-1")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    ports_dir = find_ports_root()

    if not (ports_dir / args.package).is_dir():
        print(f"ERROR: Package '{args.package}' not found in {ports_dir}", file=sys.stderr)
        sys.exit(1)

    result = compute_composite_hash(ports_dir, args.package)
    print(result)


if __name__ == "__main__":
    main()
