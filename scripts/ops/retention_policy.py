#!/usr/bin/env python3
"""
retention_policy.py — Enforce retention policy on version directories.

Usage
-----
    python scripts/ops/retention_policy.py [data_dir]

The script processes two categories independently:
  1. Non-master (data/{major}.x/):
     - Within each minor version group, keep only the latest revision.
     - Then limit to at most 3 versions per major.
  2. Master (data/master/):
     - Age-based retention with weekly / monthly / quarterly bucketing.

For each deleted version the script:
  - Deletes the entire version directory (version.yaml + variants/*.yaml)
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
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from naming import parse_version_dir, VERSION_DIR_RE


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------



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
    """Parse the ``created`` field from a version.yaml.

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
    """Return the release tag for a version directory.

    Prefers the ``release_tag`` field from the YAML; otherwise derives it
    from the parent directory name (e.g. ``ffmpeg-8.1.1-r2``).
    """
    tag = data.get("release_tag")
    if tag and isinstance(tag, str):
        return tag
    return f"ffmpeg-{file_path.parent.name}"


def get_variant_ids(data: dict[str, Any]) -> list[str]:
    """Extract all unique ``variant_id`` strings from a version.yaml's
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
# Deletion logic
# ---------------------------------------------------------------------------

def delete_version_dir(
    version_dir: Path,
    release_tag: str,
    *,
    dry_run: bool = False,
) -> None:
    """Delete an entire version directory (version.yaml + variants/*.yaml).

    Prints ``DELETE_RELEASE:`` and ``DELETE_TAG:`` lines that the CI
    workflow uses to delete the corresponding GitHub Release and git tag.
    """
    if not dry_run:
        try:
            shutil.rmtree(version_dir)
        except FileNotFoundError:
            pass  # already gone — idempotent
    else:
        print(f"  [dry-run] Would delete directory: {version_dir}/")

    # CI-consumable output
    print(f"DELETE_RELEASE:{release_tag}")
    print(f"DELETE_TAG:{release_tag}")


# ---------------------------------------------------------------------------
# Non-master retention  (data/{major}.x/)
# ---------------------------------------------------------------------------

def _collect_version_dirs(major_dir: Path) -> list[tuple[Path, str, int]]:
    """Collect all version subdirectories under *major_dir*.

    Returns list of ``(version_dir, version, revision)`` tuples
    parsed from directory names using parse_version_dir.
    """
    result: list[tuple[Path, str, int]] = []
    for d in sorted(major_dir.iterdir()):
        if not d.is_dir() or not (d / "version.yaml").exists():
            continue
        info = parse_version_dir(d.name)
        if info["version"]:
            result.append((d, info["version"], info["revision"]))
    return result


def process_non_master(
    data_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Process non-master (release) version directories under ``data/{major}.x/``.

    Master builds (revision == 0) are skipped and handled separately.

    Returns ``(kept, deleted)`` counts.
    """
    kept = 0
    deleted = 0

    major_dirs = sorted(
        d for d in data_dir.iterdir()
        if d.is_dir() and re.match(r"^\d+\.x$", d.name)
    )

    for major_dir in major_dirs:
        versions: list[dict[str, Any]] = []
        for vd, version_str, revision in _collect_version_dirs(major_dir):
            if revision == 0:
                continue  # master build, handled by process_master

            # Derive version from version_str (strip "n" prefix)
            version_str = version_str.lstrip("n").split("-")[0]
            ver_parts = version_str.split(".")
            minor_group = f"{ver_parts[0]}.{ver_parts[1]}.x" if len(ver_parts) >= 2 else "unknown"

            version_yaml = vd / "version.yaml"
            try:
                with open(version_yaml, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            except Exception:
                data = {}

            created = parse_created(data, version_yaml)
            release_tag = get_release_tag(data, version_yaml)

            versions.append({
                "path": vd,
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
        to_delete: set[str] = set()
        minor_groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for v in versions:
            mg = v["minor_group"]
            ver = v["version"]
            minor_groups.setdefault(mg, {}).setdefault(ver, []).append(v)

        for mg, ver_dict in minor_groups.items():
            for ver, ver_versions in ver_dict.items():
                ver_versions.sort(key=lambda x: (-x["revision"], -x["created"].timestamp()))
                for candidate in ver_versions[1:]:
                    to_delete.add(candidate["release_tag"])

        # ---- Phase 2: limit to at most 3 versions per major ----
        surviving = [v for v in versions if v["release_tag"] not in to_delete]
        if len(surviving) > 3:
            surviving.sort(key=lambda x: -x["created"].timestamp())
            for v in surviving[3:]:
                to_delete.add(v["release_tag"])

        # ---- Execute deletions ----
        for v in versions:
            if v["release_tag"] in to_delete:
                delete_version_dir(v["path"], v["release_tag"], dry_run=dry_run)
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
    """Process master builds (revision == 0) across all ``data/{major}.x/`` dirs.

    Master builds are identified by revision == 0 (git describe).
    Age-based retention: weekly / monthly / quarterly bucketing.

    Returns ``(kept, deleted)`` counts.
    """
    major_dirs = sorted(
        d for d in data_dir.iterdir()
        if d.is_dir() and re.match(r"^\d+\.x$", d.name)
    )

    versions: list[dict[str, Any]] = []
    for major_dir in major_dirs:
        for vd, version_str, revision in _collect_version_dirs(major_dir):
            if revision != 0:
                continue  # release build, handled by process_non_master

            version_yaml = vd / "version.yaml"
            try:
                with open(version_yaml, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            except Exception:
                data = {}

            created = parse_created(data, version_yaml)
            release_tag = get_release_tag(data, version_yaml)
            age_days = (datetime.now(timezone.utc) - created).days

            versions.append({
                "path": vd,
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
            delete_version_dir(
                v["path"],
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
        description="Enforce retention policy on version directories.",
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

    # Non-master (revision > 0, stable releases)
    km, dm = process_non_master(data_dir, dry_run=dry_run)
    total_kept += km
    total_deleted += dm

    # Master (revision == 0, git describe builds)
    kmm, dmm = process_master(data_dir, dry_run=dry_run)
    total_kept += kmm
    total_deleted += dmm

    print(f"Kept: {total_kept}, Deleted: {total_deleted}")


if __name__ == "__main__":
    main()
