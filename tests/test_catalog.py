"""Catalog migration, lookup isolation and retention with native release identities."""
from __future__ import annotations

import json
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from ffbuild import catalog, catalog_migration
from ffbuild.identity import archive_name, variant_name
from ffbuild.state import PublishedState
from ffbuild.identity import record_release_tag


def record(version="9.1", when="2026-11-25", arch="x64", channel="release", commit=None):
    row = {"version": version, "release_date": when, "channel": channel,
           "triplet": arch + "-windows", "linkage": "static", "license": "lgpl",
           "abi_hash": "a" * 64, "package_format": 2, "expected_variants": 1,
           "features": ["base"], "dependencies": ["zlib"], "compliance": {"private": True}}
    if commit:
        row["source_commit"] = commit
    row["variant_id"] = variant_name(version, 0, row["triplet"], "static", "lgpl", abi_hash=row["abi_hash"])
    row["assets"] = {"binary": {"file": archive_name(row), "size": 100, "digest": "sha256:" + "b" * 64}}
    return row


class CatalogTests(unittest.TestCase):
    def test_asset_urls_are_required_and_excluded_from_build_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = record()
            _, _, identity = catalog.release_from_records([row])
            file = row["assets"]["binary"]["file"]
            url = "https://downloads.example.org/custom/" + file
            path = catalog.register_release(root, [row], urls={file: url})
            shard = catalog.load_shard(root, "releases", "9.1")
            release = shard["releases"][0]
            self.assertEqual(identity, catalog.without_download_urls(release))
            self.assertEqual(url, next(catalog.release_assets(release))["url"])
            self.assertEqual(path, catalog.register_release(root, [row], urls={file: url}))
            for invalid in ("javascript:alert(1)", "http://example.org/a.zip", "https://user@example.org/a.zip"):
                with self.assertRaisesRegex(ValueError, "download URL"):
                    catalog.with_download_urls(identity, {file: invalid})
            with self.assertRaisesRegex(ValueError, "URL set"):
                catalog.with_download_urls(identity, {})
            with self.assertRaisesRegex(ValueError, "download URLs differ"):
                catalog.register_release(root, [row], urls={file: "https://example.org/other.zip"})
            catalog.write_json(path, dict(shard, releases=[identity]))
            with self.assertRaisesRegex(ValueError, "asset fields"):
                catalog.load_shard(root, "releases", "9.1")

    def test_lts_metadata_and_refresh(self):
        from ffbuild.identity import is_lts
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for version, expected in (("5.1.10", True), ("7.1.5", True), ("8.1.3", False),
                                      ("9.1", True), ("9.1.1", True), ("4.4.8", True), ("4.4.7", True), ("6.1.6", False), ("9.0.2", False), ("9.2", False), ("4.3.2", False)):
                path = catalog.register_release(root, [record(version)])
                shard = catalog.read_json(path)
                self.assertIs(shard["lts"], expected)
                self.assertIs(is_lts(version), expected)
            master = catalog.register_release(root, [record("7.1-dev-42-gabcdef", channel="master", commit="a" * 40)])
            shard = catalog.read_json(master)
            self.assertIs(shard["lts"], False)
            invalid = dict(shard, lts=True)
            catalog.write_json(master, invalid)
            with self.assertRaisesRegex(ValueError, "LTS classification"):
                catalog.load_shard(root, "master", 2026)
            catalog.write_json(master, shard)
            legacy = root / "releases/7.1.5.json"
            original = catalog.read_json(legacy)
            missing = dict(original)
            del missing["lts"]
            catalog.write_json(legacy, missing)
            with self.assertRaises(ValueError):
                catalog.load_shard(root, "releases", "7.1.5")
            with self.assertRaises(ValueError):
                catalog.refresh_lts(root)
            stale = dict(original, lts=False)
            catalog.write_json(legacy, stale)
            self.assertEqual(1, catalog.refresh_lts(root))
            self.assertEqual(original, catalog.read_json(legacy))
            self.assertEqual(0, catalog.refresh_lts(root))

    def test_native_format_and_legacy_asset_sets(self):
        from ffbuild.versions import ROOT
        schema = json.loads((ROOT / "schema/shard.schema.json").read_text())
        self.assertEqual(2, schema["$defs"]["variant"]["properties"]["format"]["const"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = dict(record(), linkage="shared")
            row["assets"] = {k: {"file": archive_name(row, kind=k), "size": 1,
                                  "digest": "sha256:" + "b"*64} for k in ("binary", "debug")}
            path = catalog.register_release(root, [row])
            original = catalog.read_json(path)
            import copy
            for fmt in (1, 3, 4, 99):
                invalid = copy.deepcopy(original)
                invalid["releases"][0]["variants"]["x64-windows-shared-lgpl"]["format"] = fmt
                catalog.write_json(path, invalid)
                with self.assertRaisesRegex(ValueError, "ABI or format"):
                    catalog.load_shard(root, "releases", "9.1")
            invalid = copy.deepcopy(original)
            del invalid["releases"][0]["variants"]["x64-windows-shared-lgpl"]["debug"]
            catalog.write_json(path, invalid)
            with self.assertRaisesRegex(ValueError, "asset set"):
                catalog.load_shard(root, "releases", "9.1")
            catalog.write_json(path, original)
            self.assertEqual(row["assets"], PublishedState(directory=root).find_abi(
                "9.1", row["triplet"], row["abi_hash"])["assets"])

    def test_legacy_lgpl_notice_scope_and_validation(self):
        import copy
        from ffbuild.versions import ROOT
        schema = json.loads((ROOT / "schema/shard.schema.json").read_text())
        self.assertEqual(catalog.LEGACY_LGPL_NOTE, schema["$defs"]["variant"]["properties"]["note"]["const"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, dest = root / "old", root / "new"
            old = record()
            del old["abi_hash"], old["package_format"]
            gpl = dict(old, license="gpl")
            rows = [old, gpl]
            folder = source / "9.x/9.1-r1"
            (folder / "variants").mkdir(parents=True)
            for row in rows:
                (folder / "variants" / (catalog._slot(row)+".yaml")).write_text(yaml.safe_dump(row))
            (folder / "version.yaml").write_text(yaml.safe_dump({
                "version": "9.1", "release_tag": "ffmpeg-9.1-r1",
                "release_date": old["release_date"], "channel": "release", "variants": rows}))
            catalog_migration.migrate(source, dest)
            path = dest / "releases/9.1.json"
            shard = catalog.load_shard(dest, "releases", "9.1")
            variants = shard["releases"][0]["variants"]
            self.assertEqual(catalog.LEGACY_LGPL_NOTE, variants["x64-windows-static-lgpl"]["note"])
            self.assertNotIn("note", variants["x64-windows-static-gpl"])
            catalog.register_release(dest, [record(when="2026-11-26")])
            current = catalog.load_shard(dest, "releases", "9.1")
            self.assertNotIn("note", current["releases"][0]["variants"]["x64-windows-static-lgpl"])
            self.assertIn(shard["releases"][0], current["releases"])
            for index, slot, note in (
                (0, "x64-windows-static-lgpl", catalog.LEGACY_LGPL_NOTE),
                (1, "x64-windows-static-gpl", catalog.LEGACY_LGPL_NOTE),
                (1, "x64-windows-static-lgpl", "unknown"),
            ):
                invalid = copy.deepcopy(current)
                invalid["releases"][index]["variants"][slot]["note"] = note
                catalog.write_json(path, invalid)
                with self.assertRaisesRegex(ValueError, "historical LGPL notice"):
                    catalog.load_shard(dest, "releases", "9.1")
            catalog.write_json(path, current)
            self.assertIsNotNone(PublishedState(directory=dest).find_abi(
                "9.1", "x64-windows", "a" * 64))

    def test_lookup_reads_only_requested_shard_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for version in ("9.1", "8.1.3", "7.1.5"):
                catalog.register_release(root, [record(version)])
            state = PublishedState(directory=root)
            with patch("ffbuild.catalog.load_shard", wraps=catalog.load_shard) as load,                  patch.object(Path, "rglob", side_effect=AssertionError("Global scan forbidden")):
                for _ in range(20):
                    self.assertEqual("a" * 64, state.find_abi("9.1", "x64-windows", "a" * 64)["abi_hash"])
                self.assertEqual(1, load.call_count)
                self.assertEqual(("releases", "9.1"), load.call_args.args[1:])
                self.assertIsNone(state.find_abi("6.0", "x64-windows", "a" * 64))
                self.assertEqual(1, load.call_count)
            self.assertEqual(4, len(list(root.rglob("*.json"))))
            self.assertNotIn("features", (root / "releases/9.1.json").read_text())
            self.assertNotIn("compliance", (root / "releases/9.1.json").read_text())

    def test_master_reuse_across_years_and_pinned_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = record("9.2-dev-42-gabcdef", "2026-12-31", channel="master", commit="a" * 40)
            catalog.register_release(root, [old])
            newer = dict(old, publication_date="2027-01-01")
            catalog.register_release(root, [newer])
            self.assertEqual([2027, 2026], catalog.manifest(root)["master"])
            state = PublishedState(directory=root)
            found = state.find_abi(old["version"], old["triplet"], old["abi_hash"],
                                   channel="master", source_commit="a" * 40)
            self.assertEqual("2026-12-31", found["release_date"])
            self.assertEqual("2027-01-01", found["publication_date"])
            self.assertEqual(old["assets"], found["assets"])
            self.assertIsNone(state.find_abi(old["version"], old["triplet"], old["abi_hash"],
                                             channel="master", source_commit="b" * 40))

    def test_migration_is_lossless_and_source_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, dest = root / "old", root / "new"
            row = record()
            # Build a legacy dated v1 record for migration compatibility.
            path = source / "9.x/9.1-261125/variants/x64-windows-static-lgpl.yaml"
            path.parent.mkdir(parents=True)
            path.write_text(yaml.safe_dump(row), encoding="utf-8")
            (path.parent.parent / "version.yaml").write_text(yaml.safe_dump({
                "version": row["version"], "release_tag": record_release_tag(row),
                "release_date": row["release_date"], "channel": row["channel"], "variants": [row]}), encoding="utf-8")
            before = {p: p.read_bytes() for p in source.rglob("*.yaml")}
            self.assertEqual((1, 1, 1), catalog_migration.migrate(source, dest))
            self.assertIs(catalog.load_shard(dest, "releases", "9.1")["lts"], True)
            self.assertEqual(before, {p: p.read_bytes() for p in source.rglob("*.yaml")})
            self.assertEqual(row["assets"], PublishedState(directory=dest).find_abi(
                "9.1", row["triplet"], row["abi_hash"])["assets"])
            # Disagreeing duplicate records must stop migration.
            broken = yaml.safe_load(path.read_text())
            broken["assets"]["binary"]["size"] += 1
            path.write_text(yaml.safe_dump(broken), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Legacy asset copies differ"):
                catalog_migration.migrate(source, root / "broken")
            self.assertFalse((root / "broken").exists())
            with self.assertRaisesRegex(ValueError, "Unsupported catalog layout"):
                catalog.register_release(source, [row])

    def test_reject_mixed_index_and_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog.register_release(root, [record()])
            path = root / "9.x/9.1/variants/stale.yaml"
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected legacy YAML"):
                catalog.register_release(root, [record()])
            (root / "index.json").write_text('{"schema":1,"releases":[],"master":[],"master":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate catalog key"):
                catalog.manifest(root)

    def test_production_validation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "Missing release catalog"):
                catalog.validate_catalog(root)
            path = catalog.register_release(root, [record()])
            self.assertEqual(["9.1"], catalog.validate_catalog(root)["releases"])
            original = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(ValueError, "missing shard"):
                catalog.validate_catalog(root)
            path.write_bytes(original)
            index = root / "index.json"
            good = index.read_bytes()
            index.write_text('{"schema":2,"releases":["9.1"],"master":[]}')
            with self.assertRaisesRegex(ValueError, "Invalid catalog manifest"):
                catalog.validate_catalog(root)
            index.write_bytes(good)
            index.unlink()
            with self.assertRaisesRegex(ValueError, "Missing release catalog"):
                PublishedState(directory=root).find_abi("9.1", "x64-windows", "a"*64)

    def test_git_staging_is_index_only_even_without_master_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
            git("init", "-q")
            catalog.register_release(root, [record()])
            (root / "unrelated.audit.zip").write_bytes(b"not an index")
            catalog.stage_index(root)
            self.assertEqual({"index.json", "releases/9.1.json"}, set(git("diff", "--cached", "--name-only").splitlines()))
            git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "test index")
            # Git tracks removal of the last shard even though its directory vanishes.
            (root / "releases/9.1.json").unlink()
            (root / "releases").rmdir()
            catalog.write_json(root / "index.json", {"schema": 1, "releases": [], "master": []})
            catalog.stage_index(root)
            self.assertEqual({"index.json", "releases/9.1.json"}, set(git("diff", "--cached", "--name-only").splitlines()))
            git("add", "unrelated.audit.zip")
            with self.assertRaisesRegex(ValueError, "Unrelated files already staged"):
                catalog.stage_index(root)

    def test_retention_only_removes_master_rows(self):
        import sys
        from ffbuild.retention import process_snapshots
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog.register_release(root, [record()])
            stable = (root / "releases/9.1.json").read_bytes()
            catalog.register_release(root, [record("9.0-dev-1-gabcdef", "2024-01-01", channel="master", commit="a"*40)])
            catalog.register_release(root, [record("9.0-dev-2-gabcdef", "2024-02-01", channel="master", commit="b"*40)])
            before = (root / "master/2024.json").read_bytes()
            self.assertEqual((1, 1), process_snapshots(root, dry_run=True))
            self.assertEqual(before, (root / "master/2024.json").read_bytes())
            self.assertEqual((1, 1), process_snapshots(root))
            self.assertEqual(stable, (root / "releases/9.1.json").read_bytes())
            self.assertEqual(["ffmpeg-master-240201"], [r["tag"] for r in catalog.load_shard(root, "master", 2024)["releases"]])


if __name__ == "__main__":
    unittest.main()
