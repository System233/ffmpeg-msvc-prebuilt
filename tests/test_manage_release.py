"""Tests for scripts/ci/manage_release.py."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
from manage_release import _build_title, _build_notes, create_or_upload, determine_tag


class TestBuildTitle(unittest.TestCase):
    """Tests for the _build_title pure function."""

    def test_snapshot_includes_snapshot_label(self):
        """When is_snapshot=True the title includes '(MSVC Prebuilt, Snapshot)'."""
        title = _build_title("n8.0-1234-gabc", is_snapshot=True)
        self.assertEqual(title, "FFmpeg n8.0-1234-gabc (MSVC Prebuilt, Snapshot)")

    def test_non_snapshot_excludes_snapshot(self):
        """When is_snapshot=False the title omits 'Snapshot'."""
        title = _build_title("8.1.1", is_snapshot=False)
        self.assertEqual(title, "FFmpeg 8.1.1 (MSVC Prebuilt)")
        self.assertNotIn("Snapshot", title)

    def test_various_version_strings(self):
        """The value string is always embedded in the title."""
        cases = [
            "8.1.1",
            "7.1-20260101",
            "n8.0-1234-gabc",
            "master",
        ]
        for v in cases:
            with self.subTest(version=v):
                title = _build_title(v, is_snapshot=False)
                self.assertIn(f"FFmpeg {v}", title)
                self.assertIn("(MSVC Prebuilt)", title)

    def test_snapshot_with_ref_string(self):
        """Snapshot label works with any arbitrary ref string."""
        title = _build_title("n7.1-5678-gdef", is_snapshot=True)
        self.assertEqual(title, "FFmpeg n7.1-5678-gdef (MSVC Prebuilt, Snapshot)")


class TestBuildNotes(unittest.TestCase):
    """Tests for the _build_notes pure function."""

    def test_returns_correct_format(self):
        """Notes embed the version in the standard sentence."""
        notes = _build_notes("8.1.1")
        expected = "Automated build of FFmpeg 8.1.1 using MSVC via vcpkg."
        self.assertEqual(notes, expected)

    def test_with_master_date_version(self):
        """Notes work with date-based version strings."""
        notes = _build_notes("7.1-20260101")
        expected = "Automated build of FFmpeg 7.1-20260101 using MSVC via vcpkg."
        self.assertEqual(notes, expected)

    def test_with_git_ref(self):
        """Notes work with git-ref-style version strings."""
        notes = _build_notes("n8.0-1234-gabc")
        expected = "Automated build of FFmpeg n8.0-1234-gabc using MSVC via vcpkg."
        self.assertEqual(notes, expected)


class TestDetermineTag(unittest.TestCase):
    """Tests for the determine_tag function."""

    @staticmethod
    def _write_var_yaml(dir_path: Path, variant_id: str, version: str, revision: int, **extra):
        path = dir_path / f"{variant_id}.var.yaml"
        lts = extra.get("lts", True)
        lts_str = str(lts).lower() if isinstance(lts, bool) else lts
        lines = [
            f"variant_id: {variant_id}",
            f"version: {version}",
            f"revision: {revision}",
            f"arch: {extra.get('arch', 'x64')}",
            f"triplet: {extra.get('triplet', 'x64-windows')}",
            f"linkage: {extra.get('linkage', 'shared')}",
            f"license: {extra.get('license', 'gpl')}",
            f"lts: {lts_str}",
            f"ffmpeg_ref: {extra.get('ffmpeg_ref', f'n{version}')}",
            "assets:",
            "  binary:",
            f"    file: {variant_id}.zip",
            "    size: 1234",
            "    digest: sha256:abc",
            "features: []",
            "dependencies: []",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_with_revision(self):
        """Tagged release with revision includes -r{N} suffix."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write_var_yaml(d, "ffmpeg-8.1.1-r2_x64-windows-shared-gpl", "8.1.1", 2)
            tag = determine_tag(d)
            self.assertEqual(tag, "ffmpeg-8.1.1-r2")

    def test_no_revision(self):
        """Tagged release without revision omits the -r suffix."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write_var_yaml(d, "ffmpeg-8.1.1_x64-windows-shared-gpl", "8.1.1", 0)
            tag = determine_tag(d)
            self.assertEqual(tag, "ffmpeg-8.1.1")

    def test_snapshot_version(self):
        """Snapshot (date-based) version without revision produces correct tag."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write_var_yaml(d, "ffmpeg-7.1-20260626_x64-windows-shared-gpl", "7.1-20260626", 0)
            tag = determine_tag(d)
            self.assertEqual(tag, "ffmpeg-7.1-20260626")

    def test_snapshot_with_revision(self):
        """Snapshot build that also has a revision includes both."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._write_var_yaml(d, "ffmpeg-7.1-20260626-r1_x64-windows-shared-gpl", "7.1-20260626", 1)
            tag = determine_tag(d)
            self.assertEqual(tag, "ffmpeg-7.1-20260626-r1")

    def test_first_alphabetical_when_multiple(self):
        """When multiple .var.yaml files exist, the first sorted is used."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # r0 comes first alphabetically → should produce ffmpeg-7.1.5
            self._write_var_yaml(d, "ffmpeg-7.1.5_x64-windows-shared-gpl", "7.1.5", 0)
            self._write_var_yaml(d, "ffmpeg-8.1.1-r2_x64-windows-shared-gpl", "8.1.1", 2)
            tag = determine_tag(d)
            self.assertEqual(tag, "ffmpeg-7.1.5")

    def test_quoted_x_y_version(self):
        """X.Y version serialized as quoted '9.0' must not leak quotes into the tag."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # yaml.dump quotes '9.0' because it looks like a YAML float
            import yaml
            var = {
                "variant_id": "ffmpeg-9.0_x64-windows-shared-gpl",
                "version": "9.0",
                "revision": 0,
            }
            with open(d / "ffmpeg-9.0_x64-windows-shared-gpl.var.yaml", "w", encoding="utf-8") as fh:
                yaml.dump(var, fh, default_flow_style=False, sort_keys=False)
            tag = determine_tag(d)
            self.assertEqual(tag, "ffmpeg-9.0")

    def test_no_var_files(self):
        """When no .var.yaml files exist, returns None."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            tag = determine_tag(d)
            self.assertIsNone(tag)


class TestCreateOrUploadPrerelease(unittest.TestCase):
    """Verify snapshot releases are created as prereleases, stable are not."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "ffmpeg-8.1.1-r2_x64-windows-shared-gpl.zip").write_bytes(b"zip")
        (self.dir / "ffmpeg-n8.0-1234-gabc-r1_x64-windows-shared-gpl.zip").write_bytes(b"zip")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, ref=None, yaml_val="8.1.1"):
        with mock.patch.dict("os.environ", {"GH_TOKEN": "fake"}, clear=False):
            with mock.patch("subprocess.run") as mock_run:
                def fake_run(cmd, **kwargs):
                    r = mock.MagicMock()
                    r.returncode = 0
                    # gh release view succeeds → "already exists" path
                    if cmd[0:2] == ["gh", "release", "view"]:
                        r.returncode = 0
                    return r
                mock_run.side_effect = fake_run
                create_or_upload(
                    tag="ffmpeg-8.1.1-r2",
                    artifacts_dir=self.dir,
                    ref=ref,
                    yaml_val=yaml_val,
                )
                return mock_run.call_args_list

    def test_snapshot_create_has_prerelease_flag(self):
        """Creating a new snapshot release passes --prerelease --latest=false."""
        with mock.patch("subprocess.run") as mock_run:
            def fake_run(cmd, **kwargs):
                r = mock.MagicMock()
                # view fails (release missing) → create path; everything else succeeds
                r.returncode = 1 if cmd[0:3] == ["gh", "release", "view"] else 0
                return r
            mock_run.side_effect = fake_run
            with mock.patch.dict("os.environ", {"GH_TOKEN": "fake"}, clear=False):
                create_or_upload(
                    tag="ffmpeg-n8.0-1234-gabc-r1",
                    artifacts_dir=self.dir,
                    ref="n8.0-1234-gabc",
                    yaml_val=None,
                )
        create_cmd = next(args[0] for args, _ in mock_run.call_args_list
                          if args[0][0:3] == ["gh", "release", "create"])
        self.assertIn("--prerelease", create_cmd)
        self.assertIn("--latest=false", create_cmd)

    def test_stable_create_no_prerelease_flag(self):
        """Creating a new stable release does NOT pass prerelease flags."""
        with mock.patch("subprocess.run") as mock_run:
            def fake_run(cmd, **kwargs):
                r = mock.MagicMock()
                r.returncode = 1 if cmd[0:3] == ["gh", "release", "view"] else 0
                return r
            mock_run.side_effect = fake_run
            with mock.patch.dict("os.environ", {"GH_TOKEN": "fake"}, clear=False):
                create_or_upload(
                    tag="ffmpeg-8.1.1-r2",
                    artifacts_dir=self.dir,
                    ref=None,
                    yaml_val="8.1.1",
                )
        create_cmd = next(args[0] for args, _ in mock_run.call_args_list
                          if args[0][0:3] == ["gh", "release", "create"])
        self.assertNotIn("--prerelease", create_cmd)
        self.assertNotIn("--latest=false", create_cmd)

    def test_snapshot_existing_gets_prerelease_edit(self):
        """Existing snapshot release gets flagged via gh release edit."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0)  # view succeeds → upload path
            with mock.patch.dict("os.environ", {"GH_TOKEN": "fake"}, clear=False):
                create_or_upload(
                    tag="ffmpeg-n8.0-1234-gabc-r1",
                    artifacts_dir=self.dir,
                    ref="n8.0-1234-gabc",
                    yaml_val=None,
                )
        edit_cmd = next(args[0] for args, _ in mock_run.call_args_list
                        if args[0][0:3] == ["gh", "release", "edit"])
        self.assertIn("--prerelease", edit_cmd)
        self.assertIn("--latest=false", edit_cmd)

    def test_stable_existing_no_prerelease_edit(self):
        """Existing stable release does NOT get a prerelease edit."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0)  # view succeeds → upload path
            with mock.patch.dict("os.environ", {"GH_TOKEN": "fake"}, clear=False):
                create_or_upload(
                    tag="ffmpeg-8.1.1-r2",
                    artifacts_dir=self.dir,
                    ref=None,
                    yaml_val="8.1.1",
                )
        cmds = [args[0] for args, _ in mock_run.call_args_list]
        self.assertFalse(any(cmd[0:3] == ["gh", "release", "edit"] for cmd in cmds))


if __name__ == "__main__":
    unittest.main()
