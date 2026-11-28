"""Acceptance of a real locally-built static FFmpeg vcpkg installation.

Unlike a published shared SDK this prefix must contain its dependency packages.
Use the actual package and corresponding installed triplet, not synthetic .lib
files or a copy of all installed archives.
"""
import os
import tempfile
import unittest
from pathlib import Path

from cmake_blackbox_fixture import ROOT, PKGCONF, TOOLS, run, output

PACKAGE = os.environ.get("FFBUILD_TEST_REAL_STATIC_PACKAGE")
INSTALLED = os.environ.get("FFBUILD_TEST_REAL_STATIC_INSTALLED")
TRIPLET = os.environ.get("FFBUILD_TEST_REAL_STATIC_TRIPLET", "x64-windows")
ENABLED = os.name == "nt" and os.environ.get("FFBUILD_TEST_MSVC") == "1" and TOOLS and PACKAGE and INSTALLED


@unittest.skipUnless(ENABLED, "Supply actual static FFmpeg package and matching installed triplet")
class RealStaticSDKContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ffmpeg-real-static-consumer-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.package = Path(PACKAGE).resolve()
        self.sdk = Path(INSTALLED).resolve()
        if TRIPLET not in ("x64-windows", "x86-windows"):
            self.fail("Real execution supports native x64/x86 triplets")
        self.generator = ("-G", "Visual Studio 17 2022", "-A", "x64" if TRIPLET == "x64-windows" else "Win32")
        self.assertEqual(TRIPLET, self.sdk.name, "Use the matching installed triplet prefix")
        info = (self.package / "BUILD_INFO").read_text(encoding="utf-8")
        self.assertIn("LibraryLinkage: static", info)
        self.assertIn("CRTLinkage: static", info)
        self.modules = {p.stem[3:] for p in (self.package / "lib/pkgconfig").glob("lib*.pc")}
        self.assertTrue({"avutil", "avcodec", "avformat", "avdevice", "avfilter", "swresample", "swscale"} <= self.modules,
                        "Use an actual complete core-module static Port build")
        for folder in ("", "debug"):
            for module in self.modules:
                archive = self.package / folder / "lib" / (module + ".lib")
                if folder and not archive.is_file():
                    archive = self.package / folder / "lib" / (module + "d.lib")
                self.assertTrue(archive.is_file(), str(archive))
                installed = self.sdk / folder / "lib" / archive.name
                self.assertTrue(installed.is_file(), str(installed))
                self.assertEqual(archive.stat().st_size, installed.stat().st_size,
                                 "Installed package does not match the supplied static Port")
                self.assertTrue((self.sdk / folder / "lib/pkgconfig" / ("lib" + module + ".pc")).is_file())
        self.assertEqual((self.package / "share/ffmpeg/FindFFmpeg.cmake").read_bytes(),
                         (self.sdk / "share/ffmpeg/FindFFmpeg.cmake").read_bytes(),
                         "Installed FindFFmpeg metadata does not match the static Port")

    def checked(self, args, **kwargs):
        result = run(args, **kwargs)
        self.assertEqual(0, result.returncode, output(result))
        return result.stdout

    def runtime_env(self):
        windows = Path(os.environ["SystemRoot"])
        return dict(os.environ, PATH=os.pathsep.join(map(str, (windows / "System32", windows))))

    def test_locally_built_static_port_links_and_runs_native_tester(self):
        build = self.root / "native-tester"
        self.checked(["cmake", "-S", ROOT / "ports/ffmpeg-tester", "-B", build,
                      *self.generator, "-DCMAKE_PREFIX_PATH=" + self.sdk.as_posix(),
                      "-DCMAKE_MODULE_PATH=" + (self.sdk / "share/ffmpeg").as_posix(),
                      "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>"])
        # Full static archives may produce very large executables. Test all
        # three interfaces with a filter that pulls the actual filter graph,
        # and exercise a module-only transitive link. The native CI tester
        # still runs its full target set.
        targets = ("check-avfilter", "check-full-avfilter", "check-legacy-avfilter",
                   "check-transitive-avformat")
        for config in ("Release", "Debug"):
            with self.subTest(config=config):
                for target in targets:
                    with self.subTest(target=target):
                        self.checked(["cmake", "--build", build, "--config", config,
                                      "--target", target, "--parallel", "2"], timeout=240)
                        exe = build / config / (target + ".exe")
                        self.checked([exe], env=self.runtime_env(), cwd=exe.parent)
                        # Avoid accumulating repeated copies of the static
                        # dependency closure and its linker-generated symbols.
                        for artifact in exe.parent.glob(target + ".*"):
                            if artifact.is_file():
                                artifact.unlink()
                print(f"Real locally built static SDK {config}: {len(targets)} Native Tester targets", flush=True)

    def test_locally_built_static_port_links_through_pkgconfig(self):
        src = self.root / "consumer"
        src.mkdir()
        (src / "main.c").write_text(r"""
#include <libavutil/avutil.h>
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavfilter/avfilter.h>
int main(void) {
#if LIBAVCODEC_VERSION_MAJOR < 58
    avcodec_register_all();
#endif
#if LIBAVFORMAT_VERSION_MAJOR < 58
    av_register_all();
#endif
#if LIBAVFILTER_VERSION_MAJOR < 7
    avfilter_register_all();
#endif
    return (!avutil_version() || !avcodec_find_decoder(AV_CODEC_ID_H264)
            || !av_find_input_format("matroska") || !avfilter_get_by_name("null"));
}
""", encoding="utf-8")
        (src / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(real_static_consumer C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(FFmpeg CONFIG REQUIRED)
get_target_property(kind FFmpeg::avformat TYPE)
if(NOT kind STREQUAL "STATIC_LIBRARY")
  message(FATAL_ERROR "Expected a locally built static FFmpeg installation")
endif()
set(PKG_CONFIG_USE_CMAKE_PREFIX_PATH FALSE)
find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED IMPORTED_TARGET libavformat libavcodec libavfilter libavutil)
add_executable(check-pkgconfig main.c)
target_link_libraries(check-pkgconfig PRIVATE PkgConfig::FFMPEG)
""", encoding="utf-8")
        for config, folder in (("Release", ""), ("Debug", "debug")):
            with self.subTest(config=config):
                pc_dirs = (self.sdk / folder / "lib/pkgconfig", self.sdk / "share/pkgconfig")
                paths = os.pathsep.join(map(str, pc_dirs))
                env = dict(os.environ, PKG_CONFIG_PATH=paths, PKG_CONFIG_LIBDIR=paths)
                env.pop("PKG_CONFIG_SYSROOT_DIR", None)
                # vcpkg folds private dependencies into the public fields of
                # static packages. Both forms must resolve; ordinary --libs
                # must be sufficient for an actual consumer link.
                for flags in ([], ["--static"]):
                    self.checked([PKGCONF, *flags, "--cflags", "--libs", "libavformat", "libavcodec", "libavfilter", "libavutil"], env=env)
                build = self.root / ("build-" + config)
                self.checked(["cmake", "-S", src, "-B", build, *self.generator,
                              "-DCMAKE_PREFIX_PATH=" + self.sdk.as_posix(),
                              "-DPKG_CONFIG_EXECUTABLE=" + Path(PKGCONF).as_posix(), "-DPKG_CONFIG_ARGN="], env=env)
                self.checked(["cmake", "--build", build, "--config", config, "--parallel", "2"], env=env)
                self.checked([build / config / "check-pkgconfig.exe"], env=self.runtime_env(), cwd=build / config)
