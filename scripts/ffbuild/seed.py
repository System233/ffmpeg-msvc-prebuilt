"""Plan and populate a shared cache from native vcpkg dependency graphs.

No virtual Port, no synthetic ABI, and no union of incompatible features.
All supported version/target combinations are represented; each direct
installation batch is independently resolved by vcpkg before it may build.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ffvcpkg import command as vcpkg_command, environment

from .native_abi import abi_identifier, graph_digest, native_abi_query
from .port import ffmpeg_port_name
from .targets import load_targets
from .versions import GENERATED_PORTS, ROOT, TRIPLETS, has_source, versions

TARGET_PORTS = frozenset({"ffmpeg", "ffmpeg-tester", "ffmpeg-deps"})
DEFAULT_PLAN = GENERATED_PORTS / "seed-plan.json"
_SPEC = re.compile(r"([a-z0-9][a-z0-9-]*)\[([a-z0-9,-]+)\]:([a-z0-9][a-z0-9-]*)")
_ABI = re.compile(r"[0-9a-f]{64}")


def external_batch(abis: dict[str, str], specs: dict[str, str], triplet: str) -> dict:
    if set(abis) != set(specs):
        raise ValueError("Native ABI and package spec graphs differ")
    targets = {f"ffmpeg_{triplet}", f"ffmpeg-tester_{triplet}"}
    if not targets.issubset(abis):
        raise ValueError("Native target graph missing FFmpeg or Tester")
    forbidden = {k for k in abis if abi_identifier(k)[0] in TARGET_PORTS} - targets
    if forbidden:
        raise ValueError("Unexpected target package in native dependency graph")
    batch = {"abis": {k: v for k, v in abis.items() if k not in targets},
             "specs": {k: v for k, v in specs.items() if k not in targets}}
    validate_batch(batch)
    return batch


def validate_batch(batch: dict) -> None:
    if set(batch) != {"abis", "specs"} or not batch["abis"] or set(batch["abis"]) != set(batch["specs"]):
        raise ValueError("Incomplete external dependency batch")
    for key, abi in batch["abis"].items():
        name, triplet = abi_identifier(key)
        spec = _SPEC.fullmatch(batch["specs"][key])
        if (name in TARGET_PORTS or not _ABI.fullmatch(abi) or not spec or
                (spec[1], spec[3]) != (name, triplet) or
                "core" not in spec[2].split(",")):
            raise ValueError(f"Invalid external dependency ABI/spec: {key}")


def abi_set(batches: list[dict]) -> set[str]:
    if not batches:
        raise ValueError("Empty dependency plan")
    for batch in batches:
        validate_batch(batch)
    return {abi for batch in batches for abi in batch["abis"].values()}


def seed_hash(batches: list[dict]) -> str:
    return hashlib.sha256("\n".join(sorted(abi_set(batches))).encode("utf-8")).hexdigest()


def _pairs(batches: list[dict]) -> set[tuple[str, str]]:
    return {pair for batch in batches for pair in batch["abis"].items()}


def _unique(batches: list[dict]) -> list[dict]:
    return list({graph_digest(batch): batch for batch in batches}.values())


def merge_batches(batches: list[dict]) -> list[dict]:
    """Pack compatible graphs, retaining every incompatible ABI in its own batch."""
    result: list[dict] = []
    for batch in sorted(_unique(batches), key=lambda b: (-len(b["abis"]), graph_digest(b))):
        validate_batch(batch)
        for current in result:
            shared = current["abis"].keys() & batch["abis"].keys()
            if all(current["abis"][k] == batch["abis"][k] and
                   current["specs"][k] == batch["specs"][k] for k in shared):
                current["abis"].update(batch["abis"])
                current["specs"].update(batch["specs"])
                break
        else:
            result.append({key: dict(batch[key]) for key in ("abis", "specs")})
    if _pairs(result) != _pairs(batches):
        raise RuntimeError("Dependency batch merge lost native ABI coverage")
    return result


def verify_batch(batch: dict, triplet: str, *, binary: Path | None = None,
                 evidence: Path | None = None) -> None:
    validate_batch(batch)
    specs: dict[str, str] = {}
    actual = native_abi_query(sorted(batch["specs"].values()), triplet,
                             binary=binary, specs=specs, evidence=evidence)
    if actual != batch["abis"] or specs != batch["specs"]:
        missing = set(batch["abis"].items()) - set(actual.items())
        unexpected = set(actual.items()) - set(batch["abis"].items())
        raise RuntimeError(f"Direct dependency ABI drift for {triplet}: "
                           f"missing={sorted(missing)}, unexpected={sorted(unexpected)}, "
                           f"specs_equal={specs == batch['specs']}")


def _manifest_signature(manifest: dict, roots: tuple[str, ...]) -> str:
    # Only remove fields irrelevant to dependency resolution. A requested leaf
    # with no dependency/support metadata (e.g. static) cannot alter external
    # dependencies. Keep every dependency edge, platform and default feature.
    graph = {k: v for k, v in manifest.items() if k not in
             {"version", "version-string", "version-semver", "version-date",
              "port-version", "description", "homepage", "license", "maintainers"}}
    graph["features"] = {k: {n: v for n, v in f.items() if n != "description"}
                         for k, f in graph.get("features", {}).items()}
    selected = [f for f in roots if f not in graph["features"] or graph["features"][f]]
    return graph_digest({"manifest": graph, "roots": sorted(selected)})


def seed_identity(*, triplet: str, overlay: Path = GENERATED_PORTS,
                  binary: Path | None = None, evidence: Path | None = None) -> tuple[str, dict]:
    """Derive required ABI coverage from the actual generated version Ports."""
    if triplet not in TRIPLETS:
        raise ValueError(f"Unsupported FFmpeg Triplet: {triplet}")
    names = [v for v in versions() if has_source(v)]
    if (overlay / ffmpeg_port_name("master") / "vcpkg.json").is_file():
        names.append("master")
    targets = [t for t in load_targets() if t.triplet == triplet]
    if not names or not targets:
        raise ValueError(f"No supported dependency targets for {triplet}")
    groups: dict[str, list[tuple[str, str]]] = {}
    for name in names:
        port = overlay / ffmpeg_port_name(name)
        manifest = json.loads((port / "vcpkg.json").read_text(encoding="utf-8"))
        if manifest.get("name") != "ffmpeg":
            raise ValueError(f"Expected stable ffmpeg Port: {name}")
        for target in targets:
            signature = _manifest_signature(manifest, target.roots)
            groups.setdefault(signature, []).append((name, target.package))
    original = []
    coverage = []
    for index, group in enumerate(groups.values()):
        name, package = group[0]
        specs: dict[str, str] = {}
        graph = native_abi_query([package, "ffmpeg-tester"], triplet,
                                 port_overlay=overlay / ffmpeg_port_name(name), binary=binary,
                                 specs=specs, evidence=evidence / f"target-{index}" if evidence else None)
        batch = external_batch(graph, specs, triplet)
        original.append(batch)
        coverage.append({"targets": [list(t) for t in group], "batch": graph_digest(batch)})
    batches = merge_batches(original)
    # Prove that requesting the direct package specs (without FFmpeg overlay)
    # preserves every ABI. If an optimized merge fails, use exact original
    # batches, never silently accept a different dependency graph.
    try:
        for index, batch in enumerate(batches):
            verify_batch(batch, triplet, binary=binary,
                         evidence=evidence / f"direct-{index}" if evidence else None)
    except RuntimeError as error:
        print(f"Seed batch merge rejected; verifying original graphs: {error}", file=sys.stderr)
        batches = _unique(original)
        for index, batch in enumerate(batches):
            verify_batch(batch, triplet, binary=binary,
                         evidence=evidence / f"unmerged-{index}" if evidence else None)
    if _pairs(batches) != _pairs(original):
        raise RuntimeError("Seed plan does not cover all required ABI pairs")
    expected_targets = {(name, t.package) for name in names for t in targets}
    covered_targets = [tuple(t) for entry in coverage for t in entry["targets"]]
    if set(covered_targets) != expected_targets or len(covered_targets) != len(expected_targets):
        raise RuntimeError("Incomplete or duplicate dependency target coverage")
    result = {"triplet": triplet, "batches": batches, "coverage": coverage,
              "required": [list(pair) for pair in sorted(_pairs(original))]}
    result["key"] = seed_hash(batches)
    return result["key"], result


def validate_plan(plan: dict, triplet: str, expected: str | None = None) -> dict:
    if triplet not in TRIPLETS:
        raise ValueError(f"Unsupported FFmpeg Triplet: {triplet}")
    if plan["triplet"] != triplet or seed_hash(plan["batches"]) != plan["key"]:
        raise ValueError("Invalid dependency plan identity")
    if set(tuple(pair) for pair in plan["required"]) != _pairs(plan["batches"]):
        raise ValueError("Dependency plan does not cover required ABI pairs")
    if expected is not None and plan["key"] != expected:
        raise RuntimeError(f"Seed native ABI drift for {triplet}: planned {expected}, actual {plan['key']}")
    return plan


def verify_target_coverage(plans: dict, evidence: Path) -> int:
    """Check every actual target scan against the shared external ABI union."""
    graphs = sorted(evidence.rglob("graph.json"))
    if not graphs:
        raise ValueError("Missing actual target ABI evidence")
    count = 0
    for path in graphs:
        graph = json.loads(path.read_text(encoding="utf-8"))
        targets = [abi_identifier(k)[1] for k in graph if abi_identifier(k)[0] == "ffmpeg"]
        if len(targets) != 1:
            raise ValueError("Expected exactly one FFmpeg target in ABI evidence")
        triplet = targets[0]
        plan = validate_plan(plans[triplet], triplet)
        if f"ffmpeg-tester_{triplet}" not in graph:
            raise ValueError("Missing Tester ABI evidence")
        targets = {f"ffmpeg_{triplet}", f"ffmpeg-tester_{triplet}"}
        if {k for k in graph if abi_identifier(k)[0] in TARGET_PORTS} != targets:
            raise ValueError("Unexpected target or virtual package in ABI evidence")
        external = {(k, v) for k, v in graph.items() if k not in targets}
        if not external or external - _pairs(plan["batches"]):
            raise RuntimeError(f"Seed missing actual target ABI coverage: {path}: "
                               f"{sorted(external - _pairs(plan['batches']))}")
        count += 1
    return count


def load_seed_plan(path: Path, triplet: str, expected: str | None = None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_plan(data[triplet], triplet, expected)


def require_seed_archives(plan: dict, cache: Path) -> None:
    missing = []
    for abi in sorted(abi_set(plan["batches"])):
        archive = cache / abi[:2] / (abi + ".zip")
        if not archive.is_file() or not archive.stat().st_size:
            missing.append(abi)
    if missing:
        raise RuntimeError(f"Seed cache incomplete: {len(missing)} native ABI archives absent\n" +
                           "\n".join(missing))



def prune_seed_cache(plan: dict, cache: Path) -> int:
    """Remove obsolete ABI archives only in the explicitly supplied CI cache.

    Never call this on the shared local/repair cache (which may contain other
    Triplets). Only vcpkg files-provider archive names are eligible.
    """
    require_seed_archives(plan, cache)
    required = abi_set(plan["batches"])
    removed = 0
    for archive in cache.glob("*/*.zip"):
        if (not archive.is_symlink() and not archive.parent.is_symlink() and
                _ABI.fullmatch(archive.stem) and archive.parent.name == archive.stem[:2] and
                archive.stem not in required):
            archive.unlink()
            removed += 1
    return removed

def prepare_seed(*, triplet: str, overlay: Path = GENERATED_PORTS,
                 binary: Path | None = None, install_root: Path | None = None,
                 only_downloads: bool = False, plan: dict | None = None,
                 cache_only: bool = False, cache_dir: Path | None = None,
                 evidence: Path | None = None) -> tuple[str, ...]:
    """Execute validated external-only batches in isolated installation roots."""
    from .cache_guard import installed_abis
    if triplet not in TRIPLETS:
        raise ValueError(f"Unsupported FFmpeg Triplet: {triplet}")
    if only_downloads and cache_only:
        raise ValueError("Download-only and cache-only are mutually exclusive")
    if plan is None:
        _, plan = seed_identity(triplet=triplet, overlay=overlay, binary=binary, evidence=evidence)
    validate_plan(plan, triplet)
    if cache_only:
        if cache_dir is None:
            raise ValueError("Cache-only Seed requires an explicit binary cache")
        require_seed_archives(plan, cache_dir)
    root = install_root or Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "ffbuild-seed-roots"
    root.mkdir(parents=True, exist_ok=True)
    env = environment()
    if cache_dir is not None:
        env["VCPKG_BINARY_SOURCES"] = f"clear;files,{cache_dir.resolve()},{'read' if cache_only else 'readwrite'}"
    completed = []
    for index, batch in enumerate(plan["batches"]):
        # Native resolver must match before any package may compile.
        verify_batch(batch, triplet, binary=binary,
                     evidence=evidence / f"batch-{index}" if evidence else None)
        with tempfile.TemporaryDirectory(prefix=f"seed-{index}-", dir=root) as temporary:
            arguments = ["install", *sorted(batch["specs"].values()), f"--triplet={triplet}",
                         "--recurse", f"--x-install-root={temporary}",
                         f"--overlay-ports={(ROOT / 'ports').resolve()}",
                         f"--overlay-triplets={(ROOT / 'triplets').resolve()}",
                         "--no-print-usage"]
            if only_downloads:
                arguments.append("--only-downloads")
            elif cache_only:
                arguments.extend(("--only-binarycaching", "--clean-packages-after-build"))
            else:
                arguments.extend(("--clean-buildtrees-after-build", "--clean-packages-after-build"))
            print(f"vcpkg Seed {triplet}: batch {index + 1}/{len(plan['batches'])}", flush=True)
            subprocess.run(vcpkg_command(arguments, binary=binary), cwd=ROOT, env=env, check=True)
            if not only_downloads and installed_abis(Path(temporary)) != batch["abis"]:
                raise RuntimeError(f"Installed dependency ABIs differ from batch {index + 1}")
            completed.append(graph_digest(batch))
    return tuple(completed)
