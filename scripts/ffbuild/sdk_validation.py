"""Post-packaging consumer acceptance: test the public ZIP, never vcpkg."""
from __future__ import annotations

import os
import shutil
import shlex
import tempfile
import zipfile
from pathlib import Path

import yaml

from .versions import ROOT
from .process import run_bounded

_CONFIGS = ("Release", "Debug")
_ARCH = {"x64-windows": "x64", "x86-windows": "Win32"}


def _run(args, *, cwd=None, env=None):
    result = run_bounded(args, cwd=cwd, env=env,
                         timeout=240 if "--build" in args else 60)
    if result.returncode:
        raise RuntimeError(f"SDK validation failed ({result.returncode}): {args[0]}\n"
                           + result.stdout + result.stderr)
    return result.stdout.strip()


def _runtime_env(bin_dir: Path):
    # Do not inherit any vcpkg or previously installed FFmpeg DLL directories.
    env = os.environ.copy()
    windows = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join(map(str, (bin_dir, windows / "System32", windows)))
    return env


def _extract(path: Path, prefix: Path):
    # Called after publication dry-run. Keep this helper safe for standalone use.
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError("Duplicate archive members")
        for name in names:
            if any(part in ("", ".", "..") for part in name.split("/")) or ":" in name or "\\" in name:
                raise ValueError(f"Invalid archive member: {name}")
        archive.extractall(prefix)


_CORE_MODULES = {"avutil", "avcodec", "avformat", "avfilter", "avdevice", "swresample", "swscale"}


def _sdk_modules(selected: Path):
    modules = {path.stem[3:] for path in (selected / "lib/pkgconfig").glob("lib*.pc")}
    if not _CORE_MODULES <= modules:
        raise ValueError("Missing core SDK pkg-config modules")
    return modules


def _assert_selection(build: Path, config: str, selected: Path):
    rows = (build / f"selected-{config}.txt").read_text(encoding="utf-8").splitlines()
    expected = _sdk_modules(selected)
    actual = set()
    for row in rows:
        module, dll_name, lib_name = row.split("|")
        dll, lib = Path(dll_name), Path(lib_name)
        if (module in actual or module not in expected
                or dll.parent.resolve() != (selected / "bin").resolve()
                or lib.parent.resolve() != (selected / "lib").resolve()
                or not dll.name.startswith(module + "-")
                or lib.name not in (module + ".lib", module + "d.lib")
                or not dll.is_file() or not lib.is_file()):
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


def validate_archives(binary: Path, debug: Path | None, *, triplet: str,
                      generator: str = "Visual Studio 17 2022", pkgconf: Path | None = None):
    """Run native x64/x86 CLI and SDK smoke tests on a Windows host."""
    if triplet not in _ARCH:
        raise ValueError("Archive runtime validation requires a native x64/x86 target")
    with tempfile.TemporaryDirectory(prefix="ffmpeg-sdk-validation-") as tmp:
        root = Path(tmp)
        prefix, build = root / "sdk with spaces", root / "consumer"
        prefix.mkdir()
        _extract(binary, prefix)
        bin_dir = prefix / "bin" if debug else prefix
        if not (bin_dir / "ffmpeg.exe").is_file():
            raise ValueError("Missing ffmpeg.exe")
        for executable in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
            path = bin_dir / executable
            if path.is_file():
                output = _run([path, "-version"], cwd=root, env=_runtime_env(bin_dir))
                print(f"CLI {executable}: {output.splitlines()[0]}", flush=True)
        if debug is None:
            return
        for name in ("FindFFmpeg.cmake", "FFmpegConfig.cmake", "FFmpegConfigVersion.cmake"):
            if not (prefix / "share/ffmpeg" / name).is_file():
                raise ValueError(f"Missing SDK {name}")

        def configure():
            args = ["cmake", "-S", ROOT / "tests/sdk_consumer", "-B", build, "-G", generator,
                    "-DCMAKE_PREFIX_PATH=" + prefix.as_posix()]
            if generator.startswith("Visual Studio"):
                args += ["-A", _ARCH[triplet]]
            _run(args)

        def build_and_run(config, selected, stage):
            _assert_selection(build, config, selected)
            shutil.rmtree(build / config, ignore_errors=True)
            _run(["cmake", "--build", build, "--config", config, "--clean-first", "--parallel", "2"])
            # Separate output directories prevent another target's DLLs
            # from masking missing transitive deployment.
            for target in ("check-full", "check-demand", "check-legacy"):
                out = build / config / target
                if target != "check-legacy":
                    for dll in (selected / "bin").glob("*.dll"):
                        deployed = out / dll.name
                        if target == "check-full" or deployed.is_file():
                            if not deployed.is_file() or deployed.read_bytes() != dll.read_bytes():
                                raise ValueError(f"Incorrect deployed DLL: {target}/{dll.name}")
                    env = _runtime_env(root)
                else:
                    if list(out.glob("*.dll")):
                        raise ValueError("Legacy test must not inherit deployed DLLs")
                    env = _runtime_env(selected / "bin")
                version = _run([out / (target + ".exe")], cwd=root, env=env)
                print(f"SDK {stage} {config} {target}: {version}", flush=True)

        if pkgconf:
            _verify_pkgconfig(pkgconf, prefix, prefix)
        configure()
        for config in _CONFIGS:
            build_and_run(config, prefix, "binary")
        _extract(debug, prefix)
        if pkgconf:
            _verify_pkgconfig(pkgconf, prefix, prefix / "debug")
        # Reuse the same CMake build tree to exercise cached SDK discovery.
        configure()
        for config in _CONFIGS:
            build_and_run(config, prefix / "debug" if config == "Debug" else prefix, "overlay")


def validate_directory(directory: Path, *, generator: str = "Visual Studio 17 2022", pkgconf: Path | None = None):
    records = sorted(directory.glob("*.var.yaml"))
    if len(records) != 1:
        raise ValueError("SDK validation requires exactly one Worker distribution")
    row = yaml.safe_load(records[0].read_text(encoding="utf-8"))
    assets = row["assets"]
    binary = directory / assets["binary"]["file"]
    debug = directory / assets["debug"]["file"] if row["linkage"] == "shared" else None
    validate_archives(binary, debug, triplet=row["triplet"], generator=generator, pkgconf=pkgconf)
