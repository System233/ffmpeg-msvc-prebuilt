"""Hard gate: a CI FFmpeg Worker must never compile third-party dependencies."""
from __future__ import annotations

import json
import os
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

    def test_both_workers_require_gate_before_native_vcpkg_build(self):
        ci = yaml.safe_load(
            (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"))
        for matrix in ("build", "build-extra"):
            with self.subTest(matrix=matrix):
                steps = ci["jobs"][matrix]["steps"]
                gate = next(i for i, step in enumerate(steps)
                            if step.get("name") == "Require exact third-party binary cache coverage")
                build = next(i for i, step in enumerate(steps)
                             if step.get("name") == "Build and test via native vcpkg")
                self.assertEqual(build - 1, gate)
                self.assertIn("ffbuild.ci verify-cache", steps[gate]["run"])
                self.assertIn("VCPKG_ROOT", steps[gate]["env"])
                self.assertIn("--cache-dir=", steps[gate]["run"])
                self.assertIn("ffvcpkg install", steps[build]["run"])
                self.assertEqual("Verify no external dependencies were compiled by Worker",
                                 steps[build + 1]["name"])
                self.assertIn("ffbuild.ci audit-worker", steps[build + 1]["run"])


if __name__ == "__main__":
    unittest.main()
