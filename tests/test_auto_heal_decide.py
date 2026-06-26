"""Tests for scripts/ci/auto_heal_decide.py."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from auto_heal_decide import (
    read_yaml_revision,
    decide,
    REPO_ROOT,
)


# ── YAML revision parsing ────────────────────────────────────────────────────

class TestReadYamlRevision(unittest.TestCase):
    """Test revision extraction from YAML files via read_yaml_revision."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.yaml_dir = Path(self.temp_dir.name) / "ffmpeg"
        self.yaml_dir.mkdir()
        # Redirect REPO_ROOT to the temp directory
        patcher = mock.patch("auto_heal_decide.REPO_ROOT", Path(self.temp_dir.name))
        self.mock_root = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def _write_yaml(self, name, content):
        path = self.yaml_dir / f"{name}.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_revision_extracted(self):
        """Revision field is extracted correctly."""
        self._write_yaml("8.1.1", "version: 8.1.1\nrevision: 2\nsource:\n  url: x\n")
        self.assertEqual(read_yaml_revision("8.1.1"), 2)

    def test_revision_zero(self):
        """Revision of 0 is extracted."""
        self._write_yaml("8.1.1", "revision: 0\n")
        self.assertEqual(read_yaml_revision("8.1.1"), 0)

    def test_no_revision_field(self):
        """No revision field → returns None."""
        self._write_yaml("8.1.1", "version: 8.1.1\nsource:\n  url: x\n")
        self.assertIsNone(read_yaml_revision("8.1.1"))

    def test_file_not_exists(self):
        """YAML file does not exist → returns None."""
        self.assertIsNone(read_yaml_revision("nonexistent"))

    def test_revision_with_spaces(self):
        """Revision with extra whitespace after colon."""
        self._write_yaml("test", "revision:   5\n")
        self.assertEqual(read_yaml_revision("test"), 5)

    def test_revision_multiline(self):
        """Revision field not on first line of content."""
        content = 'extends: "8.0"\nrevision: 7\nsource:\n  sha512: abc\n'
        self._write_yaml("test", content)
        self.assertEqual(read_yaml_revision("test"), 7)

    def test_revision_after_comment(self):
        """Comment lines before the revision field."""
        content = "# comment\n# another comment\nrevision: 3\n"
        self._write_yaml("test", content)
        self.assertEqual(read_yaml_revision("test"), 3)

    def test_comment_not_matched(self):
        """# revision: 99 in a comment line is not matched."""
        content = "# revision: 99\nversion: 1.0\nrevision: 4\n"
        self._write_yaml("test", content)
        self.assertEqual(read_yaml_revision("test"), 4)


# ── Branch name construction ─────────────────────────────────────────────────

class TestBranchNameConstruction(unittest.TestCase):
    """Test the branch name logic mirrored from decide()."""

    def _build_branch(self, yaml_name, revision=None):
        """Mirror the branch name construction from decide()."""
        if revision is not None:
            return f"fix/ffmpeg-{yaml_name}-r{revision + 1}"
        return f"fix/ffmpeg-{yaml_name}"

    def test_with_revision(self):
        """Branch includes -r{rev+1} when revision is known."""
        self.assertEqual(self._build_branch("8.1.1", 2), "fix/ffmpeg-8.1.1-r3")

    def test_with_revision_zero(self):
        """Revision 0 → -r1."""
        self.assertEqual(self._build_branch("7.1", 0), "fix/ffmpeg-7.1-r1")

    def test_without_revision(self):
        """No revision → plain branch name without -r suffix."""
        self.assertEqual(self._build_branch("master", None), "fix/ffmpeg-master")

    def test_without_revision_explicit_none(self):
        """Explicit None → no -r suffix."""
        self.assertEqual(self._build_branch("8.1.1", None), "fix/ffmpeg-8.1.1")


# ── Decision logic with mocked subprocess / environment ──────────────────────

class TestDecide(unittest.TestCase):
    """Test decide() with mocked subprocess, environment, and helpers."""

    def setUp(self):
        # Ensure GITHUB_REPOSITORY is set for get_owner_repo()
        self.env_patcher = mock.patch.dict(
            os.environ, {"GITHUB_REPOSITORY": "owner/repo"}, clear=True
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def _make_args(self, run_id="12345", pr_number=None, yaml=None, base_ref="main"):
        return argparse.Namespace(
            run_id=run_id,
            pr_number=pr_number,
            yaml=yaml,
            base_ref=base_ref,
        )

    # ── Scenario 1: PR number provided ───────────────────────────────────

    @mock.patch("auto_heal_decide.gh_api")
    def test_pr_number_provided(self, mock_gh_api):
        """PR number provided → action=push, checkout_ref=branch."""
        mock_gh_api.return_value = {
            "head": {"ref": "feature/fix", "sha": "abc123"},
            "base": {"ref": "main", "sha": "def456"},
            "user": {"login": "testuser"},
        }
        args = self._make_args(pr_number="42")
        result = decide(args)

        self.assertEqual(result["action"], "push")
        self.assertEqual(result["checkout_ref"], "feature/fix")
        self.assertEqual(result["branch"], "feature/fix")
        self.assertEqual(result["pr_number"], "42")
        self.assertEqual(result["pr_author"], "testuser")
        self.assertEqual(result["skip"], "false")
        self.assertEqual(result["base_revision"], "")
        mock_gh_api.assert_called_once_with("repos/owner/repo/pulls/42")

    # ── Scenario 2: YAML provided, no existing fix PR ────────────────────

    @mock.patch("auto_heal_decide.gh_has_open_fix_pr")
    @mock.patch("auto_heal_decide.read_yaml_revision")
    def test_yaml_no_existing_fix_pr(self, mock_read_rev, mock_has_fix_pr):
        """YAML provided, no existing fix PR → action=pr, skip=false."""
        mock_read_rev.return_value = 2
        mock_has_fix_pr.return_value = False
        args = self._make_args(yaml="8.1.1")
        result = decide(args)

        self.assertEqual(result["action"], "pr")
        self.assertEqual(result["skip"], "false")
        self.assertEqual(result["branch"], "fix/ffmpeg-8.1.1-r3")
        self.assertEqual(result["bump_revision"], "true")
        self.assertEqual(result["checkout_ref"], "main")
        self.assertEqual(result["base_revision"], "2")

    # ── Scenario 3: YAML provided, existing fix PR is OPEN ───────────────

    @mock.patch("auto_heal_decide.gh_has_open_fix_pr")
    @mock.patch("auto_heal_decide.read_yaml_revision")
    def test_yaml_existing_fix_pr_open(self, mock_read_rev, mock_has_fix_pr):
        """YAML provided, existing fix PR is OPEN → action=pr, skip=true."""
        mock_read_rev.return_value = 2
        mock_has_fix_pr.return_value = True
        args = self._make_args(yaml="8.1.1")
        result = decide(args)

        self.assertEqual(result["action"], "pr")
        self.assertEqual(result["skip"], "true")
        self.assertEqual(result["branch"], "fix/ffmpeg-8.1.1-r3")

    # ── Scenario 4: YAML without revision field ──────────────────────────

    @mock.patch("auto_heal_decide.gh_has_open_fix_pr")
    @mock.patch("auto_heal_decide.read_yaml_revision")
    def test_yaml_no_revision_field(self, mock_read_rev, mock_has_fix_pr):
        """YAML without revision → branch name without -r suffix, bump_revision=false."""
        mock_read_rev.return_value = None
        mock_has_fix_pr.return_value = False
        args = self._make_args(yaml="master")
        result = decide(args)

        self.assertEqual(result["branch"], "fix/ffmpeg-master")
        self.assertEqual(result["bump_revision"], "false")
        self.assertEqual(result["action"], "pr")
        self.assertEqual(result["base_revision"], "")

    # ── Scenario 6: workflow_dispatch (no PR number or yaml) ─────────────

    @mock.patch("auto_heal_decide.gh_api")
    def test_workflow_dispatch(self, mock_gh_api):
        """No PR number or yaml → workflow_dispatch path via run ID."""
        mock_gh_api.side_effect = [
            # First call: get run details → returns associated PR
            {"pull_requests": [{"number": 99}]},
            # Second call: get PR details
            {
                "head": {"ref": "fix/something", "sha": "aaa"},
                "base": {"ref": "main", "sha": "bbb"},
                "user": {"login": "devuser"},
            },
        ]
        args = self._make_args()  # no pr_number, no yaml
        result = decide(args)

        self.assertEqual(result["action"], "push")
        self.assertEqual(result["pr_number"], "99")
        self.assertEqual(result["checkout_ref"], "fix/something")
        self.assertEqual(result["branch"], "fix/something")
        self.assertEqual(result["pr_author"], "devuser")
        self.assertEqual(result["base_revision"], "")
        self.assertEqual(mock_gh_api.call_count, 2)


if __name__ == "__main__":
    unittest.main()
