#!/usr/bin/env python3
"""Commit staged changes and push to a data branch with retry logic.

Extracted from the "Commit and push data branch" steps found in:

* ``.github/workflows/build-release.yml``
* ``.github/workflows/retention-cleanup.yml``

Both workflows run ``git add -A`` in a ``data/`` checkout directory,
commit if there are staged changes, and push with up to 3 retries.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time


def git_add_all(directory: str) -> None:
    """Stage all changes (git add -A) in *directory*."""
    subprocess.run(
        ["git", "add", "-A"],
        cwd=directory,
        check=True,
    )


def has_staged_changes(directory: str) -> bool:
    """Return ``True`` if the working tree in *directory* has staged changes."""
    result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=directory,
    )
    # exit code 0  → no differences  → False
    # exit code 1  → differences     → True
    # exit code >1 → error
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    # Unexpected error — let subprocess raise
    result.check_returncode()
    return False  # unreachable


def git_commit(directory: str, message: str) -> None:
    """Commit staged changes with *message* in *directory*."""
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=directory,
        check=True,
    )


def git_push(directory: str, branch: str, max_retries: int, delay: float) -> None:
    """Push *branch* from *directory* with retry logic.

    Each attempt runs ``git pull --rebase origin {branch}`` followed by
    ``git push origin {branch}``.  Up to *max_retries* attempts are made,
    waiting *delay* seconds between retries.
    """
    for attempt in range(1, max_retries + 1):
        try:
            subprocess.run(
                ["git", "pull", "--rebase", "origin", branch],
                cwd=directory,
                check=True,
            )
            subprocess.run(
                ["git", "push", "origin", branch],
                cwd=directory,
                check=True,
            )
            print(f"Pushed to {branch!r} on attempt {attempt}")
            return
        except subprocess.CalledProcessError:
            if attempt < max_retries:
                print(
                    f"Push attempt {attempt} failed, retrying in {delay:.0f}s..."
                )
                time.sleep(delay)
            else:
                raise

    # Should not be reached, but guard against edge cases
    print(
        f"ERROR: failed to push after {max_retries} attempts",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage, commit, and push changes on a data branch."
    )
    parser.add_argument(
        "--message",
        required=True,
        help="Commit message to use.",
    )
    parser.add_argument(
        "--directory",
        default="data",
        help="Working directory for git operations (default: %(default)s).",
    )
    parser.add_argument(
        "--branch",
        default="data",
        help="Target branch to push to (default: %(default)s).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum push retry attempts (default: %(default)s).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Seconds to wait between retries (default: %(default)s).",
    )
    args = parser.parse_args()

    directory: str = args.directory
    branch: str = args.branch
    message: str = args.message
    max_retries: int = args.max_retries
    delay: float = args.delay

    # 1. Stage all changes
    print("Staging changes (git add -A)...")
    git_add_all(directory)

    # 3. Bail out early if nothing to commit
    if not has_staged_changes(directory):
        print("No changes to commit on data branch.")
        sys.exit(0)

    # 4. Commit
    print(f"Committing with message: {message!r}...")
    git_commit(directory, message)

    # 5. Push with retry
    print(f"Pushing to {branch!r} (max {max_retries} attempt(s))...")
    try:
        git_push(directory, branch, max_retries, delay=delay)
    except subprocess.CalledProcessError:
        print(
            f"ERROR: failed to push after {max_retries} attempts",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
