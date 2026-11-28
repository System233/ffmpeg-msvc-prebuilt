"""Consumer/producer contract tests. Known defects intentionally fail (RED)."""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from cmake_blackbox_fixture import CONFIGS, SDKFixture, TOOLS, output


@unittest.skipUnless(TOOLS, "CMake, Ninja and pkgconf required")
class SDKContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def fixture(self, linkage="dynamic", *, generate=True):
        f = SDKFixture(self.root, linkage)
        if generate:
            p = f.generate()
            self.assertEqual(0, p.returncode, output(p))
            if linkage == "static":
                f.install_deps()
        return f

    def configured(self, f, **kwargs):
        p = f.configure(**kwargs)
        self.assertEqual(0, p.returncode, output(p))
        return output(p)

    def test_shared_configuration_matrix_and_interfaces(self):
        f = self.fixture()
        for mode in ("CONFIG", "MODULE"):
            with self.subTest(mode=mode):
                self.configured(f, mode=mode)
                for config in CONFIGS:
                    f.assert_selection(self, config, "Debug" if config == "Debug" else "Release")

    def test_shared_overlay_lifecycle(self):
        f = self.fixture()
        overlay = self.root / "overlay"
        f.sdk.joinpath("debug").rename(overlay)
        for stage in ("absent", "partial-dll", "partial-lib", "complete", "removed"):
            with self.subTest(stage=stage):
                if stage == "partial-dll":
                    shutil.copytree(overlay, f.sdk / "debug")
                    (f.sdk / "debug/bin" / f.dll("avcodec")).unlink()
                elif stage == "partial-lib":
                    shutil.copy2(overlay / "bin" / f.dll("avcodec"), f.sdk / "debug/bin")
                    (f.sdk / "debug/lib/avformat.lib").unlink()
                elif stage == "complete":
                    shutil.copy2(overlay / "lib/avformat.lib", f.sdk / "debug/lib")
                elif stage == "removed":
                    shutil.rmtree(f.sdk / "debug")
                    f.touch(f.sdk / "debug/bin/avutil.pdb")
                self.configured(f)
                for config in CONFIGS:
                    f.assert_selection(self, config, "Debug" if stage == "complete" and config == "Debug" else "Release")

    def test_single_config_switch_and_empty_configuration(self):
        f = self.fixture("static")
        for config in ("Release", "Debug", "", "MinSizeRel", "Debug"):
            with self.subTest(config=config):
                self.configured(f, single=config)
                f.assert_selection(self, config, "Debug" if config == "Debug" else "Release")

    def test_relocated_sdk_with_spaces_and_unicode(self):
        f = self.fixture("static")
        self.configured(f)
        moved = self.root / "relocated sdk 中文"
        f.sdk.rename(moved)
        f.sdk = moved
        self.configured(f)
        f.assert_selection(self, "Debug", "Debug")

    def test_missing_release_dll_never_uses_debug(self):
        f = self.fixture()
        (f.sdk / "bin" / f.dll("avcodec")).unlink()
        p = f.configure()
        self.assertNotEqual(0, p.returncode, output(p))
        self.assertIn("avcodec", output(p).lower())

    def test_static_requires_both_configurations(self):
        f = self.fixture("static")
        shutil.rmtree(f.sdk / "debug")
        p = f.configure(single="Debug")
        self.assertNotEqual(0, p.returncode, output(p))

    def test_global_debug_configurations_consistent(self):
        f = self.fixture("static")
        p = f.configure(configs=("Debug", "Release", "ASan"),
                        before="set_property(GLOBAL PROPERTY DEBUG_CONFIGURATIONS Debug ASan)")
        if p.returncode:
            self.assertRegex(output(p), r"(?is)(ASan|configuration).*(unsupported|incompatible|conflict)|unsupported.*configuration")
        else:
            f.assert_selection(self, "ASan", "Debug")

    def test_imported_config_mapping_consistent(self):
        f = self.fixture("static")
        p = f.configure(configs=("Debug", "Release", "ASan"),
                        before="set(CMAKE_MAP_IMPORTED_CONFIG_ASAN DEBUG)")
        if p.returncode:
            self.assertRegex(output(p), r"(?is)(ASan|configuration).*(unsupported|incompatible|conflict)|unsupported.*configuration")
        else:
            f.assert_selection(self, "ASan", "Debug")

    @staticmethod
    def mapping_lines(log, config, selected):
        # Semantic contract: a FFmpeg line identifies source and selected
        # configuration in that order; punctuation and spacing are flexible.
        return [line for line in log.splitlines() if re.search(
            rf"(?i)\bFFmpeg\b.*\b{config}\b.*(?:->|=>|:|uses?|links?|mapped|selects?)\s*(?:to\s+)?\b{selected}\b", line)]

    def test_reports_release_fallback(self):
        f = self.fixture()
        shutil.rmtree(f.sdk / "debug")
        log = self.configured(f, single="Debug")
        f.assert_selection(self, "Debug", "Release")
        self.assertTrue(self.mapping_lines(log, "Debug", "Release"), "Missing actual Debug -> Release diagnostic")

    def test_reports_all_multiconfig_selections_once(self):
        f = self.fixture()
        log = self.configured(f, repeat=True)
        for config in CONFIGS:
            with self.subTest(config=config):
                expected = "Debug" if config == "Debug" else "Release"
                f.assert_selection(self, config, expected)
                self.assertEqual(1, len(self.mapping_lines(log, config, expected)), f"Missing or duplicate {config} diagnostic")

    def test_reports_incomplete_overlay(self):
        f = self.fixture()
        (f.sdk / "debug/bin" / f.dll("avcodec")).unlink()
        log = self.configured(f, single="Debug")
        f.assert_selection(self, "Debug", "Release")
        with self.subTest(diagnostic="mapping"):
            self.assertTrue(self.mapping_lines(log, "Debug", "Release"))
        with self.subTest(diagnostic="incomplete"):
            self.assertRegex(log, r"(?is)(incomplete|partial|missing).{0,160}(debug|avcodec)|(debug|avcodec).{0,160}(incomplete|partial|missing)")

    def test_quiet_discovery_suppresses_mapping(self):
        f = self.fixture()
        log = self.configured(f, quiet=True)
        self.assertFalse(re.search(r"(?im)^--.*(?:found ffmpeg|ffmpeg.*(?:->|=>))", log))

    def test_single_config_reports_only_active_selection(self):
        f = self.fixture()
        log = self.configured(f, single="Release")
        self.assertTrue(self.mapping_lines(log, "Release", "Release"))
        self.assertFalse(self.mapping_lines(log, "Debug", "Debug"))

    def test_module_metadata_cannot_be_used_with_other_sdk(self):
        f = self.fixture()
        other = self.root / "another"
        shutil.copytree(f.sdk, other)
        # A different valid package version, generated through the same producer.
        original = f.sdk
        f.sdk = other
        p = f.generate(extra=("-DFFMPEG_VERSION=8.1.3",))
        self.assertEqual(0, p.returncode, output(p))
        f.sdk = original
        p = f.configure(mode="MODULE", extra=("-DFFMPEG_ROOT=" + other.as_posix(),))
        if p.returncode:
            self.assertRegex(output(p), r"(?is)(sdk|root|metadata|package).*(different|mismatch|conflict|inconsistent)")
        else:
            # Either honor the loaded package, or re-discover B coherently.
            path = Path(f.rows("Release")["avutil"][0]).resolve()
            actual_version = f.rows("Release")["version"][0]
            valid = {
                (original / "lib/avutil.lib").resolve(): "4.4.8",
                (other / "lib/avutil.lib").resolve(): "8.1.3",
            }
            self.assertIn(path, valid)
            self.assertEqual(valid[path], actual_version, "SDK version and selected library belong to different packages")

    def test_missing_dependency_does_not_report_component_found(self):
        f = self.fixture("static")
        (f.sdk / "debug/lib/thirdd.lib").unlink()
        # Use a separate public consumer so failure is inspected rather than
        # aborted by REQUIRED.
        (f.src / "CMakeLists.txt").write_text(r"""
cmake_minimum_required(VERSION 3.21)
project(probe LANGUAGES NONE)
set(WIN32 TRUE)
set(CMAKE_FIND_LIBRARY_PREFIXES "")
set(CMAKE_FIND_LIBRARY_SUFFIXES ".lib")
find_package(FFmpeg CONFIG QUIET COMPONENTS avutil)
if(FFmpeg_FOUND OR FFmpeg_avutil_FOUND OR FFMPEG_libavutil_FOUND)
  message(FATAL_ERROR "Invalid component reported as available")
endif()
if(TARGET FFmpeg::avutil)
  message(FATAL_ERROR "Invalid component target exposed")
endif()
""", encoding="utf-8")
        from cmake_blackbox_fixture import run
        p = run(["cmake", "-S", f.src, "-B", f.build, "-G", "Ninja",
                 "-DCMAKE_PREFIX_PATH=" + f.sdk.as_posix()])
        self.assertEqual(0, p.returncode, output(p))


@unittest.skipUnless(TOOLS, "CMake, Ninja and pkgconf required")
class ProducerContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.f = SDKFixture(Path(tmp.name), "static")

    def generate_ok(self, **kwargs):
        p = self.f.generate(**kwargs)
        self.assertEqual(0, p.returncode, output(p))
        self.f.install_deps()

    def assert_rejected(self, pattern, **kwargs):
        p = self.f.generate(**kwargs)
        self.assertNotEqual(0, p.returncode, "Invalid input accepted:\n" + output(p))
        self.assertRegex(output(p), pattern)

    def test_generated_package_consumes_distinct_dependencies(self):
        self.generate_ok()
        p = self.f.configure()
        self.assertEqual(0, p.returncode, output(p))
        self.f.assert_selection(self, "Debug", "Debug")
        self.f.assert_selection(self, "Release", "Release")

    def test_explicit_opposite_search_directory_rejected(self):
        f = self.f
        f.touch(f.deps / "debug/lib/third.lib")
        f.flags["avutil"] = ("-lthird", f'-L"{(f.deps / "lib").as_posix()}" -lthird')
        f.write_pc()
        self.assert_rejected(r"(?is)(release|opposite|configuration|search).*",)

    def test_explicit_manual_link_directory_preserved(self):
        f = self.f
        for cfg in ("", "debug"):
            f.touch(f.deps / cfg / "lib/manual-link/private.lib")
        f.flags["avutil"] = tuple(f'-L"{(f.deps / cfg / "lib/manual-link").as_posix()}" -lprivate' for cfg in ("", "debug"))
        f.write_pc()
        self.generate_ok()
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        for config in ("Debug", "Release"):
            prefix = f.sdk / ("debug" if config == "Debug" else "")
            expected = (prefix / "lib/manual-link/private.lib").resolve()
            for row in ("deps-avutil", "legacy"):
                libs = [Path(x).resolve() for x in f.rows(config)[row][0].split(";") if x.lower().endswith(".lib")]
                self.assertIn(expected, libs, f"{config}: {row} dropped explicit search location")

    def test_external_absolute_library_cannot_leak_into_sdk(self):
        f = self.f
        external = f.root / "external/alien.lib"
        f.touch(external)
        f.flags["avutil"] = ("-lthird", external.as_posix())
        f.write_pc()
        self.assert_rejected(r"(?is)(alien|absolute|external|relocat|dependency)")

    def test_missing_unknown_vendor_library_rejected(self):
        # Proposed strict producer contract: an absent library must not be
        # classified as a system library solely because its name is unknown.
        self.f.flags["avutil"] = ("-lno_fixture_vendor", "-lno_fixture_vendor_d")
        self.f.write_pc()
        self.assert_rejected(r"(?is)(vendor|dependency|library)")

    def test_module_versions_must_match(self):
        p = self.f.sdk / "debug/lib/pkgconfig/libavutil.pc"
        p.write_text(p.read_text().replace("56.1.0", "56.9.0"))
        self.assert_rejected(r"(?i)(version|avutil)")

    def test_missing_release_dependency_not_resolved_from_debug(self):
        f = self.f
        (f.deps / "lib/third.lib").unlink()
        f.touch(f.deps / "debug/lib/third.lib")
        self.assert_rejected(r"(?i)(third|opposite)")

    def test_sysroot_environment_cannot_change_library_selection(self):
        f = self.f
        f.flags["avutil"] = tuple(f'-L"{(f.deps / cfg / "lib").as_posix()}" -l{name}' for cfg, name in (("", "third"), ("debug", "thirdd")))
        f.write_pc()
        self.generate_ok(env=dict(os.environ, PKG_CONFIG_SYSROOT_DIR=str(f.root / "wrong-sysroot")))
        p = f.configure()
        self.assertEqual(0, p.returncode, output(p))
        f.assert_selection(self, "Release", "Release")
        f.assert_selection(self, "Debug", "Debug")
