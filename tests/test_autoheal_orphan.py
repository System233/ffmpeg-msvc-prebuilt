"""Real local Git-tree simulations for safe Auto-Heal orphan-branch recovery.

No GitHub requests, pushes, external tools beyond local Git, or FFmpeg builds.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ffbuild.autoheal import delivery
from ffbuild.autoheal.ledger import branch_name

SIGNATURE = "b" * 64
REPO = "example/ffmpeg"


class OrphanRecoveryTests(unittest.TestCase):
    def setUp(self):
        environ = mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO})
        environ.start()
        self.addCleanup(environ.stop)

    def _repository(self, directory: Path):
        def git(*args):
            return subprocess.run(["git", *args], cwd=directory, check=True,
                                  capture_output=True, text=True).stdout.strip()

        (directory / "ffmpeg").mkdir()
        (directory / "ffmpeg" / "8.1.1.yaml").write_text("patches: []\n",
                                                       encoding="utf-8")
        git("init", "-q")
        git("config", "user.name", "ffmpeg-dev[bot]")
        git("config", "user.email",
            "295689149+ffmpeg-dev[bot]@users.noreply.github.com")
        git("add", "--all")
        git("commit", "-qm", "baseline")
        base = git("rev-parse", "HEAD")
        (directory / "ffmpeg" / "8.1.1.yaml").write_text(
            "patches: []\nrevision: 1\n", encoding="utf-8")
        git("add", "--all")
        git("commit", "-m", "fix(8.1.1): automatically repair failed MSVC build",
            "-m", f"Autoheal-Round: 1\nAutoheal-Incident: {SIGNATURE}\n"
                  "Autoheal-Source-Run: 101\nAutoheal-Source-Attempt: 1\n"
                  "Autoheal-Hypothesis: Repair config")
        sha = git("rev-parse", "HEAD")
        patch = directory / "repair.patch"
        patch.write_bytes(subprocess.run(
            ["git", "format-patch", "-1", "--stdout"], cwd=directory,
            check=True, capture_output=True).stdout)
        return base, sha, patch, git

    @staticmethod
    def _detail(base: str, sha: str, *, author: str = "ffmpeg-dev[bot]"):
        return {
            "sha": sha,
            "author": {"login": author},
            "committer": {"login": author},
            "commit": {"message":
                       "fix(8.1.1): automatically repair failed MSVC build\n\n"
                       "Autoheal-Round: 1\n"
                       f"Autoheal-Incident: {SIGNATURE}\n"
                       "Autoheal-Source-Run: 101\n"
                       "Autoheal-Source-Attempt: 1\n"
                       "Autoheal-Hypothesis: Repair config"},
            "parents": [{"sha": base}],
            "files": [{"filename": "ffmpeg/8.1.1.yaml", "status": "modified"}],
        }

    def _invoke(self, root: Path, base: str, sha: str, patch: Path,
                git_local, *, author: str = "ffmpeg-dev[bot]"):
        branch = branch_name("8.1.1", SIGNATURE)
        remote = f"{sha}\trefs/heads/{branch}"
        detail = self._detail(base, sha, author=author)
        def local_git(*args, cwd=None):
            if args[:2] == ("fetch", "origin"):
                # The same local Git object is the simulated remote commit.
                return ""
            return delivery.git_original(*args, cwd=cwd or root)

        fake_pr = {
            "number": 42, "user": {"login": "ffmpeg-dev[bot]"},
            "head": {"ref": branch, "sha": sha,
                     "repo": {"full_name": REPO}},
            "base": {"ref": "main"}, "state": "open",
        }
        report = {"source": {"run_id": 101, "run_attempt": 1}}
        native_run = delivery.run
        def fake_run(*args, cwd=None):
            if args[0] == "git":
                return native_run(*args, cwd=cwd)
            if args[:3] == ("gh", "pr", "create"):
                return ""
            raise AssertionError(f"Unexpected command: {args}")
        with mock.patch.object(delivery, "git", side_effect=local_git), \
             mock.patch.object(delivery.github, "api", return_value=detail), \
             mock.patch.object(delivery, "find_pr", return_value=fake_pr), \
             mock.patch.object(delivery, "run", side_effect=fake_run) as gh, \
             mock.patch.object(delivery, "_resume_submitted_pr",
                               return_value=True) as resume:
            delivery._recover_orphan(branch, remote, base, SIGNATURE,
                                     report, "8.1.1", patch,
                                     ["ffmpeg/8.1.1.yaml"])
            return sum(call.args[0] == "gh" for call in gh.call_args_list), resume.call_count

    def test_exact_bot_tree_can_recover_missing_pr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, sha, patch, git_local = self._repository(root)
            delivery.git_original = delivery.git
            try:
                gh_calls, resume_calls = self._invoke(root, base, sha, patch, git_local)
            finally:
                del delivery.git_original
            self.assertEqual((1, 1), (gh_calls, resume_calls))

    def test_untrusted_orphan_author_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, sha, patch, git_local = self._repository(root)
            delivery.git_original = delivery.git
            try:
                with self.assertRaisesRegex(ValueError, "belongs to the GitHub bot"):
                    self._invoke(root, base, sha, patch, git_local, author="someone-else")
            finally:
                del delivery.git_original

    def test_different_tree_cannot_be_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, sha, patch, git_local = self._repository(root)
            data = patch.read_bytes()
            self.assertIn(b"+revision: 1", data)
            patch.write_bytes(data.replace(b"+revision: 1", b"+revision: 2"))
            delivery.git_original = delivery.git
            try:
                with self.assertRaisesRegex(ValueError, "tree differs"):
                    self._invoke(root, base, sha, patch, git_local)
            finally:
                del delivery.git_original


if __name__ == "__main__":
    unittest.main()
