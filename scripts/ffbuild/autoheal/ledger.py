"""Deterministic incident identity and durable, bounded repair-event contracts."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

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
