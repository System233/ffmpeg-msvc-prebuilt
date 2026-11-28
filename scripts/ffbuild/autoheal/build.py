"""Native in-runner repair builds; no publication and no third-party rebuilds."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

from ffvcpkg import command as vcpkg_command
from ..cache_guard import (verify_dependency_cache, verify_no_dependency_builds, restore_dependencies,
                           installed_abis, require_target_plan)
from ..native_abi import native_abi_query
from ..package import _layout, _read_control, _verify_native_package_abi
from ..targets import Target, compile_target, parse_package
from ..versions import GENERATED_PORTS, ROOT, TRIPLETS, config, generate
from .models import version_name
from .scope import check_worktree

_SPEC = re.compile(r"ffmpeg\[(all-(?:gpl|lgpl|nonfree))(,static)?\]:([a-z0-9-]+)\Z")
_MACHINE = {"x86-windows": 0x14c, "x64-windows": 0x8664,
            "arm-windows": 0x1c4, "arm64-windows": 0xaa64}


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
    return Path(os.environ["FFBUILD_REPAIR_CACHE"]).resolve()


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
        if target.triplet not in {j["triplet"] for j in failed}:
            raise ValueError("Select a representative affected architecture")
        static = "static" in target.roots
        if static != all(j["linkage"] == "static" for j in failed):
            raise ValueError("Use shared for shared failures; static for static-only failure groups")
        if "all-lgpl" in target.roots and any(j["license"] != "lgpl" for j in failed):
            raise ValueError("LGPL fallback is only for LGPL-specific failures")
        if any(j["license"] == "nonfree" for j in failed) and "all-nonfree" not in target.roots:
            raise ValueError("Nonfree failures require nonfree coverage")
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
        abis = native_abi_query([job["package"], "ffmpeg-tester"], job["triplet"], port_overlay=port, env=build_env(job["triplet"]))
        verify_dependency_cache(job, cache, abi_map=abis)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise EnvironmentFailure(str(exc)) from exc
    # The Seed must never supply FFmpeg/Tester binaries: acceptance requires a real build.
    for name in ("ffmpeg", "ffmpeg-tester"):
        abi = abis[f"{name}_{job['triplet']}"]
        if (cache / abi[:2] / (abi + ".zip")).exists():
            raise EnvironmentFailure("Dependency Seed contains a target/Tester archive")
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
                            f"--url=https://github.com/ffmpeg/ffmpeg/archive/{ref}.tar.gz"]),
             env=dict(os.environ), log=runtime_dir() / "source-download.log")
    except (OSError, BuildFailure) as exc:
        raise EnvironmentFailure("Pinned FFmpeg source could not be prepared") from exc


def preflight(data: dict) -> None:
    """Restore exact dependency graphs before invoking the model. Fill a missing Seed locally."""
    from ..seed import prepare_seed
    from ..builder import patch_arm_sdk
    if "arm-windows" in data["triplets"]:
        patch_arm_sdk()
    port = prepare_port(data)
    prefetch_source(data)
    for triplet in data["triplets"]:
        specs = set()
        for diagnostic in data["diagnostics"]:
            plan = diagnostic["build_plan"]
            if plan["triplet"] != triplet:
                continue
            specs.add(spec_string(plan["package"], triplet))
            suffix = ",static" if plan["linkage"] == "static" else ""
            specs.add(spec_string(f"ffmpeg[all-gpl{suffix}]", triplet))
        jobs = [job_for(value, data) for value in sorted(specs)]
        try:
            for job in jobs:
                cached_abis(job, port)
        except EnvironmentFailure:
            cache = cache_dir(triplet)
            cache.mkdir(parents=True, exist_ok=True)
            old = os.environ.get("VCPKG_BINARY_SOURCES")
            os.environ["VCPKG_BINARY_SOURCES"] = f"clear;files,{cache},readwrite"
            try:
                prepare_seed(triplet=triplet)
            finally:
                if old is None:
                    os.environ.pop("VCPKG_BINARY_SOURCES", None)
                else:
                    os.environ["VCPKG_BINARY_SOURCES"] = old
            # A failed or incomplete dependency preparation aborts before Pi.
            for job in jobs:
                cached_abis(job, port)
    (runtime_dir() / "ready.json").write_text(json.dumps(bindings()), encoding="utf-8")
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


_PRIVATE_RUNNER_ENV = frozenset({"OPENAI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STEP_SUMMARY"})


def build_env(triplet: str) -> dict:
    env = {key: value for key, value in os.environ.items() if key.upper() not in _PRIVATE_RUNNER_ENV}
    env["VCPKG_BINARY_SOURCES"] = f"clear;files,{cache_dir(triplet)},read"
    return env


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
        _run(vcpkg_command(["remove", *targets, "--recurse", f"--overlay-triplets={ROOT / 'triplets'}", *_native_paths()]),
             env=env, log=runtime_dir() / "remove.log")


def pe_machine(path: Path) -> int:
    with path.open("rb") as f:
        if f.read(2) != b"MZ":
            raise ValueError(f"Not a PE executable: {path}")
        f.seek(0x3c)
        offset_raw = f.read(4)
        if len(offset_raw) != 4:
            raise ValueError(f"Truncated PE header: {path}")
        offset = struct.unpack("<I", offset_raw)[0]
        f.seek(offset)
        if f.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {path}")
        raw = f.read(2)
        if len(raw) != 2:
            raise ValueError(f"Truncated PE machine field: {path}")
        return struct.unpack("<H", raw)[0]


def can_execute(triplet: str) -> bool:
    """Ask Windows about native/guest machine support, never infer from target name alone."""
    if os.name != "nt":
        return False
    machine = _MACHINE[triplet]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        native, process = ctypes.c_ushort(), ctypes.c_ushort()
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.IsWow64Process2.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort)]
        kernel.IsWow64Process2.restype = ctypes.c_int
        if not kernel.IsWow64Process2(kernel.GetCurrentProcess(), ctypes.byref(process), ctypes.byref(native)):
            return False
        if machine == native.value:
            return True
        supported = ctypes.c_int()
        kernel.IsWow64GuestMachineSupported.argtypes = [ctypes.c_ushort, ctypes.POINTER(ctypes.c_int)]
        kernel.IsWow64GuestMachineSupported.restype = ctypes.c_int
        return kernel.IsWow64GuestMachineSupported(machine, ctypes.byref(supported)) == 0 and bool(supported.value)
    except AttributeError:
        # Unknown compatibility is not a claim that execution succeeded.
        return False


def coff_archive_machines(path: Path) -> set[int]:
    """Read COFF object/import headers without loading multi-GB static archives."""
    machines = set()
    length = path.stat().st_size
    with path.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise ValueError(f"Invalid COFF library: {path}")
        while stream.tell() < length:
            header = stream.read(60)
            if len(header) != 60 or header[58:] != b"`\n":
                raise ValueError(f"Invalid archive member header: {path}")
            name = header[:16].rstrip()
            size = int(header[48:58])
            start = stream.tell()
            end = start + size
            if size < 0 or end > length:
                raise ValueError(f"Truncated archive member: {path}")
            if name not in (b"/", b"//", b"/SYM64/"):
                if name.startswith(b"#1/"):
                    stream.seek(int(name[3:]), 1)
                if end - stream.tell() < 8:
                    raise ValueError(f"Truncated COFF object: {path}")
                head = stream.read(8)
                # Import-object and anonymous bigobj headers store Machine at +6.
                offset = 6 if head[:4] == b"\0\0\xff\xff" else 0
                machines.add(struct.unpack_from("<H", head, offset)[0])
            stream.seek(end + size % 2)
    if not machines:
        raise ValueError(f"No COFF objects in {path}")
    return machines


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
    libs = ["avutil", "avcodec", "avformat", "avdevice", "avfilter", "swresample", "swscale"]
    for optional in ("postproc", "avresample"):
        if (prefix / "lib" / (optional + ".lib")).is_file():
            libs.append(optional)
    expected = {f"check-{mode}{lib}.exe" for lib in libs for mode in ("", "full-", "legacy-")}
    expected.update(f"check-{mode}transitive-{lib}.exe"
                    for lib in libs if lib not in ("avutil", "postproc", "avresample")
                    for mode in ("", "full-", "legacy-"))
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
    if can_execute(triplet):
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
                _run([str(isolated_exe)], env=isolated(selected / "bin"), cwd=smoke,
                     log=smoke / (cfg + "-" + path.stem + ".log"), timeout=60)
                count += 1
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
    return {"spec": spec_string(job["package"], triplet), "abi_hash": abi,
            "ffmpeg_build": "passed", "consumer_compile_link": "passed",
            "binary_inspection": "passed", "tester_targets": {k: len(v) for k, v in testers.items()},
            "runtime": runtime, "external_dependency_builds": 0}


def build(value: str, *, clean: bool = False) -> dict:
    data = context()
    job = job_for(value, data)
    port = prepare_port(data)
    abis = cached_abis(job, port)
    triplet = job["triplet"]
    abi = abis[f"ffmpeg_{triplet}"]
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
                                        paths=_native_paths(), env=env,
                                        run=lambda args: _run(args, env=env, log=root / "restore-dependencies.log"))
        if restored != abis:
            raise RuntimeError("Native dependency graph changed during restore")
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise EnvironmentFailure(str(exc)) from exc
    error = None
    try:
        _run(vcpkg_command(["install", job["package"], "ffmpeg-tester", f"--triplet={triplet}",
                            f"--overlay-ports={port}", f"--overlay-ports={ROOT / 'ports'}",
                            *_native_paths()]), env=env, log=log)
    except BuildFailure as exc:
        error = exc
    try:
        verify_no_dependency_builds(job, buildtrees)
    except RuntimeError as exc:
        raise EnvironmentFailure(str(exc)) from exc
    if error:
        from .policy import INFRA_ERROR, VCPKG_PACKAGE_FAILURE, TARGET_PACKAGE
        text = log.read_text(encoding="utf-8", errors="replace")
        if INFRA_ERROR.search(text) or any(not TARGET_PACKAGE.fullmatch(name) for name in VCPKG_PACKAGE_FAILURE.findall(text)):
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
            _run(vcpkg_command(["install", job["package"], "ffmpeg-tester", f"--triplet={triplet}",
                                f"--overlay-ports={port}", f"--overlay-ports={ROOT / 'ports'}",
                                *_native_paths()]), env=env, log=root / "tester.log")
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
        counts = check.get("tester_targets")
        if (not isinstance(counts, dict) or set(counts) != {"release", "debug"}
                or counts["release"] not in (39, 42, 45) or counts["debug"] != counts["release"]):
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


def status() -> dict:
    data = context()
    file = runtime_dir() / "last-result.json"
    return {"target": data["target_yaml"], "triplets": data["triplets"],
            "runtime_targets": [t for t in data["triplets"] if can_execute(t)],
            "last_result": json.loads(file.read_text(encoding="utf-8")) if file.is_file() else None}
