"""Daily release selection and workflow guards (pure/offline)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import yaml

from ffbuild import schedule
from ffbuild.native_abi import build_requests
from ffbuild.versions import ROOT, has_source, versions


def workflow(name: str) -> dict:
    return yaml.load(
        (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


class DailyReleaseSelectionTests(unittest.TestCase):
    def test_rotation_contains_only_source_backed_versions_and_master(self):
        cycle = schedule.release_cycle()
        self.assertEqual(27, len(cycle))
        self.assertEqual(1, cycle.count("master"))
        self.assertEqual(len(cycle), len(set(cycle)))
        self.assertEqual({v for v in versions() if has_source(v)} | {"master"}, set(cycle))

    def test_each_day_schedules_exactly_one_version_without_starvation(self):
        start = date(2026, 1, 1)
        cycle = schedule.release_cycle()
        selected = [
            schedule.select_daily_version(start + timedelta(days=i), cycle=cycle)
            for i in range(len(cycle))
        ]
        self.assertEqual(list(cycle), selected)
        self.assertEqual(cycle[0], schedule.select_daily_version(
            start + timedelta(days=len(cycle)), cycle=cycle))
        self.assertEqual(selected[0], schedule.select_daily_version(start, cycle=cycle))

    def test_selector_never_publishes_a_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "gha-output.txt"
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(target)}):
                schedule.main(["--date", "2026-11-23", "--github-output"])
            outputs = dict(line.split("=", 1) for line in target.read_text().splitlines())
            self.assertEqual(schedule.select_daily_version(date(2026, 11, 23)),
                             outputs["version"])
            self.assertEqual("2026-11-23", outputs["date"])
            self.assertEqual("27", outputs["cycle_size"])
            self.assertNotIn(",", outputs["version"])

    def test_one_selected_release_has_at_most_sixteen_abi_variants(self):
        for name in (schedule.release_cycle()[0], schedule.release_cycle()[8]):
            requests, blocked = build_requests(version=name)
            self.assertEqual(16, len(requests))
            self.assertFalse(blocked)
            self.assertEqual({name}, {row["yaml"] for row in requests})

    def test_invalid_cycles_and_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            schedule.select_daily_version(date(2026, 1, 2), cycle=("8.1.3", "8.1.3"))
        with self.assertRaisesRegex(ValueError, "epoch"):
            schedule.select_daily_version(date(2025, 12, 31))


class WorkflowReleasePolicyTests(unittest.TestCase):
    def test_daily_trigger_passes_exactly_one_selected_version(self):
        ci = workflow("build-all.yml")
        self.assertIn("schedule", ci["on"])
        self.assertIn("select-daily-release", ci["jobs"])
        scheduler = ci["jobs"]["select-daily-release"]
        self.assertIn("python -m ffbuild.schedule --github-output",
                      str(scheduler["steps"]))
        build = ci["jobs"]["build"]
        self.assertEqual("select-daily-release", build["needs"])
        self.assertIn("needs.select-daily-release.outputs.version", build["with"]["yaml"])
        self.assertIn("needs.select-daily-release.result == 'skipped'", build["if"])

    def test_push_and_pr_are_validation_only(self):
        ci = workflow("build-all.yml")
        self.assertIn("github.event_name == 'pull_request'", ci["jobs"]["build"]["with"]["dry_run"])
        self.assertIn("github.event_name == 'push'", ci["jobs"]["build"]["with"]["dry_run"])
        self.assertEqual("true", ci["on"]["workflow_dispatch"]["inputs"]["version"]["required"])

    def test_publication_fails_without_one_explicit_version(self):
        reusable = workflow("build-release.yml")
        steps = reusable["jobs"]["plan"]["steps"]
        gates = [step for step in steps
                 if step.get("name") == "Require a single target for every publishing build"]
        self.assertEqual(1, len(gates))
        script = gates[0]["run"]
        self.assertIn("RELEASE_YAML -notmatch", script)
        self.assertIn("RELEASE_HISTORY -eq 'true'", script)
        self.assertIn("RELEASE_SHARD_COUNT", script)
        self.assertIn("RELEASE_SHARD_INDEX", script)
        self.assertIn("!inputs.dry_run", gates[0]["if"])

    def test_publish_handles_deliberately_skipped_second_matrix(self):
        publish = workflow("build-release.yml")["jobs"]["publish"]
        condition = publish["if"]
        self.assertIn("!cancelled()", condition)
        self.assertIn("needs.build-extra.result == 'skipped'", condition)
        self.assertIn("needs.build-extra.result == 'success'", condition)
        self.assertIn("needs.plan.result == 'success'", condition)
        self.assertIn("!inputs.force", condition)

    def test_master_is_not_another_independent_scheduled_release(self):
        master = workflow("master-build.yml")
        self.assertNotIn("schedule", master["on"])
        self.assertIn("github.event_name == 'push'", master["jobs"]["build"]["with"]["dry_run"])


if __name__ == "__main__":
    unittest.main()
