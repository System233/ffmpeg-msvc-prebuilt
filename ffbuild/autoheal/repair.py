"""Unprivileged repair worker; generates artifacts, never pushes a Git ref."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from . import github
from .ledger import MAX_AGENT_ATTEMPTS
from .models import validate_triage
from .scope import validate_changes


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _changed(commit: str = "HEAD") -> list[tuple[str, str]]:
    rows = _git("diff-tree", "--no-commit-id", "--name-status", "-r", commit).splitlines()
    result = []
    for row in rows:
        parts = row.split("\t")
        if len(parts) != 2:
            raise ValueError("Rename / nonstandard file delta rejected")
        result.append((parts[0], parts[1]))
    return result


def repair(report: dict, yaml: str, output: Path) -> None:
    """Execute the existing OpenCode loop behind an independent scope validator."""
    incident = validate_triage(report, yaml)
    source = report["source"]
    base_sha = (report["pr"]["head_sha"] if report.get("pr")
                else source["head_sha"])
    _git("fetch", "origin", base_sha)
    _git("checkout", "--detach", base_sha)
    if _git("rev-parse", "HEAD").lower() != base_sha.lower():
        raise ValueError("Cannot reproduce failed source commit")
    # The workflow has legitimate untracked triage and knowledge artifacts;
    # refuse modifications to *tracked* repository files, not those inputs.
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Repair requires unmodified tracked repository files")
    logs = Path("error_logs")
    logs.mkdir(exist_ok=True)
    for job in incident.jobs:
        if job["artifact"]:
            github.download_artifact(source["run_id"], job["artifact"], logs / job["artifact"])
    Path("agent_context.json").write_text(json.dumps({
        "target_yaml": incident.yaml, "base_sha": base_sha,
        "workflow_run_id": source["run_id"], "run_attempt": source["run_attempt"],
        "signature": incident.signature,
        "failed_jobs": [job["job_id"] for job in incident.jobs],
        "log_directory": str(logs),
        "constraints": "Modify only target YAML and newly-added target-exclusive source patches.",
    }, indent=2), encoding="utf-8")
    Path("failed_steps_hint.txt").write_text("\n".join(
        " / ".join(job["failed_steps"]) for job in incident.jobs
    ), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/ci/agent_repair.py", "--action", "pr",
         "--base-sha", base_sha, "--max-retries", str(MAX_AGENT_ATTEMPTS)],
        check=False,
    )
    if result.returncode:
        raise RuntimeError("OpenCode did not produce an authorized change")
    changes = _changed()
    old = _git("show", f"{base_sha}:ffmpeg/{incident.yaml}.yaml")
    validate_changes(incident.yaml, changes, Path.cwd(), before=old)
    patch = _git("format-patch", "-1", "--stdout").encode("utf-8")
    if not patch or b"diff --git " not in patch:
        raise ValueError("Missing candidate Git patch")
    output.mkdir(parents=True, exist_ok=True)
    (output / "repair.patch").write_bytes(patch)
    paths = [path for _, path in changes]
    agent_report = Path("fix_report.md")
    hypothesis = "Agent did not provide a root-cause summary"
    if agent_report.is_file() and agent_report.stat().st_size < 65536:
        assessment = agent_report.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?im)^\s*[-*]?\s*Root cause:\s*(.+)$", assessment)
        if match:
            hypothesis = match.group(1).strip()[:300]
    manifest = {
        "schema": 1, "yaml": incident.yaml, "signature": incident.signature,
        "run_id": source["run_id"], "run_attempt": source["run_attempt"],
        "base_sha": base_sha, "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "paths": paths,
        "root_cause_hypothesis": hypothesis,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report_lines = [
        f"# FFmpeg {incident.yaml} automated repair",
        "", f"Source run: {source.get('url', source['run_id'])}",
        f"Signature: {incident.signature}", "",
        "## Failed build units",
        *[f"- {job['triplet']} / {job['variant_id']} (native ABI: {job['abi_hash']})"
          for job in incident.jobs], "",
        "## Agent hypothesis (unverified)", hypothesis, "",
        "## Changed files", *[f"- {path}" for path in paths], "",
        "## Validation", "Awaiting full GitHub MSVC CI verification.",
    ]
    (output / "repair-report.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8")
