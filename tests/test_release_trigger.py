"""Event gates, immutable tags and actual version-isolated Git candidates."""
from __future__ import annotations

import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from ffbuild import release_trigger as trigger
from ffbuild.autoheal.scope import check_pr, check_worktree
from ffbuild.identity import record_release_tag
from ffbuild.native_abi import build_requests
from ffbuild import catalog

REPO = "example/ffmpeg"
SHA = "a" * 40


def pr(version="8.1.3", *, bot=True, kind="new", same_repo=True, labels=None):
    return {"number": 42, "user": {"login": trigger.BOT if bot else "human"},
            "head": {"ref": f"auto/ffmpeg-{version}" if kind == "new" else
                    f"autoheal/{version}/0123456789abcdef",
                    "repo": {"full_name": REPO if same_repo else "fork/ffmpeg"}, "sha": SHA},
            "base": {"ref": "main", "sha": "b"*40},
            "labels": [{"name": label} for label in (["version:"+version] if labels is None else labels)]}


class TriggerTests(unittest.TestCase):
    def test_only_authorized_bot_version_pr_compiles(self):
        self.assertEqual(("8.1.3", "new"), trigger.automatic_pr(pr(), REPO))
        self.assertEqual(("master", "repair"), trigger.automatic_pr(pr("master", kind="repair"), REPO))
        for ordinary in (pr(bot=False), pr(same_repo=False)):
            self.assertEqual({"version": ""}, trigger.pr_gate({"pull_request": ordinary}, REPO))
        self.assertEqual({"version": ""}, trigger.pr_gate({}, REPO))
        for labels in ([], ["version:7.1"], ["version:8.1.3", "version:7.1"]):
            with self.assertRaises(ValueError):
                trigger.automatic_pr(pr(labels=labels), REPO)

    def test_tag_date_is_pinned_and_same_day_retry_preserves_asset_date(self):
        for tag in ("ffmpeg-8.1.3-261125", "ffmpeg-8.1.3-261125R2", "ffmpeg-8.1.3-261125R10"):
            self.assertEqual(("8.1.3", "2026-11-25"), trigger.parse_tag(tag))
            row = {"version": "8.1.3", "release_date": "2026-11-25", "publication_tag": tag}
            self.assertEqual(tag, record_release_tag(row))
        for invalid in ("ffmpeg-8.1.3", "ffmpeg-master-261132", "ffmpeg-8.1.3-261125R1",
                        "ffmpeg-8.1.3-261125-r2", "ffmpeg-8.1.3-261125R02", "ffmpeg-8.1.3-261125-2", "ffmpeg-8.1.3-261125.2", "ffmpeg-8.1.3-261125r2", "ffmpeg-8.1.3-261125-R2", "ffmpeg-8.1.3-261125-extra"):
            with self.assertRaises(ValueError):
                trigger.parse_tag(invalid)

    def test_upstream_discovery_does_not_backfill_old_versions(self):
        from ffbuild.updates import select_new_versions
        upstream = {(4,4,3),(4,4,8),(4,4,9),(8,1,1),(8,1,3),(8,1,4),
                    (8,2,1),(9,0,2),(9,1,1),(9,2,0),(9,2,1)}
        self.assertEqual(["4.4.9", "8.1.4", "9.1.1", "9.2.1"],
                         select_new_versions(upstream, ["4.4.8","8.1.3","9.0.2","9.1"]))

    def test_catalog_preserves_same_day_retry_tag_and_reuse_identity(self):
        from ffbuild.identity import archive_name, variant_name
        from ffbuild.state import PublishedState
        row = {"version":"8.1.3", "channel":"release", "release_date":"2026-11-25",
               "triplet":"x64-windows","linkage":"static","license":"lgpl",
               "abi_hash":"c"*64,"package_format":3,"expected_variants":1,
               "publication_tag":"ffmpeg-8.1.3-261125R2"}
        row["variant_id"] = variant_name(row["version"],0,row["triplet"],row["linkage"],row["license"],abi_hash=row["abi_hash"])
        row["assets"]={"binary":{"file":archive_name(row),"size":123,"digest":"sha256:"+"d"*64}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            catalog.register_release(root,[row])
            stored=PublishedState(directory=root).find_abi("8.1.3","x64-windows","c"*64)
            self.assertEqual(row["publication_tag"],record_release_tag(stored))
            self.assertEqual(row["assets"],stored["assets"])

    def test_non_tag_cannot_call_production_engine(self):
        env = {"GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "push",
               "TARGET_VERSION": "8.1.3"}
        with self.assertRaises(ValueError):
            trigger.build_gate({}, env)
        with self.assertRaises(ValueError):
            trigger.build_gate({}, dict(env, VALIDATION_ONLY="true", SKIP_PUBLISH="true"))
        with self.assertRaises(ValueError):
            trigger.build_gate({"pull_request": pr(bot=False)},
                dict(env, GITHUB_EVENT_NAME="pull_request", GITHUB_REPOSITORY=REPO,
                     VALIDATION_ONLY="true", SKIP_PUBLISH="true"))
        isolated = dict(env, GITHUB_REF="refs/heads/ci/e2e-test",
                        VALIDATION_ONLY="true", SKIP_PUBLISH="true")
        with self.assertRaisesRegex(ValueError, "Unauthorized native build event"):
            trigger.build_gate({}, isolated)

    def test_dispatch_gate_requires_main_and_one_version_and_never_writes_tags(self):
        env = {"GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
               "TARGET_VERSION": "8.1.3", "GITHUB_SHA": SHA, "GITHUB_RUN_ATTEMPT": "1"}
        payload = {"inputs": {"yaml": "8.1.3"}}
        with patch.object(trigger, "git", return_value=SHA), patch.object(subprocess, "run"), patch.object(trigger, "write_publication_tag") as write:
            selected = trigger.build_gate(payload, env)
            self.assertEqual("true", selected["production"])
            self.assertEqual("8.1.3", selected["version"])
            for extra in ({"GITHUB_REF": "refs/tags/ffmpeg-8.1.3-261125"},
                          {"GITHUB_REF": "refs/heads/feature"}, {"GITHUB_EVENT_NAME": "push"},
                          {"REQUESTED_SHARDS": "2"}, {"REQUESTED_SHARD_INDEX": "1"},
                          {"TARGET_VERSION": "7.1"}, {"REQUESTED_FORCE":"true"},
                          {"GITHUB_EVENT_NAME": "schedule"}):
                with self.assertRaises(ValueError):
                    trigger.build_gate(payload, dict(env, **extra))
            write.assert_not_called()

    def test_weekly_master_pins_source_without_tag(self):
        env = {"GITHUB_REF":"refs/heads/main","GITHUB_EVENT_NAME":"schedule",
               "TARGET_VERSION":"master","GITHUB_SHA":SHA,"GITHUB_RUN_ATTEMPT":"1"}
        pin = {"ref":"n9.1-123-gabcdef0","commit":"b"*40,"sha512":"c"*128}
        with patch.object(trigger,"git",return_value=SHA), patch.object(subprocess,"run"), patch("ffbuild.master.master_metadata",return_value=pin), patch.object(trigger,"write_publication_tag") as write:
            result=trigger.build_gate({},env)
            self.assertEqual("true",result["production"])
            self.assertEqual(pin["commit"],result["commit"])
            write.assert_not_called()

    def test_production_run_uses_exact_prior_master_pin(self):
        env={"GITHUB_REF":"refs/heads/main","GITHUB_EVENT_NAME":"schedule",
             "TARGET_VERSION":"master","GITHUB_SHA":SHA,"GITHUB_RUN_ATTEMPT":"2"}
        prior={"version":"master","date":"2026-11-25","production":"true",
               "ref":"n9.1-123-gabcdef0","commit":"b"*40,"sha512":"c"*128}
        with patch.object(trigger,"git",return_value=SHA), patch.object(subprocess,"run"), patch.object(trigger,"prior_source_pin",return_value=prior), patch("ffbuild.master.master_metadata") as upstream:
            self.assertEqual(prior,trigger.build_gate({},env))
            upstream.assert_not_called()

    def test_production_request_is_bound_to_attempt_plan(self):
        from ffbuild.autoheal.triage import production_request
        request={"yaml":"master","date":"2026-11-25","production":True,
                 "repository_commit":SHA,"ref":"n9.1-123-gabcdef0","commit":"b"*40,"sha512":"c"*128}
        rows=[{"yaml":"master","release_date":request["date"],"ref":request["ref"],
               "source_ref":request["commit"],"sha512":request["sha512"]}]
        run={"name":"Build FFmpeg Master","event":"schedule","head_branch":"main","head_sha":SHA}
        plan={"jobs":rows,"request":request}
        self.assertEqual(request,production_request(run,plan))
        self.assertIsNone(production_request(dict(run,event="push"),plan))
        self.assertIsNone(production_request(dict(run,head_sha="d"*40),plan))
        self.assertIsNone(production_request(run,dict(plan,jobs=[dict(rows[0],source_ref="e"*40)])))

    def test_new_version_pr_history_preserves_initial_proposal(self):
        from ffbuild.autoheal import pr_history, github
        proposal = "b"*40
        repair_sha = "c"*40
        incident = "d"*64
        candidate = pr()
        candidate["head"]["sha"] = proposal
        details = {
            proposal: {"sha":proposal,"author":{"login":trigger.BOT},
                       "commit":{"message":"feat(ffmpeg): propose 8.1.3 build spec"}},
            repair_sha: {"sha":repair_sha,"parents":[{"sha":proposal}],
                         "commit":{"message":f"Autoheal-Round: 1\nAutoheal-Incident: {incident}\nAutoheal-Source-Run: 11\nAutoheal-Source-Attempt: 1"},
                         "files":[{"filename":"ffmpeg/8.1.3.yaml","status":"modified"}]}
        }
        def fake_api(path):
            return details[path.split("/commits/")[1].split("?")[0]]
        with (patch.dict(os.environ,{"GITHUB_REPOSITORY":REPO}), patch.object(github,"api",side_effect=fake_api),
              patch.object(github,"collection",return_value=[{"sha":proposal}]) as listed):
            self.assertEqual([],pr_history.load_new_version_rounds(candidate))
            candidate["head"]["sha"]=repair_sha
            listed.return_value=[{"sha":proposal},{"sha":repair_sha}]
            result=pr_history.load_new_version_rounds(candidate)
            self.assertEqual(1,result[0].number)
            self.assertEqual(incident,result[0].incident)
            details[repair_sha]["parents"]=[{"sha":"e"*40}]
            with self.assertRaisesRegex(ValueError,"linear"):
                pr_history.load_new_version_rounds(candidate)

    def test_full_pr_evidence_requires_every_target_and_successful_job(self):
        rows, blocked = build_requests(version="8.1.3")
        self.assertFalse(blocked)
        for i,row in enumerate(rows):
            row["id"] = "variant-"+str(i)
        jobs = [{"name": "build / ffbuild-"+row["id"], "conclusion":"success"} for row in rows]
        self.assertTrue(trigger.complete_pr_build("8.1.3", rows, jobs))
        self.assertFalse(trigger.complete_pr_build("8.1.3", rows[:-1], jobs))
        jobs[0]["conclusion"] = "skipped"
        self.assertFalse(trigger.complete_pr_build("8.1.3", rows, jobs))

    def test_same_day_publication_tag_allocates_read_only_and_resumes_exact_batch(self):
        calls = []
        batch = "d"*64
        def fake_git(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("ls-remote", "origin") and args[2].endswith("261125"):
                return "b"*40+"\t"+args[2]
            return ""
        with patch.object(trigger,"git",side_effect=fake_git):
            self.assertEqual(("ffmpeg-8.1.3-261125R2",False),
                trigger.publication_tag_candidate("8.1.3","2026-11-25",SHA,batch))
        self.assertTrue(all(call[0] == "ls-remote" for call in calls))
        ref="refs/tags/ffmpeg-8.1.3-261125"
        def existing(*args,**kwargs):
            if args[0]=="ls-remote":
                return "b"*40+"\t"+ref+"\n"+SHA+"\t"+ref+"^{}"
            if args[0]=="for-each-ref":
                return json.dumps({"batch":batch,"repository_commit":SHA})
            return ""
        with patch.object(trigger,"git",side_effect=existing):
            self.assertEqual(("ffmpeg-8.1.3-261125",True),
                trigger.publication_tag_candidate("8.1.3","2026-11-25",SHA,batch))


class ScopeGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "test")
        self.git("config", "user.email", "test@example.invalid")
        self.write("ffmpeg/base.yaml", {"patches": [], "build": {"options": "base"}})
        self.write("ffmpeg/8.1.yaml", {"extends": "base", "patches": []})
        for version in ("8.1.1", "8.1.2", "8.1.3"):
            self.write(f"ffmpeg/{version}.yaml", self.config(version))
        self.write("ffmpeg/master.yaml", {"extends": "base", "source": {"ref":"master"}})
        self.write("patches/8.x/shared.patch", "old patch\n")
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def write(self,path,value):
        p=self.root/path
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(value if isinstance(value,str) else yaml.safe_dump(value),encoding="utf-8")

    def config(self, version, **extra):
        return {"extends":".".join(version.split(".")[:2]), "source": {
            "method":"git", "repo":"ffmpeg/ffmpeg", "ref":"n"+version, "sha512":"a"*128}, **extra}

    def commit(self):
        self.git("add","-A")
        self.git("commit","-qm","candidate")
        return self.git("rev-parse","HEAD")

    def test_worktree_check_before_and_after_commit(self):
        self.write("ffmpeg/8.1.3.yaml", self.config("8.1.3", patches=["8.x/only-813.patch"]))
        self.write("patches/8.x/only-813.patch", "new patch\n")
        allowed = {"ffmpeg/8.1.3.yaml", "patches/8.x/only-813.patch"}
        self.assertEqual(allowed,set(check_worktree("8.1.3", self.base,self.root)))
        self.git("add","-A")
        self.assertEqual(allowed,set(check_worktree("8.1.3", self.base,self.root)))
        head=self.commit()
        self.assertEqual(allowed,set(check_pr("8.1.3",self.base,head,self.root)))

    def test_existing_version_config_and_patch_cannot_change(self):
        self.write("ffmpeg/8.1.3.yaml",self.config("8.1.3",build={"options":"fixed"}))
        self.write("ffmpeg/8.1.2.yaml",self.config("8.1.2",build={"options":"bad"}))
        with self.assertRaisesRegex(ValueError,"Out of scope"):
            check_worktree("8.1.3",self.base,self.root)
        self.git("restore","ffmpeg/8.1.2.yaml")
        self.write("patches/8.x/shared.patch","edited existing")
        with self.assertRaisesRegex(ValueError,"Out of scope"):
            check_worktree("8.1.3",self.base,self.root)

    def test_implicit_family_inheritance_cannot_change_other_versions(self):
        # Even a target that is itself a family must not change children.
        self.write("ffmpeg/8.1.yaml",{"extends":"base","patches":[],"build":{"options":"bad"}})
        with self.assertRaises(ValueError):
            check_worktree("8.1",self.base,self.root)
        self.git("restore","ffmpeg/8.1.yaml")
        self.write("ffmpeg/8.1.4.yaml",self.config("8.1.4"))
        head=self.commit()
        self.assertEqual(["ffmpeg/8.1.4.yaml"],check_pr("8.1.4",self.base,head,self.root,allow_new=True))

    def test_new_family_is_only_allowed_as_an_empty_new_template(self):
        self.write("ffmpeg/9.2.yaml",{"extends":"base","patches":[]})
        self.write("ffmpeg/9.2.1.yaml",self.config("9.2.1"))
        head=self.commit()
        self.assertEqual({"ffmpeg/9.2.yaml","ffmpeg/9.2.1.yaml"},
                         set(check_pr("9.2.1",self.base,head,self.root,allow_new=True)))
        self.write("ffmpeg/9.2.yaml",{"extends":"base","patches":[],"build":{"options":"bad"}})
        bad=self.commit()
        with self.assertRaisesRegex(ValueError,"empty"):
            check_pr("9.2.1",self.base,bad,self.root,allow_new=True)

    def test_staged_reversal_cannot_hide_unauthorized_change(self):
        self.write("ffmpeg/8.1.2.yaml",self.config("8.1.2",build={"options":"bad"}))
        self.git("add","ffmpeg/8.1.2.yaml")
        self.git("restore","--source",self.base,"--worktree","ffmpeg/8.1.2.yaml")
        self.write("ffmpeg/8.1.3.yaml",self.config("8.1.3",build={"options":"good"}))
        with self.assertRaisesRegex(ValueError,"Staged change hidden"):
            check_worktree("8.1.3",self.base,self.root)

    def test_scope_rejects_untracked_script_and_source_change(self):
        self.write("ffmpeg/8.1.3.yaml",self.config("8.1.3",build={"options":"fixed"}))
        self.write("scripts/evil.py","unrelated\n")
        with self.assertRaisesRegex(ValueError,"Out of scope"):
            check_worktree("8.1.3",self.base,self.root)
        (self.root/"scripts/evil.py").unlink()
        config=self.config("8.1.3")
        config["source"]["sha512"]="b"*128
        self.write("ffmpeg/8.1.3.yaml",config)
        with self.assertRaisesRegex(ValueError,"source identity"):
            check_worktree("8.1.3",self.base,self.root)


if __name__ == "__main__":
    unittest.main()
