"""Independent audit: real Git replay, local Responses HTTP, fail-closed delivery."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from ffbuild.autoheal import audit, delivery, triage
from ffbuild.autoheal.api import api_config, APIConfig
from ffbuild.versions import ROOT
from test_autoheal import artifact, job, plan_row, run_data, SOURCE_LOG, ABI, SHA

APPROVE = {"decision": "approve", "summary": "Reviewed", "findings": [], "limitations": []}
REJECT = {"decision": "reject", "summary": "Behavior removed", "findings": [
    {"severity": "high", "location": "libavcodec/example.c:42",
     "description": "Initialization is bypassed", "remediation": "Preserve initialization"}
], "limitations": []}
INCONCLUSIVE = {"decision": "inconclusive", "summary": "Missing context", "findings": [], "limitations": ["Missing source"]}


def report_for(base=SHA):
    row = dict(plan_row(), package="ffmpeg[all-gpl]", port="ffmpeg", tester_port="ffmpeg-tester",
               license="gpl", linkage="shared")
    value = triage.analyze(dict(run_data(), head_sha=base), 1, [job(row)], [artifact(row)],
                           {"jobs": [row]}, logs={artifact(row)["name"]: SOURCE_LOG})
    value["trusted_repair_source"] = True
    return value


def write_candidate(directory, report, patch=None, candidate="d"*40, tree="e"*40):
    directory.mkdir(parents=True, exist_ok=True)
    patch = patch if patch is not None else f"From {candidate} Mon Sep 17 00:00:00 2001\n\ndiff --git a/x b/x\n".encode()
    (directory/"repair.patch").write_bytes(patch)
    group = report["groups"][0]
    manifest = {"schema": 2, "yaml": "8.1.1", "signature": group["signature"],
        "run_id": report["source"]["run_id"], "run_attempt": 1,
        "base_sha": report["source"]["head_sha"], "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "paths": ["ffmpeg/8.1.1.yaml"], "validation": {"schema": 1, "candidate": candidate, "tree": tree,
        "checks": [{"spec":"ffmpeg[all-gpl]:x64-windows", "jobs":[group["jobs"][0]["job_id"]],
                   "reason":"same diagnostic", "abi_hash":ABI, "ffmpeg_build":"passed",
                   "consumer_compile_link":"passed", "binary_inspection":"passed",
                   "external_dependency_builds":0, "tester_targets":{"release":39,"debug":39},
                   "runtime":{"status":"passed","tester_executions":78,"cli_executions":2}}]}}
    (directory/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    return manifest


def write_verdict(directory, binding, verdict):
    audit.write_record(directory, {"schema":1,"binding":binding,"model":"audit-test","response_id":"resp_test",
                                  "decision":verdict["decision"],"verdict":verdict})


class AuditGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.candidate, self.output = root/"candidate", root/"audit"
        self.report = report_for()
        self.manifest = write_candidate(self.candidate, self.report)
        self.binding, _, _ = audit.candidate_identity(self.report,"8.1.1",self.candidate)

    def verify(self):
        return audit.verify_delivery(self.report,"8.1.1",self.candidate,self.output)

    def test_approve_and_exact_binding(self):
        write_verdict(self.output,self.binding,APPROVE)
        self.assertTrue(self.verify())
        # Even a whitespace change to the manifest invalidates approval.
        path=self.candidate/"manifest.json"
        path.write_bytes(path.read_bytes()+b"\n")
        with self.assertRaisesRegex(ValueError,"does not match"):
            self.verify()

    def test_reject_inconclusive_missing_and_forged_block_writer(self):
        with mock.patch.object(delivery,"find_pr") as find, mock.patch.object(delivery,"run") as run, \
             mock.patch.object(delivery.github,"api") as api:
            with self.assertRaises(ValueError):
                delivery.deliver(self.report,"8.1.1",self.candidate,self.output)
            for verdict in (REJECT,INCONCLUSIVE):
                write_verdict(self.output,self.binding,verdict)
                with self.assertRaisesRegex(ValueError,"did not approve"):
                    delivery.deliver(self.report,"8.1.1",self.candidate,self.output)
            for key in ("patch_sha256","candidate_tree","manifest_sha256","base_sha","run_id","run_attempt","signature"):
                write_verdict(self.output,dict(self.binding,**{key:"forged"}),APPROVE)
                with self.assertRaisesRegex(ValueError,"does not match"):
                    delivery.deliver(self.report,"8.1.1",self.candidate,self.output)
            find.assert_not_called()
            run.assert_not_called()
            api.assert_not_called()

    def test_modified_patch_rejected(self):
        write_verdict(self.output,self.binding,APPROVE)
        patch=self.candidate/"repair.patch"
        patch.write_bytes(patch.read_bytes()+b"\n")
        with self.assertRaises(ValueError):
            self.verify()

    def test_safe_decline_does_not_call_api(self):
        (self.candidate/"repair.patch").unlink()
        manifest={key:self.manifest[key] for key in ("yaml","signature","run_id","run_attempt","base_sha")}
        manifest.update(schema=1,decision="no_safe_fix")
        (self.candidate/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
        with mock.patch.object(audit,"responses") as call:
            audit.audit(self.report,"8.1.1",self.candidate,self.output)
            call.assert_not_called()
        self.assertFalse(self.verify())

    def test_invalid_approval_with_findings(self):
        with self.assertRaises(ValueError):
            audit.validate_verdict(dict(REJECT,decision="approve"))
        with self.assertRaises(ValueError):
            audit.validate_verdict({"decision":"approve"})
        with self.assertRaises(ValueError):
            audit.validate_verdict(dict(APPROVE,findings="none"))


class AuditProtocol(unittest.TestCase):
    def test_default_and_override_config(self):
        with mock.patch.dict(os.environ,{"OPENAI_API_KEY":"test","OPENAI_MODEL":"repair","OPENAI_AUDIT_MODEL":"audit"},clear=True):
            self.assertEqual("https://api.openai.com/v1",api_config().base_url)
            self.assertEqual("repair",api_config().model)
            self.assertEqual("audit",api_config(audit=True).model)
        for url in ("http://example.com/v1","https://user:pass@example.com/v1","https://example.com/v1/responses","https://example.com/v1?q=x"):
            with mock.patch.dict(os.environ,{"OPENAI_BASE_URL":url,"OPENAI_API_KEY":"test","OPENAI_MODEL":"model"},clear=True):
                with self.assertRaises(ValueError):
                    api_config()

    def test_real_git_replay_and_responses_http(self):
        requests=[]
        def response(output,n):
            return {"id":f"resp_{n}","status":"completed","output":output}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path,self.headers.get("Authorization"),body))
                if len(requests)==1:
                    result=response([
                        {"type":"web_search_call","id":"ws_test","status":"completed","action":{"type":"search","query":"mock"}},
                        {"type":"function_call","id":"fc_test","call_id":"read1","name":"read_context","status":"completed",
                         "arguments":json.dumps({"source":"candidate","path":"ffmpeg/8.1.1.yaml","start_line":1,"end_line":300})}],1)
                else:
                    result=response([{"type":"message","role":"assistant","content":[{"type":"output_text","text":json.dumps(APPROVE)}]}],2)
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {
                    "OPENAI_BASE_URL":f"http://127.0.0.1:{server.server_port}/v1",
                    "OPENAI_API_KEY":"local-test-only","OPENAI_MODEL":"repair-model","OPENAI_AUDIT_MODEL":"audit-model"}):
                root=Path(temp)/"repo"
                root.mkdir()
                def git(*args):
                    return subprocess.check_output(["git",*args],cwd=root,text=True,encoding="utf-8").strip()
                git("init","-q")
                git("config","user.name","Test")
                git("config","user.email","test@example.invalid")
                git("config","commit.gpgsign","false")
                shutil.copytree(ROOT/"ffmpeg",root/"ffmpeg")
                shutil.copytree(ROOT/"patches",root/"patches")
                git("add",".")
                git("commit","-qm","baseline")
                base=git("rev-parse","HEAD")
                git("remote","add","origin",str(root))
                file=root/"ffmpeg/8.1.1.yaml"
                with file.open("a",encoding="utf-8") as stream:
                    stream.write("\n# audit regression fixture\n")
                git("add","ffmpeg/8.1.1.yaml")
                git("commit","-qm","test candidate")
                candidate=git("rev-parse","HEAD")
                tree=git("rev-parse","HEAD^{tree}")
                patch=subprocess.check_output(["git","format-patch","-1","--stdout","--binary"],cwd=root)
                git("reset","--hard",base)
                report=report_for(base)
                directory=Path(temp)/"repair"
                output=Path(temp)/"audit"
                write_candidate(directory,report,patch,candidate,tree)
                audit.audit(report,"8.1.1",directory,output,root=root)
                self.assertTrue(audit.verify_delivery(report,"8.1.1",directory,output))
                self.assertEqual(base,git("rev-parse","HEAD"))
                self.assertEqual("",git("status","--porcelain"))
                self.assertEqual(2,len(requests))
                for path,authorization,body in requests:
                    self.assertEqual("/v1/responses",path)
                    self.assertEqual("Bearer local-test-only",authorization)
                    self.assertEqual("audit-model",body["model"])
                    self.assertFalse(body["store"])
                    self.assertIn({"type":"web_search"},body["tools"])
                    self.assertEqual({"web_search","function"},{item["type"] for item in body["tools"]})
                    self.assertTrue(body["text"]["format"]["strict"])
                self.assertTrue(any("audit regression fixture" in item.get("output","")
                                    for item in requests[1][2]["input"] if item.get("type")=="function_call_output"))
                self.assertEqual(1,sum(item.get("type")=="function_call_output" for item in requests[1][2]["input"]))
                # An altered tree with a matching manifest digest is still refused before model invocation.
                manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
                manifest["validation"]["tree"]="f"*40
                (directory/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
                with self.assertRaisesRegex(ValueError,"tree differs"):
                    audit.audit(report,"8.1.1",directory,output,root=root)
                self.assertEqual(2,len(requests))
        finally:
            server.shutdown()
            server.server_close()

    def test_refusal_or_incomplete_never_approve(self):
        cfg=APIConfig("https://example.invalid/v1","test","model")
        ctx=mock.Mock()
        ctx.read_failed=False
        for output in ([],[{"type":"message","role":"assistant","content":[{"type":"refusal","refusal":"no"}]}],
                       [{"type":"function_call","call_id":"bad","name":"powershell","arguments":"{}"}]):
            with mock.patch.object(audit,"responses",return_value={"id":"test","output":output}):
                with self.assertRaises(ValueError):
                    audit.review(cfg,"test",ctx)
        ctx.read.assert_not_called()

    def test_context_path_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            ctx=audit.Context(root,root,{},root,SHA,root)
            for path in ("../secret","/etc/passwd","ffmpeg/../../secret","C:/secret",".git/config","secret.txt"):
                with self.assertRaises(ValueError):
                    ctx.read({"source":"baseline","path":path,"start_line":1,"end_line":10})
            with self.assertRaises(ValueError):
                ctx.read({"source":"upstream","path":"configure","start_line":1,"end_line":1000})


class WorkflowAudit(unittest.TestCase):
    def test_delivery_needs_successful_audit_before_token(self):
        import yaml
        jobs=yaml.safe_load((ROOT/".github/workflows/auto-heal.yml").read_text(encoding="utf-8"))["jobs"]
        self.assertEqual("ubuntu-latest",jobs["audit"]["runs-on"])
        self.assertEqual("read",jobs["audit"]["permissions"]["contents"])
        self.assertIn("audit",jobs["deliver"]["needs"])
        self.assertIn("needs.audit.result == 'success'",jobs["deliver"]["if"])
        steps=jobs["deliver"]["steps"]
        gate=next(i for i,s in enumerate(steps) if s.get("id")=="gate")
        token=next(i for i,s in enumerate(steps) if s.get("id")=="bot")
        self.assertLess(gate,token)
        self.assertIn("steps.gate.outputs.approved == 'true'",steps[token]["if"])
        self.assertFalse(any("create-github-app-token" in s.get("uses","") for s in jobs["audit"]["steps"]))
