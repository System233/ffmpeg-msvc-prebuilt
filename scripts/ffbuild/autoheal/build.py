"""Native in-runner repair builds; no publication and no third-party rebuilds."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ffvcpkg import command as vcpkg_command, environment
from ..cache_guard import (verify_dependency_cache, verify_no_dependency_builds, restore_dependencies,
                           installed_abis, require_target_plan, install_target)
from ..native_abi import native_abi_query
from ..package import _layout, _read_control, _verify_native_package_abi
from ..targets import Target, compile_target, load_targets, parse_package
from ..sdk_validation import (_sdk_modules, expected_modules, tester_targets,
                              assert_installed_evidence, validate_installed)
from ..native_platform import (PE_MACHINE as _MACHINE, NATIVE_RUNTIME_TRIPLETS as _NATIVE_RUNTIME,
                               pe_machine, coff_archive_machines, can_execute)
from ..process import PRIVATE_RUNNER_ENV as _PRIVATE_RUNNER_ENV
from ..versions import GENERATED_PORTS, ROOT, TRIPLETS, config, generate
from .models import version_name
from .scope import check_worktree

_SPEC = re.compile(r"ffmpeg\[(all-(?:gpl|lgpl|nonfree))(,static)?\]:([a-z0-9-]+)\Z")


class EnvironmentFailure(RuntimeError):
    """The repair agent must not fix the infrastructure or external packages."""


class BuildFailure(RuntimeError):
    """A native FFmpeg or consumer validation failed."""


def bindings() -> dict:
    return {"context_sha256": os.environ["FFBUILD_REPAIR_CONTEXT_SHA256"],
            "contract_sha256": os.environ["FFBUILD_REPAIR_CONTRACT_SHA256"]}


def context() -> dict:
    raw = (ROOT / "agent_context.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != bindings()["context_sha256"]:
        raise ValueError("Prepared repair context was modified")
    data = json.loads(raw)
    if (data["target_yaml"] != os.environ["FFBUILD_REPAIR_TARGET"]
            or data["base_sha"] != os.environ["FFBUILD_REPAIR_BASE"]):
        raise ValueError("Repair context is not bound to the supervisor")
    return data


def runtime_dir() -> Path:
    return Path(os.environ["FFBUILD_REPAIR_DIR"]).resolve()


def cache_dir(triplet: str) -> Path:
    if triplet not in TRIPLETS:
        raise ValueError("Unknown target triplet")
    return Path(os.environ["FFBUILD_CACHE_DIR"]).resolve()


def parse_spec(value: str) -> Target:
    match = _SPEC.fullmatch(value) if isinstance(value, str) else None
    if not match or match[3] not in TRIPLETS:
        raise ValueError("Use ffmpeg[all-gpl[,static]]:<triplet> (or all-nonfree/all-lgpl)")
    package, roots = parse_package(value.split(":", 1)[0])
    return Target(package, match[3], roots)


def spec_string(package: str, triplet: str) -> str:
    return package + ":" + triplet


def pin_args(data: dict) -> dict:
    if data["target_yaml"] != "master":
        return {}
    snapshot = data["source_snapshot"]
    return {"source_version": snapshot["ref"], "ref": snapshot["commit"],
            "sha512": snapshot["sha512"]}


def version_for(data: dict) -> str:
    return (data["source_snapshot"]["ref"].removeprefix("n").split("-", 1)[0]
            if data["target_yaml"] == "master" else data["target_yaml"])


def job_for(value: str, data: dict) -> dict:
    target = parse_spec(value)
    if target.triplet not in data["triplets"]:
        raise ValueError("Target triplet was not prepared for this incident")
    yaml = version_name(data["target_yaml"])
    return dict(compile_target(config(yaml), version_for(data), target),
                yaml=yaml, port="ffmpeg", tester_port="ffmpeg-tester")


def validate_plan(raw: dict, data: dict) -> list[dict]:
    """Agent selects representative builds; every observed failed job is accounted for."""
    if not isinstance(raw, dict) or set(raw) != {"checks"} or not isinstance(raw["checks"], list):
        raise ValueError("Validation plan must contain a checks list")
    diagnostics = {j["job_id"]: j for j in data["diagnostics"]}
    if not diagnostics or not 1 <= len(raw["checks"]) <= len(diagnostics):
        raise ValueError("Validation plan must cover the incident")
    configured = set(load_targets())
    seen = set()
    specs = set()
    result = []
    for item in raw["checks"]:
        if not isinstance(item, dict) or set(item) != {"spec", "jobs", "reason"}:
            raise ValueError("Each check requires spec, jobs and reason")
        value = item["spec"]
        target = parse_spec(value)
        spec = spec_string(target.package, target.triplet)
        if spec in specs:
            raise ValueError("Duplicate representative variant")
        specs.add(spec)
        jobs, reason = item["jobs"], item["reason"]
        if (not isinstance(jobs, list) or not jobs or any(type(j) is not int for j in jobs)
                or len(set(jobs)) != len(jobs) or seen.intersection(jobs)
                or any(j not in diagnostics for j in jobs)):
            raise ValueError("Failed job IDs must be covered exactly once")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError("Explain the representative selection and failure reproduction")
        failed = [diagnostics[j]["build_plan"] for j in jobs]
        if target not in configured or any(j["license"] == "nonfree" for j in failed):
            raise ValueError("Representative target is outside the configured CI matrix")
        if target.triplet not in {j["triplet"] for j in failed}:
            raise ValueError("Select a representative affected architecture")
        static = "static" in target.roots
        if static != all(j["linkage"] == "static" for j in failed):
            raise ValueError("Use shared for shared failures; static for static-only failure groups")
        if "all-lgpl" in target.roots and any(j["license"] != "lgpl" for j in failed):
            raise ValueError("LGPL fallback is only for LGPL-specific failures")
        seen.update(jobs)
        result.append({"spec": spec, "jobs": jobs, "reason": reason})
    if seen != set(diagnostics):
        raise ValueError("Validation plan omitted failed jobs")
    return result


def contract(port: Path) -> dict:
    manifest = json.loads((port / "vcpkg.json").read_text(encoding="utf-8"))
    return {"dependencies": manifest["dependencies"], "defaults": manifest["default-features"],
            "features": {key: item.get("dependencies", []) for key, item in manifest["features"].items()},
            "policy": (port / "policy.cmake").read_text(encoding="utf-8")}


def prepare_port(data: dict) -> Path:
    check_worktree(data["target_yaml"], data["base_sha"], ROOT, allow_empty=True)
    port = generate(data["target_yaml"], **pin_args(data))
    raw = (runtime_dir() / "contract.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != bindings()["contract_sha256"]:
        raise ValueError("Prepared dependency contract was modified")
    original = json.loads(raw)
    if contract(port) != original:
        raise ValueError("Candidate changed the baseline dependency/feature/license contract")
    return port


def cached_abis(job: dict, port: Path) -> dict[str, str]:
    cache = cache_dir(job["triplet"])
    try:
        abis = native_abi_query([job["package"], "ffmpeg-tester"], job["triplet"],
                                port_overlay=port, env=build_env(job["triplet"]),
                                evidence=runtime_dir() / "abi-evidence" / "targets" / job["triplet"] /
                                (job["license"] + "-" + job["linkage"]))
        verify_dependency_cache(job, cache, abi_map=abis)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise EnvironmentFailure(str(exc)) from exc
    return abis


def prefetch_source(data: dict) -> None:
    """Verify/download the pinned source before model execution."""
    pin = pin_args(data)
    source = config(data["target_yaml"])["source"]
    ref = pin.get("ref") or source["ref"].replace("${VERSION}", data["target_yaml"])
    digest = pin.get("sha512") or source["sha512"]
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", ref) or not re.fullmatch(r"[0-9a-fA-F]{128}", digest):
        raise EnvironmentFailure("Invalid pinned source identity")
    archive = Path(os.environ["VCPKG_ROOT"]) / "downloads" / f"ffmpeg-ffmpeg-{ref}.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.is_file():
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha512").hexdigest() == digest.lower():
                return
        archive.unlink()
    try:
        _run(vcpkg_command(["x-download", str(archive), digest,
                            f"--url=https://github.com/ffmpeg/ffmpeg/archive/{ref}.tar.gz"], env=os.environ),
             env=dict(os.environ), log=runtime_dir() / "source-download.log")
    except (OSError, BuildFailure) as exc:
        raise EnvironmentFailure("Pinned FFmpeg source could not be prepared") from exc


def preflight(data: dict) -> None:
    """Restore exact dependency graphs before invoking the model. Fill a missing Seed locally."""
    from ..seed import populate_cache, load_seed_plan, DEFAULT_PLAN
    ready = runtime_dir() / "ready.json"
    ready.unlink(missing_ok=True)
    port = prepare_port(data)
    prefetch_source(data)
    configured = set(load_targets())
    for triplet in data["triplets"]:
        seed_plan = load_seed_plan(DEFAULT_PLAN, triplet)
        cache = cache_dir(triplet)
        cache.mkdir(parents=True, exist_ok=True)
        populate_cache(triplet=triplet, plan=seed_plan, cache_dir=cache,
                       evidence=runtime_dir() / "abi-evidence" / "preflight" / triplet)
        specs = set()
        failed = {}
        for diagnostic in data["diagnostics"]:
            plan = diagnostic["build_plan"]
            if plan["triplet"] != triplet:
                continue
            value = spec_string(plan["package"], triplet)
            specs.add(value)
            failed[value] = plan
            suffix = ",static" if plan["linkage"] == "static" else ""
            representative = spec_string(f"ffmpeg[all-gpl{suffix}]", triplet)
            if parse_spec(representative) in configured:
                specs.add(representative)
        for value in sorted(specs):
            graph = cached_abis(job_for(value, data), port)
            previous = failed.get(value, {})
            old_abi = previous.get("abi_hash")
            if old_abi and old_abi != graph[f"ffmpeg_{triplet}"]:
                print(f"Original failed ABI differs on the current Runner for {value}: "
                      f"{old_abi} -> {graph[f'ffmpeg_{triplet}']}", flush=True)
            old_graph = previous.get("native_graph_sha256")
            if old_graph:
                from ..native_abi import graph_digest
                if old_graph != graph_digest(graph):
                    print(f"Original native graph differs on the current Runner for {value}", flush=True)
    ready.write_text(json.dumps(bindings()), encoding="utf-8")
    print("Repair dependency environment ready.", flush=True)


def _run(args: list[str], *, env: dict, log: Path, cwd: Path = ROOT, timeout: float | None = None) -> None:
    """Stream build output and retain its log, without passing model/GitHub secrets."""
    log.parent.mkdir(parents=True, exist_ok=True)
    if timeout is not None:
        # Runtime checks must not hang indefinitely on loader errors or crashes.
        try:
            with log.open("w", encoding="utf-8") as stream:
                code = subprocess.run(args, cwd=cwd, env=env, stdout=stream,
                                      stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired as exc:
            raise BuildFailure(f"Runtime check timed out after {timeout}s; log: {log}") from exc
        if code:
            raise BuildFailure(f"Runtime check failed ({code}); log: {log}")
        return
    with log.open("w", encoding="utf-8") as stream:
        with subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as proc:
            for line in proc.stdout:
                stream.write(line)
                print(line, end="", flush=True)
            code = proc.wait()
    if code:
        raise BuildFailure(f"Command failed ({code}); log: {log}")


def build_env(triplet: str) -> dict:
    env = {key: value for key, value in os.environ.items() if key.upper() not in _PRIVATE_RUNNER_ENV}
    env["VCPKG_BINARY_SOURCES"] = f"clear;files,{cache_dir(triplet)},read"
    return environment(env)


def _remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _layout_paths() -> tuple[Path, Path, Path]:
    root = runtime_dir()
    return root / "installed", root / "buildtrees", root / "packages"


def _native_paths() -> list[str]:
    installed, buildtrees, packages = _layout_paths()
    return [f"--x-install-root={installed}", f"--x-buildtrees-root={buildtrees}",
            f"--x-packages-root={packages}"]


def _remove_targets(triplet: str, env: dict, ports: tuple[str, ...] = ("ffmpeg-tester", "ffmpeg")) -> None:
    installed, _, _ = _layout_paths()
    status = installed / "vcpkg" / "status"
    if not status.is_file():
        return
    text = status.read_text(encoding="utf-8")
    targets = []
    for port in ports:
        if any(f"Package: {port}\n" in entry + "\n" and f"Architecture: {triplet}\n" in entry + "\n"
               and "Status: install ok installed" in entry for entry in text.split("\n\n")):
            targets.append(f"{port}:{triplet}")
    if targets:
        _run(vcpkg_command(["remove", *targets, "--recurse", f"--overlay-triplets={ROOT / 'triplets'}", *_native_paths()], env=env),
             env=env, log=runtime_dir() / "remove.log")


def verify_outputs(job: dict, abi: str) -> dict:
    installed, buildtrees, packages = _layout_paths()
    triplet = job["triplet"]
    package = packages / f"ffmpeg_{triplet}"
    _verify_native_package_abi(package, "ffmpeg", abi)
    _, _, features, _ = _read_control(package)
    features -= {"core"}
    if features != set(job["features"]) or _layout(package) != job["linkage"]:
        raise BuildFailure("Installed FFmpeg feature closure or linkage differs from the selected target")
    prefix = installed / triplet
    _verify_native_package_abi(prefix, "ffmpeg", abi)
    tools = prefix / "tools" / "ffmpeg"
    libs = sorted(_sdk_modules(prefix, required=job["features"], installed=True))
    if _sdk_modules(prefix / "debug", required=job["features"], installed=True) != set(libs):
        raise BuildFailure("Release/Debug Tester module inventory differs")
    expected = {name + ".exe" for name in tester_targets(libs)}
    testers = {}
    for cfg, suffix in (("release", "rel"), ("debug", "dbg")):
        folder = buildtrees / "ffmpeg-tester" / f"{triplet}-{suffix}"
        paths = sorted(folder.rglob("check-*.exe"))
        if {p.name for p in paths} != expected or len(paths) != len(expected):
            raise BuildFailure(f"Incomplete {cfg} Tester executables ({len(paths)}/{len(expected)})")
        testers[cfg] = paths
        selected = prefix if cfg == "release" else prefix / "debug"
        for lib in libs:
            candidates = list((selected / "lib").glob(f"*{lib}*.lib"))
            if not candidates:
                raise BuildFailure(f"Missing {cfg} consumer library: {lib}")
            for path in candidates:
                if coff_archive_machines(path) != {_MACHINE[triplet]}:
                    raise BuildFailure(f"COFF library architecture mismatch: {path}")
    cli = [tools / (name + ".exe") for name in ("ffmpeg", "ffprobe", "ffplay") if name in features]
    binaries = [*cli, *testers["release"], *testers["debug"]]
    if job["linkage"] == "shared":
        for selected in (prefix, prefix / "debug"):
            dlls = list((selected / "bin").glob("*.dll"))
            for lib in libs:
                if not any(p.name.startswith(lib + "-") or p.name.startswith(lib + ".") for p in dlls):
                    raise BuildFailure(f"Missing shared library {lib} in {selected}")
            binaries.extend(dlls)
    if any(pe_machine(path) != _MACHINE[triplet] for path in binaries):
        raise BuildFailure("Target PE architecture mismatch")
    runtime = {"status": "skipped", "reason": "host_architecture_incompatible"}
    execute = can_execute(triplet)
    if triplet in _NATIVE_RUNTIME and not execute:
        raise EnvironmentFailure("Required native x64/x86 runtime execution is unavailable")
    if execute:
        from ..sdk_validation import _runtime_env
        def isolated(bin_dir: Path) -> dict:
            return {k: v for k, v in _runtime_env(bin_dir).items()
                    if k.upper() not in _PRIVATE_RUNNER_ENV}
        smoke = runtime_dir() / "smoke"
        _remove(smoke)
        smoke.mkdir(parents=True)
        count = 0
        for cfg, paths in testers.items():
            selected = prefix if cfg == "release" else prefix / "debug"
            for path in paths:
                isolated_exe = smoke / (cfg + "-" + path.name)
                shutil.copyfile(path, isolated_exe)
                try:
                    _run([str(isolated_exe)], env=isolated(selected / "bin"), cwd=smoke,
                         log=smoke / (cfg + "-" + path.stem + ".log"), timeout=60)
                    count += 1
                finally:
                    # Static consumer images can be hundreds of MB each.
                    # Keep the log, not a redundant copy of the executable.
                    isolated_exe.unlink(missing_ok=True)
        for path in cli:
            isolated_exe = smoke / path.name
            shutil.copyfile(path, isolated_exe)
            _run([str(isolated_exe), "-version"], env=isolated(prefix / "bin"), cwd=smoke,
                 log=smoke / (path.stem + "-version.log"), timeout=60)
        if (tools / "ffmpeg.exe") in cli and "x264" in features:
            ffmpeg = str(smoke / "ffmpeg.exe")
            env = isolated(prefix / "bin")
            sample = smoke / "sample.mp4"
            _run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=128x96:rate=10",
                  "-t", "1", "-c:v", "libx264", str(sample)], env=env, cwd=smoke, log=smoke / "encode.log", timeout=120)
            _run([ffmpeg, "-v", "error", "-i", str(sample), "-f", "null", "-"],
                 env=env, cwd=smoke, log=smoke / "decode.log", timeout=120)
        runtime = {"status": "passed", "tester_executions": count, "cli_executions": len(cli)}
    try:
        consumer_cases = validate_installed(
            prefix, triplet=triplet, linkage=job["linkage"], features=job["features"],
            pkgconf=installed / "x64-windows/tools/pkgconf/pkgconf.exe")
        assert_installed_evidence(consumer_cases, libs, linkage=job["linkage"], runtime=runtime["status"])
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        raise BuildFailure(f"Independent SDK consumer validation failed: {exc}") from exc
    return {"spec": spec_string(job["package"], triplet), "abi_hash": abi,
            "ffmpeg_build": "passed", "consumer_compile_link": "passed",
            "binary_inspection": "passed", "tester_targets": {k: len(v) for k, v in testers.items()},
            "tester_modules": libs,
            "tester_cases": {k: sorted(p.stem for p in v) for k, v in testers.items()},
            "runtime": runtime, "consumer_cases": consumer_cases, "external_dependency_builds": 0}


def build(value: str, *, clean: bool = False) -> dict:
    data = context()
    job = job_for(value, data)
    port = prepare_port(data)
    triplet = job["triplet"]
    env = build_env(triplet)
    installed, buildtrees, packages = _layout_paths()
    root = runtime_dir()
    state = root / "active-spec.txt"
    current = spec_string(job["package"], triplet)
    (root / "last-result.json").unlink(missing_ok=True)
    if clean or not state.is_file() or state.read_text(encoding="utf-8") != current:
        for path in (installed, buildtrees, packages):
            _remove(path)
    else:
        _remove_targets(triplet, env)
    for name in ("ffmpeg", "ffmpeg-tester"):
        _remove(buildtrees / name)
        _remove(packages / f"{name}_{triplet}")
    state.write_text(current, encoding="utf-8")
    log = root / "build.log"
    try:
        restored = restore_dependencies(job, cache_dir(triplet), port=port, installed=installed,
                                        paths=_native_paths(), env=env, candidate=True,
                                        run=lambda args: _run(args, env=env, log=root / "restore-dependencies.log"))
        abi = restored[f"ffmpeg_{triplet}"]
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise EnvironmentFailure(str(exc)) from exc
    error = None
    try:
        install_target(job, port=port, paths=_native_paths(), env=env,
                       run=lambda args: _run(args, env=env, log=log))
    except BuildFailure as exc:
        error = exc
    try:
        verify_no_dependency_builds(job, buildtrees)
    except RuntimeError as exc:
        raise EnvironmentFailure(str(exc)) from exc
    if error:
        from .policy import INFRA_ERROR, VCPKG_PACKAGE_FAILURE, TARGET_PORTS
        text = log.read_text(encoding="utf-8", errors="replace")
        if INFRA_ERROR.search(text) or any(name.lower() not in TARGET_PORTS for name in VCPKG_PACKAGE_FAILURE.findall(text)):
            raise EnvironmentFailure(str(error))
        raise error
    result = verify_outputs(job, abi)
    (root / "last-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def test(value: str, *, rebuild_tester: bool = True) -> dict:
    """Re-run consumer tests (or smoke only) on the exact active candidate."""
    data = context()
    job = job_for(value, data)
    port = prepare_port(data)
    triplet = job["triplet"]
    abis = cached_abis(job, port)
    abi = abis[f"ffmpeg_{triplet}"]
    current = spec_string(job["package"], triplet)
    root = runtime_dir()
    state = root / "active-spec.txt"
    if not state.is_file() or state.read_text(encoding="utf-8") != current:
        raise BuildFailure("Build the selected variant first")
    installed, buildtrees, packages = _layout_paths()
    _verify_native_package_abi(packages / f"ffmpeg_{triplet}", "ffmpeg", abi)
    if rebuild_tester:
        env = build_env(triplet)
        _remove_targets(triplet, env, ("ffmpeg-tester",))
        _remove(buildtrees / "ffmpeg-tester")
        _remove(packages / f"ffmpeg-tester_{triplet}")
        tester = f"ffmpeg-tester_{triplet}"
        if installed_abis(installed) != {key: value for key, value in abis.items() if key != tester}:
            raise EnvironmentFailure("Installed dependency/FFmpeg ABI graph differs before Tester rebuild")
        try:
            require_target_plan(job, port=port, paths=_native_paths(), env=env, expected={tester})
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
            raise EnvironmentFailure(str(exc)) from exc
        try:
            install_target(job, port=port, paths=_native_paths(), env=env,
                           run=lambda args: _run(args, env=env, log=root / "tester.log"))
        finally:
            try:
                verify_no_dependency_builds(job, buildtrees)
            except RuntimeError as exc:
                raise EnvironmentFailure(str(exc)) from exc
    result = verify_outputs(job, abi)
    (root / "last-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def validate_evidence(evidence: dict, data: dict) -> None:
    """Portable gate for the independent supervisor and privileged delivery."""
    from .models import commit_sha
    if not isinstance(evidence, dict) or evidence.get("schema") != 1:
        raise ValueError("Missing native repair validation evidence")
    commit_sha(evidence.get("candidate"))
    commit_sha(evidence.get("tree"))
    checks = evidence.get("checks")
    if not isinstance(checks, list) or not all(isinstance(check, dict) for check in checks):
        raise ValueError("Missing native validation checks")
    validate_plan({"checks": [{key: check.get(key) for key in ("spec", "jobs", "reason")}
                              for check in checks]}, data)
    for check in checks:
        if not re.fullmatch(r"[0-9a-f]{64}", str(check.get("abi_hash", ""))):
            raise ValueError("Missing verified native ABI")
        if any(check.get(key) != "passed" for key in ("ffmpeg_build", "consumer_compile_link", "binary_inspection")):
            raise ValueError("Unverified FFmpeg/Tester build")
        if type(check.get("external_dependency_builds")) is not int or check["external_dependency_builds"] != 0:
            raise ValueError("External dependencies may not be rebuilt during repair")
        modules = check.get("tester_modules")
        if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules) or modules != sorted(set(modules)):
            raise ValueError("Invalid Tester module evidence")
        # Reconstruct the required modules independently of the built SDK.
        # The incident's pinned version and feature contract determines
        # historical optional modules; actual extra upstream modules are
        # allowed only if the same explicit probe plan covers them.
        required = expected_modules()
        if "target_yaml" in data:
            selected = compile_target(config(version_name(data["target_yaml"])), version_for(data),
                                      parse_spec(check["spec"]))
            required = expected_modules(selected["features"])
        if not required <= set(modules):
            raise ValueError("Required Tester module omitted")
        expected = sorted(tester_targets(modules))
        cases = check.get("tester_cases")
        counts = check.get("tester_targets")
        if (cases != {"release": expected, "debug": expected}
                or counts != {"release": len(expected), "debug": len(expected)}):
            raise ValueError("Incomplete Tester verification")
        runtime = check.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("Missing target runtime status")
        if runtime.get("status") == "passed":
            if (runtime.get("tester_executions") != sum(counts.values())
                    or type(runtime.get("cli_executions")) is not int or runtime["cli_executions"] < 1):
                raise ValueError("Incomplete native runtime verification")
        elif runtime != {"status": "skipped", "reason": "host_architecture_incompatible"}:
            raise ValueError("Unsupported runtime result")
        target = parse_spec(check["spec"])
        if target.triplet in _NATIVE_RUNTIME and runtime["status"] != "passed":
            raise ValueError("Native x64/x86 runtime execution is mandatory")
        assert_installed_evidence(check.get("consumer_cases"), modules,
                                  linkage="static" if "static" in target.roots else "shared",
                                  runtime=runtime["status"])


def status() -> dict:
    data = context()
    file = runtime_dir() / "last-result.json"
    return {"target": data["target_yaml"], "triplets": data["triplets"],
            "runtime_targets": [t for t in data["triplets"] if can_execute(t)],
            "last_result": json.loads(file.read_text(encoding="utf-8")) if file.is_file() else None}
