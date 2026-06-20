"""Tests for scripts/ffport/version.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ffport"))
from version import parse_version


class TestParseVersion(unittest.TestCase):

    # ── Rule 1: Git describe ──
    def test_git_describe_simple(self):
        r = parse_version("n8.1.1-50-gabc1234")
        self.assertEqual(r["version"], "8.1.1-50-gabc1234")
        self.assertEqual(r["commit"], "abc1234")
        self.assertEqual(r["ref"], "n8.1.1-50-gabc1234")
        self.assertEqual(r["base_version"], "8.1.1")

    def test_git_describe_no_patch(self):
        r = parse_version("n8.1-10-gdeadbeef")
        self.assertEqual(r["version"], "8.1-10-gdeadbeef")
        self.assertEqual(r["base_version"], "8.1")

    def test_git_describe_two_digit_count(self):
        r = parse_version("n7.1.2-123-gabcdef0")
        self.assertEqual(r["commit"], "abcdef0")
        self.assertEqual(r["base_version"], "7.1.2")

    def test_git_describe_with_dash_in_suffix(self):
        r = parse_version("n8.0-custom-50-gabc1234")
        self.assertEqual(r["version"], "8.0-custom-50-gabc1234")
        self.assertEqual(r["commit"], "abc1234")

    # ── Rule 2: Version + tag ──
    def test_version_tag(self):
        r = parse_version("8.1-20260617")
        self.assertEqual(r["version"], "8.1-20260617")
        self.assertIsNone(r["commit"])
        self.assertIsNone(r["ref"])
        self.assertEqual(r["base_version"], "8.1")

    def test_version_tag_with_patch(self):
        r = parse_version("8.1.1-20260617")
        self.assertEqual(r["version"], "8.1.1-20260617")
        self.assertEqual(r["base_version"], "8.1.1")

    def test_version_tag_with_letters(self):
        r = parse_version("7.1-rc1")
        self.assertEqual(r["version"], "7.1-rc1")

    def test_version_tag_rejected_with_dash_in_tag(self):
        with self.assertRaises(ValueError):
            parse_version("8.1-rc-1")

    # ── Rule 3: Plain version ──
    def test_plain_major_minor(self):
        r = parse_version("8.1")
        self.assertEqual(r["version"], "8.1")
        self.assertIsNone(r["commit"])
        self.assertEqual(r["base_version"], "8.1")

    def test_plain_major_minor_patch(self):
        r = parse_version("8.1.1")
        self.assertEqual(r["version"], "8.1.1")
        self.assertEqual(r["base_version"], "8.1.1")

    # ── Invalid inputs ──
    def test_empty_string(self):
        with self.assertRaises(ValueError):
            parse_version("")

    def test_no_n_prefix_describe(self):
        """Without n prefix, Rule 1 won't match, falls through rules."""
        with self.assertRaises(ValueError):
            parse_version("8.1.1-50-gabc1234")

    def test_garbage(self):
        with self.assertRaises(ValueError):
            parse_version("not-a-version")

    def test_numeric_only(self):
        with self.assertRaises(ValueError):
            parse_version("123")

    def test_leading_v(self):
        with self.assertRaises(ValueError):
            parse_version("v8.1.1")


if __name__ == "__main__":
    unittest.main()
