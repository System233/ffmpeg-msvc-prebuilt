"""CI infrastructure helpers: MSVC SDK selection and dependency submission.

The FFmpeg build itself uses native vcpkg install.  This module is not a public command-line interface.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from ffvcpkg import command as vcpkg_command, environment

from .versions import ROOT


def patch_arm_sdk() -> None:
    """Restore the original ARM SDK workaround (c80f908), including empty values."""
    from .targets import ci_setting
    sdk = ci_setting("ARM_WINDOWS_SDK")
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", sdk):
        raise ValueError("Invalid ARM_WINDOWS_SDK")
    result = subprocess.run(["vswhere", "-all", "-legacy", "-property", "installationPath"],
                            capture_output=True, text=True, check=True)
    patched = 0
    found_files: list[Path] = []
    for location in result.stdout.splitlines():
        if not location.strip():
            continue
        path = Path(location.strip()) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
        if not path.is_file():
            continue
        found_files.append(path)
        source = path.read_bytes()
        # The original working patch used \\S*: the Windows 2022 image can
        # leave __VCVARSALL_WINSDK empty.  Using \\S+ incorrectly rejects it.
        updated, changes = re.subn(rb"(?im)(set\s+__VCVARSALL_WINSDK\s*=)\S*",
                                   rb"\g<1>" + sdk.encode("ascii"), source)
        if changes:
            if updated != source:
                path.write_bytes(updated)
            patched += 1
            print(f"ARM SDK pinned to {sdk}: {path}", flush=True)
    if not patched:
        if not found_files:
            raise RuntimeError("ARM SDK workaround found no vcvarsall.bat via vswhere")
        raise RuntimeError(f"ARM SDK workaround found vcvarsall.bat but no "
                           f"__VCVARSALL_WINSDK assignment in: {found_files}")


def submit_dependencies(*, vcpkg_root: Path, triplet: str | None = None) -> None:
    """Request the native vcpkg dependency graph for GitHub submission."""
    from .seed import seed_identity
    from .versions import generate_all
    from .master import master_metadata
    from .targets import configured_triplets
    triplets = (triplet,) if triplet is not None else configured_triplets()
    if not set(triplets) <= set(configured_triplets()):
        raise ValueError("Dependency submission Triplet is not configured")
    executable = vcpkg_root / ("vcpkg.exe" if os.name == "nt" else "vcpkg")
    if not executable.is_file():
        raise FileNotFoundError(executable)
    if "arm-windows" in triplets:
        patch_arm_sdk()
    generate_all(master=master_metadata())
    for target in triplets:
        _, plan = seed_identity(triplet=target, binary=executable)
        _submit_dependency_plan(vcpkg_root, executable, target, plan)


def _submit_dependency_plan(vcpkg_root: Path, executable: Path, triplet: str, plan: dict) -> None:
    from .native_abi import read_nuget_abis
    env = os.environ.copy()
    env.pop("GITHUB_SERVER_URL", None)
    env.update({"VCPKG_FEATURE_FLAGS": "dependencygraph",
                "VCPKG_OVERLAY_PORTS": str(ROOT / "ports"),
                "VCPKG_OVERLAY_TRIPLETS": str(ROOT / "triplets"),
                "VCPKG_ROOT": str(vcpkg_root)})
    # vcpkg's native dependency submission is manifest-only. Use a temporary
    # consumer project per compatible batch, NOT a generated cache Port.
    for index, batch in enumerate(plan["batches"]):
        dependencies = []
        for spec in sorted(batch["specs"].values()):
            name, features, arch = re.fullmatch(r"([a-z0-9-]+)\[([a-z0-9,-]+)\]:([a-z0-9-]+)", spec).groups()
            dep = {"name": name, "default-features": False}
            if arch != triplet:
                dep["host"] = True
            selected = sorted(set(features.split(",")) - {"core"})
            if selected:
                dep["features"] = selected
            dependencies.append(dep)
        with tempfile.TemporaryDirectory(prefix="ffbuild-dependency-submission-") as scratch:
            project = Path(scratch)
            (project / "vcpkg.json").write_text(json.dumps({"dependencies": dependencies}), encoding="utf-8")
            # Use the same pinned built-in registry as classic-mode Seed
            # installs. Importing a separate manifest registry baseline would
            # silently select different ports (and can require a network fetch).
            env["GITHUB_WORKFLOW"] = f"Dependency Submission ({triplet}, batch {index + 1})"
            args = ["install", f"--triplet={triplet}", "--dry-run",
                    f"--x-manifest-root={project}", f"--x-install-root={project / 'installed'}"]
            output = project / "packages.config"
            # Validate manifest mode against the classic native plan before
            # enabling GitHub submission. No network submission during probe.
            subprocess.run(vcpkg_command([*args, f"--x-write-nuget-packages-config={output}"],
                                          binary=executable, env=dict(env, VCPKG_FEATURE_FLAGS="")), cwd=project,
                           env=environment(dict(env, VCPKG_FEATURE_FLAGS="")), check=True)
            if read_nuget_abis(output) != batch["abis"]:
                raise RuntimeError("Dependency submission graph differs from native Seed plan")
            subprocess.run(vcpkg_command(args, binary=executable, env=env), cwd=project,
                           env=environment(env), check=True)
