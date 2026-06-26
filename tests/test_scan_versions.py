"""Tests for scripts/ci/scan_versions.py."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from scan_versions import run_push, run_all, _has_required_source


class TestHasRequiredSource(unittest.TestCase):
    """Tests for _has_required_source with mocked YAML resolution."""

    def setUp(self):
        self.resolve_patch = mock.patch("scan_versions.yaml_utils.resolve_chain")
        self.merge_patch = mock.patch("scan_versions.merge.deep_merge")
        self.mock_resolve = self.resolve_patch.start()
        self.mock_merge = self.merge_patch.start()
        self.addCleanup(self.resolve_patch.stop)
        self.addCleanup(self.merge_patch.stop)

    def _make_source(self, sha512=None, ref=None):
        source = {}
        if sha512:
            source["sha512"] = sha512
        if ref:
            source["ref"] = ref
        return source

    def test_has_both_sha512_and_ref(self):
        self.mock_resolve.return_value = ([{"source": {"sha512": "abc", "ref": "n1.2.3"}}], "test")
        self.mock_merge.return_value = {"source": {"sha512": "abc", "ref": "n1.2.3"}}
        self.assertTrue(_has_required_source("1.2.3"))

    def test_missing_sha512(self):
        self.mock_resolve.return_value = ([{"source": {"ref": "n1.2.3"}}], "test")
        self.mock_merge.return_value = {"source": {"ref": "n1.2.3"}}
        self.assertFalse(_has_required_source("1.2.3"))

    def test_missing_ref(self):
        self.mock_resolve.return_value = ([{"source": {"sha512": "abc"}}], "test")
        self.mock_merge.return_value = {"source": {"sha512": "abc"}}
        self.assertFalse(_has_required_source("1.2.3"))

    def test_no_source_section(self):
        self.mock_resolve.return_value = ([{"version": "1.2.3"}], "test")
        self.mock_merge.return_value = {"version": "1.2.3"}
        self.assertFalse(_has_required_source("1.2.3"))

    def test_resolve_chain_failure(self):
        self.mock_resolve.side_effect = SystemExit(1)
        self.assertFalse(_has_required_source("bad"))


class TestHasRequiredSourceIntegration(unittest.TestCase):
    """Integration tests against real YAML files in ffmpeg/."""

    def test_3_4_family_no_sha512(self):
        self.assertFalse(_has_required_source("3.4"))

    def test_3_4_14_version_has_sha512(self):
        self.assertTrue(_has_required_source("3.4.14"))

    def test_8_0_family_no_sha512(self):
        self.assertFalse(_has_required_source("8.0"))

    def test_8_1_1_version_has_sha512(self):
        self.assertTrue(_has_required_source("8.1.1"))

    def test_master_no_sha512(self):
        self.assertFalse(_has_required_source("master"))


class TestRunPush(unittest.TestCase):
    def setUp(self):
        self.mock_run = mock.patch("scan_versions.subprocess.run").start()
        self.addCleanup(mock.patch.stopall)

    def test_found_with_changes(self):
        self.mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps({
                "found": True,
                "changed": [{"version": "8.1.1", "revision": 2}],
            }),
            stderr="",
        )
        result = run_push("HEAD~1", "HEAD")
        self.assertEqual(result, [{"version": "8.1.1"}])

    def test_not_found(self):
        self.mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps({"found": False, "changed": []}),
            stderr="",
        )
        result = run_push("HEAD~1", "HEAD")
        self.assertEqual(result, [])

    def test_subprocess_failure(self):
        self.mock_run.return_value = mock.Mock(
            returncode=1, stdout="", stderr="error",
        )
        with self.assertRaises(SystemExit):
            run_push("HEAD~1", "HEAD")


class TestRunAll(unittest.TestCase):
    def setUp(self):
        self.mock_run = mock.patch("scan_versions.subprocess.run").start()
        self.addCleanup(mock.patch.stopall)

    @staticmethod
    def _scan_result(version: str) -> str:
        return json.dumps({"matrix": [{"triplet": "x64-windows"}]})

    def test_run_all_calls_has_required_source(self):
        """Verify _has_required_source is called for each version to filter."""
        self.mock_run.side_effect = [
            mock.Mock(returncode=0, stdout="3.4\n8.1.1\n", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            mock.Mock(returncode=0, stdout=self._scan_result("8.1.1"), stderr=""),
        ]
        result = run_all()
        self.assertEqual(result, [{"version": "8.1.1"}])

    def test_empty_list(self):
        self.mock_run.return_value = mock.Mock(
            returncode=0, stdout="", stderr="",
        )
        result = run_all()
        self.assertEqual(result, [])

    def test_subprocess_failure(self):
        self.mock_run.return_value = mock.Mock(
            returncode=1, stdout="", stderr="error",
        )
        with self.assertRaises(SystemExit):
            run_all()

    def test_all_family_versions_filtered(self):
        """Only concrete versions with sha512 pass the filter."""
        self.mock_run.side_effect = [
            mock.Mock(returncode=0, stdout="3.4\n3.4.14\n4.4\n4.4.7\n8.0\n8.1.1\n", stderr=""),
            mock.Mock(returncode=0, stdout="", stderr=""),
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            mock.Mock(returncode=0, stdout=self._scan_result("3.4.14"), stderr=""),
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            mock.Mock(returncode=0, stdout=self._scan_result("4.4.7"), stderr=""),
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            mock.Mock(returncode=0, stdout=self._scan_result("8.1.1"), stderr=""),
        ]
        result = run_all()
        versions = [v["version"] for v in result]
        self.assertNotIn("3.4", versions)
        self.assertIn("3.4.14", versions)
        self.assertNotIn("4.4", versions)
        self.assertIn("4.4.7", versions)
        self.assertNotIn("8.0", versions)
        self.assertIn("8.1.1", versions)


if __name__ == "__main__":
    unittest.main()
