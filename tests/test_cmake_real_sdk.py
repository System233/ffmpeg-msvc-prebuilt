"""Opt-in acceptance of an existing real FFmpeg shared build, without rebuilding it.

Inputs are a previously built vcpkg package and its installed dependency
prefix. The original package is never modified. Current production metadata
is regenerated into a scratch SDK; existing binary contents are preserved.
"""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from cmake_blackbox_fixture import ROOT, PKGCONF, TOOLS, output, run

PACKAGE = os.environ.get("FFBUILD_TEST_REAL_PACKAGE")
INSTALLED = os.environ.get("FFBUILD_TEST_REAL_INSTALLED")
ENABLED = os.name == "nt" and os.environ.get("FFBUILD_TEST_MSVC") == "1" and TOOLS and PACKAGE and INSTALLED
TRIPLET = os.environ.get("FFBUILD_TEST_REAL_TRIPLET", "x64-windows")
LIB_EXE = os.environ.get("FFBUILD_TEST_LIB_EXE")
DUMPBIN = Path(LIB_EXE).with_name("dumpbin.exe") if LIB_EXE else None


@unittest.skipUnless(ENABLED, "Set real shared package/installed prefix and native test prerequisites")
class RealFFmpegSDKContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ffmpeg-real-sdk-contract-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        source = Path(PACKAGE).resolve()
        installed = Path(INSTALLED).resolve()
        self.sdk = self.root / "sdk"
        if TRIPLET not in ("x64-windows", "x86-windows"):
            raise ValueError("This native execution fixture supports x64/x86")
        self.generator = ("-G", "Visual Studio 17 2022", "-A", "x64" if TRIPLET == "x64-windows" else "Win32")
        control = (source / "CONTROL").read_text(encoding="utf-8")
        self.version = re.search(r"(?m)^Version: (.+)$", control).group(1).strip()
        if "LibraryLinkage: dynamic" not in (source / "BUILD_INFO").read_text():
            raise ValueError("FFBUILD_TEST_REAL_PACKAGE must be a shared package")
        for folder in ("bin", "lib", "include", "debug/bin", "debug/lib"):
            # PDB pairing has separate real-native coverage. Avoid copying
            # hundreds of MB of symbols for this link and runtime test.
            shutil.copytree(source / folder, self.sdk / folder,
                            ignore=shutil.ignore_patterns("*.pdb", "*.exp", "*.def"))
        tools = self.sdk / "tools/ffmpeg"
        tools.mkdir(parents=True)
        for exe in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
            paths = list((source / "tools").glob("*/" + exe))
            if paths:
                shutil.copy2(paths[0], tools / exe)
        metadata = self.sdk / "share/ffmpeg"
        p = run(["cmake", f"-DCURRENT_PACKAGES_DIR={self.sdk.as_posix()}",
                 f"-DCURRENT_INSTALLED_DIR={installed.as_posix()}",
                 f"-DPKGCONF={Path(PKGCONF).as_posix()}", f"-DOUTPUT_DIR={metadata.as_posix()}",
                 "-DVCPKG_LIBRARY_LINKAGE=dynamic", "-DVCPKG_CRT_LINKAGE=static",
                 "-DVCPKG_TARGET_ARCHITECTURE=" + TRIPLET.split("-")[0],
                 "-DFFMPEG_VERSION=" + self.version, "-DFFBUILD_TEST_NORMALIZE_SHARED=ON",
                 "-P", ROOT / "tests/test_ffmpeg_deps.cmake"])
        if p.returncode:
            raise RuntimeError(output(p))
        # modules.txt is an adapter report, not package content.
        (metadata / "modules.txt").unlink(missing_ok=True)

    def checked(self, args, **kwargs):
        p = run(args, **kwargs)
        self.assertEqual(0, p.returncode, output(p))
        return p.stdout

    def runtime_env(self, prefix):
        windows = Path(os.environ["SystemRoot"])
        return dict(os.environ, PATH=os.pathsep.join(str(p) for p in (prefix / "bin", windows / "System32", windows)))

    def assert_static_crt_imports(self):
        self.assertIsNotNone(DUMPBIN, "Real SDK contract requires dumpbin.exe")
        crt_import = re.compile(
            r"^(?:MSVCP|MSVCR|VCRUNTIME|UCRTBASE|API-MS-WIN-CRT|CONCRT)", re.IGNORECASE)
        for config in ("", "debug"):
            for dll in sorted((self.sdk / config / "bin").glob("*.dll")):
                result = run([DUMPBIN, "/nologo", "/dependents", dll])
                self.assertEqual(0, result.returncode, output(result))
                imports = re.findall(r"^\s+([A-Za-z0-9_.-]+\.dll)\s*$", output(result),
                                     re.IGNORECASE | re.MULTILINE)
                dynamic_crt = [name for name in imports if crt_import.match(name)]
                self.assertEqual([], dynamic_crt,
                                 f"{dll} unexpectedly imports the dynamic MSVC/UCRT runtime")

    def test_repacked_real_shared_sdk_uses_production_archive_consumer(self):
        from ffbuild.package import _files, _archive
        from ffbuild.sdk_validation import validate_archives
        self.assert_static_crt_imports()
        rel, dbg = self.root / "binary.zip", self.root / "debug.zip"
        copyright_file = self.root / "copyright"
        copyright_file.write_text("Test-only repack, not a public release")
        _archive(rel, _files(self.sdk, "shared", kind="binary"), copyright_file)
        _archive(dbg, _files(self.sdk, "shared", kind="debug"), copyright_file)
        validate_archives(rel, dbg, triplet=TRIPLET, pkgconf=Path(PKGCONF))

    def test_actual_native_tester_compiles_and_executes_every_module(self):
        modules = {pc.stem[3:] for pc in (self.sdk / "lib/pkgconfig").glob("lib*.pc")}
        expected = {f"check-{mode}{m}.exe" for m in modules for mode in ("", "full-", "legacy-")}
        expected.update(f"check-{mode}transitive-{m}.exe" for m in
                        ("avcodec", "avdevice", "avformat", "avfilter", "swresample", "swscale")
                        for mode in ("", "full-", "legacy-"))
        build = self.root / "native-tester"
        self.checked(["cmake", "-S", ROOT / "ports/ffmpeg-tester", "-B", build,
                      *self.generator, "-DCMAKE_PREFIX_PATH=" + self.sdk.as_posix(),
                      "-DCMAKE_MODULE_PATH=" + (self.sdk / "share/ffmpeg").as_posix(),
                      "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>"])
        for config, folder in (("Release", ""), ("Debug", "debug")):
            with self.subTest(config=config):
                self.checked(["cmake", "--build", build, "--config", config, "--parallel", "4"])
                executables = sorted((build / config).glob("check-*.exe"))
                self.assertEqual(expected, {p.name for p in executables})
                for exe in executables:
                    self.checked([exe], env=self.runtime_env(self.sdk / folder), cwd=build / config)
                print(f"Real FFmpeg {self.version} {config}: {len(executables)} Native Tester executions", flush=True)

    def test_real_shared_sdk_accepts_all_consumer_crts(self):
        src = self.root / "crt-consumer"
        src.mkdir()
        (src / "probe.c").write_text(r"""
#ifdef __cplusplus
extern "C" {
#endif
#include <libavutil/mem.h>
#include <libavcodec/avcodec.h>
#ifdef __cplusplus
}
#include <vector>
#endif
#include <stdlib.h>
#include <string.h>
#if !defined(_MT) || (defined(_DLL) != EXPECT_DLL_CRT) || (defined(_DEBUG) != EXPECT_DEBUG_CRT)
#error Consumer CRT does not match its requested runtime
#endif
int main(void) {
    void *p=av_malloc(128), *q=malloc(128);
    AVCodecContext *c=avcodec_alloc_context3(NULL);
    if(!p || !q || !c) return 1;
    memset(p,7,128); memset(q,8,128);
#ifdef __cplusplus
    std::vector<int> v{7,8};
    if(v.at(0)!=7) return 2;
#endif
    av_free(p); free(q); avcodec_free_context(&c);
    return c!=NULL;
}
""", encoding="utf-8")
        shutil.copyfile(src / "probe.c", src / "probe.cpp")
        (src / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(crt_consumer C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_MSVC_RUNTIME_LIBRARY MultiThreaded)
find_package(FFmpeg CONFIG REQUIRED)
if(NOT CMAKE_MSVC_RUNTIME_LIBRARY STREQUAL "MultiThreaded")
  message(FATAL_ERROR "Package discovery changed consumer CRT")
endif()
foreach(lang c cpp)
  foreach(rt MT MD MTd MDd)
    set(runtime MultiThreaded)
    set(dll 0)
    set(debug 0)
    if(rt MATCHES "d$")
      string(APPEND runtime Debug)
      set(debug 1)
    endif()
    if(rt MATCHES "^MD")
      string(APPEND runtime DLL)
      set(dll 1)
    endif()
    add_executable(probe-${lang}-${rt} probe.${lang})
    set_property(TARGET probe-${lang}-${rt} PROPERTY MSVC_RUNTIME_LIBRARY "${runtime}")
    target_compile_definitions(probe-${lang}-${rt} PRIVATE EXPECT_DLL_CRT=${dll} EXPECT_DEBUG_CRT=${debug})
    target_link_libraries(probe-${lang}-${rt} PRIVATE FFmpeg::avcodec FFmpeg::avutil)
  endforeach()
endforeach()
""", encoding="utf-8")
        build = self.root / "crt-build"
        self.checked(["cmake", "-S", src, "-B", build, *self.generator,
                      "-DCMAKE_PREFIX_PATH=" + self.sdk.as_posix()])
        for config, folder in (("Release", ""), ("Debug", "debug")):
            self.checked(["cmake", "--build", build, "--config", config, "--parallel", "4"])
            for lang in ("c", "cpp"):
                for rt in ("MT", "MD", "MTd", "MDd"):
                    with self.subTest(config=config, lang=lang, runtime=rt):
                        self.checked([build / config / f"probe-{lang}-{rt}.exe"],
                                     env=self.runtime_env(self.sdk / folder), cwd=build / config)

    def test_real_pkgconfig_consumer_links_and_runs(self):
        moved = self.root / "real sdk with spaces"
        self.sdk.rename(moved)
        self.sdk = moved
        src = self.root / "pc-consumer"
        src.mkdir()
        shutil.copy2(ROOT / "tests/sdk_consumer/main.c", src)
        (src / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(pc_consumer C)
set(PKG_CONFIG_USE_CMAKE_PREFIX_PATH FALSE)
find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED IMPORTED_TARGET libavformat libavutil)
add_executable(pc-consumer main.c)
target_link_libraries(pc-consumer PRIVATE PkgConfig::FFMPEG)
""")
        for config, folder in (("Release", ""), ("Debug", "debug")):
            with self.subTest(config=config):
                build = self.root / ("pc-build-" + config)
                prefix = self.sdk / folder
                env = dict(os.environ, PKG_CONFIG_PATH="", PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"))
                env.pop("PKG_CONFIG_SYSROOT_DIR", None)
                self.checked(["cmake", "-S", src, "-B", build, *self.generator,
                              "-DPKG_CONFIG_EXECUTABLE=" + Path(PKGCONF).as_posix()], env=env)
                self.checked(["cmake", "--build", build, "--config", config, "--parallel", "2"], env=env)
                self.checked([build / config / "pc-consumer.exe"], env=self.runtime_env(prefix), cwd=build)
