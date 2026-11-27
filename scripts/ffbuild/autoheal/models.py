"""Validated, portable contracts between untrusted CI evidence and privileged delivery."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_VERSION = re.compile(r"(?:[0-9]+(?:\.[0-9]+){1,2}|master)\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z", re.I)
_SIGNATURE = re.compile(r"[0-9a-f]{16,64}\Z", re.I)


def version_name(value: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ValueError(f"Invalid FFmpeg YAML target: {value!r}")
    return value


def commit_sha(value: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("Missing or invalid Git commit SHA")
    return value.lower()


def error_signature(value: str) -> str:
    if not isinstance(value, str) or not _SIGNATURE.fullmatch(value):
        raise ValueError("Missing or invalid error signature")
    return value.lower()


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"Invalid {label}")
    return value


@dataclass(frozen=True)
class Incident:
    yaml: str
    phase: str
    signature: str
    repairable: bool
    jobs: tuple[dict[str, Any], ...]

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> "Incident":
        if not isinstance(raw, dict):
            raise ValueError("Incident must be an object")
        yaml = version_name(raw.get("yaml"))
        signature = error_signature(raw.get("signature"))
        if raw.get("repairable") is not True:
            raise ValueError("Incident is not approved for repair")
        if raw.get("phase") != "build":
            raise ValueError("Only build incidents may be repaired")
        jobs = raw.get("jobs")
        if not isinstance(jobs, list) or not jobs:
            raise ValueError("Repair requires associated failed jobs")
        for job in jobs:
            if not isinstance(job, dict) or not job.get("variant_id") or not job.get("abi_hash"):
                raise ValueError("Missing native planned job identity")
        return cls(yaml, "build", signature, True, tuple(jobs))


def validate_triage(payload: dict[str, Any], yaml: str) -> Incident:
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("Unsupported triage contract")
    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("Missing source provenance")
    _positive_int(source.get("run_id"), "run ID")
    _positive_int(source.get("run_attempt"), "run attempt")
    commit_sha(source.get("head_sha"))
    target = version_name(yaml)
    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise ValueError("Missing incident groups")
    matches = [group for group in groups if group.get("yaml") == target]
    if len(matches) != 1:
        raise ValueError("Expected precisely one target incident")
    return Incident.parse(matches[0])
