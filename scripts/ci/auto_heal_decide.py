#!/usr/bin/env python3
"""
Decide the auto-heal strategy for a failed CI workflow run.

Examines the failure context (PR build, release/master build, or manual
workflow dispatch) and determines the appropriate action:

* ``push`` — push a fix commit directly to the PR branch.
* ``pr``   — create a new PR with a (possibly bumped) revision.

The decision is printed as a single JSON object to stdout.

Usage as CLI:

    python scripts/ci/auto_heal_decide.py \\
        --run-id 12345 \\
        --pr-number 42

    python scripts/ci/auto_heal_decide.py \\
        --run-id 12345 \\
        --yaml 8.1.1

    python scripts/ci/auto_heal_decide.py \\
        --run-id 12345 \\
        --yaml master \\
        --ref n8.0-1234-gabc \\
        --base-ref main

Environment variables:

* ``GITHUB_REPOSITORY`` — ``owner/repo`` (required).
* ``GITHUB_TOKEN`` or ``GH_TOKEN`` — passed through to ``gh`` CLI for
  authenticated API calls.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Direct import of naming helpers — same single source of truth used by
# scan_variants.py, apply_fix.py, and manage_release.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ops.naming import major_version, make_version_dir

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── GitHub / Git helpers ─────────────────────────────────────────────────────


def gh_api(endpoint: str) -> dict:
    """Call ``gh api`` and return the parsed JSON response."""
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {endpoint} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def gh_pr_list_state(head_branch: str) -> str:
    """Return the state string of the first PR whose head is *head_branch*.

    Returns an empty string when no matching PR is found.
    """
    result = subprocess.run(
        [
            "gh", "pr", "list",
            "--head", head_branch,
            "--json", "state",
            "-q", ".[0].state",
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh pr list --head {head_branch} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def git_remote_branch_exists(branch: str) -> bool:
    """Return ``True`` if *branch* exists on origin."""
    result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-remote --heads origin {branch} failed: {result.stderr.strip()}"
        )
    return bool(result.stdout.strip())


def gh_has_open_fix_pr(yaml_name: str) -> bool:
    """Return ``True`` if an OPEN auto-heal PR exists for *yaml_name*.

    Identifies the PR by label ``ffmpeg-{yaml_name}`` — decoupled from
    branch naming and PR title.
    """
    owner, repo = get_owner_repo()
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues?labels=ffmpeg-{yaml_name}&state=open",
            "--jq", "map(select(.pull_request != null)) | length",
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh api label search failed: {result.stderr.strip()}"
        )
    return int(result.stdout.strip() or "0") > 0


def data_version_published(version: str, revision: int) -> bool:
    """Check if ``version.yaml`` exists on the ``data`` branch for a version+revision.

    ``version`` is the **resolved** version string (``ref || yaml_name``),
    the same value that ``scan_variants.py`` passes to ``naming.py``.

    Uses ``gh api --method HEAD`` — single HTTP HEAD, no body download.
    """
    owner, repo = get_owner_repo()
    major = major_version(version)
    ver_dir = make_version_dir(version=version, revision=revision)
    path = f"{major}/{ver_dir}/version.yaml"

    result = subprocess.run(
        ["gh", "api", "--method", "HEAD",
         f"repos/{owner}/{repo}/contents/{path}?ref=data"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    return result.returncode == 0


# ── YAML helpers ─────────────────────────────────────────────────────────────


def read_yaml_revision(yaml_name: str) -> int | None:
    """Extract the ``revision`` field from ``ffmpeg/{yaml_name}.yaml``.

    Returns ``None`` when the file does not exist or has no revision field.
    """
    yaml_path = REPO_ROOT / "ffmpeg" / f"{yaml_name}.yaml"
    if not yaml_path.exists():
        return None
    content = yaml_path.read_text(encoding="utf-8")
    m = re.search(r"^revision:\s*(\d+)", content, re.MULTILINE)
    return int(m.group(1)) if m else None


# ── Environment ──────────────────────────────────────────────────────────────


def get_owner_repo() -> tuple[str, str]:
    """Parse ``GITHUB_REPOSITORY`` into ``(owner, repo)``."""
    repo_full = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo_full:
        raise RuntimeError(
            "GITHUB_REPOSITORY is not set or invalid (expected owner/repo)"
        )
    parts = repo_full.split("/", 1)
    return parts[0], parts[1]


# ── Core decision logic ──────────────────────────────────────────────────────


def decide(args: argparse.Namespace) -> dict:
    """Run the decision logic and return a dict of outputs."""
    owner, repo = get_owner_repo()
    run_id: str = args.run_id
    yaml_name: str | None = args.yaml
    ref: str | None = args.ref
    pr_number: str | None = args.pr_number
    base_ref: str = args.base_ref or "main"

    skip = "false"
    action = ""
    branch = ""
    checkout_ref = ""
    bump_revision = "false"
    pr_author = ""
    base_sha = ""
    head_sha = ""
    head_ref = ""
    rev = None

    if pr_number:
        # ── PR Build failure ────────────────────────────────────────────
        pr = gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}")
        action = "push"
        branch = pr["head"]["ref"]
        checkout_ref = branch
        pr_author = pr["user"]["login"]
        base_sha = pr["base"]["sha"]
        base_ref = pr["base"]["ref"]
        head_sha = pr["head"]["sha"]
        head_ref = pr["head"]["ref"]

    elif yaml_name:
        # ── Release / Master failure ────────────────────────────────────
        rev = read_yaml_revision(yaml_name)
        if rev is not None:
            # Resolved version = ref (for snapshot/master) or yaml_name
            resolved_version = ref if ref else yaml_name
            if data_version_published(resolved_version, rev):
                branch = f"fix/ffmpeg-{yaml_name}-r{rev + 1}"
                bump_revision = "true"
            else:
                branch = f"fix/ffmpeg-{yaml_name}-r{rev}"
                bump_revision = "false"
        else:
            branch = f"fix/ffmpeg-{yaml_name}"
            bump_revision = "false"

        action = "pr"
        checkout_ref = "main"
        base_ref = base_ref or "main"

        if gh_has_open_fix_pr(yaml_name):
            skip = "true"

    else:
        # ── workflow_dispatch ───────────────────────────────────────────
        run = gh_api(f"repos/{owner}/{repo}/actions/runs/{run_id}")
        pull_requests = run.get("pull_requests", [])
        if not pull_requests:
            print(
                f"error: Workflow run {run_id} has no associated PR",
                file=sys.stderr,
            )
            sys.exit(1)

        pr_number = str(pull_requests[0].get("number", ""))
        pr = gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}")
        action = "push"
        branch = pr["head"]["ref"]
        checkout_ref = branch
        pr_author = pr["user"]["login"]
        base_sha = pr["base"]["sha"]
        base_ref = pr["base"]["ref"]
        head_sha = pr["head"]["sha"]
        head_ref = pr["head"]["ref"]

    return {
        "skip": skip,
        "action": action,
        "branch": branch,
        "checkout_ref": checkout_ref,
        "bump_revision": bump_revision,
        "run_id": run_id,
        "pr_number": pr_number or "",
        "pr_author": pr_author,
        "base_sha": base_sha,
        "base_ref": base_ref,
        "head_sha": head_sha,
        "head_ref": head_ref,
        "base_revision": str(rev) if rev is not None else "",
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decide the auto-heal strategy for a failed CI workflow run.",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="The workflow run ID.",
    )
    parser.add_argument(
        "--yaml",
        default=None,
        help="YAML name (without extension) for release/master failures.",
    )
    parser.add_argument(
        "--pr-number",
        default=None,
        help="The PR number for PR build failures.",
    )
    parser.add_argument(
        "--ref",
        default=None,
        help="Git ref for snapshot/master builds (e.g. n8.0-1234-gabc).",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Base ref for the fix branch (default: main).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = decide(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
