"""Ensure branch CI smoke cannot publish or mutate production refs."""
from __future__ import annotations

import unittest

import yaml

from ffbuild.native_abi import build_requests
from ffbuild.versions import ROOT


def workflow(filename: str) -> dict:
    return yaml.load(
        (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


class IsolatedE2ETests(unittest.TestCase):
    def test_both_skip_switches_exist_on_all_entrypoints(self):
        nested = workflow("build-release.yml")
        primary = workflow("build-all.yml")
        for key in ("skip_release", "skip_publish"):
            self.assertIn(key, nested["on"]["workflow_call"]["inputs"])
            self.assertIn(key, nested["on"]["workflow_dispatch"]["inputs"])
            self.assertEqual("false", nested["on"]["workflow_call"]["inputs"][key]["default"])
            self.assertIn(key, primary["on"]["workflow_dispatch"]["inputs"])
            self.assertIn("inputs." + key, primary["jobs"]["build"]["with"][key])

    def test_skip_release_disables_packaging_in_both_matrix_jobs(self):
        ci = workflow("build-release.yml")
        for name in ("build", "build-extra"):
            steps = ci["jobs"][name]["steps"]
            packages = [s for s in steps if s.get("name") ==
                        "Verify and package installed vcpkg result"]
            self.assertEqual(1, len(packages))
            self.assertIn("!inputs.skip_release", packages[0]["if"])
            uploads = [s for s in steps
                       if s.get("uses", "").startswith("actions/upload-artifact")
                       and s.get("with", {}).get("name", "").startswith("${{ matrix.id }}")]
            self.assertEqual(1, len(uploads))
            self.assertIn("!inputs.skip_release", uploads[0]["if"])
            self.assertTrue(any("ffvcpkg install" in s.get("run", "") for s in steps))

    def test_workers_select_only_one_version_port_for_stable_ffmpeg(self):
        ci = workflow("build-release.yml")
        for name in ("build", "build-extra"):
            with self.subTest(worker=name):
                steps = ci["jobs"][name]["steps"]
                build = next(step["run"] for step in steps
                             if step.get("name") == "Build and test via native vcpkg")
                self.assertIn("$job.yaml.Replace('.', '-')", build)
                self.assertIn('"--overlay-ports=$versionPort"', build)
                self.assertIn('"--overlay-ports=ports"', build)
                self.assertIn("$job.package $job.tester_port", build)
                self.assertNotIn("ffmpeg-tester-$", build)
                self.assertNotIn("--overlay-ports=_work/ffbuild/generated-ports ", build)
                self.assertIn("packages/${{ matrix.port }}_${{ matrix.triplet }}",
                              next(step["run"] for step in steps if step.get("name") ==
                                   "Verify and package installed vcpkg result"))

    def test_publish_requires_explicitly_enabled_and_not_ci_ref(self):
        ci = workflow("build-release.yml")
        gate = ci["jobs"]["publish"]["if"]
        for condition in ("!inputs.skip_release", "!inputs.skip_publish",
                          "!inputs.dry_run", "refs/heads/ci/"):
            self.assertIn(condition, gate)
        self.assertIn("needs.build.result == 'success'", gate)
        # GitHub rejects reusable workflow permission escalation at startup,
        # even when the privileged job is guarded with if: false.
        self.assertEqual("read", ci["jobs"]["publish"]["permissions"]["contents"])

    def test_ci_branch_only_runs_unprivileged_smoke(self):
        ci = workflow("ci-e2e.yml")
        self.assertEqual("FFmpeg CI E2E Isolated", ci["name"])
        self.assertEqual({"push"}, set(ci["on"]))
        self.assertEqual(["ci/e2e-*"], ci["on"]["push"]["branches"])
        self.assertEqual({"contents": "read", "actions": "read"}, ci["permissions"])
        self.assertEqual({"smoke"}, set(ci["jobs"]))
        test = ci["jobs"]["smoke"]
        self.assertEqual("./.github/workflows/build-release.yml", test["uses"])
        self.assertEqual({"contents": "read", "actions": "read"}, test["permissions"])
        self.assertNotIn("secrets", test)
        for flag in ("dry_run", "skip_publish", "force"):
            self.assertEqual("true", test["with"][flag])
        self.assertEqual("false", test["with"]["skip_release"])
        self.assertTrue(any(row["yaml"] == "5.1.10" for row in
                            test["strategy"]["matrix"]["include"]))

    def test_abi_scan_selects_static_and_shared_compliance_smoke(self):
        ci = workflow("ci-e2e.yml")["jobs"]["smoke"]
        rows = ci["strategy"]["matrix"]["include"]
        self.assertEqual("false", ci["strategy"]["fail-fast"])
        self.assertEqual(2, len(rows))
        self.assertEqual(2, len({row["yaml"] for row in rows}))
        self.assertFalse(any(row["yaml"].startswith("8.1") for row in rows))
        self.assertFalse(any(row["yaml"] == "3.4.14" for row in rows))
        self.assertEqual("${{ matrix.yaml }}", ci["with"]["yaml"])
        self.assertEqual("${{ matrix.shard_index }}", ci["with"]["shard_index"])
        self.assertEqual(16, int(ci["with"]["shard_count"]))
        expected = {
            "5.1.10": ("x64-windows", "lgpl", "static"),
            "7.1.5": ("arm-windows", "gpl", "shared"),
        }
        for row in rows:
            with self.subTest(version=row["yaml"], shard=row["shard_index"]):
                requests, blocked = build_requests(version=row["yaml"])
                self.assertFalse(blocked)
                ordered = sorted(requests, key=lambda item:
                                 (item["yaml"], item["triplet"], item["package"]))
                selected = [item for index, item in enumerate(ordered)
                            if index % int(ci["with"]["shard_count"]) == int(row["shard_index"])]
                self.assertEqual(1, len(selected))
                self.assertEqual(expected[row["yaml"]],
                                 (selected[0]["triplet"], selected[0]["license"],
                                  selected[0]["linkage"]))

    def test_isolated_name_cannot_trigger_main_autoheal(self):
        name = workflow("ci-e2e.yml")["name"]
        autoheal = workflow("auto-heal.yml")
        listened = autoheal["on"]["workflow_run"]["workflows"]
        self.assertNotIn(name, listened)


if __name__ == "__main__":
    unittest.main()
