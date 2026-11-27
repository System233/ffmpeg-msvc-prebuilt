"""Policy regressions: diagnostics are eligible, candidates remain untrusted."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ffbuild.autoheal import delivery, policy, repair, triage
from ffbuild.autoheal.ledger import MAX_REPAIR_ROUNDS, next_round
from test_autoheal import artifact, job, plan_row, run_data, SOURCE_LOG, SHA


def failed_patch(root, line=7816, index="001", patch="0068-dependencies-master.patch"):
    return (f"-- Applying patch {root}/000-0003-fix-windowsinclude.patch\n"
            f"-- Applying patch {root}/{index}-{patch}\n"
            "CMake Error: Applying patch failed: Checking patch configure...\n"
            f"Hunk #1 succeeded at {line - 32} (offset 65 lines).\n"
            f"error: patch failed: configure:{line}\n"
            "error: configure: patch does not apply\n")


class DiagnosisPolicy(unittest.TestCase):
    def test_patch_context_and_cross_arch_identity(self):
        a = failed_patch("D:/a/_work/ffmpeg-master/patches")
        b = failed_patch("C:/runner/other/patches", 7982, "004")
        self.assertEqual(("build", "source_patch", True), policy.classify(job(plan_row()), a))
        self.assertEqual("patch:0068-dependencies-master.patch", policy.patch_failure_key(a))
        self.assertEqual(policy.patch_failure_key(a), policy.patch_failure_key(b))
        self.assertEqual(triage._signature("build", "source_patch", a, "build"),
                         triage._signature("build", "source_patch", b, "build"))
        c = failed_patch("D:/a", patch="0069-lensfun-configure-fix-master.patch")
        self.assertNotEqual(policy.patch_failure_key(a), policy.patch_failure_key(c))
        # stderr is sampled before stdout, including a repeated diagnostic.
        self.assertEqual(policy.patch_failure_key(a),
                         policy.patch_failure_key("error: patch failed: configure:7816\n" + a))

    def test_unknown_diagnostics_allowed_not_just_source_filenames(self):
        for log in (
            "ERROR: amf requested but not found",
            "configure: unknown option --enable-old-option",
            "LINK : fatal error LNK1120: 1 unresolved externals",
            "consumer tester failed to resolve an exported symbol",
            "error: building ffmpeg:arm64-windows failed with: BUILD_FAILED",
            "error: building ffmpeg-tester:arm64-windows failed with: BUILD_FAILED",
            "fatal error C1083: Cannot open include file: 'runner.h'",
            "artifact_count = 0; error C2065: undeclared identifier",
            "timeout was not declared in this scope",
            "Cache miss for optional debug package\nERROR: configure option unsupported",
        ):
            with self.subTest(log=log):
                self.assertTrue(policy.classify(job(plan_row()), log)[2])
        self.assertEqual(("build", "diagnosis_required", True),
                         policy.classify(job(plan_row()), "ERROR: configure option unsupported"))

    def test_explicit_infrastructure_and_external_dependency_still_blocked(self):
        for log in (
            "error: cache miss, runner returned HTTP 503",
            "fatal: unable to access: Could not resolve host",
            "Error: artifact expired",
            "connection reset",
            "error: no space left on device",
            "error: building openssl:arm64-windows failed with: BUILD_FAILED",
            "error: building libvpx[core]:x64-windows failed with: BUILD_FAILED",
            "error: building openssl:arm64-windows failed with: BUILD_FAILED\n" + SOURCE_LOG,
            "",
            "   \n",
        ):
            with self.subTest(log=log):
                self.assertFalse(policy.classify(job(plan_row()), log)[2])
        row = plan_row()
        self.assertFalse(policy.classify(job(row, conclusion="timed_out"), SOURCE_LOG)[2])
        self.assertFalse(policy.classify(job(row, step="Verify and package installed vcpkg result"), SOURCE_LOG)[2])
        j = job(row)
        j["steps"].append({"name": "Unrecognized failed cleanup", "conclusion": "failure"})
        self.assertFalse(policy.classify(j, SOURCE_LOG)[2])

    def test_sixteen_workers_same_patch_one_stable_incident(self):
        rows = [plan_row("master", f"variant-{i}", triplet)
                for i, triplet in enumerate(
                    ["x86-windows", "x64-windows", "arm-windows", "arm64-windows"] * 4)]
        logs = {artifact(r)["name"]: failed_patch(f"D:/runner-{i}/patches", 7816+i)
                for i, r in enumerate(rows)}
        report = triage.analyze(run_data(), 1, [job(r) for r in rows],
                                [artifact(r) for r in rows], {"jobs": rows}, logs=logs)
        g = report["groups"][0]
        self.assertTrue(g["repairable"])
        self.assertEqual("source_patch", g["classification"])
        self.assertEqual(1, len({j["signature"] for j in g["jobs"]}))
        self.assertEqual(16, len(g["jobs"]))
        single = triage.analyze(run_data(), 1, [job(rows[0])], [artifact(rows[0])],
                                {"jobs": rows[:1]}, logs=logs)
        self.assertEqual(g["signature"], single["groups"][0]["signature"])

    def test_multiple_diagnostics_order_independent_and_missing_evidence_blocks(self):
        rows = [plan_row("master", "left"), plan_row("master", "right")]
        logs = {artifact(rows[0])["name"]: failed_patch("D:/a"),
                artifact(rows[1])["name"]: "ERROR: configure option unsupported"}
        def analyze(order, evidence):
            return triage.analyze(run_data(), 1, [job(r) for r in order],
                                  [artifact(r) for r in order], {"jobs": order}, logs=evidence)["groups"][0]
        g = analyze(rows, logs)
        self.assertTrue(g["repairable"])
        self.assertEqual("multiple_build_diagnostics", g["classification"])
        self.assertEqual(g["signature"], analyze(rows[::-1], logs)["signature"])
        self.assertFalse(analyze(rows, {artifact(rows[0])["name"]: logs[artifact(rows[0])["name"]]})["repairable"])
        self.assertFalse(analyze(rows, dict(logs, **{artifact(rows[1])["name"]: "error: building openssl:arm-windows failed"}))["repairable"])


class RepairEvidenceContract(unittest.TestCase):
    def test_context_contains_exact_matched_native_plan_rows(self):
        import hashlib
        from ffbuild.native_abi import build_requests
        from ffbuild.identity import variant_name

        pin = {"ref": "n9.2-dev-1234-gabcdef0", "commit": "a"*40, "sha512": "b"*128}
        for target in ("9.1", "master"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                rows, blocked = build_requests(version=target, snapshot=pin if target == "master" else None,
                                               release_date="2026-11-26")
                self.assertFalse(blocked)
                self.assertEqual(16, len(rows))
                # Use real request expansion and synthetic ABI values; no build or native scan.
                rows = [rows[0], rows[-1]]
                for i, row in enumerate(rows):
                    row["abi_hash"] = hashlib.sha256(str(i).encode()).hexdigest()
                    row["id"] = variant_name(row["version"], 0, row["triplet"],
                                             row["linkage"], row["license"], abi_hash=row["abi_hash"])
                    row["unrelated_field"] = "must not be propagated"
                jobs = [job(row) for row in rows]
                for i, entry in enumerate(jobs):
                    entry["id"] = 1000 + i
                report = triage.analyze(run_data(), 1, jobs, [artifact(r) for r in rows],
                                        {"jobs": rows}, logs={artifact(r)["name"]: SOURCE_LOG for r in rows})
                self.assertTrue(report["groups"][0]["repairable"])
                if target == "master":
                    report["source"]["request"] = pin
                report["trusted_repair_source"] = True
                expected = {r["id"]: {k: v for k, v in r.items() if k != "unrelated_field"} for r in rows}
                old = Path.cwd()
                os.chdir(temporary)
                try:
                    Path("fix_report.md").write_text("Decision: no_safe_fix\nRoot cause: test only\n", encoding="utf-8")
                    def fake_git(*args):
                        return SHA if args[:2] == ("rev-parse", "HEAD") else ""
                    def inspect_context(*args, **kwargs):
                        context = json.loads(Path("agent_context.json").read_text(encoding="utf-8"))
                        self.assertEqual(target, context["target_yaml"])
                        self.assertEqual(SHA, context["base_sha"])
                        self.assertEqual([1000, 1001], context["failed_jobs"])
                        self.assertEqual(pin if target == "master" else {}, context["source_snapshot"])
                        self.assertEqual(2, len(context["diagnostics"]))
                        for d in context["diagnostics"]:
                            row = expected[d["variant_id"]]
                            self.assertEqual(row, d["build_plan"])
                            self.assertEqual(row["triplet"], d["triplet"])
                            self.assertEqual(row["abi_hash"], d["abi_hash"])
                            self.assertEqual(artifact(row)["name"], d["artifact"])
                            self.assertEqual("error_logs/" + d["artifact"], d["log_directory"])
                            self.assertEqual(["Build and test via native vcpkg"], d["failed_steps"])
                            self.assertEqual("build", d["phase"])
                            if target != "master":
                                self.assertEqual("", d["build_plan"]["source_ref"])
                                self.assertEqual("", d["build_plan"]["sha512"])
                        self.assertEqual("master" if target == "master" else "9.1",
                                         kwargs["env"]["FFBUILD_REPAIR_TARGET"])
                        return mock.Mock(returncode=3)
                    with mock.patch.object(repair, "_git", side_effect=fake_git), \
                         mock.patch.object(repair.github, "download_artifact") as download, \
                         mock.patch.object(repair.subprocess, "run", side_effect=inspect_context), \
                         mock.patch.object(repair, "require_ready"), mock.patch.object(repair, "check_worktree") as check:
                        repair.prepare_context(report, target)
                        repair.repair(report, target, Path("out"))
                        self.assertEqual(2, download.call_count)
                        check.assert_not_called()
                        self.assertFalse(Path("out/repair.patch").exists())
                finally:
                    os.chdir(old)


class DeclineContract(unittest.TestCase):
    def setUp(self):
        row = plan_row("master")
        self.report = triage.analyze(run_data(), 1, [job(row)], [artifact(row)],
                                     {"jobs": [row]}, logs={artifact(row)["name"]: "configure: unsupported option"})
        self.report["trusted_repair_source"] = True
        self.identity = {"schema": 1, "decision": "no_safe_fix", "yaml": "master",
                         "signature": self.report["groups"][0]["signature"],
                         "run_id": self.report["source"]["run_id"],
                         "run_attempt": 1, "base_sha": SHA}

    def test_decline_never_uses_privileged_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "manifest.json").write_text(json.dumps(self.identity), encoding="utf-8")
            with mock.patch.object(delivery, "run") as run, mock.patch.object(delivery, "git") as git, \
                 mock.patch.object(delivery.github, "api") as api, mock.patch.object(delivery, "find_pr") as pr:
                delivery.deliver(self.report, "master", out)
                for action in (run, git, api, pr):
                    action.assert_not_called()
                (out / "repair.patch").write_bytes(b"unexpected")
                with self.assertRaisesRegex(ValueError, "Invalid safe-decline"):
                    delivery.deliver(self.report, "master", out)
                (out / "repair.patch").unlink()
                (out / "manifest.json").write_text(json.dumps(dict(self.identity, run_id=999)), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid safe-decline"):
                    delivery.deliver(self.report, "master", out)
                for action in (run, git, api, pr):
                    action.assert_not_called()

    def test_repair_worker_emits_only_decline_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Path.cwd()
            os.chdir(temp)
            try:
                Path("fix_report.md").write_text("Decision: no_safe_fix\nRoot cause: needs third-party Port change\n", encoding="utf-8")
                def git(*args):
                    if args[:2] == ("rev-parse", "HEAD"):
                        return SHA
                    return ""
                with mock.patch.object(repair, "_git", side_effect=git), \
                     mock.patch.object(repair.github, "download_artifact"), \
                     mock.patch.object(repair.subprocess, "run", return_value=mock.Mock(returncode=3)), \
                     mock.patch.object(repair, "require_ready"), mock.patch.object(repair, "check_worktree") as scope:
                    out = Path("out")
                    repair.repair(self.report, "master", out)
                    self.assertEqual(self.identity, json.loads((out / "manifest.json").read_text(encoding="utf-8")))
                    self.assertTrue((out / "repair-report.md").is_file())
                    self.assertFalse((out / "repair.patch").exists())
                    scope.assert_not_called()
                    # A declaration cannot hide a tracked modification.
                    def dirty(*args):
                        if args[0] == "status":
                            return " M ffmpeg/master.yaml"
                        return git(*args)
                    with mock.patch.object(repair, "_git", side_effect=dirty):
                        with self.assertRaises(ValueError):
                            repair.repair(self.report, "master", Path("invalid"))
            finally:
                os.chdir(old)

    def test_round_budget_unmodified(self):
        self.assertEqual(2, MAX_REPAIR_ROUNDS)
        self.assertEqual(2, next_round(1))
        with self.assertRaises(ValueError):
            next_round(2)


if __name__ == "__main__":
    unittest.main()
