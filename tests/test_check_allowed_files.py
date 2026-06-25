"""Tests for scripts/ci/check_allowed_files.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from _allowed import find_violations


def is_file_allowed(filename: str) -> bool:
    """Mirror the check_allowed_files logic for testing."""
    return not find_violations([filename])


class TestAllowedRegexes(unittest.TestCase):
    """Tests for the ALLOWED default patterns."""

    def test_ffmpeg_yaml_allowed_basic(self):
        """ffmpeg/*.yaml files are allowed."""
        self.assertTrue(is_file_allowed("ffmpeg/8.1.1.yaml"))

    def test_ffmpeg_master_yaml_allowed(self):
        self.assertTrue(is_file_allowed("ffmpeg/master.yaml"))

    def test_ffmpeg_base_yaml_allowed(self):
        self.assertTrue(is_file_allowed("ffmpeg/base.yaml"))

    def test_ffmpeg_subdir_yaml_allowed(self):
        """Regex ffmpeg/.*\\.yaml$ covers nested files."""
        self.assertTrue(is_file_allowed("ffmpeg/subdir/file.yaml"))

    def test_patches_patch_allowed(self):
        self.assertTrue(is_file_allowed("patches/8.x/something.patch"))

    def test_patches_nested_patch_allowed(self):
        self.assertTrue(is_file_allowed("patches/8.x/001/0001-foo.patch"))


class TestOpenCodePrefix(unittest.TestCase):
    """Tests that .opencode/ files are NOT allowed."""

    def test_opencode_skill_md_not_allowed(self):
        self.assertFalse(is_file_allowed(".opencode/skills/auto-heal/SKILL.md"))

    def test_opencode_json_not_allowed(self):
        self.assertFalse(is_file_allowed(".opencode/foo/bar.json"))

    def test_opencode_root_file_not_allowed(self):
        self.assertFalse(is_file_allowed(".opencode/config.json"))


class TestForbiddenFiles(unittest.TestCase):
    """Tests that files outside allowed scope are rejected."""

    def test_scripts_ci_py_not_allowed(self):
        self.assertFalse(is_file_allowed("scripts/ci/foo.py"))

    def test_github_workflows_yml_not_allowed(self):
        self.assertFalse(is_file_allowed(".github/workflows/foo.yml"))

    def test_data_anything_not_allowed(self):
        self.assertFalse(is_file_allowed("data/anything"))

    def test_ports_vcpkg_json_not_allowed(self):
        self.assertFalse(is_file_allowed("ports/ffmpeg/vcpkg.json"))

    def test_patches_not_dot_patch_not_allowed(self):
        """Only .patch files are allowed under patches/."""
        self.assertFalse(is_file_allowed("patches/something.txt"))

    def test_root_file_not_allowed(self):
        self.assertFalse(is_file_allowed("README.md"))


if __name__ == "__main__":
    unittest.main()
