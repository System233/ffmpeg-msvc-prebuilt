"""Independent consumer acceptance of installed and public FFmpeg SDKs."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
import shutil
import shlex
import tempfile
import zipfile
from pathlib import Path

import yaml

from .versions import ROOT
from .process import run_bounded, PRIVATE_RUNNER_ENV
from .native_platform import (VS_PLATFORM as _ARCH, PE_MACHINE,
                              NATIVE_RUNTIME_TRIPLETS as _NATIVE_RUNTIME, pe_machine, can_execute)

_CONFIGS = ("Release", "Debug")
_CONSUMER_MODES = ("CONFIG", "MODULE", "LEGACY", "PKGCONFIG", "COMPONENT")


def _run(args, *, cwd=None, env=None):
    result = run_bounded(args, cwd=cwd, env=env,
                         timeout=240 if "--build" in args else 60)
    if result.returncode:
        raise RuntimeError(f"SDK validation failed ({result.returncode}): {args[0]}\n"
                           + result.stdout + result.stderr)
    return result.stdout.strip()


def _runtime_env(bin_dir: Path):
    # Do not inherit any vcpkg or previously installed FFmpeg DLL directories.
    env = _consumer_env()
    windows = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join(map(str, (bin_dir, windows / "System32", windows)))
    return env


def _extract(path: Path, prefix: Path, *, omit_symbols=False):
    # Called after publication dry-run. Keep this helper safe for standalone use.
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("Duplicate archive members")
        for name in names:
            if any(part in ("", ".", "..") for part in name.split("/")) or ":" in name or "\\" in name:
                raise ValueError(f"Invalid archive member: {name}")
        for member in archive.infolist():
            if not omit_symbols or not member.filename.lower().endswith(".pdb"):
                archive.extract(member, prefix)


_CORE_MODULES = {"avutil", "avcodec", "avformat", "avfilter", "avdevice", "swresample", "swscale"}
_KNOWN_MODULES = _CORE_MODULES | {"avresample", "postproc"}
_TESTER = ROOT / "ports/ffmpeg-tester"


def expected_modules(features=()):
    """Requested modules, independent of generated targets or output files."""
    return _CORE_MODULES | (_KNOWN_MODULES & set(features))


def _sdk_modules(selected: Path, *, required=(), installed=False):
    modules = {path.stem[3:] for path in (selected / "lib/pkgconfig").glob("lib*.pc")}
    if installed:
        modules &= _KNOWN_MODULES  # Other installed Ports have their own .pc files.
    missing = expected_modules(required) - modules
    if missing or modules - _KNOWN_MODULES:
        raise ValueError(f"Invalid SDK module inventory: missing={sorted(missing)}, unknown={sorted(modules - _KNOWN_MODULES)}")
    return modules


def tester_targets(modules, mode="CONFIG", *, full_only=False, crt=False):
    modules = set(modules)
    if not _CORE_MODULES <= modules <= _KNOWN_MODULES or mode not in _CONSUMER_MODES:
        raise ValueError("Invalid Tester case plan")
    if mode == "COMPONENT":
        if crt:
            raise ValueError("Component probe cannot use the CRT matrix")
        return {"check-component-avformat"}
    names = {"check-full", "check-full-cpp"}
    if not full_only and mode != "LEGACY":
        names.update("check-" + m for m in modules)
    if crt:
        if mode != "CONFIG":
            raise ValueError("CRT matrix requires Config mode")
        names.update(f"check-crt-{lang}-{rt}" for lang in ("c", "cpp") for rt in ("mt", "md"))
    return names


def installed_case_ids(modules, *, linkage, modes=None):
    """Reconstruct the independent installed-SDK acceptance contract."""
    return sorted(f"installed.{mode.lower()}.{cfg.lower()}.{target}"
                  for mode in (modes or _CONSUMER_MODES) for cfg in _CONFIGS
                  for target in tester_targets(modules, mode,
                      crt=(linkage == "shared" and mode == "CONFIG")))


def assert_installed_evidence(results, modules, *, linkage, runtime, modes=None):
    """Require every independent case exactly once; never accept count alone."""
    expected = installed_case_ids(modules, linkage=linkage, modes=modes)
    if (not isinstance(results, list) or not all(isinstance(row, dict) for row in results)
            or any(not isinstance(row.get("id"), str) for row in results)
            or sorted(row["id"] for row in results) != expected):
        raise ValueError("Incomplete independent SDK consumer evidence")
    if runtime not in ("passed", "skipped"):
        raise ValueError("Invalid SDK runtime expectation")
    for row in results:
        required = {"id": row["id"], "configure": "passed", "compile_link": "passed",
                    "runtime": runtime}
        if runtime == "skipped":
            required["reason"] = "host_architecture_incompatible"
        if row != required:
            raise ValueError("Unverified independent SDK consumer case: " + row["id"])


def _assert_selection(build: Path, config: str, selected: Path, *, modules=None, linkage="shared"):
    rows = (build / f"selected-{config}.txt").read_text(encoding="utf-8").splitlines()
    expected = set(modules) if modules is not None else _sdk_modules(selected)
    actual = set()
    for row in rows:
        module, dll_name, lib_name = row.split("|")
        dll, lib = Path(dll_name), Path(lib_name)
        if (module in actual or module not in expected
                or not dll.is_absolute() or not lib.is_absolute()
                or not dll.is_file() or not lib.is_file()
                or lib.parent.resolve(strict=True) != (selected / "lib").resolve(strict=True)
                or lib.name not in (module + ".lib", module + "d.lib")
                or (linkage == "shared" and (dll.parent.resolve(strict=True) != (selected / "bin").resolve(strict=True)
                    or not dll.name.startswith(module + "-")))
                or (linkage == "static" and dll.resolve(strict=True) != lib.resolve(strict=True))):
            raise ValueError(f"Incorrect {config} SDK configuration: {row}")
        actual.add(module)
    if actual != expected:
        raise ValueError(f"Incomplete imported module selection: {sorted(expected - actual)}")


def _verify_pkgconfig(pkgconf: Path, prefix: Path, selected: Path):
    env = os.environ.copy()
    env["PKG_CONFIG_PATH"] = ""
    env["PKG_CONFIG_LIBDIR"] = str(selected / "lib/pkgconfig")
    env.pop("PKG_CONFIG_SYSROOT_DIR", None)
    modules = _sdk_modules(selected)
    for module in sorted(modules):
        name = "lib" + module
        for variable, expected in (("includedir", prefix / "include"),
                                   ("libdir", selected / "lib")):
            actual = _run([pkgconf, "--variable=" + variable, name], env=env)
            # pkgconf may escape whitespace even in --variable output,
            # whereas some implementations return the unescaped path.
            # Accept only an exact path match after one tokenization.
            matches = bool(actual) and Path(actual).resolve() == expected.resolve()
            if not matches:
                try:
                    parts = shlex.split(actual)
                    matches = len(parts) == 1 and Path(parts[0]).resolve() == expected.resolve()
                except ValueError:
                    matches = False
            if not matches:
                raise ValueError(f"Unexpected pkg-config {variable} for {name}: {actual}")
        # Inspect even the private module graph using only the public archive.
        # This is a metadata check, not a promise of a static SDK.
        for flags in ([], ["--static"]):
            output = _run([pkgconf, *flags, "--cflags", "--libs", name], env=env)
            tokens = shlex.split(output)
            for flag, directory in (("-I", prefix / "include"), ("-L", selected / "lib")):
                matches = [Path(token[len(flag):]).resolve() for token in tokens
                           if token.startswith(flag) and len(token) > len(flag)]
                if directory.resolve() not in matches:
                    raise ValueError(f"Invalid pkg-config {flag} path for {name}: {output}")
            if "-l" + module not in tokens:
                raise ValueError(f"Missing pkg-config module library for {name}: {output}")
    print(f"pkg-config {'Debug' if selected != prefix else 'Release'}: {len(modules)} modules", flush=True)


def _assert_pkgconfig_selection(build, config, selected, modules, full_only):
    expected = {"full": set(modules)}
    if not full_only:
        expected.update({m: {m} for m in modules})
    rows = {}
    for line in (build / f"pkgconfig-{config}.txt").read_text(encoding="utf-8").splitlines():
        name, raw = line.split("|", 1)
        if name in rows or name not in expected:
            raise ValueError("Unexpected pkg-config linker evidence")
        actual = set()
        for item in raw.split(";"):
            path = Path(item)
            # A bare FFmpeg library name can be resolved from an unrelated
            # default LIB search path. Require the actual selected archive.
            module = path.stem.lower()
            if module not in _KNOWN_MODULES and module.endswith("d"):
                module = module[:-1]
            if module in _KNOWN_MODULES:
                if not path.is_absolute() or not path.is_file() or path.parent.resolve(strict=True) != (selected / "lib").resolve(strict=True):
                    raise ValueError(f"Incorrect {config} pkg-config FFmpeg library: {item}")
                actual.add(module)
        if not expected[name] <= actual <= set(modules):
            raise ValueError(f"Incomplete {config} pkg-config {name} link evidence")
        rows[name] = actual
    if set(rows) != set(expected):
        raise ValueError("Missing pkg-config consumer linker evidence")


def _read_link_rows(path, expected):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, raw = line.split("|", 1)
        if name in rows or name not in expected:
            raise ValueError(f"Unexpected Legacy link evidence: {name}")
        rows[name] = [item for item in raw.split(";") if item]
    if set(rows) != set(expected):
        raise ValueError("Missing Legacy link evidence")
    return rows


def _assert_legacy_selection(build, config, selected, modules, *, prefix):
    """Check the actual evaluated Legacy target link lists, including archives."""
    modules = set(modules)
    expected_targets = {"check-full", "check-full-cpp"}
    rows = _read_link_rows(build / f"legacy-{config}.txt", expected_targets)
    references = _read_link_rows(build / f"legacy-reference-{config}.txt", modules)
    includes = _read_link_rows(build / f"legacy-includes-{config}.txt", expected_targets)
    incdir = (prefix / "include").resolve(strict=True)
    for name, paths in includes.items():
        if (not paths or any(not Path(path).is_absolute() or not Path(path).is_dir()
                             or Path(path).resolve(strict=True) != incdir for path in paths)):
            raise ValueError(f"Incorrect {config} Legacy include directory: {name}")
    libdir = (selected / "lib").resolve(strict=True)

    def normalized(items, *, reference=False):
        actual = set()
        found = set()
        for item in items:
            if reference and item.startswith("FFmpeg::") and item[8:] in modules:
                continue  # Every module's interface is enumerated separately.
            path = Path(item)
            module = path.stem.lower()
            if module not in _KNOWN_MODULES and module.endswith("d"):
                module = module[:-1]
            if path.is_absolute():
                if not path.is_file():
                    raise ValueError(f"Missing {config} Legacy SDK library: {item}")
                real = path.resolve(strict=True)
                if not real.is_relative_to(libdir):
                    raise ValueError(f"Incorrect {config} Legacy SDK library: {item}")
                actual.add(str(real).casefold())
            else:
                if module in _KNOWN_MODULES or "/" in item or "\\" in item or "::" in item:
                    raise ValueError(f"Incorrect {config} Legacy SDK library: {item}")
                actual.add(item.casefold())  # Windows system library or linker option.
            if module in _KNOWN_MODULES:
                if module not in modules or not path.is_absolute() or real.parent != libdir:
                    raise ValueError(f"Incorrect {config} Legacy FFmpeg library: {item}")
                found.add(module)
        return actual, found

    reference, found = normalized([item for values in references.values() for item in values],
                                  reference=True)
    if found != modules:
        raise ValueError(f"Incomplete {config} Legacy reference closure")
    for name, items in rows.items():
        actual, found = normalized(items)
        if found != modules or actual != reference:
            raise ValueError(f"Incomplete or inconsistent {config} Legacy link closure: {name}")


def _consumer_env():
    # A public SDK must not accidentally discover a vcpkg toolchain, a
    # package registry entry, or an unrelated package via inherited hints.
    blocked = {"CMAKE_TOOLCHAIN_FILE", "CMAKE_PREFIX_PATH", "CMAKE_MODULE_PATH",
               "FFMPEG_DIR", "FFMPEG_ROOT", "VCPKG_ROOT", "VCPKG_DEFAULT_TRIPLET",
               "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR"} | PRIVATE_RUNNER_ENV
    return {k: v for k, v in os.environ.items() if k.upper() not in blocked}


def _consumer_suite(prefix, root, *, triplet, generator, modules, linkage,
                    pkgconf, stage, configs, selected, native=False, modes=None,
                    full_only=False, crt=False, execute=True):
    """Independent CMake caches and native link/runtime evidence for every case."""
    modes = tuple(modes or _CONSUMER_MODES)
    if "PKGCONFIG" in modes and not pkgconf:
        raise ValueError("Native pkgconf is required for independent pkg-config link acceptance")
    prefix = prefix.resolve(strict=True)
    root.mkdir(parents=True, exist_ok=True)
    if linkage == "shared":
        # A valid import library does not prove the matching DLL has the
        # right architecture, especially on a cross-compiling host.
        for sdk in {selected[cfg] for cfg in configs}:
            for module in modules:
                dlls = list((sdk / "bin").glob(module + "-*.dll"))
                if len(dlls) != 1 or pe_machine(dlls[0]) != PE_MACHINE[triplet]:
                    raise ValueError(f"Missing or wrong-architecture SDK DLL: {module}")

    def exercise(mode):
        results = []
        # pkgconf needs a separate configure for each selected .pc directory;
        # the other modes use a single multi-config build across SDK stages.
        batches = [(cfg,) for cfg in configs] if mode == "PKGCONFIG" else [configs]
        for batch in batches:
            env = _consumer_env()
            build = root / (mode.lower() + ("-" + stage + "-" + batch[0] if mode == "PKGCONFIG" else ""))
            args = ["cmake", "-S", _TESTER, "-B", build, "-G", generator,
                    "-DFFBUILD_TESTER_PREFIX=" + prefix.as_posix(),
                    "-DFFBUILD_TESTER_MODULES=" + ";".join(sorted(modules)),
                    "-DFFBUILD_TESTER_MODE=" + mode,
                    "-DFFBUILD_TESTER_NATIVE=" + ("ON" if native else "OFF"),
                    "-DFFBUILD_TESTER_DEPLOY=" + ("ON" if linkage == "shared" else "OFF"),
                    "-DFFBUILD_TESTER_FULL_ONLY=" + ("ON" if full_only else "OFF"),
                    "-DFFBUILD_TESTER_CRT_MATRIX=" + ("ON" if crt and mode == "CONFIG" else "OFF"),
                    "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>"]
            if generator.startswith("Visual Studio"):
                args += ["-A", _ARCH[triplet]]
                if triplet == "arm-windows":
                    from .targets import ci_setting
                    args += ["-DCMAKE_SYSTEM_VERSION=" + ci_setting("ARM_WINDOWS_SDK")]
            if mode in ("CONFIG", "COMPONENT"):
                args += ["-DCMAKE_PREFIX_PATH=" + prefix.as_posix()]
            if mode == "PKGCONFIG":
                directories = [selected[batch[0]] / "lib/pkgconfig"]
                if native:
                    directories.append(prefix / "share/pkgconfig")
                env.update(PKG_CONFIG_PATH="", PKG_CONFIG_LIBDIR=os.pathsep.join(map(str, directories)))
                args += ["-DPKG_CONFIG_EXECUTABLE=" + Path(pkgconf).resolve(strict=True).as_posix(),
                         "-DPKG_CONFIG_ARGN="]
                if linkage == "static":
                    # vcpkg folds private static flags into the public link
                    # interface. Ordinary --libs is linked below; --static
                    # must independently resolve the same module graph.
                    _run([pkgconf, "--static", "--cflags", "--libs",
                          *("lib" + m for m in sorted(modules))], env=env)
            expected = tester_targets(modules, mode, full_only=full_only, crt=crt and mode=="CONFIG")
            _run(args, env=env)
            for cfg in batch:
                sdk = selected[cfg]
                if mode != "PKGCONFIG":
                    _assert_selection(build, cfg, sdk, modules=modules, linkage=linkage)
                    if mode == "LEGACY":
                        _assert_legacy_selection(build, cfg, sdk, modules, prefix=prefix)
                else:
                    _assert_pkgconfig_selection(build, cfg, sdk, modules, full_only)
                # Keep CMake's cache, but no binaries/deployed DLLs from a
                # previous stage may make the new link or load appear valid.
                shutil.rmtree(build / cfg, ignore_errors=True)
                _run(["cmake", "--build", build, "--config", cfg, "--clean-first", "--parallel", "2"], env=env)
                binaries = sorted((build / cfg).rglob("check-*.exe"))
                if len(binaries) != len(expected) or {p.stem for p in binaries} != expected:
                    raise ValueError(f"Incomplete {stage}/{mode}/{cfg} consumer executables")
                # A real native compiler/linker is mandatory even for targets
                # that cannot execute on this runner. Verify the PE machine.
                for exe in binaries:
                    if pe_machine(exe) != PE_MACHINE[triplet]:
                        raise ValueError(f"Wrong consumer architecture: {mode}/{cfg}/{exe.name}")
                    out = exe.parent
                    if linkage == "shared" and mode in ("CONFIG", "MODULE", "COMPONENT"):
                        # The loader must use only the copied DLLs, and no
                        # unrelated SDK may supply a missing dependency.
                        for deployed in out.glob("*.dll"):
                            correct = sdk / "bin" / deployed.name
                            if not correct.is_file() or deployed.read_bytes() != correct.read_bytes():
                                raise ValueError(f"Incorrect deployed DLL: {mode}/{cfg}/{deployed.name}")
                        if exe.stem == "check-full":
                            expected_dlls = {p.name for p in (sdk / "bin").glob("*.dll")
                                             if any(p.name.startswith(m + "-") for m in modules)}
                            if {p.name for p in out.glob("*.dll")} != expected_dlls:
                                raise ValueError("Incomplete full-target DLL deployment")
                        runtime = _runtime_env(root)
                    else:
                        if list(out.glob("*.dll")):
                            raise ValueError("Direct consumer inherited deployed DLLs")
                        runtime = _runtime_env(sdk / "bin" if linkage == "shared" else root)
                    if execute:
                        _run([exe], cwd=out, env=runtime)
                    results.append({"id": f"{stage}.{mode.lower()}.{cfg.lower()}.{exe.stem}",
                                    "configure": "passed", "compile_link": "passed",
                                    "runtime": "passed" if execute else "skipped",
                                    **({} if execute else {"reason": "host_architecture_incompatible"})})
                action = "compiled, linked and ran" if execute else "compiled and linked (runtime incompatible)"
                print(f"SDK {stage} {mode} {cfg}: {len(binaries)} {action}", flush=True)
                # Keep only configuration evidence. Static EXEs/PDBs and
                # repeated DLL deployment copies need not remain on disk.
                shutil.rmtree(build / cfg)
        return results

    # Parallel independent configure/build trees, bounded to four MSBuild
    # workers in total rather than multiplying by the matrix dimensions.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [row for group in pool.map(exercise, modes) for row in group]
    return sorted(results, key=lambda row: row["id"])


def validate_installed(prefix: Path, *, triplet: str, linkage: str, features=(),
                       generator="Visual Studio 17 2022", pkgconf: Path,
                       modes=None):
    """Test an actual full vcpkg installation from outside its toolchain."""
    if os.name != "nt" or triplet not in _ARCH or linkage not in ("static", "shared"):
        raise ValueError("Installed acceptance requires a Windows MSVC target")
    execute = can_execute(triplet)
    if triplet in _NATIVE_RUNTIME and not execute:
        raise RuntimeError("Required native x64/x86 consumer execution is unavailable")
    modules = _sdk_modules(prefix, required=features, installed=True)
    if _sdk_modules(prefix / "debug", required=features, installed=True) != modules:
        raise ValueError("Installed SDK Release/Debug module sets differ")
    with tempfile.TemporaryDirectory(prefix="ffmpeg-installed-consumer-") as tmp:
        results = _consumer_suite(prefix, Path(tmp), triplet=triplet, generator=generator,
                                  modules=modules, linkage=linkage, pkgconf=pkgconf,
                                  stage="installed", configs=_CONFIGS, native=True,
                                  selected={"Release": prefix, "Debug": prefix / "debug"},
                                  modes=modes, crt=linkage=="shared", execute=execute)
        assert_installed_evidence(results, modules, linkage=linkage,
                                  runtime="passed" if execute else "skipped", modes=modes)
        return results


def validate_archives(binary: Path, debug: Path | None, *, triplet: str,
                      generator: str = "Visual Studio 17 2022", pkgconf: Path | None = None,
                      features=()):
    """Compile/link the extracted SDK; run only on a compatible Windows host."""
    if os.name != "nt" or triplet not in _ARCH:
        raise ValueError("Archive validation requires a Windows MSVC target")
    execute = can_execute(triplet)
    if triplet in _NATIVE_RUNTIME and not execute:
        raise RuntimeError("Required native x64/x86 archive execution is unavailable")
    with tempfile.TemporaryDirectory(prefix="ffmpeg-sdk-validation-") as tmp:
        root = Path(tmp)
        prefix, build = root / "sdk with spaces", root / "consumer"
        prefix.mkdir()
        _extract(binary, prefix, omit_symbols=True)
        bin_dir = prefix / "bin" if debug else prefix
        if not (bin_dir / "ffmpeg.exe").is_file():
            raise ValueError("Missing ffmpeg.exe")
        results = []
        for executable in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
            path = bin_dir / executable
            if executable.removesuffix(".exe") in features and not path.is_file():
                raise ValueError(f"Requested CLI missing: {executable}")
            if path.is_file():
                if pe_machine(path) != PE_MACHINE[triplet]:
                    raise ValueError(f"Wrong CLI architecture: {executable}")
                if execute:
                    output = _run([path, "-version"], cwd=root, env=_runtime_env(bin_dir))
                    print(f"CLI {executable}: {output.splitlines()[0]}", flush=True)
                else:
                    print(f"CLI {executable}: PE architecture passed; runtime incompatible", flush=True)
                results.append({"id": "cli." + executable, "binary_inspection": "passed",
                                "runtime": "passed" if execute else "skipped",
                                **({} if execute else {"reason": "host_architecture_incompatible"})})
        if debug is None:
            return results
        for name in ("FindFFmpeg.cmake", "FFmpegConfig.cmake", "FFmpegConfigVersion.cmake"):
            if not (prefix / "share/ffmpeg" / name).is_file():
                raise ValueError(f"Missing SDK {name}")
        modules = _sdk_modules(prefix, required=features)
        if not pkgconf:
            raise ValueError("Public shared SDK acceptance requires native pkgconf")
        _verify_pkgconfig(pkgconf, prefix, prefix)
        # All interfaces tested with Binary alone; keep the complete
        # per-module matrix for the overlay stage, and CRT coverage in both.
        results += _consumer_suite(prefix, build, triplet=triplet, generator=generator,
                                   modules=modules, linkage="shared", pkgconf=pkgconf,
                                   stage="binary", configs=_CONFIGS, native=False,
                                   selected=dict.fromkeys(_CONFIGS, prefix), full_only=True, crt=True,
                                   modes=("CONFIG", "MODULE", "LEGACY", "PKGCONFIG"), execute=execute)
        _extract(debug, prefix, omit_symbols=True)
        if _sdk_modules(prefix / "debug", required=features) != modules:
            raise ValueError("Public Debug module inventory differs from Binary")
        _verify_pkgconfig(pkgconf, prefix, prefix / "debug")
        results += _consumer_suite(prefix, build, triplet=triplet, generator=generator,
                                   modules=modules, linkage="shared", pkgconf=pkgconf,
                                   stage="overlay", configs=_CONFIGS, native=False,
                                   selected={"Release": prefix, "Debug": prefix / "debug"}, crt=True, execute=execute)
        shutil.rmtree(prefix / "debug")
        results += _consumer_suite(prefix, build, triplet=triplet, generator=generator,
                                   modules=modules, linkage="shared", pkgconf=pkgconf,
                                   stage="removed", configs=("Debug",), native=False,
                                   selected={"Debug": prefix}, modes=("CONFIG", "LEGACY"), full_only=True, crt=True,
                                   execute=execute)
        return results


def validate_directory(directory: Path, *, generator: str = "Visual Studio 17 2022", pkgconf: Path | None = None):
    records = sorted(directory.glob("*.var.yaml"))
    if len(records) != 1:
        raise ValueError("SDK validation requires exactly one Worker distribution")
    row = yaml.safe_load(records[0].read_text(encoding="utf-8"))
    assets = row["assets"]
    binary = directory / assets["binary"]["file"]
    debug = directory / assets["debug"]["file"] if row["linkage"] == "shared" else None
    return validate_archives(binary, debug, triplet=row["triplet"], generator=generator,
                             pkgconf=pkgconf, features=row.get("features", ()))
