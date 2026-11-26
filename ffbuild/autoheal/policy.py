"""Bounded diagnosis policy; eligibility is not a claim that a fix exists."""
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
PATCH_ERROR = re.compile(
    r"\b(?:applying patch failed|patch does not apply|patch failed:|"
    r"hunk\s+#?\d+\s+failed\b)", re.I)
# Do not match mere mentions of runner, artifact, timeout, or source identifiers.
# Only explicit infrastructure diagnostics veto diagnosis.
INFRA_ERROR = re.compile(
    r"\b(?:(?:error:\s*cache miss|cache miss[:;,]?\s+(?:required|fatal|failed))|connection (?:reset|refused|timed out)|"
    r"download (?:failed|failure)|failed to download|vcpkg ABI changed|"
    r"no space left(?: on device)?|ENOSPC|disk (?:is )?full|"
    r"could not resolve host|authorization failed|authentication failed|"
    r"rate limit (?:exceeded|reached)|API rate limit|"
    r"HTTP(?: status(?: code)?)?\s*[45]\d\d\b|"
    r"(?:runner|job|process|operation|request|connection) (?:has )?timed out|"
    r"(?:runner|job) (?:was )?(?:cancelled|canceled|lost)|"
    r"(?:failed to|unable to) (?:download|upload|restore) (?:the )?artifact|"
    r"artifact (?:not found|expired)|"
    r"SSL certificate problem|certificate verify failed)\b",
    re.I,
)
VCPKG_PACKAGE_FAILURE = re.compile(
    r"(?im)^\s*(?:error:\s*)?building\s+([a-z0-9][a-z0-9-]*)"
    r"(?:\[[^\]\r\n]*\])?(?::[a-z0-9-]+)?\s+failed\b")
TARGET_PACKAGE = re.compile(r"ffmpeg(?:-tester|-master|-\d+(?:-\d+)*)?\Z", re.I)


def patch_failure_key(log: str) -> str | None:
    """Identify the failing patch, independent of runner path and hunk offsets."""
    applications = list(re.finditer(
        r"(?im)^\s*(?:--\s*)?Applying patch\s+([^\r\n]+?\.patch)\s*$", log))
    failed = set()
    for i, item in enumerate(applications):
        end = applications[i + 1].start() if i + 1 < len(applications) else len(log)
        if not PATCH_ERROR.search(log[item.end():end]):
            continue
        name = item.group(1).replace("\\", "/").split("/")[-1]
        # Generated native Ports prefix original patch names with their index.
        failed.add(re.sub(r"^\d{3}-(?=\d{4}-)", "", name).lower())
    # stderr may contain the failure before the stdout fragment containing
    # the application and its matching failure. Never bind an unproven patch.
    return "patch:" + "|".join(sorted(failed)) if failed else None


def classify(job: dict, log_text: str) -> tuple[str, str, bool]:
    """Return phase, evidence category, and eligibility for scoped Agent diagnosis.

    A trusted failed native FFmpeg build with readable evidence is eligible
    unless an explicit out-of-scope failure is identified. A candidate is not
    presumed repairable until scope checks and complete native CI pass.
    """
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
    if job.get("conclusion") == "timed_out" or any(
            s.get("conclusion") == "timed_out" for s in job.get("steps", [])):
        return ("environment", "timeout", False)
    if any("verify and package" in step for step in failed):
        return ("package", "packaging", False)
    if any("verify worker vcpkg abi" in step for step in failed):
        return ("abi", "abi_mismatch", False)
    if any(any(tag in step for tag in SYSTEM_STEPS) for step in failed):
        return ("environment", "infrastructure", False)
    if any(any(tag in step for tag in BUILD_STEPS) for step in failed):
        if not log_text.strip():
            return ("build", "insufficient_evidence", False)
        if any(not any(tag in step for tag in BUILD_STEPS) for step in failed):
            return ("build", "mixed_failed_steps", False)
        if any(not TARGET_PACKAGE.fullmatch(package)
               for package in VCPKG_PACKAGE_FAILURE.findall(log_text)):
            return ("build", "external_dependency", False)
        if INFRA_ERROR.search(log_text):
            return ("build", "environment", False)
        if PATCH_ERROR.search(log_text) or SOURCE_ERROR.search(log_text):
            return ("build", "source_patch", True)
        # Unknown configure, compiler, linker and consumer diagnostics require
        # analysis, not an ever-expanding allowlist of source filenames.
        return ("build", "diagnosis_required", True)
    return ("unknown", "unclassified", False)
