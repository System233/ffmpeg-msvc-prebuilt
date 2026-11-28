"""Failure-injection simulations for the FFmpeg Auto-Heal control plane.

All tests are offline. No vcpkg, compiler, GitHub API or PR is invoked.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_autoheal_native import consumer_evidence
from ffbuild.autoheal import delivery, ledger, triage

SHA = "a" * 40
SIG = "b" * 64
ABI = "c" * 64
REPO = "simulated/example"


def row(variant: str) -> dict:
    return {"yaml": "8.1.1", "id": variant, "triplet": "x64-windows",
            "abi_hash": ABI, "package": "ffmpeg[all-gpl]", "port": "ffmpeg", "tester_port": "ffmpeg-tester", "license": "gpl", "linkage": "shared"}


def failed_job(variant: str) -> dict:
    return {"id": len(variant) + 1, "name": "Build / ffbuild-" + variant,
            "conclusion": "failure",
            "steps": [{"name": "Build and test via native vcpkg", "conclusion": "failure"}]}


def artifact(variant: str) -> dict:
    return {"name": "build-logs-a1-8.1.1-" + variant, "expired": False}


def source() -> dict:
    return {"id": 1234, "name": "Build All FFmpeg Versions",
            "head_sha": SHA, "head_branch": "main", "run_attempt": 1,
            "conclusion": "failure", "event": "pull_request",
            "html_url": "https://github.com/simulated/example/actions/runs/1234"}


def report() -> dict:
    v = row("v1")
    value = triage.analyze(source(), 1, [failed_job("v1")],
                           [artifact("v1")], {"jobs": [v]},
                           logs={artifact("v1")["name"]:
                                 "libavcodec/worker.c:21: error C2065: missing symbol\n"})
    value["pr"] = {"number": 4, "head": ledger.branch_name("8.1.1", SIG),
                   "author": "ffmpeg-dev[bot]", "head_sha": SHA}
    return value


class SimulatedSafetyCases(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO, "GITHUB_RUN_ID": "4321", "GITHUB_RUN_ATTEMPT": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_different_source_failures_same_version_do_not_claim_one_root_cause(self):
        left, right = row("v1"), row("v2")
        logs = {artifact("v1")["name"]:
                "libavcodec/decode.c:44: error C2065: missing codec field\n",
                artifact("v2")["name"]:
                "libavfilter/unrelated.c:15: error C1083: missing include\n"}
        value = triage.analyze(source(), 1, [failed_job("v1"), failed_job("v2")],
                               [artifact("v1"), artifact("v2")],
                               {"jobs": [left, right]}, logs=logs)
        self.assertEqual(1, len(value["groups"]))
        group = value["groups"][0]
        self.assertTrue(group["repairable"], "Distinct source diagnostics permit bounded diagnosis")
        self.assertEqual("multiple_build_diagnostics", group["classification"])
        self.assertEqual(2, len({j["signature"] for j in group["jobs"]}))

    def test_closed_historical_pr_can_start_new_occurrence(self):
        value = source()
        value.update({"event": "workflow_dispatch", "name": "Build FFmpeg Release", "head_branch": "main", "status": "completed"})
        def fake_api(path):
            if "/pulls?state=open" in path:
                return []
            if "/pulls?head=" in path:
                return [{"state": "closed", "number": 8}] if "-r1234" not in path else []
            return {"run_started_at": "2026-11-23T01:00:00Z"}
        v = dict(row("v1"), release_date="2026-11-25")
        request = {"yaml":"8.1.1", "date":"2026-11-25", "production":True,
                   "repository_commit":SHA, "ref":"", "commit":"", "sha512":""}
        with mock.patch.object(triage.github, "run_data",
                               return_value=(value, 1, [failed_job("v1")],
                                             [artifact("v1")])), \
             mock.patch.object(triage.github, "api", side_effect=fake_api), \
             mock.patch.object(triage, "_plan_from_artifact",
                               return_value={"jobs": [v], "request":request}), \
             mock.patch.object(triage, "_sample_log",
                               return_value="libavcodec/source.c:11: error C2065: bad symbol"):
            report = triage.triage_run(1234)
        self.assertTrue(report["trusted_repair_source"])
        self.assertEqual(1, len(report["repair_matrix"]))
        self.assertTrue(report["repair_matrix"][0]["branch"].endswith("-r1234"))

    def test_untrusted_log_cannot_inject_managed_pr_end_marker(self):
        value = report()
        value["groups"][0]["jobs"][0]["diagnostic"] = (
            "libavcodec/code.c:11: error " + delivery.END)
        from ffbuild.autoheal import pr_history
        item = ledger.RepairRound(1, SHA, SIG, 1234, 1, ("ffmpeg/8.1.1.yaml",))
        body = pr_history.render_history([item], [], report=value)
        self.assertEqual(1, body.count(delivery.START))
        self.assertEqual(1, body.count(delivery.END))
        self.assertEqual(body, delivery.update_body(body, body))

    @mock.patch("ffbuild.autoheal.delivery.post_comment")
    @mock.patch("ffbuild.autoheal.delivery.write_pr_body")
    @mock.patch("ffbuild.autoheal.delivery.github.api")
    def test_reconcile_body_after_commit_pushed_but_description_update_failed(
            self, api, edit, comment):
        from ffbuild.autoheal import pr_history
        from ffbuild.autoheal.ledger import RepairRound
        value = report()
        existing = (pr_history.START + "\n"
                    + f"**Repair round:** 1/2\n<!-- ffbuild-autoheal-incident:v1 {SIG} -->\n"
                    + pr_history.END)
        api.return_value = {"number": 4, "user": {"login": "ffmpeg-dev[bot]"},
                            "head": {"sha": SHA}, "body": "Maintainer note\n\n" + existing}
        recorded = [
            RepairRound(1, "d" * 40, SIG, 1233, 1, ("ffmpeg/8.1.1.yaml",)),
            RepairRound(2, SHA, SIG, 1234, 1, (
                "ffmpeg/8.1.1.yaml", "patches/8.x/new.patch")),
        ]
        with mock.patch.object(pr_history, "load_rounds", return_value=recorded), \
             mock.patch.object(pr_history, "load_events", return_value=[]), \
             mock.patch.object(pr_history, "current_files",
                               return_value=["ffmpeg/8.1.1.yaml",
                                             "patches/8.x/new.patch"]):
            delivery.sync_status(value)
        edit.assert_called_once()
        changed = edit.call_args.args[1]
        self.assertIn("**Repair round:** 2/2", changed)
        self.assertIn("patches/8.x/new.patch", changed)
        self.assertIn("| 1 |", changed)
        self.assertIn("Maintainer note", changed)
        self.assertEqual(1, changed.count(delivery.START))
        self.assertEqual(3, comment.call_count)

    @mock.patch("ffbuild.autoheal.delivery.run", autospec=True)
    @mock.patch("ffbuild.autoheal.delivery.git", autospec=True)
    @mock.patch("ffbuild.autoheal.delivery.github.api")
    @mock.patch("ffbuild.autoheal.delivery.find_pr", return_value=None)
    def test_malformed_orphan_branch_is_not_adopted(self, _find, api, git, run):
        value = report()
        value["pr"] = None
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            candidate = "d" * 40
            patch = f"From {candidate} Mon Sep 17 00:00:00 2001\n\ndiff --git a/x b/x\n".encode()
            import hashlib
            (folder / "repair.patch").write_bytes(patch)
            (folder / "manifest.json").write_text(json.dumps({
                "schema": 2, "yaml": "8.1.1",
                "signature": value["groups"][0]["signature"],
                "run_id": 1234, "run_attempt": 1, "base_sha": SHA,
                "patch_sha256": hashlib.sha256(patch).hexdigest(),
                "paths": ["ffmpeg/8.1.1.yaml"], "subject": "fix(8.1.1): restore declaration",
                "root_cause_hypothesis": "Missing declaration", "repair_rationale": "Restore declaration without removing features",
                "verification_origin": {"kind": "isolated_runner", "run_id": 4321, "run_attempt": 1},
                "validation": {"schema": 1, "candidate": candidate, "tree": "e" * 40,
                    "checks": [{"spec": "ffmpeg[all-gpl]:x64-windows", "jobs": [failed_job("v1")["id"]],
                                "reason": "same diagnostic", "abi_hash": ABI,
                                "ffmpeg_build": "passed", "consumer_compile_link": "passed",
                                "binary_inspection": "passed", "external_dependency_builds": 0,
                                "tester_targets": {"release": 9, "debug": 9},
                                "tester_modules": ["avcodec", "avdevice", "avfilter", "avformat", "avutil", "swresample", "swscale"],
                                "tester_cases": {cfg: ["check-avcodec", "check-avdevice", "check-avfilter", "check-avformat", "check-avutil", "check-full", "check-full-cpp", "check-swresample", "check-swscale"] for cfg in ("release", "debug")},
                                "consumer_cases": consumer_evidence(),
                                "runtime": {"status": "passed", "tester_executions": 18, "cli_executions": 1}}]},
            }), encoding="utf-8")
            from ffbuild.autoheal.audit import candidate_identity
            binding, _, _ = candidate_identity(value, "8.1.1", folder)
            audit_dir = folder / "audit"
            audit_dir.mkdir()
            (audit_dir / "audit.json").write_text(json.dumps({
                "schema": 1, "binding": binding, "model": "test-auditor", "response_id": "resp_test",
                "decision": "approve", "verdict": {"decision": "approve", "summary": "ok", "findings": [], "limitations": []}
            }), encoding="utf-8")
            api.return_value = {"object": {"sha": SHA}}
            git.return_value = "deadbeef\trefs/heads/autoheal/8.1.1/existing"
            with self.assertRaisesRegex(ValueError, "Unexpected remote orphan branch reference"):
                delivery.deliver(value, "8.1.1", folder, audit_output=audit_dir)
            # Authentication and remote lookup are simulated, never executed.
            # Malformed orphan references must fail before fetch or mutation.
            run.assert_called_once_with("gh", "auth", "setup-git")
            git.assert_called_once_with("ls-remote", "origin", f"refs/heads/{ledger.branch_name('8.1.1', value['groups'][0]['signature'])}")


if __name__ == "__main__":
    unittest.main()
