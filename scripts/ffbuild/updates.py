"""Discover upstream FFmpeg tags and propose new version specifications."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import urllib.request
from pathlib import Path

import yaml

from .versions import ROOT, versions, has_source


UPSTREAM = "https://github.com/FFmpeg/FFmpeg.git"
_TAG = re.compile(r"refs/tags/n(\d+)\.(\d+)(?:\.(\d+))?(?:\^\{\})?$")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=True)


def select_new_versions(tags: set[tuple[int, int, int]], local: list[str]) -> list[str]:
    """Advance maintained release lines, never backfill missing historical tags."""
    known = {}
    for name in local:
        version = tuple(map(int, name.split(".")))
        version = version + (0,) * (3 - len(version))
        family = version[:2]
        known[family] = max(known.get(family, version), version)
    latest = {}
    for version in tags:
        family = version[:2]
        latest[family] = max(latest.get(family, version), version)
    newest_family = max(known, default=(0, 0))
    selected = [v for family, v in latest.items()
                if (family in known and v > known[family]) or
                   (family not in known and family > newest_family)]
    return [f"{a}.{b}.{c}" if c else f"{a}.{b}" for a, b, c in sorted(selected)]


def discover() -> list[str]:
    """Discover only new stable releases, never historical gaps."""
    output = _git("ls-remote", "--tags", UPSTREAM).stdout
    tags: set[tuple[int, int, int]] = set()
    for line in output.splitlines():
        if "\t" not in line:
            continue
        match = _TAG.fullmatch(line.split("\t", 1)[1])
        if match:
            number = tuple(int(x or 0) for x in match.groups())
            if number[0] >= 3:
                tags.add(number)
    return select_new_versions(tags, [v for v in versions() if has_source(v)])


def _reference(version: str) -> str:
    """Pick a configuration parent, not an implementation to clone."""
    family = ".".join(version.split(".")[:2])
    if version != family and (ROOT / "ffmpeg" / f"{family}.yaml").is_file():
        return family
    # A new family starts from base.  The PR must receive independent patch
    # review; never silently inherit an unrelated version's patch list.
    return "base"


def _source_sha512(version: str) -> str:
    uri = f"https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n{version}.tar.gz"
    hasher = hashlib.sha512()
    with urllib.request.urlopen(uri, timeout=120) as response:
        while data := response.read(1024 * 256):
            hasher.update(data)
    return hasher.hexdigest()


def _proposal_documents(version: str, checksum: str, *, read=None) -> dict[str, dict]:
    """Compute the exact proposed YAML documents from one immutable base tree."""
    if read is None:
        def read(name):
            file = ROOT / "ffmpeg" / f"{name}.yaml"
            return yaml.safe_load(file.read_text(encoding="utf-8")) if file.is_file() else None
    family = ".".join(version.split(".")[:2])
    old = read(version)
    docs = {}
    if version != family and read(family) is None:
        docs[family] = {"extends": "base", "patches": []}
    if old is not None:
        if not isinstance(old, dict):
            raise ValueError("Invalid version template")
        source = old.get("source") or {}
        if source.get("ref") and source.get("sha512"):
            raise ValueError("Source-backed version already exists")
        declaration = dict(old)
    else:
        declaration = {"extends": family if version != family else "base"}
    declaration["source"] = {"method": "git", "repo": "ffmpeg/ffmpeg",
                             "ref": "n"+chr(36)+"{VERSION}", "sha512": checksum}
    docs[version] = declaration
    return docs


def _create_proposal(version: str, branch: str, label: str, docs: dict[str, dict]) -> None:
    from .messages import proposal_message
    body = proposal_message(version, docs[version].get("extends", "base"),
                            [f"ffmpeg/{name}.yaml" for name in docs])
    subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch,
                    "--title", f"Build FFmpeg {version}", "--label", label,
                    "--body", body], cwd=ROOT, check=True)


def _recover_proposal(version: str, branch: str, remote: str, original: str, checksum: str) -> dict:
    from .autoheal import github
    from .autoheal.models import commit_sha
    from .autoheal.scope import check_pr
    fields = remote.split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}":
        raise ValueError("Invalid orphan branch reference")
    sha = commit_sha(fields[0])
    detail = github.api(f"repos/{github.repository()}/commits/{sha}?per_page=100")
    if (detail.get("author") or {}).get("login") != "ffmpeg-dev[bot]" or (detail.get("committer") or {}).get("login") != "ffmpeg-dev[bot]":
        raise ValueError("Orphan proposal is not authenticated Bot work")
    if (detail.get("commit") or {}).get("message") != f"feat(ffmpeg): propose {version} build spec":
        raise ValueError("Unexpected orphan proposal commit")
    parents = detail.get("parents") or []
    if len(parents) != 1:
        raise ValueError("Orphan proposal must be one commit")
    parent = commit_sha(parents[0]["sha"])
    _git("fetch", "origin", sha)
    _git("merge-base", "--is-ancestor", parent, original)
    def read(name):
        found = subprocess.run(["git", "show", f"{parent}:ffmpeg/{name}.yaml"], cwd=ROOT,
                               capture_output=True, text=True)
        return yaml.safe_load(found.stdout) if found.returncode == 0 else None
    docs = _proposal_documents(version, checksum, read=read)
    paths = check_pr(version, original, sha, ROOT, allow_new=True)
    if set(paths) != {f"ffmpeg/{v}.yaml" for v in docs}:
        raise ValueError("Orphan proposal changed unexpected files")
    for name, expected in docs.items():
        if yaml.safe_load(_git("show", f"{sha}:ffmpeg/{name}.yaml").stdout) != expected:
            raise ValueError("Orphan proposal content differs from expected source")
    return docs


def apply_versions(new: list[str], *, sha512: str = "") -> None:
    """Isolate proposal failures; recover a verified pushed branch without overwriting it."""
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("GH_TOKEN is required to create upstream version pull requests")
    subprocess.run(["gh", "auth", "setup-git"], cwd=ROOT, check=True)
    original = _git("rev-parse", "HEAD").stdout.strip()
    from .release_trigger import ensure_label
    from .autoheal import github
    from .spec import read_spec
    from .autoheal.scope import check_pr
    errors = []
    for version in new:
        try:
            if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
                raise ValueError(f"Invalid FFmpeg release: {version}")
            if (ROOT / "ffmpeg" / f"{version}.yaml").exists():
                source = read_spec(version, directory=ROOT / "ffmpeg")[0].get("source") or {}
                if source.get("ref") and source.get("sha512"):
                    continue
            probe = subprocess.run(["git", "ls-remote", "--exit-code", "--tags",
                                    UPSTREAM, f"refs/tags/n{version}"],
                                   capture_output=True, text=True)
            if probe.returncode or not probe.stdout.strip():
                raise ValueError(f"Upstream FFmpeg tag does not exist: n{version}")
            branch = f"auto/ffmpeg-{version}"
            owner = github.repository().split("/", 1)[0]
            existing = github.api(f"repos/{github.repository()}/pulls?head={owner}:{branch}&state=all")
            if not isinstance(existing, list):
                raise ValueError("Invalid existing proposal listing")
            if existing:
                # A manually closed proposal is a decision, not an invitation
                # to create it again every day. Never overwrite its branch.
                print(f"Already proposed: {version}")
                continue
            remote = _git("ls-remote", "origin", f"refs/heads/{branch}").stdout.strip()
            checksum = sha512 or _source_sha512(version)
            if not re.fullmatch(r"[0-9a-f]{128}", checksum):
                raise ValueError("Invalid source checksum")
            if remote:
                docs = _recover_proposal(version, branch, remote, original, checksum)
                _create_proposal(version, branch, ensure_label(version), docs)
                continue
            docs = _proposal_documents(version, checksum)
            label = ensure_label(version)
            _git("switch", "-c", branch)
            try:
                for name, declaration in docs.items():
                    path = ROOT / "ffmpeg" / f"{name}.yaml"
                    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
                    _git("add", f"ffmpeg/{name}.yaml")
                _git("commit", "-m", f"feat(ffmpeg): propose {version} build spec")
                check_pr(version, original, _git("rev-parse", "HEAD").stdout.strip(), ROOT, allow_new=True)
                _git("push", "-u", "origin", branch)
                _create_proposal(version, branch, label, docs)
            finally:
                _git("switch", "--detach", original)
        except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"{version}: {exc}")
            print(f"::error::{version}: {exc}")
    if errors:
        raise ValueError("Version proposal failures: " + "; ".join(errors))


def main(argv: list[str] | None = None) -> None:
    """CI-only mutation adapter; `ffbuild scan` is intentionally read-only."""
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="python -m ffbuild.updates")
    parser.add_argument("--version", default="")
    parser.add_argument("--sha512", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    found = [args.version] if args.version else discover()
    print(json.dumps(found))
    if args.apply:
        apply_versions(found, sha512=args.sha512)


if __name__ == "__main__":
    main()
