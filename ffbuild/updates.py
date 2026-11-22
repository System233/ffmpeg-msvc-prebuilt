"""Discover and create upstream version PRs without nested Python CLIs."""

from __future__ import annotations

import os
import re
import subprocess
import sys

from .versions import ROOT

ops = str(ROOT / "scripts" / "ops")
if ops not in sys.path:
    sys.path.insert(0, ops)

from scripts.ops import scan_updates, create_version_pr
from scripts.find_closest_yaml import find_closest_yaml


def discover() -> list[str]:
    upstream = scan_updates.fetch_upstream_tags()
    local = scan_updates.scan_local_yamls()
    port_pattern = re.compile(r"^ffmpeg-(\d+)-(\d+)(?:-(\d+))?$")
    for directory in (ROOT / "ports").iterdir():
        match = port_pattern.fullmatch(directory.name)
        if directory.is_dir() and match:
            local.add(tuple(int(x or 0) for x in match.groups()))
    return [
        f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"
        for major, minor, patch in upstream if (major, minor, patch) not in local
    ]


def apply_versions(new: list[str], *, sha512: str = "") -> None:
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("GH_TOKEN is required to create upstream version pull requests")
    # Let gh manage Git authentication without embedding credentials in URLs.
    subprocess.run(["gh", "auth", "setup-git"], cwd=ROOT, check=True)
    for version in new:
        if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
            raise ValueError(f"Invalid upstream FFmpeg version: {version}")
        if (ROOT / "ffmpeg" / f"{version}.yaml").exists():
            continue
        # The prior manual workflow enforced this check in Bash; retain it here.
        tag = f"refs/tags/n{version}"
        probe = subprocess.run(
            ["git", "ls-remote", "--exit-code", "--tags",
             "https://github.com/FFmpeg/FFmpeg.git", tag],
            cwd=ROOT, capture_output=True, text=True,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            raise ValueError(f"Upstream FFmpeg tag does not exist: n{version}")
        nearest = find_closest_yaml(version)
        args = ["--version", version, "--closest-yaml", nearest]
        if sha512:
            args += ["--sha512", sha512]
        create_version_pr.main(args)
