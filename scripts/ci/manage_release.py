#!/usr/bin/env python3
"""Manage GitHub Releases for FFmpeg MSVC prebuilt artifacts.

Extracted from ``.github/workflows/build-release.yml`` ("Determine release tag"
and "Create or append GitHub Release" steps).

Usage::

    python scripts/ci/manage_release.py tag --artifacts-dir ./artifacts
    python scripts/ci/manage_release.py create --tag ffmpeg-8.1.1-r2 --artifacts-dir ./artifacts
    python scripts/ci/manage_release.py create --tag ffmpeg-8.1.1-r2 --artifacts-dir ./artifacts \\
        --title "FFmpeg 8.1.1 (MSVC Prebuilt)" --ref "n8.0-1234-gabc"
"""

from __future__ import annotations

import argparse

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence


# ---------------------------------------------------------------------------
# Tag determination
# ---------------------------------------------------------------------------


def _find_naming_py() -> str:
    """Resolve the absolute path to ``scripts/ops/naming.py`` relative to this file."""
    this_dir = Path(__file__).resolve().parent  # scripts/ci/
    return str(this_dir.parent / "ops" / "naming.py")


def determine_tag(artifacts_dir: Path) -> Optional[str]:
    """Find the first ``*.var.yaml`` in *artifacts_dir* and extract the release tag.

    Returns the tag string ``ffmpeg-{version}``, or ``None`` if no ``.var.yaml``
    files exist.
    """
    var_files = sorted(str(p) for p in artifacts_dir.glob("*.var.yaml"))
    if not var_files:
        return None

    var_file = var_files[0]
    naming_py = _find_naming_py()
    result = subprocess.run(
        [sys.executable, naming_py, "var-version", var_file],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"Error running naming.py var-version: {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)

    version = result.stdout.strip()
    if not version:
        print("Error: no version extracted from var file", file=sys.stderr)
        sys.exit(1)

    return f"ffmpeg-{version}"


# ---------------------------------------------------------------------------
# Release create / upload
# ---------------------------------------------------------------------------


def _build_title(value: str, *, is_snapshot: bool) -> str:
    """Build the release title from a version/ref string."""
    if is_snapshot:
        return f"FFmpeg {value} (MSVC Prebuilt, Snapshot)"
    return f"FFmpeg {value} (MSVC Prebuilt)"


def _build_notes(value: str) -> str:
    """Build the release body / notes."""
    return f"Automated build of FFmpeg {value} using MSVC via vcpkg."


def _check_token() -> None:
    """Ensure ``GITHUB_TOKEN`` or ``GH_TOKEN`` is available."""
    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        print(
            "Error: GITHUB_TOKEN or GH_TOKEN environment variable is required",
            file=sys.stderr,
        )
        sys.exit(1)


def create_or_upload(
    tag: str,
    artifacts_dir: Path,
    title: Optional[str] = None,
    ref: Optional[str] = None,
    yaml_val: Optional[str] = None,
) -> None:
    """Create a new GitHub Release or upload assets to an existing one.

    Parameters
    ----------
    tag:
        Release tag (e.g. ``ffmpeg-8.1.1-r2``).
    artifacts_dir:
        Directory containing ``*.zip`` artifacts.
    title:
        Explicit release title.  When omitted a title is auto-generated from
        *ref* or *yaml_val*.
    ref:
        Git ref (e.g. ``n8.0-1234-gabc``).  When present the title includes
        ``(MSVC Prebuilt, Snapshot)``.
    yaml_val:
        YAML version string (e.g. ``8.1.1``).  Used when *ref* is not provided.
    """
    _check_token()

    # Locate zip artifacts
    zips = sorted(str(p) for p in artifacts_dir.glob("*.zip"))
    if not zips:
        print("No zip artifacts found -- skipping release step")
        return

    # Determine the ref/yaml string used for title and notes
    value = ref or yaml_val or ""
    is_snapshot = ref is not None and ref != ""

    # Build title if not explicitly provided
    if title is None:
        title = _build_title(value, is_snapshot=is_snapshot)

    notes = _build_notes(value)

    env = os.environ.copy()

    # Check whether the release already exists
    check = subprocess.run(
        ["gh", "release", "view", tag, "--json", "id"],
        capture_output=True,
        text=True,
        env=env,
    )

    if check.returncode == 0:
        print(f"Release {tag} already exists -- uploading additional assets")
        result = subprocess.run(
            ["gh", "release", "upload", tag, *zips, "--clobber"],
            env=env,
        )
        if result.returncode != 0:
            print("Error uploading assets", file=sys.stderr)
            sys.exit(result.returncode)
    else:
        print(f"Creating release {tag}")
        result = subprocess.run(
            [
                "gh", "release", "create", tag, *zips,
                "--title", title,
                "--notes", notes,
            ],
            env=env,
        )
        if result.returncode != 0:
            print("Error creating release", file=sys.stderr)
            sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage GitHub Releases for FFmpeg MSVC prebuilt artifacts."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- tag ---
    p_tag = sub.add_parser("tag", help="Determine the release tag from *.var.yaml artifacts")
    p_tag.add_argument(
        "--artifacts-dir",
        required=True,
        type=Path,
        help="Path to the artifacts directory",
    )

    # --- create ---
    p_create = sub.add_parser("create", help="Create a GitHub Release or upload assets")
    p_create.add_argument(
        "--tag",
        required=True,
        help="Release tag (e.g. ffmpeg-8.1.1-r2)",
    )
    p_create.add_argument(
        "--artifacts-dir",
        required=True,
        type=Path,
        help="Path to the artifacts directory containing *.zip files",
    )
    p_create.add_argument(
        "--title",
        default=None,
        help="Release title (auto-generated from --ref / --yaml if omitted)",
    )
    p_create.add_argument(
        "--ref",
        default=None,
        help="Git ref (when present, title includes 'Snapshot')",
    )
    p_create.add_argument(
        "--yaml",
        default=None,
        help="YAML version string (used when --ref is not set)",
    )

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.command == "tag":
        tag = determine_tag(args.artifacts_dir)
        if tag:
            print(tag)
        # If no var files found, exit 0 silently (consistent with the workflow).

    elif args.command == "create":
        create_or_upload(
            tag=args.tag,
            artifacts_dir=args.artifacts_dir,
            title=args.title,
            ref=args.ref,
            yaml_val=args.yaml,
        )


if __name__ == "__main__":
    main()
