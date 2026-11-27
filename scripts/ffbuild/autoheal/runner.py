"""Pi session supervisor. Only a clean native build of the candidate can succeed."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import build as native
from .scope import check_worktree


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def configure_pi(directory: Path) -> tuple[list[str], dict]:
    from .api import api_config
    config = api_config()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "models.json").write_text(json.dumps({"providers": {"autoheal": {
        "baseUrl": config.base_url, "api": "openai-responses", "apiKey": "$OPENAI_API_KEY",
        "models": [{"id": config.model, "name": config.model}]
    }}}, indent=2), encoding="utf-8")
    # Use node directly with the npm bin entrypoint, avoiding cmd.exe quoting on Windows.
    package = os.environ.get("FFBUILD_PI_PACKAGE")
    if package:
        root = Path(package)
        meta = json.loads((root / "package.json").read_text(encoding="utf-8"))
        entry = meta["bin"]["pi"] if isinstance(meta["bin"], dict) else meta["bin"]
        executable = root / entry
        if not executable.is_file() or not shutil.which("node"):
            raise ValueError("Pinned Pi installation is incomplete")
        command = ["node", str(executable)]
    else:
        executable = shutil.which("pi")
        if not executable:
            raise ValueError("Pi executable is missing")
        command = [executable]
    env = dict(os.environ)
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
                "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STEP_SUMMARY",
                "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
        env.pop(key, None)
    env["OPENAI_API_KEY"] = config.key
    env["OPENAI_MODEL"] = config.model
    env["PI_CODING_AGENT_DIR"] = str(directory)
    env["PI_CODING_AGENT_SESSION_DIR"] = str(directory / "sessions")
    return command, env


def run_pi(command: list[str], env: dict, prompt: str, *, resume: bool, timeout: float) -> int:
    args = [*command, "--print", "--mode", "json", "--provider", "autoheal",
            "--model", env["OPENAI_MODEL"], "--no-extensions",
            "--extension", str(Path(__file__).with_name("extensions") / "responses.ts"),
            "--no-approve", "--offline",
            "--no-context-files", "--no-skills", "--no-prompt-templates",
            "--tools", "read,write,edit,powershell" if os.name == "nt" else "read,write,edit,bash", *(["--continue"] if resume else [])]
    # The prompt is stdin rather than an argument (Windows length/escaping limits).
    result = subprocess.run(args, env=env, input=prompt, encoding="utf-8", errors="replace",
                            timeout=timeout, check=False, capture_output=True)
    # Keep the session in the private runtime directory. Do not emit raw tool arguments
    # or provider responses to the public CI log.
    log = Path(env["PI_CODING_AGENT_DIR"]) / "last-events.jsonl"
    key = env["OPENAI_API_KEY"]
    log.write_text((result.stdout or "").replace(key, "[redacted]"), encoding="utf-8")
    log.with_name("last-stderr.log").write_text((result.stderr or "").replace(key, "[redacted]"), encoding="utf-8")
    # Pi can exit normally even when the model response failed. Require a completed turn.
    events = []
    for line in (result.stdout or "").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    completed = any(event.get("type") == "agent_end" and any(
        msg.get("role") == "assistant" and msg.get("stopReason") in ("stop", "toolUse")
        for msg in event.get("messages", [])[-1:]) for event in events if isinstance(event, dict))
    if not result.returncode and not completed:
        print("Pi did not complete a Responses turn", flush=True)
        return 1
    if result.returncode:
        print(f"Pi exited with status {result.returncode}", flush=True)
    return result.returncode


def _declined(base: str) -> bool:
    report = Path("fix_report.md")
    if not report.is_file() or report.is_symlink() or report.stat().st_size > 65536:
        return False
    if not re.search(r"(?m)^Decision: no_safe_fix[ \t]*$", report.read_text(encoding="utf-8")):
        return False
    return git("rev-parse", "HEAD") == base and not git("status", "--porcelain", "--untracked-files=no")


def supervise(*, budget: float) -> int:
    data = native.context()
    base, target = data["base_sha"], data["target_yaml"]
    root = Path.cwd()
    if git("rev-parse", "HEAD") != base or git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Repair must start on the exact clean failed source")
    directory = native.runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "verification.json").unlink(missing_ok=True)
    command, env = configure_pi(directory / "pi")
    prompt = Path("scripts/ffbuild/autoheal/prompts/repair.md").read_text(encoding="utf-8")
    deadline = time.monotonic() + budget
    resume = False
    agent_failures = 0
    while time.monotonic() < deadline:
        try:
            rc = run_pi(command, env, prompt, resume=resume, timeout=deadline - time.monotonic())
        except subprocess.TimeoutExpired:
            print("Repair budget exhausted", flush=True)
            return 4
        resume = True
        if rc:
            agent_failures += 1
            if agent_failures >= 3:
                return 6
            prompt = "The last Pi invocation failed. Continue the same incident if possible."
            continue
        agent_failures = 0
        try:
            if _declined(base):
                if check_worktree(target, base, root, allow_empty=True):
                    raise ValueError("A declined repair cannot leave candidate changes")
                return 3
            paths = check_worktree(target, base, root)
            plan_file = Path("validation-plan.json")
            if not plan_file.is_file() or plan_file.is_symlink() or plan_file.stat().st_size > 65536:
                raise ValueError("Missing bounded validation-plan.json")
            raw = json.loads(plan_file.read_text(encoding="utf-8"))
            plan = native.validate_plan(raw, data)
            # Keep the candidate available to the Agent on failure. The final commit
            # is made only after independently rebuilding its exact staged tree.
            if git("rev-parse", "HEAD") != base:
                git("reset", "--soft", base)
            git("add", "--", *paths)
            git("diff", "--cached", "--check")
            tree = git("write-tree")
            if git("diff", "--name-only"):
                raise ValueError("Candidate has unstaged tracked modifications")
            results = []
            for item in plan:
                if time.monotonic() >= deadline:
                    return 4
                result = native.build(item["spec"], clean=True)
                results.append(dict(result, jobs=item["jobs"], reason=item["reason"]))
            if time.monotonic() >= deadline:
                return 4
            if (git("write-tree") != tree or git("diff", "--name-only")
                    or set(check_worktree(target, base, root)) != set(paths)):
                raise ValueError("Candidate changed during independent verification")
            report = Path("fix_report.md")
            if not report.is_file() or report.is_symlink() or report.stat().st_size > 65536:
                raise ValueError("Missing bounded fix_report.md")
            summary = report.read_text(encoding="utf-8")
            if not re.search(r"(?m)^Root cause:\s*\S", summary):
                raise ValueError("Report must include Root cause")
            native.validate_evidence({"schema": 1, "candidate": base, "tree": tree, "checks": results}, data)
            git("-c", "user.name=ffmpeg-dev[bot]", "-c", "user.email=ffmpeg-dev@users.noreply.github.com",
                "-c", "commit.gpgsign=false", "commit", "-m", f"fix({target}): repair native FFmpeg build")
            candidate = git("rev-parse", "HEAD")
            evidence = {"schema": 1, "candidate": candidate, "tree": tree, "checks": results}
            (directory / "verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            return 0
        except native.EnvironmentFailure as exc:
            print(f"Repair environment failed: {exc}", flush=True)
            return 5
        except (native.BuildFailure, ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
            # An Agent exit is never the success criterion. Resume with actual feedback.
            prompt = ("The independent verification failed. Continue modifying the same candidate; "
                      "do not disable features or change tests.\n" + str(exc)[-4000:])
            print(prompt, flush=True)
    return 4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-seconds", type=int, default=10800)
    args = parser.parse_args()
    if args.budget_seconds <= 0:
        parser.error("Budget must be positive")
    raise SystemExit(supervise(budget=args.budget_seconds))


if __name__ == "__main__":
    main()
