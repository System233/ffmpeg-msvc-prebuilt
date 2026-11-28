"""Ensure unprivileged PR validation cannot publish or mutate production refs."""
from __future__ import annotations

import unittest

import yaml

from ffbuild.versions import ROOT


def workflow(filename: str) -> dict:
    return yaml.load(
        (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


class IsolatedE2ETests(unittest.TestCase):
    def test_skip_switches_exist_only_on_reusable_entrypoint(self):
        nested = workflow("build-release.yml")
        primary = workflow("build-all.yml")
        for key in ("skip_release", "skip_publish"):
            self.assertIn(key, nested["on"]["workflow_call"]["inputs"])
            self.assertEqual("false", nested["on"]["workflow_call"]["inputs"][key]["default"])
        dispatch = nested["on"]["workflow_dispatch"]["inputs"]
        # Manual validation is explicit, non-publishing, and defaults off.
        # It must not expose the reusable workflow's publication bypasses.
        self.assertEqual({"yaml", "dry_run", "target_arch", "target_license"}, set(dispatch))
        self.assertEqual("false", dispatch["dry_run"]["default"])
        self.assertNotIn("skip_release", dispatch)
        self.assertNotIn("skip_publish", dispatch)
        self.assertNotIn("force", dispatch)
        self.assertIn("!inputs.dry_run", nested["jobs"]["publish"]["if"])
        self.assertNotIn("workflow_dispatch", primary["on"])
        self.assertEqual("true", primary["jobs"]["build"]["with"]["skip_publish"])

    def test_skip_release_disables_packaging_in_worker(self):
        ci = workflow("build-release.yml")
        for name in ("build",):
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
            self.assertTrue(any("ffbuild.ci worker-build" in s.get("run", "") for s in steps))

    def test_public_sdk_smoke_runs_after_archive_gate_before_upload(self):
        steps = workflow("build-release.yml")["jobs"]["build"]["steps"]
        idx = next(i for i, step in enumerate(steps)
                   if step.get("name") == "Validate extracted public SDK and CLI")
        self.assertEqual("Verify and package installed vcpkg result", steps[idx-1]["name"])
        self.assertIn("!inputs.skip_release", steps[idx]["if"])
        self.assertEqual("${{ !inputs.skip_release }}", steps[idx]["if"])
        self.assertNotIn("matrix.triplet", steps[idx]["if"])
        self.assertIn("ffbuild.ci verify-sdk", steps[idx]["run"])
        self.assertTrue(any(step.get("name") == "Upload distribution and internal audit evidence"
                            for step in steps[idx+1:]))

    def test_installed_sdk_is_validated_even_without_release_packaging(self):
        steps = workflow("build-release.yml")["jobs"]["build"]["steps"]
        idx = next(i for i, step in enumerate(steps)
                   if step.get("name") == "Validate independent installed SDK consumers")
        self.assertEqual("Verify no external dependencies were compiled by Worker", steps[idx-1]["name"])
        self.assertIn("matrix.linkage == 'static' || inputs.skip_release", steps[idx]["if"])
        self.assertNotIn("matrix.triplet", steps[idx]["if"])
        self.assertNotIn("&&", steps[idx]["if"])
        self.assertIn("verify-installed-sdk", steps[idx]["run"])
        self.assertIn("--report installed-sdk-tests.json", steps[idx]["run"])
        self.assertEqual("Verify and package installed vcpkg result", steps[idx+1]["name"])

    def test_seed_cache_keys_do_not_depend_on_consumer_source(self):
        for relative in (".github/workflows/build-release.yml", ".github/actions/prepare-repair/action.yml"):
            text=(ROOT/relative).read_text(encoding="utf-8")
            hashes=[line for line in text.splitlines() if "hashFiles(" in line]
            self.assertEqual(1,len(hashes))
            self.assertIn("'!ports/ffmpeg-tester/**'",hashes[0])

    def test_workers_select_only_one_version_port_for_stable_ffmpeg(self):
        import os,json
        from unittest.mock import patch
        from ffbuild import ci
        from ffbuild.versions import GENERATED_PORTS
        from ffbuild.port import ffmpeg_port_name
        job={"yaml":"8.1.3","port":"ffmpeg","tester_port":"ffmpeg-tester","package":"ffmpeg[all-lgpl]",
             "triplet":"x64-windows"}
        with patch.dict(os.environ,{"FFBUILD_JOB":json.dumps(job),"VCPKG_ROOT":"root","FFBUILD_CACHE_DIR":"cache"}), \
             patch("ffbuild.cache_guard.install_target") as install:
            ci.worker_build()
            self.assertEqual(job,install.call_args.args[0])
            self.assertEqual(GENERATED_PORTS/ffmpeg_port_name("8.1.3"),install.call_args.kwargs["port"])
            self.assertTrue(install.call_args.kwargs["env"]["VCPKG_BINARY_SOURCES"].endswith(",read"))

    def test_publish_requires_explicitly_enabled_and_not_ci_ref(self):
        ci = workflow("build-release.yml")
        gate = ci["jobs"]["publish"]["if"]
        for condition in ("!inputs.skip_release", "!inputs.skip_publish",
                          "!inputs.dry_run", "needs.select.outputs.production == 'true'"):
            self.assertIn(condition, gate)
        self.assertIn("needs.build.result == 'success'", gate)
        # GitHub rejects reusable workflow permission escalation at startup,
        # even when the privileged job is guarded with if: false.
        self.assertEqual("read", ci["jobs"]["publish"]["permissions"]["contents"])

    def test_no_temporary_smoke_workflow_or_branch_push_bypass(self):
        self.assertFalse((ROOT / ".github/workflows/ci-e2e.yml").exists())
        nested = workflow("build-release.yml")
        self.assertEqual("ffbuild-native-production", nested["concurrency"]["group"])
        self.assertEqual({"yaml", "dry_run", "skip_release", "skip_publish", "force", "target_arch", "target_license"},
                         set(nested["on"]["workflow_call"]["inputs"]))
        self.assertNotIn("push", nested["on"])
        from ffbuild.release_trigger import build_gate
        with self.assertRaisesRegex(ValueError, "Unauthorized native build event"):
            build_gate({}, {"GITHUB_REF":"refs/heads/ci/e2e-test",
                            "GITHUB_EVENT_NAME":"push","TARGET_VERSION":"8.1.3",
                            "VALIDATION_ONLY":"true","SKIP_PUBLISH":"true"})


if __name__ == "__main__":
    unittest.main()
