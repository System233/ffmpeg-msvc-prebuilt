"""Tests for Master release retention."""
from __future__ import annotations

import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ffbuild import catalog
from ffbuild.retention import (
    compute_month_key, compute_quarter_key, compute_week_key,
    process_snapshots,
)
from test_catalog import record

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



class TestProcessSnapshots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        catalog.write_json(self.root / "index.json", {"schema": 1, "releases": [], "master": []})

    def add_release(self, age, *, master=True):
        when = (datetime.now(timezone.utc) - timedelta(days=age)).date().isoformat()
        if master:
            row = record(f"9.1-dev-{age}-gabcdef", when, channel="master", commit="a"*40)
        else:
            row = record("9.1", when)
        catalog.register_release(self.root, [row])
        return catalog.record_release_tag(row)

    def test_empty_catalog(self):
        self.assertEqual((0, 0), process_snapshots(self.root, dry_run=True))

    def test_missing_index_fails(self):
        (self.root / "index.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing release catalog"):
            process_snapshots(self.root, dry_run=True)

    def test_stable_releases_not_counted(self):
        self.add_release(100, master=False)
        self.assertEqual((0, 0), process_snapshots(self.root, dry_run=True))

    def test_recent_snapshots(self):
        self.add_release(1)
        self.add_release(2)
        self.assertEqual((2, 0), process_snapshots(self.root, dry_run=True))

    def test_old_snapshot_and_output(self):
        # Use a fixed day in a completed quarter, independent of current date.
        today = datetime.now(timezone.utc).date()
        newest = (today - datetime(2023, 2, 10).date()).days
        kept = self.add_release(newest)
        deleted = self.add_release(newest + 10)
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual((1, 1), process_snapshots(self.root, dry_run=True))
            self.assertIn("DELETE_RELEASE:" + deleted, out.getvalue())
            self.assertNotIn("DELETE_RELEASE:" + kept, out.getvalue())
            self.assertNotIn("DELETE_TAG:", out.getvalue())
        self.assertEqual(2, len(catalog.load_shard(self.root, "master", 2023)["releases"]))


if __name__ == "__main__":
    unittest.main()
