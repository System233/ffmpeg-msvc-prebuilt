"""Tests for scripts/ci/manage_release.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from manage_release import _build_title, _build_notes


class TestBuildTitle(unittest.TestCase):
    """Tests for the _build_title pure function."""

    def test_snapshot_includes_snapshot_label(self):
        """When is_snapshot=True the title includes '(MSVC Prebuilt, Snapshot)'."""
        title = _build_title("n8.0-1234-gabc", is_snapshot=True)
        self.assertEqual(title, "FFmpeg n8.0-1234-gabc (MSVC Prebuilt, Snapshot)")

    def test_non_snapshot_excludes_snapshot(self):
        """When is_snapshot=False the title omits 'Snapshot'."""
        title = _build_title("8.1.1", is_snapshot=False)
        self.assertEqual(title, "FFmpeg 8.1.1 (MSVC Prebuilt)")
        self.assertNotIn("Snapshot", title)

    def test_various_version_strings(self):
        """The value string is always embedded in the title."""
        cases = [
            "8.1.1",
            "7.1-20260101",
            "n8.0-1234-gabc",
            "master",
        ]
        for v in cases:
            with self.subTest(version=v):
                title = _build_title(v, is_snapshot=False)
                self.assertIn(f"FFmpeg {v}", title)
                self.assertIn("(MSVC Prebuilt)", title)

    def test_snapshot_with_ref_string(self):
        """Snapshot label works with any arbitrary ref string."""
        title = _build_title("n7.1-5678-gdef", is_snapshot=True)
        self.assertEqual(title, "FFmpeg n7.1-5678-gdef (MSVC Prebuilt, Snapshot)")


class TestBuildNotes(unittest.TestCase):
    """Tests for the _build_notes pure function."""

    def test_returns_correct_format(self):
        """Notes embed the version in the standard sentence."""
        notes = _build_notes("8.1.1")
        expected = "Automated build of FFmpeg 8.1.1 using MSVC via vcpkg."
        self.assertEqual(notes, expected)

    def test_with_master_date_version(self):
        """Notes work with date-based version strings."""
        notes = _build_notes("7.1-20260101")
        expected = "Automated build of FFmpeg 7.1-20260101 using MSVC via vcpkg."
        self.assertEqual(notes, expected)

    def test_with_git_ref(self):
        """Notes work with git-ref-style version strings."""
        notes = _build_notes("n8.0-1234-gabc")
        expected = "Automated build of FFmpeg n8.0-1234-gabc using MSVC via vcpkg."
        self.assertEqual(notes, expected)


if __name__ == "__main__":
    unittest.main()
