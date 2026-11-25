"""Presentation contracts; no remote writes or compiler needed."""
import os
import re
import unittest
from unittest.mock import patch

from ffbuild.messages import release_message, proposal_message, proposal_status, proposal_pending, repair_title
from ffbuild.autoheal import pr_history
from ffbuild.autoheal.ledger import RepairRound, RepairEvent

SHA = "a" * 40
SIG = "b" * 64
REPO = "example/ffmpeg"

class MessageTests(unittest.TestCase):
    def test_release_uses_actual_matrix_and_batch_title(self):
        rows = [{"triplet":a+"-windows","linkage":link,"license":lic,
                 "assets":{"binary":{}, **({"develop":{}} if link=="shared" else {})}}
                for a in ("x86","x64","arm","arm64") for link in ("static","shared")
                for lic in ("lgpl","gpl")]
        title, body = release_message("ffmpeg-8.1.3-261125R2","8.1.3",records=rows,
                                      repo=REPO,run_id="100",attempt="2")
        self.assertEqual("FFmpeg 8.1.3 (MSVC Prebuilt) — 2026-11-25 R2",title)
        for text in ("Static","Shared","Develop","x86, x64, ARM, ARM64","LGPL / GPL","SPDX",
                     "/FFmpeg/FFmpeg/tree/n8.1.3","/actions/runs/100/attempts/2"):
            self.assertIn(text,body)
        self.assertNotIn(".zip",body)
        title, body = release_message("ffmpeg-master-261125","9.1-dev-123-gabcdef0",snapshot=True,
                                      records=[dict(rows[0],source_commit=SHA)])
        self.assertIn("Master",title)
        self.assertIn("/commit/"+SHA,body)
        self.assertNotIn("| Develop |",body)
        self.assertNotIn("| Shared |",body)

    def test_proposal_updates_only_verification_and_never_overstates_ci(self):
        body = "Maintainer note\n"+proposal_message("8.1.3","8.1",["ffmpeg/8.1.3.yaml"])
        self.assertIn("/tree/n8.1.3",body)
        self.assertIn("Awaiting",body)
        source={"run_id":20,"run_attempt":2,"head_sha":SHA,"run_conclusion":"success"}
        pending = proposal_status(body,source,False,REPO)
        self.assertNotIn("16/16 passed",pending)
        passed = proposal_status(body,source,True,REPO)
        self.assertIn("16/16 passed",passed)
        self.assertTrue(passed.startswith("Maintainer note"))
        self.assertEqual(passed,proposal_status(passed,dict(source,run_attempt=1,run_conclusion="failure"),False,REPO))
        self.assertEqual(passed,proposal_status(passed,source,True,REPO))

    def test_repaired_proposal_marks_new_head_pending(self):
        original=proposal_message("8.1.3","8.1",["ffmpeg/8.1.3.yaml"])
        source={"run_id":20,"run_attempt":1,"head_sha":SHA,"run_conclusion":"failure"}
        failed=proposal_status(original,source,False,REPO)
        pending=proposal_pending(failed,source,"c"*40,REPO)
        self.assertIn("awaiting the full MSVC build matrix for the new PR HEAD",pending)
        self.assertIn("Previous CI:",pending)
        self.assertNotIn("CI failed.",pending)
        self.assertNotIn("16/16 passed",pending)
        self.assertIn("/commit/"+"c"*40,pending)
        self.assertEqual("Manual text",proposal_pending("Manual text",source,"c"*40,REPO))
        final=proposal_status(pending,dict(source,head_sha="c"*40,run_id=21,run_conclusion="success"),True,REPO)
        self.assertIn("16/16 passed",final)
        self.assertNotIn("Previous CI:",final)

    def test_repair_title_validates_target_and_falls_back(self):
        self.assertEqual("fix(master): adapt AMF version requirement",repair_title("master","fix(master): adapt AMF version requirement"))
        for bad in ("fix(8.1): bad","fix(master): @someone","fix(master): fake\nsecond line","fix(master): 中文"):
            self.assertEqual("fix(master): repair failed MSVC build",repair_title("master",bad))

    def test_history_preserves_hidden_ledger_and_old_format(self):
        first=RepairRound(1,SHA,SIG,100,1,("ffmpeg/master.yaml",),"AMF mismatch | hypothesis","fix(master): adapt AMF requirement")
        event=RepairEvent("ci",1,SHA,SIG,101,1,"failure")
        with patch.dict(os.environ,{"GITHUB_REPOSITORY":REPO}):
            body=pr_history.render_history([first],[event],report={"groups":[{"yaml":"master","jobs":[{"abi_hash":"c"*64,"diagnostic":"raw error text"}]}]})
            visible=re.sub(r"<!--.*?-->","",body)
            self.assertNotIn(SIG,visible)
            self.assertNotIn("c"*64,visible)
            self.assertNotIn("raw error text",visible)
            self.assertIn("Adapt AMF requirement",visible)
            self.assertIn("AMF mismatch &#124; hypothesis",visible)
            self.assertEqual(SIG,pr_history.incident_from_pr_body(body))
            old=pr_history.START+"\n**Incident signature:** "+SIG+"\n"+pr_history.END
            self.assertEqual(SIG,pr_history.incident_from_pr_body(old))
            comment=pr_history.event_comment(event)
            self.assertNotIn("Event key:",comment)
            self.assertEqual(event,pr_history.parse_event({"user":{"login":pr_history.BOT},"body":comment},SIG,[first]))

if __name__ == "__main__":
    unittest.main()
