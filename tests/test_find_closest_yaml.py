"""Tests for scripts/find_closest_yaml.py (unit tests with temp filesystem)."""
import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import find_closest_yaml


def _touch(dir: Path, name: str):
    (dir / name).write_text("dummy")


class TestFindClosestYaml(unittest.TestCase):
    """Tests find_closest_yaml() by pointing YAML_DIR at a temp directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._yaml_dir = Path(self._tmp.name) / "ffmpeg"
        self._yaml_dir.mkdir()
        self._orig_yaml_dir = find_closest_yaml.YAML_DIR
        find_closest_yaml.YAML_DIR = self._yaml_dir

    def tearDown(self):
        find_closest_yaml.YAML_DIR = self._orig_yaml_dir
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────
    def _add(self, *versions: str):
        for v in versions:
            _touch(self._yaml_dir, f"{v}.yaml")

    def closest(self, version: str) -> str:
        return find_closest_yaml.find_closest_yaml(version)

    # ── 全新 major ──────────────────────────────────────────────────────
    def test_new_major_no_yamls(self):
        """没有任何 YAML 时返回 master"""
        self.assertEqual(self.closest("8.1"), "master")

    def test_new_major_no_same_major_yamls(self):
        """目标 major 没有 YAML 时返回 master"""
        self._add("7.0", "7.0.2")
        self.assertEqual(self.closest("8.0"), "master")

    # ── 活跃 major 的新 minor ────────────────────────────────────────────
    def test_active_major_new_minor(self):
        """最高 major 的新 minor → master"""
        self._add("8.0", "8.0.1", "8.1", "8.1.1")
        self.assertEqual(self.closest("8.2"), "master")

    def test_active_major_new_minor_over_multiple_minors(self):
        """最高 major 跨越多个 minor 时仍返回 master"""
        self._add("8.0")
        self.assertEqual(self.closest("8.2"), "master")

    # ── 活跃 major 同 minor 的 patch ──────────────────────────────────────
    def test_active_major_same_minor_patch(self):
        """活跃 major 的同 minor 新增 patch → 取该 minor 最新"""
        self._add("8.0", "8.1", "8.1.1")
        self.assertEqual(self.closest("8.1.5"), "8.1.1")

    def test_active_major_same_minor_no_patch(self):
        """活跃 major 的同 minor 只有 .0 → 返回 .0（降级为 minor 版本）"""
        self._add("8.0", "8.1")
        self.assertEqual(self.closest("8.1.1"), "8.1")

    def test_active_major_target_is_exact_yaml(self):
        """目标版本已存在 YAML → 返回自身"""
        self._add("8.0", "8.1", "8.1.1")
        self.assertEqual(self.closest("8.1.1"), "8.1.1")

    def test_active_major_new_minor_with_older_minor_present(self):
        """活跃 major 但有旧 minor 的 YAML → 新 minor 仍用 master"""
        self._add("8.0", "8.0.1")
        self.assertEqual(self.closest("8.2"), "master")

    # ── 旧 major 新版本 ──────────────────────────────────────────────────
    def test_legacy_major_new_minor(self):
        """旧 major 的新 minor → 取该 major 最新版"""
        self._add("7.0", "7.0.2", "7.1", "7.1.1", "7.1.2",
                  "8.0", "8.1", "8.1.1")
        self.assertEqual(self.closest("7.2"), "7.1.2")

    def test_legacy_major_new_minor_no_exact_minor(self):
        """旧 major 没有该 minor → 取该 major 最新版"""
        self._add("6.1", "6.1.1",
                  "8.0", "8.1", "8.1.1")
        self.assertEqual(self.closest("6.9"), "6.1.1")

    def test_legacy_major_same_minor_patch(self):
        """旧 major 的同 minor 新增 patch → 取该 minor 最新"""
        self._add("7.0", "7.0.2",
                  "8.0", "8.1", "8.1.1")
        self.assertEqual(self.closest("7.0.3"), "7.0.2")

    def test_legacy_major_target_is_exact_yaml(self):
        """旧 major 目标已存在 → 返回自身"""
        self._add("7.1", "7.1.2",
                  "8.0", "8.1", "8.1.1")
        self.assertEqual(self.closest("7.1.2"), "7.1.2")

    # ── 混合场景 ─────────────────────────────────────────────────────────
    def test_multiple_majors_over(self):
        """目标 major 比所有已存在的都大 → master"""
        self._add("4.4", "5.1", "6.1", "7.1")
        self.assertEqual(self.closest("9.0"), "master")

    def test_master_yaml_is_ignored(self):
        """master.yaml 不应影响版本匹配"""
        _touch(self._yaml_dir, "master.yaml")
        self.assertEqual(self.closest("8.1"), "master")

    def test_base_yaml_is_ignored(self):
        """base.yaml 不应影响版本匹配"""
        _touch(self._yaml_dir, "base.yaml")
        self._add("8.0", "8.1")
        self.assertEqual(self.closest("8.1.1"), "8.1")

    def test_active_major_with_legacy_major_new_patch(self):
        """多 major 共存时旧 major 的新 patch 不受影响"""
        self._add("6.1", "6.1.1",
                  "7.1", "7.1.1", "7.1.2",
                  "8.0", "8.1", "8.1.1")
        self.assertEqual(self.closest("6.1.2"), "6.1.1")
        self.assertEqual(self.closest("7.1.3"), "7.1.2")


if __name__ == "__main__":
    unittest.main()
