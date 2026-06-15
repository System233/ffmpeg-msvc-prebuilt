#!/usr/bin/env python3
"""
create_version_pr.py — Create a PR for a new FFmpeg version.

Usage:
    python scripts/ci/create_version_pr.py --version 6.5 --closest-yaml 6.1

Steps:
  1. Read ffmpeg/{closest_yaml}.yaml as reference
  2. Copy to ffmpeg/{version}.yaml
  3. Set revision: 0 in the new YAML
  4. Run python scripts/generate.py --version {version} --force
  5. Create git branch ci/ffmpeg-{version}
  6. git add ffmpeg/{version}.yaml and ports/ffmpeg-{dashed}/
  7. git commit -m "feat: add ffmpeg {version}"
  8. Push branch (skip if already exists on remote)
  9. Create PR via gh CLI
  10. Print PR URL to stdout
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result.

    Exits on error unless *check* is False.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or str(REPO_ROOT),
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed: {' '.join(cmd)}", file=sys.stderr)
        print(f"  stderr: {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a PR for a new FFmpeg version.",
    )
    parser.add_argument("--version", required=True, help="Target version (e.g. 6.5)")
    parser.add_argument("--closest-yaml", required=True, help="Closest existing YAML stem (e.g. 6.1)")
    parser.add_argument("--dry-run", action="store_true", help="Skip git push and PR creation")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] No remote changes will be made.")

    version = args.version
    closest_yaml = args.closest_yaml
    dashed = version.replace(".", "-")
    branch = f"ci/ffmpeg-{version}"
    yaml_path = f"ffmpeg/{version}.yaml"
    src_yaml = REPO_ROOT / "ffmpeg" / f"{closest_yaml}.yaml"
    dst_yaml = REPO_ROOT / "ffmpeg" / f"{version}.yaml"

    # ── 1. Check that source YAML exists ─────────────────────────────────────
    if not src_yaml.exists():
        print(f"ERROR: reference YAML not found: {src_yaml}", file=sys.stderr)
        sys.exit(1)

    # ── 2. Check if target YAML already exists ───────────────────────────────
    if dst_yaml.exists():
        print(f"ERROR: target YAML already exists: {dst_yaml}", file=sys.stderr)
        sys.exit(1)

    # ── 3. Check if branch already exists on remote ──────────────────────────
    result = _run(
        ["git", "ls-remote", "--heads", "origin", branch],
        check=False,
    )
    if branch in result.stdout:
        print(f"SKIP: branch '{branch}' already exists on remote", file=sys.stderr)
        sys.exit(1)

    # ── 4. Copy reference YAML ───────────────────────────────────────────────
    _run(["cp", str(src_yaml), str(dst_yaml)])
    print(f"  Copied {src_yaml.name} → {dst_yaml.name}")

    # ── 5. Set revision: 0 ───────────────────────────────────────────────────
    content = dst_yaml.read_text()
    if re.search(r'^revision:', content, re.MULTILINE):
        content = re.sub(r'^revision:.*', 'revision: 0', content, flags=re.MULTILINE)
    else:
        # Add revision: 0 after extends: line
        lines = content.split('\n')
        result_lines = []
        added = False
        for line in lines:
            result_lines.append(line)
            if line.strip().startswith('extends:') and not added:
                result_lines.append('revision: 0')
                added = True
        if not added:
            result_lines.append('revision: 0')
        content = '\n'.join(result_lines)
    dst_yaml.write_text(content + '\n')
    print(f"  Set revision: 0 in {dst_yaml.name}")

    # ── 6. Generate port files ───────────────────────────────────────────────
    print(f"  Running: python scripts/generate.py --version {version} --force")
    _run(
        [sys.executable, "scripts/generate.py", "--version", version, "--force"],
    )
    print("  Port files generated")

    # ── 7. Create git branch ─────────────────────────────────────────────────
    _run(["git", "checkout", "-b", branch])
    print(f"  Created branch: {branch}")

    # ── 8. git add ───────────────────────────────────────────────────────────
    port_dir = f"ports/ffmpeg-{dashed}"
    _run(["git", "add", yaml_path, port_dir])
    print(f"  Added: {yaml_path}, {port_dir}/")

    # ── 9. git commit ────────────────────────────────────────────────────────
    _run(["git", "commit", "-m", f"feat: add ffmpeg {version}"])
    print(f"  Committed: feat: add ffmpeg {version}")

    # ── 10. Push branch ──────────────────────────────────────────────────────
    if not args.dry_run:
        _run(["git", "push", "origin", branch])
        print(f"  Pushed: origin {branch}")

    # ── 11. Create PR ─────────────────────────────────────────────────────────
    title = f"ffmpeg {version}"
    body = f"Auto-generated port for FFmpeg {version}. Please review and merge."

    if args.dry_run:
        print(f"[DRY RUN] Would create PR: {title}")
    else:
        result = _run([
            "gh", "pr", "create",
            "--base", "main",
            "--head", branch,
            "--title", title,
            "--body", body,
        ])
        pr_url = result.stdout.strip()
        print(f"\nPR created: {pr_url}")


if __name__ == "__main__":
    main()
