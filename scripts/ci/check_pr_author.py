#!/usr/bin/env python3
"""Check whether a PR author is authorized to trigger auto-heal workflows.

Replicates the inline JS logic from .github/workflows/auto-heal.yml.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

BOT_USERS = {"github-actions[bot]", "ffmpeg-dev[bot]"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify PR author is a bot or a collaborator with admin/write access."
    )
    parser.add_argument(
        "--author",
        required=True,
        help="PR author username (e.g. 'octocat')",
    )
    args = parser.parse_args()

    author: str = args.author

    # 1. Bot users are always authorized
    if author in BOT_USERS:
        print(f"Authorized: {author} (project automation bot)")
        sys.exit(0)

    # 2. Resolve owner/repo from environment
    repo_full = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo_full or "/" not in repo_full:
        print(
            "Error: GITHUB_REPOSITORY environment variable is not set or invalid.",
            file=sys.stderr,
        )
        sys.exit(1)

    owner, repo = repo_full.split("/", 1)

    # 3. Call GitHub API via gh CLI
    endpoint = f"/repos/{owner}/{repo}/collaborators/{author}/permission"
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
    )

    # 4. Any API error → unauthorized (404 = not a collaborator, other = infrastructure issue)
    if result.returncode != 0:
        print(
            f"PR author \"{author}\" is not authorized. "
            "Auto-heal is restricted to maintainers and bot users.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 5. Parse JSON response
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(
            f"Failed to parse gh api output as JSON:\n{result.stdout}",
            file=sys.stderr,
        )
        sys.exit(1)

    permission: str = data.get("permission", "")

    # 6. Check permission level
    if permission in ("admin", "write"):
        print(f"Authorized: {author} ({permission} access)")
        sys.exit(0)
    else:
        print(
            f'PR author "{author}" has {permission} access. '
            "Only collaborators with admin/write permission or bot users are allowed.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
