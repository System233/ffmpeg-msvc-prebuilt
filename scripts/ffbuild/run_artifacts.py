"""Recover only artifacts produced by successful jobs of one immutable plan."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .autoheal import github
from .autoheal.models import commit_sha


def attempts(run_id: int, current: int, first: int = 1):
    if not 1 <= first <= current <= 100:
        raise ValueError("Invalid run attempt range")
    repo = github.repository()
    for number in range(first, current + 1):
        base = f"repos/{repo}/actions/runs/{run_id}/attempts/{number}"
        info = github.api(base)
        jobs = github.collection(base + "/jobs", "jobs")
        if int(info.get("run_attempt", number)) != number:
            raise ValueError("Attempt identity differs")
        yield number, info, [j for j in jobs if int(j.get("run_attempt", number)) == number]


def plan_artifact(run_id: int, current: int, artifacts: list[dict],
                  *, expected: int | None = None) -> tuple[int, dict, list] | None:
    """A newer plan job invalidates every artifact from its predecessor."""
    history = list(attempts(run_id, current))
    producers = [(n, j) for n, _, jobs in history for j in jobs
                 if j.get("name", "").split(" / ")[-1] == "plan"]
    if not producers:
        return None
    number, producer = producers[-1]
    if producer.get("conclusion") != "success" or (expected is not None and expected != number):
        return None
    matches = [a for a in artifacts if a.get("name") == f"ffbuild-plan-a{number}" and not a.get("expired")]
    if len(matches) != 1:
        return None
    if str(matches[0].get("created_at", "")) < str(producer.get("started_at", "")):
        return None
    return number, matches[0], history


def effective_workers(history: list, first: int, rows: list[dict]) -> dict:
    """Latest execution of each exact matrix job, within the selected plan."""
    result = {}
    ids = {r["id"] for r in rows}
    for number, _, jobs in history:
        if number < first:
            continue
        seen = set()
        for job in jobs:
            name = job.get("name", "").split(" / ")[-1]
            if not name.startswith("ffbuild-") or name[8:] not in ids:
                continue
            variant = name[8:]
            if variant in seen:
                raise ValueError("Ambiguous matrix worker job")
            seen.add(variant)
            result[variant] = (number, job)
    return result


def select_artifacts(rows: list[dict], history: list, first: int,
                     artifacts: list[dict]) -> dict[str, str]:
    selected = {}
    workers = effective_workers(history, first, rows)
    if len(workers) != len(rows):
        raise ValueError("Incomplete matrix worker history")
    for row in rows:
        variant = row["id"]
        number, job = workers[variant]
        if job.get("conclusion") != "success":
            raise ValueError(f"Latest worker is not successful: {variant}")
        name = f"{variant}-a{number}"
        matches = [a for a in artifacts if a.get("name") == name and not a.get("expired")]
        if len(matches) != 1 or str(matches[0].get("created_at", "")) < str(job.get("started_at", "")):
            raise ValueError(f"Missing successful worker artifact: {name}")
        selected[variant] = name
    return selected


def collect_release(plan_attempt: int, dest: Path, plan_path: Path) -> None:
    run_id = int(os.environ["GITHUB_RUN_ID"])
    current = int(os.environ["GITHUB_RUN_ATTEMPT"])
    sha = commit_sha(os.environ["GITHUB_SHA"])
    repo = github.repository()
    listing = github.collection(f"repos/{repo}/actions/runs/{run_id}/artifacts", "artifacts")
    selected = plan_artifact(run_id, current, listing, expected=plan_attempt)
    if selected is None:
        raise ValueError("No successful plan for this build generation")
    number, artifact, history = selected
    with TemporaryDirectory(prefix="ffbuild-plan-") as tmp:
        path = Path(tmp)
        github.download_artifact(run_id, artifact["name"], path)
        file = path / "ffbuild-plan.json"
        if not file.is_file() or file.stat().st_size > 8_000_000:
            raise ValueError("Missing or oversized plan")
        plan = json.loads(file.read_text(encoding="utf-8-sig"))
        request = plan.get("request") or {}
        if (plan.get("schema") != 3 or request.get("plan_attempt") != number
                or request.get("repository_commit") != sha or request.get("production") is not True):
            raise ValueError("Plan differs from this production source and attempt")
        rows = plan["jobs"]
        names = select_artifacts(rows, history, number, listing)
        if dest.exists() and any(dest.iterdir()):
            raise ValueError("Artifact destination must be empty")
        dest.mkdir(parents=True, exist_ok=True)
        for variant, name in names.items():
            with TemporaryDirectory(prefix="ffbuild-worker-") as scratch:
                folder = Path(scratch)
                github.download_artifact(run_id, name, folder)
                if not (folder / (variant + ".var.yaml")).is_file():
                    raise ValueError("Worker artifact differs from planned identity")
                for src in folder.iterdir():
                    if not src.is_file() or src.is_symlink() or not (src.name.endswith(".zip") or src.name.endswith(".var.yaml")):
                        raise ValueError("Unexpected worker artifact layout")
                    target = dest / src.name
                    if target.exists():
                        raise ValueError("Overlapping worker assets")
                    shutil.move(str(src), str(target))
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-attempt", required=True, type=int)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--plan", type=Path, default=Path("ffbuild-plan.json"))
    args = parser.parse_args()
    collect_release(args.plan_attempt, args.artifacts, args.plan)


if __name__ == "__main__":
    main()
