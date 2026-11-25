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
# The original CLI packager deliberately used script-root absolute imports.
# Provide that same import environment for an apples-to-apples comparison.
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from scripts import package_release as original_packager
from scripts.ffport import _generate as original_port_generator


class OriginalPortRecipeContract(unittest.TestCase):
    def test_legacy_and_versioned_build_metadata_agree_for_all_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            for version in versions():
                if not has_source(version):
                    continue
                with self.subTest(version=version):
                    old_root = Path(temp) / "original"
                    new_root = Path(temp) / "versioned"
                    with contextlib.redirect_stdout(io.StringIO()):
                        original_port_generator(version, port_name="ffmpeg", output=str(old_root))
                    new_port = generate_port(version, destination=new_root)
                    def fields(path):
                        source = path.read_text(encoding="utf-8")
                        result = {}
                        for field, value in re.findall(
                                r"(?m)^set\\((FFMPEG_[A-Z0-9_]+)\\s+([^\\r\\n]+)\\)$", source):
                            result[field] = value.strip().strip('"')
                        return result
                    original = fields(old_root / "ffmpeg" / "portfile.cmake")
                    generated = fields(new_port / "portfile.cmake")
                    original.pop("FFMPEG_PORT_REVISION", None)
                    self.assertEqual(original, generated, "FFmpeg build CMake variables changed")
                    old_manifest = json.loads((old_root / "ffmpeg" / "vcpkg.json").read_text())
                    new_manifest = json.loads((new_port / "vcpkg.json").read_text())
                    self.assertEqual(old_manifest["dependencies"], new_manifest["dependencies"])
                    self.assertEqual(old_manifest["default-features"], new_manifest["default-features"])
                    for feature, legacy in old_manifest["features"].items():
                        # Self references remain the stable ffmpeg package.
                        adapted = json.loads(json.dumps(legacy))
                        # FFmpeg 3.4 OpenSSL must remain explicitly nonfree;
                        # its legacy implicit LGPL placement was corrected by
                        # the user's license gate, not by the CI migration.
                        if version == "3.4.14" and feature in ("lgpl", "nonfree"):
                            continue
                        self.assertEqual(adapted, new_manifest["features"][feature],
                                         f"Unexpected FFmpeg feature graph drift: {feature}")
                    shutil.rmtree(old_root)
                    shutil.rmtree(new_root)


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
        self.assertIn("FFMPEG_ADD_IMPORTED_TARGET(libavcodec avcodec)", original)
        self.assertIn("FFMPEG_ADD_IMPORTED_TARGET(libavutil avutil)", original)
        self.assertIn("FFMPEG_LINK_INTERNAL_DEPS", original)


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
                                     ("shared", "develop")):
                with self.subTest(linkage=linkage, variant=variant):
                    legacy = original_packager.collect_files(
                        package, linkage, variant_type=variant)
                    original_files = {Path(name).as_posix(): path.read_bytes()
                                      for path, name in legacy}
                    # v3 deliberately replaces raw copyright with a combined
                    # notice and moves native build metadata to the audit ZIP.
                    removed = {"CONTROL", "BUILD_INFO", "share/ffmpeg/copyright",
                               "share/ffmpeg/vcpkg_abi_info.txt", "share/ffmpeg/vcpkg.spdx.json"}
                    expected_payload = {name: data for name, data in original_files.items()
                                        if name not in removed}
                    actual = _files(package, linkage, develop=variant == "develop",
                                    port=port)
                    self.assertEqual(set(expected_payload), set(actual),
                                     f"{linkage}/{variant} must preserve executable/SDK layout")
                    for name, expected in expected_payload.items():
                        self.assertEqual(expected, actual[name].read_bytes())

    def test_no_static_sdk_and_shared_archive_keeps_original_cmake_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            port = "ffmpeg"
            package = self._fixture(Path(temporary), port)
            static = _files(package, "static", develop=False, port=port)
            self.assertEqual({"ffmpeg.exe"}, set(static))
            shared = _files(package, "shared", develop=False, port=port)
            self.assertIn("share/ffmpeg/FindFFmpeg.cmake", shared)
            self.assertIn("share/ffmpeg/vcpkg-cmake-wrapper.cmake", shared)
            self.assertNotIn("share/ffmpeg/vcpkg_abi_info.txt", shared)
            self.assertNotIn("share/ffmpeg/vcpkg.spdx.json", shared)
            self.assertNotIn("share/ffmpeg/copyright", shared)  # replaced by merged evidence
            self.assertNotIn("debug/lib/avcodec.lib", shared)


if __name__ == "__main__":
    unittest.main()
