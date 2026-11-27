"""Independent build manager: feature compilation, package and DB round-trip."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml
from compliance_fixture import make_compliance_fixture

from ffbuild.identity import variant_name, archive_name
from ffbuild.package import package_job
from ffbuild.port import generate_port
from ffbuild.spec import FeatureSet, read_spec, resolve_features
from ffbuild.state import PublishedState
from ffbuild.catalog import register_release
from ffbuild.targets import Target
from native_fixture import plan_fixture as plan, install_abi, release_record
from ffbuild.versions import ROOT, versions


class NoLegacyImplementation(unittest.TestCase):
    def test_same_slot_distinct_abi_cannot_share_public_release(self):
        targets = (Target("ffmpeg[all-lgpl,static]", "x64-windows", ("all-lgpl","static")),
                   Target("ffmpeg[base,static]", "x64-windows", ("base","static")))
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)
            jobs = plan(version="8.1.3", targets=targets, state=PublishedState(directory=db))["jobs"]
            self.assertEqual(2, len({j["abi_hash"] for j in jobs}))
            self.assertEqual(2, len({j["id"] for j in jobs}))
            with self.assertRaisesRegex(ValueError, "Duplicate|duplicate"):
                register_release(db, [release_record(j) for j in jobs])

    def test_import_graph_is_isolated(self):
        for source in (ROOT / "scripts/ffbuild").rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for statement in ast.walk(tree):
                if isinstance(statement, ast.Import):
                    for name in statement.names:
                        self.assertFalse(name.name.startswith(("scripts", "ffport", "ops")), source)
                if isinstance(statement, ast.ImportFrom) and statement.level == 0:
                    self.assertFalse((statement.module or "").startswith(("scripts", "ffport", "ops")), source)

    def test_original_build_engine_is_used_by_versioned_port(self):
        with tempfile.TemporaryDirectory() as temp:
            port = generate_port("8.1.3", destination=Path(temp))
            text = (port / "portfile.cmake").read_text(encoding="utf-8")
            self.assertNotIn("scripts/", text)
            self.assertIn('include("${CMAKE_CURRENT_LIST_DIR}/builder/ffmpeg-portfile.cmake")', text)
            self.assertNotIn("vcpkg_from_github", text)
            self.assertEqual((ROOT / "scripts/cmake/ffmpeg-portfile.cmake").read_bytes(),
                             (port / "builder/ffmpeg-portfile.cmake").read_bytes())

    def test_plan_and_port_execute_without_legacy_imports(self):
        probe = '''
import builtins
from pathlib import Path
from tempfile import TemporaryDirectory
_real_import = builtins.__import__
def isolated(name, *args, **kwargs):
    if name == 'scripts' or name.startswith('scripts.') or name in ('ffport', 'ops'):
        raise AssertionError('unexpected legacy import: ' + name)
    return _real_import(name, *args, **kwargs)
builtins.__import__ = isolated
from ffbuild.native_abi import build_requests
from ffbuild.port import generate_port
from ffbuild.state import PublishedState
with TemporaryDirectory() as temporary:
    from ffbuild.targets import Target
    jobs, blocked = build_requests(version='8.1.3', targets=(Target('ffmpeg[all-lgpl,static]',
                  'x64-windows', ('all-lgpl','static')),))
    assert len(jobs) == 1 and not blocked
    assert (generate_port('8.1.3', destination=Path(temporary)) / 'policy.cmake').is_file()
'''
        run = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_all_versions_use_the_same_metadata_compiler(self):
        for version in versions():
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as temp:
                    spec, sources = read_spec(version)
                    sha = spec.get("source", {}).get("sha512") or "0" * 128
                    port = generate_port(version, destination=Path(temp), sha512=sha)
                    manifest = json.loads((port / "vcpkg.json").read_text(encoding="utf-8"))
                    graph = resolve_features(spec, version)
                    self.assertEqual(set(graph.definitions), set(manifest["features"]))
                    self.assertIn("base.yaml", {p.name for p in sources})
                    self.assertTrue((port / "policy.cmake").is_file())
                    self.assertTrue((port / "portfile.cmake").is_file())

    def test_feature_policy_is_not_automatic_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = json.loads((generate_port("8.1.3", destination=Path(temp)) /
                                   "vcpkg.json").read_text())
            self.assertEqual(["x264"], manifest["features"]["x264"]["dependencies"])
            self.assertNotIn("license-gpl", json.dumps(manifest["features"]["x264"]))
            self.assertIn("license-gpl", json.dumps(manifest["features"]["all-gpl"]))

    @unittest.skipUnless(shutil.which("cmake"), "CMake is needed for port recipe parsing")
    def test_native_port_policy_survives_direct_vcpkg_execution(self):
        # The restored original CMake builder includes ../constraints.cmake.
        # Run the exact generated guard with CMake without invoking any build.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            port = generate_port("3.4.14", destination=root)
            (root / "vars.cmake").write_text("# Stub compiler variables\n", encoding="utf-8")
            script = root / "probe.cmake"
            fixtures = [
                ("all-lgpl;lgpl;openssl", False),
                ("all-nonfree;openssl;license-gpl;license-nonfree", True),
                ("all-gpl;gpl;x264;license-gpl", True),
                ("all-lgpl;lgpl;x264", False),
            ]
            for enabled, expected in fixtures:
                script.write_text('\n'.join([
                    f'set(FEATURES "{enabled}")',
                    f'include("{(port / "constraints.cmake").as_posix()}")',
                ]) + '\n', encoding="utf-8")
                result = subprocess.run(["cmake", "-P", str(script)],
                                        capture_output=True, text=True)
                self.assertEqual(expected, result.returncode == 0,
                                 f"{enabled}: {result.stderr}")


class PackageRoundTrip(unittest.TestCase):
    def test_shared_artifact_metadata_and_local_hash_lookup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "ffmpeg_x64-windows"
            (package / "share" / "ffmpeg").mkdir(parents=True)
            (package / "bin").mkdir()
            (package / "include").mkdir()
            (package / "lib").mkdir()
            (package / "debug" / "lib").mkdir(parents=True)
            target = Target("ffmpeg[license-gpl]", "x64-windows", ("license-gpl",))
            planned = plan(version="8.1.3", targets=(target,),
                           state=PublishedState(directory=root / "empty"))["jobs"][0]
            (package / "CONTROL").write_text(
                "Package: ffmpeg\nVersion: 8.1.3\nPort-Version: 0\n\n" +
                "\n\n".join(f"Feature: {name}" for name in planned["features"]),
                encoding="utf-8")
            (package / "BUILD_INFO").write_text("LibraryLinkage: dynamic\n",encoding="utf-8")
            (package / "share" / "ffmpeg" / "copyright").write_text(
                "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n",
                encoding="utf-8")
            (package / "share/ffmpeg/vcpkg.spdx.json").write_bytes(b"native SPDX")
            (package / "share/ffmpeg/vcpkg_abi_info.txt").write_bytes(b"native ABI")
            (package / "share/ffmpeg/FindFFmpeg.cmake").write_bytes(b"consumer config")
            (package / "share/zlib").mkdir()
            (package / "share/zlib/copyright").write_bytes(b"unrelated share payload")
            (package / "bin" / "ffmpeg.exe").write_bytes(b"FFMPEG binary")
            from symbol_fixture import pe, pdb
            (package / "bin" / "avcodec.dll").write_bytes(pe())
            (package / "bin" / "avcodec.pdb").write_bytes(pdb())
            (package / "debug/bin").mkdir()
            (package / "debug/bin/avcodec.dll").write_bytes(pe(guid=b"d"*16))
            (package / "debug/bin/avcodec.pdb").write_bytes(pdb(guid=b"d"*16))
            (package / "include" / "avcodec.h").write_bytes(b"header")
            (package / "lib" / "avcodec.lib").write_bytes(b"import lib")
            (package / "debug" / "lib" / "avcodec.lib").write_bytes(b"debug lib")
            job = planned
            install_abi(package, job)
            version = job["version"]
            installed, source_tree = make_compliance_fixture(
                root, job, package / "share" / "ffmpeg" / "copyright")
            metadata = package_job(
                package, job, root / "release",
                installed_root=installed, source_tree=source_tree)
            record = yaml.safe_load(metadata.read_text(encoding="utf-8"))
            self.assertEqual(2, record["package_format"])
            self.assertEqual(archive_name(job), record["assets"]["binary"]["file"])
            self.assertEqual({"binary", "debug"}, set(record["assets"]))
            self.assertEqual(variant_name(version, 0, "x64-windows", "shared", "gpl",
                                          abi_hash=job["abi_hash"]),
                             record["variant_id"])
            self.assertEqual(job["abi_hash"], record["abi_hash"])
            with zipfile.ZipFile(root / "release" / record["assets"]["binary"]["file"]) as archive:
                self.assertIn("bin/ffmpeg.exe", archive.namelist())
                self.assertNotIn("debug/lib/avcodec.lib", archive.namelist())
                self.assertIn("share/ffmpeg/copyright", archive.namelist())
                self.assertIn(b"zlib license text", archive.read("share/ffmpeg/copyright"))
                self.assertIn("share/ffmpeg/sbom.spdx.json", archive.namelist())
                self.assertFalse(any(n.startswith(("LICENSES/", "metadata/")) for n in archive.namelist()))
                self.assertNotIn("CONTROL", archive.namelist())
                self.assertNotIn("BUILD_INFO", archive.namelist())
                self.assertEqual({"share/ffmpeg/copyright", "share/ffmpeg/sbom.spdx.json", "share/ffmpeg/FindFFmpeg.cmake"},
                                 {name for name in archive.namelist() if name.startswith("share/")})
            with zipfile.ZipFile(root / "release" / record["assets"]["debug"]["file"]) as archive:
                self.assertIn("debug/lib/avcodec.lib", archive.namelist())
                self.assertEqual({"share/ffmpeg/copyright", "share/ffmpeg/sbom.spdx.json"},
                                 {name for name in archive.namelist() if name.startswith("share/")})
                self.assertNotIn("bin/ffmpeg.exe", archive.namelist())
            from ffbuild.publication import _verify_distribution
            _verify_distribution(record, root / "release")
            db = root / "data"
            register_release(db, [record])
            self.assertEqual(1, len(list(db.glob("releases/*.json"))))
            self.assertIsNotNone(PublishedState(directory=db).find_abi(version, "x64-windows", job["abi_hash"]))
            modified = dict(record, assets=dict(record["assets"]))
            modified["assets"]["binary"] = dict(record["assets"]["binary"], digest="sha256:" + "f"*64)
            with self.assertRaisesRegex(ValueError, "different|immutable|conflict"):
                register_release(db, [modified])


if __name__ == "__main__":
    unittest.main()
