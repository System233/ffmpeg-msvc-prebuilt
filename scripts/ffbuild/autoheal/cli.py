"""CLI contracts; each operation has the least privilege needed."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import yaml

from . import triage
from .models import validate_triage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ffbuild autoheal")
    commands = parser.add_subparsers(dest="action", required=True)
    read = commands.add_parser("triage", help="Read a completed CI run and classify failures")
    read.add_argument("--run-id", type=int, required=True)
    read.add_argument("--attempt", type=int)
    read.add_argument("--output", type=Path, default=Path("autoheal-triage.json"))
    read.add_argument("--github-output", action="store_true")
    inspect = commands.add_parser("inspect", help="Inspect a saved triage report")
    inspect.add_argument("--triage", type=Path, required=True)
    repair = commands.add_parser("repair", help="Generate a version-scoped candidate patch")
    repair.add_argument("--triage", type=Path, required=True)
    repair.add_argument("--yaml", required=True)
    repair.add_argument("--output", type=Path, default=Path("repair-output"))
    deliver = commands.add_parser("deliver", help="Validate, push and synchronize a bot PR")
    deliver.add_argument("--triage", type=Path, required=True)
    deliver.add_argument("--yaml", required=True)
    deliver.add_argument("--output", type=Path, default=Path("repair-output"))
    impacts = commands.add_parser("impacts-master", help="Does a PR affect the master YAML?")
    impacts.add_argument("--base", required=True)
    impacts.add_argument("--head", required=True)
    check = commands.add_parser("check-pr", help="Validate a bot PR total file scope")
    check.add_argument("--yaml", required=True)
    check.add_argument("--base", required=True)
    check.add_argument("--head", required=True)
    commands.add_parser("check-worktree", help="Check the current Agent candidate against its bound version and base")
    sync = commands.add_parser("sync-pr", help="Synchronize bot PR message with CI result")
    sync.add_argument("--triage", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.action == "triage":
        report = triage.triage_run(args.run_id, args.attempt)
        triage.write_json(args.output, report)
        if args.github_output:
            path = os.environ.get("GITHUB_OUTPUT")
            if not path:
                raise ValueError("GITHUB_OUTPUT is required")
            with open(path, "a", encoding="utf-8") as output:
                output.write("matrix=" + json.dumps(report["repair_matrix"], separators=(",", ":")) + "\n")
                output.write("has_repairs=" + str(bool(report["repair_matrix"])).lower() + "\n")
                bot = (report["pr"] if report.get("pr") and
                       report["pr"]["author"] == "ffmpeg-dev[bot]" and
                       report.get("automatic_version_pr") else None)
                output.write("bot_pr=" + str(bot["number"] if bot else "") + "\n")
                output.write("bot_branch=" + (bot["head"] if bot else "") + "\n")
                output.write("bot_target=" + ((bot["head"].split("/")[1] if bot["head"].startswith("autoheal/") else bot["head"].removeprefix("auto/ffmpeg-")) if bot else "") + "\n")
        print(json.dumps({"groups": len(report["groups"]), "repairable": len(report["repair_matrix"]),
                          "run_id": args.run_id}))
    elif args.action == "impacts-master":
        from ..planner import changed_paths, impacted_versions
        print(str(bool(impacted_versions(changed_paths(args.base, args.head), ["master"]))).lower())
    elif args.action == "check-worktree":
        from .scope import check_worktree
        from ..versions import ROOT
        try:
            context = json.loads(Path("agent_context.json").read_text(encoding="utf-8"))
            # The supervising runner sets the authoritative target and base.
            target = os.environ["FFBUILD_REPAIR_TARGET"]
            base = os.environ["FFBUILD_REPAIR_BASE"]
            if context.get("target_yaml") != target or context.get("base_sha") != base:
                raise ValueError("Agent context differs from the supervised repair scope")
            paths = check_worktree(target, base, ROOT)
            print(json.dumps({"ok": True, "target": target, "paths": paths}))
        except (ValueError, KeyError, OSError, yaml.YAMLError, subprocess.CalledProcessError) as exc:
            print(json.dumps({"ok": False, "violations": [str(exc)]}, ensure_ascii=False))
            raise SystemExit(1)
    elif args.action == "check-pr":
        from .scope import check_pr
        from ..versions import ROOT
        print("Verified PR files:", check_pr(args.yaml, args.base, args.head, ROOT))
    else:
        report = json.loads(args.triage.read_text(encoding="utf-8"))
        if args.action == "inspect":
            print(json.dumps(report, indent=2, ensure_ascii=False))
        elif args.action == "repair":
            if not report.get("trusted_repair_source"):
                raise ValueError("Untrusted source cannot execute Repair")
            validate_triage(report, args.yaml)
            from .repair import repair
            repair(report, args.yaml, args.output)
        elif args.action == "deliver":
            if not report.get("trusted_repair_source"):
                raise ValueError("Untrusted source cannot execute Delivery")
            validate_triage(report, args.yaml)
            from .delivery import deliver
            deliver(report, args.yaml, args.output)
        elif args.action == "sync-pr":
            from .delivery import sync_status
            sync_status(report)
