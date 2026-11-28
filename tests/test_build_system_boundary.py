"""Guardrails against changing working FFmpeg build and Consumer semantics.

The old authored CMake builder, CMake consumer and release ZIP layout are
contracts. Multi-version support may use version-qualified directories, but the active
vcpkg package identity and authored Consumer must remain ffmpeg/ffmpeg-tester.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from ffbuild.package import _files
from ffbuild.port import generate_port
from ffbuild.versions import ROOT, has_source, versions
class OriginalConsumerContract(unittest.TestCase):
    def test_all_versions_use_original_consumer_unchanged(self):
        source = ROOT / "ports" / "ffmpeg-tester"
        source_files = sorted(p.relative_to(source) for p in source.rglob("*") if p.is_file())
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            for name in versions():
                if not has_source(name):
                    continue
                with self.subTest(version=name):
                    port = generate_port(name, destination=destination)
                    tester = destination / port.name.replace("ffmpeg-", "ffmpeg-tester-", 1)
                    self.assertFalse(tester.exists(), "Never generate a versioned Consumer")
                    self.assertEqual("ffmpeg", json.loads(
                        (port / "vcpkg.json").read_text(encoding="utf-8"))["name"])
                    self.assertTrue(all((source / relative).is_file() for relative in source_files))
                    tester_manifest = json.loads(
                        (source / "vcpkg.json").read_text(encoding="utf-8"))
                    self.assertEqual("ffmpeg", next(dep["name"] for dep in tester_manifest["dependencies"]
                                     if isinstance(dep, dict) and dep["name"] == "ffmpeg"))
                    shutil.rmtree(port)

    def test_original_installed_ffmpeg_cmake_module_is_independent_of_pkgconf(self):
        # Regression: cross-architecture Tester replaced this installed module
        # with find_package(PkgConfig REQUIRED), and failed to find host pkgconf.
        original = (ROOT / "scripts/cmake/FindFFmpeg.cmake.in").read_text(
            encoding="utf-8")
        self.assertNotIn("find_package(PkgConfig", original)
        self.assertIn('set(FFMPEG_MODULES "@FFMPEG_MODULES@")', original)
        self.assertIn('add_library(FFmpeg::${_mod} SHARED IMPORTED GLOBAL)', original)
        self.assertIn('target_link_libraries(FFmpeg::${_mod} INTERFACE FFmpeg::${_dep})', original)


class OriginalArchiveContract(unittest.TestCase):
    def _fixture(self, root: Path, port: str) -> Path:
        package = root / "package"
        for subdir, name in (
            ("tools/ffmpeg", "ffmpeg.exe"),
            (f"tools/{port}", "ffmpeg.exe"),
            ("bin", "avcodec-61.dll"),
            ("bin", "avcodec.pdb"),
            ("lib", "avcodec.lib"),
            ("include/libavcodec", "avcodec.h"),
            ("debug/bin", "avcodec-61.dll"),
            ("debug/bin", "avcodec.pdb"),
            ("debug/lib", "avcodec.lib"),
            ("share/ffmpeg", "FindFFmpeg.cmake"),
            ("share/ffmpeg", "FFmpegConfig.cmake"),
            ("share/ffmpeg", "FFmpegConfigVersion.cmake"),
            ("share/ffmpeg", "vcpkg-cmake-wrapper.cmake"),
            ("share/ffmpeg", "usage"),
            ("share/ffmpeg", "copyright"),
            (f"share/{port}", "copyright"),
            (f"share/{port}", "vcpkg_abi_info.txt"),
            (f"share/{port}", "vcpkg.spdx.json"),
        ):
            path = package / subdir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"original artifact: {subdir}/{name}".encode())
        for name in ("BUILD_INFO", "CONTROL"):
            (package / name).write_bytes(name.encode())
        return package

    def test_static_and_shared_payload_matches_original_without_internal_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            port = "ffmpeg"
            package = self._fixture(Path(temporary), port)
            for linkage, variant in (("static", "binary"),
                                     ("shared", "binary"),
                                     ("shared", "debug")):
                with self.subTest(linkage=linkage, variant=variant):
                    names = {"ffmpeg.exe"} if linkage == "static" else {
                        "bin/ffmpeg.exe", "bin/avcodec-61.dll", "lib/avcodec.lib",
                        "include/libavcodec/avcodec.h", "share/ffmpeg/FindFFmpeg.cmake",
                        "share/ffmpeg/FFmpegConfig.cmake", "share/ffmpeg/FFmpegConfigVersion.cmake",
                        "share/ffmpeg/vcpkg-cmake-wrapper.cmake", "share/ffmpeg/usage"}
                    if variant == "debug":
                        names = {"bin/avcodec.pdb", "debug/bin/avcodec-61.dll",
                                  "debug/bin/avcodec.pdb", "debug/lib/avcodec.lib"}
                    expected_payload = {name: (package / ("tools/ffmpeg/ffmpeg.exe" if name in
                                        ("ffmpeg.exe", "bin/ffmpeg.exe") else name)).read_bytes()
                                        for name in names}
                    actual = _files(package, linkage, kind=variant,
                                    port=port)
                    self.assertEqual(set(expected_payload), set(actual),
                                     f"{linkage}/{variant} must preserve executable/SDK layout")
                    for name, expected in expected_payload.items():
                        self.assertEqual(expected, actual[name].read_bytes())

    def test_no_static_sdk_and_shared_archive_keeps_original_cmake_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            port = "ffmpeg"
            package = self._fixture(Path(temporary), port)
            static = _files(package, "static", kind="binary", port=port)
            self.assertEqual({"ffmpeg.exe"}, set(static))
            shared = _files(package, "shared", kind="binary", port=port)
            self.assertIn("share/ffmpeg/FindFFmpeg.cmake", shared)
            self.assertIn("share/ffmpeg/FFmpegConfig.cmake", shared)
            self.assertIn("share/ffmpeg/FFmpegConfigVersion.cmake", shared)
            self.assertIn("share/ffmpeg/vcpkg-cmake-wrapper.cmake", shared)
            self.assertNotIn("share/ffmpeg/vcpkg_abi_info.txt", shared)
            self.assertNotIn("share/ffmpeg/vcpkg.spdx.json", shared)
            self.assertNotIn("share/ffmpeg/copyright", shared)  # replaced by merged evidence
            self.assertNotIn("debug/lib/avcodec.lib", shared)


if __name__ == "__main__":
    unittest.main()
