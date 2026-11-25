"""Select native ABI work units and emit a bounded single-version CI matrix.

Legacy local planning helpers remain available for compatibility; production
uses only plan_native with verified native vcpkg ABI scans.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .identity import variant_name, utc_release_date, date_suffix, public_version
from .fingerprint import overlay_port_names, recipe_fingerprint, variant_fingerprint
from .state import PublishedState
from .targets import Target, compile_target, load_targets
from .versions import (
    LICENSES, ROOT, config, dependency_names,
    has_source, latest_per_family, revision, spec_files, versions,
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
        existing = state.find_abi(record["version"], record["triplet"], record["abi_hash"],
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
        p.startswith(("ffbuild/", "ffvcpkg/", "licenses/", ".github/actions/"))
        or p in {"vcpkg-configuration.json", "requirements.txt",
                 ".github/workflows/build-all.yml", ".github/workflows/build-release.yml"}
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
            for license_ in LICENSES:
                linked.update(overlay_port_names(dependency_names(version, license_)))
            if linked.intersection(changed_ports):
                impacted.append(version)
    return impacted


def plan(*, mode: str = "all", version: str = "", base: str = "", head: str = "",
         ref: str = "", sha512: str = "", history: bool = False,
         targets: tuple[Target, ...] | None = None, state: PublishedState | None = None,
         force: bool = False, include_master: bool = False,
         commit: str = "") -> dict[str, Any]:
    """Plan declared vcpkg package specs, not ffbuild license/linkage matrices."""
    targets = targets if targets is not None else load_targets()
    if version:
        candidates = [version]
    else:
        candidates = [v for v in versions() if has_source(v)]
        if not history:
            candidates = latest_per_family(candidates)
        if mode == "changed":
            if not base or not head:
                raise ValueError("--base and --head are required for changed mode")
            changes = changed_paths(base, head)
            candidates = impacted_versions(changes, candidates)
            if include_master and impacted_versions(changes, ["master"]):
                candidates.append("master")
    master_commit = commit
    if "master" in candidates:
        from .master import master_metadata
        # Source identity is per job.  Never copy master refs into stable jobs.
        if any((ref, sha512, master_commit)) and not all((ref, sha512, master_commit)):
            raise ValueError("Master snapshot must supply --ref, --sha512 and --commit together")
        if not ref or not sha512 or not master_commit:
            info = master_metadata()
            ref = ref or info["ref"]
            sha512 = sha512 or info["sha512"]
            master_commit = master_commit or info.get("commit", "")
        if not master_commit or len(master_commit) != 40 or any(c not in "0123456789abcdef" for c in master_commit.lower()):
            raise ValueError("Master requires a pinned 40-character upstream commit")
    state = state or PublishedState()
    tasks: list[dict] = []
    reasons: list[dict] = []
    blocked: list[dict] = []
    for ver in candidates:
        resolved_source = config(ver).get("source", {})
        job_ref = ref if ver == "master" else ""
        job_sha512 = sha512 if ver == "master" else ""
        if not resolved_source.get("sha512") and not job_sha512:
            raise ValueError(f"No FFmpeg source hash for {ver}")
        source_version = job_ref.lstrip("n") if ver == "master" else ver
        source_ref = (master_commit or job_ref) if ver == "master" else ""
        recipe_hash = recipe_fingerprint(ver, ref=source_ref, sha512=job_sha512)
        # Build version changes when source, patches or transitive inputs change.
        actual_version = f"{source_version}-h{recipe_hash[:12]}"
        release_revision = revision(ver)
        pending = 0
        for target in targets:
            try:
                built = compile_target(config(ver), ver if ver != "master" else source_version.split("-", 1)[0], target)
            except (ValueError, KeyError) as error:
                blocked.append({"yaml": ver, "package": target.package,
                                "triplet": target.triplet, "errors": [str(error)]})
                continue
            if built["license"] == "nonfree":
                blocked.append({"yaml": ver, "package": target.package,
                                "triplet": target.triplet,
                                "errors": ["Nonfree artifacts are not redistributable"]})
                continue
            variant_hash = variant_fingerprint(recipe_hash, target.triplet, built["feature_hash"])
            if not force and state.target_exists(actual_version, release_revision,
                                                  target.triplet, built["feature_hash"],
                                                  recipe_hash, variant_hash):
                continue
            tasks.append({
                "id": variant_name(actual_version, release_revision, target.triplet,
                                   built["linkage"], built["license"], built["feature_hash"]),
                "yaml": ver, "version": actual_version, "revision": release_revision,
                "source_version": source_version, "source_ref": source_ref,
                "triplet": target.triplet, "package": built["package"],
                "features": built["features"], "feature_hash": built["feature_hash"],
                "license": built["license"], "linkage": built["linkage"],
                "ref": job_ref, "sha512": job_sha512,
                "build_hash": recipe_hash, "variant_hash": variant_hash,
            })
            pending += 1
        reasons.append({
            "version": actual_version, "revision": release_revision,
            "pending_variants": pending,
        })
    return {"schema": 2, "jobs": tasks, "versions": reasons,
            "blocked": blocked, "matrix": tasks}


def write_github_output(result: dict, path: Path) -> None:
    """Emit a bounded single-version CI matrix; local JSON plans remain unrestricted."""
    tasks = result["jobs"]
    if len(tasks) > 16 or len({job.get("yaml") for job in tasks}) > 1:
        raise ValueError("CI matrix must contain at most 16 jobs for one FFmpeg version")
    triplets = sorted({job["triplet"] for job in tasks})
    with path.open("a", encoding="utf-8") as output:
        output.write(f"matrix={json.dumps(tasks, separators=(',', ':'))}\n")
        output.write(f"triplets={json.dumps(triplets, separators=(',', ':'))}\n")
        output.write(f"count={len(tasks)}\n")
        output.write("publication_required=" + ("true" if result.get("publication_required", bool(tasks)) else "false") + "\n")
