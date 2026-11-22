"""GitHub event data is input, not orchestration logic in YAML."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def event_options(environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    event_path = env.get("GITHUB_EVENT_PATH", "")
    payload: dict[str, Any] = {}
    if event_path:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    event = env.get("GITHUB_EVENT_NAME", "")
    inputs = payload.get("inputs") or {}
    options: dict[str, Any] = {
        "mode": "all", "base": "", "head": "", "force": False,
        "version": str(inputs.get("version") or inputs.get("yaml") or ""),
        "ref": str(inputs.get("ref") or ""),
        "sha512": str(inputs.get("sha512") or ""),
        "history": str(inputs.get("history", "")).lower() in ("true", "1"),
        "shard_count": int(inputs.get("shard_count") or 1),
        "shard_index": int(inputs.get("shard_index") or 0),
        "include_master": False,
    }
    if event == "pull_request":
        pr = payload["pull_request"]
        options.update({
            "mode": "changed", "base": pr["base"]["sha"],
            "head": pr["head"]["sha"], "force": True, "include_master": True,
        })
    elif event == "push":
        options.update({
            "mode": "changed",
            "base": str(payload.get("before") or ""),
            "head": str(payload.get("after") or env.get("GITHUB_SHA", "")),
        })
    if str(inputs.get("force", "")).lower() in ("true", "1"):
        options["force"] = True
    if options["version"]:
        # A targeted manual build does not need Git change analysis.
        options["mode"] = "all"
    return options
