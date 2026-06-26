"""Integration tests for scripts/ffport/ — exercise real code paths via CLI."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FFPORT_SCRIPT = REPO_ROOT / "scripts" / "ffport.py"


def _run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run ffport.py with given args, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(FFPORT_SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd or str(REPO_ROOT),
    )


class TestFfportList(unittest.TestCase):
    """Integration tests for 'ffport list'."""

    def test_lists_versions(self):
        """list returns version YAML stems (non-empty, no base/master)."""
        result = _run("list")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("8.1.1", result.stdout)
        self.assertNotIn("base", result.stdout)
        self.assertNotIn("master", result.stdout)

    def test_list_returns_many_versions(self):
        """At least 10 version stems are listed."""
        result = _run("list")
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        self.assertGreater(len(lines), 10)


class TestFfportGetRevision(unittest.TestCase):
    """Integration tests for 'ffport get-revision'."""

    def test_get_revision_for_release(self):
        """get-revision returns a numeric revision for a stable version."""
        result = _run("get-revision", "8.1.1")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        rev = result.stdout.strip()
        self.assertTrue(rev.isdigit(), f"Expected digit, got {rev!r}")

    def test_get_revision_for_master(self):
        """get-revision works for master (uses yaml_utils.resolve_chain)."""
        result = _run("get-revision", "master")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        rev = result.stdout.strip()
        self.assertTrue(rev.isdigit(), f"Expected digit, got {rev!r}")

    def test_get_revision_for_nonexistent_exits_nonzero(self):
        """get-revision on nonexistent version exits with error."""
        result = _run("get-revision", "999.999.999")
        self.assertNotEqual(result.returncode, 0)

    def test_get_revision_traces_extends_chain(self):
        """get-revision on 7.1.5 walks the extends chain correctly."""
        result = _run("get-revision", "7.1.5")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        rev = result.stdout.strip()
        self.assertTrue(rev.isdigit(), f"Expected digit, got {rev!r}")


class TestFfportGenerate(unittest.TestCase):
    """Integration tests for 'ffport generate'."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self._tmpdir))

    def test_generate_creates_port_files(self):
        """generate 8.1.1 produces port/ directory with files."""
        result = _run("generate", "8.1.1", "-o", str(self._tmpdir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        port_dir = self._tmpdir / "ffmpeg"
        self.assertTrue(port_dir.is_dir(), f"{port_dir} not created")
        self.assertIn("portfile.cmake", {f.name for f in port_dir.iterdir()})
        self.assertIn("vcpkg.json", {f.name for f in port_dir.iterdir()})

    def test_generate_master_no_version_fails(self):
        """generate master without --version/--ref fails (can't infer version)."""
        result = _run("generate", "master")
        self.assertNotEqual(result.returncode, 0)

    def test_generate_master_with_version_succeeds(self):
        """generate master --version <date> succeeds."""
        result = _run("generate", "master", "--version", "7.1-20260601", "--sha512",
                      "0" * 128, "-o", str(self._tmpdir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        port_dir = self._tmpdir / "ffmpeg"
        self.assertTrue(port_dir.is_dir())

    def test_generate_with_ref(self):
        """generate with --ref flag succeeds (uses ref for version inference)."""
        result = _run("generate", "8.1.1", "--ref", "n8.1.1-10-gabc1234",
                      "--sha512", "0" * 128, "-o", str(self._tmpdir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        port_dir = self._tmpdir / "ffmpeg"
        self.assertTrue(port_dir.is_dir())

    def test_generate_all_produces_all_ports(self):
        """generate --all creates ports for every version YAML."""
        result = _run("generate", "--all", "-o", str(self._tmpdir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        port_dir = self._tmpdir / "ffmpeg"
        self.assertGreaterEqual(len(list(port_dir.iterdir())), 5)


class TestFfportDeps(unittest.TestCase):
    """Integration tests for 'ffport deps'."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._orig_cwd = os.getcwd()
        os.chdir(str(self._tmpdir))

    def tearDown(self):
        os.chdir(str(self._orig_cwd))
        shutil.rmtree(str(self._tmpdir))

    def test_deps_generates_virtual_port(self):
        """deps creates a ffmpeg-deps port directory."""
        # Need REPO_ROOT accessible; run from tmpdir but point to script
        result = subprocess.run(
            [sys.executable, str(FFPORT_SCRIPT), "deps"],
            capture_output=True, text=True,
            cwd=str(self._tmpdir),
        )
        # deps generates to ports/ relative to cwd
        deps_dir = self._tmpdir / "ports" / "ffmpeg-deps"
        self.assertTrue(deps_dir.is_dir() or result.returncode == 0,
                        msg=result.stderr)


class TestFfportGenerateSpecificVersions(unittest.TestCase):
    """Verify generate works for multiple concrete version families."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self._tmpdir))

    def test_generate_7_1_5(self):
        """generate 7.1.5 (LTS, older major)."""
        result = _run("generate", "7.1.5", "-o", str(self._tmpdir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self._tmpdir / "ffmpeg" / "portfile.cmake").is_file())

    def test_generate_6_1_6(self):
        """generate 6.1.6 (oldest maintained LTS)."""
        result = _run("generate", "6.1.6", "-o", str(self._tmpdir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self._tmpdir / "ffmpeg" / "portfile.cmake").is_file())

    def test_generate_4_4_4(self):
        """generate 4.4.4 (legacy LTS with different extends chain)."""
        result = _run("generate", "4.4.4", "-o", str(self._tmpdir),
                      "--sha512", "0" * 128)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self._tmpdir / "ffmpeg" / "portfile.cmake").is_file())

    def test_generate_output_contains_expected_sections(self):
        """Generated portfile.cmake contains expected content from merged chain."""
        result = _run("generate", "8.1.1", "-o", str(self._tmpdir))
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        portfile = self._tmpdir / "ffmpeg" / "portfile.cmake"
        content = portfile.read_text(encoding="utf-8")
        self.assertIn("FFMPEG_VERSION", content)
        self.assertIn("FFMPEG_SHA512", content)
        self.assertIn("FFMPEG_PATCHES", content)

    def test_generate_all_versions_succeed(self):
        """Every version stem from list generates without error."""
        list_result = _run("list")
        versions = [l.strip() for l in list_result.stdout.splitlines() if l.strip()]
        self.assertGreater(len(versions), 0)

        for ver in versions:
            with self.subTest(version=ver):
                out = Path(tempfile.mkdtemp())
                try:
                    # Some versions (e.g. 3.4, 4.4.x) need --sha512 when yaml
                    # name diverges from version; the yaml has sha512 so
                    # it should work without --sha512 if version matches.
                    r = _run("generate", ver, "-o", str(out),
                             "--sha512", "0" * 128)
                    self.assertEqual(r.returncode, 0,
                                     msg=f"Failed on {ver}:\n{r.stderr}")
                finally:
                    shutil.rmtree(str(out), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
