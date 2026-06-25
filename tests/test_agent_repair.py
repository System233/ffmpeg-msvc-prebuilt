"""Tests for scripts/ci/agent_repair.py."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import agent_repair  # noqa: E402

# ── Default argparse namespace ────────────────────────────────────────────────
_DEFAULT_ARGS = argparse.Namespace(
    base_sha=None,
    max_retries=3,
    prompt_file="scripts/ci/agent_prompt.md",
    feedback_file="scripts/ci/agent_feedback.md",
)


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _make_run_side_effect(responses=None):
    """Build a side_effect for subprocess.run.

    ``responses`` is a dict mapping command prefix strings to
    ``(returncode, stdout)`` tuples.  The longest matching prefix wins.
    """
    if responses is None:
        responses = {}

    # Sensible defaults so most tests only override what they need.
    defaults = {
        "git config": (0, ""),
        "git rev-parse": (0, "abc1234567890\n"),
        "git reset --hard": (0, ""),
        "git reset --soft": (0, ""),
        "git log --oneline": (0, "abc1234 fix: something\n"),
        "git log --format=%s": (0, "fix: something\n"),
        "git rev-list --count": (0, "1\n"),
        "git commit": (0, ""),
        "git format-patch": (0, "patch-output/0001-fix.patch\n"),
        "git diff": (0, "ffmpeg/8.1.1.yaml\npatches/8.x/fix.patch\n.opencode/config.json\n"),
    }
    defaults.update(responses)

    def side_effect(args, *, capture_output=True, text=True, check=False, **kwargs):
        cmd_str = " ".join(str(a) for a in args)
        # Try longest key first so e.g. "git log --format=%s" matches before "git log"
        for prefix in sorted(defaults, key=len, reverse=True):
            if cmd_str.startswith(prefix):
                rc, stdout = defaults[prefix]
                result = subprocess.CompletedProcess(args, rc, stdout=stdout, stderr="")
                if check and rc != 0:
                    raise subprocess.CalledProcessError(rc, args, stdout, result.stderr)
                return result
        # Unknown command → success, empty output
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    return side_effect


# ── Test cases ────────────────────────────────────────────────────────────────

class TestAgentRepair(unittest.TestCase):
    """All 10 required test scenarios for agent_repair.py."""

    def setUp(self):
        # Ensure DEEPSEEK_API_KEY is set (most tests need it)
        self._saved_environ = os.environ.copy()
        os.environ["DEEPSEEK_API_KEY"] = "sk-test"
        os.environ.pop("GIT_AUTHOR_NAME", None)
        os.environ.pop("GIT_AUTHOR_EMAIL", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_environ)

    # ── 1. opencode not in PATH → SystemExit ─────────────────────────────────

    @mock.patch("agent_repair.shutil.which", return_value=None)
    @mock.patch("argparse.ArgumentParser.parse_args", return_value=_DEFAULT_ARGS)
    def test_1_opencode_not_in_path(self, _parse_args, _which):
        with self.assertRaises(SystemExit) as ctx:
            agent_repair.main()
        self.assertEqual(ctx.exception.code, 1)

    # ── 2. PROMPT_FILE not found → SystemExit ────────────────────────────────

    @mock.patch.object(Path, "is_file", return_value=False)
    @mock.patch("argparse.ArgumentParser.parse_args", return_value=_DEFAULT_ARGS)
    @mock.patch("agent_repair.shutil.which", return_value="/usr/bin/opencode")
    def test_2_prompt_file_not_found(self, _which, _parse_args, _is_file):
        with self.assertRaises(SystemExit) as ctx:
            agent_repair.main()
        self.assertEqual(ctx.exception.code, 1)

    # ── 3. DEEPSEEK_API_KEY not set → error ──────────────────────────────────

    @mock.patch("argparse.ArgumentParser.parse_args", return_value=_DEFAULT_ARGS)
    def test_3_deepseek_api_key_not_set(self, _parse_args):
        del os.environ["DEEPSEEK_API_KEY"]
        with self.assertRaises(SystemExit) as ctx:
            agent_repair.main()
        self.assertEqual(ctx.exception.code, 1)

    # ── 4. Successful single attempt: opencode succeeds, no violations ───────

    @mock.patch("agent_repair.signal.signal")
    @mock.patch("agent_repair.shutil.copy")
    @mock.patch("argparse.ArgumentParser.parse_args", return_value=_DEFAULT_ARGS)
    @mock.patch("agent_repair.shutil.which", return_value="/usr/bin/opencode")
    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(Path, "exists", return_value=False)
    @mock.patch.object(Path, "glob", return_value=[Path("patch-output/0001-fix.patch")])
    @mock.patch.object(Path, "mkdir")
    @mock.patch.object(Path, "read_text", return_value="prompt content")
    @mock.patch.object(Path, "write_text")
    @mock.patch("agent_repair.subprocess.run")
    def test_4_successful_single_attempt(
        self,
        mock_run,
        _write_text,
        _read_text,
        _mkdir,
        _glob,
        _exists,
        _is_file,
        _which,
        _parse_args,
        _copy,
        _signal,
    ):
        """All checks pass on the first attempt."""
        mock_run.side_effect = _make_run_side_effect()

        try:
            agent_repair.main()
        except SystemExit as e:
            self.fail(f"main() raised SystemExit({e.code}), expected normal return")
        # main() returned normally → exit 0

    # ── 5. Scope violation with retry: first violates, second succeeds ───────

    @mock.patch("agent_repair.signal.signal")
    @mock.patch("argparse.ArgumentParser.parse_args")
    @mock.patch("agent_repair.shutil.which", return_value="/usr/bin/opencode")
    @mock.patch("agent_repair.subprocess.run")
    def test_5_scope_violation_with_retry(
        self,
        mock_run,
        _which,
        mock_parse_args,
        _signal,
    ):
        """First attempt produces violations; second succeeds."""
        # Use a real temp directory so file operations (exists, read_text,
        # write_text) work naturally without fragile Path mocking.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Create real prompt and feedback template files
            prompt_path = tmp / "agent_prompt.md"
            prompt_path.write_text("prompt content", encoding="utf-8")
            feedback_path = tmp / "agent_feedback.md"
            feedback_path.write_text(
                "## Attempt {attempt}\nViolations:\n{violations}\n",
                encoding="utf-8",
            )

            mock_parse_args.return_value = argparse.Namespace(
                base_sha=None,
                max_retries=3,
                prompt_file=str(prompt_path),
                feedback_file=str(feedback_path),
            )

            # git diff: iteration 1 → violations; iteration 2 → clean
            diff_outputs = [
                "scripts/ci/bad.py\nsrc/main.c\n",
                "ffmpeg/8.1.1.yaml\npatches/8.x/fix.patch\n",
            ]
            diff_idx = [0]  # mutable container so closure can mutate it

            def run_se(args, *, capture_output=True, text=True, check=False, **kwargs):
                cmd_str = " ".join(str(a) for a in args)
                if cmd_str.startswith("git diff"):
                    stdout = diff_outputs[diff_idx[0] % len(diff_outputs)]
                    diff_idx[0] += 1
                    return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")
                return _make_run_side_effect()(
                    args, capture_output=capture_output, text=text, check=check, **kwargs
                )

            mock_run.side_effect = run_se

            # We still need to mock glob (patch-output/*.patch) and mkdir
            # because no actual patches are generated.
            with mock.patch.object(Path, "glob", return_value=[tmp / "patch-output" / "0001-fix.patch"]), \
                 mock.patch.object(Path, "mkdir"):
                old_cwd = os.getcwd()
                os.chdir(tmpdir)
                try:
                    agent_repair.main()
                except SystemExit as e:
                    self.fail(f"main() raised SystemExit({e.code})")
                finally:
                    os.chdir(old_cwd)

                # assertions (still inside tempdir context so files exist)
                # opencode should have been invoked twice
                opencode_calls = [
                    c for c in mock_run.call_args_list
                    if c.args and c.args[0] and c.args[0][0] == "opencode"
                ]
                self.assertEqual(len(opencode_calls), 2)
                # feedback.txt should have been created between iterations
                self.assertTrue((tmp / "feedback.txt").exists())
    # ── 6. Max retries all with violations → exit 1 ──────────────────────────

    @mock.patch("agent_repair.signal.signal")
    @mock.patch("agent_repair.shutil.copy")
    @mock.patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            base_sha=None,
            max_retries=3,
            prompt_file="scripts/ci/agent_prompt.md",
            feedback_file="scripts/ci/agent_feedback.md",
        ),
    )
    @mock.patch("agent_repair.shutil.which", return_value="/usr/bin/opencode")
    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(Path, "exists", return_value=False)
    @mock.patch.object(Path, "glob", return_value=[Path("patch-output/0001-fix.patch")])
    @mock.patch.object(Path, "mkdir")
    @mock.patch.object(Path, "read_text", return_value="prompt content")
    @mock.patch.object(Path, "write_text")
    @mock.patch("agent_repair.subprocess.run")
    def test_6_max_retries_all_violations(
        self,
        mock_run,
        _write_text,
        _read_text,
        _mkdir,
        _glob,
        _exists,
        _is_file,
        _which,
        _parse_args,
        _copy,
        _signal,
    ):
        mock_run.side_effect = _make_run_side_effect({
            "git diff": (0, "scripts/ci/bad.py\nsrc/main.c\n"),
        })

        with self.assertRaises(SystemExit) as ctx:
            agent_repair.main()
        self.assertEqual(ctx.exception.code, 1)

    # ── 7. opencode fails (non-zero exit), retries succeed → exit 0 ──────────

    @mock.patch("agent_repair.signal.signal")
    @mock.patch("agent_repair.shutil.copy")
    @mock.patch("argparse.ArgumentParser.parse_args", return_value=_DEFAULT_ARGS)
    @mock.patch("agent_repair.shutil.which", return_value="/usr/bin/opencode")
    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(Path, "exists", return_value=False)
    @mock.patch.object(Path, "glob", return_value=[Path("patch-output/0001-fix.patch")])
    @mock.patch.object(Path, "mkdir")
    @mock.patch.object(Path, "read_text", return_value="prompt content")
    @mock.patch.object(Path, "write_text")
    @mock.patch("agent_repair.subprocess.run")
    def test_7_opencode_fails_retry_succeeds(
        self,
        mock_run,
        _write_text,
        _read_text,
        _mkdir,
        _glob,
        _exists,
        _is_file,
        _which,
        _parse_args,
        _copy,
        _signal,
    ):
        """First opencode returns non-zero; second succeeds with no violations."""

        # opencode: first call fails (rc=1), second succeeds (rc=0)
        oc_returncodes = iter([1, 0])

        def run_se(args, *, capture_output=True, text=True, check=False, **kwargs):
            cmd_str = " ".join(str(a) for a in args)
            if cmd_str.startswith("opencode run"):
                rc = next(oc_returncodes)
                return subprocess.CompletedProcess(args, rc, stdout="", stderr="")
            return _make_run_side_effect()(
                args, capture_output=capture_output, text=text, check=check, **kwargs
            )

        mock_run.side_effect = run_se

        try:
            agent_repair.main()
        except SystemExit as e:
            self.fail(f"main() raised SystemExit({e.code})")

        # opencode was called twice
        opencode_calls = [
            c for c in mock_run.call_args_list
            if c.args and c.args[0] and c.args[0][0] == "opencode"
        ]
        self.assertEqual(len(opencode_calls), 2)

    # ── 8. No changes made → breaks early, exit 0 ────────────────────────────

    @mock.patch("agent_repair.signal.signal")
    @mock.patch("agent_repair.shutil.copy")
    @mock.patch("argparse.ArgumentParser.parse_args", return_value=_DEFAULT_ARGS)
    @mock.patch("agent_repair.shutil.which", return_value="/usr/bin/opencode")
    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(Path, "exists", return_value=False)
    @mock.patch.object(Path, "read_text", return_value="prompt content")
    @mock.patch("agent_repair.subprocess.run")
    def test_8_no_changes_breaks_early(
        self,
        mock_run,
        _read_text,
        _exists,
        _is_file,
        _which,
        _parse_args,
        _copy,
        _signal,
    ):
        """opencode runs but makes no commits; script breaks early."""
        mock_run.side_effect = _make_run_side_effect({
            "git log --oneline": (0, ""),  # empty = no commits
        })

        try:
            agent_repair.main()
        except SystemExit as e:
            self.fail(f"main() raised SystemExit({e.code})")

        # Only one iteration (breaks early)
        # opencode was called once
        opencode_calls = [
            c for c in mock_run.call_args_list
            if c.args and c.args[0] and c.args[0][0] == "opencode"
        ]
        self.assertEqual(len(opencode_calls), 1)

    # ── 9. Multiple commits squashed into one ────────────────────────────────

    @mock.patch("agent_repair.signal.signal")
    @mock.patch("agent_repair.shutil.copy")
    @mock.patch("argparse.ArgumentParser.parse_args", return_value=_DEFAULT_ARGS)
    @mock.patch("agent_repair.shutil.which", return_value="/usr/bin/opencode")
    @mock.patch.object(Path, "is_file", return_value=True)
    @mock.patch.object(Path, "exists", return_value=False)
    @mock.patch.object(Path, "glob", return_value=[Path("patch-output/0001-fix.patch")])
    @mock.patch.object(Path, "mkdir")
    @mock.patch.object(Path, "read_text", return_value="prompt content")
    @mock.patch.object(Path, "write_text")
    @mock.patch("agent_repair.subprocess.run")
    def test_9_multiple_commits_squashed(
        self,
        mock_run,
        _write_text,
        _read_text,
        _mkdir,
        _glob,
        _exists,
        _is_file,
        _which,
        _parse_args,
        _copy,
        _signal,
    ):
        """opencode creates 3 commits → they get squashed into one."""
        mock_run.side_effect = _make_run_side_effect({
            "git rev-list --count": (0, "3\n"),  # 3 commits → trigger squash
        })

        try:
            agent_repair.main()
        except SystemExit as e:
            self.fail(f"main() raised SystemExit({e.code})")

        # Verify squash commands were issued
        all_git_calls = [
            " ".join(str(a) for a in call.args[0])
            for call in mock_run.call_args_list
        ]
        self.assertTrue(
            any("reset --soft" in c for c in all_git_calls),
            f"git reset --soft not called. Calls: {all_git_calls}",
        )
        self.assertTrue(
            any(c.startswith("git commit") for c in all_git_calls),
            f"git commit not called. Calls: {all_git_calls}",
        )
        self.assertTrue(
            any("log --format=%s" in c for c in all_git_calls),
            f"git log --format=%s not called. Calls: {all_git_calls}",
        )

    # ── 10. Feedback template substitution works correctly ────────────────────

    def test_10_feedback_template_substitution(self):
        """_generate_feedback substitutes {attempt} and {violations} correctly."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("## Attempt {attempt}\nViolations:\n{violations}\n")
            tf.flush()
            template_path = tf.name

        try:
            agent_repair._generate_feedback(
                attempt=2,
                violations=["scripts/ci/bad.py", "src/main.c"],
                feedback_file=template_path,
            )

            content = Path("feedback.txt").read_text(encoding="utf-8")
            self.assertIn("Attempt 2", content)
            self.assertIn("- scripts/ci/bad.py", content)
            self.assertIn("- src/main.c", content)
            self.assertNotIn("{attempt}", content)
            self.assertNotIn("{violations}", content)

            # Clean up generated feedback.txt
            Path("feedback.txt").unlink(missing_ok=True)
        finally:
            Path(template_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
