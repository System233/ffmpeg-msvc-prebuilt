"""Dependency Seed contracts; native fixture enabled explicitly via environment."""

from __future__ import annotations

import hashlib
import json
import zipfile
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from ffbuild.seed import (prepare_seed, seed_identity, external_batch, seed_hash,
                          select_batches, validate_plan, verify_batch, require_seed_archives, populate_cache, CacheUnavailable,
                          _manifest_signature, load_seed_plan, prune_seed_cache, verify_target_coverage)
from ffbuild.versions import ROOT, generate_all
from ffbuild.targets import Target


def batch(*rows):
    return {"abis": {f"{name}_{arch}": abi * 64 for name, arch, abi, features in rows},
            "specs": {f"{name}_{arch}": f"{name}[{features}]:{arch}" for name, arch, abi, features in rows}}


def plan_for(batches, triplet="x64-windows"):
    return {"triplet": triplet, "batches": batches, "key": seed_hash(batches)}



class SharedDependencySeedTests(unittest.TestCase):
    def test_generated_ports_contain_only_current_ffmpeg_recipes(self):
        with tempfile.TemporaryDirectory() as temporary:
            overlay=Path(temporary)
            ports=generate_all(output=overlay)
            self.assertTrue(ports)
            self.assertEqual(set(ports),set(overlay.iterdir()))
            self.assertTrue(all(json.loads((p/"vcpkg.json").read_text())["name"]=="ffmpeg" for p in ports))
            stale=overlay/"ffmpeg-unused"
            shutil.copytree(ports[0],stale)
            self.assertEqual(set(ports),set(generate_all(output=overlay)))
            self.assertFalse(stale.exists())
            note=overlay/"unrelated.txt"
            note.write_text("keep")
            with self.assertRaisesRegex(ValueError,"non-generated content"):
                generate_all(output=overlay)
            self.assertEqual("keep",note.read_text())

    def test_hash_ignores_target_abis_order_and_duplicate_batches(self):
        dep = batch(("zlib", "x64-windows", "b", "core"))
        targets = {"ffmpeg_x64-windows": "a"*64, "ffmpeg-tester_x64-windows": "c"*64}
        specs = dict(dep["specs"], **{k: k.split("_")[0]+"[core]:x64-windows" for k in targets})
        a = external_batch(dict(dep["abis"], **targets), specs, "x64-windows")
        b = external_batch(dict(dep["abis"], **{k:"d"*64 for k in targets}), specs, "x64-windows")
        self.assertEqual(a,b)
        self.assertEqual(seed_hash([a]), seed_hash([b,a,b]))
        changed = batch(("zlib", "x64-windows", "e", "core"))
        self.assertNotEqual(seed_hash([a]),seed_hash([changed]))
        self.assertNotEqual(seed_hash([a]),seed_hash([a,changed]))
        self.assertEqual(seed_hash([a,changed]),seed_hash([changed,a]))
        self.assertRaises(ValueError, external_batch, dep["abis"],dep["specs"],"x64-windows")

    def test_batch_selection_keeps_exact_graphs_and_never_unions_unrelated_ports(self):
        a=batch(("lib", "arm64-windows","a","core"),("tool","x64-windows","b","core"))
        b=batch(("lib", "arm64-windows","c","core,extra"),("tool","x64-windows","b","core"))
        c=batch(("other", "arm64-windows","d","core"))
        subset=batch(("tool","x64-windows","b","core"))
        selected=select_batches([a,b,c,a,subset])
        self.assertEqual(3,len(selected))
        self.assertEqual(seed_hash([a,b,c,subset]),seed_hash(selected))
        self.assertTrue(all(item in (a,b,c) for item in selected))
        self.assertEqual({frozenset(item["abis"].items()) for item in (a,b,c)},
                         {frozenset(item["abis"].items()) for item in selected})
        # Two separately selected Ports may own the same paths even if their
        # names and ABIs differ. A dry-run cannot certify their union.
        left=batch(("headers-old","x64-windows","e","core"))
        right=batch(("headers-new","x64-windows","f","core"))
        self.assertCountEqual([left,right],select_batches([left,right]))

    def test_manifest_dedup_only_dependency_invariant_features(self):
        m={"name":"ffmpeg","version":"1","default-features":["base"],
           "features":{"base":{"dependencies":["zlib"]},"static":{"description":"static"},
                       "extra":{"dependencies":[{"name":"lib","platform":"!arm"}]}}}
        changed=json.loads(json.dumps(m)); changed["version"]="2"
        self.assertEqual(_manifest_signature(m,("base","static")),_manifest_signature(changed,("base",)))
        self.assertNotEqual(_manifest_signature(m,("base",)),_manifest_signature(m,("base","extra")))
        changed["features"]["extra"]["dependencies"][0]["platform"]="arm"
        self.assertNotEqual(_manifest_signature(m,("base",)),_manifest_signature(changed,("base",)))

    def test_planner_resolves_every_manifest_and_never_queries_synthetic_union(self):
        with tempfile.TemporaryDirectory() as temporary:
            overlay=Path(temporary)
            for name in ("ffmpeg-1-0","ffmpeg-2-0"):
                p=overlay/name;p.mkdir()
                (p/"vcpkg.json").write_text(json.dumps({"name":"ffmpeg","version":name,
                    "features":{"base":{"dependencies":[name]}}}))
            a=batch(("lib","x64-windows","a","core"))
            b=batch(("other","x64-windows","b","core"))
            def query(packages,triplet,**kw):
                if kw.get("port_overlay"):
                    x=a if kw["port_overlay"].name=="ffmpeg-1-0" else b
                    targets={"ffmpeg_x64-windows":"c"*64,"ffmpeg-tester_x64-windows":"d"*64}
                    kw["specs"].update(dict(x["specs"],**{k:k.split("_")[0]+"[core]:x64-windows" for k in targets}))
                    return dict(x["abis"],**targets)
                if len(packages)==2:
                    raise AssertionError("synthetic union must never be queried")
                x=a if packages[0].startswith("lib[") else b
                kw["specs"].update(x["specs"]);return x["abis"]
            with mock.patch("ffbuild.seed.versions",return_value=["1.0","2.0"]), \
                 mock.patch("ffbuild.seed.has_source",return_value=True), \
                 mock.patch("ffbuild.seed.load_targets",return_value=[Target("ffmpeg[base]","x64-windows",("base",))]), \
                 mock.patch("ffbuild.seed.native_abi_query",side_effect=query) as scan:
                key,plan=seed_identity(triplet="x64-windows",overlay=overlay)
                self.assertEqual(4,scan.call_count)
                self.assertEqual(seed_hash([a,b]),key)
                self.assertEqual(2,len(plan["batches"]))
                self.assertEqual({"triplet","batches","key"},set(plan))
                validate_plan(plan,"x64-windows",key)
                (overlay/"plan.json").write_text(json.dumps({"x64-windows":plan}))
                self.assertEqual(plan,load_seed_plan(overlay/"plan.json","x64-windows",key))
                with self.assertRaisesRegex(RuntimeError,"identity mismatch"):
                    validate_plan(plan_for([a]),"x64-windows",key)
                (overlay/"ffmpeg-2-0"/"vcpkg.json").unlink()
                with self.assertRaises(FileNotFoundError):
                    seed_identity(triplet="x64-windows",overlay=overlay)

    def test_prepare_isolates_exact_batches_and_checks_installed_abis(self):
        a=batch(("lib","x64-windows","a","core"))
        b=batch(("lib","x64-windows","b","core,extra"))
        plan=plan_for([a,b])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/"installed"
            commands=[]
            def install(command,**kwargs):
                commands.append(command)
                self.assertTrue(Path(next(x.split("=",1)[1] for x in command if x.startswith("--x-install-root="))).is_dir())
                self.assertIn("--recurse",command)
                self.assertEqual(1,command.count("--x-abi-tools-use-exact-versions"))
                self.assertEqual("1",kwargs["env"]["VCPKG_FORCE_DOWNLOADED_BINARIES"])
                self.assertIn("--clean-buildtrees-after-build",command)
                self.assertIn("--clean-packages-after-build",command)
                self.assertNotIn("--clean-after-build",command)
                self.assertEqual(ROOT,kwargs["cwd"])
                self.assertTrue(kwargs["check"])
            with mock.patch("ffbuild.seed.verify_batch") as verify, \
                 mock.patch("ffbuild.seed.subprocess.run",side_effect=install), \
                 mock.patch("ffbuild.cache_guard.installed_abis",side_effect=[a["abis"],b["abis"]]):
                completed=prepare_seed(triplet="x64-windows",plan=plan,binary=Path("fake-vcpkg.exe"),install_root=root)
                self.assertEqual(2,verify.call_count)
                self.assertEqual(2,len(completed))
                self.assertEqual(["lib[core]:x64-windows","lib[core,extra]:x64-windows"],[c[2] for c in commands])
                self.assertEqual([],list(root.iterdir()))
            with mock.patch("ffbuild.seed.verify_batch",side_effect=RuntimeError("drift")), \
                 mock.patch("ffbuild.seed.subprocess.run") as run:
                with self.assertRaisesRegex(RuntimeError,"drift"):
                    prepare_seed(triplet="x64-windows",plan=plan,install_root=root)
                run.assert_not_called()

    def test_populate_and_verify_resolves_once_and_restores_independently(self):
        a=batch(("lib","x64-windows","a","core"))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with mock.patch("ffbuild.seed.verify_batch") as verify, \
                 mock.patch("ffbuild.seed.subprocess.run") as run, \
                 mock.patch("ffbuild.cache_guard.installed_abis",return_value=a["abis"]):
                prepare_seed(triplet="x64-windows",plan=plan_for([a]),binary=Path("vcpkg.exe"),
                             cache_dir=root/"cache",install_root=root/"roots",verify_after=True)
                verify.assert_called_once()
                self.assertEqual(2,run.call_count)
                first,second=run.call_args_list
                self.assertNotIn("--only-binarycaching",first.args[0])
                self.assertIn("--only-binarycaching",second.args[0])
                self.assertTrue(first.kwargs["env"]["VCPKG_BINARY_SOURCES"].endswith(",readwrite"))
                self.assertTrue(second.kwargs["env"]["VCPKG_BINARY_SOURCES"].endswith(",read"))
                self.assertNotEqual(next(x for x in first.args[0] if x.startswith("--x-install-root=")),
                                    next(x for x in second.args[0] if x.startswith("--x-install-root=")))

    def test_discard_only_confirmed_corruption_in_failed_batch(self):
        from ffbuild.seed import discard_damaged_archives
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)
            healthy_info=b"native ABI info"
            healthy=hashlib.sha256(healthy_info).hexdigest()
            wrong="a"*64
            bad="b"*64
            unrelated="c"*64
            abis={f"{name}_x64-windows":abi for name,abi in
                  (("healthy",healthy),("wrong",wrong),("bad",bad),("unrelated",unrelated))}
            specs={key:key.split("_")[0]+"[core]:x64-windows" for key in abis}
            plan=plan_for([{"abis":abis,"specs":specs}])
            for name,abi in abis.items():
                package=name.split("_")[0]
                file=cache/abi[:2]/(abi+".zip")
                file.parent.mkdir(exist_ok=True)
                if abi in (bad,unrelated):
                    file.write_bytes(b"not a zip")
                else:
                    with zipfile.ZipFile(file,"w") as z:
                        z.writestr(f"share/{package}/vcpkg_abi_info.txt",healthy_info)
            self.assertEqual(2,discard_damaged_archives(plan,cache,{healthy,wrong,bad}))
            self.assertTrue((cache/healthy[:2]/(healthy+".zip")).is_file())
            self.assertTrue((cache/unrelated[:2]/(unrelated+".zip")).is_file())
            self.assertFalse((cache/wrong[:2]/(wrong+".zip")).exists())
            self.assertFalse((cache/bad[:2]/(bad+".zip")).exists())

    def test_each_corrupt_batch_is_recovered_without_repeating_completed_batches(self):
        a=batch(("lib","x64-windows","a","core"))
        b=batch(("other","x64-windows","b","core"))
        c=batch(("healthy","x64-windows","c","core"))
        plan=plan_for([a,b,c])
        for prefer in (True,False):
            visited=[]
            recovered=set()
            def prepare(**kwargs):
                current=kwargs["plan"]["batches"][0]
                key=next(iter(current["abis"]))
                visited.append((key,kwargs.get("cache_only",False)))
                if current != c and key not in recovered:
                    if not kwargs.get("cache_only"):
                        recovered.add(key)
                    raise CacheUnavailable("corruption",current["abis"].values())
            with mock.patch("ffbuild.seed.prepare_seed",side_effect=prepare), \
                 mock.patch("ffbuild.seed.discard_damaged_archives",return_value=1):
                self.assertTrue(populate_cache(triplet="x64-windows",plan=plan,cache_dir=Path("cache"),prefer_cache=prefer))
            names=[name for name,_ in visited]
            self.assertEqual(1,names.count("healthy_x64-windows"))
            self.assertEqual(sorted(names,key=lambda name: ["lib_x64-windows","other_x64-windows","healthy_x64-windows"].index(name)),names)

    def test_seed_reuses_already_observed_target_graph_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            overlay=Path(tmp)
            port=overlay/"ffmpeg-1-0";port.mkdir()
            (port/"vcpkg.json").write_text(json.dumps({"name":"ffmpeg","version":"1.0",
                "features":{"base":{"dependencies":["lib"]}}}))
            a=batch(("lib","x64-windows","a","core"))
            with mock.patch("ffbuild.seed.versions",return_value=["1.0"]), \
                 mock.patch("ffbuild.seed.has_source",return_value=True), \
                 mock.patch("ffbuild.seed.load_targets",return_value=[Target("ffmpeg[base]","x64-windows",("base",))]), \
                 mock.patch("ffbuild.seed.native_abi_query") as query, \
                 mock.patch("ffbuild.seed.verify_batch") as verify:
                key,plan=seed_identity(triplet="x64-windows",overlay=overlay,
                    dependency_batches={("1.0","x64-windows","ffmpeg[base]"):a})
                query.assert_not_called()
                verify.assert_called_once()
                self.assertEqual(seed_hash([a]),key)
                self.assertEqual([a],plan["batches"])

    def test_refresh_reuses_old_cache_and_does_not_swallow_graph_errors(self):
        a=batch(("lib","x64-windows","a","core"))
        plan=plan_for([a])
        cache=Path("cache")
        args=dict(triplet="x64-windows",plan=plan,cache_dir=cache)
        with mock.patch("ffbuild.seed.prepare_seed") as prepare:
            self.assertFalse(populate_cache(**args))
            self.assertTrue(prepare.call_args.kwargs["cache_only"])
        with mock.patch("ffbuild.seed.prepare_seed",side_effect=[CacheUnavailable("corrupt"),None]) as prepare:
            self.assertTrue(populate_cache(**args))
            self.assertEqual(2,prepare.call_count)
            self.assertTrue(prepare.call_args_list[0].kwargs["cache_only"])
            self.assertTrue(prepare.call_args_list[1].kwargs["verify_after"])
            self.assertEqual(cache,prepare.call_args_list[1].kwargs["cache_dir"])
        with mock.patch("ffbuild.seed.prepare_seed") as prepare:
            self.assertTrue(populate_cache(**args,prefer_cache=False))
            prepare.assert_called_once()
            self.assertTrue(prepare.call_args.kwargs["verify_after"])
        with mock.patch("ffbuild.seed.prepare_seed",side_effect=RuntimeError("ABI drift")) as prepare:
            with self.assertRaisesRegex(RuntimeError,"ABI drift"):
                populate_cache(**args)
            prepare.assert_called_once()

    def test_download_only_and_cache_only(self):
        a=batch(("lib","arm64-windows","a","core"),("tool","x64-windows","b","core"))
        plan=plan_for([a],"arm64-windows")
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with mock.patch("ffbuild.seed.verify_batch") as verify,mock.patch("ffbuild.seed.subprocess.run") as run:
                prepare_seed(triplet="arm64-windows",plan=plan,binary=Path("fake-vcpkg.exe"),install_root=root,only_downloads=True)
                self.assertIn("--only-downloads",run.call_args.args[0])
                verify.assert_not_called()
                self.assertNotIn("--clean-buildtrees-after-build",run.call_args.args[0])
                with self.assertRaisesRegex(RuntimeError,"Seed cache incomplete"):
                    prepare_seed(triplet="arm64-windows",plan=plan,cache_only=True,cache_dir=root)
                self.assertEqual(1,run.call_count)
                for abi in a["abis"].values():
                    d=root/abi[:2];d.mkdir();(d/(abi+".zip")).write_bytes(b"fixture")
                with mock.patch("ffbuild.cache_guard.installed_abis",return_value=a["abis"]):
                    prepare_seed(triplet="arm64-windows",plan=plan,binary=Path("fake-vcpkg.exe"),install_root=root,cache_only=True,cache_dir=root)
                self.assertIn("--only-binarycaching",run.call_args.args[0])
                self.assertTrue(run.call_args.kwargs["env"]["VCPKG_BINARY_SOURCES"].endswith(",read"))
                with mock.patch("ffbuild.cache_guard.installed_abis",return_value={}):
                    with self.assertRaisesRegex(RuntimeError,"Installed dependency ABIs differ"):
                        prepare_seed(triplet="arm64-windows",plan=plan,binary=Path("fake-vcpkg.exe"),install_root=root,cache_only=True,cache_dir=root)

    def test_actual_target_evidence_requires_full_seed_coverage(self):
        a = batch(("zlib","x64-windows","a","core"))
        plans = {"x64-windows": plan_for([a])}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            path=root/"graph.json"
            graph=dict(a["abis"],**{"ffmpeg_x64-windows":"b"*64,"ffmpeg-tester_x64-windows":"c"*64})
            path.write_text(json.dumps(graph))
            self.assertEqual(1,verify_target_coverage(plans,root))
            graph["zlib_x64-windows"]="d"*64
            path.write_text(json.dumps(graph))
            with self.assertRaisesRegex(RuntimeError,"missing actual target ABI"):
                verify_target_coverage(plans,root)
            path.unlink()
            with self.assertRaisesRegex(ValueError,"Missing actual target"):
                verify_target_coverage(plans,root)

    def test_finalize_dedicated_cache_keeps_only_required_abi_archives(self):
        plan=plan_for([batch(("zlib","x64-windows","a","core"))])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            files=[]
            for abi in ("a"*64,"b"*64):
                d=root/abi[:2];d.mkdir()
                f=d/(abi+".zip");f.write_bytes(b"fixture");files.append(f)
            other=root/"aa"/"notes.zip";other.write_bytes(b"not ABI")
            self.assertEqual(1,prune_seed_cache(plan,root))
            self.assertTrue(files[0].is_file())
            self.assertFalse(files[1].exists())
            self.assertTrue(other.is_file())
            files[0].unlink()
            with self.assertRaisesRegex(RuntimeError,"Seed cache incomplete"):
                prune_seed_cache(plan,root)

    def test_direct_graph_verification_rejects_missing_or_changed_abis(self):
        a=batch(("lib","x64-windows","a","core"))
        with mock.patch("ffbuild.seed.native_abi_query",return_value={"lib_x64-windows":"b"*64}):
            with self.assertRaisesRegex(RuntimeError,"Direct dependency ABI drift"):
                verify_batch(a,"x64-windows")
        with mock.patch("ffbuild.seed.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError,"Unsupported FFmpeg Triplet"):
                prepare_seed(triplet="x64-linux")
            run.assert_not_called()

    def test_dependency_submission_uses_validated_manifest_not_virtual_port(self):
        from ffbuild.builder import submit_dependencies
        a=batch(("lib","arm64-windows","a","core,extra"),("tool","x64-windows","b","core"))
        plan=plan_for([a],"arm64-windows")
        calls=[]
        def run(args,**kwargs):
            project=kwargs["cwd"]
            self.assertFalse((project/"portfile.cmake").exists())
            manifest=json.loads((project/"vcpkg.json").read_text())
            self.assertEqual({"dependencies":[{"name":"lib","default-features":False,"features":["extra"]},
                                                {"name":"tool","default-features":False,"host":True}]},manifest)
            self.assertIn("--dry-run",args)
            calls.append(kwargs["env"]["VCPKG_FEATURE_FLAGS"])
            for arg in args:
                if arg.startswith("--x-write-nuget-packages-config="):
                    path=Path(arg.split("=",1)[1])
                    path.write_text("<packages>"+"".join(f'<package id="{k}" version="1.0-vcpkg{v}" />'
                                    for k,v in a["abis"].items())+"</packages>")
        with mock.patch("ffbuild.builder.Path.is_file",return_value=True), \
             mock.patch("ffbuild.versions.generate_all"),mock.patch("ffbuild.master.master_metadata",return_value={}), \
             mock.patch("ffbuild.seed.seed_identity",return_value=(plan["key"],plan)), \
             mock.patch("ffbuild.builder.subprocess.run",side_effect=run):
            submit_dependencies(vcpkg_root=Path("vcpkg"),triplet="arm64-windows")
        self.assertEqual(["","dependencygraph"],calls)

    def test_workflow_prebuilds_seed_once_per_needed_triplet(self):
        jobs=yaml.safe_load((ROOT/".github/workflows/build-release.yml").read_text(encoding="utf-8"))["jobs"]
        self.assertIn("prepare_matrix",jobs["plan"]["outputs"])
        self.assertIn("fromJSON(needs.plan.outputs.prepare_matrix)",jobs["prepare"]["strategy"]["matrix"]["include"])
        self.assertEqual(["plan","prepare"],jobs["build"]["needs"])
        self.assertEqual(["plan","download"],jobs["prepare"]["needs"])
        self.assertEqual("plan",jobs["download"]["needs"])
        download=jobs["download"]["steps"]
        source=next(s for s in download if s.get("uses","").startswith("actions/cache/save@"))
        for name in ("prepare","build"):
            restored=next(s for s in jobs[name]["steps"] if s.get("name")=="Restore shared dependency source downloads")
            self.assertEqual(source["with"]["key"],restored["with"]["key"])
            self.assertTrue(restored["with"]["fail-on-cache-miss"])
        prepared=next(s for s in jobs["prepare"]["steps"] if s.get("uses","").startswith("actions/cache/save@"))
        restored=next(s for s in jobs["build"]["steps"] if s.get("name")=="Restore centrally prebuilt dependencies")
        self.assertIn("steps.prepare-cache.outputs.save_key", prepared["with"]["key"])
        self.assertIn("matrix.seed_key", restored["with"]["key"])
        self.assertEqual(2,len(restored["with"]["restore-keys"].splitlines()))
        self.assertTrue(all("matrix.seed_key" in key for key in restored["with"]["restore-keys"].splitlines()))
        self.assertTrue(restored["with"]["fail-on-cache-miss"])
        self.assertFalse(any(s.get("uses","").startswith("actions/cache/save@") for s in jobs["build"]["steps"]))

    def test_dependency_submission_generates_one_source_snapshot_for_all_configured_triplets(self):
        from ffbuild.builder import submit_dependencies
        with mock.patch.dict(os.environ,{"TRIPLETS":"x64-windows arm64-windows"}), \
             mock.patch("ffbuild.builder.Path.is_file",return_value=True), \
             mock.patch("ffbuild.master.master_metadata",return_value={"ref":"pin"}) as pin, \
             mock.patch("ffbuild.versions.generate_all") as generate, \
             mock.patch("ffbuild.seed.seed_identity",return_value=("key",{})) as native, \
             mock.patch("ffbuild.builder._submit_dependency_plan") as submit:
            submit_dependencies(vcpkg_root=Path("vcpkg"))
            pin.assert_called_once()
            generate.assert_called_once_with(master={"ref":"pin"})
            self.assertEqual(["x64-windows","arm64-windows"],[c.kwargs["triplet"] for c in native.call_args_list])
            self.assertEqual(["x64-windows","arm64-windows"],[c.args[2] for c in submit.call_args_list])



@unittest.skipUnless(os.environ.get("FFBUILD_TEST_VCPKG_BIN"), "Set native vcpkg binary for real Seed fixture")
class NativeSeedFixture(unittest.TestCase):
    def test_direct_feature_batches_build_restore_and_reject_corruption(self):
        from ffbuild import native_abi, seed
        import ffvcpkg
        binary=Path(os.environ["FFBUILD_TEST_VCPKG_BIN"]).resolve()
        with tempfile.TemporaryDirectory(prefix="ffbuild-seed-native-") as temporary:
            root=Path(temporary)
            ports=root/"ports"; ports.mkdir()
            cache=root/"cache";cache.mkdir()
            shutil.copytree(ROOT/"triplets",root/"triplets")
            marker=root/"dependency-built"
            target_marker=root/"target-built"
            payload=('file(MAKE_DIRECTORY "${CURRENT_PACKAGES_DIR}/include")\n'
                     'file(WRITE "${CURRENT_PACKAGES_DIR}/include/${PORT}.h" "/* native fixture */")\n'
                     'file(INSTALL "${CMAKE_CURRENT_LIST_DIR}/copyright" DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")\n')
            def make(name,fields,mark):
                p=ports/name;p.mkdir()
                (p/"vcpkg.json").write_text(json.dumps(dict(name=name,version="1.0.0",license="MIT",**fields)))
                (p/"portfile.cmake").write_text(payload+f'file(WRITE "{mark.as_posix()}" "built")\n')
                (p/"copyright").write_text("MIT fixture")
                return p
            make("seed-audit-dep",{"features":{"extra":{"description":"extra"},"default-extra":{"description":"default"}},
                                   "default-features":["default-extra"]},marker)
            ffmpeg=make("ffmpeg",{"dependencies":[{"name":"seed-audit-dep","default-features":False}],
                                 "features":{"extra":{"description":"extra","dependencies":[{"name":"seed-audit-dep",
                                     "default-features":False,"features":["extra"]}]} }},target_marker)
            tester=make("ffmpeg-tester",{"dependencies":[{"name":"ffmpeg","default-features":False}]},target_marker)
            env=dict(os.environ,VCPKG_ROOT=str(binary.parent),FFVCPKG_BIN=str(binary),
                     VCPKG_BINARY_SOURCES=f"clear;files,{cache},readwrite")
            def graph(spec):
                specs={}
                result=native_abi.native_abi_query([spec,"ffmpeg-tester"],"x64-windows",
                            port_overlay=ffmpeg,binary=binary,specs=specs)
                return result,external_batch(result,specs,"x64-windows")
            with mock.patch.object(native_abi,"ROOT",root),mock.patch.object(seed,"ROOT",root), \
                 mock.patch.object(ffvcpkg,"ROOT",root),mock.patch.dict(os.environ,env):
                original,a=graph("ffmpeg[core]")
                _,b=graph("ffmpeg[core,extra]")
                self.assertNotEqual(a["abis"],b["abis"])
                plans=select_batches([a,b]); self.assertEqual(2,len(plans))
                plan=plan_for(plans)
                # Real source-only changes affect FFmpeg/Tester ABIs but not Seed.
                for p in (ffmpeg,tester):
                    f=p/"portfile.cmake"; f.write_text(f.read_text()+"# changed source\n")
                changed,a2=graph("ffmpeg[core]")
                self.assertNotEqual(original["ffmpeg_x64-windows"],changed["ffmpeg_x64-windows"])
                self.assertNotEqual(original["ffmpeg-tester_x64-windows"],changed["ffmpeg-tester_x64-windows"])
                self.assertEqual(a,a2)
                self.assertEqual(seed_hash([a,b]),seed_hash([a2,b]))
                self.assertTrue(populate_cache(triplet="x64-windows",plan=plan_for([a]),binary=binary,
                                               cache_dir=cache,install_root=root/"roots",prefer_cache=False))
                self.assertTrue(marker.exists());marker.unlink()
                abi=next(iter(a["abis"].values()))
                original_archive=cache/abi[:2]/(abi+".zip")
                original_hash=hashlib.sha256(original_archive.read_bytes()).hexdigest()
                self.assertNotEqual(plan_for([a])["key"],plan["key"])
                self.assertTrue(populate_cache(triplet="x64-windows",plan=plan,binary=binary,
                                               cache_dir=cache,install_root=root/"roots",prefer_cache=False))
                self.assertTrue(marker.exists());marker.unlink()
                self.assertEqual(original_hash,hashlib.sha256(original_archive.read_bytes()).hexdigest())
                self.assertFalse(target_marker.exists())
                require_seed_archives(plan,cache)
                abi=next(iter(a["abis"].values()))
                (cache/abi[:2]/(abi+".zip")).write_bytes(b"not a ZIP")
                # The cache provider must repair the bad file while retaining
                # valid ABI archives; no synthetic cache content is accepted.
                healthy_abi=next(iter(b["abis"].values()))
                healthy=cache/healthy_abi[:2]/(healthy_abi+".zip")
                healthy_hash=hashlib.sha256(healthy.read_bytes()).hexdigest()
                self.assertTrue(populate_cache(triplet="x64-windows",plan=plan,binary=binary,cache_dir=cache,
                                               install_root=root/"roots"))
                self.assertTrue(marker.exists());marker.unlink()
                self.assertEqual(healthy_hash,hashlib.sha256(healthy.read_bytes()).hexdigest())
                self.assertFalse(target_marker.exists())
                self.assertFalse(populate_cache(triplet="x64-windows",plan=plan,binary=binary,cache_dir=cache,
                                                install_root=root/"roots"))
                self.assertFalse(marker.exists())
                for value in (a,b):
                    abi=next(iter(value["abis"].values()))
                    (cache/abi[:2]/(abi+".zip")).write_bytes(b"not a ZIP")
                self.assertTrue(populate_cache(triplet="x64-windows",plan=plan,binary=binary,cache_dir=cache,
                                               install_root=root/"roots",prefer_cache=False))
                self.assertTrue(marker.exists()); marker.unlink()
                self.assertFalse(target_marker.exists())
                self.assertFalse(populate_cache(triplet="x64-windows",plan=plan,binary=binary,cache_dir=cache,
                                                install_root=root/"roots"))
                self.assertFalse(marker.exists())



    def test_native_file_ownership_conflict_requires_separate_observed_graphs(self):
        from ffbuild import native_abi, seed
        import ffvcpkg
        binary=Path(os.environ["FFBUILD_TEST_VCPKG_BIN"]).resolve()
        with tempfile.TemporaryDirectory(prefix="ffbuild-seed-conflict-") as temporary:
            root=Path(temporary)
            ports=root/"ports"; ports.mkdir()
            cache=root/"cache"; cache.mkdir()
            shutil.copytree(ROOT/"triplets",root/"triplets")
            names=("seed-conflict-old","seed-conflict-new")
            for name in names:
                port=ports/name; port.mkdir()
                (port/"vcpkg.json").write_text(json.dumps({"name":name,"version":"1.0.0","license":"MIT"}))
                (port/"portfile.cmake").write_text(
                    'file(MAKE_DIRECTORY "${CURRENT_PACKAGES_DIR}/include")\n'
                    'file(WRITE "${CURRENT_PACKAGES_DIR}/include/conflicting.h" "${PORT}")\n'
                    'file(INSTALL "${CMAKE_CURRENT_LIST_DIR}/copyright" DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")\n')
                (port/"copyright").write_text("MIT fixture")
            env=dict(os.environ,VCPKG_ROOT=str(binary.parent),FFVCPKG_BIN=str(binary),
                     VCPKG_BINARY_SOURCES=f"clear;files,{cache},readwrite")
            def direct(specs):
                selected={}
                abis=native_abi.native_abi_query(specs,"x64-windows",binary=binary,specs=selected)
                return {"abis":abis,"specs":selected}
            with mock.patch.object(native_abi,"ROOT",root),mock.patch.object(seed,"ROOT",root), \
                 mock.patch.object(ffvcpkg,"ROOT",root),mock.patch.dict(os.environ,env):
                original=[direct([name+"[core]"]) for name in names]
                union=direct([name+"[core]" for name in names])
                self.assertEqual(seed_hash(original),seed_hash([union]))
                # Actual dry-run permits the union. Actual installation does not.
                with self.assertRaises(subprocess.CalledProcessError):
                    prepare_seed(triplet="x64-windows",plan=plan_for([union]),binary=binary,
                                 cache_dir=cache,install_root=root/"roots")
                selected=select_batches(original)
                self.assertCountEqual(original,selected)
                plan=plan_for(selected)
                prepare_seed(triplet="x64-windows",plan=plan,binary=binary,cache_dir=cache,
                             install_root=root/"roots")
                require_seed_archives(plan,cache)
                prepare_seed(triplet="x64-windows",plan=plan,binary=binary,cache_dir=cache,
                             install_root=root/"roots",cache_only=True)


if __name__ == "__main__":
    unittest.main()
