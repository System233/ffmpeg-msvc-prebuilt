"""User-facing GitHub Markdown; machine identities remain separate."""
from __future__ import annotations

import re

from .identity import normalize_version
from .markdown import render_template
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
    downloads = ""
    if records:
        arch = {r["triplet"].removesuffix("-windows") for r in records}
        licenses = {r["license"].upper() for r in records}
        linkages = {r["linkage"] for r in records}
        packages = []
        if "static" in linkages:
            packages.append("| Static | Standalone FFmpeg executables |")
        if "shared" in linkages:
            packages.append("| Shared | Executables, DLLs and release SDK |")
        if any("debug" in r.get("assets", {}) for r in records):
            packages.append("| Debug Add-on | Debug libraries and Release/Debug PDBs; extract over matching Shared Binary |")
        if any("develop" in r.get("assets", {}) for r in records):
            packages.append("| Develop | Release SDK, debug libraries and symbols |")
        architectures = ", ".join(a.upper() if a.startswith("arm") else a
                                  for a in ("x86", "x64", "arm", "arm64") if a in arch)
        downloads = "\n".join([
            "", "## Downloads", "", "| Package | Contents |", "| --- | --- |", *packages,
            "", f"**Architectures:** {architectures}",
            "**Licenses:** " + " / ".join(l for l in ("LGPL", "GPL") if l in licenses),
            "", "License notices and an SPDX SBOM are included in each archive.",
            "", "## Source and build", "",
        ])
    if snapshot:
        source = (records or [{}])[0].get("source_commit")
        if source:
            source = commit_sha(source)
            source_line = f"**Source:** [FFmpeg {version}](https://github.com/FFmpeg/FFmpeg/commit/{source}) ({source[:12]})"
        else:
            source_line = f"**Source:** FFmpeg {version} (Master snapshot)"
    else:
        source_line = f"**Source:** [FFmpeg n{version}](https://github.com/FFmpeg/FFmpeg/tree/n{version})"
    build = ""
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) and re.fullmatch(r"[1-9][0-9]*", run_id):
        url = f"https://github.com/{repo}/actions/runs/{run_id}"
        if re.fullmatch(r"[1-9][0-9]*", attempt):
            url += f"/attempts/{attempt}"
        build = f"\n**Build:** [GitHub Actions]({url})"
    return title, render_template("release.md", downloads=downloads, source=source_line, build=build)


def _verification(status: str, references: str = "", marker: str = "") -> str:
    # The managed section is also updated independently of the initial PR.
    return "\n".join(part for part in (PROPOSAL_START, marker, "## Verification\n\n" + status + references, PROPOSAL_END) if part)


def proposal_message(version: str, parent: str, paths: list[str]) -> str:
    version_name(version)
    if parent != "base":
        version_name(parent)
    return render_template("proposal-pr.md", version=version, parent=parent,
                           changes="\n".join(f"- `{path}`" for path in paths),
                           verification=_verification("Awaiting version-scope validation and the full configured MSVC build matrix."))


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
    status = ("Version scope and complete MSVC build matrix passed." if verified else
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
    new = _verification(status, f"\n**CI:** [Run {run}, attempt {attempt}]({url})",
                        f"<!-- ffbuild-proposal-ci:v1 {head} {run} {attempt} -->")
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
    replacement = _verification(
        "Repair submitted; awaiting the full MSVC build matrix for the new PR HEAD.",
        f"\n**Current commit:** [{new_head[:12]}](https://github.com/{repo}/commit/{new_head})"
        f"\n**Previous CI:** [Run {run}, attempt {attempt}]({url})")
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
