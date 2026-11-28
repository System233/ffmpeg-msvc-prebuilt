"""Pi supervisor regressions: real Git, simulated agent and native build."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from ffbuild.autoheal import runner, build as native

SPEC = "ffmpeg[all-gpl]:x64-windows"
CHECK = {"spec": SPEC, "jobs": [1], "reason": "reproduces failure"}
RESULT = {"spec": SPEC, "abi_hash": "a"*64, "ffmpeg_build": "passed",
          "consumer_compile_link": "passed", "binary_inspection": "passed",
          "tester_targets": {"release": 9, "debug": 9},
          "tester_modules": ["avcodec", "avdevice", "avfilter", "avformat", "avutil", "swresample", "swscale"],
          "tester_cases": {cfg: ["check-avcodec", "check-avdevice", "check-avfilter", "check-avformat", "check-avutil", "check-full", "check-full-cpp", "check-swresample", "check-swscale"] for cfg in ("release", "debug")},
          "runtime": {"status": "passed", "tester_executions": 18, "cli_executions": 2},
          "external_dependency_builds": 0}


class PiConfiguration(unittest.TestCase):
    def test_pinned_entrypoint_and_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cli.js").touch()
            (root / "package.json").write_text(json.dumps({"bin": {"pi": "cli.js"}}))
            with mock.patch.dict(os.environ, {"OPENAI_BASE_URL": "https://example.invalid/v1",
                    "OPENAI_API_KEY": "secret", "OPENAI_MODEL": "test", "GH_TOKEN": "github",
                    "FFBUILD_PI_PACKAGE": str(root)}), mock.patch.object(runner.shutil, "which", return_value="node"):
                command, env = runner.configure_pi(root / "pi")
            self.assertEqual(["node", str(root / "cli.js")], command)
            self.assertNotIn("GH_TOKEN", env)
            provider = json.loads((root / "pi/models.json").read_text())["providers"]["autoheal"]
            self.assertEqual("$OPENAI_API_KEY", provider["apiKey"])
            self.assertEqual("openai-responses", provider["api"])
            self.assertEqual("test", provider["models"][0]["id"])

    def test_missing_config(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                runner.configure_pi(Path(tmp))


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = Path.cwd()
        self.addCleanup(os.chdir, old)
        os.chdir(self.tmp.name)
        runner.git("init", "-q")
        runner.git("config", "user.name", "Test")
        runner.git("config", "user.email", "test@example.invalid")
        runner.git("config", "commit.gpgsign", "false")
        self.target = Path("ffmpeg/8.1.1.yaml")
        self.target.parent.mkdir()
        self.target.write_text("original\n")
        prompt = Path("scripts/ffbuild/autoheal/prompts/repair.md")
        prompt.parent.mkdir(parents=True)
        prompt.write_text("repair")
        runner.git("add", ".")
        runner.git("commit", "-qm", "baseline")
        self.base = runner.git("rev-parse", "HEAD")
        self.data = {"base_sha": self.base, "target_yaml": "8.1.1",
                     "diagnostics": [{"job_id": 1, "build_plan":
                         {"triplet": "x64-windows", "license": "gpl", "linkage": "shared"}}]}
        self.directory = Path.cwd() / "runtime"
        for obj, name, value in [(native, "context", self.data), (native, "runtime_dir", self.directory),
                                 (runner, "configure_pi", (["pi"], {}))]:
            patch = mock.patch.object(obj, name, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(runner, "check_worktree", side_effect=self.scope)
        patch.start()
        self.addCleanup(patch.stop)

    def scope(self, *args, **kwargs):
        changed = runner.git("diff", "--name-only", self.base)
        if not changed:
            if kwargs.get("allow_empty"):
                return []
            raise ValueError("no candidate")
        if changed != self.target.as_posix():
            raise ValueError("out of scope")
        return [changed]

    def candidate(self, *args, **kwargs):
        self.target.write_text("fixed\n")
        Path("fix_report.md").write_text("Decision: candidate\nTitle: fix(8.1.1): preserve Windows macro\nRoot cause: compile error\nRepair rationale: restore the missing macro\n")
        Path("validation-plan.json").write_text(json.dumps({"checks": [CHECK]}))
        return 0

    def test_success_commits_verified_tree_only(self):
        def build(*args, **kwargs):
            self.assertEqual(self.base, runner.git("rev-parse", "HEAD"))
            self.assertTrue(kwargs["clean"])
            return RESULT
        with mock.patch.object(runner, "run_pi", side_effect=self.candidate), mock.patch.object(native, "build", side_effect=build) as worker:
            self.assertEqual(0, runner.supervise(budget=30))
        worker.assert_called_once_with(SPEC, clean=True)
        evidence = json.loads((self.directory / "verification.json").read_text())
        self.assertEqual(runner.git("rev-parse", "HEAD^{tree}"), evidence["tree"])
        self.assertEqual(runner.git("rev-parse", "HEAD"), evidence["candidate"])
        self.assertEqual("1", runner.git("rev-list", "--count", self.base+"..HEAD"))
        self.assertEqual("fix(8.1.1): preserve Windows macro", runner.git("show", "-s", "--format=%s", "HEAD"))

    def test_report_missing_rationale_never_builds_or_commits(self):
        def incomplete(*args, **kwargs):
            self.candidate()
            Path("fix_report.md").write_text("Decision: candidate\nTitle: fix(8.1.1): restore macro\nRoot cause: compile error\n")
            return 0
        with mock.patch.object(runner, "run_pi", side_effect=[0, 1, 1, 1]) as pi, mock.patch.object(native, "build") as worker:
            def first(*args, **kwargs):
                return incomplete() if pi.call_count == 1 else 1
            pi.side_effect = first
            self.assertEqual(6, runner.supervise(budget=30))
        worker.assert_not_called()
        self.assertEqual(self.base, runner.git("rev-parse", "HEAD"))
        self.assertFalse((self.directory / "verification.json").exists())

    def test_failed_build_resumes_same_session(self):
        with mock.patch.object(runner, "run_pi", side_effect=self.candidate) as pi, mock.patch.object(native, "build", side_effect=[native.BuildFailure("compile"), RESULT]):
            self.assertEqual(0, runner.supervise(budget=30))
        self.assertEqual(2, pi.call_count)
        self.assertFalse(pi.call_args_list[0].kwargs["resume"])
        self.assertTrue(pi.call_args_list[1].kwargs["resume"])
        self.assertIn("compile", pi.call_args_list[1].args[2])

    def test_environment_failure_does_not_commit(self):
        with mock.patch.object(runner, "run_pi", side_effect=self.candidate), mock.patch.object(native, "build", side_effect=native.EnvironmentFailure("cache")):
            self.assertEqual(5, runner.supervise(budget=30))
        self.assertEqual(self.base, runner.git("rev-parse", "HEAD"))
        self.assertFalse((self.directory / "verification.json").exists())

    def test_decline_no_build_or_commit(self):
        Path("fix_report.md").write_text("Decision: no_safe_fix\nRoot cause: unknown\n")
        with mock.patch.object(runner, "run_pi", return_value=0), mock.patch.object(native, "build") as worker:
            self.assertEqual(3, runner.supervise(budget=30))
        worker.assert_not_called()
        self.assertEqual(self.base, runner.git("rev-parse", "HEAD"))

    def test_agent_failure_is_bounded(self):
        with mock.patch.object(runner, "run_pi", return_value=1) as pi, mock.patch.object(native, "build") as worker:
            self.assertEqual(6, runner.supervise(budget=30))
        self.assertEqual(3, pi.call_count)
        worker.assert_not_called()

    def test_unverified_evidence_cannot_commit(self):
        with mock.patch.object(runner, "run_pi", side_effect=[0, 1, 1, 1]) as pi, mock.patch.object(native, "build", return_value=dict(RESULT, consumer_compile_link="failed")):
            def first(*args, **kwargs):
                return self.candidate() if pi.call_count == 1 else 1
            pi.side_effect = first
            self.assertEqual(6, runner.supervise(budget=30))
        self.assertEqual(self.base, runner.git("rev-parse", "HEAD"))
        self.assertFalse((self.directory / "verification.json").exists())
