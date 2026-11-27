"""Apply age-based retention to Master releases in the release catalog.

Stable releases and Git tags are never deleted. Remote deletion is verified
before the corresponding catalog entries are removed.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def process_snapshots(data_dir: Path, *, dry_run: bool = False) -> tuple[int, int]:
    # The script can be launched directly by the existing retention Workflow.
    from ffbuild import catalog
    manifest = catalog.require_manifest(data_dir)
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
    """Delete verified Master prereleases, never refs; commit later."""
    from ffbuild import catalog
    from ffbuild.publication import _release_api, _run
    from ffbuild.autoheal.github import repository
    manifest = catalog.require_manifest(data_dir)
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
        description="Enforce retention policy on Master releases.",
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

    if args.apply_remote and dry_run:
        raise ValueError("Choose apply or dry-run")
    kept, deleted = (apply_remote_retention(data_dir) if args.apply_remote else
                     process_snapshots(data_dir, dry_run=True))

    print(f"Kept: {kept}, Deleted: {deleted}")


if __name__ == "__main__":
    main()
