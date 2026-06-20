#!/usr/bin/env python3
"""
db.py — CLI tool for managing the ``data/`` YAML variant database.

Provides subcommands for importing, checking, listing, showing, merging,
validating, removing, and migrating variant data files.

Usage
-----
    python scripts/ops/db.py --help
    python scripts/ops/db.py import <var-yaml-path>
    python scripts/ops/db.py has <variant-id>
    python scripts/ops/db.py list [--major MAJOR]
    python scripts/ops/db.py show <version-id>
    python scripts/ops/db.py merge <version-id>
    python scripts/ops/db.py validate
    python scripts/ops/db.py remove <variant-id>
    python scripts/ops/db.py migrate
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import os
import subprocess
from lts import is_lts
from naming import parse_variant_id as naming_parse, major_version, ARCH_NAMES, VALID_LINKAGES, VALID_LICENSES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")  # data branch checkout (relative to repo root)
SCHEMA_VERSION = 1
TOTAL_VARIANTS = int(os.environ.get("TOTAL_VARIANTS", str(4 * 3 * 2)))


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
        Path(tmp_path_str).unlink(missing_ok=True)
        raise


def parse_variant_id(variant_id: str) -> dict[str, str | int]:
    """Parse a variant_id string into its components.

    Delegates to ci.naming.parse_variant_id for both
    new format (with '_' separator) and legacy format (all '-').
    """
    return naming_parse(variant_id)


def resolve_version_dir(version_id: str) -> Path | None:
    """Resolve a version_id to a version directory Path.

    Accepts:
        - A version ID like ``"8.1.1-r2"`` (searches ``data/*/``)
        - A full or relative path like ``"data/8.x/8.1.1-r2"``
    """
    p = Path(version_id)
    if p.is_dir():
        return p.resolve()

    # Try as relative to DATA_DIR
    p2 = DATA_DIR / version_id
    if p2.is_dir():
        return p2.resolve()

    # Search under all major directories
    if DATA_DIR.is_dir():
        for major_dir in sorted(DATA_DIR.iterdir()):
            if major_dir.is_dir():
                candidate = major_dir / version_id
                if candidate.is_dir():
                    return candidate.resolve()
    return None


def make_release_url(release_tag: str) -> str:
    """Build a GitHub release URL from a release tag."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True,
        )
        url = result.stdout.strip()
        m = re.search(r'(?:github\.com[:/])([^/]+/[^/]+?)(?:\.git)?$', url)
        if m:
            repo = m.group(1)
    if not repo:
        repo = "unknown/repository"
    return f"https://github.com/{repo}/releases/tag/{release_tag}"


def is_variant_complete(variant_count: int) -> bool:
    """Check if all expected variants have been collected."""
    return variant_count >= TOTAL_VARIANTS


# ---------------------------------------------------------------------------
# Subcommand: import
# ---------------------------------------------------------------------------

def cmd_import(args: argparse.Namespace) -> None:
    """Import a .var.yaml file into the new folder structure."""
    var_path = Path(args.var_yaml_path)
    if not var_path.is_file():
        print(f"ERROR: file not found: {var_path}", file=sys.stderr)
        sys.exit(1)

    var_data = load_yaml(var_path)
    if not isinstance(var_data, dict):
        print(f"ERROR: invalid YAML in {var_path}", file=sys.stderr)
        sys.exit(1)

    variant_id = var_data.get("variant_id")
    if not variant_id:
        print(f"ERROR: missing 'variant_id' in {var_path}", file=sys.stderr)
        sys.exit(1)

    try:
        info = parse_variant_id(variant_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    major = info["major"]
    version_id = info["version_id"]
    variant_key = info["variant_key"]

    target_dir = DATA_DIR / major / version_id / "variants"
    target_path = target_dir / f"{variant_key}.yaml"

    if target_path.exists():
        print(f"SKIPPED (already exists): {target_path}")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(var_data, target_path)
    print(f"IMPORTED {target_path}")

    # Auto-merge: collect all variants for this version and write version.yaml.
    # Idempotent — safe to call after every single import.
    merge_args = argparse.Namespace(version_id=version_id)
    cmd_merge(merge_args)


# ---------------------------------------------------------------------------
# Subcommand: has
# ---------------------------------------------------------------------------

def cmd_has(args: argparse.Namespace) -> None:
    """Check if a variant exists in the database."""
    try:
        info = parse_variant_id(args.variant_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    variant_path = (
        DATA_DIR / info["major"] / info["version_id"] / "variants"
        / f"{info['variant_key']}.yaml"
    )

    if variant_path.exists():
        sys.exit(0)
    else:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    """List versions and their variant counts."""
    if args.major:
        major_dirs = [DATA_DIR / args.major]
    else:
        if DATA_DIR.is_dir():
            major_dirs = sorted(
                d for d in DATA_DIR.iterdir() if d.is_dir()
            )
        else:
            major_dirs = []

    rows: list[dict[str, Any]] = []
    for major_dir in major_dirs:
        version_dirs = sorted(
            d for d in major_dir.iterdir()
            if d.is_dir() and (d / "variants").is_dir()
        )
        for vdir in version_dirs:
            version_id = vdir.name
            version_yaml = vdir / "version.yaml"

            if version_yaml.exists():
                meta = load_yaml(version_yaml)
                variant_count = meta.get("variant_count", 0)
                total_variants = meta.get("total_variants", TOTAL_VARIANTS)
                complete = meta.get("complete", False)
                created = meta.get("created", "")
            else:
                variant_files = sorted(vdir.glob("variants/*.yaml"))
                variant_count = len(variant_files)
                total_variants = TOTAL_VARIANTS
                complete = is_variant_complete(variant_count)
                created = ""

            rows.append({
                "version_id": version_id,
                "variant_count": variant_count,
                "total_variants": total_variants,
                "complete": complete,
                "created": created,
            })

    if not rows:
        print("No versions found.")
        return

    # Print table
    header = f"{'Version ID':<20} {'Variants':<10} {'Total':<6} {'Complete':<10} {'Created':<20}"
    print(header)
    for r in rows:
        variants_str = f"{r['variant_count']}/{r['total_variants']}"
        complete_str = "YES" if r["complete"] else "NO"
        created_str = r["created"][:10] if r["created"] else ""
        print(
            f"{r['version_id']:<20} {variants_str:<10} "
            f"{r['total_variants']:<6} {complete_str:<10} {created_str:<20}"
        )


# ---------------------------------------------------------------------------
# Subcommand: show
# ---------------------------------------------------------------------------

def cmd_show(args: argparse.Namespace) -> None:
    """Show version details and all its variants."""
    version_dir = resolve_version_dir(args.version_id)
    if not version_dir:
        print(f"ERROR: version not found: {args.version_id}", file=sys.stderr)
        sys.exit(1)

    version_yaml = version_dir / "version.yaml"

    if version_yaml.exists():
        data = load_yaml(version_yaml)
        print(f"Version:       {data.get('version', '?')}")
        print(f"Revision:      {data.get('revision', '?')}")
        print(f"LTS:           {data.get('lts', False)}")
        print(f"FFmpeg ref:    {data.get('ffmpeg_ref', '')}")
        print(f"Release tag:   {data.get('release_tag', '')}")
        print(f"Release ID:    {data.get('release_id', '')}")
        print(f"Release URL:   {data.get('release_url', '')}")
        print(f"Created:       {data.get('created', '')}")
        print(f"Updated:       {data.get('updated', '')}")
        print(f"Variants:      {data.get('variant_count', 0)}/{data.get('total_variants', '?')}")
        print(f"Complete:      {'YES' if data.get('complete', False) else 'NO'}")
        print()
        variants = data.get("variants", [])
        if variants:
            print(f"Variants ({len(variants)}):")
            for v in variants:
                vid = v.get("variant_id", "?")
                url = v.get("download_url", "")
                print(f"  {vid}")
                if url:
                    print(f"    URL: {url}")
        else:
            print("No variants listed in version.yaml.")
    else:
        # Read individual variant files
        variant_files = sorted(version_dir.glob("variants/*.yaml"))
        if not variant_files:
            print(f"No variants found in {version_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"Version directory: {version_dir}")
        print(f"Variants ({len(variant_files)}):")
        for vf in variant_files:
            v = load_yaml(vf)
            vid = v.get("variant_id", vf.stem)
            url = v.get("download_url", "")
            print(f"  {vid}")
            if url:
                print(f"    URL: {url}")


# ---------------------------------------------------------------------------
# Subcommand: merge
# ---------------------------------------------------------------------------

def cmd_merge(args: argparse.Namespace) -> None:
    """Merge individual variant files into a version.yaml."""
    version_dir = resolve_version_dir(args.version_id)
    if not version_dir:
        print(f"ERROR: version not found: {args.version_id}", file=sys.stderr)
        sys.exit(1)

    variant_files = sorted(version_dir.glob("variants/*.yaml"))
    if not variant_files:
        print(f"ERROR: no variant files found in {version_dir / 'variants'}", file=sys.stderr)
        sys.exit(1)

    # Load all variants
    all_variants = [load_yaml(vf) for vf in variant_files]

    # Extract common metadata from first variant
    first = all_variants[0]
    version = first.get("version", "")
    revision = first.get("revision")
    lts = first.get("lts", False)
    ffmpeg_ref = first.get("ffmpeg_ref", "")

    # Determine major and version_id from path
    major = version_dir.parent.name
    version_id = version_dir.name

    # Derive metadata from version_id if variant files don't have them
    # (migrated variants from old YAML format may not include these fields)
    if not version or not ffmpeg_ref:
        # Unified format: "{ffmpeg_ref}-r{revision}"
        if "-r" in version_id:
            parts = version_id.split("-r")
            derived_ffmpeg_ref = parts[0]  # "n8.1.1" or "n8.2-dev-1-gabc1234"
            derived_revision = int(parts[1]) if parts[1].isdigit() else None
            derived_version = derived_ffmpeg_ref.removeprefix("n")
            # Strip git describe suffix for version: "8.1.1-1234-gabc" → "8.1.1"
            derived_version = derived_version.split("-")[0] if "-" in derived_version else derived_version
            derived_lts = False
            try:
                ver_parts = derived_version.split(".")
                major_num = int(ver_parts[0])
                minor_num = int(ver_parts[1])
                derived_lts = is_lts(major_num, minor_num)
            except (IndexError, ValueError):
                pass

            if not version:
                version = derived_version
            if revision is None:
                revision = derived_revision
            if not ffmpeg_ref:
                ffmpeg_ref = derived_ffmpeg_ref
            if not lts:
                lts = derived_lts

    release_tag = f"ffmpeg-{version_id}"
    release_url = make_release_url(release_tag)

    # Preserve existing release_id, created, and lts if version.yaml exists
    existing_release_id = None
    existing_created = None
    existing_lts = None
    version_yaml_path = version_dir / "version.yaml"
    if version_yaml_path.exists():
        existing_data = load_yaml(version_yaml_path)
        existing_release_id = existing_data.get("release_id")
        existing_created = existing_data.get("created")
        existing_lts = existing_data.get("lts")

    # Override lts with existing value if present (it may have been manually
    # set and differ from the formula-based derivation above).
    if existing_lts is not None:
        lts = existing_lts

    merged = {
        "version": version,
        "revision": revision,
        "lts": lts,
        "schema_version": SCHEMA_VERSION,
        "ffmpeg_ref": ffmpeg_ref,
        "release_tag": release_tag,
        "release_id": existing_release_id,
        "release_url": release_url,
        "created": existing_created or now_iso(),
        "updated": now_iso(),
        "variant_count": len(all_variants),
        "total_variants": TOTAL_VARIANTS,
        "complete": is_variant_complete(len(all_variants)),
        "variants": all_variants,
    }

    write_yaml_atomic(merged, version_yaml_path)
    print(f"MERGED {version_yaml_path} ({len(all_variants)} variants)")


# ---------------------------------------------------------------------------
# Subcommand: validate
# ---------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> None:
    """Validate all data files in the database."""
    errors: list[str] = []

    if not DATA_DIR.is_dir():
        print("No data directory found.")
        return

    # Required fields for variant files
    variant_required = {"variant_id", "arch", "triplet", "linkage", "license", "download_url"}

    for major_dir in sorted(DATA_DIR.iterdir()):
        if not major_dir.is_dir():
            continue
        for version_dir in sorted(major_dir.iterdir()):
            if not version_dir.is_dir():
                continue

            # Check version.yaml if it exists
            version_yaml = version_dir / "version.yaml"
            if version_yaml.exists():
                try:
                    vdata = load_yaml(version_yaml)
                except Exception as exc:
                    errors.append(f"{version_yaml}: parse error — {exc}")
                    continue

                if "schema_version" not in vdata:
                    errors.append(f"{version_yaml}: missing 'schema_version'")

                variants_list = vdata.get("variants", [])
                actual_count = len(variants_list)
                declared_count = vdata.get("variant_count", 0)
                if declared_count != actual_count:
                    errors.append(
                        f"{version_yaml}: declared variant_count={declared_count} "
                        f"but has {actual_count} variants"
                    )

                # Validate each variant entry within version.yaml
                for i, var in enumerate(variants_list):
                    for field in variant_required:
                        if field not in var:
                            errors.append(
                                f"{version_yaml}: variant[{i}] missing '{field}'"
                            )

            # Check individual variant files
            variants_dir = version_dir / "variants"
            if variants_dir.is_dir():
                for vf in sorted(variants_dir.glob("*.yaml")):
                    try:
                        var_data = load_yaml(vf)
                    except Exception as exc:
                        errors.append(f"{vf}: parse error — {exc}")
                        continue

                    if not isinstance(var_data, dict):
                        errors.append(f"{vf}: not a dict")
                        continue

                    for field in variant_required:
                        if field not in var_data:
                            errors.append(f"{vf}: missing '{field}'")

    if errors:
        print(f"Found {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("All data files valid.")


# ---------------------------------------------------------------------------
# Subcommand: remove
# ---------------------------------------------------------------------------

def cmd_remove(args: argparse.Namespace) -> None:
    """Remove a variant file from the database."""
    try:
        info = parse_variant_id(args.variant_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    variant_path = (
        DATA_DIR / info["major"] / info["version_id"] / "variants"
        / f"{info['variant_key']}.yaml"
    )

    if not variant_path.exists():
        print(f"ERROR: variant not found: {variant_path}", file=sys.stderr)
        sys.exit(1)

    variant_path.unlink()
    print(f"REMOVED {variant_path}")

    # If variants directory is now empty, delete it and version.yaml
    variants_dir = variant_path.parent
    if variants_dir.is_dir() and not any(variants_dir.iterdir()):
        version_yaml = variants_dir.parent / "version.yaml"
        if version_yaml.exists():
            version_yaml.unlink()
            print(f"  Removed {version_yaml}")
        variants_dir.rmdir()
        print(f"  Removed {variants_dir}")

        # If version directory is now empty, delete it
        version_dir = variants_dir.parent
        if version_dir.is_dir() and not any(version_dir.iterdir()):
            version_dir.rmdir()
            print(f"  Removed {version_dir}")


# ---------------------------------------------------------------------------
# Subcommand: migrate
# ---------------------------------------------------------------------------

def cmd_migrate(args: argparse.Namespace) -> None:
    """Migrate old data structure (one big YAML per version) to the new
    folder structure (one directory per version with individual variant files
    and a version.yaml).
    """
    if not DATA_DIR.is_dir():
        print("No data directory found.")
        return

    # Scan all major directories
    for major_dir in sorted(DATA_DIR.iterdir()):
        if not major_dir.is_dir():
            continue

        # Skip directories that look like version dirs already (contain "variants")
        # We only process YAML files at the major level
        for old_file in sorted(major_dir.glob("ffmpeg-*.yaml")):
            if old_file.name == "build-index.yaml":
                continue

            # Check if already migrated
            # Old file pattern: ffmpeg-{version_id}.yaml (e.g., ffmpeg-8.1.1-r2.yaml)
            # or ffmpeg-{ffmpeg_ref}.yaml for master (e.g., ffmpeg-n8.2-dev-1-gabc1234.yaml)
            file_stem = old_file.stem  # e.g., "ffmpeg-8.1.1-r2"
            version_id = file_stem[len("ffmpeg-"):]  # e.g., "8.1.1-r2"

            target_version_dir = major_dir / version_id
            if target_version_dir.is_dir():
                print(f"SKIPPED (already migrated): {old_file} → {target_version_dir}/")
                continue

            # Load old YAML
            try:
                old_data = load_yaml(old_file)
            except Exception as exc:
                print(f"ERROR: failed to load {old_file}: {exc}", file=sys.stderr)
                continue

            if not isinstance(old_data, dict):
                print(f"ERROR: {old_file} is not a dict", file=sys.stderr)
                continue

            version = old_data.get("version", "")
            is_master = version == "master"

            if is_master:
                ffmpeg_ref = old_data.get("ffmpeg_ref", version_id)
                version_id = ffmpeg_ref
                major_name = "master"
                target_version_dir = DATA_DIR / "master" / version_id
            else:
                major_name = major_dir.name

            # Skip if already migrated (double-check with new path)
            if target_version_dir.is_dir():
                print(f"SKIPPED (already migrated): {old_file}")
                continue

            # Extract variants from old data
            old_variants = old_data.get("variants", [])
            if not old_variants:
                print(f"WARNING: no variants in {old_file}, skipping")
                continue

            # Create version directory and variants subdirectory
            variants_dir = target_version_dir / "variants"
            variants_dir.mkdir(parents=True, exist_ok=True)

            # Write each variant as an individual file
            for v in old_variants:
                # Determine variant_key
                v_triplet = v.get("triplet", "")
                v_linkage = v.get("linkage", "")
                v_license = v.get("license", "")
                variant_key = f"{v_triplet}-{v_linkage}-{v_license}"
                variant_path = variants_dir / f"{variant_key}.yaml"

                # The variant file should include the variant_id if present in old data
                # Old format may not have variant_id, so compute it
                if "variant_id" not in v:
                    v["variant_id"] = f"ffmpeg-{version_id}-{variant_key}"

                write_yaml_atomic(v, variant_path)

            # Build and write version.yaml (same as merge output)
            revision = old_data.get("revision")
            lts = old_data.get("lts", False)
            ffmpeg_ref = old_data.get("ffmpeg_ref", "")
            release_tag = old_data.get("release_tag", f"ffmpeg-{version_id}")
            release_id = old_data.get("release_id")
            existing_created = old_data.get("created")
            existing_updated = old_data.get("updated")

            merged = {
                "version": version,
                "revision": revision,
                "lts": lts,
                "schema_version": old_data.get("schema_version", SCHEMA_VERSION),
                "ffmpeg_ref": ffmpeg_ref,
                "release_tag": release_tag,
                "release_id": release_id,
                "release_url": make_release_url(release_tag),
                "created": existing_created or now_iso(),
                "updated": existing_updated or now_iso(),
                "variant_count": len(old_variants),
                "total_variants": old_data.get("total_variants", TOTAL_VARIANTS),
                "complete": old_data.get("complete", is_variant_complete(len(old_variants))),
                "variants": old_variants,
            }

            version_yaml_path = target_version_dir / "version.yaml"
            write_yaml_atomic(merged, version_yaml_path)

            print(f"MIGRATED {old_file} → {target_version_dir}/ ({len(old_variants)} variants)")

            # Delete old file
            old_file.unlink()
            print(f"  Deleted {old_file}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        prog="db",
        description="FFmpeg MSVC data DB manager",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # import
    p = subparsers.add_parser("import", help="Import a .var.yaml file")
    p.add_argument("var_yaml_path", type=str)

    # has
    p = subparsers.add_parser("has", help="Check if a variant exists")
    p.add_argument("variant_id", type=str)

    # list
    p = subparsers.add_parser("list", help="List versions")
    p.add_argument("--major", type=str, default=None)

    # show
    p = subparsers.add_parser("show", help="Show version details")
    p.add_argument("version_id", type=str)

    # merge
    p = subparsers.add_parser("merge", help="Merge variants into version.yaml")
    p.add_argument("version_id", type=str)

    # validate
    subparsers.add_parser("validate", help="Validate all data files")

    # remove
    p = subparsers.add_parser("remove", help="Remove a variant")
    p.add_argument("variant_id", type=str)

    # migrate
    subparsers.add_parser("migrate", help="Migrate old data structure to new")

    args = parser.parse_args()

    # Dispatch
    if args.command == "import":
        cmd_import(args)
    elif args.command == "has":
        cmd_has(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "migrate":
        cmd_migrate(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
