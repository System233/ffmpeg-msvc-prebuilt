"""Production scheduling and trigger boundaries."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from ffbuild.native_abi import build_requests
from ffbuild.versions import ROOT


def workflow(name: str) -> dict:
    return yaml.load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"),
                     Loader=yaml.BaseLoader)


class WorkflowReleasePolicyTests(unittest.TestCase):
    def test_exactly_one_daily_schedule_and_friday_master(self):
        schedules = {}
        for file in (ROOT / ".github/workflows").glob("*.yml"):
            data = workflow(file.name)
            if "schedule" in data["on"]:
                schedules[file.name] = [row["cron"] for row in data["on"]["schedule"]]
        self.assertEqual({"scan-updates.yml": ["0 6 * * *"],
                          "master-build.yml": ["0 6 * * 5"],
                          "dependency-submission.yml": ["0 6 * * 1"],
                          "retention-cleanup.yml": ["0 0 * * 0"]}, schedules)
        self.assertNotIn("schedule", workflow("build-all.yml")["on"])

    def test_push_and_normal_pr_only_run_static_checks(self):
        ci = workflow("build-all.yml")
        self.assertEqual({"push", "pull_request"}, set(ci["on"]))
        self.assertEqual("validate", ci["jobs"]["build"]["needs"])
        self.assertIn("needs.validate.outputs.version != ''", ci["jobs"]["build"]["if"])
        self.assertEqual("true", ci["jobs"]["build"]["with"]["dry_run"])
        self.assertEqual("true", ci["jobs"]["build"]["with"]["force"])
        self.assertEqual("true", ci["jobs"]["build"]["with"]["skip_publish"])
        self.assertIn("release_trigger pr-gate", str(ci["jobs"]["validate"]["steps"]))
        submission = workflow("dependency-submission.yml")
        self.assertEqual(["main"], submission["on"]["push"]["branches"])
        self.assertIn("ports/**", submission["on"]["push"]["paths"])
        self.assertIn("ffmpeg/**", submission["on"]["push"]["paths"])
        self.assertIn("submit-dependencies", str(submission["jobs"]["submit"]["steps"]))
        self.assertNotIn("ffvcpkg install", str(submission["jobs"]["submit"]["steps"]))

    def test_production_build_requires_dispatch_and_single_version(self):
        ci = workflow("build-release.yml")
        self.assertEqual({"workflow_dispatch", "workflow_call"}, set(ci["on"]))
        self.assertEqual({"yaml", "dry_run", "target_arch", "target_license"},
                         set(ci["on"]["workflow_dispatch"]["inputs"]))
        self.assertEqual("false", ci["on"]["workflow_dispatch"]["inputs"]["dry_run"]["default"])
        self.assertEqual("true", ci["on"]["workflow_dispatch"]["inputs"]["yaml"]["required"])
        self.assertEqual("select", ci["jobs"]["plan"]["needs"])
        self.assertIn("release_trigger build-gate", str(ci["jobs"]["select"]["steps"]))
        condition = ci["jobs"]["publish"]["if"]
        self.assertIn("needs.select.outputs.production == 'true'", condition)
        self.assertIn("needs.build.result == 'success'", condition)
        self.assertNotIn("build-extra", ci["jobs"])
        self.assertIn("!inputs.force", condition)
        self.assertIn("ffbuild.ci plan", str(ci["jobs"]["plan"]["steps"]))
        requests, blocked = build_requests(version="8.1.3", release_date="2026-11-25")
        self.assertFalse(blocked)
        from ffbuild.targets import load_targets
        self.assertEqual(len(load_targets()), len(requests))
        self.assertEqual({"8.1.3"}, {row["yaml"] for row in requests})
        self.assertEqual({"2026-11-25"}, {row["release_date"] for row in requests})

    def test_no_workflow_builds_on_tag_push_or_pr_merge(self):
        master = workflow("master-build.yml")
        self.assertEqual({"schedule"}, set(master["on"]))
        self.assertEqual("master", master["jobs"]["build"]["with"]["yaml"])
        self.assertEqual("./.github/workflows/build-release.yml", master["jobs"]["build"]["uses"])
        for file in (ROOT / ".github/workflows").glob("*.yml"):
            data = workflow(file.name)
            events = data["on"]
            body = file.read_text(encoding="utf-8")
            self.assertNotIn("tag-merged-pr", body, file.name)
            self.assertNotIn("release_trigger create-tag", body, file.name)
            if isinstance(events, dict):
                push = events.get("push") or {}
                if isinstance(push, dict) and "push" in events:
                    self.assertNotIn("tags", push, file.name)
                    self.assertTrue(push.get("branches"), file.name)
                for event in ("pull_request", "pull_request_target"):
                    config = events.get(event) or {}
                    if isinstance(config, dict):
                        self.assertNotIn("closed", config.get("types", []), file.name)
        self.assertFalse((ROOT / ".github/workflows/tag-version.yml").exists())

    def test_cli_cannot_create_prebuild_tag(self):
        from ffbuild import release_trigger
        from unittest.mock import patch
        with patch.object(release_trigger, "write_publication_tag") as create:
            for command in ("create-tag", "tag-merged-pr"):
                with self.assertRaises(SystemExit) as error:
                    release_trigger.main([command])
                self.assertEqual(2, error.exception.code)
            create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
