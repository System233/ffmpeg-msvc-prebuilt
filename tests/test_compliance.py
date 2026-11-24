"""Compliance evidence must come from actual installed vcpkg packages."""
from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from compliance_fixture import make_compliance_fixture
from ffbuild.compliance import (
    _dependency_names, _paragraphs, compliance_files, find_ffmpeg_source,
    reachable_ports,
)
from ffbuild.identity import variant_name
from ffbuild.package import package_job
from ffbuild.publication import publish
from ffbuild.store import register_variant


def fake_job() -> dict:
    return {
        "yaml": "9.1", "version": "9.1", "revision": 0,
        "triplet": "arm64-windows",
        "port": "ffmpeg", "package": "ffmpeg[base]",
        "features": ["base"], "license": "lgpl", "linkage": "static",
        "abi_hash": "c" * 64,
        "id": variant_name("9.1", 0, "arm64-windows", "static", "lgpl",
                           abi_hash="c" * 64),
    }


class InstalledLicenseEvidenceTests(unittest.TestCase):
    def test_deb822_status_supports_features_and_folded_dependencies(self):
        rows = _paragraphs("Package: ffmpeg\nDepends: zlib,\n libpng\n"
                           "Status: install ok installed\n\n"
                           "Package: x264\nVersion: 1\n\n")
        self.assertEqual("zlib, libpng", rows[0]["Depends"])
        self.assertEqual({"zlib", "libpng", "x264"},
                         _dependency_names("zlib, libpng, x264 (x64-windows)"))

    def test_collects_reachable_only_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n",
                                 encoding="utf-8")
            job = fake_job()
            installed, source = make_compliance_fixture(root, job, copyright)
            self.assertEqual(["ffmpeg", "zlib"],
                             [p.name for p in reachable_ports(installed, job["triplet"])])
            self.assertEqual(source, find_ffmpeg_source(root / "buildtrees"))
            files, summary = compliance_files(
                installed, job, ffmpeg_copyright=copyright, source_tree=source)
            self.assertEqual(2, summary["package_count"])
            for name in (
                "LICENSES/ffmpeg-arm64-windows/copyright",
                "LICENSES/zlib-arm64-windows/copyright",
                "LICENSES/zlib-arm64-windows/vcpkg.spdx.json",
                "LICENSES/ffmpeg/upstream/COPYING.GPLv3",
                "THIRD_PARTY_NOTICES.md", "BUILD_PROVENANCE.json",
                "SBOM.spdx.json",
            ):
                self.assertIn(name, files)
            self.assertNotIn("ffmpeg-tester", files["THIRD_PARTY_NOTICES.md"].decode())
            self.assertNotIn("extraneous", files["THIRD_PARTY_NOTICES.md"].decode())
            sbom = json.loads(files["SBOM.spdx.json"])
            self.assertEqual(2, len(sbom["packages"]))
            self.assertTrue(any(r["relationshipType"] == "DEPENDS_ON"
                                for r in sbom["relationships"]))
            self.assertEqual("Zlib", next(p["licenseDeclared"] for p in sbom["packages"]
                                         if p["name"] == "zlib"))
            manifest = json.loads(files["BUILD_PROVENANCE.json"])
            self.assertTrue(manifest["not_a_link_map"])
            self.assertEqual("c" * 64, manifest["abi_hash"])

    def test_missing_copyright_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n")
            job = fake_job()
            installed, source = make_compliance_fixture(root, job, copyright)
            (installed / job["triplet"] / "share" / "zlib" / "copyright").unlink()
            with self.assertRaisesRegex(ValueError, "copyright notice"):
                compliance_files(installed, job, ffmpeg_copyright=copyright,
                                 source_tree=source)

    def test_missing_spdx_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n")
            job = fake_job()
            installed, source = make_compliance_fixture(root, job, copyright)
            (installed / job["triplet"] / "share" / "zlib" / "vcpkg.spdx.json").unlink()
            with self.assertRaisesRegex(ValueError, "Missing vcpkg SPDX"):
                compliance_files(installed, job, ffmpeg_copyright=copyright,
                                 source_tree=source)

    def test_unknown_license_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n")
            job = fake_job()
            installed, source = make_compliance_fixture(root, job, copyright)
            spdx = installed / job["triplet"] / "share" / "zlib" / "vcpkg.spdx.json"
            document = json.loads(spdx.read_text())
            document["packages"][0]["licenseDeclared"] = "NOASSERTION"
            spdx.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "Unknown/NOASSERTION"):
                compliance_files(installed, job, ffmpeg_copyright=copyright,
                                 source_tree=source)

    def test_gpl_only_dependency_cannot_enter_lgpl_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n")
            job = fake_job()
            installed, source = make_compliance_fixture(root, job, copyright)
            spdx = installed / job["triplet"] / "share" / "zlib" / "vcpkg.spdx.json"
            document = json.loads(spdx.read_text())
            document["packages"][0]["licenseDeclared"] = "GPL-3.0-only"
            spdx.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "GPL-only installed dependency"):
                compliance_files(installed, job, ffmpeg_copyright=copyright,
                                 source_tree=source)

    def test_missing_referenced_package_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("LGPL")
            job = fake_job()
            installed, _ = make_compliance_fixture(root, job, copyright)
            status = installed / "vcpkg" / "status"
            status.write_text(status.read_text().replace(
                "Depends: zlib", "Depends: zlib, nonexistent"))
            with self.assertRaisesRegex(ValueError, "not installed"):
                reachable_ports(installed, job["triplet"])


class ImmutableComplianceUpgradeTests(unittest.TestCase):
    def test_static_real_zip_roundtrip_and_publication_gate(self):
        job = fake_job()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pkg = root / "package"
            copyright = pkg / "share" / "ffmpeg" / "copyright"
            copyright.parent.mkdir(parents=True)
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n")
            abi_input = copyright.parent / "vcpkg_abi_info.txt"
            abi_input.write_bytes(b"actual native ABI input")
            job["abi_hash"] = hashlib.sha256(abi_input.read_bytes()).hexdigest()
            job["id"] = variant_name("9.1", 0, "arm64-windows", "static", "lgpl",
                                      abi_hash=job["abi_hash"])
            (pkg / "CONTROL").write_text(
                "Package: ffmpeg\nVersion: 9.1\nPort-Version: 0\n"
                "\nFeature: base\n", encoding="utf-8")
            (pkg / "BUILD_INFO").write_text("LibraryLinkage: static\n")
            (pkg / "bin").mkdir()
            (pkg / "bin" / "ffmpeg.exe").write_bytes(b"MZdummy executable")
            installed, source_tree = make_compliance_fixture(root, job, copyright)
            artifacts = root / "artifacts"
            metadata = package_job(pkg, job, artifacts,
                                   installed_root=installed,
                                   source_tree=source_tree)
            record = yaml.safe_load(metadata.read_text())
            self.assertEqual(2, record["package_format"])
            self.assertEqual(2, record["compliance"]["package_count"])
            self.assertEqual(2, len(record["compliance"]["packages"]))
            self.assertEqual(2, len(record["assets"]))
            self.assertTrue((artifacts / record["sbom"]["file"]).is_file())
            with zipfile.ZipFile(artifacts / record["assets"]["binary"]["file"]) as archive:
                names = set(archive.namelist())
                self.assertIn("LICENSES/zlib-arm64-windows/copyright", names)
                self.assertIn("LICENSES/ffmpeg/upstream/COPYING.GPLv3", names)
                self.assertIn("SBOM.spdx.json", names)
                self.assertNotIn("lib/avcodec.lib", names)
                self.assertEqual(None, archive.testzip())
            self.assertEqual(["ffmpeg-9.1"], publish(artifacts_dir=artifacts,
                                                    data_dir=root / "unused",
                                                    dry_run=True))
            record["compliance"]["spdx_sha256"] = "0" * 64
            metadata.write_text(yaml.safe_dump(record))
            with self.assertRaisesRegex(
                    ValueError, "Public SPDX document does not match packaged evidence"):
                publish(artifacts_dir=artifacts, data_dir=root / "unused",
                        dry_run=True)

    def test_package_format_upgrade_keeps_same_abi_identity(self):
        job = fake_job()
        base = {
            "variant_id": job["id"], "version": job["version"],
            "revision": 0, "triplet": job["triplet"],
            "linkage": job["linkage"], "license": job["license"],
            "abi_hash": job["abi_hash"],
            "assets": {"binary": {"file": job["id"] + ".zip"}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = register_variant(root, base)
            upgraded = dict(base)
            upgraded["package_format"] = 2
            upgraded["assets"] = {"binary": {"file": job["id"] + "-pkg2.zip"}}
            self.assertEqual(path, register_variant(root, upgraded))
            self.assertEqual(2, yaml.safe_load(path.read_text())["package_format"])
            self.assertEqual(path, register_variant(root, upgraded))
            regression = dict(base)
            with self.assertRaisesRegex(ValueError, "without a package-format revision"):
                register_variant(root, regression)


if __name__ == "__main__":
    unittest.main()
