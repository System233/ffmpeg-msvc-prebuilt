"""Offline security and lifecycle tests for the independent multi-version Auto-Heal."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ffbuild.autoheal import delivery, github, ledger, policy, scope, triage
from ffbuild.autoheal.models import validate_triage, version_name

SHA = "a" * 40
ABI = "b" * 64
SIG = "c" * 64


def plan_row(version="8.1.1", variant="var001", triplet="x64-windows"):
    return {
        "yaml": version, "id": variant, "triplet": triplet, "abi_hash": ABI,
        "port": "ffmpeg-8-1-1", "package": "ffmpeg-8-1-1[gpl]",
        "revision": 1, "version": version,
    }


def job(row, *, step="Build and test via native vcpkg", conclusion="failure"):
    return {
        "id": 100 + len(row["id"]),
        "name": f"Build All / ffbuild-{row['id']}",
        "conclusion": conclusion,
        "steps": [{"name": step, "conclusion": conclusion}],
    }


def run_data(conclusion="failure"):
    return {
        "name": "Build All FFmpeg Versions", "id": 12345, "event": "schedule",
        "head_branch": "main", "head_sha": SHA, "conclusion": conclusion,
        "html_url": "https://github.com/System233/ffmpeg-msvc-prebuilt/actions/runs/12345",
    }


def artifact(row):
    return {"name": f"build-logs-a1-{row['yaml']}-{row['id']}", "expired": False}


SOURCE_LOG = "libavcodec/my_filter.c:143: error C2065: undeclared identifier\n"
INFRA_LOG = "error: cache miss, runner returned HTTP 503\n"


class TriageTests(unittest.TestCase):
    def test_two_versions_do_not_collapse_into_first_yaml(self):
        left, right = plan_row("8.1.1", "variant-a"), plan_row("7.1", "variant-b")
        report = triage.analyze(run_data(), 1, [job(left), job(right)],
                                [artifact(left), artifact(right)],
                                {"jobs": [left, right]},
                                logs={artifact(left)["name"]: SOURCE_LOG,
                                      artifact(right)["name"]: SOURCE_LOG})
        self.assertEqual({"7.1", "8.1.1"}, {g["yaml"] for g in report["groups"]})
        self.assertTrue(all(g["repairable"] for g in report["groups"]))
        self.assertEqual(2, sum(len(g["jobs"]) for g in report["groups"]))

    def test_multi_arch_failure_is_one_yaml_incident(self):
        rows = [plan_row("8.1.1", "v1", "x64-windows"),
                plan_row("8.1.1", "v2", "arm64-windows")]
        report = triage.analyze(run_data(), 1, [job(x) for x in rows],
                                [artifact(x) for x in rows], {"jobs": rows},
                                logs={artifact(x)["name"]: SOURCE_LOG for x in rows})
        self.assertEqual(1, len(report["groups"]))
        self.assertEqual(2, len(report["groups"][0]["jobs"]))
        self.assertTrue(report["groups"][0]["repairable"])

    def test_no_plan_fails_closed_with_shared_diagnostic(self):
        report = triage.analyze(run_data(), 1, [job(plan_row())], [], None)
        self.assertEqual([], report["groups"])
        self.assertFalse(report["plan_available"])
        self.assertEqual(1, len(report["diagnostics"]))

    def test_missing_build_log_or_mixed_failure_is_not_repaired(self):
        row = plan_row()
        report = triage.analyze(run_data(), 1, [job(row)], [], {"jobs": [row]})
        self.assertFalse(report["groups"][0]["repairable"])
        second = plan_row("8.1.1", "v2")
        other = triage.analyze(run_data(), 1,
                               [job(row), job(second, step="Verify worker vcpkg ABI equals planned ABI")],
                               [artifact(row), artifact(second)],
                               {"jobs": [row, second]},
                               logs={artifact(row)["name"]: SOURCE_LOG})
        self.assertFalse(other["groups"][0]["repairable"])

    def test_unknown_job_identity_does_not_guess_version(self):
        row = plan_row()
        result = triage.analyze(run_data(), 1, [{
            **job(row), "name": "build (x64-windows, gpl, shared)"
        }], [artifact(row)], {"jobs": [row]})
        self.assertFalse(result["groups"])
        self.assertEqual("build", result["diagnostics"][0]["phase"])
        self.assertFalse(result["diagnostics"][0]["repairable"])

    @mock.patch("ffbuild.autoheal.triage.github.download_artifact")
    def test_plan_artifact_is_bound_to_exact_run_attempt(self, download):
        row = plan_row()
        with tempfile.TemporaryDirectory() as temporary:
            def put_plan(run_id, name, directory):
                self.assertEqual("ffbuild-plan-a2", name)
                (directory / "ffbuild-plan.json").write_text(
                    json.dumps({"schema": 3, "jobs": [row]}), encoding="utf-8")
            download.side_effect = put_plan
            artifacts = [
                {"name": "ffbuild-plan-a1", "expired": False,
                 "created_at": "2026-11-23T00:00:00Z"},
                {"name": "ffbuild-plan-a2", "expired": False,
                 "created_at": "2026-11-23T01:05:00Z"},
            ]
            plan = triage._plan_from_artifact(12345, 2, artifacts,
                                               "2026-11-23T01:00:00Z")
            self.assertEqual(row["abi_hash"], plan["jobs"][0]["abi_hash"])
            self.assertEqual(1, download.call_count)
            self.assertIsNone(triage._plan_from_artifact(12345, 3, artifacts,
                                                        "2026-11-23T01:00:00Z"))

    def test_unsupported_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            triage.analyze({**run_data(), "name": "untrusted"}, 1, [], [], None)

    def test_timed_out_build_is_not_source_repair(self):
        row = plan_row()
        report = triage.analyze(run_data(), 1,
                                [job(row, conclusion="timed_out")],
                                [artifact(row)], {"jobs": [row]},
                                logs={artifact(row)["name"]: SOURCE_LOG})
        self.assertFalse(report["groups"][0]["repairable"])
        self.assertEqual("timeout", report["groups"][0]["jobs"][0]["classification"])

    def test_infrastructure_and_seed_always_nonrepairable(self):
        row = plan_row()
        self.assertEqual(("build", "environment", False),
                         policy.classify(job(row), INFRA_LOG))
        seed = {**job(row), "name": "prepare-arm64-windows"}
        self.assertEqual(("prepare", "seed_dependency", False),
                         policy.classify(seed, SOURCE_LOG))
        abi = job(row, step="Verify worker vcpkg ABI equals planned ABI")
        self.assertEqual(("abi", "abi_mismatch", False), policy.classify(abi, SOURCE_LOG))


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / "ffmpeg").mkdir()
        (self.root / "ffmpeg" / "base.yaml").write_text("patches: []\n", encoding="utf-8")
        (self.root / "ffmpeg" / "8.1.yaml").write_text("extends: base\n", encoding="utf-8")
        (self.root / "patches" / "8.x").mkdir(parents=True)
        (self.root / "ffmpeg" / "8.1.1.yaml").write_text(
            "patches:\n  - 8.x/exclusive.patch\n", encoding="utf-8")
        (self.root / "ffmpeg" / "8.1.2.yaml").write_text(
            "patches:\n  - 8.x/shared.patch\n", encoding="utf-8")
        (self.root / "patches" / "8.x" / "exclusive.patch").write_text(
            "diff --git a/x b/x\n", encoding="utf-8")

    def test_valid_target_and_exclusive_new_patch(self):
        self.assertEqual(
            ["ffmpeg/8.1.1.yaml", "patches/8.x/exclusive.patch"],
            scope.validate_changes("8.1.1",
                                   [("M", "ffmpeg/8.1.1.yaml"),
                                    ("A", "patches/8.x/exclusive.patch")],
                                   self.root, before="patches: []\n"))

    def test_reject_all_cross_version_and_high_privilege_files(self):
        for filename in ("ffmpeg/8.1.2.yaml", "ffmpeg/base.yaml",
                         ".github/workflows/build-all.yml",
                         "ports/lame/portfile.cmake", "data/file.yaml",
                         "scripts/ci/apply_fix.py", "../patches/8.x/bad.patch"):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    scope.validate_changes("8.1.1",
                                           [("M", "ffmpeg/8.1.1.yaml"),
                                            ("M", filename)], self.root)

    def test_missing_target_empty_changes_and_existing_patch_rejected(self):
        for changes in ([], [("A", "patches/8.x/exclusive.patch")],
                        [("M", "ffmpeg/8.1.1.yaml"),
                         ("M", "patches/8.x/exclusive.patch")]):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                scope.validate_changes("8.1.1", changes, self.root)

    def test_shared_patch_cannot_be_added_even_if_file_was_added(self):
        (self.root / "ffmpeg" / "8.1.1.yaml").write_text(
            "patches:\n - 8.x/shared.patch\n", encoding="utf-8")
        (self.root / "patches" / "8.x" / "shared.patch").write_text(
            "new\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "another version"):
            scope.validate_changes("8.1.1",
                                   [("M", "ffmpeg/8.1.1.yaml"),
                                    ("A", "patches/8.x/shared.patch")], self.root,
                                   before="patches: []\n")

    def test_inherited_family_cannot_be_automatically_modified(self):
        with self.assertRaisesRegex(ValueError, "inherited/shared YAML"):
            scope.validate_changes("8.1", [("M", "ffmpeg/8.1.yaml")], self.root)

    def test_new_patch_must_be_under_target_major_family(self):
        with self.assertRaisesRegex(ValueError, "major family"):
            scope.validate_changes("8.1.1", [("M", "ffmpeg/8.1.1.yaml"),
                                            ("A", "patches/7.x/new.patch")], self.root)

    def test_target_is_mandatory_and_path_traversal_denied(self):
        for version in ("", "../base", "8.1.1/other", "8.*", "BASE.yaml"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                version_name(version)

    def test_rename_and_symlink_rejected(self):
        with self.assertRaises(ValueError):
            scope.validate_changes("8.1.1", [("R100", "ffmpeg/8.1.1.yaml")],
                                   self.root)
        patch = self.root / "patches" / "8.x" / "exclusive.patch"
        patch.unlink()
        try:
            patch.symlink_to(self.root / "ffmpeg" / "8.1.2.yaml")
        except OSError:
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(ValueError):
            scope.validate_changes("8.1.1",
                                   [("M", "ffmpeg/8.1.1.yaml"),
                                    ("A", "patches/8.x/exclusive.patch")], self.root,
                                   before="patches: []\n")


class LedgerTests(unittest.TestCase):
    def test_incident_key_and_single_active_branch(self):
        branch = ledger.branch_name("8.1.1", SIG)
        self.assertTrue(branch.startswith("autoheal/8.1.1/"))
        self.assertEqual(branch, ledger.branch_name("8.1.1", SIG))
        self.assertNotEqual(branch, ledger.branch_name("7.1", SIG))

    def test_max_round_limit(self):
        self.assertEqual(1, ledger.next_round(0))
        self.assertEqual(2, ledger.next_round(1))
        for count in (-1, 2, 3):
            with self.assertRaises(ValueError):
                ledger.next_round(count)


class BodySynchronizationTests(unittest.TestCase):
    def setUp(self):
        self._repo_env = mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "System233/ffmpeg-msvc-prebuilt"})
        self._repo_env.start()
        self.addCleanup(self._repo_env.stop)
        self.row = plan_row()
        self.report = triage.analyze(run_data(), 1, [job(self.row)],
                                     [artifact(self.row)], {"jobs": [self.row]},
                                     logs={artifact(self.row)["name"]: SOURCE_LOG})
        self.report["pr"] = {"number": 42, "head": "autoheal/8.1.1/fix",
                             "head_sha": SHA, "author": "ffmpeg-dev[bot]"}

    def test_body_includes_actual_changes_run_and_failed_abi(self):
        from ffbuild.autoheal import pr_history
        item = ledger.RepairRound(1, SHA, SIG, 12345, 1,
                                  ("ffmpeg/8.1.1.yaml",), "Windows build fix")
        body = pr_history.render_history([item], [], report=self.report)
        self.assertIn("ffmpeg/8.1.1.yaml", body)
        self.assertNotIn(ABI, body)
        self.assertIn("12345", body)
        self.assertIn("Pending", body)

    def test_root_cause_is_labeled_unverified_until_real_ci(self):
        from ffbuild.autoheal import pr_history
        item = ledger.RepairRound(1, SHA, SIG, 12345, 1,
                                  ("ffmpeg/8.1.1.yaml",),
                                  "Missing Windows linkage macro")
        body = pr_history.render_history([item], [])
        self.assertIn("Missing Windows linkage macro", body)
        self.assertIn("hypotheses remain unverified", body)
        self.assertIn("Required CI", body)

    def test_replace_managed_section_without_erasing_human_notes(self):
        from ffbuild.autoheal import pr_history
        first_record = ledger.RepairRound(1, SHA, SIG, 12345, 1,
                                          ("ffmpeg/8.1.1.yaml",), "Fix first error")
        next_record = ledger.RepairRound(2, "d" * 40, SIG, 12346, 1,
                                         ("ffmpeg/8.1.1.yaml", "patches/8.x/new.patch"),
                                         "Fix second error")
        first = pr_history.render_history([first_record], [], status="第一轮")
        changed = pr_history.render_history([first_record, next_record], [],
                                            status="第二轮")
        original = "Maintainer note\n\n" + first + "\n\nManual checklist"
        result = delivery.update_body(original, changed)
        self.assertIn("Maintainer note", result)
        self.assertIn("Manual checklist", result)
        self.assertIn("第二轮", result)
        self.assertIn("| 1 |", result)
        self.assertIn("| 2 |", result)
        self.assertIn("Fix first error", result)
        self.assertEqual(1, result.count(delivery.START))

    def test_refuse_override_unmarked_human_body(self):
        with self.assertRaises(ValueError):
            delivery.update_body("human wrote this", "replacement")

    def test_pr_status_sync_updates_body_and_comment(self):
        from ffbuild.autoheal import pr_history
        item = ledger.RepairRound(1, SHA, SIG, 12345, 1,
                                  ("ffmpeg/8.1.1.yaml",), "Test source fix")
        event = ledger.RepairEvent("ci", 1, SHA, SIG, 12345, 1, "success")
        managed = pr_history.render_history(
            [item], [pr_history.event_for_round(item), event],
            status="CI passed; complete matrix verification not established.")
        body = delivery.update_body("Manual text\n" +
                                    pr_history.render_history([item], []),
                                    managed)
        self.assertIn("CI passed", body)
        self.assertIn("Manual text", body)
        self.assertIn("| 1 |", body)

    def test_pr_status_sync_is_idempotent(self):
        from ffbuild.autoheal import pr_history
        item = ledger.RepairRound(1, SHA, SIG, 12345, 1,
                                  ("ffmpeg/8.1.1.yaml",), "Test source fix")
        event = ledger.RepairEvent("ci", 1, SHA, SIG, 12345, 1, "success")
        managed = pr_history.render_history([item], [
            pr_history.event_for_round(item), event])
        self.assertEqual(managed, delivery.update_body(managed, managed))


class TrustAndContractTests(unittest.TestCase):
    def test_unknown_or_fork_pr_is_never_trusted(self):
        pr = {"user": {"login": "ffmpeg-dev[bot]"},
              "head": {"ref": "autoheal/8.1.1/abc",
                       "repo": {"full_name": "outsider/fork"}},
              "base": {"ref": "main"}}
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"}):
            self.assertFalse(github.has_trusted_pr(pr))
            pr["head"]["repo"]["full_name"] = "owner/repo"
            self.assertTrue(github.has_trusted_pr(pr))
            pr["user"]["login"] = "human"
            self.assertFalse(github.has_trusted_pr(pr))

    def test_validation_rejects_forged_or_missing_target(self):
        row = plan_row()
        report = triage.analyze(run_data(), 1, [job(row)], [artifact(row)],
                                {"jobs": [row]}, logs={artifact(row)["name"]: SOURCE_LOG})
        self.assertEqual("8.1.1", validate_triage(report, "8.1.1").yaml)
        with self.assertRaises(ValueError):
            validate_triage(report, "8.1.2")
        report["groups"][0]["repairable"] = False
        with self.assertRaises(ValueError):
            validate_triage(report, "8.1.1")

    def test_delivery_refuses_missing_or_corrupted_patch_pre_credentials(self):
        row = plan_row()
        report = triage.analyze(run_data(), 1, [job(row)], [artifact(row)],
                                {"jobs": [row]}, logs={artifact(row)["name"]: SOURCE_LOG})
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaisesRegex(ValueError, "missing"):
                delivery.deliver(report, "8.1.1", directory)
            (directory / "manifest.json").write_text(json.dumps({"schema": 1}))
            (directory / "repair.patch").write_bytes(b"not a patch")
            with self.assertRaisesRegex(ValueError, "Empty"):
                delivery.deliver(report, "8.1.1", directory)


class WorkflowWiringTests(unittest.TestCase):
    def test_workflow_uses_post_run_triage_and_separate_writer(self):
        root = Path(__file__).resolve().parents[1]
        wf = yaml.load((root / ".github/workflows/auto-heal.yml").read_text(encoding="utf-8"),
                       Loader=yaml.BaseLoader)
        self.assertIn("workflow_run", wf["on"])
        self.assertIn("workflow_dispatch", wf["on"])
        self.assertIn("triage", wf["jobs"])
        self.assertIn("repair", wf["jobs"])
        self.assertIn("deliver", wf["jobs"])
        self.assertIn("sync-pr", wf["jobs"])
        agent_steps = str(wf["jobs"]["repair"]["steps"])
        self.assertNotIn("permission-contents: write", agent_steps)
        self.assertIn("permission-contents", str(wf["jobs"]["deliver"]["steps"]))
        self.assertNotIn("trigger-auto-heal",
                         (root / ".github/workflows/build-release.yml").read_text(encoding="utf-8"))


class BotContinuationTests(unittest.TestCase):
    """One bot PR remains the single incident ledger across CI repair rounds."""

    def _simulate(self, round_no: int, *, stale: bool = False,
                  tampered_trailer: bool = False):
        row = plan_row()
        source = {**run_data(), "event": "pull_request", "run_attempt": 1,
                  "status": "completed"}
        branch = ledger.branch_name("8.1.1", SIG)
        original = triage.analyze(source, 1, [job(row)], [artifact(row)], {"jobs": [row]},
                                  logs={artifact(row)["name"]: SOURCE_LOG})
        from ffbuild.autoheal import pr_history
        body = (pr_history.START + "\n"
                + f"**Repair round:** {round_no}/2\n"
                + f"<!-- ffbuild-autoheal-incident:v1 {SIG} -->\n"
                + pr_history.END)
        pr = {
            "number": 42, "user": {"login": "ffmpeg-dev[bot]"}, "body": body,
            "labels": [{"name": "version:8.1.1"}],
            "head": {"ref": branch, "sha": "b" * 40 if stale else SHA,
                     "repo": {"full_name": "System233/ffmpeg-msvc-prebuilt"}},
            "base": {"ref": "main"},
        }
        def fake_api(path):
            if "/commits/" in path:
                actual = round_no + (1 if tampered_trailer else 0)
                return {"commit": {"message": f"Autoheal-Round: {actual}\n"
                                              f"Autoheal-Incident: {SIG}"}}
            return {"run_started_at": "2026-11-23T01:00:00Z"}

        actual_round = round_no + (1 if tampered_trailer else 0)
        previous = []
        if actual_round == 2:
            previous.append(ledger.RepairRound(
                1, "d" * 40, SIG, 12344, 1, ("ffmpeg/8.1.1.yaml",)))
        previous.append(ledger.RepairRound(
            actual_round, pr["head"]["sha"], SIG, 12345, 1,
            ("ffmpeg/8.1.1.yaml",)))
        with mock.patch.dict("os.environ", {
            "GITHUB_REPOSITORY": "System233/ffmpeg-msvc-prebuilt",
        }), mock.patch("ffbuild.autoheal.github.run_data",
                      return_value=(source, 1, [job(row)], [artifact(row)])), \
             mock.patch("ffbuild.autoheal.github.api", side_effect=fake_api), \
             mock.patch("ffbuild.autoheal.github.pr_for_run", return_value=pr), \
             mock.patch("ffbuild.autoheal.pr_history.load_rounds",
                        return_value=previous), \
             mock.patch("ffbuild.autoheal.triage._plan_from_artifact",
                        return_value={"jobs": [row]}), \
             mock.patch("ffbuild.autoheal.triage._sample_log", return_value=SOURCE_LOG):
            return triage.triage_run(12345, 1)

    def test_second_round_reuses_bot_branch_and_original_signature(self):
        report = self._simulate(1)
        self.assertTrue(report["trusted_repair_source"])
        self.assertEqual(1, len(report["repair_matrix"]))
        self.assertEqual(SIG, report["groups"][0]["signature"])
        self.assertEqual(ledger.branch_name("8.1.1", SIG),
                         report["repair_matrix"][0]["branch"])

    def test_round_budget_blocks_third_attempt(self):
        report = self._simulate(2)
        self.assertEqual([], report["repair_matrix"])

    def test_commit_round_allows_repair_after_stale_body_is_recovered(self):
        report = self._simulate(0, tampered_trailer=True)
        self.assertTrue(report["trusted_repair_source"])
        self.assertTrue(report["pr_body_out_of_sync"])
        self.assertEqual(1, len(report["repair_matrix"]))

    def test_pr_body_round_is_reconciled_from_authoritative_bot_commit(self):
        result = self._simulate(1, tampered_trailer=True)
        self.assertTrue(result["trusted_repair_source"])
        self.assertTrue(result["pr_body_out_of_sync"])
        self.assertEqual([], result["repair_matrix"])  # commit already at round 2

    def test_old_ci_run_cannot_modify_newer_bot_pr(self):
        report = self._simulate(1, stale=True)
        self.assertFalse(report["trusted_repair_source"])
        self.assertEqual([], report["repair_matrix"])


class PatchReplayTests(unittest.TestCase):
    def test_email_patch_is_staged_without_executing_source(self):
        import subprocess

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ffmpeg").mkdir()
            (root / "patches" / "8.x").mkdir(parents=True)
            config = root / "ffmpeg" / "8.1.1.yaml"
            config.write_text("patches: []\n", encoding="utf-8")

            def git(*arguments):
                return subprocess.run(["git", *arguments], cwd=root,
                                      capture_output=True, check=True).stdout

            git("init", "-q")
            git("add", "--all")
            git("-c", "user.name=test", "-c", "user.email=test@example.com",
                "commit", "-qm", "baseline")
            config.write_text("patches:\n - 8.x/new.patch\n", encoding="utf-8")
            (root / "patches" / "8.x" / "new.patch").write_text(
                "diff --git a/source.c b/source.c\n", encoding="utf-8")
            git("add", "--all")
            git("-c", "user.name=test", "-c", "user.email=test@example.com",
                "commit", "-qm", "fix")
            source_patch = git("format-patch", "-1", "--stdout")
            git("checkout", "-q", "HEAD~1")
            candidate = root / "candidate.mbox"
            candidate.write_bytes(source_patch)
            git("apply", "--index", "--check", str(candidate))
            git("apply", "--index", str(candidate))
            delta = delivery.changes(root)
            self.assertEqual(["ffmpeg/8.1.1.yaml", "patches/8.x/new.patch"],
                             scope.validate_changes("8.1.1", delta, root,
                                                    before="patches: []\n"))



class CurrentTargetPolicy(unittest.TestCase):
    def test_legacy_package_names_are_not_repairable(self):
        from ffbuild.autoheal.policy import classify
        job={"name":"ffbuild-fixture","conclusion":"failure",
             "steps":[{"name":"Build and test via native vcpkg","conclusion":"failure"}]}
        for package in ("ffmpeg-master","ffmpeg-8-1-3","zlib"):
            self.assertEqual(("build","external_dependency",False),
                classify(job,f"error: building {package}:x64-windows failed\nlibavcodec/foo.c error"))
        for package in ("ffmpeg","ffmpeg-tester"):
            self.assertEqual(("build","source_patch",True),
                classify(job,f"error: building {package}:x64-windows failed\nlibavcodec/foo.c error"))


if __name__ == "__main__":
    unittest.main()
