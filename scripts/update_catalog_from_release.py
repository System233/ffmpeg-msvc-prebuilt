#!/usr/bin/env python3
# DEPRECATED: Replaced by VitePress SSG site. See web/ directory.
"""
update_catalog_from_release.py - Parse a GitHub release event and update catalog.json.

Reads the release event payload from $GITHUB_EVENT_PATH, iterates over all
release assets whose filename matches the expected pattern, and calls
``scripts/update_catalog.py`` for each matching asset.

Intended to be run from a GitHub Actions workflow triggered by
``release: [published]``.

Requires: Python 3 stdlib only (no pip installs).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Filename pattern
# ---------------------------------------------------------------------------
#   ffmpeg-<version>-<triplet>-<linkage>-<license>.zip
#   e.g. ffmpeg-8.1.1-x64-windows-mixed-shared-gpl.zip
PATTERN = re.compile(
    r"ffmpeg-(\d+\.\d+\.\d+)-(.+?)-(shared|static)-(lgpl|gpl|nonfree)\.zip"
)


def main() -> None:
    # ---- Read GitHub event ----
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("ERROR: GITHUB_EVENT_PATH not set", file=sys.stderr)
        sys.exit(1)

    event = json.loads(Path(event_path).read_text())
    assets = event.get("release", {}).get("assets", [])
    release_url = event.get("release", {}).get("html_url", "")
    tag = event.get("release", {}).get("tag_name", "")

    if not assets:
        print("No assets found in release event.")
        sys.exit(0)

    print(f"Processing {len(assets)} asset(s) from release {tag}...")

    # ---- Parse each asset ----
    matched_count = 0
    for asset in assets:
        name = asset["name"]
        match = PATTERN.match(name)
        if not match:
            print(f"  SKIP {name} (doesn't match pattern)")
            continue

        version = match.group(1)
        triplet = match.group(2)
        linkage = match.group(3)
        license_ = match.group(4)

        # Extract arch from triplet (first segment before '-')
        # e.g. x64-windows-mixed → x64, arm64-windows-mixed → arm64
        arch = triplet.split("-")[0]

        size = asset["size"]
        download_url = asset["browser_download_url"]

        print(f"  Processing: {name}")
        print(f"    version:     {version}")
        print(f"    arch:        {arch}")
        print(f"    triplet:     {triplet}")
        print(f"    linkage:     {linkage}")
        print(f"    license:     {license_}")
        print(f"    size:        {size}")
        print(f"    download:    {download_url}")

        # Call update_catalog.py as a subprocess
        cmd = [
            "python", "scripts/update_catalog.py",
            "--version", version,
            "--arch", arch,
            "--triplet", triplet,
            "--license", license_,
            "--linkage", linkage,
            "--size", str(size),
            "--release-url", release_url,
            "--download-url", download_url,
            "--digest", asset.get("digest", ""),
        ]
        subprocess.run(cmd, check=True)
        print(f"  OK: {name}")
        matched_count += 1

    print(f"Matched {matched_count} / {len(assets)} asset(s).")

    if matched_count == 0:
        print("Nothing to update.")
        sys.exit(0)

    # ---- Commit and push catalog.json ----
    print("Committing and pushing catalog.json...")
    subprocess.run(
        ["git", "config", "user.name", "github-actions[bot]"],
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", "catalog.json"], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Update catalog for {tag}"],
        check=False,  # Allow empty commit (no changes)
    )
    subprocess.run(
        ["git", "push"],
        check=False,  # Allow failure if nothing to push
    )
    print("Done.")


if __name__ == "__main__":
    main()
