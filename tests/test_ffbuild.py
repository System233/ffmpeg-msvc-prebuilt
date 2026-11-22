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
from ffbuild.fingerprint import overlay_port_names
from ffbuild.legacy_release import publish
from ffbuild.planner import impacted_versions, plan, write_github_output
from ffbuild.versions import ROOT, dependency_names, revision, spec_files


class EmptyState:
    def variant_exists(self, *args):
        return False


class FullState:
    def variant_exists(self, *args):
        return True


class PlannerTests(unittest.TestCase):
    def test_existing_revision_kept(self):
        result = plan(
            version="8.1.3", triplets=("x64-windows",),
            licenses=("lgpl",), linkages=("static",),
            state=EmptyState(),
        )
        self.assertEqual(1, len(result["jobs"]))
        job = result["jobs"][0]
        self.assertEqual(revision("8.1.3"), job["revision"])
        self.assertEqual("ffmpeg-8.1.3_x64-windows-static-lgpl", job["id"])
        self.assertEqual([{"license": "lgpl", "linkage": "static"}], job["targets"])

    def test_existing_variant_is_skipped_unless_forced(self):
        opts = dict(
            version="8.1.3", triplets=("x64-windows",),
            licenses=("lgpl",), linkages=("static",), state=FullState(),
        )
        self.assertEqual([], plan(**opts)["jobs"])
        self.assertEqual(1, len(plan(force=True, **opts)["jobs"]))

    def test_full_matrix_is_16_distinct_variants(self):
        result = plan(version="8.1.3", state=EmptyState())
        self.assertEqual(16, len(result["jobs"]))
        self.assertEqual(16, len({job["id"] for job in result["jobs"]}))
        self.assertTrue(all(len(job["targets"]) == 1 for job in result["jobs"]))

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
        with mock.patch("ffbuild.planner.changed_paths", return_value={"ffmpeg/master.yaml"}):
            with mock.patch(
                "ffbuild.master.master_metadata",
                return_value={"ref": "n9.1-12-gabcdef0", "sha512": "a" * 128},
            ):
                result = plan(
                    mode="changed", base="HEAD~1", head="HEAD",
                    include_master=True, state=EmptyState(),
                    triplets=("x64-windows",), licenses=("lgpl",),
                    linkages=("static",), force=True,
                )
        matches = [x for x in result["jobs"] if x["yaml"] == "master"]
        self.assertEqual(1, len(matches))
        self.assertEqual("n9.1-12-gabcdef0", matches[0]["ref"])

    def test_github_output_is_single_line_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "output"
            result = plan(
                version="8.1.3", triplets=("x64-windows",),
                licenses=("lgpl",), linkages=("static",), state=EmptyState(),
            )
            write_github_output(result, dest)
            lines = dest.read_text(encoding="utf-8").splitlines()
            self.assertEqual(5, len(lines))
            self.assertEqual(result["jobs"], json.loads(lines[0][len("matrix="):]))
            self.assertEqual("triplets=[\"x64-windows\"]", lines[1])
            self.assertEqual("auto_heal_yaml=8.1.3", lines[3])


class EventTests(unittest.TestCase):
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
                with mock.patch.object(updates.create_version_pr, "main") as create:
                    execute.side_effect = [
                        mock.Mock(returncode=0),  # gh auth setup-git
                        mock.Mock(returncode=2, stdout=""),  # absent upstream tag
                    ]
                    with self.assertRaisesRegex(ValueError, "Upstream FFmpeg tag"):
                        updates.apply_versions(["999.999"])
                    create.assert_not_called()


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
            result = publish(
                artifacts_dir=artifact,
                data_dir=root / "unused-data",
                expected_plan=planfile,
                dry_run=True,
            )
        self.assertEqual(["ffmpeg-8.1.3"], result)

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

    def test_multiple_versions_keep_release_assets_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            checkout = root / "data"
            (checkout / ".git").mkdir(parents=True)
            for version in ("8.1.3", "9.1"):
                variant = f"ffmpeg-{version}_x64-windows-static-lgpl"
                (artifacts / f"{variant}.zip").write_bytes(version.encode())
                (artifacts / f"{variant}.var.yaml").write_text(
                    yaml.safe_dump({
                        "variant_id": variant, "version": version, "revision": 0,
                        "assets": {"binary": {"file": f"{variant}.zip"}},
                    }), encoding="utf-8",
                )
            uploaded: dict[str, list[str]] = {}

            def capture(*, tag, artifacts_dir, **kwargs):
                uploaded[tag] = sorted(p.name for p in artifacts_dir.glob("*.zip"))

            db, manager, pusher = mock.Mock(), mock.Mock(), mock.Mock()
            manager.create_or_upload.side_effect = capture
            pusher.has_staged_changes.return_value = False
            with mock.patch.dict(os.environ, {"GH_TOKEN": "mock-token"}):
                with mock.patch("ffbuild.legacy_release._legacy_modules",
                                return_value=(db, manager, pusher)):
                    publish(artifacts_dir=artifacts, data_dir=checkout)
            self.assertEqual(
                ["ffmpeg-8.1.3_x64-windows-static-lgpl.zip"],
                uploaded["ffmpeg-8.1.3"],
            )
            self.assertEqual(
                ["ffmpeg-9.1_x64-windows-static-lgpl.zip"],
                uploaded["ffmpeg-9.1"],
            )


class WorkflowTests(unittest.TestCase):
    def test_reusable_build_is_only_one_build_plan(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        self.assertIn("workflow_call", workflow["on"])
        self.assertEqual(
            {"plan", "prepare", "build", "publish", "trigger-auto-heal"},
            set(workflow["jobs"]),
        )
        self.assertIn("ffbuild plan", workflow["jobs"]["plan"]["steps"][2]["run"])
        build_steps = workflow["jobs"]["build"]["steps"]
        self.assertTrue(any("ffbuild build" in x.get("run", "") for x in build_steps))

    def test_main_build_owns_pr_trigger(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/build-all.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        self.assertIn("pull_request", workflow["on"])
        self.assertFalse((ROOT / ".github/workflows/pr-build.yml").exists())


class BuilderTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "MSVC build command test needs Windows")
    def test_build_uses_vcpkg_with_the_selected_linkage(self):
        from ffbuild import builder

        jobs = plan(
            version="8.1.3", triplets=("x64-windows",),
            licenses=("lgpl",), linkages=("static",), state=EmptyState(),
        )["jobs"]
        job = jobs[0]
        scripts = str(ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vcpkg_root = root / "vcpkg"
            vcpkg_root.mkdir()
            (vcpkg_root / "vcpkg.exe").write_bytes(b"stub")
            output = root / "release"

            def fake_package(argv):
                metadata = output / f"{job['id']}.var.yaml"
                metadata.write_text(
                    yaml.safe_dump({"variant_id": job["id"]}), encoding="utf-8",
                )

            with mock.patch.object(builder, "generate") as gen:
                with mock.patch.object(builder, "_run") as execute:
                    with mock.patch("scripts.package_release.main", side_effect=fake_package):
                        result = builder.build_job(
                            job, vcpkg_root=vcpkg_root,
                            cache_dir=root / "binary-cache",
                            output_dir=output, bootstrap_tool=False,
                        )
            self.assertEqual(1, len(result))
            gen.assert_called_once()
            args = execute.call_args.args[0]
            self.assertIn("ffmpeg[all-lgpl,static]", args)
            self.assertIn("ffmpeg-tester", args)
            self.assertIn("--triplet=x64-windows", args)
            env = execute.call_args.kwargs["env"]
            self.assertIn("readwrite", env["VCPKG_BINARY_SOURCES"])

    def test_build_cli_accepts_matrix_job_from_environment(self):
        from ffbuild.cli import main

        job = plan(
            version="8.1.3", triplets=("x64-windows",),
            licenses=("lgpl",), linkages=("static",), state=EmptyState(),
        )["jobs"][0]
        with mock.patch.dict(os.environ, {"FFBUILD_JOB": json.dumps(job)}):
            with mock.patch("ffbuild.builder.build_job", return_value=[]) as run:
                main(["build", "--job-env", "FFBUILD_JOB"])
        self.assertEqual(job, run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
