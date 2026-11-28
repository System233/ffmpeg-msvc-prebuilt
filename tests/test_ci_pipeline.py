"""Test the CI execution contract, independent of YAML command plumbing."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from ffbuild import ci
from ffbuild.native_abi import graph_digest


PIN = {"ref": "n9.2-dev-1-gabcdef0", "commit": "a"*40, "sha512": "b"*128}


class ReleasePlan(unittest.TestCase):
    def env(self, root, **updates):
        return dict({
            "TRIPLETS": "x64-windows arm64-windows", "LICENSES": "lgpl gpl",
            "LINKAGES": "shared static", "FFBUILD_VERSION": "8.1.3",
            "FFBUILD_DATE": "2026-11-28", "FFBUILD_PRODUCTION": "false",
            "FFBUILD_FORCE": "true", "FFBUILD_REF": "", "FFBUILD_COMMIT": "",
            "FFBUILD_SHA512": "", "FFBUILD_TARGET_ARCH": "x64-windows",
            "FFBUILD_TARGET_LICENSE": "lgpl", "GITHUB_SHA": "d"*40,
            "GITHUB_RUN_ATTEMPT": "2", "GITHUB_OUTPUT": str(root/"output"),
            "VCPKG_TAG": "2031.02.03", "CACHE_RECIPE": "c"*64,
            "FFBUILD_CACHE_DIR": "cache",
        }, **updates)

    @staticmethod
    def native(requests, **kwargs):
        return [dict(row, abi_hash=hashlib.sha256(row["package"].encode()).hexdigest(),
                     native_graph_sha256="e"*64,id=f"job-{index}") for index,row in enumerate(requests)]

    def test_one_complete_plan_binds_scope_pin_and_cache_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            env=self.env(root)
            with contextlib.chdir(root),patch.dict(os.environ,env,clear=True), \
                 patch("ffbuild.master.master_metadata",return_value=PIN) as master, \
                 patch("ffbuild.versions.generate_all") as generate, \
                 patch("ffbuild.native_abi.scan_native_abis",side_effect=self.native), \
                 patch("ffbuild.catalog.validate_catalog") as catalog, \
                 patch("ffbuild.state.PublishedState.find_abi",side_effect=AssertionError("forced builds cannot read data")), \
                 patch.object(ci,"seed_plans",return_value=({"x64-windows":"a"*64,"arm64-windows":"b"*64},"f"*64)) as seed:
                result=ci.plan_release()
                master.assert_called_once()
                generate.assert_called_once_with(master=PIN)
                catalog.assert_not_called()
                self.assertEqual(("x64-windows","arm64-windows"),seed.call_args.args[0])
                self.assertEqual(2,len(result["jobs"]))
                self.assertEqual(result,json.loads(Path("ffbuild-plan.json").read_text()))
                self.assertEqual(PIN,result["request"]["seed_master"])
                self.assertEqual(2,result["request"]["plan_attempt"])
                self.assertEqual("f"*64,result["request"]["download_specs"])
                self.assertEqual("ffbuild-downloads-2031.02.03-"+"f"*64+"-"+"c"*64,result["download_cache"])
                outputs=dict(line.split("=",1) for line in (root/"output").read_text().splitlines())
                self.assertEqual(result["jobs"],json.loads(outputs["matrix"]))
                prepare=json.loads(outputs["prepare_matrix"])
                self.assertEqual(1,len(prepare))
                self.assertEqual("x64-windows",prepare[0]["triplet"])
                self.assertEqual({"triplet","abi","seed_key","prefix"},set(prepare[0]))
                self.assertEqual("ffbuild-downloads-2031.02.03-",outputs["download_prefix"])
                self.assertEqual("ffbuild-seed-2031.02.03-x64-windows-"+"a"*64,prepare[0]["seed_key"])
                self.assertTrue(all(j["seed_key"]==prepare[0]["seed_key"] for j in result["jobs"]))
                self.assertEqual(result["download_cache"],outputs["download_key"])
                self.assertEqual("2",outputs["plan_attempt"])
                self.assertNotIn("seed_keys",outputs)
                self.assertNotIn("download_specs",outputs)
                self.assertNotIn("count",outputs)
                self.assertNotIn("triplets",outputs)

    def test_production_catalog_validation_and_empty_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            env=self.env(root,FFBUILD_PRODUCTION="true",FFBUILD_FORCE="false",
                         FFBUILD_TARGET_ARCH="",FFBUILD_TARGET_LICENSE="")
            def scan(requests,**kwargs):
                rows=self.native(requests,**kwargs)
                state.latest_release.return_value={"variants":rows}
                return rows
            state=Mock()
            state.find_abi.return_value={"published":True}
            with contextlib.chdir(root),patch.dict(os.environ,env,clear=True), \
                 patch("ffbuild.master.master_metadata",return_value=PIN) as master, \
                 patch("ffbuild.versions.generate_all") as generate_all, \
                 patch("ffbuild.versions.generate") as generate, \
                 patch("ffbuild.native_abi.scan_native_abis",side_effect=scan), \
                 patch("ffbuild.catalog.validate_catalog") as catalog, \
                 patch("ffbuild.state.PublishedState",return_value=state), \
                 patch.object(ci,"seed_plans") as seed:
                result=ci.plan_release()
                catalog.assert_called_once_with(Path("data"))
                self.assertTrue(state.find_abi.called)
                seed.assert_not_called()
                master.assert_not_called()
                generate_all.assert_not_called()
                generate.assert_called_once_with("8.1.3")
                self.assertNotIn("seed_master",result["request"])
                self.assertFalse(result["publication_required"])
                self.assertEqual([],result["jobs"])
                self.assertEqual({},result["seed_keys"])
                self.assertEqual("",result["download_cache"])
                outputs=dict(line.split("=",1) for line in (root/"output").read_text().splitlines())
                self.assertEqual([],json.loads(outputs["prepare_matrix"]))
                self.assertEqual("false",outputs["publication_required"])

    def test_incomplete_native_matrix_never_emits_plan_or_cache_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with contextlib.chdir(root),patch.dict(os.environ,self.env(root),clear=True), \
                 patch("ffbuild.master.master_metadata",return_value=PIN), \
                 patch("ffbuild.versions.generate_all"), \
                 patch("ffbuild.native_abi.scan_native_abis",return_value=[]), \
                 patch.object(ci,"seed_plans") as seed:
                with self.assertRaisesRegex(ValueError,"Incomplete CI target matrix"):
                    ci.plan_release()
                seed.assert_not_called()
                self.assertFalse(Path("ffbuild-plan.json").exists())
                self.assertFalse((root/"output").exists())

    def test_production_cannot_force_or_select_subset(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict(os.environ,self.env(root,FFBUILD_PRODUCTION="true"),clear=True), \
                 patch("ffbuild.versions.generate_all") as generate:
                with self.assertRaisesRegex(ValueError,"Production requires"):
                    ci.plan_release()
                generate.assert_not_called()


class CacheExecution(unittest.TestCase):
    def test_prepare_incremental_and_repaired_cache_keys(self):
        base="ffbuild-seed-2031.02.03-x64-windows-"+"a"*64
        env={"FFBUILD_CACHE_DIR":"cache","VCPKG_TAG":"2031.02.03",
             "GITHUB_RUN_ID":"12","GITHUB_RUN_ATTEMPT":"3"}
        for matched,refreshed,expected in (
            (base,False,""),(base+"-11-1",False,""),
            ("",True,base),("ffbuild-seed-2031.02.03-x64-windows-"+"b"*64,True,base),
            (base,True,base+"-12-3"),(base+"-11-1",True,base+"-12-3")):
            with self.subTest(matched=matched,refreshed=refreshed),patch.dict(os.environ,env), \
                 patch("ffbuild.seed.load_seed_plan",return_value={"key":"a"*64}), \
                 patch("ffbuild.seed.populate_cache",return_value=refreshed) as populate, \
                 patch("ffbuild.seed.prune_seed_cache") as prune:
                self.assertEqual(expected,ci.prepare_cache("x64-windows","a"*64,matched_key=matched))
                self.assertEqual(matched==base or matched.startswith(base+"-"),populate.call_args.kwargs["prefer_cache"])
                prune.assert_called_once()
        with patch.dict(os.environ,env), \
             patch("ffbuild.seed.load_seed_plan",return_value={"key":"a"*64}), \
             patch("ffbuild.seed.populate_cache",side_effect=RuntimeError("ABI drift")), \
             patch("ffbuild.seed.prune_seed_cache") as prune:
            with self.assertRaisesRegex(RuntimeError,"ABI drift"):
                ci.prepare_cache("x64-windows","a"*64,matched_key=base)
            prune.assert_not_called()

    def test_worker_and_prepare_prefer_repaired_same_abi_without_cross_abi_fallback(self):
        import yaml
        from ffbuild.versions import ROOT
        jobs=yaml.safe_load((ROOT/".github/workflows/build-release.yml").read_text(encoding="utf8"))["jobs"]
        prepare=next(s for s in jobs["prepare"]["steps"] if s.get("id")=="seed-cache")
        worker=next(s for s in jobs["build"]["steps"] if s.get("name")=="Restore centrally prebuilt dependencies")
        p=prepare["with"];w=worker["with"]
        self.assertEqual(p["key"],w["key"])
        self.assertEqual(p["restore-keys"].splitlines()[:2],w["restore-keys"].splitlines())
        self.assertIn("matrix.prefix",p["restore-keys"])
        self.assertNotIn("matrix.prefix",w["restore-keys"])
        save=next(s for s in jobs["prepare"]["steps"] if s.get("name")=="Save completed shared dependency cache")
        self.assertIn("steps.prepare-cache.outputs.save_key",save["if"])
        self.assertIn("steps.prepare-cache.outputs.save_key",save["with"]["key"])

    def test_download_uses_all_configured_architectures_without_build(self):
        with patch.dict(os.environ,{"TRIPLETS":"x64-windows arm64-windows"}), \
             patch("ffbuild.seed.load_seed_plan",side_effect=lambda p,t:{"triplet":t}), \
             patch("ffbuild.seed.prepare_seed") as run:
            ci.download_sources()
        self.assertEqual(["x64-windows","arm64-windows"],[c.kwargs["triplet"] for c in run.call_args_list])
        self.assertTrue(all(c.kwargs["only_downloads"] for c in run.call_args_list))

    def test_worker_package_gates_dry_run_before_sdk_upload(self):
        job={"port":"ffmpeg","triplet":"x64-windows"}
        with patch.dict(os.environ,{"VCPKG_ROOT":"root","FFBUILD_JOB":json.dumps(job)}), \
             patch("ffbuild.compliance.find_ffmpeg_source",return_value=Path("source")), \
             patch("ffbuild.package.package_job") as package, \
             patch("ffbuild.publication.publish") as publish:
            ci.worker_package()
            package.assert_called_once_with(Path("root/packages/ffmpeg_x64-windows"),job,Path("Release"),
                                         installed_root=Path("root/installed"),source_tree=Path("source"))
            publish.assert_called_once_with(artifacts_dir=Path("Release"),data_dir=Path("data"),dry_run=True)
            package.side_effect=RuntimeError("license violation")
            publish.reset_mock()
            with self.assertRaisesRegex(RuntimeError,"license violation"):
                ci.worker_package()
            publish.assert_not_called()

class CurrentCIContract(unittest.TestCase):
    def test_no_historical_cache_paths_keys_or_wrapper(self):
        import yaml
        from ffbuild.versions import ROOT
        workflow_files=list((ROOT/".github/workflows").glob("*.yml"))
        action_files=list((ROOT/".github/actions").glob("*/action.yml"))
        for path in workflow_files+action_files:
            body=path.read_text(encoding="utf-8")
            for marker in ("legacy-cache", "legacy_cache", "legacy-download", "legacy_download",
                           "legacy-path:", "legacy-prefix:", "download_legacy",
                           "move-legacy-cache", "vcpkg-restore-caches", "./.github/actions/restore-cache",
                           "vcpkg-seed-", "vcpkg-dl-all-"):
                self.assertNotIn(marker,body,str(path))
            doc=yaml.safe_load(body)
            for job in ([doc["runs"]] if path.name=="action.yml" else doc["jobs"].values()):
                for step in job.get("steps",[]):
                    if step.get("uses","").startswith("actions/cache/restore@"):
                        self.assertLessEqual(set(step["with"]),{"path","key","restore-keys","fail-on-cache-miss"})
                        if "restore-keys" in step["with"]:
                            self.assertTrue(any(x in step["with"]["restore-keys"] for x in ("prefix","matrix.seed_key")))
        self.assertFalse((ROOT/".github/actions/restore-cache/action.yml").exists())
        self.assertFalse(hasattr(ci,"move_legacy_cache"))
        for name in ("ci.py","autoheal/cli.py","autoheal/repair.py"):
            body=(ROOT/"scripts/ffbuild"/name).read_text(encoding="utf-8")
            for marker in ("FFBUILD_LEGACY_","vcpkg-seed-","vcpkg-dl-all-","ffbuild-native-{","legacy_prefix"):
                self.assertNotIn(marker,body)


    def test_worker_missing_native_graph_is_rejected_before_vcpkg(self):
        job={"yaml":"8.1.3","package":"ffmpeg[all-lgpl]","port":"ffmpeg",
             "tester_port":"ffmpeg-tester","triplet":"x64-windows","abi_hash":"a"*64}
        with patch.dict(os.environ,{"FFBUILD_JOB":json.dumps(job)}), \
             patch("ffbuild.cache_guard.restore_dependencies") as restore:
            with self.assertRaisesRegex(ValueError,"native_graph_sha256"):
                ci.main(["restore-dependencies"])
            restore.assert_not_called()

    def test_repair_requires_current_source_and_download_identity(self):
        from ffbuild.autoheal import repair
        from ffbuild.autoheal import build
        valid={"seed_master":PIN,"download_specs":"c"*64,"vcpkg_tag":"2031.02.03"}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for key in valid:
                source={k:v for k,v in valid.items() if k!=key}
                with self.subTest(key=key),patch.dict(os.environ,{"VCPKG_TAG":"2031.02.03"}), \
                     patch.object(repair,"prepare_context",return_value={"source_snapshot":source}), \
                     patch.object(build,"runtime_dir",return_value=root), \
                     patch("ffbuild.versions.generate_all") as generate:
                    with self.assertRaises(ValueError):
                        repair.prepare({},"8.1.3")
                    generate.assert_not_called()
