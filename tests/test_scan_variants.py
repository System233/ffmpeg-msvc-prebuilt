"""Tests for scripts/ci/scan_variants.py."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from scan_variants import main, scan_variants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_side_effect_for_variants(*args, **kwargs):
    """Side effect for subprocess.run that simulates one unbuilt variant."""
    cmd = args[0]
    if cmd[0] == "git" and cmd[1] == "fetch":
        return mock.Mock(returncode=0)
    if "data-path" in cmd:
        return mock.Mock(returncode=0, stdout="some/path\n", stderr="")
    if cmd[0] == "git" and cmd[1] == "show":
        return mock.Mock(returncode=1)  # not found → needs building
    return mock.Mock(returncode=0)


# ---------------------------------------------------------------------------
# Tests: scan_variants()
# ---------------------------------------------------------------------------


class TestScanVariants(unittest.TestCase):
    """Unit tests for the scan_variants function with mocked subprocess."""

    def setUp(self):
        patcher_run = mock.patch(
            "scan_variants.subprocess.run",
            side_effect=_run_side_effect_for_variants,
        )
        self.mock_run = patcher_run.start()
        self.addCleanup(patcher_run.stop)

        # Narrow the combinatorial space to a single variant for predictable tests
        patcher_env = mock.patch(
            "scan_variants._env_list",
            side_effect=[["x64-windows"], ["gpl"], ["shared"]],
        )
        self.mock_env_list = patcher_env.start()
        self.addCleanup(patcher_env.stop)

    def test_returns_correct_dict_structure(self):
        """scan_variants returns dict with 'matrix' and 'triplets' keys."""
        result = scan_variants(ver="8.1.1", rev="2")
        self.assertIn("matrix", result)
        self.assertIn("triplets", result)

    def test_unbuilt_variant_in_matrix(self):
        """When git show fails (variant not built), it appears in matrix."""
        result = scan_variants(ver="8.1.1", rev="2")
        self.assertEqual(len(result["matrix"]), 1)
        self.assertEqual(
            result["matrix"][0],
            {"triplet": "x64-windows", "license": "gpl", "linkage": "shared"},
        )

    def test_triplets_list(self):
        """triplets key matches the mocked _env_list value."""
        result = scan_variants(ver="8.1.1", rev="2")
        self.assertEqual(result["triplets"], ["x64-windows"])


# ---------------------------------------------------------------------------
# Tests: main() — stdout mode (default behaviour)
# ---------------------------------------------------------------------------


class TestMainStdout(unittest.TestCase):
    """Tests for main() without --github-output (existing stdout behaviour)."""

    SAMPLE_OUTPUT = {
        "matrix": [{"triplet": "x64-windows", "license": "gpl", "linkage": "shared"}],
        "triplets": ["x64-windows"],
    }

    def setUp(self):
        patcher = mock.patch(
            "scan_variants.scan_variants", return_value=self.SAMPLE_OUTPUT
        )
        self.mock_scan = patcher.start()
        self.addCleanup(patcher.stop)

    def test_prints_json_to_stdout(self):
        """Without --github-output, main() prints JSON dict to stdout."""
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            main(["--ver", "8.1.1", "--rev", "2"])

        output = json.loads(buf.getvalue())
        self.assertEqual(output, self.SAMPLE_OUTPUT)


# ---------------------------------------------------------------------------
# Tests: main() — github-output mode
# ---------------------------------------------------------------------------


class TestMainGithubOutput(unittest.TestCase):
    """Tests for main() with --github-output flag."""

    SAMPLE_OUTPUT = {
        "matrix": [{"triplet": "x64-windows", "license": "gpl", "linkage": "shared"}],
        "triplets": ["arm-windows", "arm64-windows", "x86-windows", "x64-windows"],
    }

    def setUp(self):
        patcher = mock.patch(
            "scan_variants.scan_variants", return_value=self.SAMPLE_OUTPUT
        )
        self.mock_scan = patcher.start()
        self.addCleanup(patcher.stop)

        # Suppress stderr noise during tests
        patcher_stderr = mock.patch("sys.stderr", io.StringIO())
        patcher_stderr.start()
        self.addCleanup(patcher_stderr.stop)

    def _read_gh_output(self, path):
        """Parse GITHUB_OUTPUT-style file into a dict."""
        result = {}
        with open(path) as f:
            for line in f:
                line = line.rstrip("\n")
                if "=" in line:
                    key, _, value = line.partition("=")
                    result[key] = json.loads(value)
        return result

    def test_writes_matrix_and_triplets_to_github_output_file(self):
        """--github-output writes matrix=<JSON> and triplets=<JSON> to the file."""
        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": tmp_path}):
                main(["--ver", "8.1.1", "--rev", "2", "--github-output"])

            parsed = self._read_gh_output(tmp_path)
            self.assertEqual(parsed["matrix"], self.SAMPLE_OUTPUT["matrix"])
            self.assertEqual(parsed["triplets"], self.SAMPLE_OUTPUT["triplets"])
        finally:
            os.unlink(tmp_path)

    def test_exits_1_when_github_output_env_not_set(self):
        """--github-output with no GITHUB_OUTPUT env var → SystemExit(1)."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                main(["--ver", "8.1.1", "--rev", "2", "--github-output"])
            self.assertEqual(ctx.exception.code, 1)

    def test_appends_to_existing_github_output_file(self):
        """--github-output appends to file (does not overwrite existing content)."""
        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            # Pre-populate the file with some content
            with open(tmp_path, "w") as f:
                f.write("existing_key=42\n")

            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": tmp_path}):
                main(["--ver", "8.1.1", "--rev", "2", "--github-output"])

            with open(tmp_path) as f:
                lines = f.readlines()

            self.assertTrue(any("existing_key=42" in line for line in lines))
            self.assertTrue(any("matrix=" in line for line in lines))
            self.assertTrue(any("triplets=" in line for line in lines))
        finally:
            os.unlink(tmp_path)

    def test_does_not_write_json_to_stdout(self):
        """--github-output mode does NOT write JSON to stdout."""
        buf = io.StringIO()
        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": tmp_path}):
                with mock.patch("sys.stdout", buf):
                    main(["--ver", "8.1.1", "--rev", "2", "--github-output"])

            self.assertEqual(buf.getvalue(), "")
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
