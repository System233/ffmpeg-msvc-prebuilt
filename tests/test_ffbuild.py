"""ffbuild plan/build/CLI compatibility tests (offline, no GitHub writes)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ffbuild.events import event_options
from ffbuild.dependencies import overlay_port_names
from ffbuild.publication import publish
from ffbuild.planner import impacted_versions, write_github_output
from ffbuild.targets import Target
from ffbuild.versions import ROOT, dependency_names, spec_files


from native_fixture import plan_fixture as plan, scan_fixture, install_abi, release_record
from ffbuild.state import PublishedState
from ffbuild.catalog import register_release


class EmptyState:
    def find_abi(self, *args, **kwargs):
        return None


LGPL_STATIC = (Target("ffmpeg[all-lgpl,static]", "x64-windows", ("all-lgpl", "static")),)


class PlannerTests(unittest.TestCase):
    def test_custom_vcpkg_targets_are_not_collapsed_by_license(self):
        from ffbuild.cli import main
        from ffbuild.native_abi import build_requests
        from ffbuild.identity import variant_name

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            targets = (Target("ffmpeg[all-lgpl,static]", "x64-windows", ("all-lgpl", "static")),
                       Target("ffmpeg[base,static]", "x64-windows", ("base", "static")))
            requests, blocked = build_requests(version="8.1.3", targets=targets)
            self.assertEqual([], blocked)
            for number, request in enumerate(requests):
                request["abi_hash"] = str(number + 1) * 64
                request["id"] = variant_name(request["version"], 0,
                                             request["triplet"], request["linkage"],
                                             request["license"], abi_hash=request["abi_hash"])
            abi_file = root / "scan.json"
            abi_file.write_text(json.dumps({"schema": 3, "jobs": requests}), encoding="utf-8")
            output = root / "plan.json"
            main(["plan", "--abi-file", str(abi_file),
                  "--state-dir", str(root / "data"), "--output", str(output)])
            jobs = json.loads(output.read_text(encoding="utf-8"))["jobs"]
            self.assertEqual(2, len(jobs))
            self.assertEqual({("lgpl", "static")},
                             {(j["license"], j["linkage"]) for j in jobs})
            self.assertEqual(2, len({j["abi_hash"] for j in jobs}))
            self.assertEqual(2, len({j["id"] for j in jobs}))

    def test_native_identity_kept(self):
        job = plan(version="8.1.3", targets=LGPL_STATIC, state=EmptyState())["jobs"][0]
        self.assertNotIn("revision", job)
        self.assertEqual(f"ffmpeg-8.1.3_x64-windows-static-lgpl-a{job['abi_hash'][:12]}", job["id"])
        self.assertEqual("ffmpeg[all-lgpl,static]", job["package"])
        self.assertIn("static", job["features"])

    def test_existing_variant_is_skipped_unless_forced(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)
            job = scan_fixture(version="8.1.3", targets=LGPL_STATIC)["jobs"][0]
            register_release(db, [release_record(job)])
            opts = dict(version="8.1.3", targets=LGPL_STATIC, state=PublishedState(directory=db))
            self.assertEqual([], plan(**opts)["jobs"])
            self.assertEqual(1, len(plan(force=True, **opts)["jobs"]))

    def test_full_matrix_is_16_distinct_variants(self):
        result = plan(version="8.1.3", state=EmptyState())
        self.assertEqual(16, len(result["jobs"]))
        self.assertEqual(16, len({job["id"] for job in result["jobs"]}))
        self.assertTrue(all(job["package"].startswith("ffmpeg[") for job in result["jobs"]))

    def test_changed_lame_port_impacts_all_consumer_versions(self):
        candidates = ["3.4.14", "8.1.3", "9.1"]
        self.assertEqual(
            candidates,
            impacted_versions({"ports/mp3lame/disable-mpglib.patch"}, candidates),
        )

    def test_unrelated_ports_and_patches_not_selected(self):
        candidates = ["3.4.14", "8.1.3", "9.1"]
        self.assertEqual(
            [], impacted_versions({"ports/unrelated/portfile.cmake"}, candidates),
        )
        self.assertEqual(
            ["8.1.3"],
            impacted_versions({"patches/8.x/0004-dependencies-8.1.patch"}, candidates),
        )

    def test_config_parent_changes_are_detected(self):
        self.assertIn("ffmpeg/8.1.yaml", spec_files("8.1.3"))
        self.assertIn("ffmpeg/base.yaml", spec_files("8.1.3"))
        self.assertEqual(
            ["8.1.3"], impacted_versions({"ffmpeg/8.1.yaml"}, ["3.4.14", "8.1.3"]),
        )

    def test_lame_is_reachable_for_lgpl_build(self):
        dependencies = dependency_names("8.1.3", "lgpl")
        self.assertIn("mp3lame", dependencies)
        self.assertIn("mp3lame", overlay_port_names(dependencies))

    def test_master_pr_resolves_snapshot(self):
        snapshot = {"ref": "n9.1-12-gabcdef0", "sha512": "a"*128, "commit": "a"*40}
        result = plan(version="master", snapshot=snapshot, state=EmptyState(),
                      targets=LGPL_STATIC, force=True)
        self.assertEqual(1, len(result["jobs"]))
        self.assertEqual(snapshot["ref"], result["jobs"][0]["ref"])

    def test_github_output_is_single_line_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "output"
            result = plan(
                version="8.1.3", targets=LGPL_STATIC, state=EmptyState(),
            )
            write_github_output(result, dest)
            lines = dest.read_text(encoding="utf-8").splitlines()
            self.assertEqual(4, len(lines))
            self.assertEqual("publication_required=true", lines[3])
            self.assertEqual(result["jobs"], json.loads(lines[0][len("matrix="):]))
            self.assertEqual("triplets=[\"x64-windows\"]", lines[1])
            self.assertFalse(any(line.startswith("auto_heal_") for line in lines))


class EventTests(unittest.TestCase):
    def test_explicit_force_overrides_event_defaults(self):
        from ffbuild.cli import main

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            event = root / "event.json"
            event.write_text(json.dumps({"inputs": {"version": "8.1.3"}}), encoding="utf-8")
            scan_file = root / "scan.json"
            scan_file.write_text('{"schema":3,"jobs":[]}', encoding="utf-8")
            data = {"jobs": [], "matrix": [], "blocked": [], "versions": []}
            with mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "workflow_dispatch",
                                           "GITHUB_EVENT_PATH": str(event)}):
                with mock.patch("ffbuild.planner.plan_native", return_value=data) as planned:
                    main(["plan", "--event", "--force", "--abi-file", str(scan_file),
                          "--output", str(root / "plan.json")])
            self.assertTrue(planned.call_args.kwargs["force"])
            self.assertEqual(3, planned.call_args.args[0]["schema"])

    def test_pr_is_changed_and_forced(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(
                json.dumps({"pull_request": {
                    "base": {"sha": "abc"}, "head": {"sha": "def"},
                }}),
                encoding="utf-8",
            )
            options = event_options({
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
            })
        self.assertEqual("changed", options["mode"])
        self.assertEqual(("abc", "def"), (options["base"], options["head"]))
        self.assertTrue(options["force"])
        self.assertTrue(options["include_master"])

    def test_manual_target_is_not_diff_limited(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"inputs": {"version": "8.1.3"}}), encoding="utf-8")
            options = event_options({
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_EVENT_PATH": str(event),
            })
        self.assertEqual("all", options["mode"])
        self.assertEqual("8.1.3", options["version"])


class UpdateTests(unittest.TestCase):
    def test_missing_upstream_tag_refuses_version_creation(self):
        from ffbuild import updates

        with mock.patch.dict(os.environ, {"GH_TOKEN": "mock-token"}):
            with mock.patch.object(updates.subprocess, "run") as execute:
                execute.side_effect = [
                    mock.Mock(returncode=0),  # gh auth setup-git
                    mock.Mock(returncode=0, stdout="main\n"),  # current branch
                    mock.Mock(returncode=2, stdout=""),  # absent upstream tag
                ]
                with self.assertRaisesRegex(ValueError, "Upstream FFmpeg tag"):
                    updates.apply_versions(["999.999"])
                self.assertEqual(3, execute.call_count)


class PublishCompatibilityTests(unittest.TestCase):
    def test_dry_run_does_not_write_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifacts"
            artifact.mkdir()
            name = "ffmpeg-8.1.3_x64-windows-static-lgpl"
            (artifact / f"{name}.zip").write_bytes(b"zip placeholder")
            (artifact / f"{name}.var.yaml").write_text(
                yaml.safe_dump({
                    "variant_id": name, "version": "8.1.3", "revision": 0,
                    "assets": {"binary": {"file": f"{name}.zip"}},
                }), encoding="utf-8",
            )
            planfile = root / "plan.json"
            planfile.write_text(json.dumps({"jobs": [{"id": name}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Native dated release metadata"):
                publish(artifacts_dir=artifact, data_dir=root / "unused-data",
                        expected_plan=planfile, dry_run=True)
            self.assertFalse((root / "unused-data").exists())

    def test_missing_planned_artifact_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifacts"
            artifact.mkdir()
            planfile = root / "plan.json"
            planfile.write_text(
                json.dumps({"jobs": [{"id": "missing"}]}), encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "Missing all planned"):
                publish(
                    artifacts_dir=artifact, data_dir=root / "unused",
                    expected_plan=planfile, dry_run=True,
                )

    def test_legacy_publication_cannot_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "legacy.var.yaml").write_text(yaml.safe_dump({
                "variant_id": "ffmpeg-8.1.3_x64-windows-static-lgpl", "version": "8.1.3",
                "revision": 0}), encoding="utf-8")
            with mock.patch("ffbuild.publication._release_assets") as upload:
                with self.assertRaisesRegex(ValueError, "Native dated release metadata"):
                    publish(artifacts_dir=root, data_dir=root / "data")
                upload.assert_not_called()
            self.assertFalse((root / "data").exists())


class WorkflowTests(unittest.TestCase):
    def test_reusable_build_restores_shared_dependency_prebuild(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        self.assertIn("workflow_call", workflow["on"])
        self.assertEqual(
            {"select", "plan", "download", "prepare", "build", "publish"},
            set(workflow["jobs"]),
        )
        self.assertTrue(any("python -m ffbuild.ci plan" in step.get("run", "")
                            for step in workflow["jobs"]["plan"]["steps"]))
        self.assertTrue(any("ffbuild.ci prepare-cache" in step.get("run", "")
                            for step in workflow["jobs"]["prepare"]["steps"]))
        self.assertTrue(any("ffbuild.ci download" in step.get("run", "")
                            for step in workflow["jobs"]["download"]["steps"]))
        self.assertEqual(["plan", "prepare"], workflow["jobs"]["build"]["needs"])
        build_steps = workflow["jobs"]["build"]["steps"]
        self.assertTrue(any("ffbuild.ci worker-build" in x.get("run", "") for x in build_steps))
        self.assertTrue(any("ffbuild.ci worker-package" in x.get("run", "") for x in build_steps))

    def test_main_build_owns_pr_trigger(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/build-all.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        self.assertIn("pull_request", workflow["on"])
        self.assertFalse((ROOT / ".github/workflows/pr-build.yml").exists())


class PackageCliTests(unittest.TestCase):
    def test_package_cli_accepts_matrix_job_from_environment(self):
        from ffbuild.cli import main

        job = plan(
            version="8.1.3", targets=LGPL_STATIC, state=EmptyState(),
        )["jobs"][0]
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.dict(os.environ, {"FFBUILD_JOB": json.dumps(job)}):
                with mock.patch("ffbuild.package.package_job", return_value=Path(temp) / "record.yaml") as run:
                    main(["package", "--job-env", "FFBUILD_JOB", "--port-dir", temp])
        self.assertEqual(job, run.call_args.args[1])

    def test_public_cli_has_no_build_or_license_variants(self):
        from ffbuild.cli import build_parser

        commands = next(action for action in build_parser()._actions if action.dest == "command")
        self.assertEqual({"scan", "generate", "prepare", "plan", "package", "publish", "validate", "autoheal", "recover-index", "refresh-lts"},
                         set(commands.choices))
        plan_options = commands.choices["plan"].format_help()
        self.assertNotIn("--licenses", plan_options)
        self.assertNotIn("--linkages", plan_options)

    def test_package_cli_rejects_unplanned_feature_changes(self):
        from ffbuild.package import package_job

        job = plan(version="8.1.3", targets=LGPL_STATIC, state=EmptyState())["jobs"][0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "CONTROL").write_text(
                "Package: ffmpeg\nVersion: 8.1.3\nPort-Version: 0\n\n" +
                "\n\n".join(f"Feature: {name}" for name in job["features"] + ["unplanned"]),
                encoding="utf-8")
            (root / "BUILD_INFO").write_text("LibraryLinkage: static\n", encoding="utf-8")
            install_abi(root, job)
            with self.assertRaisesRegex(ValueError, "Feature closure differs"):
                package_job(root, job, root)


if __name__ == "__main__":
    unittest.main()
