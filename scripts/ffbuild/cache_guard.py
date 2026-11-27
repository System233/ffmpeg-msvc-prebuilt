"""Fail closed before a CI worker can compile an uncached dependency.

The shared Seed is expected to contain EVERY third-party package required by
this worker. vcpkg's own read-only native ABI query resolves the exact package
graph; the files binary provider uses <first-two-ABI-hex>/<full-ABI>.zip.
Only the selected FFmpeg Port and its Consumer Tester may be built by a Worker.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .native_abi import native_abi_query, planned_specs
from ffvcpkg import command as vcpkg_command
from .port import ffmpeg_port_name
from .versions import GENERATED_PORTS, ROOT


def verify_dependency_cache(job: dict, cache_dir: Path, *, abi_map: dict[str, str] | None = None) -> int:
    """Require a complete, nonempty vcpkg files binary cache for the job.

    This is a pre-build gate; no package is compiled or installed. A missing
    binary cache cannot silently fall back to compilation in the Worker.
    """
    for field in ("package", "port", "tester_port", "triplet", "yaml"):
        if not isinstance(job.get(field), str) or not job[field].strip():
            raise ValueError(f"Missing CI job attribute: {field}")
    triplet = job["triplet"]
    target = f'{job["port"]}_{triplet}'
    tester = f'{job["tester_port"]}_{triplet}'
    if job["port"] != "ffmpeg" or job["tester_port"] != "ffmpeg-tester":
        raise ValueError("Worker must install stable ffmpeg and ffmpeg-tester Ports")
    if abi_map is None:
        abi_map = native_abi_query([job["package"], job["tester_port"]], triplet,
                                   port_overlay=GENERATED_PORTS / ffmpeg_port_name(job["yaml"]))
    if not {target, tester}.issubset(abi_map):
        raise RuntimeError(
            f"Native ABI plan missing selected FFmpeg/Tester: {target}, {tester}")
    external = {name: abi for name, abi in abi_map.items()
                if name not in {target, tester}}
    if not external:
        raise RuntimeError("Refusing to claim cache reuse without an external dependency graph")
    cache_dir = cache_dir.resolve()
    missing = []
    for name, abi in sorted(external.items()):
        if not isinstance(abi, str) or len(abi) != 64 or any(
                char not in "0123456789abcdef" for char in abi):
            raise ValueError(f"Invalid native ABI for {name}: {abi!r}")
        archive = cache_dir / abi[:2] / f"{abi}.zip"
        if not archive.is_file() or archive.stat().st_size == 0:
            missing.append(f"{name} ({abi[:12]})")
    if missing:
        raise RuntimeError(
            f"Dependency Seed binary cache incomplete: {len(missing)}/{len(external)} "
            f"external packages missing from {cache_dir}. CI Worker must NOT "
            f"compile dependencies. Missing: {', '.join(missing[:20])}"
            + (f" (+{len(missing)-20} more)" if len(missing) > 20 else ""))
    print(f"PASS: {len(external)}/{len(external)} external packages have exact "
          f"native ABI binary cache archives; only {target} and {tester} may build.",
          flush=True)
    return len(external)


def verify_no_dependency_builds(job: dict, buildtrees: Path) -> None:
    """Post-build audit: only FFmpeg and its Tester may emit vcpkg build logs.

    A cache ZIP may exist but fail to restore, in which case vcpkg can still
    compile a fallback. Newly built Ports leave per-Port buildtree logs; a
    restored binary Port does not. Do not treat compiler-detection probes as
    third-party dependency builds.
    """
    allowed = {job["port"], job["tester_port"], "detect_compiler"}
    unexpected = []
    if not buildtrees.is_dir():
        raise RuntimeError(f"Expected native vcpkg buildtrees missing: {buildtrees}")
    for directory in sorted(buildtrees.iterdir()):
        if not directory.is_dir() or directory.name in allowed:
            continue
        if any(directory.rglob("*.log")) or any(directory.rglob("*.err")):
            unexpected.append(directory.name)
    if unexpected:
        raise RuntimeError("CI Worker rebuilt external dependencies instead of using "
                           f"the Seed binary cache: {', '.join(unexpected)}")
    print("PASS: FFmpeg Worker generated no third-party dependency build logs; "
          "only FFmpeg and Consumer Tester were allowed to build.", flush=True)


def load_job(job_env: str) -> dict:
    raw = os.environ.get(job_env)
    if not raw:
        raise ValueError(f"Missing CI job environment variable: {job_env}")
    job = json.loads(raw)
    if not isinstance(job, dict):
        raise ValueError(f"CI job {job_env} must be a JSON object")
    return job


def verify_from_environment(*, job_env: str, cache_dir: Path) -> int:
    return verify_dependency_cache(load_job(job_env), cache_dir)


def installed_abis(installed: Path) -> dict[str, str]:
    from .compliance import installed_status
    if not (installed / "vcpkg" / "status").is_file():
        return {}
    return {f"{name}_{arch}": value.abi for (name, arch), value in installed_status(installed).items()}


def require_target_plan(job: dict, *, port: Path, paths: list[str], env: dict,
                        expected: set[str]) -> None:
    """Require that native vcpkg plans only the explicitly allowed target actions."""
    args = ["install", job["package"], job["tester_port"], f"--triplet={job['triplet']}",
            f"--overlay-ports={port}", f"--overlay-ports={ROOT / 'ports'}", *paths,
            "--no-print-usage", "--dry-run"]
    result = subprocess.run(vcpkg_command(args), cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    if (any(line.startswith(("The following packages will be removed", "The following packages will be rebuilt"))
            for line in result.stdout.splitlines()) or set(planned_specs(result.stdout)) != expected):
        raise RuntimeError("Native target plan would install or rebuild an external dependency")


def restore_dependencies(job: dict, cache: Path, *, port: Path, installed: Path,
                         paths: list[str], env: dict, run=None) -> dict[str, str]:
    """Install exactly the external native feature graph, cache-only, before any target build.

    A failed binary restore cannot invoke the dependency's build. Then check
    actual installed ABIs and the remaining native install plan; never allow
    vcpkg to silently rebuild or replace an external package in the target run.
    """
    specs: dict[str, str] = {}
    triplet = job["triplet"]
    packages = [job["package"], job["tester_port"]]
    abis = native_abi_query(packages, triplet, port_overlay=port, env=env, specs=specs)
    verify_dependency_cache(job, cache, abi_map=abis)
    targets = {f"{job['port']}_{triplet}", f"{job['tester_port']}_{triplet}"}
    if job.get("abi_hash") and abis[f"{job['port']}_{triplet}"] != job["abi_hash"]:
        raise RuntimeError("Native target ABI differs from the Build Plan")
    external = {key: abi for key, abi in abis.items() if key not in targets}
    options = [f"--triplet={triplet}", f"--overlay-ports={port}",
               f"--overlay-ports={ROOT / 'ports'}", *paths, "--no-print-usage"]
    def invoke(args):
        command = vcpkg_command(args)
        if run is not None:
            run(command)
        else:
            subprocess.run(command, cwd=ROOT, env=env, check=True)
    if installed_abis(installed) != external:
        invoke(["install", *(specs[key] for key in sorted(external)), *options,
                "--only-binarycaching", "--recurse"])
    if installed_abis(installed) != external:
        raise RuntimeError("Restored dependencies differ from the exact native ABI graph")
    # In the real install root only target and Tester may remain to be built.
    require_target_plan(job, port=port, paths=paths, env=env, expected=targets)
    return abis
