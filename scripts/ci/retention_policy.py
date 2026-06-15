#!/usr/bin/env python3
"""
retention_policy.py — Enforce retention policy on version YAML files.

Usage
-----
    python scripts/retention_policy.py [data_dir]

The script processes two categories independently:
  1. Non-master (data/{major}.x/):
     - Within each minor version group, keep only the latest revision.
     - Then limit to at most 3 versions per major.
  2. Master (data/master/):
     - Age-based retention with weekly / monthly / quarterly bucketing.

For each deleted version YAML the script:
  - Removes all associated variant_ids from build-index.yaml
  - Deletes the version YAML file
  - Prints DELETE_RELEASE:<release_tag> and DELETE_TAG:<release_tag> for CI

Output
------
    DELETE_RELEASE:ffmpeg-8.1.1-r1
    DELETE_TAG:ffmpeg-8.1.1-r1
    DELETE_RELEASE:ffmpeg-n8.2-dev-1-gabc1234
    DELETE_TAG:ffmpeg-n8.2-dev-1-gabc1234
    Kept: 12, Deleted: 3
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Filename pattern for non-master releases:
#   ffmpeg-8.1.1-r2.yaml
VERSION_FILE_RE = re.compile(r"^ffmpeg-(\d+)\.(\d+)\.(\d+)-r(\d+)\.yaml$")

# Filename pattern for master releases:
#   ffmpeg-n8.2-dev-1-gabc1234.yaml
MASTER_FILE_RE = re.compile(r"^ffmpeg-(.+)\.yaml$")

# Standardised date formats that may appear in the `created` field.
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_created(data: dict[str, Any], file_path: Path) -> datetime:
    """Parse the ``created`` field from a version YAML.

    Falls back to the file's mtime when the field is missing or unparseable.
    The returned datetime is always timezone-aware (UTC).
    """
    raw = data.get("created")
    if raw is not None:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if isinstance(raw, str):
            for fmt in _DATE_FORMATS:
                try:
                    dt = datetime.strptime(raw, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

    # Fallback: file modification time
    mtime = file_path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def get_release_tag(data: dict[str, Any], file_path: Path) -> str:
    """Return the release tag for a version YAML.

    Prefers the ``release_tag`` field from the YAML; otherwise derives it
    from the filename (i.e. the stem of the file).
    """
    tag = data.get("release_tag")
    if tag and isinstance(tag, str):
        return tag
    return file_path.stem


def get_variant_ids(data: dict[str, Any]) -> list[str]:
    """Extract all unique ``variant_id`` strings from a version YAML's
    ``variants`` array.

    Supports two formats inside the array:
      - dict entries with a ``variant_id`` key (preferred).
      - plain strings (used directly).
    """
    variants = data.get("variants")
    if not isinstance(variants, list):
        return []

    ids: list[str] = []
    for entry in variants:
        if isinstance(entry, dict):
            vid = entry.get("variant_id")
            if vid and isinstance(vid, str):
                ids.append(vid)
        elif isinstance(entry, str):
            ids.append(entry)
    return ids


def compute_quarter_key(dt: datetime) -> str:
    """Return ``YYYY-Q{1-4}`` for the given datetime."""
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def compute_week_key(dt: datetime) -> str:
    """Return ``YYYY-Www`` (ISO week) for the given datetime."""
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def compute_month_key(dt: datetime) -> str:
    """Return ``YYYY-MM`` for the given datetime."""
    return f"{dt.year}-{dt.month:02d}"


# ---------------------------------------------------------------------------
# build-index helpers
# ---------------------------------------------------------------------------

def _read_build_index(path: Path) -> dict[str, Any]:
    """Read and return the contents of a ``build-index.yaml``.

    Returns a default structure if the file does not exist.
    """
    if not path.exists():
        return {"variants": []}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        return {"variants": []}
    if "variants" not in data:
        data["variants"] = []
    return data


def _write_build_index(path: Path, data: dict[str, Any]) -> None:
    """Write *data* to ``build-index.yaml``."""
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


def remove_variants_from_index(
    build_index_path: Path,
    variant_ids: list[str],
) -> None:
    """Remove *variant_ids* from the ``variants`` array of a build-index.

    No-op if the build-index does not exist or the array is empty.
    The file is only written back when at least one entry was removed.
    """
    if not variant_ids:
        return
    if not build_index_path.exists():
        return

    index_data = _read_build_index(build_index_path)
    original = index_data.get("variants", [])
    if not isinstance(original, list):
        original = []

    lookup = set(variant_ids)
    pruned = [v for v in original if v not in lookup]

    if len(pruned) != len(original):
        index_data["variants"] = pruned
        _write_build_index(build_index_path, index_data)


# ---------------------------------------------------------------------------
# Deletion logic
# ---------------------------------------------------------------------------

def delete_version_yaml(
    file_path: Path,
    build_index_path: Path,
    release_tag: str,
    *,
    dry_run: bool = False,
) -> None:
    """Delete a version YAML and remove its variants from build-index.

    Prints ``DELETE_RELEASE:`` and ``DELETE_TAG:`` lines that the CI
    workflow uses to delete the corresponding GitHub Release and git tag.
    """
    # Read variant_ids before deleting the file.
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        data = {}

    variant_ids = get_variant_ids(data)

    if not dry_run:
        # Remove from build-index
        if build_index_path.exists():
            remove_variants_from_index(build_index_path, variant_ids)

        # Delete version YAML
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass  # already gone — idempotent
    else:
        print(f"  [dry-run] Would delete: {file_path.name}")

    # CI-consumable output
    print(f"DELETE_RELEASE:{release_tag}")
    print(f"DELETE_TAG:{release_tag}")


# ---------------------------------------------------------------------------
# Non-master retention  (data/{major}.x/)
# ---------------------------------------------------------------------------

def process_non_master(
    data_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Process all ``data/{major}.x/`` directories.

    Returns ``(kept, deleted)`` counts.
    """
    kept = 0
    deleted = 0

    # Locate all major-version directories (e.g. "8.x", "7.x").
    major_dirs = sorted(
        d
        for d in data_dir.iterdir()
        if d.is_dir() and re.match(r"^\d+\.x$", d.name)
    )

    for major_dir in major_dirs:
        build_index_path = major_dir / "build-index.yaml"

        # Collect version YAML files (skip build-index itself).
        version_files = sorted(
            f
            for f in major_dir.glob("*.yaml")
            if f.name != "build-index.yaml"
        )
        if not version_files:
            continue

        # ---- Parse every version file ----
        versions: list[dict[str, Any]] = []
        for vf in version_files:
            m = VERSION_FILE_RE.match(vf.name)
            if not m:
                # File does not follow naming convention; skip it.
                continue

            major_str, minor_str, patch_str, revision_str = m.groups()
            version_str = f"{major_str}.{minor_str}.{patch_str}"
            revision = int(revision_str)
            minor_group = f"{major_str}.{minor_str}.x"

            try:
                with open(vf, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            except Exception:
                data = {}

            created = parse_created(data, vf)
            release_tag = get_release_tag(data, vf)

            versions.append({
                "path": vf,
                "version": version_str,
                "revision": revision,
                "minor_group": minor_group,
                "created": created,
                "release_tag": release_tag,
                "data": data,
            })

        if not versions:
            continue

        # ---- Phase 1: per-minor-group, per-version, keep latest revision ----
        #   Group by minor_group, then by full version string.
        #   For each full version, keep only the entry with the highest revision.
        to_delete: set[str] = set()

        minor_groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for v in versions:
            mg = v["minor_group"]
            ver = v["version"]
            minor_groups.setdefault(mg, {}).setdefault(ver, []).append(v)

        for mg, ver_dict in minor_groups.items():
            for ver, ver_versions in ver_dict.items():
                # Sort by revision descending, then created descending.
                ver_versions.sort(key=lambda x: (-x["revision"], -x["created"].timestamp()))
                # First entry is the keeper; the rest are candidates for deletion.
                for candidate in ver_versions[1:]:
                    to_delete.add(candidate["release_tag"])

        # ---- Phase 2: limit to at most 3 version files per major ----
        surviving = [v for v in versions if v["release_tag"] not in to_delete]
        if len(surviving) > 3:
            # Sort by created descending and keep the 3 newest.
            surviving.sort(key=lambda x: -x["created"].timestamp())
            for v in surviving[3:]:
                to_delete.add(v["release_tag"])

        # ---- Execute deletions ----
        for v in versions:
            if v["release_tag"] in to_delete:
                delete_version_yaml(
                    v["path"],
                    build_index_path,
                    v["release_tag"],
                    dry_run=dry_run,
                )
                deleted += 1
            else:
                kept += 1

    return kept, deleted


# ---------------------------------------------------------------------------
# Master retention  (data/master/)
# ---------------------------------------------------------------------------

def process_master(
    data_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Process ``data/master/`` directory.

    Returns ``(kept, deleted)`` counts.
    """
    master_dir = data_dir / "master"
    if not master_dir.is_dir():
        return 0, 0

    build_index_path = master_dir / "build-index.yaml"

    # Collect version YAML files (skip build-index).
    version_files = sorted(
        f
        for f in master_dir.glob("*.yaml")
        if f.name != "build-index.yaml"
    )
    if not version_files:
        return 0, 0

    # ---- Parse every version file ----
    versions: list[dict[str, Any]] = []
    for vf in version_files:
        m = MASTER_FILE_RE.match(vf.name)
        if not m:
            continue  # does not follow naming convention

        try:
            with open(vf, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            data = {}

        created = parse_created(data, vf)
        release_tag = get_release_tag(data, vf)

        now = datetime.now(timezone.utc)
        age_days = (now - created).days

        versions.append({
            "path": vf,
            "created": created,
            "release_tag": release_tag,
            "age_days": age_days,
            "data": data,
        })

    if not versions:
        return 0, 0

    # ---- Age-based retention ----
    keep_tags: set[str] = set()

    # < 7 days: keep everything
    for v in versions:
        if v["age_days"] < 7:
            keep_tags.add(v["release_tag"])

    # 7–30 days: keep newest per ISO week
    week_buckets: dict[str, list[dict[str, Any]]] = {}
    for v in versions:
        if 7 <= v["age_days"] < 30:
            wk = compute_week_key(v["created"])
            week_buckets.setdefault(wk, []).append(v)
    for bucket in week_buckets.values():
        best = max(bucket, key=lambda x: x["created"])
        keep_tags.add(best["release_tag"])

    # 30 days – 1 year: keep newest per calendar month
    month_buckets: dict[str, list[dict[str, Any]]] = {}
    for v in versions:
        if 30 <= v["age_days"] < 365:
            mo = compute_month_key(v["created"])
            month_buckets.setdefault(mo, []).append(v)
    for bucket in month_buckets.values():
        best = max(bucket, key=lambda x: x["created"])
        keep_tags.add(best["release_tag"])

    # >= 1 year: keep newest per calendar quarter
    quarter_buckets: dict[str, list[dict[str, Any]]] = {}
    for v in versions:
        if v["age_days"] >= 365:
            q = compute_quarter_key(v["created"])
            quarter_buckets.setdefault(q, []).append(v)
    for bucket in quarter_buckets.values():
        best = max(bucket, key=lambda x: x["created"])
        keep_tags.add(best["release_tag"])

    # ---- Execute deletions ----
    kept = 0
    deleted = 0
    for v in versions:
        if v["release_tag"] in keep_tags:
            kept += 1
        else:
            delete_version_yaml(
                v["path"],
                build_index_path,
                v["release_tag"],
                dry_run=dry_run,
            )
            deleted += 1

    return kept, deleted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enforce retention policy on version YAML files.",
    )
    parser.add_argument(
        "data_dir",
        nargs="?",
        default="data",
        help="Path to the data/ directory (default: data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without deleting files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    dry_run = args.dry_run

    if not data_dir.is_dir():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    total_kept = 0
    total_deleted = 0

    # Non-master directories  (data/{major}.x/)
    km, dm = process_non_master(data_dir, dry_run=dry_run)
    total_kept += km
    total_deleted += dm

    # Master directory  (data/master/)
    kmm, dmm = process_master(data_dir, dry_run=dry_run)
    total_kept += kmm
    total_deleted += dmm

    print(f"Kept: {total_kept}, Deleted: {total_deleted}")


if __name__ == "__main__":
    main()
