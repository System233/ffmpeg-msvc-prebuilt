"""Tests for scripts/ci/cleanup_releases.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from cleanup_releases import _parse_lines


class TestParseLines(unittest.TestCase):
    """Tests for the _parse_lines helper."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _file(self, content: str) -> Path:
        """Write *content* to a temporary file and return its Path."""
        p = Path(self._tmpdir.name) / "cleanup.txt"
        p.write_text(content, encoding="utf-8")
        return p

    # ------------------------------------------------------------------
    # DELETE_RELEASE parsing
    # ------------------------------------------------------------------

    def test_parses_delete_release_lines(self):
        """DELETE_RELEASE: lines extract the tag name after the prefix."""
        p = self._file("DELETE_RELEASE:ffmpeg-8.1.1-r2\nDELETE_RELEASE:ffmpeg-7.1\n")
        tags = _parse_lines(p, "DELETE_RELEASE:")
        self.assertEqual(tags, ["ffmpeg-8.1.1-r2", "ffmpeg-7.1"])

    # ------------------------------------------------------------------
    # DELETE_TAG parsing
    # ------------------------------------------------------------------

    def test_parses_delete_tag_lines(self):
        """DELETE_TAG: lines extract the tag name after the prefix."""
        p = self._file("DELETE_TAG:old-tag\nDELETE_TAG:another-tag\n")
        tags = _parse_lines(p, "DELETE_TAG:")
        self.assertEqual(tags, ["old-tag", "another-tag"])

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_file(self):
        """An empty file yields an empty list."""
        p = self._file("")
        tags = _parse_lines(p, "DELETE_RELEASE:")
        self.assertEqual(tags, [])

    def test_lines_without_matching_prefix_ignored(self):
        """Lines that do not start with the requested prefix are skipped."""
        p = self._file(
            "KEEP_RELEASE:ffmpeg-8.0\nDELETE_RELEASE:ffmpeg-7.1\n"
        )
        tags = _parse_lines(p, "DELETE_RELEASE:")
        self.assertEqual(tags, ["ffmpeg-7.1"])

    def test_prefix_with_no_tag_ignored(self):
        """A line with the prefix but no tag value is ignored."""
        p = self._file("DELETE_RELEASE:\nDELETE_RELEASE:ffmpeg-8.0\n")
        tags = _parse_lines(p, "DELETE_RELEASE:")
        self.assertEqual(tags, ["ffmpeg-8.0"])

    def test_multiple_lines_same_prefix(self):
        """All matching lines are collected."""
        p = self._file("DELETE_RELEASE:a\nDELETE_RELEASE:b\nDELETE_RELEASE:c\n")
        tags = _parse_lines(p, "DELETE_RELEASE:")
        self.assertEqual(tags, ["a", "b", "c"])

    def test_mixed_prefixes_only_matching_collected(self):
        """When the file mixes prefixes, only the requested one is extracted."""
        p = self._file(
            "DELETE_RELEASE:rel-a\nDELETE_TAG:tag-b\nDELETE_RELEASE:rel-c\n"
        )
        tags = _parse_lines(p, "DELETE_RELEASE:")
        self.assertEqual(tags, ["rel-a", "rel-c"])


if __name__ == "__main__":
    unittest.main()
