#!/usr/bin/env python3
"""
sync_from_vcpkg.py - Extract FFmpeg port files from vcpkg git history.

Reads ``D:\\Repos\\vcpkg\\versions\\f-\\ffmpeg.json`` and extracts every unique
FFmpeg version's port files (with the highest *port-version*) into
``_work/extracted/<version>/`` for downstream diff analysis.

Usage
-----
    python scripts/sync_from_vcpkg.py

Requirements
------------
- Python 3.6+ (stdlib only)
- Git on PATH
- Vcpkg repository at ``D:\\Repos\\vcpkg``
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths – tweak these if your layout differs
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACT_DIR = REPO_ROOT / "_work" / "extracted"
GITIGNORE = REPO_ROOT / ".gitignore"


# ---------------------------------------------------------------------------
# Environment checks
# ---------------------------------------------------------------------------

def check_environment(vcpkg_dir: Path, versions_json: Path) -> None:
    """Verify that all prerequisites are met; exit with a message on failure."""
    if not vcpkg_dir.is_dir():
        print(f"ERROR: vcpkg repository not found at {vcpkg_dir}", file=sys.stderr)
        sys.exit(1)

    if not (vcpkg_dir / ".git").is_dir():
        print(f"ERROR: {vcpkg_dir} is not a git repository", file=sys.stderr)
        sys.exit(1)

    if not versions_json.is_file():
        print(f"ERROR: versions database not found at {versions_json}", file=sys.stderr)
        sys.exit(1)

    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: git is not available on the system PATH", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# .gitignore management
# ---------------------------------------------------------------------------

def ensure_gitignore() -> None:
    """Create/update the root ``.gitignore`` so that ``_work/`` is ignored."""
    line = "_work/"
    if GITIGNORE.is_file():
        content = GITIGNORE.read_text(encoding="utf-8")
        if line not in content:
            with open(GITIGNORE, "a", encoding="utf-8") as fh:
                fh.write(f"\n# Build and extracted data\n{line}\n")
            print(f"Updated {GITIGNORE} – added '{line}' entry")
    else:
        GITIGNORE.write_text(f"# Build and extracted data\n{line}\n")
        print(f"Created {GITIGNORE} with '{line}' entry")


# ---------------------------------------------------------------------------
# Version loading
# ---------------------------------------------------------------------------

def load_versions(versions_json: Path) -> Dict[str, dict]:
    """Parse ``ffmpeg.json`` and return unique versions with their best entry.

    For each unique version string (handling both ``version`` and
    ``version-string`` keys) the entry with the highest ``port-version``
    is selected.
    """
    with open(versions_json, encoding="utf-8") as fh:
        data = json.load(fh)

    by_version: Dict[str, list] = defaultdict(list)

    for entry in data["versions"]:
        # Older entries use 'version-string'; newer ones use 'version'.
        ver = entry.get("version") or entry.get("version-string")
        if ver is None:
            continue
        by_version[ver].append(entry)

    # Keep the entry with the largest port-version for each version string.
    result: Dict[str, dict] = {}
    for ver, entries in by_version.items():
        best = max(entries, key=lambda e: e.get("port-version", 0))
        result[ver] = best

    return result


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_version(version: str, entry: dict, vcpkg_dir: Path) -> bool:
    """Use ``git archive`` to extract port files for *version*.

    The tree SHA stored in the vcpkg versions database is passed directly
    to ``git archive``.  The resulting tar is extracted into
    ``_work/extracted/<version>/``.

    Returns ``True`` on success, ``False`` on failure.
    """
    tree_sha = entry["git-tree"]
    dest_dir = EXTRACT_DIR / version
    tar_path = EXTRACT_DIR / f"{version}.tar"

    if dest_dir.is_dir():
        return True  # already present – treat as success

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    # git archive from the vcpkg repository using the tree SHA
    try:
        subprocess.run(
            ["git", "-C", str(vcpkg_dir), "archive", tree_sha,
             "--output", str(tar_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  WARNING: git archive failed for {version} "
              f"(tree: {tree_sha}): {exc.stderr.strip()}")
        tar_path.unlink(missing_ok=True)
        return False

    # Extract the tar archive
    try:
        with tarfile.open(tar_path, "r") as tar:
            tar.extractall(path=dest_dir)
    except (tarfile.TarError, OSError) as exc:
        print(f"  WARNING: failed to extract tar for {version}: {exc}")
        return False
    finally:
        tar_path.unlink(missing_ok=True)

    return True


# ---------------------------------------------------------------------------
# File listing helper
# ---------------------------------------------------------------------------

def list_files(version_dir: Path) -> str:
    """Return a human-readable summary of files inside *version_dir*."""
    if not version_dir.is_dir():
        return "(not extracted)"

    top_files: List[str] = sorted(
        f.name for f in version_dir.iterdir() if f.is_file()
    )
    subdirs: List[str] = sorted(
        d.name for d in version_dir.iterdir() if d.is_dir()
    )

    parts: List[str] = []
    if top_files:
        parts.append(", ".join(top_files))
    for sub in subdirs:
        count = sum(1 for _ in (version_dir / sub).rglob("*") if _.is_file())
        parts.append(f"{sub}/ ({count})")

    return ", ".join(parts) if parts else "(empty)"


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(results: List[Tuple[str, int, str, str, bool]]) -> None:
    """Print a formatted summary table of all extracted versions."""
    header = f"{'Version':<15} {'Port-version':<13} {'Git-tree':<12} Files"
    print(header)
    print("-" * max(len(header), 80))
    for version, pv, sha, files, _ in results:
        print(f"{version:<15} {pv:<13} {sha[:10]:<12} {files}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract FFmpeg port files from vcpkg git history.",
    )
    parser.add_argument(
        "--vcpkg-dir",
        default=None,
        help="Vcpkg repository root (default: $VCPKG_ROOT env var)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    vcpkg_dir_s = args.vcpkg_dir or os.environ.get("VCPKG_ROOT")
    if not vcpkg_dir_s:
        print("ERROR: --vcpkg-dir is required or set $VCPKG_ROOT", file=sys.stderr)
        sys.exit(1)
    vcpkg_dir = Path(vcpkg_dir_s)
    versions_json = vcpkg_dir / "versions" / "f-" / "ffmpeg.json"

    ensure_gitignore()
    check_environment(vcpkg_dir, versions_json)

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    versions = load_versions(versions_json)
    if not versions:
        print("No versions found in the versions database.")
        return

    total = len(versions)
    sorted_versions = sorted(versions.items(), key=lambda kv: kv[0])

    results: List[Tuple[str, int, str, str, bool]] = []
    extracted_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, (version, entry) in enumerate(sorted_versions, start=1):
        dest_dir = EXTRACT_DIR / version
        tree_sha = entry["git-tree"]
        port_version = entry.get("port-version", 0)

        if dest_dir.is_dir():
            print(f"[{idx}/{total}] ffmpeg {version:<12} SKIP (already extracted)")
            skipped_count += 1
            files_summary = list_files(dest_dir)
            results.append((version, port_version, tree_sha, files_summary, True))
            continue

        print(f"[{idx}/{total}] Extracting ffmpeg {version} "
              f"(tree: {tree_sha[:8]}...)...", end=" ", flush=True)

        ok = extract_version(version, entry, vcpkg_dir)
        if ok:
            print("OK")
            extracted_count += 1
        else:
            print("FAILED")
            failed_count += 1

        files_summary = list_files(dest_dir) if ok else "(failed)"
        results.append((version, port_version, tree_sha, files_summary, ok))

    # Summary
    print()
    print_summary(results)
    print()
    print(f"Total: {total} versions "
          f"(extracted: {extracted_count}, skipped: {skipped_count}, "
          f"failed: {failed_count})")


if __name__ == "__main__":
    main()
