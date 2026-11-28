"""Hard gate: a CI FFmpeg Worker must never compile third-party dependencies."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ffbuild.cache_guard import (verify_dependency_cache, verify_from_environment,
                                 verify_no_dependency_builds)
from ffbuild.versions import ROOT


JOB = {
    "yaml": "8.1.3",
    "package": "ffmpeg[all-lgpl,static]",
    "port": "ffmpeg",
    "tester_port": "ffmpeg-tester",
    "triplet": "x64-windows",
}
GRAPH = {
    "ffmpeg_x64-windows": "a" * 64,
    "ffmpeg-tester_x64-windows": "b" * 64,
    "libilbc_x64-windows": "c" * 64,
    "mp3lame_x64-windows": "d" * 64,
}


def cache_archive(cache: Path, abi: str) -> Path:
    path = cache / abi[:2] / (abi + ".zip")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class DependencyCacheGateTests(unittest.TestCase):
    def test_all_external_native_abis_cached_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            for abi in ("c" * 64, "d" * 64):
                cache_archive(cache, abi).write_bytes(b"vcpkg zip")
            with mock.patch("ffbuild.cache_guard.native_abi_query", return_value=GRAPH) as native:
                self.assertEqual(2, verify_dependency_cache(JOB, cache))
                native.assert_called_once_with(
                    [JOB["package"], JOB["tester_port"]], "x64-windows",
                    port_overlay=ROOT / "_work/ffbuild/generated-ports/ffmpeg-8-1-3")
            self.assertFalse(cache_archive(cache, "a" * 64).exists())
            self.assertFalse(cache_archive(cache, "b" * 64).exists())

    def test_target_or_tester_archive_must_not_bypass_real_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            for abi in ("c"*64, "d"*64):
                cache_archive(cache, abi).write_bytes(b"vcpkg zip")
            for abi in ("a"*64, "b"*64):
                target = cache_archive(cache, abi)
                target.write_bytes(b"target archive")
                with self.assertRaisesRegex(RuntimeError, "target/Tester archive"):
                    verify_dependency_cache(JOB, cache, abi_map=GRAPH)
                target.unlink()

    def test_missing_dependency_fails_even_when_seed_cache_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cache_archive(cache, "c" * 64).write_bytes(b"vcpkg zip")
            with mock.patch("ffbuild.cache_guard.native_abi_query", return_value=GRAPH):
                with self.assertRaisesRegex(RuntimeError, "1/2.*mp3lame"):
                    verify_dependency_cache(JOB, cache)

    def test_zero_byte_cached_package_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cache_archive(cache, "c" * 64).write_bytes(b"")
            cache_archive(cache, "d" * 64).write_bytes(b"vcpkg zip")
            with mock.patch("ffbuild.cache_guard.native_abi_query", return_value=GRAPH):
                with self.assertRaisesRegex(RuntimeError, "libilbc"):
                    verify_dependency_cache(JOB, cache)

    def test_missing_target_or_tester_is_not_a_valid_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            for missing in (JOB["port"], JOB["tester_port"]):
                graph = {name: abi for name, abi in GRAPH.items()
                         if not name.startswith(missing + "_")}
                with mock.patch("ffbuild.cache_guard.native_abi_query", return_value=graph):
                    with self.assertRaisesRegex(RuntimeError, "missing selected FFmpeg/Tester"):
                        verify_dependency_cache(JOB, Path(tmp))

    def test_empty_dependency_graph_must_not_pass(self):
        graph = {name: abi for name, abi in GRAPH.items()
                 if name.startswith(("ffmpeg_", "ffmpeg-tester_"))}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("ffbuild.cache_guard.native_abi_query", return_value=graph):
                with self.assertRaisesRegex(RuntimeError, "external dependency graph"):
                    verify_dependency_cache(JOB, Path(tmp))

    def test_actual_dependency_recompilation_is_rejected_after_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            for name in (JOB["port"], JOB["tester_port"], "detect_compiler"):
                file = tree / name / "build.log"
                file.parent.mkdir()
                file.write_text("build transcript", encoding="utf-8")
            verify_no_dependency_builds(JOB, tree)
            external = tree / "libilbc" / "build-x64-windows-rel-out.log"
            external.parent.mkdir()
            external.write_text("unexpected recompilation", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "libilbc"):
                verify_no_dependency_builds(JOB, tree)

    def test_environment_requires_valid_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "Missing CI job"):
                    verify_from_environment(job_env="FFBUILD_JOB", cache_dir=Path(tmp))
            with mock.patch.dict(os.environ, {"FFBUILD_JOB": json.dumps(JOB)}):
                with mock.patch("ffbuild.cache_guard.native_abi_query", return_value=GRAPH):
                    with self.assertRaisesRegex(RuntimeError, "incomplete"):
                        verify_from_environment(job_env="FFBUILD_JOB", cache_dir=Path(tmp))

    def test_worker_requires_gate_before_native_vcpkg_build(self):
        ci = yaml.safe_load(
            (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"))
        for matrix in ("build",):
            with self.subTest(matrix=matrix):
                steps = ci["jobs"][matrix]["steps"]
                gate = next(i for i, step in enumerate(steps)
                            if step.get("name") == "Require exact third-party binary cache coverage")
                build = next(i for i, step in enumerate(steps)
                             if step.get("name") == "Build and test via native vcpkg")
                self.assertEqual(build - 1, gate)
                self.assertIn("ffbuild.ci restore-dependencies", steps[gate]["run"])
                self.assertNotIn("--recurse", steps[build]["run"])
                self.assertIn("VCPKG_ROOT", steps[gate]["env"])
                self.assertIn("--cache-dir=", steps[gate]["run"])
                self.assertIn("ffvcpkg install", steps[build]["run"])
                self.assertEqual("Verify no external dependencies were compiled by Worker",
                                 steps[build + 1]["name"])
                self.assertIn("ffbuild.ci audit-worker", steps[build + 1]["run"])


class NativeCacheOnly(unittest.TestCase):
    def test_native_feature_plan_is_exact(self):
        from ffbuild.native_abi import planned_specs
        text = """Computing installation plan...
The following packages will be built and installed:
  * audit-dep[core,extra]:x64-windows@1.0.0
    ffmpeg[core,all-gpl]:arm64-windows@8.1.3
    ffmpeg-tester:arm64-windows@1.0.0
Additional packages (*) will be modified to complete this operation.
"""
        self.assertEqual({"audit-dep_x64-windows": "audit-dep[core,extra]:x64-windows",
                          "ffmpeg_arm64-windows": "ffmpeg[all-gpl,core]:arm64-windows",
                          "ffmpeg-tester_arm64-windows": "ffmpeg-tester[core]:arm64-windows"}, planned_specs(text))
        with self.assertRaises(ValueError):
            planned_specs(text.replace("audit-dep[core,extra]", "invalid package"))

    def test_target_plan_rejects_unexpected_dependency_build(self):
        from ffbuild import cache_guard
        output = "The following packages will be built and installed:\n    ffmpeg:x64-windows@8.1.3\n    ffmpeg-tester:x64-windows@1.0\n  * mp3lame:x64-windows@3.100\n"
        with mock.patch.object(cache_guard, "vcpkg_command", side_effect=lambda args: args), \
                mock.patch.object(cache_guard.subprocess, "run", return_value=mock.Mock(stdout=output)):
            with self.assertRaisesRegex(RuntimeError, "external dependency"):
                cache_guard.require_target_plan(JOB, port=Path("port"), paths=[], env={},
                                                expected={"ffmpeg_x64-windows", "ffmpeg-tester_x64-windows"})

    @unittest.skipUnless(os.environ.get("FFBUILD_TEST_VCPKG_BIN"), "Set native vcpkg binary for tiny real cache-only smoke")
    def test_native_cache_only_rejects_corruption_without_building_dependency(self):
        from ffbuild import cache_guard, native_abi
        import ffvcpkg
        binary = Path(os.environ["FFBUILD_TEST_VCPKG_BIN"]).resolve()
        with tempfile.TemporaryDirectory(prefix="ffbuild-cache-only-") as tmp:
            root = Path(tmp); ports = root / "ports"; ports.mkdir(); cache = root / "cache"; cache.mkdir()
            shutil.copytree(ROOT / "triplets", root / "triplets")
            marker = root / "dep-built"
            payload = 'file(MAKE_DIRECTORY "${CURRENT_PACKAGES_DIR}/include")\nfile(WRITE "${CURRENT_PACKAGES_DIR}/include/${PORT}.h" "/* fixture */")\nfile(INSTALL "${CMAKE_CURRENT_LIST_DIR}/copyright" DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")\n'
            def make(name, fields, content):
                port = ports / name; port.mkdir()
                (port / "vcpkg.json").write_text(json.dumps(dict(name=name, version="1.0.0", license="MIT", **fields)))
                (port / "portfile.cmake").write_text(content)
                (port / "copyright").write_text("MIT fixture")
                return port
            make("audit-dep", {"features": {"extra": {"description": "required"}, "default-extra": {"description": "default"}},
                               "default-features": ["default-extra"]}, payload + f'file(WRITE "{marker.as_posix()}" "built")\n')
            ffmpeg = make("ffmpeg", {"dependencies": [{"name": "audit-dep", "default-features": False, "features": ["extra"]}],
                                    "features": {"all-gpl": {"description": "fixture"}}}, payload)
            make("ffmpeg-tester", {"dependencies": [{"name": "ffmpeg", "default-features": False}]}, payload)
            env = dict(os.environ, FFVCPKG_BIN=str(binary), VCPKG_ROOT=str(binary.parent),
                       VCPKG_BINARY_SOURCES=f"clear;files,{cache},readwrite")
            job = dict(JOB, package="ffmpeg[all-gpl]")
            def paths(name):
                return [f"--x-install-root={root / name}", f"--x-buildtrees-root={root / (name + '-trees')}",
                        f"--x-packages-root={root / (name + '-packages')}"]
            with mock.patch.object(native_abi, "ROOT", root), mock.patch.object(cache_guard, "ROOT", root), \
                    mock.patch.object(ffvcpkg, "ROOT", root), mock.patch.dict(os.environ, env):
                specs = {}
                graph = native_abi.native_abi_query([job["package"], job["tester_port"]], job["triplet"],
                                                      port_overlay=ffmpeg, binary=binary, env=env, specs=specs)
                subprocess.run(ffvcpkg.command(["install", specs["audit-dep_x64-windows"],
                    "--triplet=x64-windows", f"--overlay-ports={ffmpeg}", f"--overlay-ports={ports}", *paths("seed")]),
                    cwd=root, env=ffvcpkg.environment(env), check=True)
                self.assertTrue(marker.is_file()); marker.unlink()
                env["VCPKG_BINARY_SOURCES"] = f"clear;files,{cache},read"
                self.assertEqual(graph, cache_guard.restore_dependencies(job, cache, port=ffmpeg,
                                  installed=root / "good", paths=paths("good"), env=env))
                self.assertFalse(marker.exists())
                archive = cache_archive(cache, graph["audit-dep_x64-windows"])
                archive.write_bytes(b"not a ZIP")
                with self.assertRaises(subprocess.CalledProcessError):
                    cache_guard.restore_dependencies(job, cache, port=ffmpeg,
                            installed=root / "bad", paths=paths("bad"), env=env)
                self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
