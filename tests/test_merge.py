"""Tests for scripts/ffport/merge.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ffport"))
from merge import deep_merge


class TestDeepMerge(unittest.TestCase):

    def test_empty_override(self):
        self.assertEqual(deep_merge({"a": 1}, {}), {"a": 1})

    def test_empty_base(self):
        self.assertEqual(deep_merge({}, {"a": 1}), {"a": 1})

    def test_scalar_replace(self):
        self.assertEqual(deep_merge({"a": 1}, {"a": 2}), {"a": 2})

    def test_new_key_added(self):
        self.assertEqual(deep_merge({"a": 1}, {"b": 2}), {"a": 1, "b": 2})

    def test_recursive_dict(self):
        result = deep_merge({"a": {"x": 1}}, {"a": {"y": 2}})
        self.assertEqual(result, {"a": {"x": 1, "y": 2}})

    def test_recursive_overwrite_scalar(self):
        result = deep_merge({"a": {"x": 1}}, {"a": "scalar"})
        self.assertEqual(result, {"a": "scalar"})

    def test_delete_key_via_none(self):
        result = deep_merge({"a": 1, "b": 2}, {"a": None})
        self.assertEqual(result, {"b": 2})

    def test_delete_missing_key(self):
        result = deep_merge({"a": 1}, {"missing": None})
        self.assertEqual(result, {"a": 1})

    def test_list_replace(self):
        result = deep_merge({"a": [1, 2]}, {"a": [3]})
        self.assertEqual(result, {"a": [3]})

    def test_nested_multi_level(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 99}}}
        expected = {"a": {"b": {"c": 99, "d": 2}}}
        self.assertEqual(deep_merge(base, override), expected)

    def test_empty_dict_overwrite(self):
        result = deep_merge({"a": 1}, {"a": {}})
        self.assertEqual(result, {"a": {}})

    def test_none_delete_nested(self):
        result = deep_merge({"a": {"b": 1}}, {"a": {"b": None}})
        self.assertEqual(result, {"a": {}})

    def test_original_not_mutated(self):
        base = {"a": 1, "b": {"c": 2}}
        deep_merge(base, {"b": {"c": 99}})
        self.assertEqual(base, {"a": 1, "b": {"c": 2}})

    def test_false_values_preserved(self):
        result = deep_merge({"a": True}, {"a": False})
        self.assertEqual(result, {"a": False})

    def test_zero_values_preserved(self):
        result = deep_merge({"a": 1}, {"a": 0})
        self.assertEqual(result, {"a": 0})


if __name__ == "__main__":
    unittest.main()
