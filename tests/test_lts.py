"""Tests for scripts/ops/lts.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
from lts import is_lts, is_lts_version


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

    # ── Version-string checks (release vs dev snapshot) ──
    def test_9_1_dev_snapshot_not_lts(self):
        """9.1-dev master snapshots must NOT be treated as LTS."""
        self.assertFalse(is_lts_version("9.1-dev-829-g6092f06"))
        self.assertFalse(is_lts_version("n9.1-dev-829-g6092f06"))

    def test_8_2_dev_snapshot_not_lts(self):
        self.assertFalse(is_lts_version("8.2-dev-1873-gc6bb22d"))

    def test_dated_build_not_lts(self):
        """Dated branch builds (7.1-20260101) are not official releases."""
        self.assertFalse(is_lts_version("7.1-20260101"))
        self.assertFalse(is_lts_version("7.1-20260101+dev-10-gabcd"))

    def test_master_not_lts(self):
        self.assertFalse(is_lts_version("master"))
        self.assertFalse(is_lts_version(""))

    def test_release_versions_unchanged(self):
        self.assertTrue(is_lts_version("5.1"))
        self.assertTrue(is_lts_version("5.1.10"))
        self.assertTrue(is_lts_version("7.1.5"))
        self.assertTrue(is_lts_version("n7.1.5"))
        self.assertTrue(is_lts_version("4.4.8"))
        self.assertTrue(is_lts_version("9.1"))  # next official LTS release
        self.assertFalse(is_lts_version("9.0"))
        self.assertFalse(is_lts_version("9.0.1"))
        self.assertFalse(is_lts_version("6.1"))
        self.assertFalse(is_lts_version("8.1.2"))


if __name__ == "__main__":
    unittest.main()
