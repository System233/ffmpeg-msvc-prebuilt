"""Tests for scripts/ops/ci_detect_changes.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
from ci_detect_changes import _get_revision, _git_show


class TestGetRevision(unittest.TestCase):
    def test_revision_set(self):
        self.assertEqual(_get_revision("version: 8.1.1\nrevision: 2\n"), 2)

    def test_revision_zero(self):
        self.assertEqual(_get_revision("version: 8.1.1\nrevision: 0\n"), 0)

    def test_no_revision_field(self):
        self.assertEqual(_get_revision("version: 8.1.1\n"), 0)

    def test_empty_content(self):
        self.assertEqual(_get_revision(""), 0)

    def test_revision_with_spaces(self):
        self.assertEqual(_get_revision("revision:   3\n"), 3)

    def test_multiline_revision(self):
        content = """extends: "8.0"
revision: 5
source:
  sha512: abc
"""
        self.assertEqual(_get_revision(content), 5)


class TestGitShow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_cwd = Path.cwd()
        self.repo = Path(self.temp_dir.name)
        _git(["init", "-b", "main"], self.repo)
        _git(["config", "user.email", "test@test"], self.repo)
        _git(["config", "user.name", "Test"], self.repo)

    def tearDown(self):
        # Restore original cwd and path override before cleanup
        import ci_detect_changes as mod
        mod.REPO_ROOT = Path(__file__).resolve().parents[1]
        self.temp_dir.cleanup()

    def _set_repo_root(self, path: Path):
        import ci_detect_changes as mod
        mod.REPO_ROOT = path

    def test_file_exists(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "init"], self.repo)
        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("revision: 2\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "add yaml"], self.repo)
        sha = _git(["rev-parse", "HEAD"], self.repo).strip()

        self._set_repo_root(self.repo)
        result = _git_show(sha, "ffmpeg/8.1.1.yaml")
        self.assertEqual(result, "revision: 2\n")

    def test_file_not_exists(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "init"], self.repo)
        sha = _git(["rev-parse", "HEAD"], self.repo).strip()

        self._set_repo_root(self.repo)
        result = _git_show(sha, "ffmpeg/nonexistent.yaml")
        self.assertEqual(result, "")

    def test_file_added_in_later_commit(self):
        """File doesn't exist in before SHA, exists in after SHA."""
        # First commit — empty ffmpeg dir with keep file
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "first"], self.repo)
        before = _git(["rev-parse", "HEAD"], self.repo).strip()
        _git(["rm", "--cached", "ffmpeg/.gitkeep"], self.repo)
        _git(["commit", "-m", "remove keep"], self.repo)

        # Second commit — add a yaml
        (self.repo / "ffmpeg" / "6.5.yaml").write_text("revision: 0\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "add 6.5"], self.repo)
        after = _git(["rev-parse", "HEAD"], self.repo).strip()

        self._set_repo_root(self.repo)
        old_content = _git_show(before, "ffmpeg/6.5.yaml")
        new_content = _git_show(after, "ffmpeg/6.5.yaml")
        self.assertEqual(old_content, "")
        self.assertNotEqual(new_content, "")


class TestGetChangedVersionsIntegration(unittest.TestCase):
    """Integration test with a real git repo."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        _git(["init", "-b", "main"], self.repo)
        _git(["config", "user.email", "test@test"], self.repo)
        _git(["config", "user.name", "Test"], self.repo)

    def tearDown(self):
        import ci_detect_changes as mod
        mod.REPO_ROOT = Path(__file__).resolve().parents[1]
        self.temp_dir.cleanup()

    def _get_changed(self, before: str, after: str):
        import ci_detect_changes as mod
        orig = mod.REPO_ROOT
        mod.REPO_ROOT = self.repo
        try:
            return mod.get_changed_versions(before, after)
        finally:
            mod.REPO_ROOT = orig

    def test_new_file_detected_as_change(self):
        """New YAML file with revision: 0 should be detected."""
        # First commit
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "first"], self.repo)
        before = _git(["rev-parse", "HEAD"], self.repo).strip()
        _git(["rm", "--cached", "ffmpeg/.gitkeep"], self.repo)
        _git(["commit", "-m", "remove keep"], self.repo)

        # Add new version YAML
        (self.repo / "ffmpeg" / "6.5.yaml").write_text("extends: 6.1\nrevision: 0\nsource:\n  sha512: abc\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "add 6.5"], self.repo)
        after = _git(["rev-parse", "HEAD"], self.repo).strip()

        result = self._get_changed(before, after)
        self.assertIn("6.5", result)

    def test_revision_change_detected(self):
        """Existing file with revision change should be detected."""
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("extends: 8.1\nrevision: 2\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "base"], self.repo)
        before = _git(["rev-parse", "HEAD"], self.repo).strip()

        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("extends: 8.1\nrevision: 3\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "bump rev"], self.repo)
        after = _git(["rev-parse", "HEAD"], self.repo).strip()

        result = self._get_changed(before, after)
        self.assertEqual(result, {"8.1.1": 3})

    def test_no_change_not_detected(self):
        """File with same revision on both sides should not be detected."""
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("extends: 8.1\nrevision: 2\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "base"], self.repo)
        sha = _git(["rev-parse", "HEAD"], self.repo).strip()

        result = self._get_changed(sha, sha)
        self.assertEqual(result, {})


def _git(args: list[str], cwd: Path) -> str:
    import subprocess
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=str(cwd))
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout


if __name__ == "__main__":
    unittest.main()
