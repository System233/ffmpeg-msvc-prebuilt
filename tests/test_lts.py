"""Tests for scripts/ops/lts.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
from lts import is_lts


class TestIsLTS(unittest.TestCase):

    # ── Known LTS releases ──
    def test_4_4_is_lts(self):
        self.assertTrue(is_lts(4, 4))

    def test_5_1_is_lts(self):
        self.assertTrue(is_lts(5, 1))

    def test_7_1_is_lts(self):
        self.assertTrue(is_lts(7, 1))

    # ── Non-LTS releases ──
    def test_4_0_not_lts(self):
        self.assertFalse(is_lts(4, 0))

    def test_4_2_not_lts(self):
        self.assertFalse(is_lts(4, 2))

    def test_5_0_not_lts(self):
        self.assertFalse(is_lts(5, 0))

    def test_6_0_not_lts(self):
        self.assertFalse(is_lts(6, 0))

    def test_6_1_not_lts(self):
        """6.1 was NOT designated as an LTS by FFmpeg."""
        self.assertFalse(is_lts(6, 1))

    def test_8_0_not_lts(self):
        self.assertFalse(is_lts(8, 0))

    def test_8_1_not_lts(self):
        """8.1 was NOT designated as an LTS by FFmpeg."""
        self.assertFalse(is_lts(8, 1))

    def test_3_4_not_lts(self):
        self.assertFalse(is_lts(3, 4))


if __name__ == "__main__":
    unittest.main()
