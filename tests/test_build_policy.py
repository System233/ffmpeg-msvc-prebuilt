"""Offline policy, pinned build-hash and native vcpkg adapter regression."""

from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ffbuild.fingerprint import ROOT, _add_file, recipe_fingerprint, variant_fingerprint
from ffbuild.planner import plan
from ffbuild.state import PublishedState
from ffbuild.versions import generate, validate_variant
from ffvcpkg import command
from ffbuild.spec import FeatureSet, _platform_applies
from ffbuild.port import _policy_script
from ffbuild.package import package_job
from ffbuild.targets import Target, compile_target
from ffbuild.versions import config


class PolicyTests(unittest.TestCase):
    def test_packager_refuses_wrong_license_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            (package / "CONTROL").write_text("Version: 3.4.14\n\nFeature: license-nonfree\n",encoding="utf-8")
            (package / "BUILD_INFO").write_text("LibraryLinkage: dynamic\n", encoding="utf-8")
            job = {"version":"3.4.14-h"+"a"*12, "revision":0, "triplet":"x64-windows",
                   "yaml":"3.4.14", "build_hash":"a"*64,"variant_hash":"b"*64,
                   "license":"lgpl", "linkage":"shared"}
            with self.assertRaisesRegex(ValueError, "license mismatch"):
                package_job(package, job, package)

    def test_legacy_openssl_never_implicitly_raises_license(self):
        from ffbuild.native_abi import build_requests
        from ffbuild.targets import load_targets
        from ffbuild.versions import config
        from ffbuild.spec import resolve_features
        self.assertEqual([], validate_variant("3.4.14", "lgpl"))
        self.assertEqual([], validate_variant("3.4.14", "gpl"))
        self.assertEqual([], validate_variant("3.4.14", "nonfree"))
        self.assertEqual([], validate_variant("8.1.3", "lgpl"))
        graph = resolve_features(config("3.4.14"), "3.4.14")
        self.assertNotIn("openssl", graph.closure(["all-lgpl"]))
        self.assertNotIn("openssl", graph.closure(["all-gpl"]))
        self.assertIn("openssl", graph.closure(["all-nonfree"]))
        scheduled, blocked = build_requests(version="3.4.14", targets=load_targets())
        self.assertEqual((16, 0), (len(scheduled), len(blocked)))

    def test_requires_and_conflicts_do_not_add_dependencies(self):
        registry = {"codec": {"requires": ["feature:base", "package:opus"],
                              "conflicts": ["feature:other", "package:x264"]},
                    "base": {}, "other": {}}
        graph = FeatureSet(registry, (), {"codec":("opus",)}, {}, ())
        self.assertEqual([], graph.policy_errors({"codec", "base"}))
        self.assertIn("requires feature:base", " ".join(
            graph.policy_errors({"codec"})))
        conflict_graph = FeatureSet(registry, (), {"codec":("opus","x264")}, {}, ())
        self.assertIn("conflicts package:x264", " ".join(
            conflict_graph.policy_errors({"codec", "base"})))

    @unittest.skipUnless(shutil.which("cmake"), "CMake is needed for native-port guard tests")
    def test_generated_port_enforces_license_without_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = generate("3.4.14", output=Path(tmp))
            constraints = port / "policy.cmake"
            self.assertTrue(constraints.is_file())
            script = Path(tmp) / "check.cmake"
            for flags, allowed in (("all-lgpl;lgpl;openssl", False),
                                   ("all-nonfree;openssl;license-gpl;license-nonfree", True)):
                script.write_text(
                    f'set(FEATURES "{flags}")\ninclude("{constraints.as_posix()}")\n',
                    encoding="utf-8",
                )
                result = subprocess.run(["cmake", "-P", str(script)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, allowed, result.stderr)
                if not allowed:
                    self.assertIn("requires explicit nonfree", result.stderr)

    def test_generated_arbitrary_feature_package_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = FeatureSet(
                {"core": {"requires": ["feature:base", "package:opus"],
                          "conflicts": ["feature:other"]},
                 "base": {}, "other": {}}, (), {"core": ("opus",)}, {}, ())
            cmake = _policy_script(graph)
            self.assertIn('NOT "base" IN_LIST FEATURES', cmake)
            self.assertIn('NOT "opus" IN_LIST _FFBUILD_REQUIRED_PACKAGES', cmake)
            self.assertIn('"other" IN_LIST FEATURES', cmake)


class HashAndStateTests(unittest.TestCase):
    def test_text_hash_is_cross_platform_stable(self):
        # Fresh CI worktrees do not contain ignored build directories.
        (ROOT / "_work").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "_work") as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_bytes(b"first\r\nsecond\r\n")
            windows = hashlib.sha256()
            _add_file(windows, path)
            path.write_bytes(b"first\nsecond\n")
            linux = hashlib.sha256()
            _add_file(linux, path)
            self.assertEqual(windows.hexdigest(), linux.hexdigest())

    def test_version_hash_and_variant_hash_are_deterministic(self):
        digest = recipe_fingerprint("8.1.3")
        self.assertEqual(64, len(digest))
        self.assertEqual(digest, recipe_fingerprint("8.1.3"))
        lgpl = compile_target(config("8.1.3"), "8.1.3",
                              Target("ffmpeg[all-lgpl,static]", "x64-windows", ("all-lgpl", "static")))
        base = compile_target(config("8.1.3"), "8.1.3",
                              Target("ffmpeg[base,static]", "x64-windows", ("base", "static")))
        self.assertEqual((lgpl["license"], lgpl["linkage"]),
                         (base["license"], base["linkage"]))
        self.assertNotEqual(variant_fingerprint(digest, "x64-windows", lgpl["feature_hash"]),
                            variant_fingerprint(digest, "x64-windows", base["feature_hash"]))

    def test_published_hash_dedupes_across_legacy_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "8.x" / "8.1.3-r3" / "variants" / "x64-windows-static-lgpl.yaml"
            path.parent.mkdir(parents=True)
            path.write_text(yaml.safe_dump({"build_hash": "a" * 64,
                                             "assets": {"binary": {"file": "archive.zip"}}}),
                            encoding="utf-8")
            state = PublishedState(directory=root)
            self.assertTrue(state.variant_exists("8.1.3-habc", 0, "x64-windows",
                                                 "lgpl", "static", "a" * 64))
            self.assertFalse(state.variant_exists("8.1.3-hdef", 0, "x64-windows",
                                                  "lgpl", "static", "b" * 64))
            self.assertFalse(state.target_exists("8.1.3-habc", 0, "x64-windows",
                                                 "c" * 64, "a" * 64, "b" * 64),
                             "Legacy records without Feature identities must not deduplicate new builds")

    def test_master_and_stable_builds_do_not_share_source(self):
        with mock.patch("ffbuild.planner.changed_paths", return_value={"ffmpeg/base.yaml"}):
            with mock.patch("ffbuild.master.master_metadata", return_value={
                "ref": "n9.1-12-gabcdef0", "sha512": "a" * 128,
                "commit": "a" * 40,
            }):
                result = plan(mode="changed", base="x", head="y", include_master=True,
                              force=True, targets=(Target("ffmpeg[all-lgpl,static]", "x64-windows",
                                                          ("all-lgpl", "static")),))
        jobs = result["jobs"]
        self.assertTrue(any(j["yaml"] == "master" for j in jobs))
        for job in jobs:
            if job["yaml"] != "master":
                self.assertEqual("", job["ref"])
                self.assertEqual("", job["sha512"])
                self.assertEqual("", job["source_ref"])
            else:
                self.assertEqual("a" * 40, job["source_ref"])

    def test_master_port_uses_pinned_full_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = generate("master", source_version="n9.1-12-gabcdef0",
                            ref="a" * 40, sha512="a" * 128, output=Path(tmp))
            cmake = (port / "portfile.cmake").read_text(encoding="utf-8")
            # The original FFmpeg CMake builder consumes FFMPEG_REF, not
            # the temporary FFBUILD_SOURCE_REF used by the discarded recipe.
            self.assertIn('set(FFMPEG_REF "' + "a" * 40 + '")', cmake)
            self.assertEqual("9.1-12-gabcdef0",
                             json.loads((port / "vcpkg.json").read_text())["version"])
            self.assertNotIn("VCPKG_USE_HEAD_VERSION", cmake)


class VcpkgWrapperTests(unittest.TestCase):
    def test_native_vcpkg_command_is_not_interpreted(self):
        fake = Path("fake-vcpkg.exe")
        # An empty checkout has no generated ports yet. Materialize the
        # expected overlay in a temporary root instead of assuming a prior
        # test already ran port generation.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = root / "_work" / "ffbuild" / "generated-ports"
            selected = generated / "ffmpeg-9-1"
            selected.mkdir(parents=True)
            (selected / "vcpkg.json").write_text('{"name":"ffmpeg","version":"9.1"}')
            with mock.patch("ffvcpkg.ROOT", root):
                args = command(["install", "ffmpeg[all-lgpl,static]", "--triplet=x64-windows",
                                f"--overlay-ports={selected}", f"--overlay-ports={root / 'ports'}"],
                               binary=fake)
        self.assertEqual(str(fake), args[0])
        self.assertEqual("ffmpeg[all-lgpl,static]", args[2])
        self.assertIn("--triplet=x64-windows", args)
        self.assertEqual(2, sum(a.startswith("--overlay-ports=") for a in args))
        self.assertEqual(1, sum(a.startswith("--overlay-triplets=") for a in args))

    def test_multiple_version_overlay_parent_is_never_implicitly_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "_work" / "ffbuild" / "generated-ports"
            parent.mkdir(parents=True)
            selected = parent / "ffmpeg-9-1"
            selected.mkdir()
            (selected / "vcpkg.json").write_text('{"name":"ffmpeg","version":"9.1"}')
            with mock.patch("ffvcpkg.ROOT", root):
                with self.assertRaisesRegex(ValueError, "single-version"):
                    command(["install", "ffmpeg[base]"], binary=Path("vcpkg.exe"))
                with self.assertRaisesRegex(ValueError, "generated-ports parent"):
                    command(["install", "ffmpeg[base]",
                             f"--overlay-ports={parent}"], binary=Path("vcpkg.exe"))
                with self.assertRaisesRegex(ValueError, "single-version"):
                    command(["install", "ffmpeg-tester",
                             f"--overlay-ports={root / 'ports'}"], binary=Path("vcpkg.exe"))
                args = command(["install", "ffmpeg-tester",
                                f"--overlay-ports={selected}"], binary=Path("vcpkg.exe"))
                self.assertIn(f"--overlay-ports={selected}", args)

    def test_generic_dependency_port_does_not_load_multi_version_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_work" / "ffbuild" / "generated-ports").mkdir(parents=True)
            with mock.patch("ffvcpkg.ROOT", root):
                args = command(["install", "zlib"], binary=Path("vcpkg.exe"))
                self.assertIn(f"--overlay-ports={root / 'ports'}", args)
                self.assertFalse(any("generated-ports" in arg for arg in args))

    def test_explicit_overlays_are_preserved(self):
        args = command(["install", "zlib", "--overlay-ports=custom",
                        "--overlay-triplets=other"], binary=Path("vcpkg.exe"))
        self.assertIn("--overlay-ports=custom", args)
        self.assertIn("--overlay-triplets=other", args)
        self.assertEqual(5, len(args))

    def test_non_build_commands_pass_through_unchanged(self):
        self.assertEqual(["vcpkg.exe", "version"],
                         command(["version"], binary=Path("vcpkg.exe")))


class NativePlatformFeatureTests(unittest.TestCase):
    def test_vcpkg_architecture_predicates(self):
        self.assertFalse(_platform_applies("!x86 & !arm32 & !uwp", "x86-windows"))
        self.assertFalse(_platform_applies("!x86 & !arm32 & !uwp", "arm-windows"))
        self.assertTrue(_platform_applies("!x86 & !arm32 & !uwp", "arm64-windows"))
        self.assertFalse(_platform_applies("!x86 & !arm", "arm64-windows"))
        self.assertTrue(_platform_applies("!x86 & !arm", "x64-windows"))
        self.assertFalse(_platform_applies("!uwp & !arm & !arm64", "arm64-windows"))
        self.assertTrue(_platform_applies("!uwp & !arm & !arm64", "x64-windows"))
        self.assertTrue(_platform_applies("(x64 | arm64) & !uwp", "arm64-windows"))
        self.assertFalse(_platform_applies("(x64 | arm64) & !uwp", "x86-windows"))
        with self.assertRaisesRegex(ValueError, "Unknown vcpkg platform"):
            _platform_applies("!unsupported", "x64-windows")

    def test_target_closure_matches_native_vcpkg_platform_conditions(self):
        samples = (
            ("6.1.6", "x86-windows", "ffmpeg[all-gpl]", ("svtav1",)),
            ("9.1", "arm64-windows", "ffmpeg[all-lgpl,static]", ("nvcodec", "vvenc")),
        )
        for version, triplet, package, disabled in samples:
            with self.subTest(version=version, triplet=triplet):
                roots = tuple(package.split("[", 1)[1].removesuffix("]").split(","))
                result = compile_target(config(version), version,
                                        Target(package, triplet, roots))
                for feature in disabled:
                    self.assertNotIn(feature, result["features"])
                self.assertIn("base", result["features"])
                self.assertEqual(package, result["package"])

    def test_build_target_rejects_old_versioned_package_identity(self):
        from ffbuild.targets import parse_package
        with self.assertRaisesRegex(ValueError, "Expected an FFmpeg"):
            parse_package("ffmpeg-9-1[base]")


if __name__ == "__main__":
    unittest.main()
