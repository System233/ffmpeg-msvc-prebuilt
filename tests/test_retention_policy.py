"""Tests for scripts/ops/retention_policy.py."""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
from retention_policy import (
    _collect_version_dirs,
    compute_month_key,
    compute_quarter_key,
    compute_week_key,
    delete_version_dir,
    get_release_tag,
    get_variant_ids,
    is_snapshot_ref,
    parse_created,
    process_snapshots,
)


# =========================================================================
# is_snapshot_ref
# =========================================================================

class TestIsSnapshotRef(unittest.TestCase):
    """Tests for the is_snapshot_ref function."""

    def test_snapshot_git_describe(self):
        """Git describe string with n prefix is a snapshot."""
        self.assertTrue(is_snapshot_ref("n8.0-1234-gabc1234"))

    def test_snapshot_master_dev(self):
        """Master/dev describe string is a snapshot."""
        self.assertTrue(is_snapshot_ref("n7.1-567-gdeadbeef"))

    def test_release_tag(self):
        """Simple release tag like n8.1.1 is NOT a snapshot."""
        self.assertFalse(is_snapshot_ref("n8.1.1"))

    def test_release_with_patch(self):
        """Release tag with patch version is not a snapshot."""
        self.assertFalse(is_snapshot_ref("n8.1.2"))

    def test_empty_string(self):
        """Empty string is not a snapshot."""
        self.assertFalse(is_snapshot_ref(""))

    def test_none_coerced_to_empty(self):
        """None is coerced to empty string and not a snapshot."""
        self.assertFalse(is_snapshot_ref(None))

    def test_short_hash_too_few_segments(self):
        """A describe-like string missing the commit count is not a snapshot."""
        self.assertFalse(is_snapshot_ref("n8.0-gabc"))

    def test_non_numeric_commit_count(self):
        """Git describe with non-numeric commit count does not match."""
        self.assertFalse(is_snapshot_ref("n8.0-x-gabc"))


# =========================================================================
# Date helpers
# =========================================================================

class TestDateHelpers(unittest.TestCase):
    """Tests for the date bucketing helpers."""

    def test_compute_quarter_key_q1(self):
        """January is Q1."""
        dt = datetime(2025, 1, 15, tzinfo=timezone.utc)
        self.assertEqual(compute_quarter_key(dt), "2025-Q1")

    def test_compute_quarter_key_q4(self):
        """December is Q4."""
        dt = datetime(2025, 12, 1, tzinfo=timezone.utc)
        self.assertEqual(compute_quarter_key(dt), "2025-Q4")

    def test_compute_week_key(self):
        """ISO week key format YYYY-Www."""
        dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        key = compute_week_key(dt)
        self.assertRegex(key, r"^\d{4}-W\d{2}$")

    def test_compute_month_key(self):
        """YYYY-MM format."""
        dt = datetime(2025, 3, 15, tzinfo=timezone.utc)
        self.assertEqual(compute_month_key(dt), "2025-03")

    def test_compute_month_key_padded(self):
        """Single digit month is zero-padded."""
        dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(compute_month_key(dt), "2025-01")


# =========================================================================
# parse_created
# =========================================================================

class TestParseCreated(unittest.TestCase):
    """Tests for the parse_created function."""

    def test_iso_format_z(self):
        """ISO 8601 with Z suffix is parsed correctly."""
        data = {"created": "2025-06-01T12:00:00Z"}
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            result = parse_created(data, Path(tmp.name))
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 1)
        self.assertIsNotNone(result.tzinfo)

    def test_iso_format_with_tz(self):
        """ISO 8601 with timezone offset."""
        data = {"created": "2025-06-01T12:00:00+0000"}
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            result = parse_created(data, Path(tmp.name))
        self.assertEqual(result.year, 2025)

    def test_datetime_object(self):
        """Direct datetime object is returned as-is (with UTC if naive)."""
        dt = datetime(2025, 6, 1, 12, 0, 0)
        data = {"created": dt}
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            result = parse_created(data, Path(tmp.name))
        self.assertEqual(result, dt.replace(tzinfo=timezone.utc))

    def test_datetime_aware(self):
        """Already aware datetime is preserved."""
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        data = {"created": dt}
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            result = parse_created(data, Path(tmp.name))
        self.assertEqual(result, dt)

    def test_date_only_format(self):
        """YYYY-MM-DD without time is accepted."""
        data = {"created": "2025-06-01"}
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            result = parse_created(data, Path(tmp.name))
        self.assertEqual(result.year, 2025)

    def test_missing_created_falls_back_to_mtime(self):
        """When 'created' is absent, the file's mtime is used."""
        data: dict = {}
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            result = parse_created(data, Path(tmp.name))
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)

    def test_none_created_falls_back(self):
        """When 'created' is None, the file's mtime is used."""
        data = {"created": None}
        with tempfile.NamedTemporaryFile(suffix=".yaml") as tmp:
            result = parse_created(data, Path(tmp.name))
        self.assertIsNotNone(result)


# =========================================================================
# get_release_tag
# =========================================================================

class TestGetReleaseTag(unittest.TestCase):
    """Tests for the get_release_tag function."""

    def test_uses_data_field(self):
        """release_tag from data dict is preferred."""
        data = {"release_tag": "ffmpeg-8.1.1-r2"}
        result = get_release_tag(data, Path("/some/path/variant.yaml"))
        self.assertEqual(result, "ffmpeg-8.1.1-r2")

    def test_fallback_to_dirname(self):
        """When release_tag is missing, derived from parent dir name."""
        data: dict = {}
        result = get_release_tag(data, Path("/data/8.x/8.1.1-r2/version.yaml"))
        self.assertEqual(result, "ffmpeg-8.1.1-r2")

    def test_empty_tag_falls_back(self):
        """Empty string release_tag falls back to dirname."""
        data = {"release_tag": ""}
        result = get_release_tag(data, Path("/data/7.x/7.1.0/version.yaml"))
        self.assertEqual(result, "ffmpeg-7.1.0")


# =========================================================================
# get_variant_ids
# =========================================================================

class TestGetVariantIds(unittest.TestCase):
    """Tests for the get_variant_ids function."""

    def test_dict_entries(self):
        """Dict entry with variant_id is extracted."""
        data = {"variants": [{"variant_id": "id1"}, {"variant_id": "id2"}]}
        self.assertEqual(get_variant_ids(data), ["id1", "id2"])

    def test_string_entries(self):
        """Plain string entries are used directly."""
        data = {"variants": ["id1", "id2"]}
        self.assertEqual(get_variant_ids(data), ["id1", "id2"])

    def test_mixed_entries(self):
        """Both formats are handled."""
        data = {"variants": [{"variant_id": "id1"}, "id2"]}
        self.assertEqual(get_variant_ids(data), ["id1", "id2"])

    def test_no_variants_field(self):
        """Missing variants field returns empty list."""
        self.assertEqual(get_variant_ids({}), [])

    def test_non_list_variants(self):
        """Non-list variants field returns empty list."""
        self.assertEqual(get_variant_ids({"variants": "not_a_list"}), [])

    def test_dict_without_variant_id(self):
        """Dict entry without variant_id is skipped."""
        data = {"variants": [{"other": "value"}]}
        self.assertEqual(get_variant_ids(data), [])


# =========================================================================
# _collect_version_dirs
# =========================================================================

class TestCollectVersionDirs(unittest.TestCase):
    """Tests for the _collect_version_dirs helper."""

    def test_empty_directory(self):
        """Empty directory yields no results."""
        with tempfile.TemporaryDirectory() as tmp:
            result = _collect_version_dirs(Path(tmp))
        self.assertEqual(result, [])

    def test_skips_non_dirs(self):
        """Files in the directory are skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "file.txt").write_text("")
            result = _collect_version_dirs(Path(tmp))
        self.assertEqual(result, [])

    def test_skips_dir_without_version_yaml(self):
        """Directory without version.yaml is skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "8.1.1-r1").mkdir()
            result = _collect_version_dirs(Path(tmp))
        self.assertEqual(result, [])

    def test_collects_dir_with_version_yaml(self):
        """Directory with version.yaml is collected."""
        with tempfile.TemporaryDirectory() as tmp:
            version_dir = Path(tmp) / "8.1.1-r1"
            version_dir.mkdir()
            (version_dir / "version.yaml").write_text("", encoding="utf-8")
            result = _collect_version_dirs(Path(tmp))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].name, "8.1.1-r1")
        self.assertEqual(result[0][1], "8.1.1")
        self.assertEqual(result[0][2], 1)


# =========================================================================
# delete_version_dir
# =========================================================================

class TestDeleteVersionDir(unittest.TestCase):
    """Tests for the delete_version_dir function."""

    def test_dry_run_prints_and_does_not_delete(self):
        """Dry run prints message but does not remove directory."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "to-keep"
            d.mkdir()
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                delete_version_dir(d, "ffmpeg-8.0-abc", dry_run=True)
            self.assertTrue(d.exists())
            output = mock_stdout.getvalue()
            self.assertIn("DELETE_RELEASE:ffmpeg-8.0-abc", output)
            self.assertIn("DELETE_TAG:ffmpeg-8.0-abc", output)

    @patch("shutil.rmtree")
    def test_real_delete_calls_rmtree(self, mock_rmtree: MagicMock):
        """Real (non-dry-run) delete calls shutil.rmtree."""
        d = Path("/tmp/fake-dir")
        with patch("sys.stdout", new_callable=io.StringIO):
            delete_version_dir(d, "ffmpeg-8.0-abc", dry_run=False)
        mock_rmtree.assert_called_once_with(d)

    @patch("shutil.rmtree", side_effect=FileNotFoundError)
    def test_real_delete_file_not_found_is_idempotent(
        self, mock_rmtree: MagicMock
    ):
        """FileNotFoundError during delete is silently caught."""
        d = Path("/tmp/already-gone")
        with patch("sys.stdout", new_callable=io.StringIO):
            delete_version_dir(d, "ffmpeg-8.0-abc", dry_run=False)
        # Should not raise


# =========================================================================
# process_snapshots — integration
# =========================================================================

class TestProcessSnapshots(unittest.TestCase):
    """Tests for the process_snapshots function with temp directory setup."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_version(self, major: str, version_id: str, ffmpeg_ref: str,
                      *, age_days: int = 1) -> Path:
        """Create a version directory under major.x/ with a version.yaml."""
        major_dir = self.data_dir / major
        major_dir.mkdir(parents=True, exist_ok=True)
        vd = major_dir / version_id
        vd.mkdir()
        created = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=age_days)
        import yaml
        data = {
            "ffmpeg_ref": ffmpeg_ref,
            "version": version_id,
            "created": created.isoformat(),
            "release_tag": f"ffmpeg-{version_id}",
            "release_id": None,
            "variants": [],
        }
        (vd / "version.yaml").write_text(
            yaml.dump(data), encoding="utf-8"
        )
        return vd

    def test_no_major_dirs(self):
        """Empty data dir yields 0 kept, 0 deleted."""
        kept, deleted = process_snapshots(self.data_dir, dry_run=True)
        self.assertEqual((kept, deleted), (0, 0))

    def test_skips_tagged_releases(self):
        """Non-snapshot ffmpeg_ref (tagged release) is skipped entirely."""
        self._make_version("8.x", "8.1.1-r2", "n8.1.1", age_days=100)
        kept, deleted = process_snapshots(self.data_dir, dry_run=True)
        self.assertEqual((kept, deleted), (0, 0))

    def test_keeps_recent_snapshots(self):
        """Snapshots under 7 days are kept."""
        self._make_version("8.x", "8.0-abc", "n8.0-123-gabc1234", age_days=1)
        kept, deleted = process_snapshots(self.data_dir, dry_run=True)
        self.assertEqual((kept, deleted), (1, 0))

    def test_deletes_old_snapshot(self):
        """Old snapshot (> 1 year) deletes older, keeps newer per quarter."""
        self._make_version("8.x", "8.0-new", "n8.0-2-gabc1234", age_days=400)
        self._make_version("8.x", "8.0-old", "n8.0-1-gdeadbeef", age_days=410)
        kept, deleted = process_snapshots(self.data_dir, dry_run=True)
        self.assertEqual((kept, deleted), (1, 1))

    def test_skips_non_major_dirs(self):
        """Directories not matching major.x/ pattern are skipped."""
        (self.data_dir / "other").mkdir()
        kept, deleted = process_snapshots(self.data_dir, dry_run=True)
        self.assertEqual((kept, deleted), (0, 0))

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_output_format(self, mock_stdout: MagicMock):
        """Output includes DELETE_RELEASE and DELETE_TAG for deleted items."""
        self._make_version("8.x", "8.0-new", "n8.0-2-gabc1234", age_days=400)
        self._make_version("8.x", "8.0-old", "n8.0-1-gdeadbeef", age_days=410)
        process_snapshots(self.data_dir, dry_run=True)
        output = mock_stdout.getvalue()
        # deleted (older, same quarter)
        self.assertIn("DELETE_RELEASE:ffmpeg-8.0-old", output)
        self.assertIn("DELETE_TAG:ffmpeg-8.0-old", output)
        # kept (newer, same quarter)
        self.assertNotIn("DELETE_RELEASE:ffmpeg-8.0-new", output)
        self.assertNotIn("DELETE_TAG:ffmpeg-8.0-new", output)


if __name__ == "__main__":
    unittest.main()
