"""Minimal project overlay adapter for native vcpkg commands.

This module deliberately does not plan builds, resolve dependencies, or
interpret publication metadata.  vcpkg retains full ownership of its ABI
cache, dependency graph and install/build lifecycle.
"""

from __future__ import annotations

import os
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
        if not any(a == "--overlay-ports" or a.startswith("--overlay-ports=") for a in args):
            generated = ROOT / "_work" / "ffbuild" / "generated-ports"
            if generated.is_dir():
                args.append(f"--overlay-ports={generated}")
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
