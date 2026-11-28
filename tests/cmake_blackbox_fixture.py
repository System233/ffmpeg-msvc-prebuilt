"""Independent SDK fixture and public consumer probes.

The expected paths and runtime values come from fixture inputs, never from
the generated package metadata. The production metadata pipeline is exercised
through its existing script-mode adapter; no source-text assertions.
"""
import os
import shutil
from pathlib import Path

from ffbuild.versions import ROOT
from ffbuild.process import run_bounded as run

PKGCONF = os.environ.get("FFBUILD_TEST_PKGCONF") or shutil.which("pkgconf")
TOOLS = shutil.which("cmake") and shutil.which("ninja") and PKGCONF
CONFIGS = ("Debug", "Release", "RelWithDebInfo", "MinSizeRel")



def output(result):
    return result.stdout + result.stderr


def canonical_existing_path(path):
    """Compare existing absolute paths, including Windows 8.3 aliases.

    Do not accept a missing file, a relative linker token, or a different
    SDK/configuration just because the file names match.
    """
    path = Path(path)
    if not path.is_absolute():
        raise AssertionError(f"Expected an absolute path, got {path}")
    return path.resolve(strict=True)


def filesystem_alias(directory):
    """Exercise a real short-name alias when NTFS provides one.

    Volumes with 8.3 creation disabled still exercise a distinct existing
    path spelling through a parent component; no filesystem settings change.
    """
    import ctypes
    from ctypes import wintypes

    directory = canonical_existing_path(directory)
    get_short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
    get_short_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    get_short_path.restype = wintypes.DWORD
    buf = ctypes.create_unicode_buffer(32768)
    size = get_short_path(str(directory), buf, len(buf))
    if 0 < size < len(buf) and Path(buf.value) != directory:
        alias = Path(buf.value)
        if not alias.samefile(directory):
            raise AssertionError("Windows short name does not identify the fixture directory")
        return alias, "8.3"
    child = directory / "alias-component"
    child.mkdir()
    return child / "..", "parent-component"


class SDKFixture:
    def __init__(self, root, linkage="dynamic"):
        self.root = Path(root)
        self.sdk = self.root / "sdk"
        self.deps = self.root / "installed"
        self.src = self.root / "consumer"
        self.build = self.root / "build"
        self.linkage = linkage
        self.modules = {"avutil": "56.1.0", "avcodec": "58.1.0", "avformat": "58.1.0"}
        self.graph = {"avutil": (), "avcodec": ("avutil",), "avformat": ("avcodec", "avutil")}
        self.flags = {
            "avutil": ("-lthird -lws2_32", "-lthirdd -lws2_32"),
            "avcodec": ("-lsecond", "-lsecond"),
            "avformat": ("", ""),
        } if linkage == "static" else {m: ("", "") for m in self.modules}
        for cfg in ("", "debug"):
            for m in self.modules:
                self.touch(self.sdk / cfg / "lib" / (m + ".lib"))
                if linkage == "dynamic":
                    self.touch(self.sdk / cfg / "bin" / self.dll(m))
            for name in (("third", "second") if not cfg else ("thirdd", "second")):
                self.touch(self.deps / cfg / "lib" / (name + ".lib"))
        for m in self.modules:
            self.touch(self.sdk / "include" / ("lib" + m) / (m + ".h"))
        self.write_pc()
        self.src.mkdir()

    @staticmethod
    def touch(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    @staticmethod
    def header(module):
        return "postprocess.h" if module == "postproc" else module + ".h"

    def add_module(self, module, version, requires=()):
        self.modules[module] = version
        self.graph[module] = tuple(requires)
        self.flags[module] = ("", "")
        self.touch(self.sdk / "include" / ("lib" + module) / self.header(module))
        for cfg in ("", "debug"):
            self.touch(self.sdk / cfg / "lib" / (module + ".lib"))
            if self.linkage == "dynamic":
                self.touch(self.sdk / cfg / "bin" / self.dll(module))
        self.write_pc()

    def dll(self, module):
        return module + "-" + self.modules[module].split(".")[0] + ".dll"

    def write_pc(self):
        for m, version in self.modules.items():
            for i, cfg in enumerate(("", "debug")):
                pc = self.sdk / cfg / "lib/pkgconfig" / ("lib" + m + ".pc")
                pc.parent.mkdir(parents=True, exist_ok=True)
                requires = " ".join("lib" + d for d in self.graph[m])
                pc.write_text(f"Name: lib{m}\nDescription: test {m}\nVersion: {version}\n"
                              f"Requires: {requires}\nLibs: -l{m} {self.flags[m][i]}\n",
                              encoding="utf-8")

    def generate(self, *, env=None, extra=()):
        return run(["cmake", f"-DCURRENT_PACKAGES_DIR={self.sdk.as_posix()}",
                    f"-DCURRENT_INSTALLED_DIR={self.deps.as_posix()}",
                    f"-DPKGCONF={Path(PKGCONF).as_posix()}",
                    f"-DOUTPUT_DIR={(self.sdk / 'share/ffmpeg').as_posix()}",
                    f"-DVCPKG_LIBRARY_LINKAGE={self.linkage}", "-DVCPKG_TARGET_ARCHITECTURE=x64",
                    "-DVCPKG_CRT_LINKAGE=static", *extra,
                    "-P", ROOT / "tests/test_ffmpeg_deps.cmake"], env=env)

    def install_deps(self):
        for cfg in ("", "debug"):
            for p in (self.deps / cfg / "lib").rglob("*.lib"):
                dest = self.sdk / cfg / "lib" / p.relative_to(self.deps / cfg / "lib")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)

    def configure(self, *, mode="CONFIG", configs=CONFIGS, single=None, before="", after="",
                  quiet=False, repeat=False, extra=(), prefix=None, package="FFmpeg"):
        if os.name != "nt":
            raise RuntimeError("MSVC SDK contracts require a native Windows host")
        source = r"""
cmake_minimum_required(VERSION 3.21)
project(blackbox LANGUAGES NONE)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Windows" OR CMAKE_CROSSCOMPILING)
    message(FATAL_ERROR "Expected native Windows platform semantics")
endif()
set(CMAKE_FIND_LIBRARY_PREFIXES "")
set(CMAKE_FIND_LIBRARY_SUFFIXES ".lib")
set(CMAKE_FIND_USE_PACKAGE_REGISTRY FALSE)
set(CMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY FALSE)
list(APPEND CMAKE_MODULE_PATH "${PROBE_MODULE_PATH}")
""" + before + "\n"
        call = f"find_package({package} {mode} REQUIRED {'QUIET' if quiet else ''})\n"
        source += call * (2 if repeat else 1) + after + "\n" + r"""
add_library(legacy INTERFACE)
target_link_libraries(legacy INTERFACE ${FFMPEG_LIBRARIES})
set(rows "version|${FFmpeg_VERSION}\n")
foreach(m IN LISTS PROBE_MODULES)
  string(APPEND rows "${m}|$<TARGET_LINKER_FILE:FFmpeg::${m}>|$<TARGET_FILE:FFmpeg::${m}>\n")
  string(APPEND rows "deps-${m}|$<TARGET_GENEX_EVAL:FFmpeg::${m},$<TARGET_PROPERTY:FFmpeg::${m},INTERFACE_LINK_LIBRARIES>>\n")
endforeach()
string(APPEND rows "legacy|$<TARGET_GENEX_EVAL:legacy,$<TARGET_PROPERTY:legacy,INTERFACE_LINK_LIBRARIES>>\n")
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/selected-$<CONFIG>.txt" CONTENT "${rows}")
"""
        (self.src / "CMakeLists.txt").write_text(source, encoding="utf-8")
        args = ["cmake", "-S", self.src, "-B", self.build,
                "-G", "Ninja Multi-Config" if single is None else "Ninja",
                "-DCMAKE_PREFIX_PATH=" + (prefix or self.sdk).as_posix(),
                "-DPROBE_MODULE_PATH=" + (self.sdk / "share/ffmpeg").as_posix(),
                "-DPROBE_MODULES=" + ";".join(self.modules)]
        args += ["-DCMAKE_CONFIGURATION_TYPES=" + ";".join(configs)] if single is None else ["-DCMAKE_BUILD_TYPE=" + single]
        return run(args + list(extra))

    def rows(self, config):
        return {line.split("|", 1)[0]: line.split("|")[1:]
                for line in (self.build / f"selected-{config}.txt").read_text(encoding="utf-8").splitlines()}

    def assert_selection(self, case, config, expected, *, deps=True):
        rows = self.rows(config)
        prefix = self.sdk / ("debug" if expected == "Debug" else "")
        lib_dir = canonical_existing_path(prefix / "lib")
        for m in self.modules:
            expected_lib = prefix / "lib" / (m + ".lib")
            expected_file = prefix / "bin" / self.dll(m) if self.linkage == "dynamic" else expected_lib
            case.assertEqual(canonical_existing_path(rows[m][0]),
                             canonical_existing_path(expected_lib), (config, m))
            case.assertEqual(canonical_existing_path(rows[m][1]),
                             canonical_existing_path(expected_file), (config, m))
        legacy = [canonical_existing_path(p) for p in rows["legacy"][0].split(";") if p.lower().endswith(".lib")]
        for m in self.modules:
            case.assertIn(canonical_existing_path(lib_dir / (m + ".lib")), legacy)
        for p in legacy:
            case.assertTrue(p.is_relative_to(lib_dir),
                            f"{config}: unexpected legacy library {p} outside {lib_dir}")
        if deps and self.linkage == "static":
            name = "thirdd.lib" if expected == "Debug" else "third.lib"
            for m, lib in (("avutil", name), ("avcodec", "second.lib")):
                paths = [canonical_existing_path(p) for p in rows["deps-" + m][0].split(";") if p.lower().endswith(".lib")]
                expected_dep = canonical_existing_path(lib_dir / lib)
                case.assertIn(expected_dep, paths)
                case.assertIn(expected_dep, legacy)
                case.assertTrue(all(p.is_relative_to(lib_dir) for p in paths), (config, m, paths))
