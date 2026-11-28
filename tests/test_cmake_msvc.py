"""Small real MSVC link tests; no FFmpeg source or third-party build required.

Run on a VS 2022 host with FFBUILD_TEST_MSVC=1 and pkgconf on PATH
(or FFBUILD_TEST_PKGCONF pointing to vcpkg's host pkgconf).
"""
import os
import shutil
from cmake_blackbox_fixture import run as run_command
import tempfile
import unittest
from pathlib import Path

from ffbuild.versions import ROOT

PKGCONF = os.environ.get("FFBUILD_TEST_PKGCONF") or shutil.which("pkgconf")


@unittest.skipUnless(os.name == "nt" and os.environ.get("FFBUILD_TEST_MSVC") == "1"
                     and shutil.which("cmake") and PKGCONF, "Opt-in MSVC + pkgconf test")
class NativeLinkageTests(unittest.TestCase):
    def test_static_dependency_crt_and_system_library(self):
        with tempfile.TemporaryDirectory(prefix="ffmpeg-cmake-msvc-") as tmp:
            root = Path(tmp)
            sdk = root / "sdk"
            producer = root / "producer"
            consumer = root / "consumer"
            producer.mkdir()
            consumer.mkdir()

            def run(args, *, success=True, reason=None):
                result = run_command([str(a) for a in args], timeout=120)
                output = result.stdout + result.stderr
                self.assertEqual(success, result.returncode == 0, output)
                if reason:
                    self.assertIn(reason, output)

            (producer / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(native_fixture CXX)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_library(third STATIC third.cpp)
add_library(avutil STATIC avutil.cpp)
set_target_properties(third PROPERTIES DEBUG_POSTFIX d)
foreach(t third avutil)
  set_target_properties(${t} PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY_RELEASE "${SDK}/lib"
    ARCHIVE_OUTPUT_DIRECTORY_DEBUG "${SDK}/debug/lib")
endforeach()
""")
            (producer / "third.cpp").write_text(r"""
#include <vector>
extern "C" int third(void) {
#ifdef _DEBUG
    std::vector<int> v{2};
#else
    std::vector<int> v{1};
#endif
    return v.at(0);
}
""")
            (producer / "avutil.cpp").write_text(r"""
#include <winsock2.h>
extern "C" int third(void);
extern "C" int avutil_version(void) {
    WSASetLastError(0);
    return third() + WSAGetLastError();
}
""")
            generator = ["-G", "Visual Studio 17 2022", "-A", "x64"]
            run(["cmake", "-S", producer, "-B", root / "pb", *generator, f"-DSDK={sdk.as_posix()}"])
            for cfg in ("Release", "Debug"):
                run(["cmake", "--build", root / "pb", "--config", cfg, "--parallel", "2"])

            header = sdk / "include/libavutil/avutil.h"
            header.parent.mkdir(parents=True)
            header.write_text('extern "C" int avutil_version(void);\n')
            for cfg, name in (("", "third"), ("debug", "thirdd")):
                pc = sdk / cfg / "lib/pkgconfig/libavutil.pc"
                pc.parent.mkdir(parents=True)
                pc.write_text("Name: libavutil\nDescription: Native fixture\nVersion: 56.1.0\n"
                              f"Libs: -lavutil -l{name} -lws2_32\n")
            metadata = sdk / "share/ffmpeg"
            run(["cmake", f"-DCURRENT_PACKAGES_DIR={sdk.as_posix()}",
                 f"-DCURRENT_INSTALLED_DIR={sdk.as_posix()}", f"-DPKGCONF={Path(PKGCONF).as_posix()}",
                 f"-DOUTPUT_DIR={metadata.as_posix()}", "-P", ROOT / "tests/test_ffmpeg_deps.cmake"])
            (consumer / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(consumer CXX)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(FFmpeg 4.4.8 EXACT CONFIG REQUIRED COMPONENTS avutil)
list(APPEND CMAKE_MODULE_PATH "${FFmpeg_DIR}")
find_package(FFmpeg MODULE REQUIRED)
find_package(FFmpeg CONFIG REQUIRED)
foreach(mode demand full legacy)
  add_executable(check-${mode} main.cpp)
  target_compile_definitions(check-${mode} PRIVATE EXPECTED=$<IF:$<CONFIG:Debug>,2,1>)
endforeach()
target_link_libraries(check-demand PRIVATE FFmpeg::avutil)
target_link_libraries(check-full PRIVATE FFmpeg::FFmpeg)
target_include_directories(check-legacy PRIVATE ${FFMPEG_INCLUDE_DIRS})
target_link_libraries(check-legacy PRIVATE ${FFMPEG_LIBRARIES})
""")
            (consumer / "main.cpp").write_text(r"""
#include <libavutil/avutil.h>
#include <vector>
int main() {
    std::vector<int> expected{EXPECTED};
    return avutil_version() == expected.at(0) ? 0 : 1;
}
""")
            build = root / "cb"
            args = ["cmake", "-S", consumer, "-B", build, *generator, f"-DCMAKE_PREFIX_PATH={sdk.as_posix()}"]
            run(args)
            for cfg in ("Release", "Debug"):
                run(["cmake", "--build", build, "--config", cfg, "--parallel", "2"])
                for mode in ("demand", "full", "legacy"):
                    run([build / cfg / f"check-{mode}.exe"])

            # Producer-side configuration integrity: a Release /MT archive
            # mislabeled as the Debug /MTd dependency must be rejected. This
            # is not a restriction on consumers of the public shared SDK.
            debug_lib = sdk / "debug/lib/thirdd.lib"
            shutil.copyfile(sdk / "lib/third.lib", debug_lib)
            run(["cmake", "--build", build, "--config", "Debug", "--target", "check-demand", "--clean-first"],
                success=False, reason="LNK2038")
            debug_lib.unlink()
            run(args + [f"-DCMAKE_LIBRARY_PATH={(sdk / 'lib').as_posix()}"],
                success=False, reason="thirdd.lib")
