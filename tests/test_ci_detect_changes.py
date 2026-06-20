"""Tests for scripts/ops/ci_detect_changes.py."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
from ci_detect_changes import (
    get_revision,
    git_show,
    git_diff_names,
    detect_changes,
    DetectionResult,
    print_result,
    main,
)


class TestGetRevision(unittest.TestCase):
    def test_revision_set(self):
        self.assertEqual(get_revision("version: 8.1.1\nrevision: 2\n"), 2)

    def test_revision_zero(self):
        self.assertEqual(get_revision("version: 8.1.1\nrevision: 0\n"), 0)

    def test_no_revision_field(self):
        self.assertEqual(get_revision("version: 8.1.1\n"), 0)

    def test_empty_content(self):
        self.assertEqual(get_revision(""), 0)

    def test_revision_with_spaces(self):
        self.assertEqual(get_revision("revision:   3\n"), 3)

    def test_multiline_revision(self):
        content = 'extends: "8.0"\nrevision: 5\nsource:\n  sha512: abc\n'
        self.assertEqual(get_revision(content), 5)


class TestDetectionResult(unittest.TestCase):
    def test_empty_default(self):
        r = DetectionResult.empty()
        self.assertFalse(r.found)
        self.assertEqual(r.changed, [])

    def test_add(self):
        r = DetectionResult()
        r.add("8.1.1", 2)
        self.assertTrue(r.found)
        self.assertEqual(r.changed[0].version, "8.1.1")
        self.assertEqual(r.changed[0].revision, 2)

    def test_multiple_adds(self):
        r = DetectionResult()
        r.add("8.1.1", 2)
        r.add("7.1.2", 1)
        self.assertEqual(len(r.changed), 2)


class TestPrintResult(unittest.TestCase):
    def capture(self, result, use_json, empty_msg=""):
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            print_result(result, use_json, empty_msg)
        finally:
            sys.stdout = old
        return buf.getvalue().strip()

    def test_empty_text(self):
        out = self.capture(DetectionResult.empty(), use_json=False)
        self.assertEqual(out, "")

    def test_empty_text_with_msg(self):
        out = self.capture(DetectionResult.empty(), use_json=False, empty_msg="no changes")
        self.assertEqual(out, "no changes")

    def test_empty_json(self):
        out = self.capture(DetectionResult.empty(), use_json=True)
        self.assertEqual(json.loads(out), {"changed": [], "found": False})

    def test_changes_text(self):
        r = DetectionResult()
        r.add("8.1.1", 2)
        out = self.capture(r, use_json=False)
        self.assertEqual(out, "8.1.1 2")

    def test_changes_json(self):
        r = DetectionResult()
        r.add("8.1.1", 2)
        out = self.capture(r, use_json=True)
        data = json.loads(out)
        self.assertTrue(data["found"])
        self.assertEqual(data["changed"], [{"version": "8.1.1", "revision": 2}])


class TestCLI(unittest.TestCase):
    def test_zero_sha_base(self):
        """0000... base should produce empty result."""
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            main(["--base", "0000000000000000000000000000000000000000", "--json"])
        finally:
            sys.stdout = old
        data = json.loads(out.getvalue().strip())
        self.assertFalse(data["found"])

    def test_help(self):
        """--help should not crash."""
        with self.assertRaises(SystemExit):
            main(["--help"])


class TestGitShow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        _git(["init", "-b", "main"], self.repo)
        _git(["config", "user.email", "test@test"], self.repo)
        _git(["config", "user.name", "Test"], self.repo)
        import ci_detect_changes as mod
        self.orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = self.repo

    def tearDown(self):
        import ci_detect_changes as mod
        mod.REPO_ROOT = self.orig_root
        self.temp_dir.cleanup()

    def test_file_exists(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "init"], self.repo)
        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("revision: 2\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "add yaml"], self.repo)
        sha = _git(["rev-parse", "HEAD"], self.repo).strip()
        result = git_show(sha, "ffmpeg/8.1.1.yaml")
        self.assertEqual(result, "revision: 2\n")

    def test_file_not_exists(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "init"], self.repo)
        sha = _git(["rev-parse", "HEAD"], self.repo).strip()
        result = git_show(sha, "ffmpeg/nonexistent.yaml")
        self.assertEqual(result, "")

    def test_file_added_in_later_commit(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "first"], self.repo)
        before = _git(["rev-parse", "HEAD"], self.repo).strip()
        _git(["rm", "--cached", "ffmpeg/.gitkeep"], self.repo)
        _git(["commit", "-m", "remove keep"], self.repo)
        (self.repo / "ffmpeg" / "6.5.yaml").write_text("revision: 0\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "add 6.5"], self.repo)
        after = _git(["rev-parse", "HEAD"], self.repo).strip()
        old_content = git_show(before, "ffmpeg/6.5.yaml")
        new_content = git_show(after, "ffmpeg/6.5.yaml")
        self.assertEqual(old_content, "")
        self.assertNotEqual(new_content, "")


class TestDetectChangesIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        _git(["init", "-b", "main"], self.repo)
        _git(["config", "user.email", "test@test"], self.repo)
        _git(["config", "user.name", "Test"], self.repo)
        import ci_detect_changes as mod
        self.orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = self.repo

    def tearDown(self):
        import ci_detect_changes as mod
        mod.REPO_ROOT = self.orig_root
        self.temp_dir.cleanup()

    def test_new_file_detected(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / ".gitkeep").write_text("")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "first"], self.repo)
        before = _git(["rev-parse", "HEAD"], self.repo).strip()
        _git(["rm", "--cached", "ffmpeg/.gitkeep"], self.repo)
        _git(["commit", "-m", "rm keep"], self.repo)
        (self.repo / "ffmpeg" / "6.5.yaml").write_text("extends: 6.1\nrevision: 0\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "add 6.5"], self.repo)
        after = _git(["rev-parse", "HEAD"], self.repo).strip()
        result = detect_changes(before, after)
        self.assertTrue(result.found)
        self.assertEqual(result.changed[0].version, "6.5")

    def test_revision_change_detected(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("extends: 8.1\nrevision: 2\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "base"], self.repo)
        before = _git(["rev-parse", "HEAD"], self.repo).strip()
        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("extends: 8.1\nrevision: 3\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "bump"], self.repo)
        after = _git(["rev-parse", "HEAD"], self.repo).strip()
        result = detect_changes(before, after)
        self.assertTrue(result.found)
        self.assertEqual(result.changed[0].version, "8.1.1")
        self.assertEqual(result.changed[0].revision, 3)

    def test_no_change(self):
        (self.repo / "ffmpeg").mkdir(parents=True)
        (self.repo / "ffmpeg" / "8.1.1.yaml").write_text("extends: 8.1\nrevision: 2\n")
        _git(["add", "-A"], self.repo)
        _git(["commit", "-m", "base"], self.repo)
        sha = _git(["rev-parse", "HEAD"], self.repo).strip()
        result = detect_changes(sha, sha)
        self.assertFalse(result.found)
        self.assertEqual(result.changed, [])


def _git(args: list[str], cwd: Path) -> str:
    import subprocess
    r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=str(cwd))
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout


if __name__ == "__main__":
    unittest.main()
