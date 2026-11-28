"""Historical vcpkg ABI and selective validation regression contracts."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
import ffvcpkg
from ffbuild import release_trigger
from ffbuild.native_abi import collect_abi_evidence, compare_abi_evidence
from ffbuild.seed import seed_hash, require_seed_archives
from ffbuild.versions import ROOT


class NativeToolPolicy(unittest.TestCase):
    def test_environment_rejects_incompatible_downloaded_tools(self):
        original = {"VCPKG_FORCE_DOWNLOADED_BINARIES": "0", "VCPKG_BINARY_SOURCES": "clear",
                    "PYTHONIOENCODING": "cp1252"}
        with self.assertRaisesRegex(ValueError,"VCPKG_FORCE_DOWNLOADED_BINARIES"):
            ffvcpkg.environment(original)
        result = ffvcpkg.environment(dict(original,VCPKG_FORCE_DOWNLOADED_BINARIES="1"))
        self.assertEqual("1", result["VCPKG_FORCE_DOWNLOADED_BINARIES"])
        self.assertEqual("utf-8", result["PYTHONIOENCODING"])
        self.assertEqual("clear", result["VCPKG_BINARY_SOURCES"])
        self.assertEqual("0", original["VCPKG_FORCE_DOWNLOADED_BINARIES"])

    def test_all_install_modes_use_exact_versions_once(self):
        for options in ([], ["--dry-run"], ["--only-downloads"], ["--only-binarycaching"],
                        ["--dry-run", ffvcpkg.EXACT_ABI_TOOLS]):
            with self.subTest(options=options):
                command = ffvcpkg.command(["install", "zlib", *options], binary=Path("vcpkg.exe"))
                self.assertEqual(1, command.count(ffvcpkg.EXACT_ABI_TOOLS))
                self.assertTrue(all(option in command for option in options))
        self.assertEqual(["vcpkg.exe", "version"], ffvcpkg.command(["version"], binary=Path("vcpkg.exe")))

    def test_explicit_subprocess_environment_is_command_authority(self):
        with patch.dict(os.environ,{"VCPKG_INSTALL_OPTIONS":ffvcpkg.EXACT_ABI_TOOLS}):
            env={"VCPKG_INSTALL_OPTIONS":ffvcpkg.EXACT_ABI_TOOLS+" --no-print-usage"}
            command=ffvcpkg.command(["install","zlib"],binary=Path("vcpkg.exe"),env=env)
            self.assertIn("--no-print-usage",command)
            with self.assertRaisesRegex(ValueError,"VCPKG_INSTALL_OPTIONS"):
                ffvcpkg.command(["install","zlib"],binary=Path("vcpkg.exe"),env={"VCPKG_INSTALL_OPTIONS":"--dry-run"})

    def test_missing_exact_tool_policy_is_not_silently_appended(self):
        with patch.dict(os.environ,{"VCPKG_INSTALL_OPTIONS":"--dry-run"}):
            with self.assertRaisesRegex(ValueError,"VCPKG_INSTALL_OPTIONS"):
                ffvcpkg.command(["install","zlib",ffvcpkg.EXACT_ABI_TOOLS],binary=Path("vcpkg.exe"))

    def test_cli_native_environment(self):
        with patch("ffvcpkg.executable", return_value=Path("vcpkg.exe")), \
                patch("ffvcpkg.subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertEqual(0, ffvcpkg.main(["install", "zlib", "--dry-run"]))
            self.assertIn(ffvcpkg.EXACT_ABI_TOOLS, run.call_args.args[0])
            self.assertEqual("1", run.call_args.kwargs["env"]["VCPKG_FORCE_DOWNLOADED_BINARIES"])

    def test_seed_archive_gate_uses_only_external_abis(self):
        batch = {"abis":{"zlib_x64-windows":"b"*64},
                 "specs":{"zlib_x64-windows":"zlib[core]:x64-windows"}}
        plan = {"batches":[batch]}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "Seed cache incomplete"):
                require_seed_archives(plan, cache)
            abi = "b"*64
            folder = cache / abi[:2]; folder.mkdir()
            archive=folder / (abi + ".zip")
            archive.touch()
            with self.assertRaisesRegex(RuntimeError, "Seed cache incomplete"):
                require_seed_archives(plan, cache)
            archive.write_bytes(b"fixture")
            require_seed_archives(plan, cache)

    def test_actual_input_files_must_match_graph_and_show_component_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            buildtrees = root / "buildtrees"
            p = buildtrees / "zlib" / "x64-windows.vcpkg_abi_info.txt"
            p.parent.mkdir(parents=True)
            old = b"cmake 4.3.2\npowershell 7.6.1\ntriplet_abi abc\n"
            new = b"cmake 4.3.2\npowershell 7.7.0\ntriplet_abi abc\n"
            for data, name in ((old, "before"), (new, "after")):
                p.write_bytes(data)
                collect_abi_evidence({"zlib_x64-windows": hashlib.sha256(data).hexdigest()},
                                     buildtrees, root / name)
            report = compare_abi_evidence(root / "before", root / "after")
            self.assertEqual({"powershell": {"before": ["7.6.1"], "after": ["7.7.0"]}},
                             report["changed"]["zlib_x64-windows"]["entries"])
            with self.assertRaisesRegex(RuntimeError, "differs"):
                collect_abi_evidence({"zlib_x64-windows": hashlib.sha256(old).hexdigest()},
                                     buildtrees, root / "invalid")
            (root / "after/zlib_x64-windows.txt").write_bytes(old)
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                compare_abi_evidence(root / "before", root / "after")

    def test_workflow_seed_exact_key_and_gate(self):
        jobs = yaml.safe_load((ROOT / ".github/workflows/build-release.yml").read_text())["jobs"]
        prepare = jobs["prepare"]["steps"]
        saved = next(s for s in prepare if s.get("uses","").startswith("actions/cache/save@"))
        restored = next(s for s in jobs["build"]["steps"] if s.get("name")=="Restore centrally prebuilt dependencies")
        self.assertIn("steps.prepare-cache.outputs.save_key", saved["with"]["key"])
        self.assertIn("matrix.seed_key", restored["with"]["key"])
        self.assertEqual(2,len(restored["with"]["restore-keys"].splitlines()))
        self.assertTrue(all("matrix.seed_key" in key for key in restored["with"]["restore-keys"].splitlines()))
        self.assertTrue(restored["with"]["fail-on-cache-miss"])
        gate = next(i for i,s in enumerate(prepare) if "prepare-cache" in s.get("run",""))
        self.assertLess(gate,prepare.index(saved))
        self.assertIn("!inputs.dry_run", jobs["publish"]["if"])


class VcpkgVersionDeclaration(unittest.TestCase):
    def test_workflows_declare_and_forward_same_vcpkg_tag(self):
        from ffbuild.targets import workflow_defaults
        tag=workflow_defaults()["VCPKG_TAG"]
        self.assertRegex(tag,r"^\d{4}\.\d{2}\.\d{2}$")
        for p in list((ROOT/".github/workflows").glob("*.yml"))+list((ROOT/".github/actions").glob("*/action.yml")):
            self.assertNotIn(tag,p.read_text(encoding="utf-8"),p.name)
        action=yaml.safe_load((ROOT/".github/actions/setup-vcpkg/action.yml").read_text(encoding="utf-8"))
        bootstrap=next(s for s in action["runs"]["steps"] if s.get("uses")=="./.github/actions/vcpkg-bootstrap")
        self.assertEqual("${{ steps.config.outputs.vcpkg_tag }}",bootstrap["with"]["tag"])
        self.assertEqual("${{ steps.config.outputs.vcpkg_root }}",bootstrap["with"]["vcpkg-root"])
        for name in ("builder.py","ci.py"):
            self.assertNotIn(tag,(ROOT/"scripts/ffbuild"/name).read_text(encoding="utf-8"))

    def test_python_bootstrap_never_guesses_a_tag(self):
        from ffbuild.builder import bootstrap
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "vcpkg"
            with patch.dict(os.environ, {}, clear=True), patch("ffbuild.builder.subprocess.run") as run:
                with self.assertRaisesRegex(ValueError, "VCPKG_TAG"):
                    bootstrap(root)
                run.assert_not_called()
            for env, explicit, expected in (
                ({"VCPKG_TAG": "2031.02.03"}, None, "2031.02.03"),
                ({"VCPKG_TAG": "2031.02.03"}, "2032.04.05", "2032.04.05"),
            ):
                with self.subTest(env=env, explicit=explicit), patch.dict(os.environ, env, clear=True), \
                        patch("ffbuild.builder.subprocess.run", side_effect=RuntimeError("clone probe")) as run:
                    with self.assertRaisesRegex(RuntimeError, "clone probe"):
                        bootstrap(root, tag=explicit)
                    args = run.call_args.args[0]
                    self.assertEqual(expected, args[args.index("--branch") + 1])
            root.mkdir()
            executable = root / ("vcpkg.exe" if os.name == "nt" else "vcpkg")
            executable.touch()
            with patch.dict(os.environ, {}, clear=True), patch("ffbuild.builder.subprocess.run") as run:
                self.assertEqual(executable, bootstrap(root))
                run.assert_not_called()


class DynamicCIConfiguration(unittest.TestCase):
    def test_axes_expand_and_change_every_consumer(self):
        from ffbuild.native_abi import build_requests
        from ffbuild.targets import load_targets, configured_triplets, select_targets, require_complete_targets
        from ffbuild.release_trigger import complete_pr_build
        from ffbuild import ci
        for env, count in (
            ({"TRIPLETS":"x64-windows","LICENSES":"lgpl","LINKAGES":"shared"}, 1),
            ({"TRIPLETS":"x86-windows arm64-windows","LICENSES":"gpl lgpl","LINKAGES":"static"}, 4),
            ({"TRIPLETS":"x64-windows arm-windows","LICENSES":"gpl","LINKAGES":"static shared"}, 4),
        ):
            with self.subTest(env=env), patch.dict(os.environ,env), tempfile.TemporaryDirectory() as directory:
                targets=load_targets()
                self.assertEqual(count,len(targets))
                self.assertEqual(tuple(env["TRIPLETS"].split()),configured_triplets())
                rows,blocked=build_requests(version="8.1.3")
                self.assertFalse(blocked)
                self.assertEqual(count,len(rows))
                self.assertTrue(all(row["expected_variants"]==count for row in rows))
                require_complete_targets(rows,version="8.1.3",targets=targets)
                for i,row in enumerate(rows):
                    row["id"]=str(i)
                jobs=[{"name":"build / ffbuild-"+row["id"],"conclusion":"success"} for row in rows]
                self.assertTrue(complete_pr_build("8.1.3",rows,jobs))
                self.assertFalse(complete_pr_build("8.1.3",rows[:-1],jobs))
                with self.assertRaisesRegex(ValueError,"Incomplete CI target matrix"):
                    require_complete_targets([rows[0]]*count if count>1 else [],version="8.1.3",targets=targets)
                path=Path(directory)/"plan.json"
                path.write_text(json.dumps({"jobs":rows}))
                require_complete_targets(json.loads(path.read_text())["jobs"],version="8.1.3",targets=targets)
                self.assertEqual({targets[0].triplet}, {t.triplet for t in select_targets(arch=targets[0].triplet)})
                with patch("ffbuild.ci.patch_arm_sdk") as arm:
                    ci.main(["prepare-host","--configured"])
                    self.assertEqual("arm-windows" in configured_triplets(),arm.called)

    def test_invalid_axes_fail_closed(self):
        from ffbuild.targets import load_targets
        for change in ({"TRIPLETS":""},{"TRIPLETS":"x64-windows x64-windows"},
                       {"TRIPLETS":"x64-linux"},{"LICENSES":"nonfree"},{"LINKAGES":"wrong"}):
            with self.subTest(change=change),patch.dict(os.environ,change),self.assertRaises(ValueError):
                load_targets()

    def test_config_exports_current_cache_paths_and_options(self):
        from ffbuild import ci
        from ffbuild.targets import workflow_defaults
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/"env"
            temp=r"D:\\a\\_temp"
            with patch.dict(os.environ,{"RUNNER_TEMP":temp,"GITHUB_ENV":str(output),"GITHUB_OUTPUT":str(output.with_suffix(".outputs")),"VCPKG_TAG":"2031.02.03",
                                       "TRIPLETS":"x64-windows","VCPKG_INSTALL_OPTIONS":"--x-abi-tools-use-exact-versions --clean-after-build"}):
                ci.main(["configure"])
                args=ffvcpkg.command(["install","zlib","--dry-run"],binary=Path("vcpkg.exe"))
                self.assertIn("--clean-after-build",args)
                self.assertEqual(1,args.count(ffvcpkg.EXACT_ABI_TOOLS))
            env=dict(line.split("=",1) for line in output.read_text().splitlines())
            self.assertEqual(set(workflow_defaults()) | {"VCPKG_ROOT","FFBUILD_CACHE_DIR","FFBUILD_DOWNLOADS_DIR",
                "FFBUILD_REPAIR_DIR","FFBUILD_REPAIR_CACHE"},set(env))
            self.assertEqual(temp+"/ffbuild/vcpkg-cache",env["FFBUILD_CACHE_DIR"])
            self.assertEqual(temp+"/ffbuild/vcpkg/downloads",env["FFBUILD_DOWNLOADS_DIR"])
            self.assertEqual("2031.02.03",env["VCPKG_TAG"])
            emitted=dict(line.split("=",1) for line in output.with_suffix(".outputs").read_text().splitlines())
            self.assertEqual(env["VCPKG_TAG"],emitted["vcpkg_tag"])
            self.assertEqual(env["VCPKG_ROOT"],emitted["vcpkg_root"])
            self.assertEqual(env["FFBUILD_CACHE_DIR"],emitted["cache_dir"])
            self.assertNotIn("triplets",emitted)
            with patch.dict(os.environ,env):
                request=ci.cache_request("seed",tag=env["VCPKG_TAG"],triplet="x64-windows",abi="a"*64)
                prefix="ffbuild-seed-2031.02.03-x64-windows-"
                self.assertEqual({"key":prefix+"a"*64,"prefix":prefix},request)
                source=ci.cache_request("downloads",tag=env["VCPKG_TAG"],download_specs="b"*64,recipe_hash="c"*64)
                prefix="ffbuild-downloads-2031.02.03-"
                self.assertEqual({"key":prefix+"b"*64+"-"+"c"*64,"prefix":prefix},source)
                with self.assertRaisesRegex(ValueError,"Invalid source download cache identity"):
                    ci.cache_request("downloads",tag=env["VCPKG_TAG"],recipe_hash="c"*64)


    def test_force_plan_does_not_touch_publication_state(self):
        from ffbuild.native_abi import build_requests
        from ffbuild.planner import plan_native
        from unittest.mock import Mock
        with patch.dict(os.environ,{"TRIPLETS":"x64-windows","LICENSES":"lgpl","LINKAGES":"shared"}):
            rows,_=build_requests(version="8.1.3")
            rows[0].update(id="one",abi_hash="a"*64)
            state=Mock()
            state.find_abi.side_effect=AssertionError("No catalog read during force")
            state.latest_release.side_effect=AssertionError("No catalog read during force")
            plan=plan_native({"schema":3,"jobs":rows},state=state,force=True)
            self.assertEqual(rows,plan["jobs"])
            state.find_abi.assert_not_called()
            state.latest_release.assert_not_called()

    def test_master_requires_actual_pin_and_arm_sdk_uses_declaration(self):
        from ffbuild.versions import feature_version
        self.assertEqual("12.3",feature_version("master","n12.3-dev-123-gabcdef0"))
        with self.assertRaisesRegex(ValueError,"pinned source"):
            feature_version("master")
        from ffbuild.builder import patch_arm_sdk
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            file=root/"VC/Auxiliary/Build/vcvarsall.bat"
            file.parent.mkdir(parents=True)
            file.write_bytes(b"set __VCVARSALL_WINSDK=\r\n")
            with patch.dict(os.environ,{"ARM_WINDOWS_SDK":"10.0.99999.0"}), \
                    patch("ffbuild.builder.subprocess.run",return_value=Mock(stdout=str(root))):
                patch_arm_sdk()
            self.assertEqual(b"set __VCVARSALL_WINSDK=10.0.99999.0\r\n",file.read_bytes())

    def test_repair_cache_plan_covers_incident_without_architecture_expansion(self):
        from ffbuild import ci
        from ffbuild.targets import configured_triplets
        from ffbuild.native_platform import PE_MACHINE
        triplets=list(configured_triplets())
        action=yaml.safe_load((ROOT/".github/actions/prepare-repair/action.yml").read_text(encoding="utf-8"))
        steps=action["runs"]["steps"]
        slots=[s for s in steps if s.get("name","").startswith("Restore native dependency cache")]
        self.assertEqual(len(PE_MACHINE),len(slots))
        self.assertFalse(any("npm" in s.get("run","") or "setup-node" in s.get("uses","") for s in steps))
        env={"VCPKG_TAG":"2031.02.03","FFBUILD_CACHE_DIR":"cache",
             "FFBUILD_REPAIR_DIR":"repair"}
        with patch.dict(os.environ,env),patch.object(ci,"patch_arm_sdk"),patch.object(ci,"seed_plans") as plan:
            for chosen in (triplets[:1],triplets[1:3],triplets[::-1]):
                plan.return_value=({t:"a"*64 for t in chosen},"b"*64)
                rows=json.loads(ci.repair_cache_plan(chosen)["seeds"])
                self.assertEqual([f"ffbuild-seed-2031.02.03-{t}-"+"a"*64 for t in chosen],[r["key"] for r in rows])
            for invalid in ([],triplets+triplets[:1],["bad-triplet"]):
                with self.assertRaises(ValueError):
                    ci.repair_cache_plan(invalid)
    def test_workflow_configuration_outputs_are_declared_and_initialized(self):
        action=yaml.safe_load((ROOT/".github/actions/setup-vcpkg/action.yml").read_text(encoding="utf-8"))
        declared=set(action["outputs"])
        self.assertEqual({"vcpkg_tag","vcpkg_root","cache_dir","downloads_dir","repair_dir"},declared)
        import re
        for filename in ("build-release.yml","auto-heal.yml","dependency-submission.yml"):
            doc=yaml.safe_load((ROOT/".github/workflows"/filename).read_text(encoding="utf-8"))
            for job in doc["jobs"].values():
                configured=False
                for step in job.get("steps",[]):
                    if step.get("uses")=="./.github/actions/setup-vcpkg":
                        self.assertEqual("config",step["id"])
                        configured=True
                    fields=set(re.findall(r"steps\.config\.outputs\.(\w+)",str(step)))
                    if fields:
                        self.assertTrue(configured, filename)
                        self.assertLessEqual(fields,declared)
        submission=yaml.safe_load((ROOT/".github/workflows/dependency-submission.yml").read_text(encoding="utf-8"))
        self.assertEqual({"submit"},set(submission["jobs"]))
        self.assertNotIn("strategy",submission["jobs"]["submit"])



class ManualValidationScope(unittest.TestCase):
    def test_explicit_validation_only_allows_filters(self):
        sha = "a"*40
        env = {"GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
               "GITHUB_SHA": sha, "TARGET_VERSION": "8.1.3", "VALIDATION_ONLY": "true",
               "SKIP_PUBLISH": "true", "TARGET_ARCH": "arm-windows", "TARGET_LICENSE": "gpl"}
        payload = {"inputs": {"yaml": "8.1.3", "dry_run": "true",
                              "target_arch": "arm-windows", "target_license": "gpl"}}
        with patch.object(release_trigger, "git", return_value=sha), \
                patch.object(release_trigger.subprocess, "run"):
            self.assertEqual("false", release_trigger.build_gate(payload, env)["production"])
            for change in ({"VALIDATION_ONLY": "false"}, {"SKIP_PUBLISH": "false"},
                           {"GITHUB_REF": "refs/heads/topic"}, {"TARGET_ARCH": "x64-windows"},
                           {"TARGET_LICENSE": "nonfree"}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    release_trigger.build_gate(payload, dict(env, **change))
            with self.assertRaises(ValueError):
                release_trigger.build_gate({"inputs": dict(payload["inputs"], dry_run="false")}, env)


if __name__ == "__main__":
    unittest.main()
