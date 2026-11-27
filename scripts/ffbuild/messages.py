"""User-facing GitHub Markdown; machine identities remain separate."""
from __future__ import annotations

import re

from .identity import normalize_version
from .autoheal.models import version_name, commit_sha

PROPOSAL_START = "<!-- ffbuild-proposal:start -->"
PROPOSAL_END = "<!-- ffbuild-proposal:end -->"


def release_message(tag: str, version: str, *, snapshot: bool = False,
                    records: list[dict] | None = None, repo: str = "",
                    run_id: str = "", attempt: str = "") -> tuple[str, str]:
    from .release_trigger import parse_tag
    version = normalize_version(version)
    title = f"FFmpeg {version} (MSVC Prebuilt)"
    if snapshot:
        title = f"FFmpeg Master (MSVC Prebuilt)"
    try:
        _, day = parse_tag(tag)
    except ValueError:
        day = ""
    if day:
        rev = re.search(r"R[0-9]+$", tag)
        title += " — " + day + (" " + rev[0] if rev else "")
    lines = ["Prebuilt FFmpeg binaries for Windows, built with MSVC and vcpkg."]
    if records:
        arch = {r["triplet"].removesuffix("-windows") for r in records}
        licenses = {r["license"].upper() for r in records}
        linkages = {r["linkage"] for r in records}
        lines += ["", "## Downloads", "", "| Package | Contents |", "| --- | --- |"]
        if "static" in linkages:
            lines.append("| Static | Standalone FFmpeg executables |")
        if "shared" in linkages:
            lines.append("| Shared | Executables, DLLs and release SDK |")
        if any("debug" in r.get("assets", {}) for r in records):
            lines.append("| Debug Add-on | Debug libraries and Release/Debug PDBs; extract over matching Shared Binary |")
        if any("develop" in r.get("assets", {}) for r in records):
            lines.append("| Develop | Release SDK, debug libraries and symbols |")
        lines += ["", "**Architectures:** " + ", ".join(a for a in ("x86", "x64", "arm", "arm64") if a in arch).replace("arm64", "ARM64").replace("arm", "ARM"),
                  "**Licenses:** " + " / ".join(l for l in ("LGPL", "GPL") if l in licenses),
                  "", "License notices and an SPDX SBOM are included in each archive.",
                  "", "## Source and build"]
    if snapshot:
        source = (records or [{}])[0].get("source_commit")
        if source:
            source = commit_sha(source)
            lines += ["", f"**Source:** [FFmpeg {version}](https://github.com/FFmpeg/FFmpeg/commit/{source}) ({source[:12]})"]
        else:
            lines += ["", f"**Source:** FFmpeg {version} (Master snapshot)"]
    else:
        lines += ["", f"**Source:** [FFmpeg n{version}](https://github.com/FFmpeg/FFmpeg/tree/n{version})"]
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) and re.fullmatch(r"[1-9][0-9]*", run_id):
        url = f"https://github.com/{repo}/actions/runs/{run_id}"
        if re.fullmatch(r"[1-9][0-9]*", attempt):
            url += f"/attempts/{attempt}"
        lines.append(f"**Build:** [GitHub Actions]({url})")
    return title, "\n".join(lines)


def proposal_message(version: str, parent: str, paths: list[str]) -> str:
    version_name(version)
    if parent != "base":
        version_name(parent)
    return "\n".join([
        f"Add support for [FFmpeg n{version}](https://github.com/FFmpeg/FFmpeg/tree/n{version}).",
        "", f"**Configuration:** inherits `{parent}`.", "", "## Changes",
        *[f"- `{path}`" for path in paths],
        "", PROPOSAL_START, "## Verification", "",
        "Awaiting version-scope validation and the full MSVC build matrix (16 variants).",
        PROPOSAL_END, "", "This PR does not publish a release or create a tag.",
    ])


def proposal_status(body: str, source: dict, verified: bool, repo: str) -> str:
    """Update only the generated verification section; preserve maintainer notes."""
    if PROPOSAL_START not in body and PROPOSAL_END not in body:
        return body
    if body.count(PROPOSAL_START) != 1 or body.count(PROPOSAL_END) != 1:
        raise ValueError("Invalid version proposal markers")
    a, b = body.index(PROPOSAL_START), body.index(PROPOSAL_END)
    if b <= a:
        raise ValueError("Reversed version proposal markers")
    conclusion = source.get("run_conclusion")
    status = ("Version scope and MSVC build matrix: 16/16 passed." if verified else
              {"failure": "CI failed. See the build logs for details.",
               "success": "CI completed; the complete version matrix has not been verified.",
               "cancelled": "CI cancelled.", "timed_out": "CI timed out."}.get(conclusion, "Awaiting full MSVC validation."))
    run, attempt = source["run_id"], source["run_attempt"]
    if type(run) is not int or type(attempt) is not int or run < 1 or attempt < 1:
        raise ValueError("Invalid CI run identity")
    head = commit_sha(source["head_sha"])
    previous = re.findall(r"(?m)^<!-- ffbuild-proposal-ci:v1 ([0-9a-f]{40}) ([1-9][0-9]*) ([1-9][0-9]*) -->$", body[a:b])
    if len(previous) > 1:
        raise ValueError("Duplicate proposal CI identity")
    if previous and previous[0][0] == head and (int(previous[0][1]), int(previous[0][2])) > (run, attempt):
        return body
    url = f"https://github.com/{repo}/actions/runs/{run}/attempts/{attempt}"
    new = "\n".join([PROPOSAL_START, f"<!-- ffbuild-proposal-ci:v1 {head} {run} {attempt} -->", "## Verification", "", status,
                      f"**CI:** [Run {run}, attempt {attempt}]({url})", PROPOSAL_END])
    return body[:a] + new + body[b+len(PROPOSAL_END):]


def proposal_pending(body: str, source: dict, new_head: str, repo: str) -> str:
    """A repair commit invalidates the previous HEAD's visible CI result."""
    previous_head = commit_sha(source["head_sha"])
    new_head = commit_sha(new_head)
    if previous_head == new_head:
        raise ValueError("Repair must change the PR HEAD")
    # Retain the earlier failed CI link as context, not as current verification.
    updated = proposal_status(body, dict(source, run_conclusion="pending"), False, repo)
    if PROPOSAL_START not in updated:
        return updated
    a, b = updated.index(PROPOSAL_START), updated.index(PROPOSAL_END)
    run, attempt = source["run_id"], source["run_attempt"]
    url = f"https://github.com/{repo}/actions/runs/{run}/attempts/{attempt}"
    replacement = "\n".join([
        PROPOSAL_START, "## Verification", "",
        "Repair submitted; awaiting the full MSVC build matrix for the new PR HEAD.",
        f"**Current commit:** [{new_head[:12]}](https://github.com/{repo}/commit/{new_head})",
        f"**Previous CI:** [Run {run}, attempt {attempt}]({url})", PROPOSAL_END,
    ])
    return updated[:a] + replacement + updated[b+len(PROPOSAL_END):]


def repair_title(version: str, subject: str = "") -> str:
    """Accept a concise English conventional-commit subject for this target only."""
    version_name(version)
    prefix = f"fix({version}): "
    if (isinstance(subject, str) and subject.startswith(prefix) and
            0 < len(subject) <= 120 and
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,/_()+:\-]*", subject[len(prefix):])):
        return subject
    return prefix + "repair failed MSVC build"
