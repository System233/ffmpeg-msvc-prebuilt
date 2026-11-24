"""Discover upstream FFmpeg tags and propose new version specifications."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import urllib.request
from pathlib import Path

import yaml

from .versions import ROOT, versions


UPSTREAM = "https://github.com/FFmpeg/FFmpeg.git"
_TAG = re.compile(r"refs/tags/n(\d+)\.(\d+)(?:\.(\d+))?(?:\^\{\})?$")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=True)


def discover() -> list[str]:
    """Discover stable tags. Preserve historical patch releases for LTS families."""
    output = _git("ls-remote", "--tags", UPSTREAM).stdout
    tags: set[tuple[int, int, int]] = set()
    for line in output.splitlines():
        if "\t" not in line:
            continue
        match = _TAG.fullmatch(line.split("\t", 1)[1])
        if match:
            number = tuple(int(x or 0) for x in match.groups())
            if number[0] >= 4:
                tags.add(number)
    latest = {major: max(v for v in tags if v[0] == major) for major in {v[0] for v in tags}}
    selected = {v for v in tags if (v[0], v[1]) == (4, 4) or v[1] % 2 == 1}
    selected.update(latest.values())
    local = set(versions())
    return [f"{a}.{b}.{c}" if c else f"{a}.{b}"
            for a, b, c in sorted(selected) if
            (f"{a}.{b}.{c}" if c else f"{a}.{b}") not in local]


def _reference(version: str) -> str:
    """Pick a configuration parent, not an implementation to clone."""
    family = ".".join(version.split(".")[:2])
    if (ROOT / "ffmpeg" / f"{family}.yaml").is_file():
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


def apply_versions(new: list[str], *, sha512: str = "") -> None:
    """Create reviewable version PRs; never commit or push when discovery-only."""
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("GH_TOKEN is required to create upstream version pull requests")
    subprocess.run(["gh", "auth", "setup-git"], cwd=ROOT, check=True)
    original = _git("branch", "--show-current").stdout.strip()
    for version in new:
        if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
            raise ValueError(f"Invalid FFmpeg release: {version}")
        if (ROOT / "ffmpeg" / f"{version}.yaml").exists():
            continue
        probe = subprocess.run(["git", "ls-remote", "--exit-code", "--tags",
                                UPSTREAM, f"refs/tags/n{version}"],
                               capture_output=True, text=True)
        if probe.returncode or not probe.stdout.strip():
            raise ValueError(f"Upstream FFmpeg tag does not exist: n{version}")
        checksum = sha512 or _source_sha512(version)
        if not re.fullmatch(r"[0-9a-f]{128}", checksum):
            raise ValueError("Invalid source checksum")
        yaml_path = ROOT / "ffmpeg" / f"{version}.yaml"
        family = ".".join(version.split(".")[:2])
        family_yaml = ROOT / "ffmpeg" / f"{family}.yaml"
        needs_family = len(version.split(".")) == 3 and not family_yaml.exists()
        branch = f"auto/ffmpeg-{version}"
        _git("switch", "-c", branch)
        try:
            if needs_family:
                family_yaml.write_text(yaml.safe_dump({"extends": "base", "patches": []},
                                                      sort_keys=False), encoding="utf-8")
            declaration = {
                "extends": family if needs_family else _reference(version),
                "revision": 0,
                "source": {"method": "git", "repo": "ffmpeg/ffmpeg",
                           "ref": "n${VERSION}", "sha512": checksum},
            }
            yaml_path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
            if needs_family:
                _git("add", f"ffmpeg/{family}.yaml")
            _git("add", f"ffmpeg/{version}.yaml")
            _git("commit", "-m", f"feat(ffmpeg): propose {version} build spec")
            _git("push", "-u", "origin", branch)
            subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch,
                            "--title", f"Build FFmpeg {version}",
                            "--body", "New FFmpeg release; validate dependency and patch compatibility before merge."],
                           cwd=ROOT, check=True)
        finally:
            _git("switch", original)


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
