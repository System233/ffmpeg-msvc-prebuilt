"""Offline CI reliability contracts; never contacts GitHub or compiles FFmpeg."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from ffbuild import publication
from ffbuild.cli import main
from ffbuild.events import event_options
from ffbuild.planner import write_github_output
from ffbuild.versions import ROOT


class MatrixAndPolicyTests(unittest.TestCase):
    def test_single_version_matrix_is_complete(self):
        jobs = [{"id": f"job-{i}", "yaml": "8.1.3", "triplet": "x64-windows"} for i in range(16)]
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "output"
            write_github_output({"jobs": jobs}, destination)
            lines = dict(line.split("=", 1) for line in destination.read_text(encoding="utf-8").splitlines())
        self.assertEqual(jobs, json.loads(lines["matrix"]))
        self.assertEqual("16", lines["count"])
        self.assertNotIn("matrix_extra", lines)

    def test_oversized_or_multi_version_matrix_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "output"
            for rows in ([{"yaml":"8.1.3","triplet":"x64-windows"}]*17,
                         [{"yaml":v,"triplet":"x64-windows"} for v in ("8.1.3","9.1")]):
                with self.assertRaisesRegex(ValueError, "16 jobs for one FFmpeg version"):
                    write_github_output({"jobs": rows}, dest)
                self.assertFalse(dest.exists())

    def test_modified_old_version_is_scanned_on_main_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "push.json"
            event.write_text(json.dumps({
                "before": "a" * 40, "after": "b" * 40,
            }), encoding="utf-8")
            with mock.patch.dict(os.environ, {
                "GITHUB_EVENT_NAME": "push", "GITHUB_EVENT_PATH": str(event)
            }), mock.patch("ffbuild.planner.changed_paths",
                          return_value={"ffmpeg/8.1.1.yaml"}), \
                 mock.patch("ffbuild.native_abi.build_requests",
                            return_value=([], [])) as request, \
                 mock.patch("ffbuild.native_abi.scan_native_abis",
                            return_value=[]):
                main(["scan", "--event", "--output", str(Path(tmp) / "scan.json")])
        versions = request.call_args.kwargs["selected_versions"]
        self.assertIn("8.1.1", versions)
        self.assertNotIn("8.1.3", versions)

    def test_blocked_targets_fail_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan = root / "scan.json"
            scan.write_text('{"schema":3,"jobs":[]}', encoding="utf-8")
            with mock.patch("ffbuild.planner.plan_native", return_value={
                "jobs": [{"id": "works"}], "matrix": [{"id": "works"}],
                "versions": [], "blocked": [{"yaml": "bad", "errors": ["license"]}]
            }):
                with self.assertRaisesRegex(ValueError, "Unsupported FFmpeg target"):
                    main(["plan", "--abi-file", str(scan),
                          "--output", str(root / "plan.json")])

    def test_manual_force_input_is_available_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "dispatch.json"
            event.write_text('{"inputs":{"version":"8.1.3","force":true}}',
                             encoding="utf-8")
            options = event_options({
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_EVENT_PATH": str(event),
            })
        self.assertTrue(options["force"])
        path = ROOT / ".github/workflows/build-release.yml"
        workflow = yaml.load(path.read_text(encoding="utf-8"),
                             Loader=yaml.BaseLoader)
        self.assertIn("force", workflow["on"]["workflow_call"]["inputs"])
        self.assertIn("!inputs.force", workflow["jobs"]["publish"]["if"])

    def test_only_one_bounded_worker_matrix_required_for_publication(self):
        workflow = yaml.load((ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertNotIn("build-extra", workflow["jobs"])
        self.assertEqual(["select","plan","build"], workflow["jobs"]["publish"]["needs"])
        self.assertIn("needs.build.result == 'success'", workflow["jobs"]["publish"]["if"])
        self.assertEqual("4", workflow["jobs"]["build"]["strategy"]["max-parallel"])
        self.assertIn("ffbuild package", str(workflow["jobs"]["build"]["steps"]))

    def test_failure_evidence_is_ci_only(self):
        workflow = yaml.load((ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"),
                             Loader=yaml.BaseLoader)
        for name in ("build",):
            steps = workflow["jobs"][name]["steps"]
            evidence = next(step for step in steps if step.get("name") == "Upload installed license evidence on packaging failure")
            self.assertIn("failure()", evidence["if"])
            for entry in ("vcpkg/status", "vcpkg/info/*.list", "share/*/copyright", "share/*/vcpkg.spdx.json"):
                self.assertIn(entry, evidence["with"]["path"])
            self.assertNotIn("*.zip", evidence["with"]["path"])
            self.assertTrue(evidence["with"]["name"].startswith("license-evidence-"))

    def test_pr_security_checks_are_fail_closed(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/build-all.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader)
        run = workflow["jobs"]["all-checks-passed"]["steps"][0]["run"]
        self.assertIn('test "$VALIDATE_RESULT" = success', run)
        self.assertIn('test "$BUILD_RESULT" = success', run)
        self.assertIn('if [[ -n "$VERSION" ]]', run)
        self.assertIn('test "$BUILD_RESULT" = skipped', run)


class ReleaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "example/ffmpeg"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @staticmethod
    def _asset(path: Path) -> dict:
        return {"name": path.name, "size": path.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_partial_asset_upload_is_recovered_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.zip"
            b = root / "b.zip"
            a.write_bytes(b"a")
            b.write_bytes(b"b")
            storage: dict[str, dict] = {}
            state = {"created": False, "lost_once": False}
            calls: list[tuple[str, ...]] = []

            def run(*args, **kwargs):
                calls.append(args)
                if args[:3] == ("gh", "release", "create"):
                    state["created"] = True
                elif args[:3] == ("gh", "release", "upload"):
                    file = Path(args[4])
                    if file.name in storage:
                        raise AssertionError("Attempted to overwrite existing Release archive")
                    storage[file.name] = self._asset(file)
                    if not state["lost_once"]:
                        state["lost_once"] = True
                        raise RuntimeError("network response lost after successful upload")
                return SimpleNamespace(returncode=0)

            def read_release(tag):
                return {"id": 42} if state["created"] else None

            with mock.patch.object(publication, "_run", side_effect=run), \
                 mock.patch.object(publication, "_release_api",
                                   side_effect=read_release), \
                 mock.patch.object(publication, "_release_asset_list",
                                   side_effect=lambda _: dict(storage)):
                with self.assertRaisesRegex(RuntimeError, "network response lost"):
                    publication._release_assets("ffmpeg-8.1.3", [a, b],
                                                upstream_version="8.1.3")
                publication._release_assets("ffmpeg-8.1.3", [a, b],
                                            upstream_version="8.1.3")
                publication._release_assets("ffmpeg-8.1.3", [a, b],
                                            upstream_version="8.1.3")
            self.assertEqual({"a.zip", "b.zip"}, set(storage))
            self.assertEqual(1, sum(c[:3] == ("gh", "release", "create")
                                    for c in calls))
            self.assertEqual(2, sum(c[:3] == ("gh", "release", "upload")
                                    for c in calls))

    def test_existing_different_asset_is_never_clobbered(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "a.zip"
            file.write_bytes(b"local")
            with mock.patch.object(publication, "_release_api",
                                   return_value={"id": 42}), \
                 mock.patch.object(publication, "_release_asset_list",
                                   return_value={
                                       "a.zip": {"name": "a.zip", "size": 5,
                                                 "digest": "sha256:" + "0" * 64}
                                   }), mock.patch.object(publication, "_run") as run:
                with self.assertRaisesRegex(ValueError, "content differs"):
                    publication._release_assets("ffmpeg-8.1.3", [file],
                                                upstream_version="8.1.3")
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
