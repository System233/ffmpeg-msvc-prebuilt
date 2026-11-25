"""Minimal project overlay adapter for native vcpkg commands.

This module deliberately does not plan builds, resolve dependencies, or
interpret publication metadata.  vcpkg retains full ownership of its ABI
cache, dependency graph and install/build lifecycle.
"""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def executable() -> Path:
    configured = os.environ.get("FFVCPKG_BIN")
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"FFVCPKG_BIN not found: {candidate}")
    vcpkg_root = os.environ.get("VCPKG_ROOT")
    if vcpkg_root:
        candidate = Path(vcpkg_root) / ("vcpkg.exe" if os.name == "nt" else "vcpkg")
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"VCPKG_ROOT has no vcpkg executable: {candidate}")
    found = shutil.which("vcpkg")
    if found:
        return Path(found)
    candidate = ROOT / "_work" / "ffbuild" / "vcpkg" / ("vcpkg.exe" if os.name == "nt" else "vcpkg")
    if candidate.is_file():
        return candidate
    raise FileNotFoundError("Cannot locate vcpkg. Set FFVCPKG_BIN or VCPKG_ROOT.")


def command(arguments: list[str], *, binary: Path | None = None) -> list[str]:
    """Forward untouched native arguments, adding only missing overlay paths."""
    if not arguments:
        raise ValueError("A native vcpkg command is required")
    args = list(arguments)
    if args[0] in ("install", "depend-info", "upgrade"):
        generated = ROOT / "_work" / "ffbuild" / "generated-ports"
        overlays: list[Path] = []
        for index, arg in enumerate(args):
            if arg.startswith("--overlay-ports="):
                overlays.append(Path(arg.split("=", 1)[1]))
            elif arg == "--overlay-ports":
                if index + 1 >= len(args):
                    raise ValueError("--overlay-ports requires a directory")
                overlays.append(Path(args[index + 1]))
        for port in overlays:
            if port.resolve() == generated.resolve():
                raise ValueError(
                    "The generated-ports parent contains multiple ffmpeg versions; "
                    "select one direct ffmpeg-<version> Port directory")
        needs_ffmpeg = any(re.fullmatch(
            r"ffmpeg(?:\[[^\]]+\])?(?::[a-z0-9-]+)?|ffmpeg-tester(?::[a-z0-9-]+)?",
            argument) for argument in args[1:])
        if needs_ffmpeg and not any(
            (port / "vcpkg.json").is_file() and
            json.loads((port / "vcpkg.json").read_text(encoding="utf-8")).get("name") == "ffmpeg"
            for port in overlays
        ):
            raise ValueError(
                "Install ffmpeg and ffmpeg-tester with an explicit single-version "
                "--overlay-ports=<generated-ports/ffmpeg-version> directory")
        if not overlays:
            args.append(f"--overlay-ports={ROOT / 'ports'}")
        if not any(a == "--overlay-triplets" or a.startswith("--overlay-triplets=") for a in args):
            args.append(f"--overlay-triplets={ROOT / 'triplets'}")
    return [str(binary or executable()), *args]


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args == ["--help"]:
        print("Usage: python -m ffvcpkg <native-vcpkg-command> [arguments...]\n"
              "Adds the project's overlay ports and triplets; all other flags pass through.")
        return 0 if args else 2
    return subprocess.run(command(args), cwd=ROOT, check=False).returncode
