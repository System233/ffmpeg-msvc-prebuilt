"""Dated public artifacts, immutable releases and incremental native ABI reuse."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import yaml

from compliance_fixture import make_compliance_fixture
from ffbuild.identity import archive_name, record_release_tag, dated_variant_path, variant_name
from ffbuild.package import package_job
from ffbuild.planner import plan_native
from ffbuild.publication import publish, _release_assets, _release_api
from ffbuild.state import PublishedState
from ffbuild.store import register_variant


def make_variant(root, date, triplet, linkage, abi_input, *, version="9.1", channel="release"):
    root.mkdir(parents=True)
    job = {
        "yaml": "master" if channel == "master" else version,
        "version": version, "release_date": date, "triplet": triplet,
        "port": "ffmpeg", "package": "ffmpeg[base]",
        "features": ["base"], "license": "lgpl", "linkage": linkage,
        "abi_hash": hashlib.sha256(abi_input).hexdigest(), "expected_variants": 2,
    }
    if channel == "master":
        job.update(source_ref="a" * 40, ref="n" + version, sha512="b" * 128)
    job["id"] = variant_name(version, 0, triplet, linkage, "lgpl", abi_hash=job["abi_hash"])
    package = root / "package"
    copyright = package / "share/ffmpeg/copyright"
    copyright.parent.mkdir(parents=True)
    copyright.write_text("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n", encoding="utf-8")
    (copyright.parent / "vcpkg_abi_info.txt").write_bytes(abi_input)
    (package / "CONTROL").write_text(f"Package: ffmpeg\nVersion: {version}\n\nFeature: base\n", encoding="utf-8")
    (package / "BUILD_INFO").write_text("LibraryLinkage: " + ("dynamic" if linkage == "shared" else "static") + "\n", encoding="utf-8")
    (package / "bin").mkdir()
    (package / "bin/ffmpeg.exe").write_bytes(abi_input)
    installed, source = make_compliance_fixture(root, job, copyright)
    return job, package, installed, source


def package_variant(variant, output):
    job, package, installed, source = variant
    file = package_job(package, job, output, installed_root=installed, source_tree=source)
    return yaml.safe_load(file.read_text(encoding="utf-8"))


class DatedPublication(unittest.TestCase):
    def test_public_naming_and_master(self):
        row = {"version": "9.1", "triplet": "arm64-windows", "linkage": "shared",
               "license": "gpl", "release_date": "2026-11-25"}
        self.assertEqual("ffmpeg-9.1_arm64-windows-shared-gpl-261125.zip", archive_name(row))
        self.assertEqual("ffmpeg-9.1_arm64-windows-shared-gpl-develop-261125.zip", archive_name(row, develop=True))
        self.assertEqual("ffmpeg-9.1-261125", record_release_tag(row))
        row.update(channel="master", version="9.2-123-gabc")
        self.assertEqual("ffmpeg-master_arm64-windows-shared-gpl-develop-261125.zip", archive_name(row, develop=True))
        self.assertEqual("ffmpeg-master-261125", record_release_tag(row))
        row["release_date"] = "2026-02-30"
        with self.assertRaises(ValueError):
            archive_name(row)

    def test_incremental_reuse_only_zip_and_preserve_original_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_variant(root / "old", "2026-11-24", "x64-windows", "shared", b"old shared")
            old_dir = root / "old_assets"
            prior = package_variant(old, old_dir)
            data = root / "data"
            (data / ".git").mkdir(parents=True)
            register_variant(data, prior)
            unchanged = dict(old[0], release_date="2026-11-25")
            new = make_variant(root / "new", "2026-11-25", "arm64-windows", "static", b"new static")
            result = plan_native({"schema": 3, "jobs": [unchanged, new[0]]},
                                 state=PublishedState(directory=data))
            self.assertEqual([new[0]], result["jobs"])
            self.assertEqual(1, len(result["reuse"]))
            output = root / "new_assets"
            fresh = package_variant(new, output)
            self.assertEqual({"binary"}, set(fresh["assets"]))
            plan = root / "plan.json"
            plan.write_text(json.dumps(result), encoding="utf-8")
            uploads = []
            def fetch(source, directory):
                from ffbuild.publication import _verify_distribution
                self.assertEqual(prior["assets"], source["assets"])
                for asset in source["assets"].values():
                    shutil.copyfile(old_dir / asset["file"], directory / asset["file"])
                _verify_distribution(source, directory)
            def upload(tag, files, **kwargs):
                self.assertTrue(kwargs["strict_batch"])
                uploads.append((tag, {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files}))
            with patch.dict(os.environ, {"GH_TOKEN": "mock", "GITHUB_REPOSITORY": "test/repo"}), \
                 patch("ffbuild.publication._fetch_reused", side_effect=fetch), \
                 patch("ffbuild.publication._release_assets", side_effect=upload), \
                 patch("ffbuild.publication._push_data"):
                self.assertEqual(["ffmpeg-9.1-261125"], publish(artifacts_dir=output, data_dir=data, expected_plan=plan))
            self.assertEqual(1, len(uploads))
            self.assertEqual(3, len(uploads[0][1]))
            for asset in prior["assets"].values():
                self.assertEqual(asset["digest"].removeprefix("sha256:"), uploads[0][1][asset["file"]])
            copied = dict(prior, publication_date="2026-11-25")
            stored = yaml.safe_load((data / dated_variant_path(copied)).read_text(encoding="utf-8"))
            self.assertEqual(prior["assets"], stored["assets"])
            self.assertEqual("2026-11-24", stored["release_date"])
            self.assertEqual("2026-11-25", stored["publication_date"])
            index = yaml.safe_load((data / dated_variant_path(copied)).parent.parent.joinpath("version.yaml").read_text(encoding="utf-8"))
            self.assertTrue(index["complete"])
            self.assertNotIn("revision", index)
            self.assertEqual([], plan_native({"schema": 3, "jobs": [unchanged, new[0]]},
                                            state=PublishedState(directory=data))["jobs"])

    def test_same_date_collision_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_variant(root / "old", "2026-11-25", "x64-windows", "static", b"old")
            prior = package_variant(old, root / "old_assets")
            data = root / "data"
            (data / ".git").mkdir(parents=True)
            register_variant(data, prior)
            new = make_variant(root / "new", "2026-11-25", "x64-windows", "static", b"new")
            package_variant(new, root / "new_assets")
            with patch.dict(os.environ, {"GH_TOKEN": "mock", "GITHUB_REPOSITORY": "test/repo"}), \
                 patch("ffbuild.publication._release_assets") as upload:
                with self.assertRaisesRegex(ValueError, "different build"):
                    publish(artifacts_dir=root / "new_assets", data_dir=data)
                upload.assert_not_called()

    def test_draft_is_published_only_after_complete_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "artifact.zip"
            file.write_bytes(b"payload")
            remote = {}
            state = {"created": False}
            def run(*args, **kwargs):
                if args[:3] == ("gh", "release", "create"):
                    self.assertIn("--draft", args)
                    state["created"] = True
                elif args[:3] == ("gh", "release", "upload"):
                    remote[file.name] = {"size": file.stat().st_size, "digest": "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest()}
                elif args[:3] == ("gh", "release", "edit"):
                    self.assertIn("--draft=false", args)
                    self.assertEqual({file.name}, set(remote))
            with patch("ffbuild.publication._run", side_effect=run) as call, \
                 patch("ffbuild.publication._release_api", side_effect=lambda _: {"id": 1, "draft": True} if state["created"] else None), \
                 patch("ffbuild.publication._release_asset_list", side_effect=lambda _: dict(remote)):
                _release_assets("ffmpeg-9.1-261125", [file], upstream_version="9.1", strict_batch=True)
                self.assertEqual(3, call.call_count)

    def test_complete_standard_matrix_has_24_unique_zip_names(self):
        files = set()
        for arch in ("x64", "x86", "arm64", "arm"):
            for license in ("lgpl", "gpl"):
                for linkage in ("static", "shared"):
                    record = {"version": "9.1", "triplet": arch + "-windows",
                              "linkage": linkage, "license": license,
                              "release_date": "2026-11-25"}
                    files.add(archive_name(record))
                    if linkage == "shared":
                        files.add(archive_name(record, develop=True))
        self.assertEqual(24, len(files))
        self.assertTrue(all(name.endswith("-261125.zip") for name in files))

    def test_draft_fallback_uses_authenticated_release_listing(self):
        from types import SimpleNamespace
        missing = SimpleNamespace(returncode=1, stderr="gh: Not Found (HTTP 404)")
        found = SimpleNamespace(returncode=0, stdout=json.dumps([
            [{"id": 1, "tag_name": "other"}],
            [{"id": 2, "tag_name": "ffmpeg-9.1-261125", "draft": True}]
        ]))
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/repo"}), \
             patch("ffbuild.publication.subprocess.run", side_effect=[missing, found]) as call:
            self.assertEqual(2, _release_api("ffmpeg-9.1-261125")["id"])
            self.assertIn("--paginate", call.call_args.args[0])

    def test_master_pin_is_packaged_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = make_variant(root / "master", "2026-11-25", "x64-windows", "static",
                                  b"master", version="9.1", channel="master")
            output = root / "assets"
            record = package_variant(master, output)
            self.assertFalse(record["lts"])
            self.assertEqual("a" * 40, record["source_commit"])
            self.assertEqual("ffmpeg-master-261125", record_release_tag(record))
            self.assertEqual(["ffmpeg-master-261125"], publish(
                artifacts_dir=output, data_dir=root / "unused", dry_run=True))
            path = output / record["assets"]["binary"]["file"]
            with zipfile.ZipFile(path) as archive:
                self.assertEqual("a" * 40, json.loads(
                    archive.read("metadata/BUILD_PROVENANCE.json"))["source"]["upstream_ref"])

    def test_missing_port_license_inside_zip_is_rejected_even_with_new_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "static", b"payload")
            output = root / "assets"
            record = package_variant(variant, output)
            path = output / record["assets"]["binary"]["file"]
            rebuilt = root / "stripped.zip"
            with zipfile.ZipFile(path) as original, zipfile.ZipFile(rebuilt, "w") as target:
                for name in original.namelist():
                    if name != "LICENSES/zlib-x64-windows/copyright":
                        target.writestr(name, original.read(name))
            rebuilt.replace(path)
            record["assets"]["binary"].update(size=path.stat().st_size,
                digest="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
            metadata = next(output.glob("*.var.yaml"))
            metadata.write_text(yaml.safe_dump(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "per-Port evidence"):
                publish(artifacts_dir=output, data_dir=root / "unused", dry_run=True)

    def test_all_cached_abis_with_different_latest_matrix_publish_without_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            (data / ".git").mkdir(parents=True)
            old = make_variant(root / "old", "2026-11-23", "x64-windows", "static", b"rollback")
            common = make_variant(root / "common", "2026-11-23", "arm64-windows", "shared", b"unchanged")
            changed = make_variant(root / "changed", "2026-11-24", "x64-windows", "static", b"latest")
            old_dir = root / "old_assets"
            common_dir = root / "common_assets"
            prior = package_variant(old, old_dir)
            other = package_variant(common, common_dir)
            latest = package_variant(changed, root / "latest_assets")
            register_variant(data, prior)
            register_variant(data, other)
            register_variant(data, latest)
            register_variant(data, dict(other, publication_date="2026-11-24"))
            scan = {"schema": 3, "jobs": [dict(old[0], release_date="2026-11-25"),
                                         dict(common[0], release_date="2026-11-25")]}
            result = plan_native(scan, state=PublishedState(directory=data))
            self.assertEqual([], result["jobs"])
            self.assertTrue(result["publication_required"])
            self.assertEqual(2, len(result["reuse"]))
            plan = root / "plan.json"
            plan.write_text(json.dumps(result), encoding="utf-8")
            def fetch(source, directory):
                source_dir = old_dir if source["abi_hash"] == prior["abi_hash"] else common_dir
                for asset in source["assets"].values():
                    shutil.copyfile(source_dir / asset["file"], directory / asset["file"])
            with patch.dict(os.environ, {"GH_TOKEN": "mock", "GITHUB_REPOSITORY": "test/repo"}), \
                 patch("ffbuild.publication._fetch_reused", side_effect=fetch), \
                 patch("ffbuild.publication._release_assets") as upload, \
                 patch("ffbuild.publication._push_data"):
                self.assertEqual(["ffmpeg-9.1-261125"], publish(
                    artifacts_dir=root / "absent", data_dir=data, expected_plan=plan))
                self.assertEqual(3, len(upload.call_args.args[1]))
            current = plan_native(scan, state=PublishedState(directory=data))
            self.assertFalse(current["publication_required"])
            self.assertEqual([], current["reuse"])

    def test_register_recovers_missing_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "static", b"payload")
            record = package_variant(variant, root / "assets")
            location = register_variant(root / "data", record)
            index = location.parent.parent / "version.yaml"
            index.unlink()
            register_variant(root / "data", record)
            self.assertTrue(index.is_file())


    def test_verified_same_triplet_host_tool_is_not_target_gpl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "static", b"host tool proof")
            job, package, installed, source = variant
            triplet = job["triplet"]
            status = installed / "vcpkg/status"
            text = status.read_text(encoding="utf-8").replace(
                "Package: zlib\nVersion: 1.3.2\nArchitecture: x64-windows",
                "Package: zlib\nVersion: 1.3.2\nArchitecture: x64-windows\nDepends: tool")
            status.write_text(text + "\n\nPackage: tool\nVersion: 1\nArchitecture: x64-windows\n"
                                     "Status: install ok installed\n", encoding="utf-8")
            share = installed / triplet / "share"
            tool = share / "tool"
            tool.mkdir()
            (tool / "copyright").write_text("Tool GNU GPL terms")
            template = json.loads((share / "zlib/vcpkg.spdx.json").read_text())
            document = json.loads(json.dumps(template))
            for row in document["packages"][:2]:
                row["name"] = row["name"].replace("zlib", "tool")
                row["licenseConcluded"] = "GPL-3.0-only"
            (tool / "vcpkg.spdx.json").write_text(json.dumps(document), encoding="utf-8")
            manifest = installed.parent / "ports/zlib/vcpkg.json"
            manifest.parent.mkdir(parents=True)
            raw = json.dumps({"name": "zlib", "version": "1.3.2", "dependencies": [{"name": "tool", "host": True}]}).encode()
            manifest.write_bytes(raw)
            template["files"] = [{"fileName": "./vcpkg.json", "SPDXID": "SPDXRef-port-file-0",
                                  "checksums": [{"algorithm": "SHA256", "checksumValue": hashlib.sha256(raw).hexdigest()}]}]
            template["relationships"] = [{"spdxElementId": "SPDXRef-port-file-0",
                                          "relationshipType": "DEPENDENCY_MANIFEST_OF", "relatedSpdxElement": "SPDXRef-port"}]
            (share / "zlib/vcpkg.spdx.json").write_text(json.dumps(template), encoding="utf-8")
            output = root / "assets"
            record = package_variant(variant, output)
            tool_record = next(p for p in record["compliance"]["packages"] if p["name"] == "tool")
            self.assertEqual("build-only", tool_record["scope"])
            self.assertEqual(["ffmpeg-9.1-261125"], publish(
                artifacts_dir=output, data_dir=root / "unused", dry_run=True))
            manifest.write_bytes(raw + b" ")
            with self.assertRaisesRegex(ValueError, "GPL-only installed dependency"):
                package_variant(variant, root / "bad")

    def test_supplemental_spdx_roundtrip_and_publication_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "static", b"supplemental SPDX")
            job, package, installed, source = variant
            status = installed / "vcpkg/status"
            status.write_text(status.read_text(encoding="utf-8").replace("zlib", "liblzma").replace("1.3.2", "5.8.3"), encoding="utf-8")
            share = installed / job["triplet"] / "share"
            (share / "zlib").rename(share / "liblzma")
            original = share / "liblzma/vcpkg.spdx.json"
            document = json.loads(original.read_text(encoding="utf-8"))
            for row in document["packages"][:2]:
                row["name"] = row["name"].replace("zlib", "liblzma")
                row["licenseConcluded"] = "LicenseRef-vcpkg-null"
            raw = json.dumps(document).encode()
            original.write_bytes(raw)
            output = root / "assets"
            record = package_variant(variant, output)
            item = next(p for p in record["compliance"]["packages"] if p["name"] == "liblzma")
            self.assertEqual("0BSD", item["license_expression"])
            self.assertEqual("local-declaration", item["license_source"])
            with zipfile.ZipFile(output / record["assets"]["binary"]["file"]) as archive:
                self.assertEqual(raw, archive.read("LICENSES/liblzma-x64-windows/vcpkg.spdx.json"))
                provenance = json.loads(archive.read("metadata/BUILD_PROVENANCE.json"))
                declaration = next(p["license_declaration"] for p in provenance["installed_packages"] if p["name"] == "liblzma")
                self.assertEqual("SPDX-2.3", declaration["spdxVersion"])
                self.assertEqual("0BSD", declaration["packages"][0]["licenseConcluded"])
            self.assertEqual(["ffmpeg-9.1-261125"], publish(
                artifacts_dir=output, data_dir=root / "unused", dry_run=True))
            # Publication must not accept a locally changed declaration.
            declarations = root / "declarations"
            declarations.mkdir()
            declaration["packages"][0]["licenseConcluded"] = "MIT"
            (declarations / "liblzma.spdx.json").write_text(json.dumps(declaration), encoding="utf-8")
            with patch("ffbuild.compliance.LICENSE_DECLARATIONS", declarations):
                with self.assertRaisesRegex(ValueError, "Supplemental license declaration differs"):
                    publish(artifacts_dir=output, data_dir=root / "unused", dry_run=True)

    def test_external_system_sdk_roundtrip_and_archive_exclusion(self):
        from ffbuild.compliance import _OPENGL_PORT_SHA256
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "shared", b"system SDK")
            job, package, installed, source = variant
            status = installed / "vcpkg/status"
            status.write_text(status.read_text(encoding="utf-8").replace("zlib", "opengl").replace(
                "1.3.2", "2022-12-04\nPort-Version: 3"), encoding="utf-8")
            share = installed / job["triplet"] / "share"
            (share / "zlib").rename(share / "opengl")
            (share / "opengl/copyright").write_bytes(b"See https://developer.microsoft.com/windows/downloads/windows-10-sdk for the Windows 10 SDK license.")
            file = share / "opengl/vcpkg.spdx.json"
            doc = json.loads(file.read_text(encoding="utf-8"))
            for row in doc["packages"][:2]:
                row["name"] = row["name"].replace("zlib", "opengl")
                row["licenseConcluded"] = "LicenseRef-vcpkg-null"
            doc["files"] = [{"SPDXID": "SPDXRef-port-file-0", "fileName": "./portfile.cmake",
                             "checksums": [{"algorithm": "SHA256", "checksumValue": sorted(_OPENGL_PORT_SHA256)[0]}]}]
            doc["relationships"] = [{"spdxElementId": "SPDXRef-port", "relationshipType": "CONTAINS",
                                     "relatedSpdxElement": "SPDXRef-port-file-0"}]
            for i, filename in enumerate(("include/GL/gl.h", "include/GL/glu.h", "lib/OpenGL32.Lib", "lib/GlU32.Lib")):
                ref = f"SPDXRef-binary-file-{i}"
                doc["files"].append({"SPDXID": ref, "fileName": "./"+filename})
                doc["relationships"].append({"spdxElementId":"SPDXRef-binary","relationshipType":"CONTAINS","relatedSpdxElement":ref})
            file.write_text(json.dumps(doc), encoding="utf-8")
            output = root / "assets"
            record = package_variant(variant, output)
            item = next(p for p in record["compliance"]["packages"] if p["name"] == "opengl")
            self.assertEqual(("system-dependency", "NOASSERTION"), (item["scope"], item["license_expression"]))
            self.assertEqual(["ffmpeg-9.1-261125"], publish(
                artifacts_dir=output, data_dir=root / "unused", dry_run=True))
            sdk = package / "lib/OpenGL32.Lib"
            sdk.parent.mkdir()
            sdk.write_bytes(b"SDK")
            with self.assertRaisesRegex(ValueError, "System SDK file must not be redistributed"):
                package_variant(variant, root / "bad")

if __name__ == "__main__":
    unittest.main()
