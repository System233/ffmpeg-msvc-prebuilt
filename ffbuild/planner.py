"""Select build work units for PR, push, scheduled and manual executions.

Release metadata remains compatible with the existing data branch. A future
release-state migration must not be coupled to the Python build migration.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from scripts.ops.naming import build_variant_id
from .fingerprint import overlay_port_names
from .state import PublishedState
from .versions import (
    LICENSES, LINKAGES, ROOT, TRIPLETS, config, dependency_names,
    has_source, latest_per_family, revision, spec_files, versions,
)


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
        p.startswith(("scripts/", "ffbuild/", ".github/actions/", ".github/workflows/"))
        or p in {"vcpkg-configuration.json", "requirements.txt"}
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
         triplets: tuple[str, ...] = TRIPLETS, licenses: tuple[str, ...] = LICENSES,
         linkages: tuple[str, ...] = LINKAGES, state: PublishedState | None = None,
         force: bool = False, include_master: bool = False) -> dict[str, Any]:
    """Build plan with the existing revision/variant identity convention.

    PR validation may use force=True, but the established data branch format
    and revision allocation policy are intentionally untouched.
    """
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
    if "master" in candidates and (not ref or not sha512):
        from .master import master_metadata
        info = master_metadata()
        ref = ref or info["ref"]
        sha512 = sha512 or info["sha512"]
    state = state or PublishedState()
    tasks: list[dict] = []
    reasons: list[dict] = []
    for ver in candidates:
        resolved_source = config(ver).get("source", {})
        if not resolved_source.get("sha512") and not sha512:
            raise ValueError(f"No FFmpeg source hash for {ver}")
        actual_version = ref.lstrip("n") if ver == "master" else ver
        release_revision = revision(ver)
        pending = 0
        for triplet in triplets:
            for lic in licenses:
                for linkage in linkages:
                    if not force and state.variant_exists(actual_version, release_revision,
                                                          triplet, lic, linkage):
                        continue
                    tasks.append({
                        "id": build_variant_id(
                            version=actual_version, revision=release_revision,
                            triplet=triplet, license=lic, linkage=linkage,
                        ),
                        "yaml": ver, "version": actual_version, "revision": release_revision,
                        "triplet": triplet, "ref": ref, "sha512": sha512,
                        "targets": [{"license": lic, "linkage": linkage}],
                    })
                    pending += 1
        reasons.append({
            "version": actual_version, "revision": release_revision,
            "pending_variants": pending,
        })
    return {"schema": 1, "jobs": tasks, "versions": reasons,
            "matrix": tasks}


def write_github_output(result: dict, path: Path) -> None:
    """GITHUB_OUTPUT is a platform boundary; no business logic belongs in YAML."""
    yaml_versions = {job["yaml"] for job in result["jobs"]}
    single = next(iter(yaml_versions)) if len(yaml_versions) == 1 else ""
    single_ref = result["jobs"][0]["ref"] if single else ""
    triplets = sorted({job["triplet"] for job in result["jobs"]})
    with path.open("a", encoding="utf-8") as output:
        output.write(f"matrix={json.dumps(result['matrix'], separators=(',', ':'))}\n")
        output.write(f"triplets={json.dumps(triplets, separators=(',', ':'))}\n")
        output.write(f"count={len(result['jobs'])}\n")
        output.write(f"auto_heal_yaml={single}\n")
        output.write(f"auto_heal_ref={single_ref}\n")
