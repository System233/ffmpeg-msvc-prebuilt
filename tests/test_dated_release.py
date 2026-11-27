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
from ffbuild.identity import archive_name, record_release_tag, dated_variant_path, variant_name, audit_name
from ffbuild.package import package_job
from ffbuild.compliance import PUBLIC_COPYRIGHT, PUBLIC_SPDX
from ffbuild.planner import plan_native
from ffbuild.publication import publish, _release_assets, _release_api
from ffbuild.state import PublishedState
from ffbuild import catalog
from ffbuild.catalog import register_release


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
    def test_production_tag_only_after_verified_complete_batch(self):
        from ffbuild.native_abi import build_requests
        from ffbuild import release_trigger
        day = "2026-11-25"
        commit = "a"*40
        request = {"yaml":"9.1","date":day,"repository_commit":commit,
                   "production":True,"ref":"","commit":"","sha512":""}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / ".git").mkdir()
            catalog.write_json(data / "index.json", {"schema":2,"releases":[],"master":[]})
            out = root / "out"
            out.mkdir()
            rows, blocked = build_requests(version="9.1", release_date=day)
            self.assertEqual(16, len(rows))
            self.assertFalse(blocked)
            for i,row in enumerate(rows):
                row["abi_hash"] = hashlib.sha256(str(i).encode()).hexdigest()
                row["id"] = variant_name("9.1",0,row["triplet"],row["linkage"],row["license"],abi_hash=row["abi_hash"])
                record = dict(row, variant_id=row["id"], channel="release", package_format=2,
                              package_spec=row["package"])
                record["assets"] = {}
                for kind in (("binary","debug") if row["linkage"]=="shared" else ("binary",)):
                    name = archive_name(record,kind=kind)
                    payload = (name+" fixture").encode()
                    (out/name).write_bytes(payload)
                    record["assets"][kind] = {"file":name,"size":len(payload),"digest":"sha256:"+hashlib.sha256(payload).hexdigest()}
                (out/(row["id"]+".var.yaml")).write_text(yaml.safe_dump(record),encoding="utf-8")
            plan = root/"plan.json"
            plan.write_text(json.dumps({"schema":3,"jobs":rows,"reuse":[],"request":request}),encoding="utf-8")
            env = {"FFBUILD_PUBLISH":"true","FFBUILD_PUBLISH_VERSION":"9.1",
                   "FFBUILD_PUBLISH_DATE":day,"GITHUB_REF":"refs/heads/main",
                   "GITHUB_EVENT_NAME":"workflow_dispatch","GITHUB_SHA":commit,
                   "GH_TOKEN":"mock","GITHUB_REPOSITORY":"test/repo"}
            actions=[]
            def verified(*args,**kwargs):
                actions.append("verified")
            def allocate(*args):
                self.assertEqual(16,actions.count("verified"))
                actions.append("allocate")
                return "ffmpeg-9.1-261125R2",False
            def write(*args, **kwargs):
                self.assertEqual("allocate",actions[-1])
                actions.append("tag")
            def release(*args,**kwargs):
                self.assertEqual("tag",actions[-1])
                self.assertEqual(24,len(args[1]))
                actions.append("release")
            with (patch.dict(os.environ,env),
                  patch("ffbuild.publication._verify_distribution",side_effect=verified),
                  patch.object(release_trigger,"git",return_value=commit),
                  patch.object(release_trigger,"publication_tag_candidate",side_effect=allocate) as alloc,
                  patch.object(release_trigger,"write_publication_tag",side_effect=write) as create,
                  patch("ffbuild.publication._release_api",return_value=None),
                  patch("ffbuild.publication._release_assets",side_effect=release),
                  patch("ffbuild.publication._push_data")):
                file = next(out.glob("*.var.yaml"))
                text = file.read_bytes()
                file.unlink()
                with self.assertRaisesRegex(RuntimeError,"Missing planned"):
                    publish(artifacts_dir=out,data_dir=data,expected_plan=plan)
                alloc.assert_not_called()
                create.assert_not_called()
                file.write_bytes(text)
                actions.clear()
                self.assertEqual(["ffmpeg-9.1-261125R2"],
                    publish(artifacts_dir=out,data_dir=data,expected_plan=plan))
                create.assert_called_once()
                self.assertEqual(["allocate","tag","release"],actions[-3:])
                shard = catalog.load_shard(data,"releases","9.1")
                self.assertEqual("ffmpeg-9.1-261125R2",shard["releases"][0]["tag"])
                self.assertEqual(16,len(shard["releases"][0]["variants"]))

    def test_public_naming_and_master(self):
        row = {"version": "9.1", "triplet": "arm64-windows", "linkage": "shared",
               "license": "gpl", "release_date": "2026-11-25"}
        self.assertEqual("ffmpeg-9.1_arm64-windows-shared-gpl-261125.zip", archive_name(row))
        self.assertEqual("ffmpeg-9.1_arm64-windows-shared-gpl-debug-261125.zip", archive_name(row, kind="debug"))
        self.assertEqual("ffmpeg-9.1-261125", record_release_tag(row))
        row.update(channel="master", version="9.2-123-gabc")
        self.assertEqual("ffmpeg-master_arm64-windows-shared-gpl-debug-261125.zip", archive_name(row, kind="debug"))
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
            register_release(data, [dict(prior, expected_variants=1)])
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
                _verify_distribution(source, directory, reused=True)
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
            shard = catalog.load_shard(data, "releases", "9.1")
            rows = catalog.expanded("releases", "9.1", shard["releases"][0])
            stored = next(row for row in rows if row["triplet"] == prior["triplet"])
            self.assertEqual(prior["assets"], stored["assets"])
            self.assertNotIn("compliance", stored)
            self.assertTrue(all(p.suffix == ".json" for p in data.rglob("*") if p.is_file()))
            self.assertEqual("2026-11-24", stored["release_date"])
            self.assertEqual("2026-11-25", stored["publication_date"])
            self.assertEqual(2, len(rows))
            self.assertEqual("ffmpeg-9.1-261125", shard["releases"][0]["tag"])
            self.assertNotIn("revision", shard["releases"][0])
            self.assertEqual([], plan_native({"schema": 3, "jobs": [unchanged, new[0]]},
                                            state=PublishedState(directory=data))["jobs"])

    def test_same_date_collision_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = make_variant(root / "old", "2026-11-25", "x64-windows", "static", b"old")
            prior = package_variant(old, root / "old_assets")
            data = root / "data"
            (data / ".git").mkdir(parents=True)
            register_release(data, [dict(prior, expected_variants=1)])
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
                        files.add(archive_name(record, kind="debug"))
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
            with zipfile.ZipFile(output / audit_name(record)) as archive:
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
                    if name != PUBLIC_COPYRIGHT:
                        target.writestr(name, original.read(name))
            rebuilt.replace(path)
            record["assets"]["binary"].update(size=path.stat().st_size,
                digest="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
            metadata = next(output.glob("*.var.yaml"))
            metadata.write_text(yaml.safe_dump(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing distribution license file"):
                publish(artifacts_dir=output, data_dir=root / "unused", dry_run=True)

    def test_data_contains_only_release_index_and_reuse_survives_audit_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "static", b"audit payload")
            output = root / "assets"
            record = package_variant(variant, output)
            audit = output / audit_name(record)
            data = root / "data"
            scan = {"schema": 3, "jobs": [variant[0]]}
            record["internal_debug"] = {"must_not_persist": True}
            location = register_release(data, [dict(record, expected_variants=1)])
            shard = catalog.read_json(location)
            stored = catalog.expanded("releases", "9.1", shard["releases"][0])[0]
            self.assertEqual(record["assets"], stored["assets"])
            self.assertNotIn("compliance", location.read_text())
            self.assertNotIn("internal_debug", location.read_text())
            self.assertNotIn("features", location.read_text())
            self.assertEqual(2, len(list(data.rglob("*.json"))))
            self.assertTrue(all(p.suffix == ".json" for p in data.rglob("*") if p.is_file()))
            audit.unlink()
            self.assertEqual([], plan_native(scan, state=PublishedState(directory=data))["jobs"])
            from ffbuild.publication import _verify_distribution
            _verify_distribution(stored, output, reused=True)
            with self.assertRaisesRegex(ValueError, "Missing or invalid internal license audit"):
                publish(artifacts_dir=output, data_dir=root / "unused", dry_run=True)
            # The published archive digest is still mandatory on the reuse path.
            public = output / stored["assets"]["binary"]["file"]
            public.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "digest or size mismatch"):
                _verify_distribution(stored, output, reused=True)
            shard["releases"][0]["variants"]["x64-windows-static-lgpl"]["format"] = 99
            catalog.write_json(location, shard)
            with self.assertRaisesRegex(ValueError, "Invalid catalog ABI or format"):
                plan_native(scan, state=PublishedState(directory=data))

    def test_public_copyright_reproduced_from_original_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "assets"
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "static", b"audit payload")
            record = package_variant(variant, output)
            public = output / record["assets"]["binary"]["file"]
            audit = output / audit_name(record)
            def rewrite(path, transform):
                replacement = path.with_suffix(".replacement.zip")
                with zipfile.ZipFile(path) as source, zipfile.ZipFile(replacement, "w") as target:
                    for name in source.namelist():
                        target.writestr(name, transform(name, source.read(name)))
                replacement.replace(path)
            altered = b"FFmpeg only, third-party license omitted"
            rewrite(public, lambda name, raw: altered if name == PUBLIC_COPYRIGHT else raw)
            record["assets"]["binary"].update(size=public.stat().st_size, digest="sha256:" + hashlib.sha256(public.read_bytes()).hexdigest())
            record["compliance"]["copyright_sha256"] = hashlib.sha256(altered).hexdigest()
            def bind_assets(name, raw):
                if name != "metadata/BUILD_PROVENANCE.json":
                    return raw
                provenance = json.loads(raw)
                provenance["assets"] = record["assets"]
                return json.dumps(provenance).encode()
            rewrite(audit, bind_assets)
            record["compliance"]["audit_sha256"] = hashlib.sha256(audit.read_bytes()).hexdigest()
            next(output.glob("*.var.yaml")).write_text(yaml.safe_dump(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Public license evidence differs from original audit"):
                publish(artifacts_dir=output, data_dir=root / "unused", dry_run=True)

    def test_reject_other_share_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "assets"
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "shared", b"share payload")
            record = package_variant(variant, output)
            path = output / record["assets"]["binary"]["file"]
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("share/zlib/copyright", b"conflicting package")
            record["assets"]["binary"].update(size=path.stat().st_size, digest="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
            next(output.glob("*.var.yaml")).write_text(yaml.safe_dump(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected public archive member: share/zlib"):
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
            register_release(data, [prior, other])
            register_release(data, [latest, dict(other, publication_date="2026-11-24")])
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

    def test_register_batch_is_idempotent_and_rejects_partial_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            variant = make_variant(root / "build", "2026-11-25", "x64-windows", "static", b"payload")
            record = package_variant(variant, root / "assets")
            data = root / "data"
            with self.assertRaisesRegex(ValueError, "Incomplete dated release matrix"):
                register_release(data, [record])
            self.assertFalse(data.exists())
            record["expected_variants"] = 1
            location = register_release(data, [record])
            original = {p: p.read_bytes() for p in data.rglob("*.json")}
            self.assertEqual(location, register_release(data, [record]))
            self.assertEqual(original, {p: p.read_bytes() for p in data.rglob("*.json")})

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
            with zipfile.ZipFile(output / record["assets"]["binary"]["file"]) as archive:
                self.assertNotIn(b"Tool GNU GPL terms", archive.read(PUBLIC_COPYRIGHT))
                self.assertTrue(any(r["relationshipType"] == "BUILD_DEPENDENCY_OF" for r in json.loads(archive.read(PUBLIC_SPDX))["relationships"]))
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
            with zipfile.ZipFile(output / audit_name(record)) as archive:
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
