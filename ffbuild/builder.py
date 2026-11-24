"""CI infrastructure helpers only: vcpkg bootstrap and dependency submission.

The FFmpeg build itself is a native vcpkg install in the workflow, not an
ffbuild command.  This module is not a public command-line interface.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from ffvcpkg import command as vcpkg_command

from .port import generate_seed_port
from .versions import ROOT


VCPKG_TAG = "2026.06.01"


def bootstrap(vcpkg_root: Path, *, tag: str = VCPKG_TAG) -> Path:
    executable = vcpkg_root / ("vcpkg.exe" if os.name == "nt" else "vcpkg")
    if executable.is_file():
        return executable
    if vcpkg_root.exists() and any(vcpkg_root.iterdir()):
        raise RuntimeError("Existing vcpkg directory has no executable")
    vcpkg_root.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--branch", tag, "--depth", "1",
                    "https://github.com/microsoft/vcpkg.git", str(vcpkg_root)], check=True)
    if os.name != "nt":
        raise RuntimeError("Native vcpkg dependency submission requires Windows")
    subprocess.run(["cmd", "/c", str(vcpkg_root / "bootstrap-vcpkg.bat")],
                   cwd=vcpkg_root, check=True)
    if not executable.is_file():
        raise FileNotFoundError(executable)
    return executable


def patch_arm_sdk() -> None:
    """Preserve the existing Windows ARM SDK selection workaround in CI."""
    result = subprocess.run(["vswhere", "-all", "-legacy", "-property", "installationPath"],
                            capture_output=True, text=True, check=True)
    patched = 0
    for location in result.stdout.splitlines():
        path = Path(location.strip()) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
        if not path.is_file():
            continue
        source = path.read_bytes()
        updated, changes = re.subn(rb"(?im)(set\s+__VCVARSALL_WINSDK\s*=)\S+",
                                   rb"\g<1>10.0.22621.0", source)
        if changes:
            path.write_bytes(updated)
            patched += 1
    if not patched:
        raise RuntimeError("ARM SDK workaround could not locate vcvarsall.bat")


def submit_dependencies(*, vcpkg_root: Path, triplet: str) -> None:
    """Request the native vcpkg dependency graph for GitHub submission."""
    port = generate_seed_port()
    executable = bootstrap(vcpkg_root)
    manifest = json.loads((port / "vcpkg.json").read_text(encoding="utf-8"))
    features = [f"--x-feature={name}" for name in manifest.get("features", {})]
    if not features:
        return
    env = os.environ.copy()
    env.pop("GITHUB_SERVER_URL", None)
    env.update({"VCPKG_FEATURE_FLAGS": "dependencygraph",
                "VCPKG_OVERLAY_PORTS": str(ROOT / "ports"),
                "VCPKG_OVERLAY_TRIPLETS": str(ROOT / "triplets"),
                "VCPKG_ROOT": str(vcpkg_root),
                "GITHUB_WORKFLOW": f"Dependency Submission ({triplet})"})
    subprocess.run(vcpkg_command(["install", *features, f"--triplet={triplet}", "--dry-run"],
                                 binary=executable), cwd=port, env=env, check=True)
