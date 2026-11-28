"""Additional black-box package discovery, historical module and search tests."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cmake_blackbox_fixture import CONFIGS, ROOT, SDKFixture, TOOLS, output, run


@unittest.skipUnless(TOOLS, "CMake, Ninja and pkgconf required")
class SDKBoundaryContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def sdk(self, linkage="dynamic", *, generate=True):
        f = SDKFixture(self.root, linkage)
        if generate:
            self.generate(f)
        return f

    def generate(self, f, **kw):
        p = f.generate(**kw)
        self.assertEqual(0, p.returncode, output(p))
        if f.linkage == "static":
            f.install_deps()

    def configure(self, f, **kw):
        p = f.configure(**kw)
        self.assertEqual(0, p.returncode, output(p))
        return output(p)

    def standalone(self, f, source, *, extra=(), success=True):
        (f.src / "CMakeLists.txt").write_text(
            'cmake_minimum_required(VERSION 3.21)\nproject(probe LANGUAGES NONE)\n'
            'set(WIN32 TRUE)\nset(CMAKE_FIND_LIBRARY_PREFIXES "")\n'
            'set(CMAKE_FIND_LIBRARY_SUFFIXES ".lib")\n'
            'set(CMAKE_FIND_USE_PACKAGE_REGISTRY FALSE)\n'
            'set(CMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY FALSE)\n' + source,
            encoding="utf-8")
        p = run(["cmake", "-S", f.src, "-B", f.build, "-G", "Ninja",
                 "-DCMAKE_PREFIX_PATH=" + f.sdk.as_posix(),
                 "-DPROBE_MODULE_PATH=" + (f.sdk / "share/ffmpeg").as_posix(), *extra])
        self.assertEqual(success, p.returncode == 0, output(p))
        return output(p)

    def test_historical_modules_and_optional_components(self):
        f = self.sdk(generate=False)
        f.add_module("postproc", "54.0.0", ("avutil",))
        f.add_module("avresample", "3.1.0", ("avutil",))
        self.generate(f, extra=("-DFFMPEG_VERSION=3.4.14",))
        self.configure(f, after=r"""
find_package(FFmpeg 3.4 CONFIG REQUIRED COMPONENTS postproc avresample
             OPTIONAL_COMPONENTS nonexistent)
if(NOT FFmpeg_postproc_FOUND OR NOT FFmpeg_avresample_FOUND OR FFmpeg_nonexistent_FOUND)
  message(FATAL_ERROR "Incorrect historical component status")
endif()
""")
        for cfg in CONFIGS:
            f.assert_selection(self, cfg, "Debug" if cfg == "Debug" else "Release")

    def test_historical_debug_overlay_missing_module_falls_back_as_unit(self):
        f = self.sdk(generate=False)
        f.add_module("postproc", "55.1.0", ("avutil",))
        f.add_module("avresample", "4.0.0", ("avutil",))
        self.generate(f)
        (f.sdk / "debug/lib/avresample.lib").unlink()
        self.configure(f)
        f.assert_selection(self, "Debug", "Release")

    def test_minimal_avutil_only_package(self):
        f = self.sdk(generate=False)
        for m in ("avformat", "avcodec"):
            for cfg in ("", "debug"):
                (f.sdk / cfg / "lib" / (m + ".lib")).unlink()
                (f.sdk / cfg / "bin" / f.dll(m)).unlink()
                (f.sdk / cfg / "lib/pkgconfig" / ("lib" + m + ".pc")).unlink()
            shutil.rmtree(f.sdk / "include" / ("lib" + m))
            del f.modules[m], f.graph[m], f.flags[m]
        self.generate(f)
        self.configure(f, after=r"""
find_package(FFmpeg CONFIG REQUIRED COMPONENTS avutil OPTIONAL_COMPONENTS avcodec avformat)
if(NOT FFmpeg_avutil_FOUND OR FFmpeg_avcodec_FOUND OR FFmpeg_avformat_FOUND)
  message(FATAL_ERROR "Incorrect minimal package components")
endif()
if(TARGET FFmpeg::avcodec OR TARGET FFmpeg::avformat)
  message(FATAL_ERROR "Absent module exported")
endif()
""")
        f.assert_selection(self, "Debug", "Debug")

    def test_uppercase_legacy_module_with_components(self):
        f = self.sdk()
        self.configure(f, mode="MODULE", package="FFMPEG", after=r"""
if(NOT FFMPEG_FOUND OR NOT FFmpeg_FOUND OR NOT TARGET FFMPEG::ffmpeg)
  message(FATAL_ERROR "Legacy uppercase interface unavailable")
endif()
find_package(FFMPEG MODULE REQUIRED COMPONENTS avutil OPTIONAL_COMPONENTS nonexistent)
if(NOT FFMPEG_avutil_FOUND OR FFMPEG_nonexistent_FOUND)
  message(FATAL_ERROR "Incorrect uppercase component status")
endif()
""")
        f.assert_selection(self, "Debug", "Debug")

    def test_target_architecture_width_for_all_official_triplets(self):
        f = self.sdk(generate=False)
        for architecture, width in (("x86", 4), ("arm", 4), ("x64", 8), ("arm64", 8)):
            with self.subTest(architecture=architecture):
                self.generate(f, extra=("-DVCPKG_TARGET_ARCHITECTURE=" + architecture,))
                for consumer_width in (4, 8):
                    source = f"""
set(CMAKE_SIZEOF_VOID_P {consumer_width})
find_package(FFmpeg 4.4.8 EXACT CONFIG QUIET)
if(FFmpeg_FOUND AND NOT {width} EQUAL {consumer_width})
  message(FATAL_ERROR "Wrong target width accepted")
elseif(NOT FFmpeg_FOUND AND {width} EQUAL {consumer_width})
  message(FATAL_ERROR "Matching target width rejected")
endif()
"""
                    self.standalone(f, source)

    def test_quiet_failed_discovery_does_not_announce_success(self):
        f = self.sdk()
        (f.sdk / "bin" / f.dll("avutil")).unlink()
        log = self.standalone(f, r"""
find_package(FFmpeg CONFIG QUIET)
if(FFmpeg_FOUND)
  message(FATAL_ERROR "Broken SDK accepted")
endif()
""")
        self.assertNotRegex(log, r"(?im)^--.*(?:found ffmpeg|ffmpeg.*(?:->|=>))")

    def test_failed_exact_request_does_not_create_package_targets(self):
        f = self.sdk()
        # MODULE invokes the implementation before version evaluation.
        # A failed first discovery must not create linkable package targets.
        self.standalone(f, r"""
list(APPEND CMAKE_MODULE_PATH "${PROBE_MODULE_PATH}")
find_package(FFmpeg 99.0 EXACT MODULE QUIET)
if(FFmpeg_FOUND OR TARGET FFmpeg::FFmpeg OR TARGET FFmpeg::avutil)
  message(FATAL_ERROR "Rejected version exposed usable SDK targets")
endif()
find_package(FFmpeg 4.4.8 EXACT MODULE REQUIRED)
if(NOT TARGET FFmpeg::avutil)
  message(FATAL_ERROR "Later valid discovery failed")
endif()
""")

    def test_component_failure_propagates_to_dependent_modules(self):
        f = self.sdk("static")
        (f.sdk / "debug/lib/thirdd.lib").unlink()
        self.standalone(f, r"""
find_package(FFmpeg CONFIG QUIET COMPONENTS avformat)
if(FFmpeg_FOUND OR FFmpeg_avutil_FOUND OR FFmpeg_avcodec_FOUND OR FFmpeg_avformat_FOUND)
  message(FATAL_ERROR "Broken transitive component reported usable")
endif()
""")

    def test_debug_sdk_not_discovered_from_unrelated_search_path(self):
        f = self.sdk()
        external = self.root / "foreign"
        shutil.copytree(f.sdk / "debug", external)
        shutil.rmtree(f.sdk / "debug")
        self.configure(f, extra=("-DCMAKE_LIBRARY_PATH=" + (external / "lib").as_posix(),
                                 "-DCMAKE_PREFIX_PATH=" + f.sdk.as_posix() + ";" + external.as_posix()))
        f.assert_selection(self, "Debug", "Release")

    def test_module_discovery_without_pkgconf(self):
        f = self.sdk("static")
        # Disable external program lookup and poison PkgConfig discovery
        # explicitly. Installed SDK consumption must not invoke it at all.
        self.configure(f, mode="MODULE", before=r"""
set(CMAKE_DISABLE_FIND_PACKAGE_PkgConfig TRUE)
set(PKG_CONFIG_EXECUTABLE "${CMAKE_BINARY_DIR}/nonexistent-pkgconf")
set(CMAKE_FIND_USE_SYSTEM_ENVIRONMENT_PATH FALSE)
""", extra=("-DCMAKE_MAKE_PROGRAM=" + Path(shutil.which("ninja")).as_posix(),))
        f.assert_selection(self, "Debug", "Debug")

    def test_later_quiet_or_failed_lookup_does_not_corrupt_valid_package(self):
        f = self.sdk()
        self.configure(f, after=r"""
find_package(FFmpeg 99 CONFIG QUIET)
if(FFmpeg_FOUND)
  message(FATAL_ERROR "Invalid version accepted")
endif()
find_package(FFmpeg CONFIG QUIET COMPONENTS nonexistent)
if(FFmpeg_FOUND)
  message(FATAL_ERROR "Invalid component accepted")
endif()
find_package(FFmpeg 4.4.8 EXACT CONFIG REQUIRED COMPONENTS avutil)
if(NOT FFmpeg_FOUND OR NOT FFmpeg_avutil_FOUND)
  message(FATAL_ERROR "Valid package state lost")
endif()
""")
        f.assert_selection(self, "Release", "Release")

    def test_compatible_explicit_debug_postfix(self):
        f = self.sdk()
        for m in f.modules:
            (f.sdk / "debug/lib" / (m + ".lib")).rename(f.sdk / "debug/lib" / (m + "d.lib"))
        self.configure(f)
        rows = f.rows("Debug")
        for m in f.modules:
            self.assertEqual((f.sdk / "debug/lib" / (m + "d.lib")).resolve(), Path(rows[m][0]).resolve())
            self.assertEqual((f.sdk / "debug/bin" / f.dll(m)).resolve(), Path(rows[m][1]).resolve())

    def test_imported_target_configuration_cannot_disagree_with_legacy(self):
        f = self.sdk("static")
        # Standard CMake permits mappings before package discovery. The
        # package may explicitly reject an unsupported override, but it
        # cannot silently make only part of the link use the opposite CRT.
        p = f.configure(before="set(CMAKE_MAP_IMPORTED_CONFIG_RELWITHDEBINFO DEBUG)")
        if p.returncode:
            self.assertRegex(output(p), r"(?is)(configuration|RelWithDebInfo).*(unsupported|incompatible|conflict)")
        else:
            # Standard configuration retains its established Release default;
            # a fully honored mapping is also coherent.
            row = f.rows("RelWithDebInfo")["avutil"][0]
            expected = "Debug" if "/debug/" in row.replace(chr(92), "/") else "Release"
            f.assert_selection(self, "RelWithDebInfo", expected)


@unittest.skipUnless(TOOLS, "CMake, Ninja and pkgconf required")
class ProducerBoundaryContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.f = SDKFixture(Path(tmp.name), "static")

    def generate(self):
        p = self.f.generate()
        self.assertEqual(0, p.returncode, output(p))
        self.f.install_deps()

    def reject(self, pattern):
        p = self.f.generate()
        self.assertNotEqual(0, p.returncode, output(p))
        self.assertRegex(output(p), pattern)

    def test_quoted_third_party_pc_path_in_space_containing_install(self):
        f = self.f
        moved = f.root / "installed dependencies"
        f.deps.rename(moved)
        f.deps = moved
        for cfg, name in (("", "third"), ("debug", "thirdd")):
            pc = f.deps / cfg / "lib/pkgconfig"
            pc.mkdir(parents=True)
            f.touch(f.deps / cfg / "lib/manual-link" / (name + ".lib"))
            (pc / "third.pc").write_text(
                'prefix=${pcfiledir}/../..\nName: third\nDescription: third-party package\n'
                'Version: 1.0\nLibs: "-L${prefix}/lib/manual-link" -l' + name + '\n')
            module = f.sdk / cfg / "lib/pkgconfig/libavutil.pc"
            module.write_text("Name: libavutil\nDescription: fixture\nVersion: 56.1.0\n"
                              "Requires: third\nLibs: -lavutil -lws2_32\n")
        self.generate()
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        for config, cfg, name in (("Release", "", "third"), ("Debug", "debug", "thirdd")):
            with self.subTest(config=config):
                expected = (f.sdk / cfg / "lib/manual-link" / (name + ".lib")).resolve()
                actual = f.rows(config)["deps-avutil"][0].split(";")
                self.assertIn(expected, [Path(x).resolve() for x in actual if x.lower().endswith(".lib")])

    def test_explicit_filename_library_syntax(self):
        f = self.f
        f.flags["avutil"] = ("-l:third.lib", "-l:thirdd.lib")
        f.write_pc()
        self.generate()
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        f.assert_selection(self, "Release", "Release")
        f.assert_selection(self, "Debug", "Debug")

    def test_absolute_matching_archive_is_relocatable(self):
        f = self.f
        f.flags["avutil"] = tuple((f.deps / cfg / "lib" / name).as_posix()
                                   for cfg, name in (("", "third.lib"), ("debug", "thirdd.lib")))
        f.write_pc()
        self.generate()
        shutil.rmtree(f.deps)
        moved = f.root / "relocated"
        f.sdk.rename(moved)
        f.sdk = moved
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        f.assert_selection(self, "Debug", "Debug")
        f.assert_selection(self, "Release", "Release")

    def test_manual_link_precedence_with_identical_archive_names(self):
        f = self.f
        for cfg, name in (("", "third.lib"), ("debug", "thirdd.lib")):
            f.touch(f.deps / cfg / "lib/manual-link" / name)
        f.flags["avutil"] = tuple(f'-L"{(f.deps / cfg / "lib/manual-link").as_posix()}" -L"{(f.deps / cfg / "lib").as_posix()}" -l{name}'
                                  for cfg, name in (("", "third"), ("debug", "thirdd")))
        f.write_pc()
        self.generate()
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        for cfg, name in (("Release", "third.lib"), ("Debug", "thirdd.lib")):
            prefix = f.sdk / ("debug" if cfg == "Debug" else "")
            expected = (prefix / "lib/manual-link" / name).resolve()
            for row in ("deps-avutil", "legacy"):
                paths = [Path(x).resolve() for x in f.rows(cfg)[row][0].split(";") if x.lower().endswith(".lib")]
                self.assertIn(expected, paths)
                self.assertNotIn((prefix / "lib" / name).resolve(), paths)

    def test_shared_private_graph_without_private_archives(self):
        f = self.f
        f.linkage = "dynamic"
        for m in f.modules:
            f.flags[m] = ("", "")
            for cfg in ("", "debug"):
                f.touch(f.sdk / cfg / "bin" / f.dll(m))
        f.write_pc()
        for cfg in ("", "debug"):
            for pc in (f.sdk / cfg / "lib/pkgconfig").glob("*.pc"):
                pc.write_text(pc.read_text().replace("Requires:", "Requires.private:"))
        # No third party archives are installed into this public SDK.
        p = f.generate()
        self.assertEqual(0, p.returncode, output(p))
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        for cfg in ("Release", "Debug"):
            f.assert_selection(self, cfg, cfg)
            for m, deps in f.graph.items():
                items = f.rows(cfg)["deps-" + m][0].split(";")
                for dep in deps:
                    self.assertIn("FFmpeg::" + dep, items)

    def test_debug_only_extra_module_rejected(self):
        f = self.f
        pc = f.sdk / "debug/lib/pkgconfig/libextra.pc"
        pc.write_text("Name: libextra\nDescription: unexpected\nVersion: 1.0\nLibs: -lextra\n")
        self.reject(r"(?is)(module|extra|debug)")

    def test_declared_required_module_with_missing_header_rejected(self):
        f = self.f
        (f.sdk / "include/libavcodec/avcodec.h").unlink()
        self.reject(r"(?is)(avcodec|header)")


    def test_historical_4_4_8_tesseract_and_zeromq_names_reach_link_interface(self):
        f = self.f
        # This is the exact historical naming divergence that triggered
        # the 4.4.8 native static Debug link failure.
        releases = ("tesseract55", "libzmq-mt-s-4_3_5")
        debugs = ("tesseract55d", "libzmq-mt-sgd-4_3_5")
        f.flags["avcodec"] = ("-lsecond " + " ".join("-l" + n for n in releases),
                             "-lsecond " + " ".join("-l" + n for n in debugs))
        for cfg, names in (("", releases), ("debug", debugs)):
            for name in names:
                f.touch(f.deps / cfg / "lib" / (name + ".lib"))
        f.write_pc()
        self.generate()
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        for cfg, names, opposite in (("Release", releases, debugs), ("Debug", debugs, releases)):
            f.assert_selection(self, cfg, cfg)
            prefix = f.sdk / ("debug" if cfg == "Debug" else "")
            for row in ("deps-avcodec", "legacy"):
                paths = [Path(x).resolve() for x in f.rows(cfg)[row][0].split(";") if x.lower().endswith(".lib")]
                for name in names:
                    self.assertIn((prefix / "lib" / (name + ".lib")).resolve(), paths)
                self.assertTrue(all(p.stem not in opposite for p in paths), (cfg, row))
