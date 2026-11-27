"""Deterministic incident identity and durable, bounded repair-event contracts."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass

MAX_REPAIR_ROUNDS = 2
MAX_INFRA_RERUNS = 1
MAX_CONCURRENT_REPAIRS = 2

_SHA = re.compile(r"[a-f0-9]{40}\Z", re.I)
_SIGNATURE = re.compile(r"[a-f0-9]{64}\Z", re.I)
_EVENT_TYPES = {"repair", "ci"}
_CONCLUSIONS = {"pending", "success", "failure", "cancelled", "timed_out",
                "skipped", "neutral", "action_required", "stale"}


def incident_key(yaml: str, signature: str) -> str:
    return hashlib.sha256(f"{yaml}\0{signature}".encode()).hexdigest()[:16]


def branch_name(yaml: str, signature: str, occurrence: int | None = None) -> str:
    if not re.fullmatch(r"(?:master|\d+(?:\.\d+){1,2})", yaml):
        raise ValueError("Invalid YAML name in repair branch")
    if not re.fullmatch("[0-9a-f]{16,64}", signature):
        raise ValueError("Invalid error signature")
    suffix = ""
    if occurrence is not None:
        if type(occurrence) is not int or occurrence < 1:
            raise ValueError("Invalid original failure run for incident occurrence")
        suffix = f"-r{occurrence}"
    return f"autoheal/{yaml}/{incident_key(yaml, signature)}{suffix}"


def branch_matches(branch: str, yaml: str, signature: str) -> bool:
    base = branch_name(yaml, signature)
    return branch == base or bool(re.fullmatch(re.escape(base) + r"-r[1-9][0-9]*", branch))


def next_round(previous: int) -> int:
    if type(previous) is not int or previous < 0 or previous >= MAX_REPAIR_ROUNDS:
        raise ValueError("Auto-heal round budget exhausted")
    return previous + 1


@dataclass(frozen=True)
class AuditReport:
    """Public, bounded approval summary from the independently validated record."""
    run_id: int
    attempt: int
    tree: str
    patch_sha256: str
    summary: str

    def __post_init__(self) -> None:
        if type(self.run_id) is not int or self.run_id < 1 or type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("Invalid audit workflow provenance")
        if not isinstance(self.tree, str) or not _SHA.fullmatch(self.tree):
            raise ValueError("Invalid audited candidate tree")
        if not isinstance(self.patch_sha256, str) or not _SIGNATURE.fullmatch(self.patch_sha256):
            raise ValueError("Invalid audited patch digest")
        if not isinstance(self.summary, str) or not self.summary.strip() or len(self.summary) > 8000:
            raise ValueError("Invalid audit summary")

    def trailer(self) -> str:
        # Encode untrusted model text: it must never inject a commit trailer.
        raw = json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii")

    @classmethod
    def from_trailer(cls, value: str) -> AuditReport:
        if not isinstance(value, str) or len(value) > 66000 or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
            raise ValueError("Invalid audit commit trailer")
        try:
            raw = base64.b64decode(value, altchars=b"-_", validate=True)
            record = cls(**json.loads(raw))
            if record.trailer() != value:
                raise ValueError("Noncanonical audit commit trailer")
            return record
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ValueError("Invalid audit commit trailer") from exc


@dataclass(frozen=True)
class RepairDetails:
    """Public repair rationale and actual supervisor validation, bound to a bot commit."""
    rationale: str
    validation: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rationale, str) or len(self.rationale) > 1200:
            raise ValueError("Invalid repair rationale")
        if (not isinstance(self.validation, tuple) or not 1 <= len(self.validation) <= 16 or
                any(not isinstance(line, str) or not line.strip() or len(line) > 500 for line in self.validation)):
            raise ValueError("Invalid native validation summary")

    def trailer(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True, separators=(",", ":"))

    @classmethod
    def from_trailer(cls, value: str) -> RepairDetails:
        if not isinstance(value, str) or len(value) > 64000:
            raise ValueError("Invalid repair details trailer")
        try:
            data = json.loads(value)
            if not isinstance(data, dict) or set(data) != {"rationale", "validation"} or not isinstance(data["validation"], list):
                raise ValueError("Invalid repair details fields")
            record = cls(data["rationale"], tuple(data["validation"]))
            if record.trailer() != value:
                raise ValueError("Noncanonical repair details trailer")
            return record
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid repair details trailer") from exc


def native_validation_summary(evidence: dict) -> tuple[str, ...]:
    """Presentation only; callers must first run the native evidence gate."""
    lines = []
    for check in evidence["checks"]:
        runtime = check["runtime"]
        counts = check["tester_targets"]
        execution = (f"runtime passed ({runtime['tester_executions']} Tester, {runtime['cli_executions']} CLI executions)"
                     if runtime["status"] == "passed" else "runtime skipped (host architecture incompatible)")
        lines.append(f"{check['spec']}: FFmpeg, Tester compile/link ({counts['release']} Release + {counts['debug']} Debug), "
                     f"PE/COFF passed; {execution}; external dependency builds: 0.")
    return tuple(lines)


@dataclass(frozen=True)
class RepairRound:
    """Immutable facts extracted from a bot commit, not a mutable PR body."""
    number: int
    sha: str
    incident: str
    source_run: int
    source_attempt: int
    paths: tuple[str, ...]
    hypothesis: str = ""
    subject: str = ""
    audit: AuditReport | None = None
    details: RepairDetails | None = None

    def __post_init__(self) -> None:
        if type(self.number) is not int or not 1 <= self.number <= MAX_REPAIR_ROUNDS:
            raise ValueError("Invalid repair round")
        if not isinstance(self.sha, str) or not _SHA.fullmatch(self.sha):
            raise ValueError("Invalid repair commit")
        if not isinstance(self.incident, str) or not _SIGNATURE.fullmatch(self.incident):
            raise ValueError("Invalid incident signature")
        if type(self.source_run) is not int or self.source_run < 1:
            raise ValueError("Invalid source run")
        if type(self.source_attempt) is not int or self.source_attempt < 1:
            raise ValueError("Invalid source run attempt")
        if not isinstance(self.paths, tuple) or not self.paths:
            raise ValueError("Repair commit has no changed files")
        if any(not isinstance(path, str) or not path for path in self.paths):
            raise ValueError("Invalid changed file")
        if not isinstance(self.hypothesis, str) or len(self.hypothesis) > 300:
            raise ValueError("Invalid root-cause hypothesis")
        if not isinstance(self.subject, str) or len(self.subject) > 120 or "\n" in self.subject or "\r" in self.subject:
            raise ValueError("Invalid repair subject")
        if self.audit is not None and not isinstance(self.audit, AuditReport):
            raise ValueError("Invalid repair audit report")
        if self.details is not None and not isinstance(self.details, RepairDetails):
            raise ValueError("Invalid repair details")


@dataclass(frozen=True)
class RepairEvent:
    """An append-only GitHub issue-comment event with a deterministic key."""
    kind: str
    round: int
    sha: str
    incident: str
    run_id: int
    attempt: int
    conclusion: str

    def __post_init__(self) -> None:
        if self.kind not in _EVENT_TYPES:
            raise ValueError("Unsupported repair event")
        if type(self.round) is not int or not 1 <= self.round <= MAX_REPAIR_ROUNDS:
            raise ValueError("Invalid repair event round")
        if not isinstance(self.sha, str) or not _SHA.fullmatch(self.sha):
            raise ValueError("Invalid repair event commit")
        if not isinstance(self.incident, str) or not _SIGNATURE.fullmatch(self.incident):
            raise ValueError("Invalid repair event signature")
        if type(self.run_id) is not int or self.run_id < 1:
            raise ValueError("Invalid repair event run")
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("Invalid repair event attempt")
        if self.conclusion not in _CONCLUSIONS:
            raise ValueError("Invalid repair event conclusion")
        if self.kind == "repair" and self.conclusion != "pending":
            raise ValueError("A repair submission must start pending")

    @property
    def key(self) -> str:
        identity = (f"{self.incident}\0{self.round}\0{self.kind}\0"
                    f"{self.run_id}\0{self.attempt}\0{self.sha}")
        return hashlib.sha256(identity.encode("ascii")).hexdigest()[:32]
