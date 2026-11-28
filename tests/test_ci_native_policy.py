"""Historical vcpkg ABI and selective validation regression contracts."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
import ffvcpkg
from ffbuild import release_trigger
from ffbuild.native_abi import collect_abi_evidence, compare_abi_evidence
from ffbuild.seed import seed_hash, require_seed_archives
from ffbuild.versions import ROOT


class NativeToolPolicy(unittest.TestCase):
    def test_environment_preserves_caller_and_forces_downloaded_tools(self):
        original = {"VCPKG_FORCE_DOWNLOADED_BINARIES": "0", "VCPKG_BINARY_SOURCES": "clear",
                    "PYTHONIOENCODING": "cp1252"}
        result = ffvcpkg.environment(original)
        self.assertEqual("1", result["VCPKG_FORCE_DOWNLOADED_BINARIES"])
        self.assertEqual("utf-8", result["PYTHONIOENCODING"])
        self.assertEqual("clear", result["VCPKG_BINARY_SOURCES"])
        self.assertEqual("0", original["VCPKG_FORCE_DOWNLOADED_BINARIES"])

    def test_all_install_modes_use_exact_versions_once(self):
        for options in ([], ["--dry-run"], ["--only-downloads"], ["--only-binarycaching"],
                        ["--dry-run", ffvcpkg.EXACT_ABI_TOOLS]):
            with self.subTest(options=options):
                command = ffvcpkg.command(["install", "zlib", *options], binary=Path("vcpkg.exe"))
                self.assertEqual(1, command.count(ffvcpkg.EXACT_ABI_TOOLS))
                self.assertTrue(all(option in command for option in options))
        self.assertEqual(["vcpkg.exe", "version"], ffvcpkg.command(["version"], binary=Path("vcpkg.exe")))

    def test_cli_native_environment(self):
        with patch("ffvcpkg.executable", return_value=Path("vcpkg.exe")), \
                patch("ffvcpkg.subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertEqual(0, ffvcpkg.main(["install", "zlib", "--dry-run"]))
            self.assertIn(ffvcpkg.EXACT_ABI_TOOLS, run.call_args.args[0])
            self.assertEqual("1", run.call_args.kwargs["env"]["VCPKG_FORCE_DOWNLOADED_BINARIES"])

    def test_seed_archive_gate_uses_only_external_abis(self):
        batch = {"abis":{"zlib_x64-windows":"b"*64},
                 "specs":{"zlib_x64-windows":"zlib[core]:x64-windows"}}
        plan = {"batches":[batch]}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "Seed cache incomplete"):
                require_seed_archives(plan, cache)
            abi = "b"*64
            folder = cache / abi[:2]; folder.mkdir()
            archive=folder / (abi + ".zip")
            archive.touch()
            with self.assertRaisesRegex(RuntimeError, "Seed cache incomplete"):
                require_seed_archives(plan, cache)
            archive.write_bytes(b"fixture")
            require_seed_archives(plan, cache)

    def test_actual_input_files_must_match_graph_and_show_component_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            buildtrees = root / "buildtrees"
            p = buildtrees / "zlib" / "x64-windows.vcpkg_abi_info.txt"
            p.parent.mkdir(parents=True)
            old = b"cmake 4.3.2\npowershell 7.6.1\ntriplet_abi abc\n"
            new = b"cmake 4.3.2\npowershell 7.7.0\ntriplet_abi abc\n"
            for data, name in ((old, "before"), (new, "after")):
                p.write_bytes(data)
                collect_abi_evidence({"zlib_x64-windows": hashlib.sha256(data).hexdigest()},
                                     buildtrees, root / name)
            report = compare_abi_evidence(root / "before", root / "after")
            self.assertEqual({"powershell": {"before": ["7.6.1"], "after": ["7.7.0"]}},
                             report["changed"]["zlib_x64-windows"]["entries"])
            with self.assertRaisesRegex(RuntimeError, "differs"):
                collect_abi_evidence({"zlib_x64-windows": hashlib.sha256(old).hexdigest()},
                                     buildtrees, root / "invalid")
            (root / "after/zlib_x64-windows.txt").write_bytes(old)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                compare_abi_evidence(root / "before", root / "after")

    def test_workflow_seed_exact_key_and_gate(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-release.yml").read_text())
        for job in ("prepare", "build"):
            steps = workflow["jobs"][job]["steps"]
            for step in steps:
                key = step.get("with", {}).get("key", "")
                if key.startswith("ffbuild-seed-"):
                    self.assertIn("fromJSON(needs.plan.outputs.seed_keys)[matrix.triplet]", key)
                    self.assertNotIn("hashFiles", key)
        prepare = [s.get("name") for s in workflow["jobs"]["prepare"]["steps"]]
        self.assertLess(prepare.index("Verify Seed runner native ABI equals planned ABI"),
                        prepare.index("Restore previously prebuilt dependency binaries"))
        self.assertLess(prepare.index("Verify prepared Seed has every native ABI archive"),
                        prepare.index("Save completed shared dependency cache"))
        self.assertIn("!inputs.dry_run", workflow["jobs"]["publish"]["if"])


class ManualValidationScope(unittest.TestCase):
    def test_explicit_validation_only_allows_filters(self):
        sha = "a"*40
        env = {"GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
               "GITHUB_SHA": sha, "TARGET_VERSION": "8.1.3", "VALIDATION_ONLY": "true",
               "SKIP_PUBLISH": "true", "TARGET_ARCH": "arm-windows", "TARGET_LICENSE": "gpl"}
        payload = {"inputs": {"yaml": "8.1.3", "dry_run": "true",
                              "target_arch": "arm-windows", "target_license": "gpl"}}
        with patch.object(release_trigger, "git", return_value=sha), \
                patch.object(release_trigger.subprocess, "run"):
            self.assertEqual("false", release_trigger.build_gate(payload, env)["production"])
            for change in ({"VALIDATION_ONLY": "false"}, {"SKIP_PUBLISH": "false"},
                           {"GITHUB_REF": "refs/heads/topic"}, {"TARGET_ARCH": "x64-windows"},
                           {"TARGET_LICENSE": "nonfree"}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    release_trigger.build_gate(payload, dict(env, **change))
            with self.assertRaises(ValueError):
                release_trigger.build_gate({"inputs": dict(payload["inputs"], dry_run="false")}, env)


if __name__ == "__main__":
    unittest.main()
