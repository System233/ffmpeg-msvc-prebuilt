"""Privileged writer: validates untrusted candidate patches and synchronizes bot PR messages."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from . import github
from .ledger import RepairRound, branch_name, branch_matches, next_round
from . import pr_history
from .models import commit_sha, validate_triage
from ..release_trigger import automatic_pr, ensure_label
from .scope import validate_changes, check_worktree, check_pr
from ..messages import repair_title, proposal_status, proposal_pending

START = pr_history.START
END = pr_history.END
BOT = pr_history.BOT


def run(*command: str, cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed: {result.stderr[-1000:]}")
    return result.stdout.strip()


def git(*args: str, cwd: Path | None = None) -> str:
    return run("git", "-c", "core.hooksPath=/dev/null", *args, cwd=cwd)


def changes(worktree: Path) -> list[tuple[str, str]]:
    rows = git("diff", "--cached", "--name-status", "--no-renames", cwd=worktree)
    result = []
    for row in rows.splitlines():
        parts = row.split("\t")
        if len(parts) != 2:
            raise ValueError("Unexpected git index delta")
        result.append((parts[0], parts[1]))
    return result


def check_modes(worktree: Path) -> None:
    for row in git("diff", "--cached", "--raw", "--no-abbrev", cwd=worktree).splitlines():
        columns = row.split("\t", 1)[0].split()
        if len(columns) < 5 or columns[1] != "100644":
            raise ValueError("Only non-executable regular files may be committed")


def find_pr(branch: str) -> dict | None:
    owner = github.repository().split("/", 1)[0]
    rows = github.api(f"repos/{github.repository()}/pulls?head={owner}:{branch}&state=all&per_page=100")
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError("Ambiguous repair PR branch")
    return rows[0] if rows else None


def verify_pr(pr: dict, branch: str) -> None:
    if pr.get("user", {}).get("login") != BOT:
        raise ValueError("Repair branch belongs to a non-bot author")
    if pr.get("head", {}).get("ref") != branch or pr.get("base", {}).get("ref") != "main":
        raise ValueError("Unexpected PR branch or base")
    if pr.get("head", {}).get("repo", {}).get("full_name", "").lower() != github.repository().lower():
        raise ValueError("Repair PR is from an untrusted repository")
    if pr.get("state") != "open":
        raise ValueError("Repair PR is no longer open")


def update_body(existing: str, replacement: str) -> str:
    """Preserve user-written PR content outside the owned managed section."""
    if START not in existing and END not in existing:
        if existing.strip():
            raise ValueError("Existing PR has no managed body section")
        return replacement
    if existing.count(START) != 1 or existing.count(END) != 1:
        raise ValueError("Malformed managed PR section")
    a = existing.index(START)
    b = existing.index(END) + len(END)
    if b < a:
        raise ValueError("Reversed PR section markers")
    return existing[:a] + replacement + existing[b:]


def write_pr_body(number: int, body: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                     suffix=".md", delete=False) as f:
        f.write(body)
        path = Path(f.name)
    try:
        run("gh", "pr", "edit", str(number), "--repo", github.repository(),
            "--body-file", str(path))
    finally:
        path.unlink(missing_ok=True)


def post_comment(number: int, message: str) -> None:
    run("gh", "pr", "comment", str(number), "--repo", github.repository(),
        "--body", message)


def _ensure_auto_merge(pr: dict) -> None:
    enabled = run("gh", "pr", "view", str(pr["number"]), "--repo",
                  github.repository(), "--json", "autoMergeRequest",
                  "--jq", ".autoMergeRequest != null")
    if enabled != "true":
        command = ["gh", "pr", "merge", str(pr["number"]),
                   "--repo", github.repository(), "--auto", "--squash"]
        if pr.get("head", {}).get("sha"):
            command.extend(["--match-head-commit", commit_sha(pr["head"]["sha"])])
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Could not enable GitHub auto-merge: {result.stderr[-800:]}")


def _resume_submitted_pr(pr: dict, incident: str, report: dict, base: str) -> bool:
    """Recover a successful push / PR creation without consuming another round."""
    history = (pr_history.load_new_version_rounds(pr) if pr["head"]["ref"].startswith("auto/ffmpeg-") else pr_history.load_rounds(pr, incident))
    latest = history[-1]
    source = report["source"]
    if latest.source_run != source["run_id"] or \
       latest.source_attempt != source["run_attempt"]:
        return False
    detail = github.api(f"repos/{github.repository()}/commits/{latest.sha}")
    parents = detail.get("parents")
    if not isinstance(parents, list) or len(parents) != 1 or \
       commit_sha(parents[0].get("sha")) != base.lower():
        return False
    events = pr_history.load_events(pr["number"], incident, history)
    for item in history:
        pr_history.publish_event(pr["number"], pr_history.event_for_round(item), events)
    view = github.api(f"repos/{github.repository()}/pulls/{pr['number']}")
    verify_pr(view, pr["head"]["ref"])
    section = pr_history.render_history(history, events,
               cumulative_paths=pr_history.current_files(pr["number"]))
    original = view.get("body") or ""
    if START not in original and END not in original:
        updated = original.rstrip() + ("\n\n" if original.strip() else "") + section
    else:
        updated = update_body(original, section)
    if len(updated) > 60_000:
        raise ValueError("Auto-Heal PR summary exceeds size budget")
    if updated != original:
        write_pr_body(pr["number"], updated)
    if report["source"].get("event") not in ("workflow_dispatch", "schedule", "pull_request"):
        _ensure_auto_merge(view)
    return True


def _recover_orphan(
        branch: str, remote: str, base: str, incident: str,
        report: dict, yaml: str, patch: Path, expected_paths: list[str]) -> None:
    """Recover a pushed bot commit only when it equals the candidate patch.

    A remote branch without a PR is not evidence of bot ownership. Require
    GitHub's mapped bot identity, verified provenance, an exact parent, source
    scope, and an identical Git tree before creating any PR for that branch.
    """
    parts = remote.split()
    if len(parts) != 2 or parts[1] != f"refs/heads/{branch}":
        raise ValueError("Unexpected remote orphan branch reference")
    sha = commit_sha(parts[0])
    detail = github.api(f"repos/{github.repository()}/commits/{sha}?per_page=100")
    if (detail.get("author") or {}).get("login") != BOT or \
       (detail.get("committer") or {}).get("login") != BOT:
        raise ValueError("Cannot verify an orphan branch belongs to the GitHub bot")
    entry = pr_history.round_from_commit(detail, incident)
    source = report["source"]
    if entry.number != 1 or entry.source_run != source["run_id"] or \
       entry.source_attempt != source["run_attempt"]:
        raise ValueError("Orphan commit was produced for a different incident occurrence")
    parents = detail.get("parents")
    if not isinstance(parents, list) or len(parents) != 1 or \
       commit_sha(parents[0].get("sha")) != base.lower():
        raise ValueError("Orphan commit does not descend from the failed source")
    if sorted(entry.paths) != sorted(expected_paths):
        raise ValueError("Orphan commit changed a different set of files")
    git("fetch", "origin", sha)
    actual_tree = git("rev-parse", f"{sha}^{{tree}}")
    with tempfile.TemporaryDirectory(prefix="autoheal-orphan-verify-") as scratch:
        workspace = Path(scratch)
        git("worktree", "add", "--detach", str(workspace), base)
        try:
            before = git("show", f"HEAD:ffmpeg/{yaml}.yaml", cwd=workspace)
            git("apply", "--index", "--check", str(patch.resolve()), cwd=workspace)
            git("apply", "--index", str(patch.resolve()), cwd=workspace)
            git("diff", "--cached", "--check", cwd=workspace)
            applied = validate_changes(yaml, changes(workspace), workspace, before=before)
            if sorted(applied) != sorted(expected_paths):
                raise ValueError("Candidate patch scope differs from orphan commit")
            check_modes(workspace)
            if report["source"].get("event") in ("workflow_dispatch", "schedule"):
                check_worktree(yaml, base, workspace)
            if git("write-tree", cwd=workspace) != actual_tree:
                raise ValueError("Orphan commit tree differs from submitted repair patch")
        finally:
            git("worktree", "remove", "--force", str(workspace))
    summary = pr_history.render_history([entry], [pr_history.event_for_round(entry)],
                    status="Repair submitted; awaiting full MSVC CI.")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                     suffix=".md", delete=False) as file:
        file.write(summary)
        body_path = Path(file.name)
    try:
        label_args = (["--label", ensure_label(yaml)] if report["source"].get("event") in ("workflow_dispatch", "schedule") else [])
        run("gh", "pr", "create", "--repo", github.repository(),
            "--base", "main", "--head", branch,
            "--title", repair_title(yaml, (detail.get("commit", {}).get("message") or "").split("\n", 1)[0]),
            "--body-file", str(body_path), *label_args)
    finally:
        body_path.unlink(missing_ok=True)
    pr = find_pr(branch)
    if pr is None:
        raise RuntimeError("Recovered orphan branch PR creation was not confirmed")
    verify_pr(pr, branch)
    if not _resume_submitted_pr(pr, incident, report, base):
        raise RuntimeError("Recovered orphan PR did not pass source provenance checks")


def deliver(report: dict, yaml: str, output: Path) -> None:
    incident = validate_triage(report, yaml)
    manifest_path = output / "manifest.json"
    patch_path = output / "repair.patch"
    if not manifest_path.is_file() or not patch_path.is_file():
        raise ValueError("Repair artifact or manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    patch = patch_path.read_bytes()
    if not patch or b"diff --git " not in patch:
        raise ValueError("Empty repair patch")
    base = report["pr"]["head_sha"] if report.get("pr") else report["source"]["head_sha"]
    commit_sha(base)
    expected = {
        "schema": 1, "yaml": yaml, "signature": incident.signature,
        "run_id": report["source"]["run_id"],
        "run_attempt": report["source"]["run_attempt"],
        "base_sha": base, "patch_sha256": hashlib.sha256(patch).hexdigest(),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Candidate patch does not match authenticated triage record")
    subject = repair_title(yaml, manifest.get("subject", ""))
    hypothesis = manifest.get("root_cause_hypothesis", "Not independently verified")
    if not isinstance(hypothesis, str) or len(hypothesis) > 300:
        raise ValueError("Invalid agent root-cause summary")
    hypothesis = re.sub(r"[\r\n\[\]<>]", " ", hypothesis)
    target_group = next(group for group in report["groups"] if group["yaml"] == yaml)
    branch = target_group.get("branch") or (report["pr"]["head"] if report.get("pr")
                                             else branch_name(yaml, incident.signature))
    new_pr = bool(report.get("pr") and branch == f"auto/ffmpeg-{yaml}")
    if not new_pr and not branch_matches(branch, yaml, incident.signature):
        raise ValueError("Repair branch is not bound to the incident")
    if report.get("pr") and branch != report["pr"]["head"]:
        raise ValueError("Repair PR branch changed since triage")
    if not report.get("pr") and branch not in (
            branch_name(yaml, incident.signature),
            branch_name(yaml, incident.signature, report["source"]["run_id"])):
        raise ValueError("Unexpected incident occurrence for the original run")
    previous_pr = find_pr(branch)
    if previous_pr:
        verify_pr(previous_pr, branch)
        if report.get("automatic_version_pr") and automatic_pr(previous_pr, github.repository()) != (yaml, "new" if new_pr else "repair"):
            raise ValueError("Automatic PR target changed")
    if report.get("pr"):
        if not previous_pr or report["pr"]["number"] != previous_pr["number"]:
            raise ValueError("Cannot modify another PR for this incident")
    if previous_pr and previous_pr["head"]["sha"].lower() != base.lower():
        if _resume_submitted_pr(previous_pr, incident.signature, report, base):
            return
        raise ValueError("Repair PR changed since this CI failure")
    if previous_pr and not report.get("pr"):
        if _resume_submitted_pr(previous_pr, incident.signature, report, base):
            return
        raise ValueError("Incident branch has a PR for a different source run")
    if not previous_pr:
        if report["source"].get("event") in ("workflow_dispatch", "schedule"):
            from .duplicates import open_repairs
            if any(p["head"]["ref"] != branch for p in open_repairs(yaml, incident.signature)):
                raise ValueError("An equivalent repair incident already has an open PR")
            request = report["source"].get("request") or {}
            if request.get("yaml") != yaml or request.get("repository_commit") != base or request.get("production") is not True:
                raise ValueError("Failed production request differs from repair scope")
        main = github.api(f"repos/{github.repository()}/git/ref/heads/main")
        main_sha = commit_sha(main.get("object", {}).get("sha"))
        if main_sha != base.lower():
            # A build can finish after unrelated main commits. Use the original
            # build tree only if it is an ancestor and target inputs are unchanged.
            if report["source"].get("event") not in ("workflow_dispatch", "schedule"):
                raise ValueError("Main branch advanced since the failed source run")
            if report["source"].get("request", {}).get("yaml") != yaml:
                raise ValueError("Failed build target differs")
            git("fetch", "origin", main_sha, base)
            git("merge-base", "--is-ancestor", base, main_sha)
            changed = git("diff", "--name-only", base, main_sha, "--",
                          "ffmpeg", "patches", "ports", "triplets", "ffbuild", "ffvcpkg", "licenses",
                          "vcpkg-configuration.json", "requirements.txt")
            if changed:
                raise ValueError("Build inputs changed since the failed build; manual retry required")
    previous_rounds = (pr_history.load_new_version_rounds(previous_pr) if new_pr else
                       pr_history.load_rounds(previous_pr, incident.signature) if previous_pr else [])
    previous_events = (pr_history.load_events(previous_pr["number"],
                      incident.signature, previous_rounds) if previous_pr else [])
    if previous_rounds and previous_rounds[-1].sha.lower() != base.lower():
        raise ValueError("History does not match source repair HEAD")
    # Authenticate Git only after the privileged writer has verified the
    # triage/manifest/source policy. Orphan recovery requires authenticated fetch.
    run("gh", "auth", "setup-git")
    remote = git("ls-remote", "origin", f"refs/heads/{branch}")
    if remote and not previous_pr:
        _recover_orphan(branch, remote, base, incident.signature,
                        report, yaml, patch_path, manifest["paths"])
        return
    if bool(remote) != bool(previous_pr):
        raise ValueError("Remote branch and bot PR disagree")
    if previous_pr and remote.split()[0].lower() != base.lower():
        raise ValueError("Bot branch moved before delivery")
    git("fetch", "origin", base)
    with tempfile.TemporaryDirectory(prefix="autoheal-writer-") as scratch:
        workspace = Path(scratch)
        git("worktree", "add", "--detach", str(workspace), base)
        try:
            round_no = next_round(previous_rounds[-1].number if previous_rounds else 0)
            before = git("show", f"HEAD:ffmpeg/{yaml}.yaml", cwd=workspace)
            git("apply", "--index", "--check", str(patch_path.resolve()), cwd=workspace)
            git("apply", "--index", str(patch_path.resolve()), cwd=workspace)
            git("diff", "--cached", "--check", cwd=workspace)
            modified = changes(workspace)
            if report["source"].get("event") in ("workflow_dispatch", "schedule", "pull_request"):
                verified_paths = check_worktree(yaml, base, workspace)
                paths = [path for _, path in modified]
                if set(paths) != set(verified_paths):
                    raise ValueError("Repair index does not equal verified scope")
            else:
                paths = validate_changes(yaml, modified, workspace, before=before)
            if paths != manifest.get("paths"):
                raise ValueError("Applied changes do not match original manifest")
            check_modes(workspace)
            git("-c", "user.name=ffmpeg-dev[bot]",
                "-c", "user.email=295689149+ffmpeg-dev[bot]@users.noreply.github.com",
                "-c", "commit.gpgsign=false", "commit",
                "-m", subject,
                "-m", f"Autoheal-Round: {round_no}\n"
                      f"Autoheal-Incident: {incident.signature}\n"
                      f"Autoheal-Source-Run: {report['source']['run_id']}\n"
                      f"Autoheal-Source-Attempt: {report['source']['run_attempt']}\n"
                      f"Autoheal-Hypothesis: {hypothesis}", cwd=workspace)
            submitted_sha = commit_sha(git("rev-parse", "HEAD", cwd=workspace))
            if report.get("automatic_version_pr") or report["source"].get("event") in ("workflow_dispatch", "schedule"):
                git("fetch", "origin", "main", cwd=workspace)
                check_pr(yaml, git("rev-parse", "FETCH_HEAD", cwd=workspace), submitted_sha,
                         workspace, allow_new=new_pr)
            git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=workspace)
        finally:
            git("worktree", "remove", "--force", str(workspace))
    current_round_record = RepairRound(
        round_no, submitted_sha, incident.signature,
        report["source"]["run_id"], report["source"]["run_attempt"],
        tuple(paths), hypothesis, subject)
    rounds = [*previous_rounds, current_round_record]
    events = [*previous_events, pr_history.event_for_round(current_round_record)]
    status = "Repair submitted; awaiting full MSVC CI."
    body = pr_history.render_history(rounds, events, status=status, report=report)
    if previous_pr:
        latest = github.api(f"repos/{github.repository()}/pulls/{previous_pr['number']}")
        verify_pr(latest, branch)
        pr_history.publish_event(latest["number"], events[-1], previous_events)
        old_body = latest.get("body") or ""
        if new_pr:
            old_body = proposal_pending(old_body, report["source"], submitted_sha, github.repository())
        if new_pr and START not in old_body and END not in old_body:
            write_pr_body(latest["number"], old_body.rstrip() + "\n\n" + body)
        else:
            write_pr_body(latest["number"], update_body(old_body, body))
    else:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         suffix=".md", delete=False) as f:
            f.write(body)
            name = Path(f.name)
        try:
            label_args = (["--label", ensure_label(yaml)] if report["source"].get("event") in ("workflow_dispatch", "schedule") else [])
            run("gh", "pr", "create", "--repo", github.repository(),
                "--base", "main", "--head", branch,
                "--title", subject,
                "--body-file", str(name), *label_args)
        finally:
            name.unlink(missing_ok=True)
        latest = find_pr(branch)
        if latest is None:
            raise RuntimeError("PR creation could not be verified")
        verify_pr(latest, branch)
        pr_history.publish_event(latest["number"], events[-1], previous_events)
    if report["source"].get("event") not in ("workflow_dispatch", "schedule", "pull_request"):
        _ensure_auto_merge(latest)


def sync_status(report: dict) -> None:
    """Rebuild all rounds and append a deduplicated CI event.

    If an earlier write or comment failed, reconstruct the whole history
    from authenticated bot commits and the existing immutable CI events.
    """
    pr = report.get("pr")
    if not pr or pr.get("author") != BOT or not pr.get("head", "").startswith(("autoheal/", "auto/ffmpeg-")):
        return
    latest = github.api(f"repos/{github.repository()}/pulls/{pr['number']}")
    if latest.get("user", {}).get("login") != BOT:
        return
    if report.get("automatic_version_pr") and not automatic_pr(latest, github.repository()):
        return
    if latest.get("head", {}).get("sha", "").lower() != report["source"]["head_sha"].lower():
        return  # Older CI cannot overwrite a newer PR HEAD.
    body = latest.get("body") or ""
    if (START in body) != (END in body):
        raise ValueError("Damaged Auto-Heal PR managed section")

    new_pr = latest.get("head", {}).get("ref", "").startswith("auto/ffmpeg-")
    if new_pr:
        rounds = pr_history.load_new_version_rounds(latest)
        if not rounds:
            fresh = github.api(f"repos/{github.repository()}/pulls/{latest['number']}")
            if fresh.get("head", {}).get("sha", "").lower() != report["source"]["head_sha"].lower():
                return
            body = fresh.get("body") or ""
            updated = proposal_status(body, report["source"], bool(report.get("verified_version_ci")), github.repository())
            if updated != body:
                write_pr_body(latest["number"], updated)
            if report.get("verified_version_ci") and fresh.get("state") == "open":
                _ensure_auto_merge(fresh)
            return
        incident = rounds[0].incident
    else:
        incident = pr_history.incident_from_pr(latest)
        rounds = pr_history.load_rounds(latest, incident)
    events = pr_history.load_events(latest["number"], incident, rounds)
    # A branch push can succeed while its comment write fails.
    for item in rounds:
        pr_history.publish_event(latest["number"],
                                 pr_history.event_for_round(item), events)
    observed = pr_history.ci_event(rounds[-1], report["source"])
    pr_history.publish_event(latest["number"], observed, events)
    paths = pr_history.current_files(latest["number"])
    authoritative = pr_history.latest_ci_event(rounds[-1], events)
    if authoritative is not None and authoritative.key != observed.key:
        return  # the later CI event already owns the current presentation
    outcome = authoritative.conclusion if authoritative else "pending"
    status = {
        "success": ("Full MSVC matrix: 16/16 passed." if report.get("verified_version_ci") else
                    "CI passed; complete matrix verification not established."),
        "failure": ("CI failed; repair budget exhausted." if rounds[-1].number >= 2 else
                    "CI failed; see the linked run."),
        "cancelled": "CI cancelled.",
        "timed_out": "CI timed out.",
        "pending": "Awaiting CI.",
    }.get(outcome, "CI completed.")
    replacement = pr_history.render_history(rounds, events, cumulative_paths=paths,
                                             status=status, report=report)
    # Re-fetch immediately before writing, so edits made by a maintainer
    # while we were processing events are incorporated rather than lost.
    fresh = github.api(f"repos/{github.repository()}/pulls/{latest['number']}")
    if fresh.get("head", {}).get("sha", "").lower() != report["source"]["head_sha"].lower():
        return
    fresh_body = fresh.get("body") or ""
    if new_pr:
        fresh_body = proposal_status(fresh_body, report["source"], bool(report.get("verified_version_ci")), github.repository())
    if START not in fresh_body and END not in fresh_body:
        updated = fresh_body.rstrip() + ("\n\n" if fresh_body.strip() else "") + replacement
    else:
        updated = update_body(fresh_body, replacement)
    if len(updated) > 60_000:
        raise ValueError("Auto-Heal PR summary exceeds size budget")
    if updated != (fresh.get("body") or ""):
        write_pr_body(latest["number"], updated)
    # Repair delivery may have completed its PR write but failed to set
    # Auto-merge. A successful CI sync resumes this final idempotent step.
    if report.get("automatic_version_pr") and not automatic_pr(fresh, github.repository()):
        return
    if fresh.get("state") == "open" and (report.get("verified_version_ci") or
            ("verified_version_ci" not in report and outcome == "success")):
        _ensure_auto_merge(fresh)
