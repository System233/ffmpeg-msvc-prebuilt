"""Regression checks for the original CI dependency prebuild architecture.

All tests are offline. In particular, they never invoke a compiler or vcpkg.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ffbuild.port import generate_seed_port
from ffbuild.seed import prepare_seed, seed_profiles
from ffbuild.versions import ROOT


class SharedDependencySeedTests(unittest.TestCase):
    def test_conflicting_dependencies_and_platform_restrictions(self):
        with tempfile.TemporaryDirectory() as temporary:
            overlay = Path(temporary)
            seed = generate_seed_port(overlay)
            manifest = json.loads((seed / "vcpkg.json").read_text(encoding="utf-8"))
            self.assertEqual("ffmpeg-deps", manifest["name"])
            self.assertEqual(("all", "ffnvcodec", "ffnvcodec-11", "libvpl", "mfx-dispatch"),
                             seed_profiles(overlay))
            normal = {entry["name"]: entry for entry in
                      manifest["features"]["all"]["dependencies"]}
            self.assertNotIn("ffnvcodec", normal)
            self.assertNotIn("ffnvcodec-11", normal)
            self.assertNotIn("libvpl", normal)
            self.assertNotIn("mfx-dispatch", normal)
            self.assertEqual("!arm", normal["lensfun"]["platform"])
            self.assertEqual("!uwp & !xbox", normal["libbluray"]["platform"])
            self.assertEqual("!x86 & !arm32 & !uwp", normal["svt-av1"]["platform"])
            self.assertTrue(normal["ffmpeg-bin2c"]["host"])
            self.assertTrue(normal["vcpkg-cmake-get-vars"]["host"])
            self.assertTrue(normal["vcpkg-pkgconfig-get-modules"]["host"])
            # Regenerating must be deterministic, including dependency order.
            first = (seed / "vcpkg.json").read_bytes()
            generate_seed_port(overlay)
            self.assertEqual(first, (seed / "vcpkg.json").read_bytes())

    def test_prepare_isolates_features_and_writes_no_install_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            overlay = Path(temporary) / "ports"
            generate_seed_port(overlay)
            roots = Path(temporary) / "installed"
            commands: list[list[str]] = []

            def fake_install(command: list[str], **kwargs):
                commands.append(command)
                install_arg = next(x for x in command if x.startswith("--x-install-root="))
                self.assertTrue(Path(install_arg.split("=", 1)[1]).is_dir())
                self.assertIn("--recurse", command)
                self.assertIn("--clean-buildtrees-after-build", command)
                self.assertIn("--clean-packages-after-build", command)
                self.assertNotIn("--clean-after-build", command)
                self.assertEqual(kwargs["cwd"], ROOT)
                self.assertTrue(kwargs["check"])

            with mock.patch("ffbuild.seed.subprocess.run", side_effect=fake_install):
                completed = prepare_seed(triplet="x64-windows", overlay=overlay,
                                         binary=Path("fake-vcpkg.exe"), install_root=roots)
            self.assertEqual(5, len(completed))
            self.assertEqual(len(completed), len(commands))
            self.assertEqual(0, len(list(roots.iterdir())))
            self.assertEqual([f"ffmpeg-deps[{feature}]" for feature in completed],
                             [command[2] for command in commands])
            self.assertTrue(all("ffmpeg-8-1-3" not in command for command in commands))

    def test_download_only_never_requests_compilation(self):
        with tempfile.TemporaryDirectory() as temporary:
            overlay = Path(temporary) / "ports"
            generate_seed_port(overlay)
            with mock.patch("ffbuild.seed.subprocess.run") as run:
                prepare_seed(triplet="arm64-windows", overlay=overlay,
                             binary=Path("fake-vcpkg.exe"),
                             install_root=Path(temporary) / "installed",
                             only_downloads=True)
            self.assertEqual(5, run.call_count)
            for call in run.call_args_list:
                self.assertIn("--only-downloads", call.args[0])
                self.assertNotIn("--clean-buildtrees-after-build", call.args[0])
                self.assertNotIn("--clean-packages-after-build", call.args[0])

    def test_invalid_triplet_rejected_before_any_vcpkg_call(self):
        with mock.patch("ffbuild.seed.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "Unsupported FFmpeg Triplet"):
                prepare_seed(triplet="x64-linux")
            run.assert_not_called()

    def test_workflow_prebuilds_seed_once_per_needed_triplet(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"))
        plan = workflow["jobs"]["plan"]
        prepare = workflow["jobs"]["prepare"]
        download = workflow["jobs"]["download"]
        build = workflow["jobs"]["build"]
        self.assertIn("triplets", plan["outputs"])
        plan_steps = plan["steps"]
        sdk = next(i for i, step in enumerate(plan_steps)
                   if "Align ARM SDK selection" in step.get("name", ""))
        scanner = next(i for i, step in enumerate(plan_steps)
                       if "Scan exact native vcpkg" in step.get("name", ""))
        self.assertLess(sdk, scanner)
        self.assertIn("prepare-host --triplet=arm-windows", plan_steps[sdk]["run"])
        self.assertIn("fromJSON(needs.plan.outputs.triplets)",
                      prepare["strategy"]["matrix"]["triplet"])
        self.assertEqual(["plan", "prepare"], build["needs"])
        self.assertEqual(["plan", "download"], prepare["needs"])
        self.assertEqual("plan", download["needs"])
        prepare_steps = prepare["steps"]
        build_steps = build["steps"]
        download_steps = download["steps"]
        self.assertTrue(any("--only-downloads" in step.get("run", "")
                            for step in download_steps))
        source_save = next(step for step in download_steps if
                           step.get("uses", "").startswith("actions/cache/save@"))
        source_restore = next(step for step in prepare_steps if
                              step.get("name") == "Restore shared dependency source downloads")
        self.assertEqual(source_save["with"]["key"], source_restore["with"]["key"])
        self.assertEqual(True, source_restore["with"]["fail-on-cache-miss"])
        seed_save = next(step for step in prepare_steps if
                         step.get("uses", "").startswith("actions/cache/save@"))
        restored = next(step for step in build_steps if
                        step.get("uses", "").startswith("actions/cache/restore@"))
        self.assertEqual(seed_save["with"]["key"], restored["with"]["key"])
        self.assertEqual(True, restored["with"]["fail-on-cache-miss"])
        self.assertFalse(any(step.get("uses", "").startswith("actions/cache/save@")
                             for step in build_steps))
        worker_install = next(step for step in build_steps
                              if "Build and test via native vcpkg" in step.get("name", ""))
        self.assertTrue(worker_install["env"]["VCPKG_BINARY_SOURCES"].endswith(",read"))
        self.assertTrue(any("python -m ffbuild prepare" in step.get("run", "")
                            for step in prepare_steps))


if __name__ == "__main__":
    unittest.main()
