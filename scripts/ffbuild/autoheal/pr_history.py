"""Rebuild the complete Auto-Heal PR history from Git commits and bot events.

Git commits own repair rounds. GitHub issue comments are append-only, deduped
CI and submission events. A PR body is *only* a derived presentation, never a
mutable source of truth for past fixes or the round budget.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import asdict
from typing import Any

from . import github
from .ledger import MAX_REPAIR_ROUNDS, AuditReport, RepairDetails, RepairEvent, RepairRound
from .models import commit_sha, error_signature, version_name
from ..markdown import render_template

BOT = "ffmpeg-dev[bot]"
START = "<!-- ffbuild-autoheal:start -->"
END = "<!-- ffbuild-autoheal:end -->"
EVENT_PREFIX = "<!-- ffbuild-autoheal-event:v1 "
EVENT_PATTERN = re.compile(r"^<!-- ffbuild-autoheal-event:v1 (\{[^\r\n]*\}) -->", re.ASCII)
_TRAILER = re.compile(r"(?m)^Autoheal-(Round|Incident|Source-Run|Source-Attempt|Hypothesis|Audit|Details): ([^\r\n]*)$")
_SAFE = re.compile(r"[\x00-\x1f\x7f]")


def _text(value: str, limit: int = 500) -> str:
    """Untrusted log/path/Agent text must not be able to inject HTML or MD."""
    if not isinstance(value, str):
        raise ValueError("Expected a string in Auto-Heal history")
    return html.escape(_SAFE.sub(" ", value[:limit]), quote=True).replace("[", "&#91;").replace("]", "&#93;").replace(chr(96), "&#96;").replace("*", "&#42;")


def _url(repo: str, run: int, attempt: int) -> str:
    return f"https://github.com/{repo}/actions/runs/{run}/attempts/{attempt}"


def _commit_url(repo: str, sha: str) -> str:
    return f"https://github.com/{repo}/commit/{commit_sha(sha)}"


def round_from_commit(raw: dict[str, Any], incident: str) -> RepairRound:
    """Validate a single ordinary GitHub commit-detail response."""
    error_signature(incident)
    if not isinstance(raw, dict):
        raise ValueError("Invalid GitHub commit")
    sha = commit_sha(raw.get("sha"))
    message = (raw.get("commit") or {}).get("message", "")
    if not isinstance(message, str):
        raise ValueError("Missing repair commit message")
    values: dict[str, str] = {}
    for key, value in _TRAILER.findall(message):
        if key in values:
            raise ValueError(f"Duplicate Auto-Heal trailer: {key}")
        values[key] = value
    if not values or values.get("Incident") != incident:
        raise ValueError("PR contains a nonmatching or unmarked repair commit")
    try:
        number = int(values["Round"])
        source_run = int(values["Source-Run"])
        source_attempt = int(values.get("Source-Attempt", "1"))
    except (KeyError, ValueError) as exc:
        raise ValueError("Invalid Auto-Heal commit provenance") from exc
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Commit file details unavailable")
    paths: list[str] = []
    for item in files:
        if not isinstance(item, dict) or item.get("status") not in ("added", "modified"):
            raise ValueError("Unsafe or incomplete repair commit")
        path = item.get("filename")
        if not isinstance(path, str) or not path:
            raise ValueError("Invalid repair path")
        paths.append(path)
    subject = message.split("\n", 1)[0]
    if len(subject) > 120:
        subject = ""
    audit = AuditReport.from_trailer(values["Audit"]) if "Audit" in values else None
    if audit is not None:
        if ((raw.get("author") or {}).get("login") != BOT or
                (raw.get("committer") or {}).get("login") != BOT):
            raise ValueError("Audit trailer is not from the authorized bot")
        if commit_sha((raw.get("commit", {}).get("tree") or {}).get("sha")) != audit.tree:
            raise ValueError("Audit trailer does not match repair commit tree")
    details = RepairDetails.from_trailer(values["Details"]) if "Details" in values else None
    if details is not None and audit is None:
        raise ValueError("Repair details require an authenticated audit trailer")
    return RepairRound(number, sha, incident, source_run, source_attempt,
                       tuple(paths), values.get("Hypothesis", ""), subject, audit, details)


def validate_rounds(rounds: list[RepairRound], incident: str, expected_head: str | None = None) -> None:
    """A PR must have a complete, linear, bounded repair history."""
    error_signature(incident)
    if not rounds or len(rounds) > MAX_REPAIR_ROUNDS:
        raise ValueError("Missing or excessive repair commits")
    for expected, item in enumerate(rounds, start=1):
        if item.number != expected or item.incident != incident:
            raise ValueError("Repair commits are not sequential or share a different incident")
        if len(item.paths) != len(set(item.paths)):
            raise ValueError("Duplicate repair files")
    if expected_head is not None and rounds[-1].sha.lower() != commit_sha(expected_head):
        raise ValueError("PR HEAD does not match its last repair commit")


def load_rounds(pr: dict, incident: str) -> list[RepairRound]:
    """Fetch the entire PR commit list, not just its latest commit."""
    if not isinstance(pr, dict) or type(pr.get("number")) is not int:
        raise ValueError("Invalid bot PR")
    repo = github.repository()
    endpoint = f"repos/{repo}/pulls/{pr['number']}/commits"
    listed = github.collection(endpoint, "commits", limit=MAX_REPAIR_ROUNDS)
    rounds = []
    for entry in listed:
        sha = commit_sha(entry.get("sha"))
        details = github.api(f"repos/{repo}/commits/{sha}?per_page=100")
        item = round_from_commit(details, incident)
        if rounds:
            parents = details.get("parents")
            if not isinstance(parents, list) or len(parents) != 1 or \
               commit_sha(parents[0].get("sha")) != rounds[-1].sha.lower():
                raise ValueError("Auto-Heal PR commits do not form a linear repair chain")
        rounds.append(item)
    validate_rounds(rounds, incident, (pr.get("head") or {}).get("sha"))
    return rounds


def load_new_version_rounds(pr: dict) -> list[RepairRound]:
    """Verify the single bot proposal followed by zero or two bounded repair commits."""
    from ..release_trigger import automatic_pr
    repo = github.repository()
    selected = automatic_pr(pr, repo)
    if not selected or selected[1] != "new":
        raise ValueError("Not an authenticated new-version PR")
    target = selected[0]
    listed = github.collection(f"repos/{repo}/pulls/{pr['number']}/commits", "commits",
                               limit=MAX_REPAIR_ROUNDS + 1)
    if not listed or len(listed) > MAX_REPAIR_ROUNDS + 1:
        raise ValueError("Invalid new-version repair history")
    previous = None
    rounds = []
    for i, entry in enumerate(listed):
        sha = commit_sha(entry.get("sha"))
        detail = github.api(f"repos/{repo}/commits/{sha}?per_page=100")
        message = (detail.get("commit") or {}).get("message", "")
        if i == 0:
            if message != f"feat(ffmpeg): propose {target} build spec" or (detail.get("author") or {}).get("login") != BOT:
                raise ValueError("Initial version proposal is not from the authorized Bot")
        else:
            parents = detail.get("parents") or []
            if len(parents) != 1 or commit_sha(parents[0].get("sha")) != previous:
                raise ValueError("New-version repair history is not linear")
            incident = rounds[0].incident if rounds else incident_from_pr(pr)
            rounds.append(round_from_commit(detail, incident))
        previous = sha
    if previous != commit_sha(pr["head"]["sha"]):
        raise ValueError("New-version PR head does not match history")
    if rounds:
        validate_rounds(rounds, rounds[0].incident, previous)
    return rounds


def current_files(pr_number: int) -> list[str]:
    """Collect *cumulative* PR diff rather than unioning historical commits."""
    if type(pr_number) is not int or pr_number < 1:
        raise ValueError("Invalid PR number")
    repo = github.repository()
    entries = github.collection(f"repos/{repo}/pulls/{pr_number}/files", "files", limit=400)
    paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
            raise ValueError("Malformed PR diff")
        if entry.get("status") not in ("added", "modified"):
            raise ValueError("Unexpected PR file change")
        paths.append(entry["filename"])
    if not paths:
        raise ValueError("PR has no file changes")
    return paths


def event_for_round(item: RepairRound) -> RepairEvent:
    return RepairEvent("repair", item.number, item.sha, item.incident,
                       item.source_run, item.source_attempt, "pending")


def ci_event(item: RepairRound, source: dict[str, Any]) -> RepairEvent:
    if source.get("head_sha", "").lower() != item.sha.lower():
        raise ValueError("CI run SHA does not match the repair round")
    return RepairEvent("ci", item.number, item.sha, item.incident,
                       source["run_id"], source["run_attempt"],
                       source.get("run_conclusion") or "pending")


def event_comment(event: RepairEvent) -> str:
    payload = {**asdict(event), "key": event.key}
    marker = EVENT_PREFIX + json.dumps(payload, ensure_ascii=True,
                                       sort_keys=True, separators=(",", ":")) + " -->"
    repo = github.repository()
    label = "Repair submitted" if event.kind == "repair" else f"CI {event.conclusion}"
    return marker + "\n" + render_template("repair-event.md", round=event.round, label=label,
        commit=f"[`{event.sha[:12]}`]({_commit_url(repo, event.sha)})",
        ci=f"[Run {event.run_id}, attempt {event.attempt}]({_url(repo, event.run_id, event.attempt)})")


def parse_event(comment: dict, incident: str, rounds: list[RepairRound]) -> RepairEvent | None:
    """Only bot-authored, well-formed comments tied to real repair commits count."""
    if not isinstance(comment, dict) or (comment.get("user") or {}).get("login") != BOT:
        return None
    body = comment.get("body")
    if not isinstance(body, str):
        return None
    marker = EVENT_PATTERN.match(body)
    if not marker:
        return None
    try:
        payload = json.loads(marker[1])
        if not isinstance(payload, dict):
            return None
        key = payload.pop("key", None)
        event = RepairEvent(**payload)
        if key != event.key or event.incident != incident:
            return None
    except (ValueError, TypeError):
        return None
    if not any(item.number == event.round and item.sha == event.sha for item in rounds):
        return None
    return event


def load_events(pr_number: int, incident: str,
                rounds: list[RepairRound]) -> list[RepairEvent]:
    """An invalid user comment is ignored; conflicting bot events fail closed."""
    repo = github.repository()
    records = github.collection(f"repos/{repo}/issues/{pr_number}/comments",
                                "comments", limit=2000)
    found: dict[str, RepairEvent] = {}
    for comment in records:
        event = parse_event(comment, incident, rounds)
        if event is None:
            continue
        previous = found.get(event.key)
        if previous is not None and previous != event:
            raise ValueError("Conflicting bot event records")
        found[event.key] = event
    return list(found.values())


def publish_event(pr_number: int, event: RepairEvent, previous: list[RepairEvent]) -> bool:
    """Idempotently append an immutable event, never rewrite an old comment."""
    if any(item.key == event.key for item in previous):
        return False
    # Deferred import avoids the cycle between the writer and history module.
    from .delivery import post_comment
    post_comment(pr_number, event_comment(event))
    previous.append(event)
    return True


def latest_ci_event(item: RepairRound, events: list[RepairEvent]) -> RepairEvent | None:
    """A delayed old CI notification cannot replace a newer run attempt."""
    checks = [event for event in events if event.kind == "ci" and event.sha == item.sha]
    return max(checks, key=lambda event: (event.run_id, event.attempt), default=None)


def status_for(item: RepairRound, events: list[RepairEvent]) -> str:
    newest = latest_ci_event(item, events)
    if newest is None:
        return "Pending"
    return {"success": "Passed", "failure": "Failed",
            "cancelled": "Cancelled", "timed_out": "Timed out",
            "pending": "Running"}.get(newest.conclusion, "Completed")


def render_history(rounds: list[RepairRound], events: list[RepairEvent],
                   *, cumulative_paths: list[str] | None = None,
                   status: str | None = None,
                   report: dict | None = None,
                   target_yaml: str | None = None) -> str:
    """One complete managed Markdown section, rebuilt without discarding rounds."""
    if not rounds:
        raise ValueError("No Auto-Heal rounds")
    incident = rounds[0].incident
    validate_rounds(rounds, incident)
    repo = github.repository()
    if target_yaml is None:
        target_names = [m[1] for path in rounds[0].paths
                        if (m := re.fullmatch(r"ffmpeg/((?:master|[0-9]+(?:\.[0-9]+){1,2}))\.yaml", path))]
        if len(target_names) != 1:
            raise ValueError("Cannot derive one FFmpeg target from initial repair")
        target_yaml = target_names[0]
    version_name(target_yaml)
    source = rounds[0]
    original_url = _url(repo, source.source_run, source.source_attempt)
    latest = rounds[-1]
    state = status or status_for(latest, events)
    full_paths = cumulative_paths if cumulative_paths is not None else sorted({
        path for item in rounds for path in item.paths
    })
    if not full_paths:
        raise ValueError("Cannot render an empty cumulative PR diff")

    def cell(value: str) -> str:
        return _text(value, 300).replace("|", "&#124;").replace("`", "&#96;").replace("*", "&#42;").replace("_", "&#95;")

    from ..messages import repair_title
    action = repair_title(target_yaml, latest.subject).split(": ", 1)[1]
    changes = [f"- `{_text(path)}`" for path in full_paths[:40]]
    if len(full_paths) > 40:
        changes.append(f"- {len(full_paths) - 40} additional files (see Files changed)")
    history = []
    earlier = []
    for item in rounds:
        checks = sorted((e for e in events if e.kind == "ci" and e.sha == item.sha),
                        key=lambda e: (e.run_id, e.attempt))
        ci = status_for(item, events)
        if checks:
            newest = checks[-1]
            ci = f"[{ci} (Run {newest.run_id}, attempt {newest.attempt})]({_url(repo, newest.run_id, newest.attempt)})"
        history.append(f"| {item.number} | [`{item.sha[:12]}`]({_commit_url(repo, item.sha)}) | "
                       f"{cell(item.hypothesis or 'Not provided')} | {ci} |")
        for event in checks[:-1][-20:]:
            earlier.append(f"- Round {item.number}: [Run {event.run_id}, attempt {event.attempt}]({_url(repo, event.run_id, event.attempt)}) — {event.conclusion}")

    def public_text(value: str, limit: int) -> str:
        # Treat all report fields as display-only plain text, not Markdown.
        # Encode original characters in one pass; never re-escape entity syntax.
        special = "&<>\"'[]`*@:_~!#|(){}\\"
        return _SAFE.sub(" ", value[:limit]).translate(str.maketrans({c: f"&#{ord(c)};" for c in special}))

    round_reports = []
    for item in rounds:
        audit = item.audit
        current = "current candidate" if item == latest else "previous candidate"
        if audit is None:
            audit_text = "No persisted audit report is available for this round."
        else:
            artifact = f"autoheal-audit-a{audit.attempt}-{target_yaml}-{item.incident}"
            summary = public_text(audit.summary, 8000)
            if len(summary) > 6000:
                summary = re.sub(r"&(?:#\d*)?$", "", summary[:6000]) + "… (see full report)"
            audit_text = "\n".join([
                "**Independent security audit**", "", "**Decision:** Approved", "", summary, "",
                f"- Audit run: [Run {audit.run_id}, attempt {audit.attempt}]({_url(repo, audit.run_id, audit.attempt)})",
                f"- Full report: `audit-report.md` in artifact `{artifact}` (7-day retention).",
                "- Read-only review of existing evidence; no additional build or test execution.",
            ])
        details = item.details
        rationale = public_text(details.rationale, 1200) if details and details.rationale else "No persisted repair rationale is available."
        validation = ("\n".join(f"- {public_text(line, 500)}" for line in details.validation)
                      if details else "No persisted native validation summary is available.")
        round_reports.append("\n".join([
            f"**Round {item.number} ({current}) — [`{item.sha[:12]}`]({_commit_url(repo, item.sha)})**",
            "", f"**Repair:** {rationale}", "", "**Native validation:**", "", validation,
            "", audit_text,
        ]))
    earlier_attempts = ("\n<details>\n<summary>Earlier CI attempts</summary>\n\n"
                        + "\n".join(earlier) + "\n\n</details>\n") if earlier else ""
    body = render_template("repair-pr.md", status=_text(state), round=latest.number, max_rounds=MAX_REPAIR_ROUNDS,
                           source_failure=f"[Run {source.source_run}, attempt {source.source_attempt}]({original_url})",
                           summary=(public_text(latest.hypothesis, 300) if latest.details and latest.hypothesis else
                                    _text(action[0].upper() + action[1:]) + "."), changes="\n".join(changes),
                           history="\n".join(history), earlier_attempts=earlier_attempts,
                           round_reports="\n\n".join(round_reports))
    return "\n".join([START, f"<!-- ffbuild-autoheal-incident:v1 {incident} -->", body, END])


def incident_from_pr_body(body: str) -> str:
    if body.count(START) != 1 or body.count(END) != 1:
        raise ValueError("Invalid Auto-Heal PR managed section")
    section = body.split(START, 1)[1].split(END, 1)[0]
    matches = re.findall(r"(?m)^<!-- ffbuild-autoheal-incident:v1 ([0-9a-f]{64}) -->$", section)
    if len(matches) != 1:
        raise ValueError("No unique canonical incident in bot PR")
    return error_signature(matches[0])


def incident_from_pr(pr: dict) -> str:
    """Recover the original incident from the bot commit if PR body was lost."""
    body = pr.get("body") or ""
    if START in body or END in body:
        return incident_from_pr_body(body)
    sha = commit_sha((pr.get("head") or {}).get("sha"))
    detail = github.api(f"repos/{github.repository()}/commits/{sha}")
    message = (detail.get("commit") or {}).get("message", "")
    trailers = re.findall(r"(?m)^Autoheal-Incident: ([a-f0-9]{64})$", message)
    if len(trailers) != 1:
        raise ValueError("Bot PR lacks one trusted incident commit trailer")
    return error_signature(trailers[0])


def find_pr_round(pr: dict) -> int:
    """For Triage; round is derived from Git commits, not mutable text."""
    body = pr.get("body") or ""
    incident = incident_from_pr(pr)
    rounds = load_rounds(pr, incident)
    return rounds[-1].number
