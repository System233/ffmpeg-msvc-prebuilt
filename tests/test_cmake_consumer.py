import shutil
from cmake_blackbox_fixture import canonical_existing_path, filesystem_alias, run as run_command
import tempfile
import unittest
from pathlib import Path

from ffbuild.versions import ROOT

GENERATOR = ROOT / "scripts/cmake/package-config.cmake"


@unittest.skipUnless(shutil.which("cmake") and shutil.which("ninja"), "CMake and Ninja required")
class CMakeConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sdk = self.root / "sdk"
        self.src = self.root / "src"
        self.src.mkdir()
        self.build = self.root / "build"
        self.modules = {"avutil": ("56.1.0", "avutil.h", "", "", ""),
                        "avcodec": ("58.1.0", "avcodec.h", "avutil", "", "")}
        self.linkage = "static"
        self.version = "4.4.8"
        for name, (_, header, *_) in self.modules.items():
            for path in (f"include/lib{name}/{header}", f"lib/{name}.lib", f"debug/lib/{name}.lib"):
                self.touch(path)

    def touch(self, name):
        path = self.sdk / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def render(self):
        records = []
        for name, (version, header, deps, release, debug) in self.modules.items():
            for key, value in (("VERSION", version), ("HEADER", header), ("DEPS", deps),
                               ("RELEASE", release), ("DEBUG", debug)):
                records.append(f'set(_ff_{name}_{key} [==[{value}]==])')
        script = self.root / "render.cmake"
        script.write_text(
            'cmake_minimum_required(VERSION 3.21)\n'
            f'set(FFMPEG_VERSION "{self.version}")\n'
            f'set(VCPKG_LIBRARY_LINKAGE "{self.linkage}")\n'
            'set(VCPKG_TARGET_ARCHITECTURE x64)\n'
            f'set(FFMPEG_MODULES "{";".join(self.modules)}")\n'
            'set(FFMPEG_MODULE_METADATA [====[' + "\n".join(records) + ']====])\n'
            f'include("{GENERATOR.as_posix()}")\n'
            f'ffmpeg_install_cmake_package("{(self.sdk / "share/ffmpeg").as_posix()}")\n',
            encoding="utf-8",
        )
        run_command(["cmake", "-P", str(script)], check=True)

    def configure(self, body, *, success=True, reason=None, multi=True, config="Debug",
                  config_only=False, extra=()):
        self.render()
        (self.build / "selected-location.txt").unlink(missing_ok=True)
        preamble = """cmake_minimum_required(VERSION 3.21)
project(consumer LANGUAGES NONE)
set(WIN32 TRUE)
set(CMAKE_FIND_LIBRARY_PREFIXES "")
set(CMAKE_FIND_LIBRARY_SUFFIXES ".lib")
"""
        if not config_only:
            preamble += 'list(APPEND CMAKE_MODULE_PATH "${FFMPEG_ROOT}/share/ffmpeg")\n'
        (self.src / "CMakeLists.txt").write_text(preamble + body, encoding="utf-8")
        args = ["cmake", "-S", str(self.src), "-B", str(self.build),
                "-G", "Ninja Multi-Config" if multi else "Ninja",
                "-DCMAKE_PREFIX_PATH=" + self.sdk.as_posix()]
        if not config_only:
            args += ["-DFFMPEG_ROOT=" + self.sdk.as_posix()]
        if multi:
            args += ["-DCMAKE_CONFIGURATION_TYPES=Debug;Release;RelWithDebInfo;MinSizeRel"]
        else:
            args += ["-DCMAKE_BUILD_TYPE=" + config]
        result = run_command(args + list(extra))
        output = result.stdout + result.stderr
        self.assertEqual(success, result.returncode == 0, output)
        if reason:
            self.assertIn(reason, output)

    def test_repeat_and_sibling_scope(self):
        for name in ("a", "b"):
            p = self.src / name
            p.mkdir()
            (p / "CMakeLists.txt").write_text("find_package(FFmpeg REQUIRED)\n")
        self.configure("""add_subdirectory(a)
add_subdirectory(b)
find_package(FFmpeg REQUIRED)
find_package(FFmpeg REQUIRED)
get_target_property(libs FFmpeg::FFmpeg INTERFACE_LINK_LIBRARIES)
if(NOT libs STREQUAL "FFmpeg::avutil;FFmpeg::avcodec")
  message(FATAL_ERROR "Duplicate or missing targets: ${libs}")
endif()
""")

    def test_required_and_optional_component(self):
        self.configure("find_package(FFmpeg REQUIRED COMPONENTS avfilter)\n",
                       success=False, reason="avfilter")

    def test_optional_component(self):
        self.configure("""find_package(FFmpeg REQUIRED OPTIONAL_COMPONENTS postproc)
if(FFmpeg_postproc_FOUND)
  message(FATAL_ERROR "Missing optional module found")
endif()
""")

    def test_legacy_reconfigure(self):
        body = """find_package(FFmpeg REQUIRED)
if(NOT FFMPEG_LIBRARY STREQUAL FFMPEG_LIBRARIES)
  message(FATAL_ERROR "Legacy variable lost")
endif()
"""
        self.configure(body)
        self.configure(body)

    def test_missing_static_debug(self):
        (self.sdk / "debug/lib/avutil.lib").unlink()
        self.configure("find_package(FFmpeg REQUIRED)\n", success=False, reason="avutil")

    def test_missing_static_release(self):
        (self.sdk / "lib/avutil.lib").unlink()
        self.configure("find_package(FFmpeg REQUIRED)\n", success=False, reason="avutil")

    def test_missing_shared_dll(self):
        self.linkage = "dynamic"
        self.touch("bin/avcodec-58.dll")
        self.configure("find_package(FFmpeg REQUIRED)\n", success=False, reason="avutil")

    def test_historical_module(self):
        self.modules["postproc"] = ("55.1.0", "postprocess.h", "avutil", "", "")
        for name in ("include/libpostproc/postprocess.h", "lib/postproc.lib", "debug/lib/postproc.lib"):
            self.touch(name)
        self.configure("""find_package(FFmpeg REQUIRED COMPONENTS postproc)
if(NOT TARGET FFmpeg::postproc OR NOT TARGET FFMPEG::postproc)
  message(FATAL_ERROR "Historical module absent")
endif()
""")

    def test_static_dependency_never_falls_back(self):
        self.modules["avutil"] = ("56.1.0", "avutil.h", "", "vcpkg-lib:third.lib", "vcpkg-lib:third.lib")
        self.touch("lib/third.lib")
        self.configure("""list(APPEND CMAKE_LIBRARY_PATH "${FFMPEG_ROOT}/lib")
find_package(FFmpeg REQUIRED)
""", success=False, reason="third.lib")

    def test_system_dependency_and_config_paths(self):
        self.modules["avutil"] = ("56.1.0", "avutil.h", "", "vcpkg-lib:third.lib;ws2_32", "vcpkg-lib:thirdd.lib;ws2_32")
        self.touch("lib/third.lib")
        self.touch("debug/lib/thirdd.lib")
        self.configure("""find_package(FFmpeg REQUIRED)
get_target_property(libs FFmpeg::avutil INTERFACE_LINK_LIBRARIES)
if(NOT libs MATCHES "/debug/lib/thirdd.lib" OR NOT libs MATCHES "/lib/third.lib" OR NOT libs MATCHES "ws2_32")
  message(FATAL_ERROR "Wrong dependency metadata: ${libs}")
endif()
""")

    def assert_release_location(self):
        actual = (self.build / "selected-location.txt").read_text(encoding="utf-8")
        self.assertEqual(canonical_existing_path(self.sdk / "lib/avutil.lib"),
                         canonical_existing_path(actual))

    def test_relocate_cached_sdk(self):
        body = """find_package(FFmpeg REQUIRED)
get_target_property(loc FFmpeg::avutil IMPORTED_LOCATION_RELEASE)
file(WRITE "${CMAKE_BINARY_DIR}/selected-location.txt" "${loc}")
"""
        self.configure(body)
        self.assert_release_location()
        moved = self.root / "moved sdk"
        self.sdk.rename(moved)
        self.sdk = moved
        self.configure(body)
        self.assert_release_location()

    def test_changed_root_in_one_configure_rejected(self):
        self.configure("""find_package(FFmpeg REQUIRED)
set(FFMPEG_ROOT "${FFMPEG_ROOT}/another")
find_package(FFmpeg REQUIRED)
""", success=False, reason="different SDK")

    def test_cached_library_removed(self):
        self.configure("find_package(FFmpeg REQUIRED)\n")
        (self.sdk / "lib/avcodec.lib").unlink()
        self.configure("find_package(FFmpeg REQUIRED)\n", success=False, reason="avcodec")

    def test_configuration_mapping(self):
        self.configure("""find_package(FFmpeg REQUIRED)
file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/selected-$<CONFIG>.txt"
     CONTENT "$<TARGET_LINKER_FILE:FFmpeg::avutil>")
""")
        for cfg in ("Release", "RelWithDebInfo", "MinSizeRel", "Debug"):
            expected = self.sdk / ("debug/lib" if cfg == "Debug" else "lib") / "avutil.lib"
            actual = (self.build / f"selected-{cfg}.txt").read_text()
            self.assertEqual(expected.resolve(), Path(actual).resolve())

    def test_missing_internal_dependency(self):
        self.modules["avcodec"] = ("58.1.0", "avcodec.h", "avfilter", "", "")
        self.configure("find_package(FFmpeg REQUIRED)\n", success=False, reason="missing internal dependency avfilter")

    def test_repeated_version_requests(self):
        self.configure("""find_package(FFmpeg 4.0 REQUIRED)
find_package(FFmpeg 99.0 QUIET)
if(FFmpeg_FOUND)
  message(FATAL_ERROR "Version requirement ignored")
endif()
find_package(FFmpeg 4.4.8 EXACT REQUIRED)
""")

    def test_config_prefix_discovery_without_module_path_or_legacy_root(self):
        self.configure("""find_package(FFmpeg 4.4.8 EXACT CONFIG REQUIRED COMPONENTS avcodec)
if(NOT TARGET FFmpeg::avcodec OR NOT FFmpeg_avcodec_FOUND OR NOT FFMPEG_FOUND)
  message(FATAL_ERROR "Config mode did not publish targets and variables")
endif()
if(NOT FFmpeg_VERSION STREQUAL "4.4.8" OR NOT FFMPEG_VERSION STREQUAL FFmpeg_VERSION)
  message(FATAL_ERROR "Wrong version metadata")
endif()
if(CMAKE_MODULE_PATH OR DEFINED FFMPEG_ROOT)
  message(FATAL_ERROR "Config mode unexpectedly required legacy discovery")
endif()
""", config_only=True)

    def test_config_version_selection(self):
        self.configure("""find_package(FFmpeg 3.4 CONFIG REQUIRED)
find_package(FFmpeg 4.0...<5.0 CONFIG REQUIRED)
find_package(FFmpeg 4.4.7 EXACT CONFIG QUIET)
if(FFmpeg_FOUND)
  message(FATAL_ERROR "Wrong EXACT version accepted")
endif()
find_package(FFmpeg 5.0 CONFIG QUIET)
if(FFmpeg_FOUND)
  message(FATAL_ERROR "Wrong minimum version accepted")
endif()
find_package(FFmpeg 4.4.8 EXACT CONFIG REQUIRED)
""", config_only=True)

    def test_config_required_component_missing(self):
        self.configure("find_package(FFmpeg CONFIG REQUIRED COMPONENTS postproc)\n",
                       config_only=True, success=False, reason="postproc")

    def test_config_optional_component(self):
        self.configure("""find_package(FFmpeg CONFIG REQUIRED OPTIONAL_COMPONENTS postproc)
if(FFmpeg_postproc_FOUND)
  message(FATAL_ERROR "Unavailable optional component reported present")
endif()
""", config_only=True)

    def test_config_module_interoperability(self):
        for first, second in (("CONFIG", "MODULE"), ("MODULE", "CONFIG")):
            with self.subTest(first=first):
                self.configure(f"""find_package(FFmpeg {first} REQUIRED)
find_package(FFmpeg {second} REQUIRED)
get_target_property(libs FFmpeg::FFmpeg INTERFACE_LINK_LIBRARIES)
if(NOT libs STREQUAL "FFmpeg::avutil;FFmpeg::avcodec")
  message(FATAL_ERROR "Duplicate or missing targets: ${{libs}}")
endif()
""")

    def test_config_uses_selected_package_not_stale_legacy_root(self):
        self.configure("""find_package(FFmpeg CONFIG REQUIRED)
get_target_property(loc FFmpeg::avutil IMPORTED_LOCATION_RELEASE)
file(WRITE "${CMAKE_BINARY_DIR}/selected-location.txt" "${loc}")
""", config_only=True, extra=["-DFFMPEG_ROOT=" + (self.root / "unrelated").as_posix()])
        self.assert_release_location()

    def test_config_target_pointer_width(self):
        self.configure("""set(CMAKE_SIZEOF_VOID_P 4)
find_package(FFmpeg CONFIG REQUIRED)
""", config_only=True, success=False, reason="64bit")

    def test_config_relocation(self):
        body = """find_package(FFmpeg CONFIG REQUIRED)
get_target_property(loc FFmpeg::avutil IMPORTED_LOCATION_RELEASE)
file(WRITE "${CMAKE_BINARY_DIR}/selected-location.txt" "${loc}")
"""
        self.configure(body, config_only=True)
        self.assert_release_location()
        moved = self.root / "new prefix"
        self.sdk.rename(moved)
        self.sdk = moved
        self.configure(body, config_only=True)
        self.assert_release_location()

    def test_config_relocation_via_windows_path_alias(self):
        alias, kind = filesystem_alias(self.root)
        self.assertNotEqual(alias, self.root.resolve())
        self.assertTrue(alias.samefile(self.root))
        print(f"Windows Config path alias regression: {kind}", flush=True)
        self.root = alias
        self.sdk = alias / "sdk"
        self.test_config_relocation()

        # A real but different archive, or a relative/missing location,
        # must not pass the same filesystem-normalized comparison.
        evidence = self.build / "selected-location.txt"
        correct = evidence.read_text(encoding="utf-8")
        for wrong in (self.sdk / "debug/lib/avutil.lib", self.sdk / "lib/missing.lib",
                      Path("avutil.lib")):
            with self.subTest(wrong=str(wrong)):
                evidence.write_text(wrong.as_posix(), encoding="utf-8")
                with self.assertRaises((AssertionError, FileNotFoundError)):
                    self.assert_release_location()
        evidence.write_text(correct, encoding="utf-8")
        self.assert_release_location()

    def test_config_mixed_sibling_scope(self):
        for name, mode in (("a", "CONFIG"), ("b", "MODULE")):
            p = self.src / name
            p.mkdir()
            (p / "CMakeLists.txt").write_text(f"find_package(FFmpeg {mode} REQUIRED)\n")
        self.configure("""add_subdirectory(a)
add_subdirectory(b)
get_target_property(libs FFmpeg::FFmpeg INTERFACE_LINK_LIBRARIES)
if(NOT libs STREQUAL "FFmpeg::avutil;FFmpeg::avcodec")
  message(FATAL_ERROR "Inconsistent sibling targets")
endif()
""")

    def test_config_explicit_directory(self):
        self.configure("""find_package(FFmpeg CONFIG REQUIRED)
if(NOT TARGET FFmpeg::FFmpeg)
  message(FATAL_ERROR "Config directory did not load package")
endif()
""", config_only=True, extra=["-DCMAKE_PREFIX_PATH=",
                              "-DFFmpeg_DIR=" + (self.sdk / "share/ffmpeg").as_posix()])

    def test_config_master_snapshot_version(self):
        self.version = "9.1-12-gabcdef0"
        self.configure("""find_package(FFmpeg 9.1 CONFIG REQUIRED)
if(NOT FFmpeg_VERSION STREQUAL "9.1-12-gabcdef0")
  message(FATAL_ERROR "Master source identity lost")
endif()
find_package(FFmpeg 9.1 EXACT CONFIG QUIET)
if(FFmpeg_FOUND)
  message(FATAL_ERROR "Snapshot incorrectly accepted as exact release")
endif()
find_package(FFmpeg CONFIG REQUIRED)
""", config_only=True)
