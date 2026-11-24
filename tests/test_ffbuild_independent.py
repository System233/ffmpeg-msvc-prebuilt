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

from ffbuild.identity import variant_name
from ffbuild.package import package_job
from ffbuild.port import generate_port
from ffbuild.spec import FeatureSet, read_spec, resolve_features
from ffbuild.state import PublishedState
from ffbuild.store import register_variant
from ffbuild.targets import Target
from ffbuild.planner import plan
from ffbuild.versions import ROOT, versions


class NoLegacyImplementation(unittest.TestCase):
    def test_same_license_linkage_different_features_have_distinct_data_files(self):
        targets = (
            Target("ffmpeg[all-lgpl,static]", "x64-windows", ("all-lgpl", "static")),
            Target("ffmpeg[base,static]", "x64-windows", ("base", "static")),
        )
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)
            jobs = plan(version="8.1.3", targets=targets,
                        state=PublishedState(directory=db))["jobs"]
            self.assertEqual(2, len(jobs))
            self.assertEqual({("lgpl", "static")},
                             {(j["license"], j["linkage"]) for j in jobs})
            self.assertEqual(2, len({j["feature_hash"] for j in jobs}))
            self.assertEqual(2, len({j["variant_hash"] for j in jobs}))
            self.assertEqual(2, len({j["id"] for j in jobs}))
            for job in jobs:
                record = {**job, "variant_id": job["id"],
                          "package_spec": job["package"],
                          "assets": {"binary": {"file": job["id"] + ".zip"}}}
                register_variant(db, record)
            state = PublishedState(directory=db)
            self.assertEqual([], plan(version="8.1.3", targets=targets,
                                      state=state)["jobs"])
            self.assertEqual(2, len(list(db.rglob("variants/*.yaml"))))
            index = next(db.rglob("version.yaml"))
            self.assertEqual(16, yaml.safe_load(index.read_text())["total_variants"])

    def test_import_graph_is_isolated(self):
        for source in (ROOT / "ffbuild").rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for statement in ast.walk(tree):
                if isinstance(statement, ast.Import):
                    for name in statement.names:
                        self.assertFalse(name.name.startswith(("scripts", "ffport", "ops")), source)
                if isinstance(statement, ast.ImportFrom) and statement.level == 0:
                    self.assertFalse((statement.module or "").startswith(("scripts", "ffport", "ops")), source)

    def test_no_legacy_template_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            port = generate_port("8.1.3", destination=Path(temp))
            text = (port / "portfile.cmake").read_text(encoding="utf-8")
            self.assertNotIn("scripts/", text)
            self.assertNotIn("builder/ffmpeg-portfile.cmake", text)
            self.assertIn("vcpkg_from_github", text)

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
from ffbuild.planner import plan
from ffbuild.port import generate_port
from ffbuild.state import PublishedState
with TemporaryDirectory() as temporary:
    from ffbuild.targets import Target
    result = plan(version='8.1.3', targets=(Target('ffmpeg[all-lgpl,static]',
                  'x64-windows', ('all-lgpl','static')),),
                  state=PublishedState(directory=Path(temporary)))
    assert len(result['jobs']) == 1
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
        # Stub vcpkg's native CMake helpers; parse the whole generated recipe,
        # not just its policy file, without executing any real build process.
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
                    'set(VCPKG_TARGET_IS_WINDOWS TRUE)',
                    'set(VCPKG_TARGET_IS_MINGW FALSE)',
                    'set(VCPKG_TARGET_ARCHITECTURE x64)',
                    'set(VCPKG_CONCURRENCY 2)',
                    'set(TARGET_TRIPLET x64-windows)',
                    f'set(CURRENT_BUILDTREES_DIR "{root.as_posix()}/buildtrees")',
                    f'set(CURRENT_PACKAGES_DIR "{root.as_posix()}/packages")',
                    f'function(vcpkg_from_github)\n  set(SOURCE_PATH "{root.as_posix()}" PARENT_SCOPE)\nendfunction()',
                    f'function(vcpkg_acquire_msys output)\n  set(${{output}} "{root.as_posix()}" PARENT_SCOPE)\nendfunction()',
                    f'function(vcpkg_cmake_get_vars output)\n  set(${{output}} "{(root / "vars.cmake").as_posix()}" PARENT_SCOPE)\nendfunction()',
                    f'function(vcpkg_find_acquire_program output)\n  set(${{output}} "{root.as_posix()}/tool.exe" PARENT_SCOPE)\nendfunction()',
                    'function(vcpkg_add_to_path)\nendfunction()',
                    'function(z_vcpkg_setup_pkgconfig_path)\nendfunction()',
                    'function(z_vcpkg_restore_pkgconfig_path)\nendfunction()',
                    'function(vcpkg_execute_required_process)\nendfunction()',
                    'function(vcpkg_copy_tools)\nendfunction()',
                    'function(vcpkg_fixup_pkgconfig)\nendfunction()',
                    'function(vcpkg_copy_pdbs)\nendfunction()',
                    f'include("{(port / "portfile.cmake").as_posix()}")',
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
            (package / "share" / "ffmpeg" / "copyright").write_text("LGPL/GPL license",encoding="utf-8")
            (package / "bin" / "ffmpeg.exe").write_bytes(b"FFMPEG binary")
            (package / "bin" / "avcodec.dll").write_bytes(b"release dll")
            (package / "include" / "avcodec.h").write_bytes(b"header")
            (package / "lib" / "avcodec.lib").write_bytes(b"import lib")
            (package / "debug" / "lib" / "avcodec.lib").write_bytes(b"debug lib")
            job = planned
            version = job["version"]
            metadata = package_job(package, job, root / "release")
            record = yaml.safe_load(metadata.read_text(encoding="utf-8"))
            self.assertEqual(variant_name(version, 0, "x64-windows", "shared", "gpl",
                                          job["feature_hash"]),
                             record["variant_id"])
            self.assertEqual(job["build_hash"], record["build_hash"])
            with zipfile.ZipFile(root / "release" / record["assets"]["binary"]["file"]) as archive:
                self.assertIn("bin/ffmpeg.exe", archive.namelist())
                self.assertNotIn("debug/lib/avcodec.lib", archive.namelist())
            with zipfile.ZipFile(root / "release" / record["assets"]["develop"]["file"]) as archive:
                self.assertIn("debug/lib/avcodec.lib", archive.namelist())
            db = root / "data"
            record_path = register_variant(db, record)
            self.assertTrue(record_path.exists())
            self.assertEqual(1, yaml.safe_load((record_path.parent.parent / "version.yaml").read_text())["variant_count"])
            self.assertTrue(PublishedState(directory=db).target_exists(
                version, 0, "x64-windows", job["feature_hash"],
                job["build_hash"], job["variant_hash"]))
            modified = dict(record)
            modified["assets"] = dict(record["assets"])
            modified["assets"]["binary"] = {"file": "different.zip"}
            with self.assertRaisesRegex(ValueError, "different release assets"):
                register_variant(db, modified)


if __name__ == "__main__":
    unittest.main()
