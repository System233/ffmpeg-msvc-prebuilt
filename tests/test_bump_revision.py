"""Tests for scripts/ci/bump_revision.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from bump_revision import bump


class TestBump(unittest.TestCase):
    """Tests for the bump function."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _yaml(self, content: str) -> Path:
        """Write *content* to a temp YAML file and return its Path."""
        p = Path(self._tmpdir.name) / "test.yaml"
        p.write_text(content, encoding="utf-8")
        return p

    # ------------------------------------------------------------------
    # Basic increment behavior
    # ------------------------------------------------------------------

    def test_increments_revision_from_2_to_3(self):
        """Revision 2 bumps to 3 and file is updated."""
        p = self._yaml("revision: 2\n")
        before, after = bump(p)
        self.assertEqual(before, 2)
        self.assertEqual(after, 3)
        self.assertIn("revision: 3", p.read_text(encoding="utf-8"))

    def test_increments_revision_from_0_to_1(self):
        """Revision 0 bumps to 1."""
        p = self._yaml("revision: 0\n")
        before, after = bump(p)
        self.assertEqual(before, 0)
        self.assertEqual(after, 1)
        self.assertIn("revision: 1", p.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Return value
    # ------------------------------------------------------------------

    def test_returns_correct_tuple(self):
        """The (before, after) tuple matches the actual revision change."""
        p = self._yaml("revision: 7\n")
        self.assertEqual(bump(p), (7, 8))

    # ------------------------------------------------------------------
    # File content fidelity
    # ------------------------------------------------------------------

    def test_file_content_written_correctly(self):
        """Non-revision lines are preserved when the file is rewritten."""
        p = self._yaml("something: else\nrevision: 5\nmore: data\n")
        bump(p)
        content = p.read_text(encoding="utf-8")
        self.assertIn("revision: 6", content)
        self.assertIn("something: else", content)
        self.assertIn("more: data", content)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_raises_system_exit_when_no_revision(self):
        """A file without a 'revision:' field triggers SystemExit."""
        p = self._yaml("foo: bar\nbaz: qux\n")
        with self.assertRaises(SystemExit):
            bump(p)

    # ------------------------------------------------------------------
    # Multi-revision guard
    # ------------------------------------------------------------------

    def test_only_bumps_first_revision(self):
        """Only the first ``revision:`` field is incremented."""
        p = self._yaml("revision: 10\nrevision: 20\n")
        bump(p)
        content = p.read_text(encoding="utf-8")
        self.assertIn("revision: 11", content)
        # The second occurrence must remain untouched
        self.assertIn("revision: 20", content)

    # ------------------------------------------------------------------
    # Whitespace tolerance
    # ------------------------------------------------------------------

    def test_revision_with_extra_spaces(self):
        """Extra whitespace after the colon is preserved."""
        p = self._yaml("revision:   5\n")
        before, after = bump(p)
        self.assertEqual(before, 5)
        self.assertEqual(after, 6)
        content = p.read_text(encoding="utf-8")
        # The spacing before the digit must be kept
        self.assertIn("revision:   6", content)


if __name__ == "__main__":
    unittest.main()
