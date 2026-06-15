#!/usr/bin/env python3
"""
get_features_for_version.py — Extract features and dependencies for a given
FFmpeg version from the YAML chain.

Reuses functions from generate.py:
  - resolve_chain(version)       — builds YAML chain
  - merge_features(docs, version) — resolves enabled features
  - merge_dict_chain(docs, key)   — merges a key along the chain
  - collect_deps(features, dep_overrides, host_deps) — collects external deps

Usage:
  python scripts/get_features_for_version.py --version 8.1.1

Outputs compact JSON to stdout:
  {"version":"8.1.1","features":["avcodec",...],"dependencies":["x264",...]}
"""

import argparse
import json
import sys
from pathlib import Path

# Allow importing from scripts/ directory when called from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract features and dependencies for an FFmpeg version"
    )
    parser.add_argument(
        "--version", required=True,
        help="FFmpeg version (e.g. 8.1.1)",
    )
    args = parser.parse_args()

    # ---- Resolve YAML chain ----
    try:
        docs, _family = generate.resolve_chain(args.version)
    except SystemExit:
        # resolve_chain / load_yaml already printed details to stderr
        print(
            f"ERROR: could not resolve YAML chain for version '{args.version}'",
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- Merge features list ----
    feats = generate.merge_features(docs, args.version)
    features_dict = feats["features"]

    # ---- Merge dep_overrides (e.g. nvcodec -> ffnvcodec-12) ----
    dep_overrides = generate.merge_dict_chain(docs, "dep_overrides")

    # ---- Merge build config for host_deps ----
    build = generate.merge_dict_chain(docs, "build")
    host_deps = build.get("host_deps", [])

    # ---- Collect external package dependencies ----
    feature_deps, _feature_refs, host_deps = generate.collect_deps(
        features_dict, dep_overrides, host_deps,
    )

    # ---- Aggregate all external package names ----
    dependencies: set[str] = set()

    # Feature-level package dependencies
    for deps in feature_deps.values():
        for dep in deps:
            if isinstance(dep, str):
                dependencies.add(dep)
            elif isinstance(dep, dict) and "name" in dep:
                dependencies.add(dep["name"])

    # Host dependencies (e.g. ffmpeg-bin2c, vcpkg-cmake-get-vars)
    for dep in host_deps:
        if isinstance(dep, str):
            dependencies.add(dep)
        elif isinstance(dep, dict) and "name" in dep:
            dependencies.add(dep["name"])

    # ---- Build output ----
    output = {
        "version": args.version,
        "features": sorted(features_dict.keys()),
        "dependencies": sorted(dependencies),
    }

    # ---- Write compact JSON to stdout ----
    json.dump(output, sys.stdout, separators=(",", ":"), ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
