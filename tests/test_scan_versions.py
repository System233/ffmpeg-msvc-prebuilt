"""Tests for scripts/ci/scan_versions.py."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from scan_versions import run_push, run_all


class TestRunPush(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("scan_versions.subprocess.run")
        self.mock_run = patcher.start()
        self.addCleanup(patcher.stop)

    def test_found_with_changes(self):
        """Mock output with found=true and changed list → returns version objects."""
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
        """Mock output with found=false → returns empty list."""
        self.mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps({"found": False, "changed": []}),
            stderr="",
        )
        result = run_push("HEAD~1", "HEAD")
        self.assertEqual(result, [])

    def test_subprocess_failure(self):
        """Non-zero return code → raises SystemExit."""
        self.mock_run.return_value = mock.Mock(
            returncode=1,
            stdout="",
            stderr="ci_detect_changes.py error",
        )
        with self.assertRaises(SystemExit) as ctx:
            run_push("HEAD~1", "HEAD")
        self.assertEqual(ctx.exception.code, 1)


class TestRunAll(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("scan_versions.subprocess.run")
        self.mock_run = patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _scan_result(version: str) -> str:
        """Return fake scan_variants.py JSON stdout with a non-empty matrix."""
        return json.dumps({"matrix": [{"triplet": "x64-windows"}]})

    def test_typical_output(self):
        """Two versions on separate lines → returns two version objects."""
        self.mock_run.side_effect = [
            mock.Mock(returncode=0, stdout="8.1.1\n7.1.2\n", stderr=""),
            # git fetch (ignored)
            mock.Mock(returncode=0, stdout="", stderr=""),
            # ffport.py get-revision 8.1.1
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            # scan_variants.py for 8.1.1
            mock.Mock(returncode=0, stdout=self._scan_result("8.1.1"), stderr=""),
            # ffport.py get-revision 7.1.2
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            # scan_variants.py for 7.1.2
            mock.Mock(returncode=0, stdout=self._scan_result("7.1.2"), stderr=""),
        ]
        result = run_all()
        self.assertEqual(result, [{"version": "8.1.1"}, {"version": "7.1.2"}])

    def test_empty_lines_filtered(self):
        """Empty lines and whitespace-only lines are skipped."""
        self.mock_run.side_effect = [
            mock.Mock(returncode=0, stdout="8.1.1\n\n  \n7.1.2\n\n", stderr=""),
            # git fetch (ignored)
            mock.Mock(returncode=0, stdout="", stderr=""),
            # ffport.py get-revision 8.1.1
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            # scan_variants.py for 8.1.1
            mock.Mock(returncode=0, stdout=self._scan_result("8.1.1"), stderr=""),
            # ffport.py get-revision 7.1.2
            mock.Mock(returncode=0, stdout="0\n", stderr=""),
            # scan_variants.py for 7.1.2
            mock.Mock(returncode=0, stdout=self._scan_result("7.1.2"), stderr=""),
        ]
        result = run_all()
        self.assertEqual(result, [{"version": "8.1.1"}, {"version": "7.1.2"}])

    def test_subprocess_failure(self):
        """Non-zero return code → raises SystemExit."""
        self.mock_run.return_value = mock.Mock(
            returncode=1,
            stdout="",
            stderr="ffport.py list error",
        )
        with self.assertRaises(SystemExit) as ctx:
            run_all()
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
