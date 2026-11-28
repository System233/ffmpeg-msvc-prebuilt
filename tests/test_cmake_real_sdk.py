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
        from ffbuild.sdk_validation import tester_targets
        expected = {name + ".exe" for name in tester_targets(modules)}
        build = self.root / "native-tester"
        self.checked(["cmake", "-S", ROOT / "ports/ffmpeg-tester", "-B", build,
                      *self.generator, "-DCMAKE_PREFIX_PATH=" + self.sdk.as_posix(),
                      "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>"])
        for config, folder in (("Release", ""), ("Debug", "debug")):
            with self.subTest(config=config):
                self.checked(["cmake", "--build", build, "--config", config, "--parallel", "4"])
                executables = sorted((build / config).rglob("check-*.exe"))
                self.assertEqual(expected, {p.name for p in executables})
                for exe in executables:
                    self.checked([exe], env=self.runtime_env(self.sdk / folder), cwd=exe.parent)
                print(f"Real FFmpeg {self.version} {config}: {len(executables)} Native Tester executions", flush=True)

    def test_real_shared_sdk_accepts_all_consumer_crts(self):
        from ffbuild.sdk_validation import validate_installed
        report = validate_installed(self.sdk, triplet=TRIPLET, linkage="shared",
                                    generator=self.generator[1], pkgconf=Path(PKGCONF),
                                    modes=("CONFIG",))
        self.assertEqual(8, sum(".check-crt-" in row["id"] for row in report))

    def test_real_pkgconfig_consumer_links_and_runs(self):
        from ffbuild.sdk_validation import validate_installed
        moved = self.root / "real sdk with spaces"
        self.sdk.rename(moved)
        self.sdk = moved
        report = validate_installed(self.sdk, triplet=TRIPLET, linkage="shared",
                                    generator=self.generator[1], pkgconf=Path(PKGCONF),
                                    modes=("PKGCONFIG",))
        self.assertTrue(report)
