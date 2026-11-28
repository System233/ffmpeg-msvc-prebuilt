"""Select native ABI work units and emit a bounded single-version CI matrix.

Planning consumes only verified native vcpkg ABI scans.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .identity import utc_release_date, date_suffix, public_version
from .dependencies import overlay_port_names
from .state import PublishedState
from .versions import (
    ROOT, config, dependency_names,
    spec_files,
)


def plan_native(scan: dict, *, state: PublishedState | None = None,
                force: bool = False) -> dict[str, Any]:
    """Filter native vcpkg ABI results by publication state, without hashing.

    The ABI scanner has already resolved the vcpkg graph, including the exact
    Features and dependency ABI. Neither the Python Feature graph nor Git
    change heuristics decide build identity here.
    """
    if scan.get("schema") != 3 or not isinstance(scan.get("jobs"), list):
        raise ValueError("Expected a verified native vcpkg ABI scan (schema 3)")
    state = state if state is not None else PublishedState()
    jobs = []
    counts: dict[str, int] = {}
    reused = []
    requested: dict[str, list[dict]] = {}
    dates = {row.get("release_date") for row in scan["jobs"] if row.get("release_date")}
    if len(dates) > 1:
        raise ValueError("One release plan must use one UTC date")
    release_date = next(iter(dates), utc_release_date())
    date_suffix(release_date)
    for record in scan["jobs"]:
        if not all(record.get(key) for key in
                   ("id", "port", "package", "abi_hash", "triplet", "version")):
            raise ValueError("Native vcpkg scan record is missing its build identity")
        record = dict(record, release_date=release_date)
        record.pop("revision", None)
        group = public_version(record)
        requested.setdefault(group, []).append(record)
        channel = "master" if record.get("yaml") == "master" else "release"
        existing = None if force else state.find_abi(record["version"], record["triplet"], record["abi_hash"],
                                  channel=channel, source_commit=record.get("source_ref") or None)
        if force or not existing:
            jobs.append(record)
            counts[record["version"]] = counts.get(record["version"], 0) + 1
        else:
            reused.append({"job": record, "record": existing})
    changed_groups = {public_version(job) for job in jobs}
    def matrix_identity(rows):
        return {(row["version"], row["triplet"], row["linkage"], row["license"], row.get("abi_hash"))
                for row in rows}
    if not force:
        for group, wanted in requested.items():
            if group in changed_groups:
                continue
            latest = state.latest_release(wanted[0])
            if not latest or matrix_identity(wanted) != matrix_identity(latest.get("variants", [])):
                changed_groups.add(group)
    selected_reuse = [row for row in reused if public_version(row["job"]) in changed_groups]
    descriptions = sorted({record["version"] for record in scan["jobs"]})
    return {"schema": 3, "jobs": jobs, "matrix": jobs,
            "release_date": release_date, "publication_required": bool(changed_groups),
            "reuse": selected_reuse,
            "blocked": scan.get("blocked", []),
            "versions": [{"version": version, "pending_variants": counts.get(version, 0)}
                         for version in descriptions]}


def changed_paths(base: str, head: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base, head, "--"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return set(result.stdout.splitlines())


def impacted_versions(paths: set[str], candidates: list[str]) -> list[str]:
    """Conservative dependency-aware impact detection, including inherited specs."""
    if not paths:
        return []
    shared = any(
        p.startswith(("ffbuild/", "ffvcpkg/", "scripts/ffbuild/", "scripts/ffvcpkg/", "scripts/cmake/", "licenses/", ".github/actions/"))
        or p in {"vcpkg-configuration.json", "requirements.txt", "pyproject.toml",
                 ".github/workflows/build-all.yml", ".github/workflows/build-release.yml", ".github/ci.env"}
        for p in paths
    )
    impacted = []
    changed_ports = {
        p.split("/")[1] for p in paths if p.startswith("ports/") and len(p.split("/")) >= 3
    }
    changed_triplets = any(p.startswith("triplets/") for p in paths)
    for version in candidates:
        spec = config(version)
        if shared or spec_files(version).intersection(paths):
            impacted.append(version)
            continue
        if any(p == f"patches/{name}" for name in spec.get("patches", []) for p in paths):
            impacted.append(version)
            continue
        if changed_triplets:
            impacted.append(version)
            continue
        if changed_ports:
            linked = set()
            # Without an upstream pin it is unsafe to exclude any changed
            # overlay from Master impact analysis.
            if version == "master":
                impacted.append(version)
                continue
            from .targets import matrix_axes
            for license_ in matrix_axes()["LICENSES"]:
                linked.update(overlay_port_names(dependency_names(version, license_)))
            if linked.intersection(changed_ports):
                impacted.append(version)
    return impacted


def write_github_output(result: dict, path: Path) -> None:
    """Emit a bounded single-version CI matrix; local JSON plans remain unrestricted."""
    tasks = result["jobs"]
    # GitHub Actions' own 256-job limit is a platform constraint, not a
    # declaration of the current FFmpeg matrix size.
    if len(tasks) > 256 or len({job.get("yaml") for job in tasks}) > 1:
        raise ValueError("CI matrix must contain one FFmpeg version and at most 256 jobs")
    identities = [(job.get("triplet"), job.get("package")) for job in tasks]
    if any(not all(identity) for identity in identities) or len(identities) != len(set(identities)):
        raise ValueError("Missing or duplicate CI target identity")
    job_ids = [job.get("id") for job in tasks if job.get("id") is not None]
    if len(job_ids) != len(set(job_ids)):
        raise ValueError("Duplicate CI job identity")
    with path.open("a", encoding="utf-8") as output:
        output.write(f"matrix={json.dumps(tasks, separators=(',', ':'))}\n")
        output.write("publication_required=" + ("true" if result.get("publication_required", bool(tasks)) else "false") + "\n")
