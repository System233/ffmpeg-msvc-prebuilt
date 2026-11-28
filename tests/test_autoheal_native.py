"""Representative validation and cross-architecture binary checks."""
import copy
import hashlib
import os
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from ffbuild.autoheal import build


def plan(*rows):
    return {"diagnostics": [{"job_id": i+1, "build_plan": {"triplet": t, "license": l, "linkage": k}}
                             for i, (t,l,k) in enumerate(rows)]}


def check(spec, *jobs):
    return {"spec": spec, "jobs": list(jobs), "reason": "same failure"}


def consumer_evidence(modules=None, *, linkage="shared", runtime="passed"):
    modules = modules or ("avcodec", "avdevice", "avfilter", "avformat", "avutil", "swresample", "swscale")
    result = []
    for cfg in ("release", "debug"):
        for mode in ("config", "module", "legacy", "pkgconfig", "component"):
            names = ["check-full", "check-full-cpp"]
            if mode == "component":
                names = ["check-component-avformat"]
            elif mode != "legacy":
                names += ["check-" + m for m in modules]
            if mode == "config" and linkage == "shared":
                names += ["check-crt-" + lang + "-" + crt for lang in ("c", "cpp") for crt in ("mt", "md")]
            for name in names:
                result.append({"id": f"installed.{mode}.{cfg}.{name}", "configure": "passed",
                               "compile_link": "passed", "runtime": runtime,
                               **({"reason": "host_architecture_incompatible"} if runtime == "skipped" else {})})
    return result


def pe(path, machine):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, machine)
    path.write_bytes(data)


def archive(path, machine):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"object.obj/".ljust(16) + b"0".ljust(12) + b"0".ljust(6) + b"0".ljust(6) + b"0".ljust(8) + b"8".ljust(10) + b"`\n"
    path.write_bytes(b"!<arch>\n" + header + struct.pack("<H", machine) + bytes(6))


class NativeValidation(unittest.TestCase):
    def test_shared_superset_covers_static_and_shared(self):
        data = plan(("x64-windows","lgpl","shared"), ("arm64-windows","gpl","static"))
        item = check("ffmpeg[all-gpl]:x64-windows",1,2)
        self.assertEqual([item], build.validate_plan({"checks":[item]},data))
        for spec in ("ffmpeg[all-gpl,static]:x64-windows","ffmpeg[all-lgpl]:x64-windows","ffmpeg[all-gpl]:x86-windows"):
            with self.assertRaises(ValueError):
                build.validate_plan({"checks":[check(spec,1,2)]},data)
        with self.assertRaises(ValueError):
            build.validate_plan({"checks":[check(item["spec"],1)]},data)

    def test_static_only_and_nonfree(self):
        data = plan(("arm64-windows","nonfree","static"))
        valid = check("ffmpeg[all-nonfree,static]:arm64-windows",1)
        self.assertEqual([valid],build.validate_plan({"checks":[valid]},data))
        for spec in ("ffmpeg[all-gpl,static]:arm64-windows","ffmpeg[all-nonfree]:arm64-windows"):
            with self.assertRaises(ValueError):
                build.validate_plan({"checks":[check(spec,1)]},data)

    def test_cross_arch_and_native_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed, trees, packages = root/"installed",root/"buildtrees",root/"packages"
            triplet = "arm64-windows"
            prefix = installed/triplet
            machine = 0xaa64
            libs = ["avutil","avcodec","avformat","avdevice","avfilter","swresample","swscale"]
            names = {"check-full.exe", "check-full-cpp.exe"} | {f"check-{lib}.exe" for lib in libs}
            for config, suffix in ((prefix,"rel"),(prefix/"debug","dbg")):
                for lib in libs:
                    archive(config/"lib"/(lib+".lib"),machine)
                    pc = config/"lib/pkgconfig"/("lib"+lib+".pc")
                    pc.parent.mkdir(parents=True,exist_ok=True)
                    pc.touch()
                    pe(config/"bin"/(lib+"-1.dll"),machine)
                for name in names:
                    pe(trees/"ffmpeg-tester"/f"{triplet}-{suffix}"/name,machine)
            pe(prefix/"tools/ffmpeg/ffmpeg.exe",machine)
            job = {"triplet":triplet,"package":"ffmpeg[all-gpl]","features":["ffmpeg"],"linkage":"shared"}
            with mock.patch.object(build,"_layout_paths",return_value=(installed,trees,packages)), \
                 mock.patch.object(build,"_verify_native_package_abi"), \
                 mock.patch.object(build,"_read_control",return_value=(None,None,{"ffmpeg","core"},None)), \
                 mock.patch.object(build,"_layout",return_value="shared"), \
                 mock.patch.object(build,"can_execute",return_value=False), \
                 mock.patch.object(build,"validate_installed",
                     side_effect=lambda *a, **kw: consumer_evidence(
                         libs, linkage=kw["linkage"], runtime="passed" if build.can_execute(triplet) else "skipped")) as sdk, \
                 mock.patch.object(build,"_run") as run:
                result=build.verify_outputs(job,"a"*64)
                self.assertEqual("skipped",result["runtime"]["status"])
                self.assertEqual({"release":9,"debug":9},result["tester_targets"])
                self.assertEqual(68, len(result["consumer_cases"]))
                sdk.assert_called_once()
                run.assert_not_called()
                data=plan((triplet,"gpl","shared"))
                evidence={"schema":1,"candidate":"b"*40,"tree":"c"*40,
                          "checks":[dict(result,jobs=[1],reason="same error")]}
                build.validate_evidence(evidence,data)
                for replacement in (result["tester_cases"]["release"][:-1],
                                    result["tester_cases"]["release"][:-1] + [result["tester_cases"]["release"][0]]):
                    bad = copy.deepcopy(evidence)
                    bad["checks"][0]["tester_cases"]["release"] = replacement
                    with self.assertRaisesRegex(ValueError, "Incomplete Tester"):
                        build.validate_evidence(bad, data)
                bad=copy.deepcopy(evidence)
                bad["checks"][0]["runtime"]={"status":"passed"}
                with self.assertRaises(ValueError):
                    build.validate_evidence(bad,data)
                pe(prefix/"bin/avcodec-1.dll",0x8664)
                with self.assertRaisesRegex(build.BuildFailure,"architecture mismatch"):
                    build.verify_outputs(job,"a"*64)
                pe(prefix/"bin/avcodec-1.dll",machine)
                with mock.patch.object(build,"can_execute",return_value=True), mock.patch.object(build,"runtime_dir",return_value=root), mock.patch("ffbuild.sdk_validation._runtime_env",return_value={}):
                    result=build.verify_outputs(job,"a"*64)
                    self.assertEqual(18,result["runtime"]["tester_executions"])
                    self.assertEqual(19,run.call_count)
                for selected, suffix in ((prefix, "rel"), (prefix / "debug", "dbg")):
                    for lib in ("postproc", "avresample"):
                        archive(selected / "lib" / (lib + ".lib"), machine)
                        pe(selected / "bin" / (lib + "-1.dll"), machine)
                        pc = selected / "lib/pkgconfig" / f"lib{lib}.pc"
                        pc.touch()
                        pe(trees / "ffmpeg-tester" / f"{triplet}-{suffix}" /
                           f"check-{lib}.exe", machine)
                libs.extend(("postproc", "avresample"))
                result = build.verify_outputs(job, "a" * 64)
                self.assertEqual({"release": 11, "debug": 11}, result["tester_targets"])
                build.validate_evidence(dict(evidence, checks=[dict(result, jobs=[1], reason="same error")]), data)

    def test_evidence_rejects_native_skip_and_missing_independent_cases(self):
        from test_agent_repair import RESULT
        data = plan(("x64-windows", "gpl", "shared"))
        result = dict(copy.deepcopy(RESULT), jobs=[1], reason="same error")
        evidence = {"schema": 1, "candidate": "a"*40, "tree": "b"*40, "checks": [result]}
        build.validate_evidence(evidence, data)
        for edit in ("skip", "omit", "duplicate", "fail", "runtime"):
            bad = copy.deepcopy(evidence)
            row = bad["checks"][0]
            if edit == "skip":
                row["runtime"] = {"status": "skipped", "reason": "host_architecture_incompatible"}
                row["consumer_cases"] = consumer_evidence(runtime="skipped")
            elif edit == "omit":
                row["consumer_cases"] = [r for r in row["consumer_cases"] if ".legacy." not in r["id"]]
            elif edit == "duplicate":
                row["consumer_cases"][-1] = row["consumer_cases"][0]
            elif edit == "fail":
                row["consumer_cases"][0]["compile_link"] = "failed"
            else:
                row["consumer_cases"][0]["runtime"] = "skipped"
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                build.validate_evidence(bad, data)

    def test_invalid_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"bad"
            file.write_bytes(b"MZ")
            with self.assertRaises(ValueError):
                build.pe_machine(file)
            file.write_bytes(b"!<arch>\n")
            with self.assertRaises(ValueError):
                build.coff_archive_machines(file)

    def test_pinned_source_preparation_and_cache_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b"verified source"
            digest = hashlib.sha512(payload).hexdigest()
            archive_path = root/"downloads/ffmpeg-ffmpeg-n8.1.1.tar.gz"
            archive_path.parent.mkdir()
            archive_path.write_bytes(payload)
            data = {"target_yaml":"8.1.1"}
            with mock.patch.dict(os.environ, {"VCPKG_ROOT":str(root), "FFBUILD_REPAIR_CACHE":str(root/"cache")}), \
                 mock.patch.object(build,"config",return_value={"source":{"ref":"n${VERSION}","sha512":digest}}), \
                 mock.patch.object(build,"runtime_dir",return_value=root), \
                 mock.patch.object(build,"vcpkg_command",side_effect=lambda args:args), \
                 mock.patch.object(build,"_run") as run:
                build.prefetch_source(data)
                run.assert_not_called()
                archive_path.write_bytes(b"wrong")
                build.prefetch_source(data)
                self.assertFalse(archive_path.exists())
                self.assertEqual(["x-download",str(archive_path),digest,
                                  "--url=https://github.com/ffmpeg/ffmpeg/archive/n8.1.1.tar.gz"],run.call_args.args[0])
                self.assertEqual(build.cache_dir("x64-windows"),build.cache_dir("arm64-windows"))

    def test_preflight_fills_cache_before_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=plan(("x64-windows","gpl","shared"))
            data["triplets"]=["x64-windows"]
            data["diagnostics"][0]["build_plan"]["package"]="ffmpeg[all-gpl]"
            with mock.patch.object(build,"prepare_port",return_value=root), \
                 mock.patch.object(build,"prefetch_source") as prefetch, \
                 mock.patch.object(build,"runtime_dir",return_value=root), \
                 mock.patch.object(build,"cache_dir",return_value=root/"cache"), \
                 mock.patch.object(build,"job_for",return_value={"triplet":"x64-windows"}), \
                 mock.patch.object(build,"cached_abis",side_effect=[build.EnvironmentFailure("missing"),{}]) as scan, \
                 mock.patch.object(build,"bindings",return_value={"context_sha256":"a","contract_sha256":"b"}), \
                 mock.patch("ffbuild.seed.DEFAULT_PLAN", root/"missing-plan.json"), \
                 mock.patch("ffbuild.seed.prepare_seed") as seed:
                build.preflight(data)
                prefetch.assert_called_once_with(data)
                seed.assert_called_once_with(triplet="x64-windows",plan=None,cache_dir=root/"cache")
                self.assertEqual(2,scan.call_count)
                self.assertTrue((root/"ready.json").is_file())

    def test_workflow_reuses_production_cache_path(self):
        import yaml
        from ffbuild.versions import ROOT
        repair=yaml.safe_load((ROOT/".github/actions/prepare-repair/action.yml").read_text(encoding="utf-8"))["runs"]
        worker=yaml.safe_load((ROOT/".github/workflows/build-release.yml").read_text(encoding="utf-8"))["jobs"]["prepare"]
        seed=[step["with"] for step in worker["steps"] if step.get("uses","").startswith("actions/cache/save") and step.get("with",{}).get("key","").startswith("ffbuild-seed-")][0]
        restores=[step["with"] for step in repair["steps"] if step.get("with",{}).get("key","").startswith("ffbuild-seed-")]
        self.assertEqual(4,len(restores))
        self.assertTrue(all(item["path"]==seed["path"] for item in restores))
        paths=next(step["env"] for step in repair["steps"] if step.get("name")=="Initialize native repair paths")
        self.assertEqual(seed["path"],paths["FFBUILD_REPAIR_CACHE"])

    def test_legacy_restore_uses_original_cache_version_and_current_destination(self):
        import yaml
        from ffbuild.versions import ROOT
        workflow=yaml.safe_load((ROOT/".github/workflows/auto-heal.yml").read_text(encoding="utf-8"))
        steps=yaml.safe_load((ROOT/".github/actions/prepare-repair/action.yml").read_text(encoding="utf-8"))["runs"]["steps"]
        fallback=[s for s in steps if s.get("uses")=="./.github/actions/restore-legacy-cache"]
        self.assertEqual(5,len(fallback))
        for item in fallback:
            cfg=item["with"]
            self.assertNotEqual(cfg["legacy-path"],cfg["path"])
            self.assertIn("cache-matched-key == ''", item["if"])
            self.assertIn("/ffbuild/",cfg["path"])
        for arch in ("x64","x86","arm64","arm"):
            cfg=next(s["with"] for s in fallback if s["name"]==f"Reuse legacy {arch}-windows dependency Seed")
            self.assertTrue(cfg["legacy-path"].endswith("/vcpkg-cache"))
            self.assertTrue(cfg["prefix"].endswith(f"{arch}-windows-"))
        action=yaml.safe_load((ROOT/".github/actions/restore-legacy-cache/action.yml").read_text(encoding="utf-8"))
        self.assertEqual("${{ inputs.legacy-path }}",action["runs"]["steps"][0]["with"]["path"])
        self.assertIn("Move-Item",action["runs"]["steps"][1]["run"])

    def test_audit_artifacts_are_attempt_scoped(self):
        import yaml
        from ffbuild.versions import ROOT
        jobs=yaml.safe_load((ROOT/".github/workflows/auto-heal.yml").read_text(encoding="utf-8"))["jobs"]
        for job in jobs.values():
            for step in job.get("steps",[]):
                if step.get("uses","").startswith(("actions/upload-artifact","actions/download-artifact")):
                    name=step.get("with",{}).get("name","")
                    if name.startswith("autoheal-"):
                        self.assertIn("a${{ github.run_attempt }}",name)
