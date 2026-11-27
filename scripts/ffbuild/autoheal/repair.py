"""Unprivileged repair worker; prepares and verifies one source-bound candidate."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import github
from .models import validate_triage
from .scope import check_worktree


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", check=True)
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


def incident_context(report: dict, yaml: str) -> dict:
    from ..versions import TRIPLETS
    incident = validate_triage(report, yaml)
    source = report["source"]
    base = report["pr"]["head_sha"] if report.get("pr") else source["head_sha"]
    triplets = sorted({job["triplet"] for job in incident.jobs})
    if not triplets or not set(triplets).issubset(TRIPLETS):
        raise ValueError("Invalid incident target architectures")
    logs = Path("error_logs")
    return {
        "target_yaml": incident.yaml, "base_sha": base,
        "workflow_run_id": source["run_id"], "run_attempt": source["run_attempt"],
        "signature": incident.signature,
        "failed_jobs": [job["job_id"] for job in incident.jobs],
        "triplets": triplets,
        "diagnostics": [{
            "job_id": job["job_id"], "variant_id": job["variant_id"],
            "triplet": job.get("triplet"), "abi_hash": job["abi_hash"],
            "artifact": job["artifact"], "log_directory": (logs / job["artifact"]).as_posix(),
            "failed_steps": job["failed_steps"], "phase": job.get("phase"),
            "classification": job.get("classification"), "signature": job.get("signature"),
            "build_plan": job.get("build_plan", {}),
        } for job in incident.jobs],
        "source_snapshot": source.get("request", {}),
        "log_directory": str(logs),
        "constraints": "Modify only target YAML and newly-added target-exclusive source patches.",
    }


def prepare_context(report: dict, yaml: str) -> dict:
    data = incident_context(report, yaml)
    base = data["base_sha"]
    trusted = _git("rev-parse", "HEAD")
    _git("fetch", "origin", base)
    _git("checkout", "--detach", base)
    if _git("rev-parse", "HEAD").lower() != base.lower():
        raise ValueError("Cannot reproduce failed source commit")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Repair requires unmodified tracked repository files")
    # Workflow code is from trusted main. An older/incompatible failed run must
    # be rebuilt with current tools, not execute different code with Agent secrets.
    if _git("diff", "--name-only", trusted, base, "--", "scripts", "ports", "triplets",
            "pyproject.toml", "requirements.txt", "vcpkg-configuration.json",
            ".agents/skills/ffmpeg-autoheal", ".agents/skills/ffmpeg-autoheal-audit", ".github/actions"):
        raise ValueError("Failed source uses different build/repair tooling; rebuild with current main")
    for job in data["diagnostics"]:
        if job["artifact"]:
            github.download_artifact(data["workflow_run_id"], job["artifact"], Path(job["log_directory"]))
    Path("agent_context.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    Path("failed_steps_hint.txt").write_text("\n".join(
        " / ".join(job["failed_steps"]) for job in data["diagnostics"]
    ), encoding="utf-8")
    return data


def prepare(report: dict, yaml: str) -> dict:
    """Generate the exact Seed key and immutable baseline before restoring caches."""
    from . import build as native
    from ..versions import generate_all, GENERATED_PORTS
    from ..port import ffmpeg_port_name
    data = prepare_context(report, yaml)
    runtime = native.runtime_dir()
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "ready.json").unlink(missing_ok=True)
    generate_all(master=data["source_snapshot"] if yaml == "master" else None)
    contract = native.contract(GENERATED_PORTS / ffmpeg_port_name(yaml))
    contract_file = runtime / "contract.json"
    contract_file.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    return {"base": data["base_sha"], "triplets": json.dumps(data["triplets"]),
            "context_sha256": hashlib.sha256(Path("agent_context.json").read_bytes()).hexdigest(),
            "contract_sha256": hashlib.sha256(contract_file.read_bytes()).hexdigest()}


def require_ready(data: dict) -> None:
    from . import build as native
    if native.context() != data:
        raise ValueError("Prepared context differs from authenticated incident")
    if _git("rev-parse", "HEAD") != data["base_sha"] or _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Prepared repair checkout is not the exact clean source")
    ready = json.loads((native.runtime_dir() / "ready.json").read_text(encoding="utf-8"))
    if ready != native.bindings():
        raise ValueError("Dependency environment was not prepared for this incident")


def redact(text: str) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    return text.replace(key, "[redacted]") if key else text


def repair(report: dict, yaml: str, output: Path) -> None:
    """Run the Pi session after preflight, then export only verified changes."""
    from . import build as native
    incident = validate_triage(report, yaml)
    source = report["source"]
    data = incident_context(report, yaml)
    base_sha = data["base_sha"]
    require_ready(data)
    env = {**os.environ, "FFBUILD_REPAIR_TARGET": incident.yaml, "FFBUILD_REPAIR_BASE": base_sha}
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    result = subprocess.run(
        [sys.executable, "-m", "ffbuild.autoheal.runner", "--budget-seconds",
         os.environ.get("FFBUILD_REPAIR_BUDGET_SECONDS", "10800")], env=env, check=False,
    )
    if result.returncode == 3:
        if (_git("rev-parse", "HEAD").lower() != base_sha.lower() or
                _git("status", "--porcelain", "--untracked-files=no")):
            raise ValueError("Declined repair must leave the source unchanged")
        report_path = Path("fix_report.md")
        if not report_path.is_file() or report_path.is_symlink() or report_path.stat().st_size > 65536:
            raise ValueError("Missing safe-decline report")
        report_text = redact(report_path.read_text(encoding="utf-8", errors="replace"))
        if not re.search(r"(?m)^Decision: no_safe_fix[ \t]*$", report_text):
            raise ValueError("Missing explicit safe-decline decision")
        output.mkdir(parents=True, exist_ok=True)
        (output / "manifest.json").write_text(json.dumps({
            "schema": 1, "decision": "no_safe_fix", "yaml": yaml,
            "signature": incident.signature, "run_id": source["run_id"],
            "run_attempt": source["run_attempt"], "base_sha": base_sha,
        }, indent=2) + "\n", encoding="utf-8")
        (output / "repair-report.md").write_text(report_text, encoding="utf-8")
        print("Diagnosis completed without an authorized repair candidate.")
        return
    if result.returncode:
        reason = {4: "budget_exceeded", 5: "environment_failed"}.get(result.returncode, "agent_failed")
        raise RuntimeError(f"Pi repair ended without verified candidate: {reason}")
    paths = check_worktree(incident.yaml, base_sha, Path.cwd())
    changes = _changed()
    if (_git("status", "--porcelain", "--untracked-files=no") or
            _git("rev-list", "--count", f"{base_sha}..HEAD") != "1" or
            set(paths) != {path for _, path in changes}):
        raise ValueError("Supervisor must commit the complete verified candidate exactly once")
    evidence = json.loads((native.runtime_dir() / "verification.json").read_text(encoding="utf-8"))
    native.validate_evidence(evidence, data)
    if (evidence["candidate"] != _git("rev-parse", "HEAD")
            or evidence["tree"] != _git("rev-parse", "HEAD^{tree}")):
        raise ValueError("Verified candidate tree differs from the submitted commit")
    patch = subprocess.check_output(["git", "format-patch", "-1", "--stdout", "--binary"])
    if not patch or b"diff --git " not in patch:
        raise ValueError("Missing candidate Git patch")
    key = os.environ.get("OPENAI_API_KEY")
    if key and key.encode("utf-8") in patch:
        raise ValueError("Refusing to publish a patch containing the API key")
    for check in evidence["checks"]:
        check["reason"] = redact(check["reason"])
    paths = [path for _, path in changes]
    agent_report = Path("fix_report.md")
    hypothesis = "Agent did not provide a root-cause summary"
    if agent_report.is_file() and agent_report.stat().st_size < 65536:
        assessment = redact(agent_report.read_text(encoding="utf-8", errors="replace"))
        match = re.search(r"(?im)^\s*[-*]?\s*Root cause:\s*(.+)$", assessment)
        if match:
            hypothesis = match.group(1).strip()[:300]
    from ..messages import repair_title
    subject = repair_title(incident.yaml, _git("show", "-s", "--format=%s", "HEAD"))
    manifest = {
        "schema": 2, "yaml": incident.yaml, "signature": incident.signature,
        "run_id": source["run_id"], "run_attempt": source["run_attempt"],
        "base_sha": base_sha, "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "paths": paths, "root_cause_hypothesis": hypothesis, "subject": subject,
        "validation": evidence,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "repair.patch").write_bytes(patch)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report_lines = [
        f"# FFmpeg {incident.yaml} automated repair",
        "", f"Source run: {source.get('url', source['run_id'])}", "",
        "## Failed build units",
        *[f"- {job['triplet']} / {job['variant_id']}" for job in incident.jobs], "",
        "## Agent hypothesis", hypothesis, "",
        "## Changed files", *[f"- {path}" for path in paths], "",
        "## Independent in-runner validation",
        *[f"- {check['spec']}: FFmpeg + Tester compile/link + PE/COFF passed; "
          f"runtime {check['runtime']['status']}; covers failed jobs {check['jobs']}"
          for check in evidence["checks"]],
        "", "Production full-matrix CI remains the merge/publication gate.",
    ]
    (output / "repair-report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
