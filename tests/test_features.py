"""Unit tests for scripts/ffport/features.py."""
import sys
import unittest
from pathlib import Path

# Add scripts/ffport to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ffport"))

from features import (
    expand_items,
    apply_exclusions,
    version_gate_match,
    resolve_features,
    collect_deps,
    _normalise_list,
)


class TestNormaliseList(unittest.TestCase):
    """_normalise_list: convert various inputs to list."""

    def test_string(self):
        self.assertEqual(_normalise_list("foo"), ["foo"])

    def test_empty_string(self):
        self.assertEqual(_normalise_list(""), [""])

    def test_dict(self):
        self.assertEqual(_normalise_list({"a": 1}), [{"a": 1}])

    def test_list(self):
        self.assertEqual(_normalise_list(["a", "b"]), ["a", "b"])

    def test_none(self):
        self.assertEqual(_normalise_list(None), [])

    def test_int_zero(self):
        self.assertEqual(_normalise_list(0), [])

    def test_empty_list(self):
        self.assertEqual(_normalise_list([]), [])

    def test_false(self):
        self.assertEqual(_normalise_list(False), [])


class TestExpandItems(unittest.TestCase):
    """expand_items: resolve @aliases into flat feature name set."""

    def test_plain_list(self):
        result = expand_items(["a", "b"], {})
        self.assertEqual(result, {"a", "b"})

    def test_empty(self):
        result = expand_items([], {})
        self.assertEqual(result, set())

    def test_at_ref_in_defines(self):
        defines = {"mygroup": ["x", "y"]}
        result = expand_items(["@mygroup"], defines)
        self.assertEqual(result, {"x", "y"})

    def test_at_ref_in_registry(self):
        defines = {}
        registry = {"z": {}}
        result = expand_items(["@z"], defines, registry)
        self.assertEqual(result, {"z"})

    def test_at_ref_not_found(self):
        result = expand_items(["@missing"], {}, {"other": {}})
        # Not found in defines or registry → silently skipped
        self.assertEqual(result, set())

    def test_comma_separated(self):
        result = expand_items(["a,b"], {})
        self.assertEqual(result, {"a", "b"})

    def test_comma_with_spaces(self):
        result = expand_items(["a, b, c"], {})
        self.assertEqual(result, {"a", "b", "c"})

    def test_nested_at_refs(self):
        defines = {"top": ["@mid"], "mid": ["a", "b"]}
        result = expand_items(["@top"], defines)
        self.assertEqual(result, {"a", "b"})

    def test_circular_ref(self):
        defines = {"a": ["@b"], "b": ["@a"]}
        # Should raise RecursionError, not hang
        with self.assertRaises(RecursionError):
            expand_items(["@a"], defines)

    def test_mixed_plain_and_at(self):
        defines = {"g": ["x"]}
        result = expand_items(["a", "@g", "b"], defines)
        self.assertEqual(result, {"a", "b", "x"})

    def test_list_nested_items(self):
        result = expand_items([["a", "b"], "c"], {})
        self.assertEqual(result, {"a", "b", "c"})

    def test_empty_string_skipped(self):
        result = expand_items(["", "a"], {})
        self.assertEqual(result, {"a"})

    def test_whitespace_stripped(self):
        result = expand_items(["  a  ", "b"], {})
        self.assertEqual(result, {"a", "b"})


class TestApplyExclusions(unittest.TestCase):
    """apply_exclusions: fnmatch-based exclusion filtering."""

    def test_no_exclusions(self):
        result = apply_exclusions({"a", "b"}, set())
        self.assertEqual(result, {"a", "b"})

    def test_exact_match(self):
        result = apply_exclusions({"a", "b"}, {"a"})
        self.assertEqual(result, {"b"})

    def test_wildcard(self):
        result = apply_exclusions({"libA", "libB", "toolC"}, {"lib*"})
        self.assertEqual(result, {"toolC"})

    def test_multiple_patterns(self):
        result = apply_exclusions({"a", "b", "c", "d"}, {"a", "b"})
        self.assertEqual(result, {"c", "d"})

    def test_no_match(self):
        result = apply_exclusions({"a"}, {"z*"})
        self.assertEqual(result, {"a"})

    def test_empty_items(self):
        result = apply_exclusions(set(), {"*"})
        self.assertEqual(result, set())

    def test_double_wildcard(self):
        result = apply_exclusions({"a", "ab", "abc"}, {"ab*"})
        self.assertEqual(result, {"a"})

    def test_all_excluded(self):
        result = apply_exclusions({"a", "b"}, {"*"})
        self.assertEqual(result, set())


class TestVersionGateMatch(unittest.TestCase):
    """version_gate_match: version constraint evaluation."""

    # ── Valid operators ──
    def test_ge_match(self):
        self.assertTrue(version_gate_match(">=6.0", "8.1.1"))

    def test_ge_no_match(self):
        self.assertFalse(version_gate_match(">=9.0", "8.1.1"))

    def test_le_match(self):
        self.assertTrue(version_gate_match("<=8.0", "8.0"))

    def test_le_no_match(self):
        self.assertFalse(version_gate_match("<=8.0", "8.1"))

    def test_gt_match(self):
        self.assertTrue(version_gate_match(">6.0", "6.1"))

    def test_gt_no_match(self):
        self.assertFalse(version_gate_match(">6.0", "6.0"))

    def test_lt_match(self):
        self.assertTrue(version_gate_match("<8.0", "7.1"))

    def test_lt_no_match(self):
        self.assertFalse(version_gate_match("<8.0", "8.0"))

    # ── Invalid operators (silently ignored in original code) ──
    def test_invalid_eq_operator(self):
        self.assertFalse(version_gate_match("==8.0", "8.1.1"))

    def test_invalid_not_operator(self):
        self.assertFalse(version_gate_match("!6.0", "8.1.1"))

    def test_invalid_bang_operator(self):
        self.assertFalse(version_gate_match("!=6.0", "8.1.1"))

    # ── Non-numeric version parts ──
    def test_non_numeric_gate(self):
        self.assertFalse(version_gate_match(">=8.O", "8.1.1"))

    def test_non_numeric_target(self):
        self.assertFalse(version_gate_match(">=6.0", "abc"))

    # ── Edge cases ──
    def test_empty_gate(self):
        self.assertTrue(version_gate_match("", "8.1.1"))

    def test_none_gate(self):
        self.assertTrue(version_gate_match(None, "8.1.1"))

    def test_three_part_version(self):
        self.assertTrue(version_gate_match(">=6.0", "6.1.2"))

    def test_single_part_version(self):
        self.assertTrue(version_gate_match(">=6", "6"))

    def test_equal_boundary(self):
        self.assertTrue(version_gate_match(">=8.1.1", "8.1.1"))

    def test_lt_equal_boundary(self):
        self.assertFalse(version_gate_match("<8.1.1", "8.1.1"))

    # ── Comma OR groups ──
    def test_or_group_first_matches(self):
        self.assertTrue(version_gate_match("<5.0,>=7.0", "8.0"))

    def test_or_group_second_matches(self):
        self.assertTrue(version_gate_match("<5.0,>=7.0", "4.0"))

    def test_or_group_none_match(self):
        self.assertFalse(version_gate_match("<5.0,>=7.0", "6.0"))

    # ── Space AND groups ──
    def test_and_group_both_match(self):
        self.assertTrue(version_gate_match(">=6.0 <8.0", "7.0"))

    def test_and_group_one_fails(self):
        self.assertFalse(version_gate_match(">=6.0 <7.0", "7.5"))

    def test_complex_or_and(self):
        self.assertTrue(version_gate_match(">=6.0 <7.0, >=8.0", "8.1"))


class TestResolveFeatures(unittest.TestCase):
    """resolve_features: full feature resolution pipeline."""

    REGISTRY = {
        "libA": {"description": "A"},
        "libB": {"description": "B"},
        "libC": {"description": "C"},
    }

    # ── Basic include/exclude ──
    def test_no_define(self):
        r = resolve_features({"features": dict(self.REGISTRY)})
        self.assertEqual(set(r["features"].keys()), {"libA", "libB", "libC"})
        self.assertEqual(r["defaults"], [])

    def test_include_all(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"include": ["libA", "libB", "libC"]},
        })
        self.assertEqual(set(r["features"].keys()), {"libA", "libB", "libC"})

    def test_include_subset(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"include": ["libA", "libB"]},
        })
        self.assertEqual(set(r["features"].keys()), {"libA", "libB"})

    def test_exclude(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"exclude": ["libB"]},
        })
        self.assertEqual(set(r["features"].keys()), {"libA", "libC"})

    def test_include_and_exclude(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"include": ["libA", "libB"], "exclude": ["libB"]},
        })
        self.assertEqual(set(r["features"].keys()), {"libA"})

    def test_exclude_wildcard(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"exclude": ["lib*"]},
        })
        self.assertEqual(set(r["features"].keys()), set())

    def test_empty_include(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"include": []},
        })
        self.assertEqual(set(r["features"].keys()), set())

    def test_empty_exclude(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"exclude": []},
        })
        self.assertEqual(set(r["features"].keys()), {"libA", "libB", "libC"})

    # ── Defaults ──
    def test_defaults_bare_name(self):
        r = resolve_features({
            "features": {"libA": {}, "libB": {}},
            "define": {"defaults": ["libA"]},
        })
        self.assertEqual(r["defaults"], ["libA"])

    def test_defaults_at_ref(self):
        r = resolve_features({
            "features": {"libA": {}, "libB": {}},
            "define": {"defaults": ["@libA"]},
        })
        self.assertEqual(r["defaults"], ["libA"])

    def test_defaults_excluded(self):
        """Defaults must be subset of included (excluded defaults discarded)."""
        r = resolve_features({
            "features": {"libA": {}, "libB": {}},
            "define": {"include": ["libA"], "defaults": ["libB"]},
        })
        self.assertEqual(r["defaults"], [])
        self.assertNotIn("libB", r["features"])

    def test_defaults_at_ref_excluded(self):
        r = resolve_features({
            "features": {"libA": {}, "libB": {}},
            "define": {"include": ["libA"], "defaults": ["@libB"]},
        })
        self.assertEqual(r["defaults"], [])

    def test_defaults_not_in_registry(self):
        r = resolve_features({
            "features": {"libA": {}},
            "define": {"defaults": ["missing"]},
        })
        self.assertEqual(r["defaults"], [])
        self.assertNotIn("missing", r["features"])

    # ── Version gating ──
    def test_version_gate_included(self):
        r = resolve_features({
            "features": {"libA": {"version": ">=7.0"}},
            "define": {"include": ["libA"]},
        }, version_str="8.0")
        self.assertIn("libA", r["features"])

    def test_version_gate_excluded(self):
        r = resolve_features({
            "features": {"libA": {"version": "<5.0"}},
            "define": {"include": ["libA"]},
        }, version_str="8.0")
        self.assertNotIn("libA", r["features"])

    def test_version_gate_complex(self):
        r = resolve_features({
            "features": {"libA": {"version": ">=6.0 <8.0, >=9.0"}},
            "define": {"include": ["libA"]},
        }, version_str="8.1")
        self.assertNotIn("libA", r["features"])

    # ── Auto-include @depends references ──
    def test_auto_include_depends_ref(self):
        r = resolve_features({
            "features": {
                "libA": {"depends": ["@libB"]},
                "libB": {},
            },
            "define": {"include": ["libA"]},
        })
        self.assertIn("libB", r["features"])

    def test_auto_include_depends_not_in_registry(self):
        """@depends referencing non-existent feature should warn but not crash."""
        r = resolve_features({
            "features": {
                "libA": {"depends": ["@missing"]},
            },
            "define": {"include": ["libA"]},
        })
        self.assertIn("libA", r["features"])
        # missing should not be added (not in registry)
        self.assertNotIn("missing", r["features"])

    # ── Auto-include alias definitions ──
    def test_auto_include_alias_ref(self):
        r = resolve_features({
            "features": {"libA": {}, "libB": {}},
            "define": {
                "include": ["libA"],
                "myalias": ["libB"],
            },
        })
        # libB is referenced by alias definition but not @-prefixed
        self.assertIn("libB", r["features"])

    # ── Exclusions re-applied after auto-includes ──
    def test_auto_include_then_excluded(self):
        r = resolve_features({
            "features": {
                "libA": {"depends": ["@libB"]},
                "libB": {},
            },
            "define": {"include": ["libA"], "exclude": ["libB"]},
        })
        # libA depends on @libB, so libB is auto-included, then excluded again
        self.assertNotIn("libB", r["features"])
        self.assertIn("libA", r["features"])

    # ── @alias definition inclusion ──
    def test_alias_definition_expansion_in_include(self):
        r = resolve_features({
            "features": {"libA": {}, "libB": {}},
            "define": {"include": ["@mygroup"], "mygroup": ["libA", "libB"]},
        })
        self.assertEqual(set(r["features"].keys()), {"libA", "libB"})

    def test_alias_definition_expansion_in_exclude(self):
        r = resolve_features({
            "features": {"libA": {}, "libB": {}, "libC": {}},
            "define": {
                "include": ["libA", "libB", "libC"],
                "exclude": ["@mygroup"],
                "mygroup": ["libA", "libB"],
            },
        })
        self.assertEqual(set(r["features"].keys()), {"libC"})

    # ── Edge cases ──
    def test_define_include_not_present_fallsback_to_all(self):
        r = resolve_features({
            "features": dict(self.REGISTRY),
            "define": {"exclude": ["libB"]},
        })
        self.assertEqual(set(r["features"].keys()), {"libA", "libC"})

    def test_empty_registry(self):
        r = resolve_features({"features": {}})
        self.assertEqual(r["features"], {})

    def test_features_returned_as_dicts_not_mutable(self):
        r = resolve_features({
            "features": {"libA": {"flag": "--enable-a"}},
        })
        self.assertEqual(r["features"]["libA"]["flag"], "--enable-a")

    def test_features_are_copies_not_references(self):
        original = {"libA": {"flag": "--enable-a"}}
        r = resolve_features({"features": original})
        r["features"]["libA"]["flag"] = "MODIFIED"
        self.assertEqual(original["libA"]["flag"], "--enable-a")


class TestCollectDeps(unittest.TestCase):
    """collect_deps: per-feature dependency and feature-reference maps."""

    FEATURES = {
        "core": {"depends": ["zlib", "bzip2"]},
        "gpl": {"depends": ["x264"]},
        "x264": {"depends": [], "flag": "--enable-libx264"},
    }

    def test_basic_deps(self):
        fd, fr, _ = collect_deps(self.FEATURES, {}, [])
        self.assertIn("core", fd)
        self.assertIn("zlib", fd["core"])

    def test_feature_refs(self):
        features_with_refs = {
            "core": {"depends": ["zlib", "@license-gpl"]},
            "license-gpl": {},
        }
        fd, fr, _ = collect_deps(features_with_refs, {}, [])
        self.assertIn("license-gpl", fr.get("core", [{}])[0].get("name", ""))

    def test_override(self):
        fd, _, _ = collect_deps(
            {"core": {"depends": ["zlib"]}},
            {"core": "minizip"},
            [],
        )
        self.assertEqual(fd["core"], ["minizip"])

    def test_dict_dependency(self):
        features = {
            "core": {"depends": [{"name": "libfoo", "platform": "!windows"}]},
        }
        fd, _, _ = collect_deps(features, {}, [])
        self.assertEqual(len(fd["core"]), 1)
        self.assertEqual(fd["core"][0]["name"], "libfoo")

    def test_dict_dep_with_override(self):
        features = {
            "core": {"depends": [{"name": "libfoo", "platform": "!windows"}]},
        }
        fd, _, _ = collect_deps(features, {"core": "libbar"}, [])
        # Override replaces name in dict dep
        self.assertEqual(fd["core"][0]["name"], "libbar")
        self.assertEqual(fd["core"][0]["platform"], "!windows")

    def test_host_deps_appended(self):
        _, _, hd = collect_deps({}, {}, ["cmake", "pkgconf"])
        self.assertEqual(hd, ["cmake", "pkgconf"])

    def test_at_ref_with_platform(self):
        features = {
            "core": {"depends": [{"name": "@license-gpl", "platform": "!uwp"}]},
            "license-gpl": {},
        }
        _, fr, _ = collect_deps(features, {}, [])
        self.assertEqual(len(fr.get("core", [])), 1)
        self.assertEqual(fr["core"][0]["name"], "license-gpl")
        self.assertEqual(fr["core"][0]["platform"], "!uwp")

    def test_warning_on_missing_ref(self):
        features = {
            "core": {"depends": ["@nonexistent"]},
        }
        # Should print warning via stderr, not crash
        fd, fr, _ = collect_deps(features, {}, [])
        # Feature should still be in feature_deps (ref was skipped)
        self.assertEqual(fd.get("core", []), [])

    def test_simplified_dict_dep(self):
        features = {
            "core": {"depends": [{"name": "zlib"}]},
        }
        fd, _, _ = collect_deps(features, {}, [])
        # Single-key dict simplified to string
        self.assertEqual(fd["core"], ["zlib"])

    def test_dict_dep_extra_keys_not_simplified(self):
        features = {
            "core": {"depends": [{"name": "zlib", "platform": "!uwp"}]},
        }
        fd, _, _ = collect_deps(features, {}, [])
        self.assertIsInstance(fd["core"][0], dict)
        self.assertEqual(fd["core"][0]["name"], "zlib")

    def test_non_dict_non_list_dep_skipped(self):
        features = {
            "core": {"depends": [42]},
        }
        fd, _, _ = collect_deps(features, {}, [])
        self.assertEqual(fd.get("core"), None)  # No valid deps = nothing in map


if __name__ == "__main__":
    unittest.main()
