"""Tests for scripts/porthash.py (unit tests with temp filesystem)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from porthash import (
    extract_dep_names,
    collect_all_dep_names,
    hash_port_dir,
    compute_composite_hash,
)


class TestExtractDepNames(unittest.TestCase):
    def test_string_deps(self):
        self.assertEqual(extract_dep_names(["a", "b"]), ["a", "b"])

    def test_dict_deps(self):
        self.assertEqual(
            extract_dep_names([{"name": "a", "host": True}, {"name": "b"}]),
            ["a", "b"],
        )

    def test_mixed_deps(self):
        self.assertEqual(
            extract_dep_names(["a", {"name": "b"}, "c"]),
            ["a", "b", "c"],
        )

    def test_empty(self):
        self.assertEqual(extract_dep_names([]), [])

    def test_dict_missing_name(self):
        self.assertEqual(extract_dep_names([{"host": True}]), [])

    def test_non_string_name(self):
        self.assertEqual(extract_dep_names([{"name": 123}]), [])


class TestCollectAllDepNames(unittest.TestCase):
    def test_top_level_deps(self):
        data = {"dependencies": ["a", "b"]}
        self.assertEqual(collect_all_dep_names(data), {"a", "b"})

    def test_feature_deps(self):
        data = {"features": {"feat1": {"dependencies": ["x", "y"]}}}
        self.assertEqual(collect_all_dep_names(data), {"x", "y"})

    def test_both(self):
        data = {
            "dependencies": ["a"],
            "features": {"f1": {"dependencies": ["b"]}},
        }
        self.assertEqual(collect_all_dep_names(data), {"a", "b"})

    def test_feature_as_string(self):
        """When feature value is a string (not dict), skip."""
        data = {"features": {"f1": "description only"}}
        self.assertEqual(collect_all_dep_names(data), set())


class TestHashPortDir(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(__file__).parent / "_test_ports_tmp"

    def tearDown(self):
        import shutil
        if self.tmpdir.is_dir():
            shutil.rmtree(self.tmpdir)

    def _make_port(self, name: str, files: dict[str, str]):
        pkg = self.tmpdir / name
        pkg.mkdir(parents=True, exist_ok=True)
        for relpath, content in files.items():
            fp = pkg / relpath
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)

    def test_empty_port(self):
        self._make_port("mypkg", {})
        result = hash_port_dir(self.tmpdir, "mypkg")
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)

    def test_single_file(self):
        self._make_port("mypkg", {"vcpkg.json": '{"name": "mypkg"}'})
        result = hash_port_dir(self.tmpdir, "mypkg")
        self.assertEqual(len(result), 64)

    def test_different_content_different_hash(self):
        self._make_port("pkg", {"f.txt": "hello"})
        h1 = hash_port_dir(self.tmpdir, "pkg")

        import shutil
        shutil.rmtree(self.tmpdir / "pkg")
        self._make_port("pkg", {"f.txt": "world"})
        h2 = hash_port_dir(self.tmpdir, "pkg")

        self.assertNotEqual(h1, h2)

    def test_deterministic(self):
        self._make_port("pkg", {"a.txt": "aaa", "b.txt": "bbb"})
        h1 = hash_port_dir(self.tmpdir, "pkg")
        h2 = hash_port_dir(self.tmpdir, "pkg")
        self.assertEqual(h1, h2)

    def test_missing_port(self):
        result = hash_port_dir(self.tmpdir, "nonexistent")
        self.assertEqual(len(result), 64)

    def test_subdirectory_file(self):
        self._make_port("pkg", {"sub/f.txt": "data"})
        result = hash_port_dir(self.tmpdir, "pkg")
        self.assertEqual(len(result), 64)


class TestComputeCompositeHash(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(__file__).parent / "_test_composite_tmp"

    def tearDown(self):
        import shutil
        if self.tmpdir.is_dir():
            shutil.rmtree(self.tmpdir)

    def _make_port(self, name: str, deps: list = None, features: dict = None):
        pkg = self.tmpdir / name
        pkg.mkdir(parents=True, exist_ok=True)
        data = {"name": name}
        if deps:
            data["dependencies"] = deps
        if features:
            data["features"] = features
        (pkg / "vcpkg.json").write_text(json.dumps(data))
        (pkg / f"{name}.cmake").write_text(f"# {name} port")

    def test_single_port_no_deps(self):
        self._make_port("ffmpeg-deps")
        result = compute_composite_hash(self.tmpdir, "ffmpeg-deps")
        self.assertEqual(len(result), 64)

    def test_port_with_local_deps(self):
        self._make_port("ffmpeg-deps", deps=[{"name": "zlib", "host": True}, "bzip2"])
        self._make_port("zlib")
        self._make_port("bzip2")
        result = compute_composite_hash(self.tmpdir, "ffmpeg-deps")
        self.assertEqual(len(result), 64)

    def test_transitive_deps(self):
        self._make_port("ffmpeg-deps", deps=["libpng"])
        self._make_port("libpng", deps=["zlib"])
        self._make_port("zlib")
        result = compute_composite_hash(self.tmpdir, "ffmpeg-deps")
        self.assertEqual(len(result), 64)

    def test_different_content_different_hash(self):
        self._make_port("pkg", deps=["depA"])
        self._make_port("depA")

        h1 = compute_composite_hash(self.tmpdir, "pkg")

        import shutil
        shutil.rmtree(self.tmpdir / "depA")
        self._make_port("depA", deps=[])
        (self.tmpdir / "depA" / "extra.txt").write_text("extra")

        h2 = compute_composite_hash(self.tmpdir, "pkg")
        self.assertNotEqual(h1, h2)

    def test_missing_dep_skipped(self):
        """If a dependency is not in ports_dir, it's skipped (not local)."""
        self._make_port("pkg", deps=["external-dep"])
        result = compute_composite_hash(self.tmpdir, "pkg")
        self.assertEqual(len(result), 64)


if __name__ == "__main__":
    unittest.main()
