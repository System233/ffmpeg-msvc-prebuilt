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
    _dependency_names, _paragraphs, _spdx_license, compliance_files, find_ffmpeg_source,
    reachable_ports, distribution_evidence, PUBLIC_COPYRIGHT, PUBLIC_SPDX,
)
from ffbuild.identity import variant_name, audit_name
from ffbuild.package import package_job
from ffbuild.publication import publish
from ffbuild.catalog import register_release


def fake_job() -> dict:
    return {
        "yaml": "9.1", "version": "9.1", "release_date": "2026-11-25",
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
            public, files, summary = compliance_files(
                installed, job, ffmpeg_copyright=copyright, source_tree=source)
            self.assertEqual(2, summary["package_count"])
            for name in (
                "LICENSES/ffmpeg-arm64-windows/copyright",
                "LICENSES/zlib-arm64-windows/copyright",
                "LICENSES/zlib-arm64-windows/vcpkg.spdx.json",
                "LICENSES/ffmpeg/upstream/COPYING.GPLv3",
                "metadata/BUILD_PROVENANCE.json",
            ):
                self.assertIn(name, files)
            manifest = json.loads(files["metadata/BUILD_PROVENANCE.json"])
            self.assertEqual(public, distribution_evidence(files.__getitem__, manifest))
            self.assertEqual({PUBLIC_COPYRIGHT, PUBLIC_SPDX}, set(public))
            self.assertNotIn(b"ffmpeg-tester", public[PUBLIC_COPYRIGHT])
            self.assertNotIn(b"extraneous", public[PUBLIC_COPYRIGHT])
            self.assertIn(b"zlib license text", public[PUBLIC_COPYRIGHT])
            self.assertIn(b"upstream COPYING.GPLv3", public[PUBLIC_COPYRIGHT])
            self.assertNotIn(b"upstream COPYING.GPLv2", public[PUBLIC_COPYRIGHT])
            sbom = json.loads(public[PUBLIC_SPDX])
            self.assertEqual(2, len(sbom["packages"]))
            self.assertTrue(any(r["relationshipType"] == "DEPENDS_ON"
                                for r in sbom["relationships"]))
            zlib = next(p for p in sbom["packages"] if p["name"] == "zlib")
            self.assertEqual("Zlib", zlib["licenseConcluded"])
            self.assertEqual("NOASSERTION", zlib["licenseDeclared"])
            self.assertEqual("licenseConcluded", next(p["license_source"] for p in summary["packages"]
                                                       if p["name"] == "zlib"))
            manifest = json.loads(files["metadata/BUILD_PROVENANCE.json"])
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
            for package in document["packages"]:
                package["licenseConcluded"] = "NOASSERTION"
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
            for package in document["packages"][:2]:
                package["licenseConcluded"] = "GPL-3.0-only"
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

    def test_vcpkg_abseil_apache_license_in_concluded(self):
        for triplet in ("arm-windows", "x64-windows"):
            with self.subTest(triplet=triplet):
                document = {"spdxVersion": "SPDX-2.2", "packages": [
                    {"SPDXID": "SPDXRef-port", "name": "abseil",
                     "licenseDeclared": "NOASSERTION", "licenseConcluded": "Apache-2.0"},
                    {"SPDXID": "SPDXRef-binary", "name": f"abseil:{triplet}",
                     "licenseDeclared": "NOASSERTION", "licenseConcluded": "Apache-2.0"},
                    {"SPDXID": "SPDXRef-resource-0", "name": "source",
                     "licenseDeclared": "NOASSERTION", "licenseConcluded": "NOASSERTION"},
                ]}
                self.assertEqual(("Apache-2.0", "licenseConcluded"),
                                 _spdx_license(document, f"abseil:{triplet}"))
                document["packages"][1]["licenseConcluded"] = "GPL-3.0-only"
                with self.assertRaisesRegex(ValueError, "Conflicting vcpkg"):
                    _spdx_license(document, f"abseil:{triplet}")

    def test_declared_fallback_and_unknown_primary_not_hidden_by_resource(self):
        document = {"spdxVersion": "SPDX-2.3", "packages": [
            {"name": "zlib", "SPDXID": "SPDXRef-Package",
             "licenseDeclared": "Zlib", "licenseConcluded": "NOASSERTION"},
            {"name": "resource", "SPDXID": "SPDXRef-resource",
             "licenseDeclared": "MIT", "licenseConcluded": "MIT"},
        ]}
        self.assertEqual(("Zlib", "licenseDeclared"), _spdx_license(document, "zlib:x64-windows"))
        document["packages"][0]["licenseDeclared"] = "NOASSERTION"
        with self.assertRaisesRegex(ValueError, "Unknown/NOASSERTION"):
            _spdx_license(document, "zlib:x64-windows")
        document["packages"][0]["licenseConcluded"] = "MIT AND LicenseRef-vcpkg-null"
        with self.assertRaisesRegex(ValueError, "Unknown/NOASSERTION"):
            _spdx_license(document, "zlib:x64-windows")
        document["packages"][0]["licenseConcluded"] = "MIT"
        document["packages"][0]["licenseDeclared"] = "GPL-3.0-only"
        with self.assertRaisesRegex(ValueError, "Conflicting SPDX"):
            _spdx_license(document, "zlib:x64-windows")

    def test_reviewed_pkgconf_copyright_resolves_explicit_null_only(self):
        # Exact text verified against pkgconf-2.5.1/COPYING and two real
        # vcpkg cache archives, without copying any binary payload.
        notice = (
            "Copyright (c) 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018\n"
            "    pkgconf authors (see AUTHORS file in source directory).\n\n"
            "Permission to use, copy, modify, and/or distribute this software for any\n"
            "purpose with or without fee is hereby granted, provided that the above\n"
            "copyright notice and this permission notice appear in all copies.\n\n"
            "This software is provided 'as is' and without any warranty, express or\n"
            "implied.  In no event shall the authors be liable for any damages arising\n"
            "from the use of this software.\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n")
            job = fake_job()
            installed, source = make_compliance_fixture(root, job, copyright)
            status = installed / "vcpkg/status"
            status.write_text(status.read_text().replace("zlib", "pkgconf").replace("1.3.2", "2.5.1\nPort-Version: 4"))
            share = installed / job["triplet"] / "share"
            (share / "zlib").rename(share / "pkgconf")
            target = share / "pkgconf/copyright"
            target.write_bytes(notice)
            spdx = share / "pkgconf/vcpkg.spdx.json"
            document = json.loads(spdx.read_text())
            for row in document["packages"][:2]:
                row["name"] = row["name"].replace("zlib", "pkgconf")
                row["licenseConcluded"] = "LicenseRef-vcpkg-null"
            spdx.write_text(json.dumps(document))
            public, files, summary = compliance_files(installed, job, ffmpeg_copyright=copyright, source_tree=source)
            pkg = next(row for row in summary["packages"] if row["name"] == "pkgconf")
            self.assertEqual("local-declaration", pkg["license_source"])
            self.assertEqual("LicenseRef-Pkgconf-2.5.1", pkg["license_expression"])
            sbom = json.loads(public[PUBLIC_SPDX])
            extracted = sbom["hasExtractedLicensingInfos"][0]
            self.assertEqual(pkg["license_expression"], extracted["licenseId"])
            self.assertEqual(notice.decode(), extracted["extractedText"])
            target.write_bytes(notice + b"unreviewed modification")
            with self.assertRaisesRegex(ValueError, "Unknown/NOASSERTION"):
                compliance_files(installed, job, ffmpeg_copyright=copyright, source_tree=source)
            target.write_bytes(notice)
            for row in document["packages"][:2]:
                row["licenseConcluded"] = "GPL-3.0-only AND LicenseRef-vcpkg-null"
            spdx.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "Unknown/NOASSERTION"):
                compliance_files(installed, job, ffmpeg_copyright=copyright, source_tree=source)

    def test_all_incompatible_ports_are_reported_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copyright = root / "copyright"
            copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n")
            job = fake_job()
            installed, source = make_compliance_fixture(root, job, copyright)
            status = installed / "vcpkg/status"
            status.write_text(status.read_text().replace("Depends: zlib", "Depends: zlib, extraneous"))
            share = installed / job["triplet"] / "share"
            for name, expression in (("zlib", "GPL-3.0-only"), ("extraneous", "LicenseRef-Unknown")):
                folder = share / name
                folder.mkdir(exist_ok=True)
                (folder / "copyright").write_text("Actual license text")
                document = {"spdxVersion": "SPDX-2.2", "packages": [
                    {"name": name, "SPDXID": "SPDXRef-port", "licenseConcluded": expression, "licenseDeclared": "NOASSERTION"},
                    {"name": name + ":" + job["triplet"], "SPDXID": "SPDXRef-binary", "licenseConcluded": expression, "licenseDeclared": "NOASSERTION"},
                ]}
                (folder / "vcpkg.spdx.json").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ValueError) as error:
                compliance_files(installed, job, ffmpeg_copyright=copyright, source_tree=source)
            message = str(error.exception)
            self.assertIn("rejected 2 installed Ports", message)
            self.assertIn("License deny for zlib", message)
            self.assertIn("License review for extraneous", message)


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
            self.assertEqual(3, record["package_format"])
            self.assertEqual("ffmpeg-9.1_arm64-windows-static-lgpl-261125.zip", record["assets"]["binary"]["file"])
            self.assertEqual(2, record["compliance"]["package_count"])
            self.assertEqual(2, len(record["compliance"]["packages"]))
            self.assertEqual({"binary"}, set(record["assets"]))
            self.assertNotIn("revision", record)
            self.assertEqual({metadata.name, audit_name(record), record["assets"]["binary"]["file"]},
                             {p.name for p in artifacts.iterdir()})
            with zipfile.ZipFile(artifacts / record["assets"]["binary"]["file"]) as archive:
                names = set(archive.namelist())
                self.assertEqual({"ffmpeg.exe", "LICENSE.txt", PUBLIC_COPYRIGHT, PUBLIC_SPDX}, names)
                self.assertIn(b"zlib license text", archive.read(PUBLIC_COPYRIGHT))
                self.assertIn(b"upstream COPYING.GPLv3", archive.read(PUBLIC_COPYRIGHT))
                self.assertNotIn(b"upstream COPYING.GPLv2", archive.read(PUBLIC_COPYRIGHT))
                self.assertNotIn("lib/avcodec.lib", names)
                self.assertEqual(None, archive.testzip())
            self.assertEqual(["ffmpeg-9.1-261125"], publish(artifacts_dir=artifacts,
                                                    data_dir=root / "unused",
                                                    dry_run=True))
            record["compliance"]["spdx_sha256"] = "0" * 64
            metadata.write_text(yaml.safe_dump(record))
            with self.assertRaisesRegex(
                    ValueError, "Compliance metadata hash differs"):
                publish(artifacts_dir=artifacts, data_dir=root / "unused",
                        dry_run=True)

    def test_package_format_does_not_bypass_immutable_abi_identity(self):
        from test_catalog import record
        base = record()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            register_release(root, [base])
            before = (root / "releases/9.1.json").read_bytes()
            upgraded = dict(base, package_format=2, assets={
                "binary": dict(base["assets"]["binary"], digest="sha256:" + "f"*64)})
            with self.assertRaisesRegex(ValueError, "different|immutable|conflict"):
                register_release(root, [upgraded])
            self.assertEqual(before, (root / "releases/9.1.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
