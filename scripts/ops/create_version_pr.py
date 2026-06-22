#!/usr/bin/env python3
"""
create_version_pr.py — Create a PR for a new FFmpeg version.

Usage:
    python scripts/ops/create_version_pr.py --version 6.5 --closest-yaml 6.1

Steps:
   1. Read ffmpeg/{closest_yaml}.yaml as reference
   2. Copy to ffmpeg/{version}.yaml
   3. Set revision: 0 in the new YAML
   4. Compute sha512 from upstream tarball, write to YAML
   5. Run ffport.py generate to create port files
   6. Create git branch auto/ffmpeg-{version}
   7. git add + commit
   8. Push branch (skip if already exists on remote)
   9. Create PR via gh CLI with auto-merge enabled
"""

import argparse
import hashlib
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = "https://github.com/FFmpeg/FFmpeg"


def _run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or str(REPO_ROOT),
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: {' '.join(cmd)} failed", file=sys.stderr)
        print(f"  stderr: {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def compute_sha512(version: str) -> str:
    """Download upstream tarball for n{version} and compute SHA-512."""
    tag = f"n{version}"
    url = f"{UPSTREAM}/archive/{tag}.tar.gz"
    print(f"  Downloading {url} ...")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            if resp.status != 200:
                print(f"ERROR: HTTP {resp.status} for {url}", file=sys.stderr)
                sys.exit(1)
            h = hashlib.sha512()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except Exception as exc:
        print(f"ERROR: failed to download {url}: {exc}", file=sys.stderr)
        sys.exit(1)
    return h.hexdigest()


def set_source_sha512_yaml(path: Path, sha512: str) -> None:
    """Parse YAML, set source.sha512, write back preserving structure."""
    data = yaml.safe_load(path.read_text())
    if "source" not in data:
        data["source"] = {}
    data["source"]["sha512"] = sha512
    # 用 master.yaml 做模板时，修正 source 区为 release 格式
    if data["source"].get("ref") == "${FFMPEG_REF}":
        data["source"]["ref"] = "n${VERSION}"
        data["source"].pop("head_ref", None)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)
    print(f"  Set source.sha512 in {path.name}")


def set_revision_yaml(path: Path, revision: str = "0") -> None:
    """Set or replace revision field in a YAML file using regex (format-safe)."""
    content = path.read_text()
    pat = re.compile(r"^revision:.*", re.MULTILINE)
    if pat.search(content):
        content = pat.sub(f"revision: {revision}", content)
    else:
        content = re.sub(
            r"(^extends:.*)",
            rf"\1\nrevision: {revision}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    path.write_text(content + "\n", encoding="utf-8")
    print(f"  Set revision: {revision} in {path.name}")


def _create_pr(branch: str, version: str) -> None:
    """Create a PR for the given branch and enable auto-merge."""
    title = f"ffmpeg {version}"
    body = f"Auto-generated port for FFmpeg {version}. Please review and merge."
    result = _run([
        "gh", "pr", "create",
        "--base", "main",
        "--head", branch,
        "--title", title,
        "--body", body,
    ])
    pr_url = result.stdout.strip()
    pr_number = pr_url.rstrip("/").split("/")[-1]
    print(f"\nPR created: {pr_url}")
    merge_result = _run(
        ["gh", "pr", "merge", pr_number, "--auto", "--squash"],
        check=False,
    )
    if merge_result.returncode != 0:
        print(f"  WARNING: auto-merge not enabled for this repository ({merge_result.stderr.strip()})")
    else:
        print(f"  Auto-merge enabled for #{pr_number}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a PR for a new FFmpeg version.",
    )
    parser.add_argument("--version", required=True, help="Target version (e.g. 6.5)")
    parser.add_argument("--closest-yaml", required=True, help="Closest existing YAML stem (e.g. 6.1)")
    parser.add_argument("--sha512", default=None, help="Pre-computed SHA-512 (skip download)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] No remote changes will be made.")

    original_branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

    version = args.version
    closest_yaml = args.closest_yaml
    branch = f"auto/ffmpeg-{version}"
    yaml_path = f"ffmpeg/{version}.yaml"
    src_yaml = REPO_ROOT / "ffmpeg" / f"{closest_yaml}.yaml"
    dst_yaml = REPO_ROOT / "ffmpeg" / f"{version}.yaml"

    if not src_yaml.exists():
        print(f"ERROR: reference YAML not found: {src_yaml}", file=sys.stderr)
        sys.exit(1)

    if dst_yaml.exists():
        print(f"ERROR: target YAML already exists: {dst_yaml}", file=sys.stderr)
        sys.exit(1)

    result = _run(["git", "ls-remote", "--heads", "origin", branch], check=False)
    if any(f"refs/heads/{branch}" in line for line in result.stdout.splitlines()):
        pr_result = _run(["gh", "pr", "list", "--head", branch, "--json", "number", "-q", ".[0].number"], check=False)
        existing_pr = pr_result.stdout.strip()
        if existing_pr:
            print(f"SKIP: PR #{existing_pr} already exists for branch '{branch}'")
        else:
            print(f"Branch '{branch}' exists but no PR found — creating PR from existing branch")
            if not args.dry_run:
                _create_pr(branch, version)
        sys.exit(0)

    _run(["cp", str(src_yaml), str(dst_yaml)])
    print(f"  Copied {src_yaml.name} -> {dst_yaml.name}")

    set_revision_yaml(dst_yaml, "0")

    sha512 = args.sha512 or compute_sha512(version)
    print(f"  sha512: {sha512}")
    set_source_sha512_yaml(dst_yaml, sha512)

    print(f"  Running: python scripts/ffport.py generate {version}")
    _run([sys.executable, "scripts/ffport.py", "generate", version])
    print("  Port files generated")

    _run(["git", "checkout", "-b", branch])
    print(f"  Created branch: {branch}")

    _run(["git", "add", yaml_path])
    print(f"  Added: {yaml_path} and ports/")

    _run(["git", "commit", "-m", f"feat: add ffmpeg {version}"])
    print(f"  Committed: feat: add ffmpeg {version}")

    if not args.dry_run:
        _run(["git", "push", "origin", branch])
        print(f"  Pushed: origin {branch}")

    _run(["git", "checkout", original_branch])
    print(f"  Restored branch: {original_branch}")

    if args.dry_run:
        print(f"[DRY RUN] Would create PR: ffmpeg {version}")
    else:
        _create_pr(branch, version)


if __name__ == "__main__":
    main()
