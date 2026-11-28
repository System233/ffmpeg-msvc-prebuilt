"""Full generated Port control-flow contract, with external build test doubles."""
import os
import shutil
import shlex
import tempfile
import unittest
from pathlib import Path

from cmake_blackbox_fixture import ROOT, PKGCONF, TOOLS, run, output
from ffbuild.port import generate_port
from ffbuild.versions import versions, has_source, latest_per_family

VCPKG_ROOT = os.environ.get("FFBUILD_TEST_VCPKG_ROOT") or os.environ.get("VCPKG_ROOT")
HELPERS = Path(VCPKG_ROOT) / "scripts/cmake" if VCPKG_ROOT else None
HAVE_HELPERS = HELPERS and (HELPERS / "z_vcpkg_setup_pkgconfig_path.cmake").is_file()


def fixture_bash():
    if os.environ.get("FFBUILD_TEST_BASH"):
        return Path(os.environ["FFBUILD_TEST_BASH"])
    if os.name == "nt" and VCPKG_ROOT:
        for p in sorted((Path(VCPKG_ROOT) / "downloads/tools/msys2").glob("*/usr/bin/bash.exe")):
            if p.with_name("make.exe").is_file():
                return p
    if os.name != "nt" and shutil.which("bash") and shutil.which("make"):
        return Path(shutil.which("bash"))
    return None


BASH = fixture_bash()
NATIVE_LIB = os.environ.get("FFBUILD_TEST_LIB_EXE")


@unittest.skipUnless(TOOLS and HAVE_HELPERS, "Real vcpkg helpers and pkgconf required")
class PortContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.port = generate_port("4.4.8", destination=self.root / "ports")
        source = self.root / "source"
        source.mkdir()
        shutil.copyfile(ROOT / "tests/fixtures/port-configure.sh", source / "configure")
        for name in ("COPYING.LGPLv2.1", "COPYING.LGPLv3", "COPYING.GPLv2", "COPYING.GPLv3"):
            (source / name).write_text(name)
        for cfg, name in (("", "third_release"), ("debug", "third_debug")):
            pc = self.root / "installed" / cfg / "lib/pkgconfig/third.pc"
            pc.parent.mkdir(parents=True, exist_ok=True)
            pc.write_text(f"Name: third\nDescription: fixture {cfg}\nVersion: 1.0\nLibs: -l{name}\n")
        self.env = dict(os.environ)
        for key in ("PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR"):
            self.env.pop(key, None)

    def invoke(self, **extra):
        args = ["cmake", "-DFIXTURE=" + self.root.as_posix(),
                "-DTEST_PORT=" + self.port.as_posix(),
                "-DPKGCONF=" + Path(PKGCONF).as_posix(),
                "-DVCPKG_HELPERS=" + HELPERS.as_posix()]
        args.extend(f"-D{k}={v}" for k, v in extra.items())
        return run(args + ["-P", ROOT / "tests/fixtures/port-contract.cmake"], env=self.env)

    def test_native_default_lib_path_is_fallback_and_restored(self):
        system = self.root / "system-libs"
        system.mkdir()
        self.env["LIB"] = str(system)
        p = self.invoke()
        self.assertEqual(0, p.returncode, output(p))
        for cfg, subfolder in (("rel", "lib"), ("dbg", "debug/lib")):
            with self.subTest(config=cfg):
                actual = (self.root / f"{cfg}.lib-env").read_text().split(os.pathsep)
                self.assertEqual([self.root / "installed" / subfolder, system],
                                 [Path(item) for item in actual])
                self.assertNotIn("--extra-ldflags=-libpath:", (self.root / f"{cfg}.sh").read_text())
        self.assertEqual(str(system), (self.root / "restored-lib-env.txt").read_text())

    def test_requested_non_library_feature_has_actual_configure_evidence(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;openssl",
                        MISSING_FEATURE_MACRO="CONFIG_OPENSSL", MISSING_FEATURE_CONFIG="dbg")
        self.assertNotEqual(0, p.returncode, "Debug accepted disabled OpenSSL")
        self.assertRegex(output(p), r"(?is)(openssl|feature)")

    def test_multiple_explicit_switches_in_one_feature_are_all_validated(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;nvcodec",
                        MISSING_FEATURE_MACRO="CONFIG_NVENC", MISSING_FEATURE_CONFIG="rel")
        self.assertNotEqual(0, p.returncode, "Release accepted disabled NVENC within nvcodec")
        self.assertRegex(output(p), r"(?is)(nvenc|feature)")

    def test_legacy_have_sdl2_evidence_is_supported(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;sdl2",
                        FIXTURE_SDL2_HAVE_ONLY="ON")
        self.assertEqual(0, p.returncode, output(p))

    def test_disabled_config_sdl2_is_not_masked_by_have_sdl2(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;sdl2",
                        MISSING_FEATURE_MACRO="CONFIG_SDL2", MISSING_FEATURE_CONFIG="dbg")
        self.assertNotEqual(0, p.returncode, "HAVE_SDL2 masked disabled CONFIG_SDL2")
        self.assertRegex(output(p), r"(?is)(sdl2|feature)")

    def test_version3_license_request_rejects_version2_output(self):
        for profile, evidence in (("core;avcodec;avformat", "LGPL version 2.1 or later"),
                                  ("core;avcodec;avformat;license-gpl", "GPL version 2 or later")):
            with self.subTest(evidence=evidence):
                for name in ("sdk", "buildtrees"):
                    shutil.rmtree(self.root / name, ignore_errors=True)
                p = self.invoke(TEST_FEATURES=profile, FIXTURE_LICENSE=evidence)
                self.assertNotEqual(0, p.returncode, "Explicit version3 request accepted version2 evidence")
                self.assertRegex(output(p), r"(?is)license")

    def test_requested_nonfree_profile_and_copyright(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;license-nonfree;fdk-aac",
                        FIXTURE_LICENSE="nonfree and unredistributable")
        self.assertEqual(0, p.returncode, output(p))
        self.assertEqual("License: nonfree and unredistributable",
                         (self.root / "sdk/share/ffmpeg/copyright").read_text())

    def test_requested_nonfree_profile_rejects_redistributable_license(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;license-nonfree;fdk-aac")
        self.assertNotEqual(0, p.returncode, "Nonfree request accepted LGPL evidence")
        self.assertRegex(output(p), r"(?is)license")

    def test_supported_windows_triplets_use_static_crt(self):
        for arch in ("x86", "x64", "arm", "arm64"):
            with self.subTest(arch=arch):
                triplet = ROOT / "triplets" / f"{arch}-windows.cmake"
                text = triplet.read_text(encoding="utf-8")
                self.assertRegex(text, r"(?m)^set\(VCPKG_CRT_LINKAGE static\)$")
                self.assertRegex(text, r"(?m)^set\(VCPKG_LIBRARY_LINKAGE static\)$")

    def events(self):
        p = self.root / "events.txt"
        return p.read_text().splitlines() if p.exists() else []

    def test_complete_port_build_invocations_and_install_layout(self):
        p = self.invoke(STATIC_FIXTURE="ON")
        self.assertEqual(0, p.returncode, output(p))
        self.assertEqual(["source", "rel", "dbg"], self.events())
        for cfg, crt, lib, optimization in (
                ("rel", "-MT", "third_release", "--enable-optimizations"),
                ("dbg", "-MTd", "third_debug", "--disable-optimizations")):
            script = (self.root / f"{cfg}.sh").read_text()
            self.assertRegex(script, rf"--extra-cflags={crt}(?:\s|$)")
            self.assertIn(optimization, script)
            self.assertIn("--enable-static", script)
            self.assertIn("--disable-shared", script)
            self.assertIn("--enable-libtesseract", script)
            self.assertIn("--enable-libzmq", script)
            self.assertEqual("0|-l" + lib, (self.root / f"{cfg}.pkgconf").read_text())
            self.assertIn(crt, (self.root / f"{cfg}.rsp").read_text())
        sdk = self.root / "sdk"
        self.assertTrue((sdk / "include/libavutil/avutil.h").is_file())
        self.assertFalse((sdk / "debug/include").exists())
        self.assertTrue((sdk / "share/ffmpeg/FFmpegConfig.cmake").is_file())
        self.assertFalse((sdk / "bin").exists())
        self.assertFalse((sdk / "debug/bin").exists())

    def test_shared_feature_build_invocation(self):
        p = self.invoke()
        self.assertEqual(0, p.returncode, output(p))
        for cfg in ("rel", "dbg"):
            script = (self.root / f"{cfg}.sh").read_text()
            self.assertIn("--enable-shared", script)
            self.assertIn("--disable-static", script)
        for cfg in ("", "debug"):
            self.assertTrue((self.root / "sdk" / cfg / "bin/avutil-56.dll").is_file())

    def test_release_external_failure_stops_pipeline(self):
        p = self.invoke(FAIL_STAGE="rel")
        self.assertNotEqual(0, p.returncode, output(p))
        self.assertIn("Fixture external build failure: rel", output(p))
        self.assertEqual(["source", "rel"], self.events())
        self.assertFalse((self.root / "sdk/share/ffmpeg/FFmpegConfig.cmake").exists())

    def test_debug_external_failure_stops_pipeline(self):
        p = self.invoke(FAIL_STAGE="dbg")
        self.assertNotEqual(0, p.returncode, output(p))
        self.assertIn("Fixture external build failure: dbg", output(p))
        self.assertEqual(["source", "rel", "dbg"], self.events())
        self.assertFalse((self.root / "sdk/share/ffmpeg/FFmpegConfig.cmake").exists())

    def test_debug_configure_does_not_fall_back_to_external_release_pc(self):
        (self.root / "installed/debug/lib/pkgconfig/third.pc").unlink()
        self.env["PKG_CONFIG_PATH"] = str(self.root / "installed/lib/pkgconfig")
        p = self.invoke()
        self.assertNotEqual(0, p.returncode, "Debug configure accepted external Release dependency")
        self.assertRegex(output(p), r"(?is)(third|pkg.config|debug)")

    def test_single_config_rejected_before_external_build(self):
        p = self.invoke(VCPKG_BUILD_TYPE="release")
        self.assertNotEqual(0, p.returncode, output(p))
        self.assertNotIn("rel", self.events(), "Unsupported triplet ran expensive build before rejecting")

    def test_configuration_license_mismatch_rejected(self):
        p = self.invoke(WRONG_DEBUG_LICENSE="ON")
        self.assertNotEqual(0, p.returncode, "Debug GPL output accepted for LGPL Release package")
        self.assertRegex(output(p), r"(?is)license")

    def test_requested_feature_disabled_in_debug_rejected(self):
        p = self.invoke(MISSING_DEBUG_FEATURE="ON")
        self.assertNotEqual(0, p.returncode, "Debug output disabled requested Tesseract")
        self.assertRegex(output(p), r"(?is)(tesseract|feature)")

    def test_configure_pkgconfig_sysroot_does_not_change_search_paths(self):
        # The fixture records the actual pkgconf output during each build,
        # rather than inferring isolation from generated metadata.
        for cfg in ("", "debug"):
            folder = self.root / "installed" / cfg / "lib"
            pc = folder / "pkgconfig/third.pc"
            pc.write_text(pc.read_text().replace("Libs:", f'Libs: -L"{folder.as_posix()}"'))
        wrong = self.root / "alien-sysroot"
        self.env["PKG_CONFIG_SYSROOT_DIR"] = str(wrong)
        p = self.invoke()
        self.assertEqual(0, p.returncode, output(p))
        for cfg, folder in (("rel", "lib"), ("dbg", "debug/lib")):
            result = (self.root / f"{cfg}.pkgconf").read_text().replace(chr(92), "/")
            self.assertNotIn("alien-sysroot", result)
            self.assertIn((self.root / "installed" / folder).as_posix().lower(), result.lower())


    def test_alternate_dynamic_crt_triplet_flags_and_native_debug_optimizations(self):
        # Generic vcpkg triplet compatibility only. The project's four
        # supported Windows triplets above all select static CRT (/MT,/MTd).
        p = self.invoke(VCPKG_CRT_LINKAGE="dynamic", STATIC_FIXTURE="ON")
        self.assertEqual(0, p.returncode, output(p))
        for cfg, crt in (("rel", "-MD"), ("dbg", "-MDd")):
            script = (self.root / f"{cfg}.sh").read_text()
            flags = (self.root / f"{cfg}.rsp").read_text().split()
            self.assertRegex(script, rf"--extra-cflags={crt}(?:\s|$)")
            self.assertIn(crt, flags)
            self.assertNotIn("-MT", flags)
            self.assertNotIn("-MTd", flags)
        debug_flags = (self.root / "dbg.rsp").read_text().split()
        self.assertIn("-O2", debug_flags)
        self.assertNotIn("-Od", debug_flags)
        self.assertNotIn("-RTC1", debug_flags)

    def test_architecture_def_conversion_commands_and_cleanup(self):
        # Check all supported machine mappings at the external lib.exe boundary.
        # Only test_native_def_archives invokes the actual native librarian.
        for arch, machine, build_arch in (("x86", "X86", "x86"), ("x64", "X64", "x86_64"),
                                           ("arm", "ARM", "arm"), ("arm64", "ARM64", "arm64")):
            with self.subTest(arch=arch):
                for name in ("def-commands.txt", "tools.txt", "events.txt"):
                    (self.root / name).unlink(missing_ok=True)
                for name in ("sdk", "buildtrees"):
                    shutil.rmtree(self.root / name, ignore_errors=True)
                p = self.invoke(TEST_ARCH=arch, GENERATE_DEF="ON")
                self.assertEqual(0, p.returncode, output(p))
                commands = (self.root / "def-commands.txt").read_text().splitlines()
                self.assertEqual(6, len(commands))
                for cmd in commands:
                    self.assertIn("/MACHINE:" + machine, cmd.upper())
                    self.assertIn("/out:", cmd.lower())
                for cfg in ("", "debug"):
                    lib = self.root / "sdk" / cfg / "lib"
                    self.assertTrue((lib / "avutil.lib").is_file())
                    self.assertFalse(list(lib.glob("*.def")))
                    self.assertFalse(list(lib.glob("*.exp")))
                tools = (self.root / "tools.txt").read_text().splitlines()
                self.assertEqual(arch in ("x86", "x64"), "NASM" in tools)
                self.assertEqual(os.name == "nt" and arch in ("arm", "arm64"), "GASPREPROCESSOR" in tools)
                self.assertIn("build_ffmpeg " + build_arch, (self.root / "rel.sh").read_text())

    @unittest.skipUnless(NATIVE_LIB and Path(NATIVE_LIB).is_file(), "Set FFBUILD_TEST_LIB_EXE to native lib.exe")
    def test_native_def_archives(self):
        from ffbuild.native_platform import coff_archive_machines
        for arch, machine in (("x86", 0x14c), ("x64", 0x8664), ("arm", 0x1c4), ("arm64", 0xaa64)):
            with self.subTest(arch=arch):
                shutil.rmtree(self.root / "sdk", ignore_errors=True)
                shutil.rmtree(self.root / "buildtrees", ignore_errors=True)
                p = self.invoke(TEST_ARCH=arch, GENERATE_DEF="ON", NATIVE_LIB=Path(NATIVE_LIB).as_posix())
                self.assertEqual(0, p.returncode, output(p))
                for cfg in ("", "debug"):
                    for module in ("avutil", "avcodec", "avformat"):
                        archive = self.root / "sdk" / cfg / "lib" / (module + ".lib")
                        self.assertEqual({machine}, coff_archive_machines(archive))

    def test_cli_tool_install_and_debug_cleanup(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;ffmpeg;ffprobe",
                        FIXTURE_MODULES="avutil;avcodec;avformat", STATIC_FIXTURE="ON")
        self.assertEqual(0, p.returncode, output(p))
        sdk = self.root / "sdk"
        self.assertEqual({"ffmpeg.exe", "ffprobe.exe"}, {p.name for p in (sdk / "tools/ffmpeg").glob("*.exe")})
        for name in ("ffmpeg", "ffprobe"):
            self.assertEqual("fixture executable rel", (sdk / "tools/ffmpeg" / (name + ".exe")).read_text())
        self.assertFalse((sdk / "debug/bin").exists())
        self.assertIn("copy-pdbs", (self.root / "helpers.txt").read_text())

    def test_missing_debug_license_evidence_rejected(self):
        p = self.invoke(MISSING_DEBUG_LICENSE="ON")
        self.assertNotEqual(0, p.returncode, "Package accepted absent Debug license evidence")
        self.assertRegex(output(p), r"(?is)license")

    def test_requested_feature_disabled_in_release_rejected(self):
        p = self.invoke(MISSING_RELEASE_FEATURE="ON")
        self.assertNotEqual(0, p.returncode, "Release output disabled requested Tesseract")
        self.assertRegex(output(p), r"(?is)(tesseract|feature)")

    def test_native_package_rejects_missing_debug_dll(self):
        p = self.invoke(MISSING_DEBUG_DLL="ON")
        self.assertNotEqual(0, p.returncode, "Native Port accepted missing Debug DLL")
        self.assertRegex(output(p), r"(?is)(debug|avcodec|dll)")

    def test_native_static_package_rejects_missing_debug_archive(self):
        p = self.invoke(STATIC_FIXTURE="ON", MISSING_DEBUG_ARCHIVE="ON")
        self.assertNotEqual(0, p.returncode, "Native Port accepted missing Debug archive")
        self.assertRegex(output(p), r"(?is)(debug|avcodec|archive|library)")

    def test_pkgconfig_libdir_cannot_supply_missing_debug_dependency(self):
        (self.root / "installed/debug/lib/pkgconfig/third.pc").unlink()
        self.env["PKG_CONFIG_LIBDIR"] = str(self.root / "installed/lib/pkgconfig")
        p = self.invoke()
        self.assertNotEqual(0, p.returncode, "Debug configure accepted Release-only PKG_CONFIG_LIBDIR")
        self.assertRegex(output(p), r"(?is)(third|pkg.config|debug)")

    def test_requested_gpl_profile_and_copyright(self):
        p = self.invoke(TEST_FEATURES="core;avcodec;avformat;license-gpl;postproc",
                        FIXTURE_MODULES="avutil;avcodec;avformat;postproc",
                        FIXTURE_LICENSE="GPL version 3 or later")
        self.assertEqual(0, p.returncode, output(p))
        for cfg in ("rel", "dbg"):
            self.assertIn("--enable-gpl", (self.root / f"{cfg}.sh").read_text())
        self.assertEqual("COPYING.GPLv3", (self.root / "sdk/share/ffmpeg/copyright").read_text())

    def test_unrequested_gpl_license_rejected_in_both_configurations(self):
        p = self.invoke(FIXTURE_LICENSE="GPL version 3 or later")
        self.assertNotEqual(0, p.returncode, "LGPL feature set accepted GPL output")
        self.assertRegex(output(p), r"(?is)(license|gpl)")

    def test_version_family_port_entry_points(self):
        # Execute the complete generated Port for the latest supported source
        # of each family. Historical module sets are controlled inputs, not
        # claims about an upstream version's actual build.
        families = latest_per_family([v for v in versions() if has_source(v)])
        self.assertGreaterEqual(len(families), 7)
        cases = [(version, version, {}) for version in families]
        cases.append(("master", "9.1-12-gabcdef0", {
            "source_version": "9.1-12-gabcdef0", "ref": "a" * 40, "sha512": "b" * 128}))
        for version, identity, opts in cases:
            with self.subTest(version=version):
                self.port = generate_port(version, destination=self.root / "ports", **opts)
                for name in ("sdk", "buildtrees"):
                    shutil.rmtree(self.root / name, ignore_errors=True)
                (self.root / "path-events.txt").unlink(missing_ok=True)
                p = self.invoke(TEST_FEATURES="core;avcodec;avformat", FIXTURE_VERSION=identity)
                self.assertEqual(0, p.returncode, output(p))
                src = self.root / "family-consumer"
                src.mkdir(exist_ok=True)
                (src / "CMakeLists.txt").write_text(
                    'cmake_minimum_required(VERSION 3.21)\nproject(consumer LANGUAGES NONE)\n'
                    'set(WIN32 TRUE)\nset(CMAKE_FIND_LIBRARY_PREFIXES "")\n'
                    'set(CMAKE_FIND_LIBRARY_SUFFIXES ".lib")\n'
                    'find_package(FFmpeg CONFIG REQUIRED)\n'
                    f'if(NOT FFmpeg_VERSION STREQUAL "{identity}")\n'
                    'message(FATAL_ERROR "Incorrect package version")\nendif()\n'
                    'if(NOT TARGET FFmpeg::avformat)\nmessage(FATAL_ERROR "Missing target")\nendif()\n')
                p = run(["cmake", "-S", src, "-B", self.root / "family-build", "-G", "Ninja",
                         "-DCMAKE_PREFIX_PATH=" + (self.root / "sdk").as_posix()])
                self.assertEqual(0, p.returncode, output(p))
                if version == "master" or version.startswith(("8.1.", "9.")):
                    self.assertIn("manual-tools/ffmpeg-bin2c", (self.root / "path-events.txt").read_text())

    @unittest.skipUnless(BASH, "MSYS2/GNU make or native bash/make required")
    def test_real_generated_build_shell_invokes_configure_make_install(self):
        p = self.invoke(REAL_BASH=BASH.as_posix())
        self.assertEqual(0, p.returncode, output(p))
        for cfg, prefix in (("rel", self.root / "sdk"), ("dbg", self.root / "sdk/debug")):
            build = self.root / "buildtrees" / ("x64-windows-" + cfg)
            args = (build / "configure.args").read_text().splitlines()
            self.assertIn("--prefix=" + prefix.as_posix(), args)
            self.assertIn("--arch=x86_64", args)
            self.assertIn("--enable-shared", args)
            self.assertIn("--extra-cflags=" + ("-MT" if cfg == "rel" else "-MTd"), args)
            self.assertTrue((build / "make.marker").is_file())
            self.assertTrue((prefix / "fixture-install.marker").is_file())
            self.assertTrue((build / "configure.cflags").read_text().strip().startswith("@"))

    @unittest.skipUnless(BASH, "MSYS2/GNU make or native bash/make required")
    def test_real_shell_propagates_failure_at_each_stage(self):
        for stage in ("configure", "build", "install"):
            with self.subTest(stage=stage):
                shutil.rmtree(self.root / "sdk", ignore_errors=True)
                shutil.rmtree(self.root / "buildtrees", ignore_errors=True)
                (self.root / "events.txt").unlink(missing_ok=True)
                p = self.invoke(REAL_BASH=BASH.as_posix(), SHELL_FAIL_STAGE=stage)
                self.assertNotEqual(0, p.returncode, output(p))
                self.assertIn("fixture " + ("make" if stage == "build" else stage) + " failure", output(p))
                self.assertEqual(["source", "rel"], self.events())
                self.assertFalse((self.root / "sdk/share/ffmpeg/FFmpegConfig.cmake").exists())


    def test_actual_vcpkg_fixup_preserves_private_static_dependencies_and_relocation(self):
        for cfg, name in (("", "third_rel"), ("debug", "third_dbg")):
            library = self.root / "installed" / cfg / "lib" / (name + ".lib")
            library.touch()
        p = self.invoke(REAL_FIXUP="ON", STATIC_FIXTURE="ON")
        self.assertEqual(0, p.returncode, output(p))
        # Inspect the real helper's externally consumed pkgconf result, not
        # the implementation or generated CMake source.
        sdk = self.root / "sdk"
        for cfg, name in (("", "third_rel"), ("debug", "third_dbg")):
            env = dict(self.env, PKG_CONFIG_LIBDIR=str(sdk / cfg / "lib/pkgconfig"), PKG_CONFIG_PATH="")
            result = run([PKGCONF, "--libs", "libavformat"], env=env)
            self.assertEqual(0, result.returncode, output(result))
            self.assertIn("-l" + name, result.stdout)
            result = run([PKGCONF, "--variable=includedir", "libavformat"], env=env)
            self.assertEqual((sdk / "include").resolve(), Path(result.stdout.strip()).resolve())

    def test_actual_vcpkg_fixup_public_shared_graph_does_not_require_private_archives(self):
        p = self.invoke(REAL_FIXUP="ON")
        self.assertEqual(0, p.returncode, output(p))
        sdk = self.root / "sdk"
        moved = self.root / "moved shared sdk"
        sdk.rename(moved)
        for cfg in ("", "debug"):
            env = dict(self.env, PKG_CONFIG_LIBDIR=str(moved / cfg / "lib/pkgconfig"), PKG_CONFIG_PATH="")
            result = run([PKGCONF, "--libs", "--static", "libavformat"], env=env)
            self.assertEqual(0, result.returncode, output(result))
            self.assertIn("-lavutil", result.stdout)
            self.assertIn("-lavcodec", result.stdout)
            self.assertNotIn("-lthird_", result.stdout)
            result = run([PKGCONF, "--variable=libdir", "libavformat"], env=env)
            # pkgconf escapes spaces when returning a variable on its CLI.
            # Decode the single shell token before comparing the path.
            tokens = shlex.split(result.stdout.strip())
            self.assertEqual(1, len(tokens), result.stdout)
            self.assertEqual((moved / cfg / "lib").resolve(), Path(tokens[0]).resolve())

    def test_shared_private_pkgconfig_packages_are_not_required_after_install(self):
        self.prepare_private_package_graph()
        p = self.invoke(REAL_FIXUP="ON", PRIVATE_PACKAGE_REQUIRES="ON")
        self.assertEqual(0, p.returncode, output(p))
        sdk = self.root / "sdk"
        moved = self.root / "relocated shared sdk"
        sdk.rename(moved)
        shutil.rmtree(self.root / "installed")
        for cfg in ("", "debug"):
            env = dict(self.env, PKG_CONFIG_LIBDIR=str(moved / cfg / "lib/pkgconfig"),
                       PKG_CONFIG_PATH="")
            for flags in ([], ["--static"]):
                with self.subTest(config=cfg or "Release", flags=flags):
                    result = run([PKGCONF, *flags, "--cflags", "--libs", "libavformat"], env=env)
                    self.assertEqual(0, result.returncode, output(result))
                    self.assertNotRegex(result.stdout, r"-l(?:third|leaf)_")
                    self.assertNotIn("FIXTURE_PRIVATE_HEADER", result.stdout)
                    # Keep the internal graph and its static-query semantics.
                    if flags:
                        tokens = shlex.split(result.stdout)
                        for module in ("avformat", "avcodec", "avutil"):
                            self.assertIn("-l" + module, tokens)

    def prepare_private_package_graph(self):
        for cfg, suffix, third in (("", "release", "third_release"), ("debug", "debug", "third_debug")):
            folder = self.root / "installed" / cfg / "lib"
            leaf = "leaf_" + suffix
            (folder / (third + ".lib")).touch()
            (folder / (leaf + ".lib")).touch()
            # The installed vcpkg dependency metadata is already normalized.
            (folder / "pkgconfig/third.pc").write_text(
                "prefix=${pcfiledir}/../..\nName: third\nDescription: private third\nVersion: 1.0\n"
                f"Requires: leaf >= 1.0\nLibs: -L${{prefix}}/lib -l{third}\n"
                "Cflags: -DFIXTURE_PRIVATE_HEADER=1\n")
            (folder / "pkgconfig/leaf.pc").write_text(
                "prefix=${pcfiledir}/../..\nName: leaf\nDescription: private leaf\nVersion: 1.0\n"
                f"Libs: -L${{prefix}}/lib -l{leaf}\n")

    def test_static_private_pkgconfig_packages_survive_local_vcpkg_install(self):
        self.prepare_private_package_graph()
        # Keep the direct Libs.private flags distinct from the Requires graph.
        for cfg, name in (("", "third_rel"), ("debug", "third_dbg")):
            (self.root / "installed" / cfg / "lib" / (name + ".lib")).touch()
        p = self.invoke(REAL_FIXUP="ON", STATIC_FIXTURE="ON", PRIVATE_PACKAGE_REQUIRES="ON")
        self.assertEqual(0, p.returncode, output(p))
        # Simulate vcpkg's merge of the installed FFmpeg files into the same
        # triplet prefix as its dependencies, not a published static ZIP.
        prefix = self.root / "installed"
        shutil.copytree(self.root / "sdk", prefix, dirs_exist_ok=True)
        shutil.rmtree(self.root / "sdk")
        moved = self.root / "relocated static install"
        prefix.rename(moved)
        for cfg, suffix, direct in (("", "release", "third_rel"), ("debug", "debug", "third_dbg")):
            env = dict(self.env, PKG_CONFIG_LIBDIR=str(moved / cfg / "lib/pkgconfig"), PKG_CONFIG_PATH="")
            for flags in ([], ["--static"]):
                with self.subTest(config=cfg or "Release", flags=flags):
                    result = run([PKGCONF, *flags, "--cflags", "--libs", "libavformat"], env=env)
                    self.assertEqual(0, result.returncode, output(result))
                    tokens = shlex.split(result.stdout)
                    for library in ("avformat", "avcodec", "avutil", direct,
                                    "third_" + suffix, "leaf_" + suffix):
                        self.assertIn("-l" + library, tokens)
                    self.assertIn("-DFIXTURE_PRIVATE_HEADER=1", tokens)
                    opposite = "release" if suffix == "debug" else "debug"
                    self.assertNotIn("-lthird_" + opposite, tokens)
                    self.assertNotIn("-lleaf_" + opposite, tokens)
                    self.assertNotIn((self.root / "sdk").as_posix(), result.stdout)
