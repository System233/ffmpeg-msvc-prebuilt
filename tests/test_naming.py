"""Tests for scripts/ops/naming.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
from naming import (
    clean_version,
    major_version,
    build_variant_id,
    build_release_tag,
    build_zip_name,
    build_var_yaml_name,
    build_data_path,
    make_version_dir,
    parse_variant_id,
    parse_version_dir,
)


class TestCleanVersion(unittest.TestCase):
    def test_removes_dev_suffix(self):
        self.assertEqual(clean_version("7.1-20260101+dev-10-gabcd"), "7.1-20260101")

    def test_no_suffix(self):
        self.assertEqual(clean_version("8.1.1"), "8.1.1")

    def test_empty(self):
        self.assertEqual(clean_version(""), "")


class TestMajorVersion(unittest.TestCase):
    def test_major_minor_patch(self):
        self.assertEqual(major_version("8.1.1"), "8.x")

    def test_version_with_date(self):
        self.assertEqual(major_version("7.1-20260101"), "7.x")

    def test_with_n_prefix(self):
        self.assertEqual(major_version("n8.1.1"), "8.x")

    def test_single_number(self):
        self.assertEqual(major_version("9"), "9.x")


class TestMakeVersionDir(unittest.TestCase):
    def test_no_revision(self):
        self.assertEqual(make_version_dir(version="8.1.1"), "8.1.1")

    def test_with_revision(self):
        self.assertEqual(make_version_dir(version="8.1.1", revision=2), "8.1.1-r2")

    def test_master_no_revision(self):
        self.assertEqual(make_version_dir(version="7.1-20260101"), "7.1-20260101")


class TestBuildVariantId(unittest.TestCase):
    def test_standard(self):
        vid = build_variant_id(version="8.1.1", revision=2, triplet="x64-windows", linkage="shared", license="gpl")
        self.assertEqual(vid, "ffmpeg-8.1.1-r2_x64-windows-shared-gpl")

    def test_no_revision(self):
        vid = build_variant_id(version="7.1", revision=0, triplet="arm64-windows", linkage="static", license="lgpl")
        self.assertEqual(vid, "ffmpeg-7.1_arm64-windows-static-lgpl")

    def test_master(self):
        vid = build_variant_id(version="7.1-20260101", revision=0, triplet="x64-windows", linkage="shared", license="nonfree")
        self.assertEqual(vid, "ffmpeg-7.1-20260101_x64-windows-shared-nonfree")


class TestBuildReleaseTag(unittest.TestCase):
    def test_with_revision(self):
        self.assertEqual(build_release_tag(version="8.1.1", revision=2), "ffmpeg-8.1.1-r2")

    def test_no_revision(self):
        self.assertEqual(build_release_tag(version="8.1.1"), "ffmpeg-8.1.1")

    def test_master(self):
        self.assertEqual(build_release_tag(version="7.1-20260101"), "ffmpeg-7.1-20260101")


class TestBuildZipName(unittest.TestCase):
    def test_binary(self):
        self.assertEqual(build_zip_name("ffmpeg-8.1.1-r2_x64-windows-shared-gpl"), "ffmpeg-8.1.1-r2_x64-windows-shared-gpl.zip")

    def test_dev(self):
        self.assertEqual(build_zip_name("ffmpeg-8.1.1-r2_x64-windows-shared-gpl", dev=True), "ffmpeg-8.1.1-r2_x64-windows-shared-gpl-develop.zip")


class TestBuildVarYamlName(unittest.TestCase):
    def test_standard(self):
        self.assertEqual(build_var_yaml_name("ffmpeg-8.1.1-r2_x64-windows-shared-gpl"), "ffmpeg-8.1.1-r2_x64-windows-shared-gpl.var.yaml")


class TestBuildDataPath(unittest.TestCase):
    def test_standard(self):
        path = build_data_path(version="8.1.1", revision=2, triplet="x64-windows", linkage="shared", license="gpl")
        self.assertEqual(path, "8.x/8.1.1-r2/variants/x64-windows-shared-gpl.yaml")

    def test_no_revision(self):
        path = build_data_path(version="7.1.2", revision=0, triplet="arm64-windows", linkage="static", license="lgpl")
        self.assertEqual(path, "7.x/7.1.2/variants/arm64-windows-static-lgpl.yaml")

    def test_master(self):
        path = build_data_path(version="7.1-20260101", revision=0, triplet="x64-windows", linkage="shared", license="nonfree")
        self.assertEqual(path, "7.x/7.1-20260101/variants/x64-windows-shared-nonfree.yaml")


class TestParseVariantId(unittest.TestCase):
    def test_new_format(self):
        r = parse_variant_id("ffmpeg-8.1.1-r2_x64-windows-shared-gpl")
        self.assertEqual(r["version"], "8.1.1")
        self.assertEqual(r["revision"], 2)
        self.assertEqual(r["triplet"], "x64-windows")
        self.assertEqual(r["linkage"], "shared")
        self.assertEqual(r["license"], "gpl")
        self.assertEqual(r["arch"], "x64")
        self.assertEqual(r["major"], "8.x")

    def test_new_format_no_revision(self):
        r = parse_variant_id("ffmpeg-8.1.1_x64-windows-static-lgpl")
        self.assertEqual(r["version"], "8.1.1")
        self.assertEqual(r["revision"], 0)
        self.assertEqual(r["triplet"], "x64-windows")
        self.assertEqual(r["linkage"], "static")

    def test_arm_triplet(self):
        r = parse_variant_id("ffmpeg-7.1.2-r1_arm-windows-shared-gpl")
        self.assertEqual(r["arch"], "arm")
        self.assertEqual(r["triplet"], "arm-windows")

    def test_arm64_triplet(self):
        r = parse_variant_id("ffmpeg-8.0_arm64-windows-static-lgpl")
        self.assertEqual(r["arch"], "arm64")
        self.assertEqual(r["triplet"], "arm64-windows")

    def test_x86_triplet(self):
        r = parse_variant_id("ffmpeg-8.1.1-r3_x86-windows-static-lgpl")
        self.assertEqual(r["arch"], "x86")

    def test_master_version(self):
        r = parse_variant_id("ffmpeg-7.1-20260101_x64-windows-shared-nonfree")
        self.assertEqual(r["version"], "7.1-20260101")
        self.assertEqual(r["revision"], 0)

    def test_legacy_format(self):
        r = parse_variant_id("ffmpeg-n8.1.1-r2-x64-windows-shared-gpl")
        self.assertEqual(r["version"], "8.1.1")
        self.assertEqual(r["revision"], 2)
        self.assertEqual(r["triplet"], "x64-windows")

    def test_invalid_prefix(self):
        with self.assertRaises(ValueError):
            parse_variant_id("invalid-8.1.1-r2_x64-windows-shared-gpl")

    def test_invalid_linkage(self):
        with self.assertRaises(ValueError):
            parse_variant_id("ffmpeg-8.1.1_x64-windows-unknown-gpl")

    def test_invalid_license(self):
        with self.assertRaises(ValueError):
            parse_variant_id("ffmpeg-8.1.1_x64-windows-shared-bad")

    def test_invalid_legacy_arch(self):
        with self.assertRaises(ValueError):
            parse_variant_id("ffmpeg-n8.1.1-r2-unknown-windows-shared-gpl")


class TestParseVersionDir(unittest.TestCase):
    def test_with_revision(self):
        r = parse_version_dir("8.1.1-r2")
        self.assertEqual(r["version"], "8.1.1")
        self.assertEqual(r["revision"], 2)

    def test_no_revision(self):
        r = parse_version_dir("8.1.1")
        self.assertEqual(r["version"], "8.1.1")
        self.assertEqual(r["revision"], 0)

    def test_master_date_format(self):
        r = parse_version_dir("7.1-20260101")
        self.assertEqual(r["version"], "7.1-20260101")
        self.assertEqual(r["revision"], 0)

    def test_revision_zero(self):
        r = parse_version_dir("8.0-r0")
        self.assertEqual(r["version"], "8.0")
        self.assertEqual(r["revision"], 0)


if __name__ == "__main__":
    unittest.main()
