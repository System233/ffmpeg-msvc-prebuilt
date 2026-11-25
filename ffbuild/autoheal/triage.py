"""Correlate GitHub workflow evidence with native FFmpeg build identities."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import github
from .ledger import branch_name, branch_matches
from .models import commit_sha, version_name
from .policy import classify

BUILD_WORKFLOWS = {"Build All FFmpeg Versions", "Build FFmpeg Release", "Build FFmpeg Master"}


def _artifact_names(artifacts: list[dict]) -> set[str]:
    return {item["name"] for item in artifacts if isinstance(item.get("name"), str)
            and not item.get("expired")}


def _matching_job(job: dict, planned: list[dict]) -> dict | None:
    """Match a deliberately explicit matrix job name; never guess by triplet."""
    name = str(job.get("name", ""))
    matches = [row for row in planned
               if re.search(r"(?<![A-Za-z0-9_-])ffbuild-" + re.escape(row["id"])
                            + r"(?![A-Za-z0-9_-])", name)]
    if len(matches) > 1:
        raise ValueError("Ambiguous FFmpeg matrix job identity")
    return matches[0] if matches else None


def _sample_log(run_id: int, artifact: str) -> str:
    with tempfile.TemporaryDirectory(prefix="autoheal-log-") as temporary:
        directory = Path(temporary)
        github.download_artifact(run_id, artifact, directory)
        fragments = []
        remaining = 200_000
        # Read only bounded build evidence; never execute anything in an artifact.
        candidates = sorted((p for p in directory.rglob("*") if p.is_file()),
                            key=lambda p: ("ffmpeg" not in p.name.lower(), p.as_posix()))
        for path in candidates:
            if path.suffix.lower() not in (".log", ".err", ".txt"):
                continue
            if not path.resolve().is_relative_to(directory.resolve()):
                continue
            with path.open("rb") as inp:
                size = path.stat().st_size
                inp.seek(max(0, size - min(remaining, 50000)))
                data = inp.read(min(remaining, 50000))
            remaining -= len(data)
            fragments.append(data.decode("utf-8", errors="replace"))
            if remaining <= 0:
                break
        return "\n".join(fragments)


def _signature(phase: str, classification: str, log: str, step: str) -> str:
    # Stable across equivalent variants, paths and numerical job identifiers.
    lines = [s.strip()[:250] for s in log.splitlines()
             if re.search(r"\berror\b|\bfatal\b|unresolved|undefined|failed", s, re.I)]
    diagnostic = "\n".join(lines[:12]) or step
    diagnostic = re.sub(r"\b[0-9a-f]{16,}\b", "<hex>", diagnostic, flags=re.I)
    diagnostic = re.sub(r"(?<![A-Za-z])\d{5,}(?![A-Za-z])", "<id>", diagnostic)
    return hashlib.sha256(f"{phase}\0{classification}\0{diagnostic}".encode()).hexdigest()


def _plan_from_artifact(run_id: int, attempt: int,
                        artifacts: list[dict], attempt_started: str) -> dict | None:
    plan_name = f"ffbuild-plan-a{attempt}"
    plans = [a for a in artifacts if a.get("name") == plan_name and not a.get("expired")]
    # Old attempt's plan can accidentally be mistaken for a current attempt's.
    plans = [p for p in plans if str(p.get("created_at", "")) >= attempt_started]
    if len(plans) != 1:
        return None
    with tempfile.TemporaryDirectory(prefix="autoheal-plan-") as temporary:
        directory = Path(temporary)
        github.download_artifact(run_id, plan_name, directory)
        file = directory / "ffbuild-plan.json"
        if not file.is_file() or file.stat().st_size > 8_000_000:
            raise ValueError("Missing or oversized ffbuild-plan.json")
        data = json.loads(file.read_text(encoding="utf-8"))
        if data.get("schema") != 3 or not isinstance(data.get("jobs"), list):
            raise ValueError("Unsupported native ABI plan")
        for row in data["jobs"]:
            if not isinstance(row, dict):
                raise ValueError("Invalid planned FFmpeg build")
            version_name(row.get("yaml"))
            if not all(row.get(k) for k in ("id", "abi_hash", "triplet", "package", "port")):
                raise ValueError("Incomplete planned ABI identity")
        return data


def analyze(run: dict, attempt: int, jobs: list[dict], artifacts: list[dict],
            plan: dict | None, *, logs: dict[str, str] | None = None) -> dict:
    """Pure analysis of already-fetched evidence; logs keyed by artifact name."""
    if run.get("name") not in BUILD_WORKFLOWS:
        raise ValueError("Not an allowlisted FFmpeg build workflow")
    commit_sha(run.get("head_sha"))
    available = _artifact_names(artifacts)
    planned = plan["jobs"] if plan is not None else []
    by_yaml: dict[str, list[dict]] = defaultdict(list)
    diagnostics: list[dict] = []
    log_overrides = logs or {}
    for job in jobs:
        if job.get("conclusion") not in ("failure", "timed_out"):
            continue
        plan_row = _matching_job(job, planned)
        if plan_row is None:
            phase, reason, _ = classify(job, "")
            diagnostics.append({"job_id": job.get("id"), "job_name": job.get("name"),
                                "phase": phase if phase != "unknown" else "shared_or_unknown",
                                "classification": reason, "repairable": False,
                                "failed_steps": [s.get("name") for s in job.get("steps", [])
                                                 if s.get("conclusion") == "failure"]})
            continue
        artifact = f"build-logs-a{attempt}-{plan_row['yaml']}-{plan_row['id']}"
        log_text = log_overrides.get(artifact, "")
        phase, reason, repairable = classify(job, log_text)
        if job.get("conclusion") == "timed_out":
            phase, reason, repairable = "environment", "timeout", False
        failed_steps = [step.get("name", "") for step in job.get("steps", [])
                        if step.get("conclusion") in ("failure", "timed_out")]
        entry = {
            "job_id": job["id"], "variant_id": plan_row["id"],
            "triplet": plan_row["triplet"], "abi_hash": plan_row["abi_hash"],
            "artifact": artifact if artifact in available else "",
            "failed_steps": failed_steps, "phase": phase,
            "classification": reason, "repairable": repairable and artifact in available,
            "signature": _signature(phase, reason, log_text, "; ".join(failed_steps)),
            "diagnostic": "\n".join(log_text.splitlines()[-20:])[-2000:],
        }
        by_yaml[plan_row["yaml"]].append(entry)
    groups = []
    for yaml_name, units in sorted(by_yaml.items()):
        # A single version has only one auto-repair task: mixed / ambiguous
        # failures must be diagnosed rather than repaired speculatively.
        fixable = all(unit["repairable"] for unit in units)
        phases = {unit["phase"] for unit in units}
        reasons = {unit["classification"] for unit in units}
        signatures = {unit["signature"] for unit in units}
        # A version may fail in several unrelated variants. Do not let one
        # deterministic branch key accidentally represent different root causes.
        signatures_match = len(signatures) == 1
        signature = hashlib.sha256(
            (yaml_name + "\0" + "\0".join(sorted(signatures))).encode()).hexdigest()
        groups.append({
            "yaml": yaml_name,
            "phase": next(iter(phases)) if len(phases) == 1 else "mixed",
            "classification": ("divergent_source_errors" if not signatures_match and
                               reasons == {"source_patch"} else
                               next(iter(reasons)) if len(reasons) == 1 else "mixed"),
            "repairable": (fixable and signatures_match and phases == {"build"}
                           and reasons == {"source_patch"}),
            "signature": signature,
            "jobs": units,
        })
    return {
        "schema": 1,
        "source": {"run_id": int(run["id"]), "run_attempt": attempt,
                   "head_sha": run["head_sha"], "event": run.get("event", ""),
                   "run_name": run["name"], "run_conclusion": run.get("conclusion"),
                   "head_branch": run.get("head_branch", ""),
                   "url": run.get("html_url", "")},
        "groups": groups, "diagnostics": diagnostics,
        "plan_available": plan is not None,
        "planned_variants": len(planned),
    }


def production_request(run: dict, plan: dict | None) -> dict | None:
    """Bind a main-branch production run to its exact plan and source pin."""
    from ..identity import date_suffix
    from ..release_trigger import snapshot
    event = run.get("event")
    if (run.get("head_branch") != "main" or
            (run.get("name"), event) not in {
                ("Build FFmpeg Release", "workflow_dispatch"),
                ("Build FFmpeg Master", "schedule")} or not plan):
        return None
    request = plan.get("request")
    if not isinstance(request, dict) or request.get("production") is not True:
        return None
    try:
        version = version_name(request["yaml"])
        if event == "schedule" and version != "master":
            return None
        if commit_sha(request["repository_commit"]) != commit_sha(run["head_sha"]):
            return None
        date_suffix(request["date"])
        rows = [*plan["jobs"], *(r["job"] for r in plan.get("reuse", []))]
        if not rows or any(r["yaml"] != version or r["release_date"] != request["date"] for r in rows):
            return None
        if version == "master":
            pin = snapshot({k: request[k] for k in ("ref", "commit", "sha512")})
            if any((r.get("ref"), r.get("source_ref"), r.get("sha512")) !=
                   (pin["ref"], pin["commit"], pin["sha512"]) for r in rows):
                return None
        return request
    except (ValueError, KeyError, TypeError):
        return None


def retry_plan_bound_to_run(request: dict, run: dict, generation: int) -> bool:
    """PR CI checks a merge commit; API run head identifies the PR branch."""
    if request.get("plan_attempt") != generation:
        return False
    try:
        commit_sha(request["repository_commit"])
        if run.get("event") == "pull_request":
            commit_sha(request["pr_base"])
            return commit_sha(request["pr_head"]) == commit_sha(run["head_sha"])
        return commit_sha(request["repository_commit"]) == commit_sha(run["head_sha"])
    except (ValueError, KeyError, TypeError):
        return False


def triage_run(run_id: int, attempt: int | None = None) -> dict:
    run, attempt, jobs, artifacts = github.run_data(run_id, attempt)
    repo = github.repository()
    current = github.api(f"repos/{repo}/actions/runs/{run_id}/attempts/{attempt}")
    started = current.get("run_started_at")
    if not isinstance(started, str) or not started:
        raise ValueError("Cannot establish run attempt artifact provenance")
    plan = _plan_from_artifact(run_id, attempt, artifacts, started)
    if plan is None and attempt > 1 and run.get("event") in ("workflow_dispatch", "schedule", "pull_request"):
        from ..run_artifacts import plan_artifact
        selected = plan_artifact(run_id, attempt, artifacts)
        if selected and selected[0] < attempt:
            generation, artifact, history = selected
            start = next(info["run_started_at"] for n, info, _ in history if n == generation)
            prior = _plan_from_artifact(run_id, generation, artifacts, start)
            request = (prior or {}).get("request") or {}
            if retry_plan_bound_to_run(request, run, generation):
                plan = prior
    samples: dict[str, str] = {}
    if plan is not None:
        available = _artifact_names(artifacts)
        for job in jobs:
            if job.get("conclusion") not in ("failure", "timed_out"):
                continue
            matched = _matching_job(job, plan["jobs"])
            if not matched:
                continue
            artifact = f"build-logs-a{attempt}-{matched['yaml']}-{matched['id']}"
            if artifact in available and artifact not in samples:
                samples[artifact] = _sample_log(run_id, artifact)
    result = analyze(run, attempt, jobs, artifacts, plan, logs=samples)
    pr = github.pr_for_run(run) if run.get("event") == "pull_request" else None
    result["pr"] = ({"number": pr["number"], "head": pr["head"]["ref"],
                     "head_sha": pr["head"]["sha"], "author": pr["user"]["login"]}
                    if pr else None)
    from ..release_trigger import automatic_pr
    selected = None
    if pr:
        try:
            selected = automatic_pr(pr, repo)
        except ValueError as exc:
            result["invalid_version_pr"] = str(exc)
    request = production_request(run, plan) if not pr else None
    trusted = bool(selected) if pr else bool(request)
    if request:
        result["source"]["request"] = request
        for group in result["groups"]:
            if group["yaml"] != request["yaml"]:
                group["repairable"] = False
    if pr and pr["head"]["sha"].lower() != run["head_sha"].lower():
        trusted = False
        result["stale_pr_head"] = True
    if pr and trusted and selected[1] == "new":
        # New version PRs keep their original proposal commit and are
        # repaired in-place, never by a competing PR against main.
        from .pr_history import load_new_version_rounds
        try:
            history = load_new_version_rounds(pr)
            for group in result["groups"]:
                if group["yaml"] != selected[0] or len(history) >= 2:
                    group["repairable"] = False
                else:
                    if history:
                        group["observed_signature"] = group["signature"]
                        group["signature"] = history[0].incident
                    group["branch"] = pr["head"]["ref"]
        except ValueError as exc:
            trusted = False
            result["bot_pr_invalid_history"] = str(exc)
    if pr and trusted and selected[1] == "repair":
        # The PR's repair history comes from all bot commits, never the
        # last-written PR body or the latest Agent message.
        from .pr_history import incident_from_pr, load_rounds
        branch = pr["head"]["ref"]
        parts = branch.split("/")
        try:
            incident = incident_from_pr(pr)
            if len(parts) != 3 or not branch_matches(branch, parts[1], incident):
                raise ValueError("Bot repair branch/incident mismatch")
            history = load_rounds(pr, incident)
            if branch != branch_name(parts[1], incident) and \
               branch != branch_name(parts[1], incident, history[0].source_run):
                raise ValueError("Bot repair occurrence does not match original source run")
            authoritative_round = history[-1].number
            import re as regex
            old_round = regex.search(
                r"(?m)^\*\*Repair round:\*\* ([0-9]+)/2$",
                pr.get("body") or "")
            if not old_round or authoritative_round != int(old_round[1]):
                result["pr_body_out_of_sync"] = True
        except ValueError as exc:
            trusted = False
            result["bot_pr_invalid_history"] = str(exc)
        if trusted:
            target = parts[1]
            for group in result["groups"]:
                if group["yaml"] != target or authoritative_round >= 2:
                    group["repairable"] = False
                    group["decision"] = "not bot target or repair round limit reached"
                else:
                    group["observed_signature"] = group["signature"]
                    group["signature"] = incident
    if not pr and run.get("event") == "pull_request":
        trusted = False
    if not pr and not request:
        trusted = False
    # Successful PRs may merge only after the complete target matrix ran.
    from ..release_trigger import complete_pr_build
    verification_jobs = jobs
    if pr and selected and trusted and plan is not None and attempt > 1:
        generation = (plan.get("request") or {}).get("plan_attempt")
        if type(generation) is int and 1 <= generation < attempt:
            from ..run_artifacts import attempts, effective_workers
            history = list(attempts(run_id, attempt, generation))
            verification_jobs = [job for _, job in effective_workers(history, generation, plan["jobs"]).values()]
    result["verified_version_ci"] = bool(pr and selected and trusted and
        plan is not None and complete_pr_build(selected[0], plan["jobs"], verification_jobs) and
        run.get("conclusion") == "success" and attempt == int(run["run_attempt"]))
    result["automatic_version_pr"] = bool(pr and selected)
    if run.get("conclusion") != "failure":
        trusted = False
    if attempt != int(run["run_attempt"]):
        trusted = False  # never repair stale attempts
    result["trusted_repair_source"] = trusted
    if not trusted:
        for group in result["groups"]:
            group["repairable"] = False
    # Do not burn another Agent round when an earlier run already owns a bot
    # PR for the same version/signature. Continue only from that PR's own CI.
    if trusted and not pr:
        owner = repo.split("/", 1)[0]
        for group in result["groups"]:
            if not group["repairable"]:
                continue
            from .duplicates import open_repairs
            if open_repairs(group["yaml"], group["signature"]):
                group["repairable"] = False
                group["decision"] = "incident already has an open repair PR"
                continue
            branch = branch_name(group["yaml"], group["signature"])
            active = github.api(
                f"repos/{repo}/pulls?head={owner}:{branch}&state=all&per_page=100")
            if active:
                if any(item.get("state") == "open" for item in active):
                    group["repairable"] = False
                    group["decision"] = "incident already has an open repair PR"
                else:
                    branch = branch_name(group["yaml"], group["signature"],
                                         result["source"]["run_id"])
                    again = github.api(
                        f"repos/{repo}/pulls?head={owner}:{branch}&state=all&per_page=100")
                    if again:
                        group["repairable"] = False
                        group["decision"] = "this source run already has a repair PR"
            group["branch"] = branch
    result["repair_matrix"] = [
        {"yaml": group["yaml"], "signature": group["signature"],
         "branch": group.get("branch") or branch_name(group["yaml"], group["signature"])}
        for group in result["groups"] if group["repairable"]
    ]
    return result


def write_json(destination: Path, value: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
