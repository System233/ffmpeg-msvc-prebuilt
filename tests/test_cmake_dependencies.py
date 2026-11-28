"""Run the production Port's dependency pipeline with real pkgconf fixtures."""
import os
import shutil
from cmake_blackbox_fixture import run as run_command
import tempfile
import unittest
from pathlib import Path

from ffbuild.versions import ROOT

PKGCONF = os.environ.get("FFBUILD_TEST_PKGCONF") or shutil.which("pkgconf")


@unittest.skipUnless(shutil.which("cmake") and PKGCONF, "CMake and pkgconf required")
class DependencyMetadataTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.package = self.root / "package"
        self.installed = self.root / "installed"
        self.output = self.root / "out"
        for cfg in ("", "debug"):
            (self.package / cfg / "lib/pkgconfig").mkdir(parents=True)
            (self.installed / cfg / "lib/pkgconfig").mkdir(parents=True)
        self.module("avutil", release="-lthird -lws2_32", debug="-lthirdd -lws2_32")
        self.module("avcodec", requires="libavutil", release="-lcodecdep", debug="-lcodecdep")
        self.module("postproc", requires="libavutil")
        for cfg, names in (("", ["third.lib", "codecdep.lib"]), ("debug", ["thirdd.lib", "codecdep.lib"])):
            for name in names:
                (self.installed / cfg / "lib" / name).touch()

    def module(self, name, requires="", release="", debug="", private=False):
        header = self.package / "include" / f"lib{name}" / ("postprocess.h" if name == "postproc" else f"{name}.h")
        header.parent.mkdir(parents=True, exist_ok=True)
        header.touch()
        for cfg, flags in (("", release), ("debug", debug)):
            field = "Requires.private" if private else "Requires"
            text = f"Name: lib{name}\nDescription: FFmpeg fixture\nVersion: 56.1.0\n{field}: {requires}\nLibs: -l{name} {flags}\n"
            (self.package / cfg / "lib/pkgconfig" / f"lib{name}.pc").write_text(text)

    def run_pipeline(self, success=True, reason=None, env=None, **kwargs):
        args = ["cmake", f"-DCURRENT_PACKAGES_DIR={self.package.as_posix()}",
                f"-DCURRENT_INSTALLED_DIR={self.installed.as_posix()}",
                f"-DPKGCONF={Path(PKGCONF).as_posix()}", f"-DOUTPUT_DIR={self.output.as_posix()}"]
        args += [f"-D{k}={v}" for k, v in kwargs.items()]
        result = run_command(args + ["-P", str(ROOT / "tests/test_ffmpeg_deps.cmake")],
                                env=env)
        text = result.stdout + result.stderr
        self.assertEqual(success, result.returncode == 0, text)
        if reason:
            self.assertIn(reason, text)
        if success:
            return (self.output / "FindFFmpeg.cmake").read_text()

    def test_module_graph_and_configuration_specific_metadata(self):
        text = self.run_pipeline()
        self.assertIn("set(_ff_avutil_RELEASE [==[vcpkg-lib:third.lib;ws2_32]==])", text)
        self.assertIn("set(_ff_avutil_DEBUG [==[vcpkg-lib:thirdd.lib;ws2_32]==])", text)
        self.assertIn("set(_ff_avcodec_RELEASE [==[vcpkg-lib:codecdep.lib]==])", text)
        self.assertIn("set(_ff_avcodec_DEPS [==[avutil]==])", text)
        self.assertIn("set(_ff_postproc_DEPS [==[avutil]==])", text)
        self.assertEqual("avutil;avcodec;postproc", (self.output / "modules.txt").read_text())

    def test_shared_private_module_graph_preserved(self):
        self.module("avutil")
        self.module("avcodec", requires="libavutil", private=True)
        self.module("postproc", requires="libavutil", private=True)
        text = self.run_pipeline(VCPKG_LIBRARY_LINKAGE="dynamic")
        self.assertIn("set(_ff_avcodec_DEPS [==[avutil]==])", text)

    def test_debug_module_missing(self):
        (self.package / "debug/lib/pkgconfig/libpostproc.pc").unlink()
        self.run_pipeline(False, "Missing Debug pkg-config module: libpostproc")

    def test_requested_module_missing(self):
        self.run_pipeline(False, "Requested FFmpeg module missing", FFMPEG_PKGCONFIG_MODULES="libavutil;libavfilter")

    def test_opposite_configuration_dependency_rejected(self):
        self.module("avutil", release="-lthird", debug="-lthird")
        self.run_pipeline(False, "exists only in the opposite configuration")

    def test_cycle_rejected(self):
        self.module("avutil", requires="libavcodec")
        self.run_pipeline(False, "Circular dependency")

    def test_graph_mismatch(self):
        path = self.package / "debug/lib/pkgconfig/libavcodec.pc"
        path.write_text(path.read_text().replace("Requires: libavutil", "Requires:"))
        self.run_pipeline(False, "internal module graph differs")

    def test_host_pkgconfig_cannot_supply_missing_target_package(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "hostonly.pc").write_text("Name: hostonly\nDescription: Wrong host package\nVersion: 1.0\nLibs: -lhostonly\n")
        self.module("avcodec", requires="libavutil hostonly")
        env = dict(os.environ, PKG_CONFIG_LIBDIR=str(outside), PKG_CONFIG_PATH=str(outside))
        self.run_pipeline(False, "hostonly", env=env)

    def test_unrepresented_internal_library_rejected(self):
        self.module("avcodec", release="-lavutil", debug="-lavutil")
        self.run_pipeline(False, "absent from its dependency graph")

    def test_vcpkg_recorded_debug_file_removed(self):
        record = self.root / "vcpkg/info/third_1_installed.list"
        record.parent.mkdir(parents=True)
        record.write_text("installed/lib/third.lib\ninstalled/debug/lib/thirdd.lib\n")
        (self.installed / "debug/lib/thirdd.lib").unlink()
        self.run_pipeline(False, "recorded by vcpkg but its archive is missing")

    def test_historical_tesseract_and_zeromq_debug_names(self):
        release = ("tesseract55", "libzmq-mt-s-4_3_5")
        debug = ("tesseract55d", "libzmq-mt-sgd-4_3_5")
        self.module("avutil", release=" ".join("-l" + lib for lib in release),
                    debug=" ".join("-l" + lib for lib in debug))
        for cfg, names in (("", release), ("debug", debug)):
            for name in names:
                (self.installed / cfg / "lib" / (name + ".lib")).touch()
        text = self.run_pipeline()
        for cfg, names in (("RELEASE", release), ("DEBUG", debug)):
            encoded = ";".join("vcpkg-lib:" + name + ".lib" for name in names)
            self.assertIn(f"set(_ff_avutil_{cfg} [==[{encoded}]==])", text)
