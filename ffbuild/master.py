"""Resolve pinned upstream master source identity for snapshot builds."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path


def master_metadata() -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="ffbuild-master-") as scratch:
        source = Path(scratch) / "ffmpeg"
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "https://github.com/FFmpeg/FFmpeg.git",
             str(source)], check=True,
        )
        description = subprocess.check_output(
            ["git", "-C", str(source), "describe", "--tags", "--abbrev=7"],
            text=True,
        ).strip()
        commit = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True,
        ).strip()
        url = f"https://github.com/FFmpeg/FFmpeg/archive/{commit}.tar.gz"
        digest = hashlib.sha512()
        with urllib.request.urlopen(url, timeout=120) as response:
            while block := response.read(1024 * 1024):
                digest.update(block)
        return {"ref": description, "commit": commit, "sha512": digest.hexdigest()}


def write_github_output(data: dict[str, str], filename: Path) -> None:
    with filename.open("a", encoding="utf-8") as stream:
        for key, value in data.items():
            stream.write(f"{key}={value}\n")
