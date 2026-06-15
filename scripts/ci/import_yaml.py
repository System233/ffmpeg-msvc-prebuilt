#!/usr/bin/env python3
"""
import_yaml.py — Merge variant .var.yaml artifacts into data branch YAML.

Reads all ``.var.yaml`` files from a given artifacts directory, groups them
by ``version + revision`` (or by ``ffmpeg_commit`` for master), and merges
them into version YAML files under a ``data/`` hierarchy.

Usage
-----
    python scripts/import_yaml.py --artifacts-dir ./artifacts

Output
------
    data/{major}.x/ffmpeg-{version}-r{revision}.yaml   (versioned)
    data/master/ffmpeg-{ffmpeg_commit}.yaml              (master)
    data/{major}.x/build-index.yaml                      (index, updated)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOTAL_VARIANTS = 24
"""Expected number of variants per version (4 triplets × 3 licenses × 2 linkages)."""

DATA_DIR = "data"
"""Top-level directory for all generated metadata files."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_yaml_atomic(data: dict[str, Any], path: Path) -> None:
    """Write a YAML file atomically (write to temp, then rename).

    This avoids partial writes if the process is interrupted.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        suffix=".yaml",
        prefix=".tmp_",
        dir=str(path.parent),
    )
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
        Path(tmp_path_str).replace(path)
    except BaseException:
        # Clean up the temp file on failure
        Path(tmp_path_str).unlink(missing_ok=True)
        raise


def determine_group_key(var: dict[str, Any]) -> tuple:
    """Determine the grouping key for a variant.

    For regular releases, the key is ``(version, revision)``.
    For master builds (version == "master"), the key is ``(ffmpeg_commit,)``.

    Returns a tuple usable as a dict key.
    """
    version = var.get("version", "")
    if version == "master":
        commit = var.get("ffmpeg_commit")
        if not commit:
            print("  WARNING: master variant missing 'ffmpeg_commit', skipping", file=sys.stderr)
            return None
        return (commit,)
    revision = var.get("revision", 0)
    return (version, revision)


def determine_target_path(version: str, group_key: tuple) -> Path:
    """Determine the target version YAML path for a group.

    Args:
        version: The version string (e.g. ``"8.1.1"`` or ``"master"``).
        group_key: The grouping key from :func:`determine_group_key`.

    Returns:
        Relative ``Path`` under ``DATA_DIR``.
    """
    if version == "master":
        commit = group_key[0]
        return Path(DATA_DIR) / "master" / f"ffmpeg-{commit}.yaml"
    revision = group_key[1]
    major = version.split(".")[0]
    return Path(DATA_DIR) / f"{major}.x" / f"ffmpeg-{version}-r{revision}.yaml"


def determine_build_index_path(version: str) -> Path:
    """Determine the build-index path for a version's major group.

    Args:
        version: The version string (e.g. ``"8.1.1"`` or ``"master"``).

    Returns:
        Relative ``Path`` under ``DATA_DIR``.
    """
    if version == "master":
        return Path(DATA_DIR) / "master" / "build-index.yaml"
    major = version.split(".")[0]
    return Path(DATA_DIR) / f"{major}.x" / "build-index.yaml"


def make_release_tag(version: str, revision: int | None, ffmpeg_commit: str | None) -> str:
    """Build the GitHub release tag for a version group.

    Args:
        version: Version string (e.g. ``"8.1.1"`` or ``"master"``).
        revision: Revision number (``None`` for master).
        ffmpeg_commit: Git describe string (master only).

    Returns:
        Release tag string.
    """
    if version == "master":
        return f"ffmpeg-{ffmpeg_commit}"
    return f"ffmpeg-{version}-r{revision}"


def is_complete(variant_count: int) -> bool:
    """Check if all expected variants have been collected."""
    return variant_count >= TOTAL_VARIANTS


def merge_variants(existing_variants: list[dict], new_variants: list[dict]) -> list[dict]:
    """Merge new variants into an existing list, deduplicating by ``variant_id``.

    Args:
        existing_variants: The current list of variants.
        new_variants: New variants to append.

    Returns:
        A new list with duplicates removed (first occurrence wins).
    """
    seen = {v["variant_id"] for v in existing_variants if "variant_id" in v}
    merged = list(existing_variants)
    for v in new_variants:
        vid = v.get("variant_id")
        if vid and vid not in seen:
            merged.append(v)
            seen.add(vid)
    return merged


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def import_artifacts(artifacts_dir: Path) -> dict[str, Any]:
    """Import all ``.var.yaml`` artifacts and merge into data YAML files.

    Args:
        artifacts_dir: Directory containing ``.var.yaml`` files.

    Returns:
        A summary dict with keys:
        - ``files_created``: list of created version YAML paths
        - ``files_updated``: list of updated version YAML paths
        - ``variants_added``: total number of new variants added
        - ``errors``: list of error messages
    """
    summary: dict[str, Any] = {
        "files_created": [],
        "files_updated": [],
        "build_indices_created": [],
        "build_indices_updated": [],
        "variants_added": 0,
        "errors": [],
    }

    # ---- Discover .var.yaml files ----
    var_files = sorted(artifacts_dir.glob("*.var.yaml"))
    if not var_files:
        print("No .var.yaml files found in", artifacts_dir)
        return summary

    print(f"Found {len(var_files)} .var.yaml file(s) in {artifacts_dir}")

    # ---- Parse all variant YAML files ----
    variants: list[dict[str, Any]] = []
    for vf in var_files:
        try:
            var_data = load_yaml(vf)
            if not isinstance(var_data, dict) or "variant_id" not in var_data:
                summary["errors"].append(f"{vf.name}: missing variant_id, skipping")
                continue
            variants.append(var_data)
        except Exception as exc:
            summary["errors"].append(f"{vf.name}: parse error — {exc}")
            continue

    if not variants:
        print("No valid variants to import.")
        return summary

    print(f"Parsed {len(variants)} valid variant(s)")

    # ---- Group variants ----
    groups: dict[tuple, list[dict]] = {}
    for var in variants:
        key = determine_group_key(var)
        if key is None:
            continue
        groups.setdefault(key, []).append(var)

    print(f"Grouped into {len(groups)} version group(s)")

    # ---- Track build-index updates per major ----
    # build_index_updates: {build_index_path -> set of variant_ids to add}
    build_index_updates: dict[Path, set[str]] = {}

    # ---- Process each group ----
    for group_key, group_variants in groups.items():
        first = group_variants[0]
        version = first["version"]
        target_path = determine_target_path(version, group_key)

        # Collect variant_ids for build-index
        for var in group_variants:
            vid = var.get("variant_id")
            if vid:
                bi_path = determine_build_index_path(version)
                build_index_updates.setdefault(bi_path, set()).add(vid)

        if target_path.exists():
            # ---- Update existing version YAML ----
            try:
                existing = load_yaml(target_path)
            except Exception as exc:
                summary["errors"].append(
                    f"{target_path}: failed to load — {exc}, skipping group"
                )
                continue

            old_count = len(existing.get("variants", []))
            merged_variants = merge_variants(
                existing.get("variants", []), group_variants
            )
            new_count = len(merged_variants)

            if new_count == old_count:
                print(f"  {target_path}: no new variants (already up-to-date)")
                continue

            existing["variants"] = merged_variants
            existing["variant_count"] = new_count
            existing["complete"] = is_complete(new_count)
            existing["updated"] = now_iso()

            try:
                write_yaml_atomic(existing, target_path)
                summary["files_updated"].append(str(target_path))
                summary["variants_added"] += new_count - old_count
                print(f"  UPDATED {target_path}: {old_count} → {new_count} variants")
            except Exception as exc:
                summary["errors"].append(
                    f"{target_path}: write error — {exc}"
                )
        else:
            # ---- Create new version YAML ----
            ffmpeg_tag = first.get("ffmpeg_tag")
            ffmpeg_commit = first.get("ffmpeg_commit")
            revision = first.get("revision", 0) if version != "master" else None
            lts = first.get("lts", False)

            release_tag = make_release_tag(version, revision, ffmpeg_commit)

            target_variants = list(group_variants)
            variant_count = len(target_variants)

            version_yaml = {
                "version": version,
                "revision": revision,
                "lts": lts,
                "ffmpeg_tag": ffmpeg_tag,
                "ffmpeg_commit": ffmpeg_commit,
                "release_tag": release_tag,
                "release_id": None,
                "created": now_iso(),
                "updated": now_iso(),
                "variant_count": variant_count,
                "total_variants": TOTAL_VARIANTS,
                "complete": is_complete(variant_count),
                "variants": target_variants,
            }

            try:
                write_yaml_atomic(version_yaml, target_path)
                summary["files_created"].append(str(target_path))
                summary["variants_added"] += variant_count
                print(f"  CREATED {target_path}: {variant_count} variants")
            except Exception as exc:
                summary["errors"].append(
                    f"{target_path}: write error — {exc}"
                )

    # ---- Update build-index files ----
    for bi_path, new_vids in sorted(build_index_updates.items()):
        bi_existed = bi_path.exists()
        if bi_existed:
            try:
                bi_data = load_yaml(bi_path)
            except Exception as exc:
                summary["errors"].append(
                    f"{bi_path}: failed to load — {exc}"
                )
                continue

            existing_vids = set(bi_data.get("variants", []))
            merged_vids = existing_vids | new_vids
            if merged_vids == existing_vids:
                print(f"  {bi_path}: no new variant IDs (up-to-date)")
                continue

            bi_data["variants"] = sorted(merged_vids)
            bi_data["last_updated"] = now_iso()
            added_count = len(merged_vids - existing_vids)
        else:
            # Create new build-index
            bi_data = {
                "last_updated": now_iso(),
                "variants": sorted(new_vids),
            }
            added_count = len(new_vids)

        try:
            write_yaml_atomic(bi_data, bi_path)
            if bi_existed:
                summary["build_indices_updated"].append(str(bi_path))
                print(f"  UPDATED {bi_path}: +{added_count} variant ID(s)")
            else:
                summary["build_indices_created"].append(str(bi_path))
                print(f"  CREATED {bi_path}: +{added_count} variant ID(s)")
        except Exception as exc:
            summary["errors"].append(f"{bi_path}: write error — {exc}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Import .var.yaml artifacts and merge into data branch YAML files.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default=".",
        help="Directory containing .var.yaml files (default: current directory)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point."""
    args = parse_args(argv)

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        print(f"ERROR: artifacts directory not found: {artifacts_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Importing from: {artifacts_dir.resolve()}")
    print()

    summary = import_artifacts(artifacts_dir)

    print()
    print("=" * 50)
    print("IMPORT SUMMARY")
    print("=" * 50)
    print(f"  Version files created:   {len(summary['files_created'])}")
    for fp in summary["files_created"]:
        print(f"    - {fp}")
    print(f"  Version files updated:   {len(summary['files_updated'])}")
    for fp in summary["files_updated"]:
        print(f"    - {fp}")
    print(f"  Build indices created:   {len(summary['build_indices_created'])}")
    for fp in summary["build_indices_created"]:
        print(f"    - {fp}")
    print(f"  Build indices updated:   {len(summary['build_indices_updated'])}")
    for fp in summary["build_indices_updated"]:
        print(f"    - {fp}")
    print(f"  Variants added:          {summary['variants_added']}")
    if summary["errors"]:
        print(f"  Errors:                  {len(summary['errors'])}")
        for err in summary["errors"]:
            print(f"    - {err}")
    print()

    # Exit with non-zero if there were errors
    if summary["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
