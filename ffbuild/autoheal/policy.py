"""Conservative auto-repair policy; unknown or shared infrastructure fails closed."""
from __future__ import annotations

import re

SYSTEM_STEPS = (
    "checkout", "bootstrap", "restore", "cache", "download sources",
    "prepare architecture", "scan", "generate", "plan", "publish",
    "upload", "verify worker vcpkg abi", "save completed",
)
BUILD_STEPS = ("build and test via native vcpkg",)
SOURCE_ERROR = re.compile(
    r"(?:libav(?:codec|device|filter|format|util)|libsw(?:resample|scale)|fftools|"
    r"libpostproc|tests/[a-z_]+)[/\\][^\r\n]{0,220}"
    r"(?:error|fatal|undefined|unresolved|failed)"
    r"|(?:error|fatal|unresolved)[^\r\n]{0,220}"
    r"(?:libav(?:codec|device|filter|format|util)|libsw(?:resample|scale)|fftools)",
    re.I,
)
INFRA_ERROR = re.compile(
    r"(?:cache miss|HTTP\s*[45]\d\d|timed? out|runner|connection reset|"
    r"download failed|vcpkg ABI changed|no space left|ENOSPC|"
    r"could not resolve host|authorization failed|rate limit|artifact)",
    re.I,
)


def classify(job: dict, log_text: str) -> tuple[str, str, bool]:
    """Returns (phase, classification, repairable)."""
    name = str(job.get("name", "")).lower()
    if "prepare-" in name or "/ prepare" in name:
        return ("prepare", "seed_dependency", False)
    if "download" in name:
        return ("download", "infrastructure", False)
    if "plan" in name or "scan" in name:
        return ("plan", "planning", False)
    if "publish" in name:
        return ("publish", "publishing", False)
    failed = [str(s.get("name", "")).lower() for s in job.get("steps", [])
              if s.get("conclusion") in ("failure", "timed_out")]
    if not failed:
        return ("unknown", "insufficient_evidence", False)
    if any("verify and package" in step for step in failed):
        return ("package", "packaging", False)
    if any("verify worker vcpkg abi" in step for step in failed):
        return ("abi", "abi_mismatch", False)
    if any(any(tag in step for tag in SYSTEM_STEPS) for step in failed):
        return ("environment", "infrastructure", False)
    if any(any(tag in step for tag in BUILD_STEPS) for step in failed):
        if INFRA_ERROR.search(log_text):
            return ("build", "environment", False)
        if SOURCE_ERROR.search(log_text):
            return ("build", "source_patch", True)
        return ("build", "unclassified_build_failure", False)
    return ("unknown", "unclassified", False)
