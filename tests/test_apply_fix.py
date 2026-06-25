"""Tests for scripts/ci/apply_fix.py."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from apply_fix import (
    _apply_patch,
    _bump_revision,
    _is_violation,
    _push_and_pr,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    """Return a successful ``CompletedProcess`` with the given *stdout*."""
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stdout, stderr=""
    )


def _fail() -> subprocess.CompletedProcess[str]:
    """Return a failed ``CompletedProcess`` (returncode=1)."""
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")


def _plat(path: str) -> str:
    """Convert a forward-slash path to the platform-native form."""
    return str(Path(path))


def _git_am_cmd(patch_file: str = ANY) -> list[str]:
    return ["git", "am", patch_file]


def _git_diff_cmd() -> list[str]:
    return ["git", "diff", "HEAD~1..HEAD", "--name-only"]


def _git_log_cmd() -> list[str]:
    return ["git", "log", "-1", "--format=%s", "HEAD"]


# ---------------------------------------------------------------------------
# _is_violation
# ---------------------------------------------------------------------------


class TestIsViolation(unittest.TestCase):
    """Tests for the ``_is_violation`` helper."""

    def test_ffmpeg_yaml_allowed(self) -> None:
        self.assertFalse(_is_violation("ffmpeg/8.1.1.yaml"))

    def test_ffmpeg_nested_yaml_allowed(self) -> None:
        self.assertFalse(_is_violation("ffmpeg/subdir/file.yaml"))

    def test_patches_patch_allowed(self) -> None:
        self.assertFalse(_is_violation("patches/8.x/something.patch"))

    def test_patches_nested_patch_allowed(self) -> None:
        self.assertFalse(_is_violation("patches/8.x/001/0001-foo.patch"))

    def test_opencode_allowed(self) -> None:
        self.assertFalse(_is_violation(".opencode/skills/auto-heal/SKILL.md"))

    def test_opencode_config_allowed(self) -> None:
        self.assertFalse(_is_violation(".opencode/config.json"))

    def test_scripts_py_violation(self) -> None:
        self.assertTrue(_is_violation("scripts/ci/foo.py"))

    def test_github_workflows_violation(self) -> None:
        self.assertTrue(_is_violation(".github/workflows/auto-heal.yml"))

    def test_readme_violation(self) -> None:
        self.assertTrue(_is_violation("README.md"))

    def test_patches_txt_violation(self) -> None:
        """Only .patch files under patches/ are allowed."""
        self.assertTrue(_is_violation("patches/something.txt"))


# ---------------------------------------------------------------------------
# _apply_patch
# ---------------------------------------------------------------------------


class TestApplyPatch(unittest.TestCase):
    """Tests for the ``_apply_patch`` function."""

    def setUp(self) -> None:
        self._patch_dir = "patch-input"
        self._bot_name = "ffmpeg-dev[bot]"
        self._bot_id = "12345"
        self._token = "gh_token"
        self._repo = "owner/repo"

    # -- 1. No patch files found → exit 0 ---------------------------------

    @patch.object(Path, "is_dir", return_value=True)
    @patch.object(Path, "glob", return_value=[])
    def test_no_patches_exits_zero(
        self, _mock_glob: MagicMock, _mock_is_dir: MagicMock
    ) -> None:
        with self.assertRaises(SystemExit) as ctx:
            _apply_patch(
                self._patch_dir,
                self._bot_name,
                self._bot_id,
                self._token,
                self._repo,
            )
        self.assertEqual(ctx.exception.code, 0)

    # -- 2. Successful apply + no violations → continue -------------------

    @patch("apply_fix.subprocess.run")
    @patch.object(Path, "is_dir", return_value=True)
    @patch.object(Path, "glob")
    def test_success_no_violations(
        self,
        mock_glob: MagicMock,
        _mock_is_dir: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_glob.return_value = [Path("patch-input/0001-fix.patch")]

        mock_run.side_effect = lambda args, **kwargs: (
            _ok()
            if args == _git_am_cmd(ANY)
            else _ok("ffmpeg/8.1.1.yaml\n.opencode/skills/auto-heal/SKILL.md\n")
            if args == _git_diff_cmd()
            else _ok()
        )

        # Should not raise
        _apply_patch(
            self._patch_dir,
            self._bot_name,
            self._bot_id,
            self._token,
            self._repo,
        )

        # Verify git am was called (use ANY for platform-variant path)
        mock_run.assert_any_call(_git_am_cmd(ANY))

    # -- 3. Scope violations → exit 1 ------------------------------------

    @patch("apply_fix.subprocess.run")
    @patch.object(Path, "is_dir", return_value=True)
    @patch.object(Path, "glob")
    def test_scope_violations_exit_one(
        self,
        mock_glob: MagicMock,
        _mock_is_dir: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_glob.return_value = [Path("patch-input/0001-fix.patch")]

        mock_run.side_effect = lambda args, **kwargs: (
            _ok()
            if args == _git_am_cmd(ANY)
            else _ok("scripts/ci/bad.py\nREADME.md\n")
            if args == _git_diff_cmd()
            else _ok()
        )

        with self.assertRaises(SystemExit) as ctx:
            _apply_patch(
                self._patch_dir,
                self._bot_name,
                self._bot_id,
                self._token,
                self._repo,
            )
        self.assertEqual(ctx.exception.code, 1)

        # Verify git reset --hard HEAD~1 was called
        mock_run.assert_any_call(
            ["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True
        )

    # -- 4. Mixed scope with .opencode/ → allowed -------------------------

    @patch("apply_fix.subprocess.run")
    @patch.object(Path, "is_dir", return_value=True)
    @patch.object(Path, "glob")
    def test_opencode_files_not_violations(
        self,
        mock_glob: MagicMock,
        _mock_is_dir: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_glob.return_value = [Path("patch-input/0001-fix.patch")]

        mock_run.side_effect = lambda args, **kwargs: (
            _ok()
            if args == _git_am_cmd(ANY)
            else _ok(".opencode/skills/auto-heal/SKILL.md\nffmpeg/8.1.1.yaml\n")
            if args == _git_diff_cmd()
            else _ok()
        )

        # Should not raise
        _apply_patch(
            self._patch_dir,
            self._bot_name,
            self._bot_id,
            self._token,
            self._repo,
        )

    # -- 5. git am fails → exit 1 ----------------------------------------

    @patch("apply_fix.subprocess.run")
    @patch.object(Path, "is_dir", return_value=True)
    @patch.object(Path, "glob")
    def test_git_am_failure(
        self,
        mock_glob: MagicMock,
        _mock_is_dir: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_glob.return_value = [Path("patch-input/0001-fix.patch")]

        def _fake_run(
            args: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if args[0] == "git" and args[1] == "am":
                return _fail()
            return _ok()

        mock_run.side_effect = _fake_run

        with self.assertRaises(SystemExit) as ctx:
            _apply_patch(
                self._patch_dir,
                self._bot_name,
                self._bot_id,
                self._token,
                self._repo,
            )
        self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------------------
# _push_and_pr
# ---------------------------------------------------------------------------


class TestPushAndPr(unittest.TestCase):
    """Tests for the ``_push_and_pr`` function and helpers."""

    def setUp(self) -> None:
        self._branch = "fix/test-branch"
        self._yaml = "8.1.1"
        self._repo = "owner/repo"
        self._fix_report = "fix-report"

    # -- 6. ACTION=pr: gh pr create + gh pr merge called correctly --------

    @patch.object(Path, "exists", return_value=False)  # no body file
    @patch("apply_fix.subprocess.run")
    def test_action_pr_creates_and_merges(
        self,
        mock_run: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        commit_msg = "fix(8.1.1): auto-fix build failure"

        mock_run.side_effect = lambda args, **kwargs: (
            _ok(commit_msg)
            if args == _git_log_cmd()
            else _ok("https://github.com/owner/repo/pull/42\n")
            if args[0] == "gh" and args[1] == "pr" and args[2] == "create"
            else _ok()
            if args == ["gh", "pr", "merge", "42", "--auto", "--squash"]
            else _ok()
        )

        _push_and_pr(
            action="pr",
            branch=self._branch,
            yaml_name=self._yaml,
            bump_revision_flag=False,
            pr_number="",
            fix_report_dir=self._fix_report,
            github_repository=self._repo,
        )

        # Verify git push
        mock_run.assert_any_call(
            ["git", "push", "origin", f"HEAD:{self._branch}"], check=True
        )

        # Verify gh pr create with correct args (no --body-file)
        mock_run.assert_any_call(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                self._branch,
                "--title",
                commit_msg,
                "--repo",
                self._repo,
            ],
            capture_output=True,
            text=True,
            
        )

        # Verify gh pr merge
        mock_run.assert_any_call(
            ["gh", "pr", "merge", "42", "--auto", "--squash"]
        )

    # -- 6b. ACTION=pr with empty commit message → fallback title ---------

    @patch.object(Path, "exists", return_value=False)
    @patch("apply_fix.subprocess.run")
    def test_action_pr_fallback_title(
        self,
        mock_run: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        mock_run.side_effect = lambda args, **kwargs: (
            _ok("")
            if args == _git_log_cmd()
            else _ok("https://github.com/owner/repo/pull/42\n")
            if args[0] == "gh" and args[1] == "pr" and args[2] == "create"
            else _ok()
        )

        _push_and_pr(
            action="pr",
            branch=self._branch,
            yaml_name=self._yaml,
            bump_revision_flag=False,
            pr_number="",
            fix_report_dir=self._fix_report,
            github_repository=self._repo,
        )

        fallback_title = f"fix({self._yaml}): auto-fix build failure"
        mock_run.assert_any_call(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                self._branch,
                "--title",
                fallback_title,
                "--repo",
                self._repo,
            ],
            capture_output=True,
            text=True,
            
        )

    # -- 6c. ACTION=pr with fix report body file --------------------------

    @patch.object(Path, "exists", return_value=True)
    @patch("apply_fix.subprocess.run")
    def test_action_pr_with_body_file(
        self,
        mock_run: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        commit_msg = "fix: apply auto-heal"
        body_path = _plat(f"{self._fix_report}/fix_report.md")

        mock_run.side_effect = lambda args, **kwargs: (
            _ok(commit_msg)
            if args == _git_log_cmd()
            else _ok("https://github.com/owner/repo/pull/42\n")
            if args[0] == "gh" and args[1] == "pr" and args[2] == "create"
            else _ok()
        )

        _push_and_pr(
            action="pr",
            branch=self._branch,
            yaml_name=self._yaml,
            bump_revision_flag=False,
            pr_number="",
            fix_report_dir=self._fix_report,
            github_repository=self._repo,
        )

        # --body-file should be present
        mock_run.assert_any_call(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                self._branch,
                "--title",
                commit_msg,
                "--repo",
                self._repo,
                "--body-file",
                body_path,
            ],
            capture_output=True,
            text=True,
            
        )

    # -- 7. ACTION=push + PR_NUMBER: gh pr edit called --------------------

    @patch.object(Path, "exists", return_value=True)  # body file exists
    @patch("apply_fix.subprocess.run")
    def test_action_push_with_pr_number_edits(
        self,
        mock_run: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        commit_msg = "fix: update from auto-heal"
        body_path = _plat(f"{self._fix_report}/fix_report.md")

        mock_run.side_effect = lambda args, **kwargs: (
            _ok(commit_msg) if args == _git_log_cmd() else _ok()
        )

        _push_and_pr(
            action="push",
            branch=self._branch,
            yaml_name=self._yaml,
            bump_revision_flag=False,
            pr_number="42",
            fix_report_dir=self._fix_report,
            github_repository=self._repo,
        )

        # Verify gh pr edit was called with correct args
        mock_run.assert_any_call(
            [
                "gh",
                "pr",
                "edit",
                "42",
                "--title",
                commit_msg,
                "--repo",
                self._repo,
                "--body-file",
                body_path,
            ],
            
        )

        # Verify NO gh pr create or gh pr merge calls
        for call_args in mock_run.call_args_list:
            args = call_args[0][0]
            self.assertNotIn("create", args[:3] if len(args) >= 3 else [])
            self.assertNotIn("merge", args[:3] if len(args) >= 3 else [])

    # -- 8. ACTION=push without PR_NUMBER: only push, no PR edit ----------

    @patch("apply_fix.subprocess.run")
    def test_action_push_no_pr_number_only_pushes(
        self,
        mock_run: MagicMock,
    ) -> None:
        commit_msg = "fix: something"

        mock_run.side_effect = lambda args, **kwargs: (
            _ok(commit_msg) if args == _git_log_cmd() else _ok()
        )

        _push_and_pr(
            action="push",
            branch=self._branch,
            yaml_name=self._yaml,
            bump_revision_flag=False,
            pr_number="",
            fix_report_dir=self._fix_report,
            github_repository=self._repo,
        )

        # Verify git push
        mock_run.assert_any_call(
            ["git", "push", "origin", f"HEAD:{self._branch}"], check=True
        )

        # Verify git pull --rebase (best-effort in push mode)
        mock_run.assert_any_call(
            ["git", "pull", "--rebase", "origin", self._branch]
        )

        # Verify NO gh commands were called
        for call_args in mock_run.call_args_list:
            args = call_args[0][0]
            self.assertFalse(
                args[0] == "gh", f"Unexpected gh call: {args}"
            )

    # -- 9. bump_revision=True → bump_revision.bump called ----------------

    @patch.object(Path, "exists", return_value=True)  # YAML exists
    @patch("apply_fix.bump", return_value=(5, 6))
    @patch("apply_fix.subprocess.run")
    def test_bump_revision_called(
        self,
        mock_run: MagicMock,
        mock_bump: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        commit_msg = "fix: apply auto-heal"
        yaml_path_str = _plat(f"ffmpeg/{self._yaml}.yaml")

        mock_run.side_effect = lambda args, **kwargs: (
            _ok(commit_msg) if args == _git_log_cmd() else _ok()
        )

        _push_and_pr(
            action="push",
            branch=self._branch,
            yaml_name=self._yaml,
            bump_revision_flag=True,
            pr_number="",
            fix_report_dir=self._fix_report,
            github_repository=self._repo,
        )

        # Verify bump was called with the correct Path
        mock_bump.assert_called_once_with(Path(f"ffmpeg/{self._yaml}.yaml"))

        # Verify git add and commit (use platform-native paths)
        mock_run.assert_any_call(
            ["git", "add", yaml_path_str], check=True
        )
        mock_run.assert_any_call(
            ["git", "commit", "-m", f"fix({self._yaml}): bump revision to 6"], check=True
        )

    # -- 10. bump_revision but YAML file missing → warning ----------------

    @patch.object(Path, "exists", return_value=False)  # YAML missing
    @patch("apply_fix.subprocess.run")
    def test_bump_revision_missing_yaml_warns(
        self,
        mock_run: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        mock_run.side_effect = lambda args, **kwargs: (
            _ok("fix: something") if args == _git_log_cmd() else _ok()
        )

        # Should not raise; bump is skipped
        _push_and_pr(
            action="push",
            branch=self._branch,
            yaml_name=self._yaml,
            bump_revision_flag=True,
            pr_number="",
            fix_report_dir=self._fix_report,
            github_repository=self._repo,
        )

        # git add/commit should NOT have been called for bump
        for call_args in mock_run.call_args_list:
            args = call_args[0][0]
            if args[0] == "git" and args[1] == "commit":
                self.assertNotIn("bump revision", " ".join(args))


# ---------------------------------------------------------------------------
# _bump_revision
# ---------------------------------------------------------------------------


class TestBumpRevision(unittest.TestCase):
    """Tests for the ``_bump_revision`` function."""

    @patch.object(Path, "exists", return_value=True)
    @patch("apply_fix.bump", return_value=(3, 4))
    @patch("apply_fix.subprocess.run")
    def test_bump_adds_and_commits(
        self,
        mock_run: MagicMock,
        mock_bump: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        _bump_revision("master")

        mock_bump.assert_called_once_with(Path("ffmpeg/master.yaml"))
        mock_run.assert_any_call(
            ["git", "add", _plat("ffmpeg/master.yaml")], check=True
        )
        mock_run.assert_any_call(
            ["git", "commit", "-m", "fix(master): bump revision to 4"], check=True
        )

    @patch.object(Path, "exists", return_value=False)
    @patch("apply_fix.subprocess.run")
    def test_bump_missing_yaml_noops(
        self,
        mock_run: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        _bump_revision("nonexistent")

        # No git 'add' commands should have been called
        add_calls = [
            c
            for c in mock_run.call_args_list
            if c[0][0][0] == "git"
            and len(c[0][0]) > 1
            and c[0][0][1] == "add"
        ]
        self.assertEqual(len(add_calls), 0)


# ---------------------------------------------------------------------------
# Integration: full flow via _push_and_pr with mocked _apply_patch
# ---------------------------------------------------------------------------


class TestFullFlow(unittest.TestCase):
    """End-to-end style tests for the main orchestration logic."""

    @patch.object(Path, "exists", return_value=False)
    @patch("apply_fix.subprocess.run")
    @patch.object(Path, "is_dir", return_value=True)
    @patch.object(Path, "glob")
    def test_full_successful_flow(
        self,
        mock_glob: MagicMock,
        _mock_is_dir: MagicMock,
        mock_run: MagicMock,
        _mock_exists: MagicMock,
    ) -> None:
        """Apply patch with allowed files, then push (no PR)."""
        mock_glob.return_value = [Path("patch-input/0001-fix.patch")]

        commit_msg = "fix: auto-heal applied"

        mock_run.side_effect = lambda args, **kwargs: (
            _ok()
            if args == _git_am_cmd(ANY)
            else _ok("ffmpeg/8.1.1.yaml\n.opencode/config.json\n")
            if args == _git_diff_cmd()
            else _ok(commit_msg)
            if args == _git_log_cmd()
            else _ok()
        )

        # Phase 1
        _apply_patch(
            "patch-input",
            "ffmpeg-dev[bot]",
            "12345",
            "gh_token",
            "owner/repo",
        )

        # Phase 2
        _push_and_pr(
            action="push",
            branch="fix/branch",
            yaml_name="8.1.1",
            bump_revision_flag=False,
            pr_number="",
            fix_report_dir="fix-report",
            github_repository="owner/repo",
        )

        # Verify push happened
        mock_run.assert_any_call(
            ["git", "push", "origin", "HEAD:fix/branch"], check=True
        )

    @patch("apply_fix.subprocess.run")
    @patch.object(Path, "is_dir", return_value=True)
    @patch.object(Path, "glob")
    def test_violation_prevents_push(
        self,
        mock_glob: MagicMock,
        _mock_is_dir: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """Violation in phase 1 should prevent phase 2 from running."""
        mock_glob.return_value = [Path("patch-input/0001-fix.patch")]

        mock_run.side_effect = lambda args, **kwargs: (
            _ok()
            if args == _git_am_cmd(ANY)
            else _ok("scripts/ci/bad.py\n")
            if args == _git_diff_cmd()
            else _ok()
        )

        with self.assertRaises(SystemExit) as ctx:
            _apply_patch(
                "patch-input",
                "ffmpeg-dev[bot]",
                "12345",
                "gh_token",
                "owner/repo",
            )
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
