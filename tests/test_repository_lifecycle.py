"""Consecutive repository events and failure injection; all remote writes mocked."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, Mock

import yaml

from ffbuild import catalog, publication, updates, run_artifacts
from ffbuild.autoheal import duplicates, github, ledger
from ffbuild.autoheal.scope import check_pr
from ffbuild.identity import archive_name, variant_name, record_release_tag
from ffbuild.native_abi import build_requests
from ffbuild.planner import plan_native
from ffbuild.state import PublishedState
from ffbuild.release_trigger import BOT

from ffbuild import retention as retention_policy

SHA = "a"*40
SIG = "b"*64
DAY = "2026-11-25"
REPO = "example/ffmpeg"


def matrix(version="8.1.3", day=DAY, salt="a", pin=None):
    jobs, blocked = build_requests(version=version, release_date=day, snapshot=pin)
    assert not blocked and len(jobs) == 16
    for job in jobs:
        abi = hashlib.sha256((job["version"]+job["triplet"]+job["package"]+salt).encode()).hexdigest()
        job.update(abi_hash=abi, id=variant_name(job["version"],0,job["triplet"],job["linkage"],job["license"],abi_hash=abi))
    return jobs


def records(rows, tag=None):
    result = []
    for job in rows:
        r = dict(job, variant_id=job["id"], channel="master" if job["yaml"]=="master" else "release",
                 package_format=2, package_spec=job["package"], assets={})
        if job.get("source_ref"):
            r["source_commit"] = job["source_ref"]
        for k in (("binary","debug") if r["linkage"]=="shared" else ("binary",)):
            name=archive_name(r, kind=k)
            r["assets"][k]={"file":name,"size":100,"digest":"sha256:"+hashlib.sha256((name+r["abi_hash"]).encode()).hexdigest()}
        if tag:
            r["publication_tag"]=tag
        result.append(r)
    return result


def pr(number, head, *, master=False, author=BOT):
    version = "master" if master else "8.1.3"
    return {"number":number,"state":"open","user":{"login":author},
            "head":{"ref":ledger.branch_name(version,SIG,number),"sha":head,"repo":{"full_name":REPO}},
            "base":{"ref":"main","sha":"f"*40},"labels":[{"name":"version:"+version}]}


class CatalogLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/".git").mkdir()
        catalog.write_json(self.root/"index.json",{"schema":1,"releases":[],"master":[]})

    def test_same_day_R10_is_latest_and_no_republication(self):
        first=matrix(salt="1")
        r2=matrix(salt="2")
        r9=matrix(salt="9")
        r10=matrix(salt="10")
        for rows,suffix in ((first,""),(r2,"R2"),(r9,"R9"),(r10,"R10")):
            catalog.register_release(self.root,records(rows,"ffmpeg-8.1.3-261125"+suffix))
        state=PublishedState(directory=self.root)
        latest=state.latest_release(r10[0])
        self.assertEqual("ffmpeg-8.1.3-261125R10", record_release_tag(latest["variants"][0]))
        plan=plan_native({"schema":3,"jobs":r10},state=state)
        self.assertFalse(plan["publication_required"])
        self.assertEqual([],plan["jobs"])

    def _old_master(self):
        pin={"ref":"n9.1-dev-4000-gabcdef0","commit":"b"*40,"sha512":"c"*128}
        for suffix in ("","R2","R9","R10"):
            catalog.register_release(self.root,records(matrix("master","2026-11-20",suffix,pin),"ffmpeg-master-261120"+suffix))
        catalog.register_release(self.root,records(matrix()))
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):
                return datetime(2026,12,7,tzinfo=timezone.utc)
        return Clock

    def test_cleanup_only_public_releases_and_index_after_confirmation(self):
        clock=self._old_master()
        before=(self.root/"master/2026.json").read_bytes()
        remote={"ffmpeg-master-261120"+s:{"id":i,"tag_name":"ffmpeg-master-261120"+s,"draft":False,"prerelease":True} for i,s in enumerate(("","R2","R9","R10"),1)}
        deleted=[]
        def delete(*args,**kwargs):
            self.assertEqual(("gh","api"),args[:2])
            self.assertEqual(("--method","DELETE"),args[-2:])
            self.assertIn("/releases/",args[2])
            tag=next(t for t,r in remote.items() if str(r["id"]) == args[2].rsplit("/",1)[1])
            deleted.append(tag)
            remote.pop(tag)
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":REPO}),patch.object(retention_policy,"datetime",clock),patch.object(publication,"_release_api",side_effect=lambda t:remote.get(t)),patch.object(publication,"_run",side_effect=RuntimeError("HTTP 403")):
            with self.assertRaisesRegex(RuntimeError,"403"):
                retention_policy.apply_remote_retention(self.root)
        self.assertEqual(before,(self.root/"master/2026.json").read_bytes())
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":REPO}),patch.object(retention_policy,"datetime",clock),patch.object(publication,"_release_api",side_effect=lambda t:remote.get(t)),patch.object(publication,"_run",side_effect=delete):
            self.assertEqual((1,3),retention_policy.apply_remote_retention(self.root))
            self.assertEqual((1,0),retention_policy.apply_remote_retention(self.root))
        self.assertEqual({"ffmpeg-master-261120","ffmpeg-master-261120R2","ffmpeg-master-261120R9"},set(deleted))
        self.assertEqual(["ffmpeg-master-261120R10"],[x["tag"] for x in catalog.load_shard(self.root,"master",2026)["releases"]])
        self.assertEqual(["8.1.3"],catalog.manifest(self.root)["releases"])

    def test_recover_index_checks_all_remote_assets_and_never_republishes(self):
        rows=records(matrix())
        _,_,batch=catalog.release_from_records(rows)
        digest=hashlib.sha256(json.dumps(batch,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        annotation={"repository_commit":SHA,"batch":digest,"release":batch}
        tag="ffmpeg-8.1.3-261125R2"
        assets={a["file"]:{"size":a["size"],"digest":a["digest"]} for r in rows for a in r["assets"].values()}
        def fake_git(*args):
            return json.dumps(annotation) if args[0]=="for-each-ref" else SHA
        with patch.dict(os.environ,{"GITHUB_REF":"refs/heads/main","GITHUB_REPOSITORY":REPO}),patch("ffbuild.release_trigger.git",side_effect=fake_git),patch("ffbuild.publication.subprocess.run"),patch.object(publication,"_release_api",return_value={"id":1,"tag_name":tag,"draft":False,"prerelease":False}),patch.object(publication,"_release_asset_list",return_value=assets),patch.object(publication,"_push_data") as push,patch.object(publication,"_release_assets") as publish:
            key=next(iter(assets))
            saved=assets[key]["digest"]
            assets[key]["digest"]="sha256:"+"0"*64
            with self.assertRaisesRegex(ValueError,"digest"):
                publication.recover_index(tag,self.root)
            push.assert_not_called()
            assets[key]["digest"]=saved
            publication.recover_index(tag,self.root)
            push.assert_called_once()
            publish.assert_not_called()
        recovered=catalog.load_shard(self.root,"releases","8.1.3")["releases"][0]
        self.assertEqual(dict(batch,tag=tag),recovered)


class GateLifecycle(unittest.TestCase):
    def test_legacy_auto_merge_PR_cannot_pass_as_ordinary_PR(self):
        from ffbuild.release_trigger import automatic_pr
        legacy=pr(80,SHA,master=True)
        legacy["head"]["ref"]="fix/ffmpeg-master-r2"
        legacy["labels"]=[{"name":"ffmpeg-master"}]
        with self.assertRaisesRegex(ValueError,"Invalid automatic"):
            automatic_pr(legacy,REPO)


class RetryLifecycle(unittest.TestCase):
    def test_PR_retry_plan_binds_PR_head_not_synthetic_merge_commit(self):
        from ffbuild.autoheal.triage import retry_plan_bound_to_run
        request={"plan_attempt":1,"repository_commit":"d"*40,"pr_head":SHA,"pr_base":"f"*40}
        self.assertTrue(retry_plan_bound_to_run(request,{"event":"pull_request","head_sha":SHA},1))
        self.assertFalse(retry_plan_bound_to_run(request,{"event":"pull_request","head_sha":"c"*40},1))
        self.assertFalse(retry_plan_bound_to_run(request,{"event":"workflow_dispatch","head_sha":SHA},1))

    def test_partial_retry_preserves_successful_old_worker_and_new_plan_invalidates(self):
        rows=[{"id":"ffmpeg-a"},{"id":"ffmpeg-b"}]
        def job(name,status):
            return {"name":"build / "+name,"conclusion":status,"started_at":"2026-11-25T00:00:00Z"}
        history=[(1,{},[job("plan","success"),job("ffbuild-ffmpeg-a","success"),job("ffbuild-ffmpeg-b","failure")]),
                 (2,{},[job("ffbuild-ffmpeg-b","success")])]
        artifacts=[{"name":n,"created_at":"2026-11-25T01:00:00Z"} for n in ("ffbuild-plan-a1","ffmpeg-a-a1","ffmpeg-b-a2")]
        with patch.object(run_artifacts,"attempts",return_value=iter(history)):
            selected=run_artifacts.plan_artifact(1,2,artifacts,expected=1)
        self.assertEqual(1,selected[0])
        self.assertEqual({"ffmpeg-a":"ffmpeg-a-a1","ffmpeg-b":"ffmpeg-b-a2"},run_artifacts.select_artifacts(rows,history,1,artifacts))
        history.append((3,{},[job("plan","success"),job("ffbuild-ffmpeg-b","success")]))
        artifacts.append({"name":"ffbuild-plan-a3","created_at":"2026-11-25T01:00:00Z"})
        with patch.object(run_artifacts,"attempts",return_value=iter(history)):
            self.assertIsNone(run_artifacts.plan_artifact(1,3,artifacts,expected=1))
        with self.assertRaisesRegex(ValueError,"Incomplete"):
            run_artifacts.select_artifacts(rows,history,3,artifacts)
        with self.assertRaisesRegex(ValueError,"not successful"):
            run_artifacts.select_artifacts(rows,history[:2]+[(3,{},[job("ffbuild-ffmpeg-a","failure")])],1,artifacts)


class DuplicateLifecycle(unittest.TestCase):
    def test_all_occurrences_filter_human_prs(self):
        first, second, human = pr(1,SHA),pr(2,"c"*40),pr(3,"d"*40,author="human")
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":REPO}),patch.object(github,"collection",return_value=[first,second,human]):
            self.assertEqual([1,2],[x["number"] for x in duplicates.open_repairs("8.1.3",SIG)])

    def test_report_without_patch_cannot_trigger_delivery(self):
        from ffbuild.autoheal.delivery import deliver
        source={"schema":1,"trusted_repair_source":True,"automatic_version_pr":True,
                "source":{"run_id":100,"run_attempt":1,"head_sha":SHA},
                "pr":{"number":1,"head":ledger.branch_name("8.1.3",SIG),"head_sha":SHA},
                "groups":[{"yaml":"8.1.3","signature":SIG,"phase":"build","repairable":True,
                           "jobs":[{"variant_id":"a","abi_hash":"d"*64}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"manifest.json").write_text(json.dumps({"schema":1,"mode":"duplicate-only"}))
            with patch("ffbuild.autoheal.delivery.run") as run:
                with self.assertRaisesRegex(ValueError,"Repair artifact or manifest missing"):
                    deliver(source,"8.1.3",root)
                run.assert_not_called()


class ScannerLifecycle(unittest.TestCase):
    def test_template_upgrade_preserves_existing_child_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"ffmpeg").mkdir()
            (root/"patches").mkdir()
            (root/"patches/placeholder").write_text("")
            (root/"ffmpeg/base.yaml").write_text("{}")
            (root/"ffmpeg/10.0.yaml").write_text("extends: base\npatches: []\n")
            (root/"ffmpeg/10.0.1.yaml").write_text(yaml.safe_dump({"source":{"method":"git","repo":"ffmpeg/ffmpeg","ref":"n"+chr(36)+"{VERSION}","sha512":"d"*128}}))
            def git(*args): return subprocess.check_output(["git",*args],cwd=root,text=True).strip()
            git("init","-q","-b","main");git("config","user.name","test");git("config","user.email","test@example.invalid");git("add",".");git("commit","-qm","base")
            base=git("rev-parse","HEAD")
            with patch.object(updates,"ROOT",root):
                docs=updates._proposal_documents("10.0","c"*128)
            self.assertEqual("base",docs["10.0"]["extends"])
            (root/"ffmpeg/10.0.yaml").write_text(yaml.safe_dump(docs["10.0"]))
            git("add",".");git("commit","-qm","proposal")
            self.assertEqual(["ffmpeg/10.0.yaml"],check_pr("10.0",base,git("rev-parse","HEAD"),root,allow_new=True))
            with self.assertRaisesRegex(ValueError,"source identity"):
                check_pr("10.0",base,git("rev-parse","HEAD"),root)

    def test_recover_orphan_from_real_git_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo";remote=Path(tmp)/"remote.git"
            root.mkdir();(root/"ffmpeg").mkdir();(root/"patches").mkdir()
            (root/"patches/placeholder").write_text("")
            (root/"ffmpeg/base.yaml").write_text("{}")
            (root/"ffmpeg/10.0.yaml").write_text("extends: base\npatches: []\n")
            def git(*args):return subprocess.check_output(["git",*map(str,args)],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
            git("init","-q","-b","main");git("init","--bare","-q",remote)
            git("config","user.name","test");git("config","user.email","test@example.invalid")
            git("add",".");git("commit","-qm","base");base=git("rev-parse","HEAD")
            git("remote","add","origin",remote);git("push","-u","origin","main")
            branch="auto/ffmpeg-10.0.1";git("switch","-c",branch)
            with patch.object(updates,"ROOT",root):
                docs=updates._proposal_documents("10.0.1","c"*128)
            for name,doc in docs.items():
                (root/f"ffmpeg/{name}.yaml").write_text(yaml.safe_dump(doc))
            git("add",".");git("commit","-qm","feat(ffmpeg): propose 10.0.1 build spec")
            sha=git("rev-parse","HEAD");git("push","origin",branch);git("switch","main")
            info={"author":{"login":BOT},"committer":{"login":BOT},"commit":{"message":"feat(ffmpeg): propose 10.0.1 build spec"},"parents":[{"sha":base}]}
            with patch.dict(os.environ,{"GITHUB_REPOSITORY":REPO}),patch.object(updates,"ROOT",root),patch.object(github,"api",return_value=info):
                recovered=updates._recover_proposal("10.0.1",branch,sha+"\trefs/heads/"+branch,base,"c"*128)
                self.assertEqual(docs,recovered)
                with self.assertRaisesRegex(ValueError,"content differs"):
                    updates._recover_proposal("10.0.1",branch,sha+"\trefs/heads/"+branch,base,"d"*128)
            self.assertEqual(base,git("rev-parse","HEAD"))

    def test_orphan_failure_does_not_block_next_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"ffmpeg").mkdir()
            def fake_git(*args):
                return subprocess.CompletedProcess([],0,SHA if args[0]=="rev-parse" else SHA+"\t"+args[-1],"")
            result=subprocess.CompletedProcess([],0,"exists","")
            with patch.dict(os.environ,{"GH_TOKEN":"mock","GITHUB_REPOSITORY":REPO}),patch.object(updates,"ROOT",root),patch.object(updates,"_git",side_effect=fake_git),patch.object(updates.subprocess,"run",return_value=result),patch.object(github,"api",return_value=[]),patch.object(updates,"_recover_proposal",side_effect=[ValueError("untrusted orphan"),{"9.1.1":{"extends":"9.1"}}]) as recover,patch.object(updates,"_create_proposal") as create,patch("ffbuild.release_trigger.ensure_label",return_value="version:9.1.1"):
                with self.assertRaisesRegex(ValueError,"untrusted orphan"):
                    updates.apply_versions(["8.1.4","9.1.1"],sha512="c"*128)
                self.assertEqual(2,recover.call_count)
                self.assertEqual("9.1.1",create.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
