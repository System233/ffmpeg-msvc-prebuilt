"""Read-only GitHub evidence acquisition; write credentials stay in delivery jobs."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def repository() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo.count("/") != 1 or any(not part for part in repo.split("/")):
        raise ValueError("GITHUB_REPOSITORY must identify owner/name")
    return repo


def api(path: str, *, method: str = "GET", fields: dict[str, str] | None = None) -> Any:
    if not path.startswith("repos/") or any(c in path for c in "\n\r"):
        raise ValueError("Expected a repository-relative GitHub API resource")
    args = ["gh", "api", path, "--method", method]
    for key, value in (fields or {}).items():
        args.extend(["-f", f"{key}={value}"])
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"GitHub API {path} failed: {result.stderr[-800:]}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def collection(endpoint: str, key: str, *, limit: int = 2000) -> list[dict]:
    output: list[dict] = []
    for page in range(1, 1 + (limit + 99) // 100):
        separator = "&" if "?" in endpoint else "?"
        payload = api(f"{endpoint}{separator}per_page=100&page={page}")
        rows = payload.get(key, []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError(f"Invalid GitHub {key} collection")
        output.extend(rows)
        if len(output) > limit:
            raise ValueError(f"GitHub {key} exceeds maximum page budget")
        if len(rows) < 100:
            return output
    raise ValueError(f"GitHub {key} pagination exhausted")


def run_data(run_id: int, attempt: int | None = None) -> tuple[dict, int, list[dict], list[dict]]:
    repo = repository()
    run = api(f"repos/{repo}/actions/runs/{run_id}")
    if run.get("repository", {}).get("full_name", repo).lower() != repo.lower():
        raise ValueError("Run does not belong to configured repository")
    actual_attempt = int(run.get("run_attempt", 0))
    attempt = actual_attempt if attempt is None else attempt
    if attempt < 1 or attempt > actual_attempt:
        raise ValueError("Unrecognized run attempt")
    if run.get("status") != "completed":
        raise ValueError("Build has not completed")
    jobs = collection(f"repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs")
    artifacts = collection(f"repos/{repo}/actions/runs/{run_id}/artifacts", "artifacts")
    return run, attempt, jobs, artifacts


def download_artifact(run_id: int, name: str, directory: Path) -> None:
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ValueError("Invalid artifact name")
    directory.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["gh", "run", "download", str(run_id), "--repo", repository(),
         "--name", name, "--dir", str(directory)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(f"Could not download {name}: {result.stderr[-800:]}")


def pr_for_run(run: dict) -> dict | None:
    numbers = [entry.get("number") for entry in run.get("pull_requests", [])]
    if len(numbers) != 1 or type(numbers[0]) is not int:
        return None
    return api(f"repos/{repository()}/pulls/{numbers[0]}")


def has_trusted_pr(pr: dict | None) -> bool:
    if not pr:
        return True
    repo = repository().lower()
    if (pr.get("head", {}).get("repo") or {}).get("full_name", "").lower() != repo:
        return False
    # Only the repository's dedicated bot branches enter automated repair.
    return (pr.get("user", {}).get("login") == "ffmpeg-dev[bot]"
            and str(pr.get("head", {}).get("ref", "")).startswith("autoheal/")
            and pr.get("base", {}).get("ref") == "main")
