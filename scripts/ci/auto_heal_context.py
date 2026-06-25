#!/usr/bin/env python3
"""
Generate agent context JSON for the auto-heal workflow.

Replaces the inline ``actions/github-script`` step in ``auto-heal.yml``
with a local Python CLI so the step can be run without requiring the
GitHub Script action.

Usage
-----
    python scripts/ci/auto_heal_context.py --run-id 12345678

    python scripts/ci/auto_heal_context.py \\
        --run-id 12345678 \\
        --pr-number 42 \\
        --base-sha abc123 \\
        --base-ref main \\
        --head-branch feature/foo \\
        --head-sha def456 \\
        --trigger schedule

Outputs
-------
``agent_context.json``        Workflow-run metadata as JSON.
``failed_steps_hint.txt``     Newline-separated list of failed job names.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────────────────────

def _gh_api(owner: str, repo: str, run_id: int, token: str | None) -> dict:
    """Call ``gh api`` to list workflow-run jobs and return parsed JSON."""
    endpoint = f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token

    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        print(f"gh api failed (exit {result.returncode}): {result.stderr}",
              file=sys.stderr)
        sys.exit(result.returncode)

    return json.loads(result.stdout)


def _git_diff_patches(base_sha: str) -> list[str]:
    """Return new files added under ``patches/`` since *base_sha*."""
    result = subprocess.run(
        [
            "git", "diff", "--name-only", "--diff-filter=A",
            f"{base_sha}..HEAD", "--", "patches/",
        ],
        capture_output=True,
        text=True,
    )
    # Non-zero exit may mean no matching files; treat as empty.
    if result.returncode != 0:
        return []
    output = result.stdout.strip()
    return output.split("\n") if output else []


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate auto-heal agent context from a workflow run.",
    )
    parser.add_argument(
        "--run-id", type=int, required=True,
        help="GitHub Actions workflow run ID",
    )
    parser.add_argument(
        "--pr-number", type=str, default="",
        help="Pull request number (optional)",
    )
    parser.add_argument(
        "--base-sha", type=str, default="",
        help="Base commit SHA for patch detection diff",
    )
    parser.add_argument(
        "--base-ref", type=str, default="",
        help="Base branch ref (e.g. main)",
    )
    parser.add_argument(
        "--head-branch", type=str, default="",
        help="Head branch name (e.g. feature/foo)",
    )
    parser.add_argument(
        "--head-sha", type=str, default="",
        help="Head commit SHA",
    )
    parser.add_argument(
        "--trigger", type=str, default="call",
        help="Trigger event name (default: %(default)s)",
    )
    parser.add_argument(
        "--log-dir", type=str, default="./error_logs",
        help="Log directory path written into the context record (default: %(default)s)",
    )
    parser.add_argument(
        "--output", type=str, default="agent_context.json",
        help="Path for the generated context JSON file (default: %(default)s)",
    )
    args = parser.parse_args()

    # ── Resolve owner / repo from environment ────────────────────────────
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in gh_repo:
        print("GITHUB_REPOSITORY env var not set or invalid (expected owner/repo)",
              file=sys.stderr)
        sys.exit(1)
    owner, repo = gh_repo.split("/", 1)

    # ── Resolve token ────────────────────────────────────────────────────
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    # ── 1. Fetch workflow-run jobs ───────────────────────────────────────
    jobs_payload = _gh_api(owner, repo, args.run_id, token)

    failed_job_names: list[str] = []
    if "jobs" in jobs_payload:
        for job in jobs_payload["jobs"]:
            if job.get("conclusion") == "failure":
                failed_job_names.append(job.get("name", ""))

    # ── 2. Write hint file (always in cwd, matching the original JS) ─────
    hint_rel = "./failed_steps_hint.txt"
    Path("failed_steps_hint.txt").write_text(
        "\n".join(failed_job_names), encoding="utf-8",
    )
    print(f"Failed jobs written to {hint_rel}")

    # ── 3. Discover new patches ──────────────────────────────────────────
    new_patches: list[str] = []
    if args.base_sha:
        new_patches = _git_diff_patches(args.base_sha)
        if new_patches:
            print(f"New patches detected: {new_patches}")
        else:
            print("No new patches detected.")

    # ── 4. Build context payload ─────────────────────────────────────────
    context = {
        "pr_number": int(args.pr_number) if args.pr_number else None,
        "base_branch": args.base_ref,
        "base_sha": args.base_sha,
        "head_branch": args.head_branch,
        "head_sha": args.head_sha,
        "workflow_run_id": args.run_id,
        "workflow_url": (
            f"https://github.com/{owner}/{repo}/actions/runs/{args.run_id}"
        ),
        "failed_jobs": failed_job_names,
        "new_patches": new_patches,
        "log_directory": args.log_dir,
        "hint_file": hint_rel,
        "trigger": args.trigger,
    }

    # ── 5. Write context JSON ────────────────────────────────────────────
    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(context, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Agent context written to {output_path}")


if __name__ == "__main__":
    main()
