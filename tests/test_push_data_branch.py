"""Tests for scripts/ci/push_data_branch.py."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from push_data_branch import (
    has_staged_changes,
    git_config,
    git_add_all,
    git_commit,
    git_push,
)


class TestHasStagedChanges(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("push_data_branch.subprocess.run")
        self.mock_run = patcher.start()
        self.addCleanup(patcher.stop)

    def test_no_changes(self):
        """git diff --staged --quiet returns 0 → False (no changes)."""
        self.mock_run.return_value = mock.Mock(returncode=0)
        result = has_staged_changes("data")
        self.assertFalse(result)

    def test_has_changes(self):
        """git diff --staged --quiet returns 1 → True (has changes)."""
        self.mock_run.return_value = mock.Mock(returncode=1)
        result = has_staged_changes("data")
        self.assertTrue(result)

    def test_error_exit_code(self):
        """git diff --staged --quiet returns 128 → raises CalledProcessError."""
        mock_result = mock.Mock(returncode=128)
        mock_result.check_returncode.side_effect = subprocess.CalledProcessError(
            128, "git diff --staged --quiet"
        )
        self.mock_run.return_value = mock_result
        with self.assertRaises(subprocess.CalledProcessError):
            has_staged_changes("data")


class TestGitPushRetry(unittest.TestCase):
    def setUp(self):
        patcher_run = mock.patch("push_data_branch.subprocess.run")
        self.mock_run = patcher_run.start()
        self.addCleanup(patcher_run.stop)
        patcher_sleep = mock.patch("push_data_branch.time.sleep")
        self.mock_sleep = patcher_sleep.start()
        self.addCleanup(patcher_sleep.stop)

    def test_first_attempt_succeeds(self):
        """First attempt succeeds → returns without retry."""
        git_push("data", "main", max_retries=3, delay=5.0)
        self.assertEqual(self.mock_run.call_count, 2)  # pull + push
        self.mock_sleep.assert_not_called()
        self.mock_run.assert_has_calls([
            mock.call(
                ["git", "pull", "--rebase", "origin", "main"],
                cwd="data", check=True,
            ),
            mock.call(
                ["git", "push", "origin", "main"],
                cwd="data", check=True,
            ),
        ])

    def test_first_attempt_fails_second_succeeds(self):
        """First attempt fails, second succeeds.

        When the first pull raises, the subsequent push on the same attempt
        is never executed, so only 3 subprocess.run calls happen total.
        """
        self.mock_run.side_effect = [
            subprocess.CalledProcessError(1, "git"),  # attempt 1 pull → raises
            mock.DEFAULT,  # attempt 2 pull → succeeds
            mock.DEFAULT,  # attempt 2 push → succeeds
        ]
        git_push("data", "main", max_retries=3, delay=5.0)
        self.mock_sleep.assert_called_once_with(5.0)
        self.assertEqual(self.mock_run.call_count, 3)

    def test_all_attempts_fail(self):
        """All attempts fail → raises CalledProcessError on last attempt."""
        self.mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        with self.assertRaises(subprocess.CalledProcessError):
            git_push("data", "main", max_retries=3, delay=5.0)
        self.assertEqual(self.mock_sleep.call_count, 2)  # slept after attempts 1 and 2

    def test_sleep_called_between_retries(self):
        """Verify time.sleep is called with correct delay between retries."""
        self.mock_run.side_effect = [
            subprocess.CalledProcessError(1, "git"),
            mock.DEFAULT,  # attempt 2 pull
            mock.DEFAULT,  # attempt 2 push
        ]
        git_push("data", "main", max_retries=3, delay=2.5)
        self.mock_sleep.assert_called_once_with(2.5)

    def test_correct_git_commands_called(self):
        """Verify pull --rebase + push commands for the target branch."""
        git_push("/tmp/repo", "data-branch", max_retries=1, delay=5.0)
        self.mock_run.assert_has_calls([
            mock.call(
                ["git", "pull", "--rebase", "origin", "data-branch"],
                cwd="/tmp/repo", check=True,
            ),
            mock.call(
                ["git", "push", "origin", "data-branch"],
                cwd="/tmp/repo", check=True,
            ),
        ])


class TestIntegration(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("push_data_branch.subprocess.run")
        self.mock_run = patcher.start()
        self.addCleanup(patcher.stop)

    def test_full_flow(self):
        """Test the full flow by mocking all subprocess calls."""
        call_results = []

        def side_effect(*args, **kwargs):
            cmd = args[0]
            call_results.append(cmd)
            # git diff --staged --quiet → returncode=1 means has changes
            if cmd[0] == "git" and cmd[1] == "diff":
                return mock.Mock(returncode=1)
            return mock.Mock(returncode=0)

        self.mock_run.side_effect = side_effect

        # Simulate the full flow from main()
        git_config("data", "user.name", "github-actions[bot]")
        git_config("data", "user.email", "github-actions[bot]@users.noreply.github.com")
        git_add_all("data")

        self.assertTrue(has_staged_changes("data"))

        git_commit("data", "test commit")
        git_push("data", "data", max_retries=3, delay=5.0)

        expected_commands = [
            ["git", "config", "user.name", "github-actions[bot]"],
            ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
            ["git", "add", "-A"],
            ["git", "diff", "--staged", "--quiet"],  # has_staged_changes
            ["git", "commit", "-m", "test commit"],
            ["git", "pull", "--rebase", "origin", "data"],
            ["git", "push", "origin", "data"],
        ]
        for i, expected in enumerate(expected_commands):
            self.assertEqual(call_results[i], expected)
        self.assertEqual(len(call_results), len(expected_commands))


if __name__ == "__main__":
    unittest.main()
