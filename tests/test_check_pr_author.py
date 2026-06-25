"""Tests for scripts/ci/check_pr_author.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from check_pr_author import BOT_USERS


def is_authorized(author: str, permission: str | None) -> bool:
    """Mirror the check_pr_author logic for testing."""
    if author in BOT_USERS:
        return True
    return permission in ("admin", "write")


class TestBotUsers(unittest.TestCase):
    """Tests for the BOT_USERS module-level constant."""

    def test_contains_github_actions_bot(self):
        self.assertIn("github-actions[bot]", BOT_USERS)

    def test_contains_ffmpeg_dev_bot(self):
        self.assertIn("ffmpeg-dev[bot]", BOT_USERS)

    def test_random_user_not_in_bot_users(self):
        self.assertNotIn("random-user", BOT_USERS)

    def test_regular_maintainer_not_in_bot_users(self):
        self.assertNotIn("octocat", BOT_USERS)


class TestAuthorizationLogic(unittest.TestCase):
    """Tests for the authorization decision logic (bot + permission check)."""

    # --- Bot users always pass ---

    def test_github_actions_bot_authorized_without_permission(self):
        self.assertTrue(is_authorized("github-actions[bot]", None))

    def test_ffmpeg_dev_bot_authorized_with_read_permission(self):
        self.assertTrue(is_authorized("ffmpeg-dev[bot]", "read"))

    def test_github_actions_bot_authorized_regardless_of_permission(self):
        self.assertTrue(is_authorized("github-actions[bot]", "triage"))

    # --- Permission-level checks ---

    def test_admin_permission_authorized(self):
        self.assertTrue(is_authorized("maintainer", "admin"))

    def test_write_permission_authorized(self):
        self.assertTrue(is_authorized("contributor", "write"))

    def test_read_permission_not_authorized(self):
        self.assertFalse(is_authorized("viewer", "read"))

    def test_triage_permission_not_authorized(self):
        self.assertFalse(is_authorized("triage-user", "triage"))

    def test_none_permission_not_authorized(self):
        self.assertFalse(is_authorized("rando", None))

    def test_maintain_permission_not_authorized(self):
        """Only admin/write pass; 'maintain' is not in the allowlist."""
        self.assertFalse(is_authorized("maintainer", "maintain"))


if __name__ == "__main__":
    unittest.main()
