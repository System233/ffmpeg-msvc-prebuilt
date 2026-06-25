#!/usr/bin/env python3
"""OpenCode autonomous agent repair loop.

Runs OpenCode with an agent prompt to autonomously fix CI build failures,
iterating up to --max-retries times. After each attempt, validates that
only allowed files (ffmpeg/*.yaml, patches/*.patch, .opencode/) were modified.
On scope violation, appends feedback and retries. On success, creates a
patch-output/ directory with git format-patch output.

Usage
-----
  export DEEPSEEK_API_KEY="sk-..."
  python scripts/ci/agent_repair.py [--max-retries 3]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import List

from _allowed import find_violations

# ── Feedback generation (bash _generate_feedback equivalent) ──────────────────

def _generate_feedback(attempt: int, violations: List[str], feedback_file: str) -> None:
    """Read FEEDBACK_FILE template, substitute {attempt} and {violations},
    and write feedback.txt."""
    # sed 's/^/- /' equivalent: prefix each violation line with "- "
    formatted = "\n".join(f"- {v}" for v in violations)

    template = Path(feedback_file).read_text(encoding="utf-8")
    content = template.replace("{attempt}", str(attempt)).replace("{violations}", formatted)
    Path("feedback.txt").write_text(content, encoding="utf-8")


# ── Git helpers ───────────────────────────────────────────────────────────────

def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command, return CompletedProcess without checking exit code."""
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _git_check(*args: str) -> str:
    """Run a git command that must succeed; return stripped stdout."""
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


# ── OpenCode execution ────────────────────────────────────────────────────────

def _run_opencode(prompt_text: str) -> int:
    """Run opencode with the given prompt as a single argument.
    Returns the process exit code."""
    result = subprocess.run(
        ["opencode", "run", "--model",
         "deepseek/deepseek-v4-flash",
         "--dangerously-skip-permissions",
         prompt_text],
    )
    return result.returncode


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenCode autonomous agent repair loop",
    )
    parser.add_argument(
        "--action",
        default="pr",
        choices=["pr", "push"],
        help="Operation mode: 'pr' reset to base_sha, 'push' stays on PR HEAD (default: pr)",
    )
    parser.add_argument(
        "--base-sha",
        default=None,
        help="Base commit SHA (default: git rev-parse HEAD)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max repair attempts (default: 3)",
    )
    parser.add_argument(
        "--prompt-file",
        default="scripts/ci/agent_prompt.md",
        help="Path to prompt template (default: scripts/ci/agent_prompt.md)",
    )
    parser.add_argument(
        "--feedback-file",
        default="scripts/ci/agent_feedback.md",
        help="Path to feedback template (default: scripts/ci/agent_feedback.md)",
    )
    args = parser.parse_args()

    # ── Validate DEEPSEEK_API_KEY (bash: ${DEEPSEEK_API_KEY:?...}) ────────────
    if "DEEPSEEK_API_KEY" not in os.environ:
        print("ERROR: DEEPSEEK_API_KEY is required", file=sys.stderr)
        sys.exit(1)

    # ── Validate opencode in PATH (bash: command -v opencode) ──────────────────
    if shutil.which("opencode") is None:
        print("ERROR: opencode not found in PATH", file=sys.stderr)
        sys.exit(1)

    # ── Validate prompt file exists (bash: [ -f "$PROMPT_FILE" ]) ─────────────
    prompt_file = args.prompt_file
    if not Path(prompt_file).is_file():
        print(f"ERROR: PROMPT_FILE not found: {prompt_file}", file=sys.stderr)
        sys.exit(1)

    # ── Validate feedback file exists (bash: [ -f "$FEEDBACK_FILE" ]) ─────────
    feedback_file = args.feedback_file
    if not Path(feedback_file).is_file():
        print(f"ERROR: FEEDBACK_FILE not found: {feedback_file}", file=sys.stderr)
        sys.exit(1)

    # ── Read target_yaml from context (bash: read target_yaml from agent_context.json) ─
    context_path = Path("agent_context.json")
    target_yaml = None
    if context_path.is_file():
        ctx = json.loads(context_path.read_text(encoding="utf-8"))
        target_yaml = ctx.get("target_yaml")
    if target_yaml:
        print(f"Allowed YAML scope: ffmpeg/{target_yaml}.yaml")
    else:
        print("WARNING: target_yaml not found in context, allowing any ffmpeg/*.yaml", file=sys.stderr)

    # ── Resolve BASE_SHA (bash: [ -z "$BASE_SHA" ] && BASE_SHA=$(git rev-parse HEAD)) ─
    base_sha = args.base_sha
    if not base_sha:
        base_sha = _git_check("rev-parse", "HEAD")

    # Determine the start SHA for the agent loop.
    # For push: start from PR branch HEAD to preserve existing commits.
    # For pr:    start from base_sha (main) for a clean base.
    start_sha = _git_check("rev-parse", "HEAD") if args.action == "push" else base_sha

    max_retries: int = args.max_retries

    # ── Initialize prompt from template (bash: cp "$PROMPT_FILE" prompt.txt) ──
    shutil.copy(prompt_file, "prompt.txt")

    # ── Reset SIGINT/SIGTERM to default (lets runner kill process group) ───
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    # ── Main repair loop ──────────────────────────────────────────────────────
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        print(f"=== Agent repair attempt {attempt}/{max_retries} ===")

        # Reset to the loop's start SHA so each attempt begins cleanly.
        _git_check("reset", "--hard", start_sha)

        # If feedback.txt exists, append it to prompt.txt
        # (bash: if [ -f feedback.txt ]; then cat feedback.txt >> prompt.txt; fi)
        if Path("feedback.txt").exists():
            feedback_content = Path("feedback.txt").read_text(encoding="utf-8")
            with open("prompt.txt", "a", encoding="utf-8") as fh:
                fh.write(feedback_content)

        # Run opencode with accumulated prompt (bash: opencode run ... "$(cat prompt.txt)" &)
        prompt_text = Path("prompt.txt").read_text(encoding="utf-8")
        oc_rc = _run_opencode(prompt_text)
        if oc_rc != 0:
            print(f"[WARNING] opencode failed (exit {oc_rc})", file=sys.stderr)
            continue

        # Check if any commits were made (bash: if ! git log --oneline ... | grep -q .)
        log_result = _git("log", "--oneline", f"{start_sha}..HEAD")
        if not log_result.stdout.strip():
            print(f"No changes on attempt {attempt}")
            break

        # Count commits; squash if > 1 (bash: COMMIT_COUNT=$(git rev-list --count ...))
        commit_count_str = _git_check("rev-list", "--count", f"{start_sha}..HEAD")
        commit_count = int(commit_count_str)
        if commit_count > 1:
            print(f"Squashing {commit_count} commits into one")
            # Get latest commit message from the range
            # (bash: MSG=$(git log --format=%s -1 "${BASE_SHA}..HEAD"))
            msg = _git_check("log", "--format=%s", "-1", f"{start_sha}..HEAD")
            _git_check("reset", "--soft", start_sha)
            _git_check("commit", "-m", msg)

        # Generate patch (bash: mkdir -p patch-output; git format-patch -1 HEAD -o patch-output)
        Path("patch-output").mkdir(exist_ok=True)
        _git_check("format-patch", "-1", "HEAD", "-o", "patch-output")

        # (bash: PATCH=$(ls patch-output/*.patch 2>/dev/null | head -1); [ -z "$PATCH" ] && continue)
        patch_files = list(Path("patch-output").glob("*.patch"))
        if not patch_files:
            continue

        # Check for scope violations (bash: git diff HEAD~1..HEAD --name-only | grep -vE ... || true)
        files_output = _git_check("diff", "HEAD~1..HEAD", "--name-only")
        changed_files = [line for line in files_output.splitlines() if line.strip()]
        violations = find_violations(changed_files, yaml=target_yaml)

        if violations:
            print(f"[WARNING] Scope violation on attempt {attempt}:", file=sys.stderr)
            for f in violations:
                print(f"[WARNING]   {f}", file=sys.stderr)

            if attempt < max_retries:
                _generate_feedback(attempt, violations, feedback_file)
                continue
        else:
            print(f"All checks passed on attempt {attempt}")
            break

    # ── Post-loop: check max retry outcome (bash lines 147-160) ──────────────
    if attempt >= max_retries:
        # (bash: if git log --oneline "${BASE_SHA}..HEAD" | grep -q .; then ...)
        log_result = _git("log", "--oneline", f"{start_sha}..HEAD")
        if log_result.stdout.strip():
            # (bash: PATCH=$(ls patch-output/*.patch 2>/dev/null | head -1); [ -n "$PATCH" ] && ...)
            patch_files = list(Path("patch-output").glob("*.patch"))
            if patch_files:
                files_output = _git_check("diff", "HEAD~1..HEAD", "--name-only")
                changed_files = [line for line in files_output.splitlines() if line.strip()]
                violations = find_violations(changed_files, yaml=target_yaml)
                if not violations:
                    sys.exit(0)
        # (bash: echo "[ERROR] Max retries exhausted with violations" >&2; exit 1)
        print("[ERROR] Max retries exhausted with violations", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
