"""Tests for scripts/ci/compute_port_hash.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from compute_port_hash import compute_port_hash


class TestComputePortHash(unittest.TestCase):
    """Tests for the compute_port_hash function."""

    def test_deterministic_output(self):
        """Same files produce the same hash across multiple calls."""
        with tempfile.TemporaryDirectory() as tmp:
            ports = Path(tmp)
            (ports / "a.txt").write_text("hello", encoding="utf-8")
            (ports / "b.txt").write_text("world", encoding="utf-8")
            h1 = compute_port_hash(ports)
            h2 = compute_port_hash(ports)
            self.assertEqual(h1, h2)

    def test_different_files_produce_different_hash(self):
        """Different file sets produce different hashes."""
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            ports1 = Path(tmp1)
            ports2 = Path(tmp2)
            (ports1 / "x.txt").write_text("abc", encoding="utf-8")
            (ports2 / "y.txt").write_text("xyz", encoding="utf-8")
            h1 = compute_port_hash(ports1)
            h2 = compute_port_hash(ports2)
            self.assertNotEqual(h1, h2)

    def test_empty_directory(self):
        """Empty directory returns a valid SHA-256 hex digest (all uppercase)."""
        with tempfile.TemporaryDirectory() as tmp:
            ports = Path(tmp)
            h = compute_port_hash(ports)
            # SHA-256 of empty byte stream
            self.assertEqual(
                h, "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855"
            )
            self.assertEqual(len(h), 64)
            self.assertTrue(all(c in "0123456789ABCDEF" for c in h))

    def test_single_file(self):
        """Hash includes both relative path and file content.

        Same content under a different filename produces a different hash,
        proving the relative path is part of the hash input.
        """
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            ports1 = Path(tmp1)
            ports2 = Path(tmp2)
            (ports1 / "one.txt").write_text("content", encoding="utf-8")
            (ports2 / "two.txt").write_text("content", encoding="utf-8")
            h1 = compute_port_hash(ports1)
            h2 = compute_port_hash(ports2)
            self.assertNotEqual(h1, h2)

    def test_content_change_changes_hash(self):
        """Modifying file content changes the hash."""
        with tempfile.TemporaryDirectory() as tmp:
            ports = Path(tmp)
            f = ports / "data.txt"
            f.write_text("version 1", encoding="utf-8")
            h1 = compute_port_hash(ports)
            f.write_text("version 2", encoding="utf-8")
            h2 = compute_port_hash(ports)
            self.assertNotEqual(h1, h2)

    def test_file_ordering_does_not_affect_hash(self):
        """Sorted walk produces same hash regardless of filesystem creation order."""
        with tempfile.TemporaryDirectory() as tmp:
            ports = Path(tmp)
            # Create files in non-alphabetical order
            (ports / "c.txt").write_text("c", encoding="utf-8")
            (ports / "a.txt").write_text("a", encoding="utf-8")
            (ports / "b.txt").write_text("b", encoding="utf-8")
            h1 = compute_port_hash(ports)

            # Remove and recreate in a different order
            for name in ("c.txt", "a.txt", "b.txt"):
                (ports / name).unlink()
            (ports / "b.txt").write_text("b", encoding="utf-8")
            (ports / "c.txt").write_text("c", encoding="utf-8")
            (ports / "a.txt").write_text("a", encoding="utf-8")
            h2 = compute_port_hash(ports)

            self.assertEqual(h1, h2)

    def test_backslash_paths_normalized(self):
        """Backslash separators in relative paths are normalized to forward slashes.

        On Windows, ``str(rel)`` naturally produces backslash separators, so
        the function's ``.replace("\\\\", "/")`` is exercised on every
        subdirectory file.  The hash must be deterministic and valid.
        """
        with tempfile.TemporaryDirectory() as tmp:
            ports = Path(tmp)
            sub = ports / "subdir"
            sub.mkdir()
            (sub / "file.txt").write_text("data", encoding="utf-8")

            h = compute_port_hash(ports)
            # Must be a valid 64-char uppercase hex digest
            self.assertEqual(len(h), 64)
            self.assertTrue(all(c in "0123456789ABCDEF" for c in h))

            # Deterministic on repeat calls
            h2 = compute_port_hash(ports)
            self.assertEqual(h, h2)


if __name__ == "__main__":
    unittest.main()
