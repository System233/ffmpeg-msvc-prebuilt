"""Opt-in actual pinned Pi protocol test with a loopback Responses server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from ffbuild.autoheal import runner


@unittest.skipUnless(os.environ.get("FFBUILD_TEST_PI_PACKAGE"), "Set FFBUILD_TEST_PI_PACKAGE to installed Pi")
class PiResponsesIntegration(unittest.TestCase):
    def test_search_tool_execution_and_resume(self):
        requests = []
        tool_name = "powershell" if os.name == "nt" else "bash"
        tool_command = "Write-Output 'responses-native-tool-ok'" if os.name == "nt" else "printf 'responses-native-tool-ok'"
        source_url = "https://ffmpeg.org/documentation.html"

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, body, self.headers.get("Authorization")))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                n = len(requests)
                resp = {"id": f"resp_{n}", "object": "response", "created_at": 1, "status": "completed",
                        "model": "test-model", "output": [], "usage": {"input_tokens": 10, "output_tokens": 10,
                        "total_tokens": 20, "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}}
                if n == 1:
                    search = {"type": "web_search_call", "id": "ws_1", "status": "completed",
                              "action": {"type": "search", "query": "FFmpeg docs", "sources": [{"type": "url", "url": source_url}]}}
                    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": tool_name,
                            "arguments": json.dumps({"command": tool_command, "timeout": 30}), "status": "completed"}
                    items = [search, call]
                else:
                    items = [{"type": "message", "id": f"msg_{n}", "role": "assistant", "status": "completed",
                              "content": [{"type": "output_text", "text": "verified response",
                                "annotations": [{"type": "url_citation", "url": source_url, "title": "FFmpeg", "start_index": 0, "end_index": 8}]}]}]
                sequence = 0

                def send(kind, **fields):
                    nonlocal sequence
                    sequence += 1
                    obj = {"type": kind, "sequence_number": sequence, **fields}
                    self.wfile.write(("event: " + kind + "\ndata: " + json.dumps(obj) + "\n\n").encode())

                send("response.created", response=dict(resp, status="in_progress"))
                for i, item in enumerate(items):
                    if item["type"] == "function_call":
                        send("response.output_item.added", output_index=i, item=dict(item, arguments="", status="in_progress"))
                        send("response.function_call_arguments.delta", output_index=i, item_id=item["id"], delta=item["arguments"])
                        send("response.function_call_arguments.done", output_index=i, item_id=item["id"], arguments=item["arguments"])
                    elif item["type"] == "message":
                        send("response.output_item.added", output_index=i, item=dict(item, content=[], status="in_progress"))
                        send("response.content_part.added", output_index=i, item_id=item["id"], content_index=0,
                             part={"type": "output_text", "text": "", "annotations": []})
                        send("response.output_text.delta", output_index=i, item_id=item["id"], content_index=0, delta="verified response")
                        send("response.output_text.annotation.added", output_index=i, item_id=item["id"], content_index=0,
                             annotation_index=0, annotation=item["content"][0]["annotations"][0])
                        send("response.output_text.done", output_index=i, item_id=item["id"], content_index=0, text="verified response")
                        send("response.content_part.done", output_index=i, item_id=item["id"], content_index=0, part=item["content"][0])
                    else:
                        send("response.output_item.added", output_index=i, item=dict(item, status="in_progress"))
                    send("response.output_item.done", output_index=i, item=item)
                send("response.completed", response=dict(resp, output=items))
                self.wfile.write(b"data: [DONE]\n\n")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
                "OPENAI_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                "OPENAI_API_KEY": "local-test-only", "OPENAI_MODEL": "test-model",
                "FFBUILD_PI_PACKAGE": os.environ["FFBUILD_TEST_PI_PACKAGE"],
            }):
                old = Path.cwd()
                directory = Path(tmp) / "pi"
                os.chdir(tmp)
                try:
                    command, env = runner.configure_pi(directory)
                    for i in range(2):
                        rc = runner.run_pi(command, env, "test prompt " + str(i), resume=bool(i), timeout=30)
                        diagnostic = "\n".join((directory / name).read_text(encoding="utf-8")[-3500:]
                                               for name in ("last-stderr.log", "last-events.jsonl"))
                        self.assertEqual(0, rc, diagnostic)
                    self.assertEqual(3, len(requests))
                    for path, body, authorization in requests:
                        self.assertEqual("/v1/responses", path)
                        self.assertEqual("Bearer local-test-only", authorization)
                        self.assertIn({"type": "web_search"}, body["tools"])
                        self.assertFalse(body["store"])
                    self.assertTrue(any("responses-native-tool-ok" in str(m) for m in requests[1][1]["input"]))
                    self.assertTrue(any("test prompt 0" in str(m) for m in requests[2][1]["input"]))
                    self.assertFalse((directory / "search-evidence.jsonl").exists())
                finally:
                    os.chdir(old)
        finally:
            server.shutdown()
            server.server_close()
