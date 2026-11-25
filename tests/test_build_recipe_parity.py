"""Byte-level build recipe parity against the original ffport CMake engine.

This checks *every* source-backed FFmpeg version and every source patch
without starting vcpkg, compiling dependencies or altering the main workspace.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from ffbuild.port import generate_port
from ffbuild.spec import read_spec, resolve_features
from ffbuild.versions import ROOT, versions
from scripts.ffport import merge as legacy_merge, yaml_utils as legacy_yaml
from scripts.ffport.templates import generate_features_cmake


BUILDER_FILES = (
    "ffmpeg-portfile.cmake",
    "build.sh.in",
    "FindFFmpeg.cmake.in",
    "vcpkg-cmake-wrapper.cmake",
)


class OriginalBuildRecipeParityTests(unittest.TestCase):
    def test_all_versions_preserve_original_builder_patches_and_features(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            checked = 0
            for version in versions():
                spec, _ = read_spec(version)
                # Compare inheritance against the original production ffport
                # resolver, not only the new ffbuild model. A silent drop or
                # reordering of ARM/version patches must fail this test.
                old_docs, _ = legacy_yaml.resolve_chain(version)
                old_spec = {}
                for doc in old_docs:
                    old_spec = legacy_merge.deep_merge(old_spec, doc)
                for key in ("patches", "build", "source", "dep_overrides", "features", "define"):
                    self.assertEqual(old_spec.get(key), spec.get(key), f"{version}: {key}")
                source = spec.get("source", {})
                if not source.get("sha512"):
                    continue
                with self.subTest(version=version):
                    port = generate_port(version, destination=output)
                    generated = (port / "portfile.cmake").read_text(encoding="utf-8")
                    manifest = json.loads((port / "vcpkg.json").read_text(encoding="utf-8"))
                    self.assertEqual("ffmpeg", manifest["name"])
                    self.assertEqual("ffmpeg-" + version.replace(".", "-"), port.name)
                    self.assertNotIn("port-version", manifest)
                    self.assertEqual(set(resolve_features(spec, version).definitions),
                                     set(manifest["features"]))
                    self.assertIn("builder/ffmpeg-portfile.cmake", generated)
                    self.assertIn(f'set(FFMPEG_VERSION "{version}")', generated)
                    self.assertIn(f'set(FFMPEG_SHA512 "{source["sha512"]}")', generated)
                    self.assertNotIn("FFBUILD_ACTIVE_FLAGS", generated)
                    self.assertEqual((port / "policy.cmake").read_bytes(),
                                     (port / "constraints.cmake").read_bytes())

                    # Compare each shipped builder and usage asset byte-for-byte.
                    for asset in BUILDER_FILES:
                        self.assertEqual(
                            hashlib.sha256((ROOT / "scripts" / "cmake" / asset).read_bytes()).digest(),
                            hashlib.sha256((port / "builder" / asset).read_bytes()).digest(),
                            asset)
                    self.assertEqual((ROOT / "scripts/cmake/usage.in").read_bytes(),
                                     (port / "usage").read_bytes())

                    # Match original patch content and order exactly. The numbered
                    # prefix only ensures collision-free filenames per version.
                    found = re.findall(r"\{CMAKE_CURRENT_LIST_DIR\}/(patches/[^\"\\\s]+)",
                                       generated)
                    self.assertEqual(len(spec.get("patches", [])), len(found))
                    for i, relative in enumerate(spec.get("patches", [])):
                        actual = port / found[i]
                        self.assertEqual(f"{i:03d}-{Path(relative).name}", actual.name)
                        self.assertEqual((ROOT / "patches" / relative).read_bytes(),
                                         actual.read_bytes(),
                                         f"{version} patch {i}: {relative}")

                    # Compare feature mapping against original ffport generation.
                    legacy = output / "legacy-feature-check"
                    legacy.mkdir(exist_ok=True)
                    generate_features_cmake(spec.get("features", {}), legacy)
                    expected = [
                        line.strip() for line in (legacy / "features.cmake").read_text(
                            encoding="utf-8").splitlines()
                        if line.startswith(("ffmpeg_feature(", "ffmpeg_feature_core("))
                    ]
                    actual = [
                        line.strip() for line in (port / "features.cmake").read_text(
                            encoding="utf-8").splitlines()
                        if line.startswith(("ffmpeg_feature(", "ffmpeg_feature_core("))
                    ]
                    self.assertEqual(expected, actual)
                    for key, value in spec.get("build", {}).get("cmake_defines", {}).items():
                        self.assertIn(f"set({key} ", generated)
                    checked += 1
            self.assertGreaterEqual(checked, 20, "Coverage unexpectedly lost version families")

    def test_original_arm_and_release_debug_behaviors_cannot_be_dropped(self):
        script = (ROOT / "scripts/cmake/ffmpeg-portfile.cmake").read_text(encoding="utf-8")
        shell = (ROOT / "scripts/cmake/build.sh.in").read_text(encoding="utf-8")
        for requirement in (
            'FFMPEG_NEED_BIN2C', 'FFMPEG_NEED_OPSTOOL',
            'vcpkg_find_acquire_program(GASPREPROCESSOR)',
            'VCPKG_TARGET_ARCHITECTURE STREQUAL "arm"',
            "VCPKG_DETECTED_MSVC", "VCPKG_CRT_LINKAGE",
            "--extra-ldflags=-libpath:", 'OPTIONS_DEBUG', 'OPTIONS_RELEASE',
            'z_vcpkg_setup_pkgconfig_path(CONFIG RELEASE)',
            'z_vcpkg_setup_pkgconfig_path(CONFIG DEBUG)',
            'ffmpeg_pkgconf_run', 'vcpkg_fixup_pkgconfig',
            'libconvert-', 'vcpkg_copy_tools',
            'FindFFmpeg.cmake.in', 'vcpkg-cmake-wrapper.cmake',
            'FFMPEG_PATCHES', '/constraints.cmake',
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, script)
        # Release and Debug .pc files can carry different vcpkg library
        # identities (notably ZeroMQ's -s vs -sgd static CRT archives).
        self.assertIn('function(ffmpeg_pkgconf_run out_var config)', script)
        self.assertIn('ffmpeg_pkgconf_run(libs_raw "${cfg}" --libs "${pkgmod}")', script)
        self.assertIn('"${CURRENT_PACKAGES_DIR}/${_ff_prefix}lib/pkgconfig', script)
        self.assertIn('${CURRENT_INSTALLED_DIR}/${_ff_prefix}lib/pkgconfig', script)
        self.assertNotIn('set(PKG_${pkgmod}_LIBS_DEBUG "${libs_raw}")', script)
        for requirement in ("OPTIONS_arm=", "OPTIONS_arm64=",
                            "build_ffmpeg()", "configure", "make"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, shell)

    def test_master_snapshot_retains_pinned_commit_and_all_patches(self):
        with tempfile.TemporaryDirectory() as temp:
            source = "a" * 40
            port = generate_port(
                "master", destination=Path(temp), source_version="n9.1-12-gabcdef0",
                ref=source, sha512="b" * 128)
            generated = (port / "portfile.cmake").read_text(encoding="utf-8")
            self.assertIn(f'set(FFMPEG_REF "{source}")', generated)
            self.assertIn('set(FFMPEG_SHA512 "' + ("b" * 128) + '")', generated)
            self.assertTrue((port / "builder/ffmpeg-portfile.cmake").is_file())


if __name__ == "__main__":
    unittest.main()
