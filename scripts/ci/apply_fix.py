#!/usr/bin/env python3
"""Apply a patch and push / create PR for auto-heal.

Ported from ``scripts/ci/apply_fix.sh``.

Two subcommand-style modes controlled by the ``--action`` argument:

* ``pr``   -- create a new PR from the fix branch and enable auto-merge.
* ``push`` -- push directly to the target branch and update the existing
             PR (when ``--pr-number`` is set).

The script always runs the "apply patch" phase first, followed by the
push/pr phase.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, Sequence

RE_REVISION = re.compile(r"^(revision:\s*)(\d+)", re.MULTILINE)

from _allowed import find_violations


# ---------------------------------------------------------------------------
# Phase 1: apply patch
# ---------------------------------------------------------------------------


def _make_body(body_path: Path | None, run_id: str) -> str:
    """Read body from file (if exists) and append run_id footer."""
    content = body_path.read_text(encoding="utf-8") if body_path and body_path.is_file() else ""
    footer = f"\n---\nTriggered by auto-heal run: #{run_id}"
    return content + footer


def _apply_patch(
    patch_dir: str,
    bot_user_name: str,
    bot_user_id: str,
    gh_token: str,
    github_repository: str,
) -> None:
    """Find and apply the first ``.patch`` file, validate scope.

    Exits with code 0 when no patches are found.
    Exits with code 1 on git-am failures or scope violations.
    """
    patch_dir_path = Path(patch_dir)
    patches: list[Path] = (
        sorted(patch_dir_path.glob("*.patch")) if patch_dir_path.is_dir() else []
    )
    if not patches:
        print(f"No patch found in {patch_dir}/. Agent made no changes.")
        sys.exit(0)

    patch_file = patches[0]
    print(f"==> Applying patch: {patch_file}")

    # -- set origin with token --
    subprocess.run(
        ["git", "remote", "set-url", "origin", f"https://x-access-token:{gh_token}@github.com/{github_repository}"],
        capture_output=True,
        text=True,
    )

    # -- apply the patch --
    result = subprocess.run(["git", "am", str(patch_file)])
    if result.returncode != 0:
        print("::error::git am failed", file=sys.stderr)
        sys.exit(1)

    # -- validate scope: only ffmpeg/*.yaml, patches/*.patch, .opencode/ --
    result = subprocess.run(
        ["git", "diff", "HEAD~1..HEAD", "--name-only"],
        capture_output=True,
        text=True,
    )
    changed_files = [f for f in result.stdout.strip().split("\n") if f]
    violations = find_violations(changed_files)

    if violations:
        print("::error::Agent modified files outside allowed scope:")
        for f in violations:
            print(f)
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True)
        sys.exit(1)

    print("All modified files are within allowed scope.")


# ---------------------------------------------------------------------------
# Phase 2: push / create PR
# ---------------------------------------------------------------------------


def _bump_revision(yaml_name: str, base_revision: str) -> None:
    """Bump the revision field based on *base_revision* (value from base branch).

    Reads the YAML file from the working tree and sets its revision to
    ``base_revision + 1`` regardless of what the agent may have left in the
    file.
    """
    if not base_revision:
        print("::warning::No base revision provided; skipping revision bump")
        return

    yaml_path = Path(f"ffmpeg/{yaml_name}.yaml")
    if not yaml_path.exists():
        print(
            f"::warning::YAML file not found at {yaml_path}; skipping revision bump"
        )
        return

    base_rev = int(base_revision)
    new_rev = base_rev + 1

    content = yaml_path.read_text(encoding="utf-8")
    new_content = RE_REVISION.sub(
        lambda match: f"{match.group(1)}{new_rev}", content, count=1
    )
    yaml_path.write_text(new_content, encoding="utf-8")

    if content == new_content:
        print("Revision unchanged (already at base_revision + 1); skipping commit")
        return

    print(f"Bumped revision: {base_rev} -> {new_rev}")

    subprocess.run(["git", "add", str(yaml_path)], check=True)
    subprocess.run(["git", "commit", "-m", f"fix({yaml_name}): bump revision to {new_rev}"], check=True)


def _push_and_pr(
    action: str,
    branch: str,
    yaml_name: str,
    bump_revision_flag: bool,
    base_revision: str,
    pr_number: str,
    fix_report_dir: str,
    github_repository: str,
    run_id: str,
) -> None:
    """Push changes and handle PR creation/update."""
    # -- extract commit message --
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s", "HEAD"],
        capture_output=True,
        text=True,
    )
    agent_title = result.stdout.strip().replace("\n", " ") if result.returncode == 0 else ""

    # -- bump revision (optional) --
    if bump_revision_flag and yaml_name:
        _bump_revision(yaml_name, base_revision)

    # -- rebase onto latest main before push (push mode only) --
    if action == "push":
        print("==> Rebasing onto latest main before push (action=push)")
        subprocess.run(["git", "fetch", "origin"])
        subprocess.run(["git", "pull", "--rebase", "origin", "main"])

    # -- push to branch --
    print(f"==> Pushing to origin HEAD:{branch}")
    subprocess.run(["git", "push", "--force-with-lease", "origin", f"HEAD:{branch}"], check=True)

    # -- PR operations --
    if action == "pr":
        _create_pr(agent_title, yaml_name, branch, fix_report_dir, github_repository, run_id)
    elif action == "push" and pr_number:
        _edit_pr(agent_title, pr_number, fix_report_dir, github_repository, run_id)


def _create_pr(
    agent_title: str,
    yaml_name: str,
    branch: str,
    fix_report_dir: str,
    github_repository: str,
    run_id: str,
) -> None:
    """Create a new PR and enable auto-merge."""
    print("==> Creating PR")

    if not agent_title:
        agent_title = f"fix({yaml_name}): auto-fix build failure"

    body_file = Path(fix_report_dir) / "fix_report.md"
    body = _make_body(body_file, run_id)
    cmd = [
        "gh",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        branch,
        "--title",
        agent_title,
        "--repo",
        github_repository,
        "--body",
        body,
        "--label",
        f"ffmpeg-{yaml_name}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"::error::gh pr create failed:\n{result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    pr_url = result.stdout.strip()

    # Extract PR number from the URL (last numeric segment)
    m = re.search(r"(\d+)$", pr_url)
    if m:
        created_pr_number = m.group(1)
        print(f"==> Enabling auto-merge on PR #{created_pr_number}")
        subprocess.run(
            ["gh", "pr", "merge", created_pr_number, "--auto", "--squash"],
        )
    else:
        print(
            f"::warning::Could not determine PR number from '{pr_url}'; "
            "auto-merge not enabled"
        )


def _edit_pr(
    agent_title: str,
    pr_number: str,
    fix_report_dir: str,
    github_repository: str,
    run_id: str,
) -> None:
    """Update an existing PR's title and body."""
    print(f"==> Updating existing PR #{pr_number}")

    body_file = Path(fix_report_dir) / "fix_report.md"
    body = _make_body(body_file, run_id)
    cmd = [
        "gh",
        "pr",
        "edit",
        pr_number,
        "--title",
        agent_title or "",
        "--repo",
        github_repository,
        "--body",
        body,
    ]

    subprocess.run(cmd)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _die(msg: str) -> NoReturn:
    """Print *msg* to stderr and exit 1."""
    print(msg, file=sys.stderr)
    sys.exit(1)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply patch + push / create PR for auto-heal."
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["pr", "push"],
        help="Operation mode: 'pr' to create a new PR, 'push' to push directly.",
    )
    parser.add_argument("--branch", required=True, help="Target branch name.")
    parser.add_argument(
        "--bot-user-id", required=True, help="Bot GitHub user ID (used in email)."
    )
    parser.add_argument(
        "--yaml",
        default="",
        help="YAML name for title / bump fallback (e.g. '8.1.1').",
    )
    parser.add_argument(
        "--bump-revision",
        default=False,
        action="store_true",
        help="Bump revision after applying patch.",
    )
    parser.add_argument(
        "--base-revision",
        default="",
        help="Base revision to bump from (required when --bump-revision is set).",
    )
    parser.add_argument(
        "--pr-number",
        default="",
        help="Existing PR number to update (used with --action=push).",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Auto-heal workflow run ID (appended to PR body for traceability).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)

    # -- required environment variables --
    gh_token = os.environ.get("GH_TOKEN", "")
    if not gh_token:
        _die("GH_TOKEN is required")

    github_repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not github_repository:
        _die("GITHUB_REPOSITORY is required")

    # -- optional environment variables with defaults --
    bot_user_name = os.environ.get("BOT_USER_NAME", "ffmpeg-dev[bot]")
    patch_dir = os.environ.get("PATCH_DIR", "patch-input")
    fix_report_dir = os.environ.get("FIX_REPORT_DIR", "fix-report")

    # -- Phase 1: apply patch --
    _apply_patch(
        patch_dir=patch_dir,
        bot_user_name=bot_user_name,
        bot_user_id=args.bot_user_id,
        gh_token=gh_token,
        github_repository=github_repository,
    )

    # -- Phase 2: push / PR --
    _push_and_pr(
        action=args.action,
        branch=args.branch,
        yaml_name=args.yaml,
        bump_revision_flag=args.bump_revision,
        base_revision=args.base_revision,
        pr_number=args.pr_number,
        fix_report_dir=fix_report_dir,
        github_repository=github_repository,
        run_id=args.run_id,
    )


if __name__ == "__main__":
    main()
