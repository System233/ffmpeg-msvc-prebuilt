#!/usr/bin/env python3
"""
retention_policy.py — Enforce retention policy on snapshot version directories.

Only snapshot builds (identified by ffmpeg_ref matching git describe format)
are cleaned up. Tagged releases are never removed.

Usage
-----
    python -m ffbuild.retention [data_dir]

Age-based retention with weekly / monthly / quarterly bucketing.

For each deleted version the script:
  - Deletes the entire version directory (version.yaml + variants/*.yaml)
  - Prints DELETE_RELEASE:<release_tag> for CI; Git tags are retained

Output
------
    DELETE_RELEASE:ffmpeg-n8.0-1234-gabc
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

from .identity import release_tag


def parse_version_dir(dirname: str) -> dict:
    match = re.fullmatch(r"(.+?)(?:-r(\d+))?", dirname)
    if not match:
        raise ValueError(f"Invalid legacy version directory: {dirname}")
    return {"version": match[1], "revision": int(match[2] or 0)}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------



_GIT_DESCRIBE_RE = re.compile(r"^n\d+\.\d+.*-\d+-g[0-9a-f]+$")


def is_snapshot_ref(ffmpeg_ref: str) -> bool:
    """Return True if *ffmpeg_ref* is a git describe string (snapshot build)."""
    return bool(_GIT_DESCRIBE_RE.match(ffmpeg_ref or ""))


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
    info = parse_version_dir(file_path.parent.name)
    return release_tag(info["version"], info["revision"])


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
    """Report historical YAML expiry without modifying the legacy index."""
    if not dry_run:
        raise ValueError("Migrate Data before cleanup; legacy YAML is read-only")
    print(f"  [dry-run] Would delete directory: {version_dir}/")

    # CI-consumable output
    print(f"DELETE_RELEASE:{release_tag}")


# ---------------------------------------------------------------------------
# Snapshot retention  (data/{major}.x/)
# ---------------------------------------------------------------------------

def _collect_version_dirs(major_dir: Path) -> list[tuple[Path, str, int]]:
    """Collect all version subdirectories under *major_dir*."""
    result: list[tuple[Path, str, int]] = []
    for d in sorted(major_dir.iterdir()):
        if not d.is_dir() or not (d / "version.yaml").exists():
            continue
        info = parse_version_dir(d.name)
        if info["version"]:
            result.append((d, info["version"], info["revision"]))
    return result


def process_snapshots(
    data_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Process snapshot builds across all ``data/{major}.x/`` dirs.

    Snapshots identified by ``ffmpeg_ref`` matching git describe format
    (e.g. ``n8.0-1234-gabc``).  Tagged releases are skipped entirely.

    Age-based retention: weekly / monthly / quarterly bucketing.

    Returns ``(kept, deleted)`` counts.
    """
    if (data_dir / "index.json").is_file():
        return process_catalog_snapshots(data_dir, dry_run=dry_run)
    if not dry_run:
        raise ValueError("Migrate Data before cleanup; legacy YAML is read-only")
    major_dirs = sorted(
        d for d in data_dir.iterdir()
        if d.is_dir() and re.match(r"^\d+\.x$", d.name)
    )

    versions: list[dict[str, Any]] = []
    for major_dir in major_dirs:
        for vd, version_str, revision in _collect_version_dirs(major_dir):
            version_yaml = vd / "version.yaml"
            try:
                with open(version_yaml, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            except Exception:
                data = {}

            if data.get("channel") != "master" and not is_snapshot_ref(data.get("ffmpeg_ref", "")):
                continue  # tagged release, skip

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

    keep_tags = retention_keep_tags(versions)

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


def _retention_order(row: dict):
    from ffbuild.identity import release_order
    created = row["created"]
    return (created, release_order(created.date().isoformat(), row["release_tag"]))


def retention_keep_tags(versions):
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
        best = max(bucket, key=_retention_order)
        keep_tags.add(best["release_tag"])

    # 30 days – 1 year: keep newest per calendar month
    month_buckets: dict[str, list[dict[str, Any]]] = {}
    for v in versions:
        if 30 <= v["age_days"] < 365:
            mo = compute_month_key(v["created"])
            month_buckets.setdefault(mo, []).append(v)
    for bucket in month_buckets.values():
        best = max(bucket, key=_retention_order)
        keep_tags.add(best["release_tag"])

    # >= 1 year: keep newest per calendar quarter
    quarter_buckets: dict[str, list[dict[str, Any]]] = {}
    for v in versions:
        if v["age_days"] >= 365:
            q = compute_quarter_key(v["created"])
            quarter_buckets.setdefault(q, []).append(v)
    for bucket in quarter_buckets.values():
        best = max(bucket, key=_retention_order)
        keep_tags.add(best["release_tag"])

    return keep_tags


def process_catalog_snapshots(data_dir: Path, *, dry_run: bool = False) -> tuple[int, int]:
    # The script can be launched directly by the existing retention Workflow.
    from ffbuild import catalog
    manifest = catalog.manifest(data_dir)
    shards = {}
    versions = []
    now = datetime.now(timezone.utc)
    for year in manifest["master"]:
        path = catalog.shard_path(data_dir, "master", year)
        if not path.is_file():
            raise ValueError("Missing master catalog shard")
        shard = catalog.load_shard(data_dir, "master", year)
        shards[year] = shard
        for release in shard["releases"]:
            created = datetime.fromisoformat(release["date"]).replace(tzinfo=timezone.utc)
            versions.append({"created": created, "age_days": (now - created).days,
                             "release_tag": release["tag"]})
    keep = retention_keep_tags(versions)
    deleted = [row["release_tag"] for row in versions if row["release_tag"] not in keep]
    if not dry_run:
        for year, shard in shards.items():
            filtered = [r for r in shard["releases"] if r["tag"] in keep]
            if filtered == shard["releases"]:
                continue
            path = catalog.shard_path(data_dir, "master", year)
            if filtered:
                catalog.write_json(path, dict(shard, releases=filtered))
            else:
                path.unlink()
                manifest["master"].remove(year)
        catalog.write_json(data_dir / "index.json", manifest)
    for tag in deleted:
        print(f"DELETE_RELEASE:{tag}")
    return len(versions) - len(deleted), len(deleted)


def apply_remote_retention(data_dir: Path) -> tuple[int, int]:
    """Plan from v2 only; delete verified prereleases, never refs; commit later."""
    from ffbuild import catalog
    from ffbuild.publication import _release_api, _run
    from ffbuild.autoheal.github import repository
    if not (data_dir / "index.json").is_file():
        raise ValueError("Migrate Data before automatic cleanup")
    manifest = catalog.manifest(data_dir)
    shards = {}
    candidates = []
    now = datetime.now(timezone.utc)
    for year in manifest["master"]:
        path = catalog.shard_path(data_dir, "master", year)
        if not path.is_file():
            raise ValueError("Missing Master catalog shard")
        shard = catalog.load_shard(data_dir, "master", year)
        shards[year] = shard
        for item in shard["releases"]:
            created = datetime.fromisoformat(item["date"]).replace(tzinfo=timezone.utc)
            tag = item["tag"]
            if not (re.fullmatch(r"ffmpeg-master-[0-9]{6}(?:R[2-9][0-9]*|R1[0-9]+)?", tag)
                    or re.fullmatch(r"ffmpeg-n?[0-9]+\.[A-Za-z0-9.+-]*-[0-9]+-g[0-9a-f]+(?:-r[0-9]+)?", tag)):
                raise ValueError(f"Refusing non-Master retention candidate: {tag}")
            candidates.append({"created": created, "age_days": (now-created).days, "release_tag": tag})
    keep = retention_keep_tags(candidates)
    delete = {r["release_tag"] for r in candidates} - keep
    # No local index mutation before all remote operations are confirmed.
    for tag in sorted(delete):
        release = _release_api(tag)
        if release is not None:
            if release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not True:
                raise ValueError(f"Refusing to delete non-snapshot or draft Release: {tag}")
            if type(release.get("id")) is not int or release["id"] <= 0:
                raise ValueError("Invalid GitHub Release identity")
            _run("gh", "api", f"repos/{repository()}/releases/{release['id']}", "--method", "DELETE")
            if _release_api(tag) is not None:
                raise RuntimeError(f"Release deletion not confirmed: {tag}")
        print(f"CONFIRMED_RELEASE_REMOVED:{tag}")
    for year, shard in shards.items():
        filtered = [r for r in shard["releases"] if r["tag"] not in delete]
        if filtered == shard["releases"]:
            continue
        path = catalog.shard_path(data_dir, "master", year)
        if filtered:
            catalog.write_json(path, dict(shard, releases=filtered))
        else:
            path.unlink()
            manifest["master"].remove(year)
    catalog.write_json(data_dir / "index.json", manifest)
    return len(candidates)-len(delete), len(delete)


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
        help="Print actions without deleting files (default unless --apply-remote)",
    )
    parser.add_argument("--apply-remote", action="store_true", help="Delete verified Master Releases only, preserve all tags")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    dry_run = args.dry_run

    if not data_dir.is_dir():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    # Only clean snapshots (ffmpeg_ref matches git describe format)
    if args.apply_remote and dry_run:
        raise ValueError("Choose apply or dry-run")
    kept, deleted = (apply_remote_retention(data_dir) if args.apply_remote else
                     process_snapshots(data_dir, dry_run=True))

    print(f"Kept: {kept}, Deleted: {deleted}")


if __name__ == "__main__":
    main()
