"""Windows build execution. No nested Python command invocation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .versions import ROOT, generate

VCPKG_TAG = "2026.06.01"
INSTALL_OPTIONS = ("--x-abi-tools-use-exact-versions",)


def _run(args: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    print("+ " + " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd or ROOT, env=env, check=True)


def bootstrap(vcpkg_root: Path, *, tag: str = VCPKG_TAG) -> Path:
    """Clone and bootstrap the pinned vcpkg tool only when necessary."""
    exe = vcpkg_root / ("vcpkg.exe" if os.name == "nt" else "vcpkg")
    if exe.is_file():
        return exe
    if vcpkg_root.exists() and any(vcpkg_root.iterdir()):
        raise RuntimeError(f"vcpkg root exists but no executable found: {vcpkg_root}")
    vcpkg_root.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--branch", tag, "--depth", "1",
          "https://github.com/microsoft/vcpkg.git", str(vcpkg_root)])
    if os.name != "nt":
        raise RuntimeError("FFmpeg MSVC compilation requires a Windows runner")
    _run(["cmd", "/c", str(vcpkg_root / "bootstrap-vcpkg.bat")], cwd=vcpkg_root)
    if not exe.is_file():
        raise FileNotFoundError(f"vcpkg bootstrap did not produce {exe}")
    return exe


def patch_arm_sdk() -> None:
    """Preserve the existing ARM vcvarsall workaround in the Python build layer."""
    result = subprocess.run(
        ["vswhere", "-all", "-legacy", "-property", "installationPath"],
        capture_output=True, text=True, check=True,
    )
    installations = [Path(p.strip()) for p in result.stdout.splitlines() if p.strip()]
    count = 0
    for root in installations:
        path = root / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
        if not path.is_file():
            continue
        raw = path.read_bytes()
        updated, n = re.subn(
            rb"(?im)(set\s+__VCVARSALL_WINSDK\s*=)\S+",
            rb"\g<1>10.0.22621.0",
            raw,
        )
        if n:
            path.write_bytes(updated)
            count += 1
    if count == 0:
        raise RuntimeError("ARM Windows SDK workaround could not find a patchable vcvarsall.bat")


def build_job(job: dict, *, vcpkg_root: Path, cache_dir: Path,
              output_dir: Path, bootstrap_tool: bool = True) -> list[Path]:
    """Build all selected licenses/linkages for one version+triplet job."""
    if sys.platform != "win32":
        raise RuntimeError("Building MSVC artifacts requires Windows")
    exe = bootstrap(vcpkg_root) if bootstrap_tool else vcpkg_root / "vcpkg.exe"
    if not exe.is_file():
        raise FileNotFoundError(exe)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if job["triplet"] == "arm-windows":
        patch_arm_sdk()

    env = os.environ.copy()
    env["VCPKG_OVERLAY_PORTS"] = str(ROOT / "ports")
    env["VCPKG_OVERLAY_TRIPLETS"] = str(ROOT / "triplets")
    env["VCPKG_BINARY_SOURCES"] = f"clear;files,{cache_dir},readwrite"
    env["VCPKG_FORCE_DOWNLOADED_BINARIES"] = "1"
    env.setdefault("VCPKG_ROOT", str(vcpkg_root))

    # Direct import of the packaging library (not another Python process).
    # Compatibility with the current packager's top-level ffport/ops imports.
    # This disappears when the packager is folded into ffbuild.artifacts.
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from scripts.package_release import main as package_release

    outputs: list[Path] = []
    for target in job["targets"]:
        license_ = target["license"]
        linkage = target["linkage"]
        print(f"Building {job['id']} {license_}/{linkage}", flush=True)
        generate(job["yaml"], revision_override=int(job["revision"]),
                 ref=job.get("ref") or None, sha512=job.get("sha512") or None)

        enabled_features = f"all-{license_}"
        if linkage == "static":
            enabled_features += ",static"
        _run(
            [str(exe), "install", f"ffmpeg[{enabled_features}]", "ffmpeg-tester",
             f"--triplet={job['triplet']}", "--recurse", *INSTALL_OPTIONS],
            env=env,
        )
        pack_args = [
            "--port-dir", str(vcpkg_root / "packages" / f"ffmpeg_{job['triplet']}"),
            "--license", license_, "--output-dir", str(output_dir),
        ]
        if job.get("ref"):
            pack_args += ["--ref", job["ref"]]
        package_release(pack_args)
        from scripts.ops.naming import build_variant_id
        variant_id = build_variant_id(
            version=job["version"], revision=int(job["revision"]),
            triplet=job["triplet"], license=license_, linkage=linkage,
        )
        metadata = output_dir / f"{variant_id}.var.yaml"
        if not metadata.is_file():
            raise FileNotFoundError(f"Packager did not produce expected variant: {metadata}")
        data = yaml.safe_load(metadata.read_text(encoding="utf-8"))
        if data["variant_id"] != variant_id:
            raise ValueError("Packaged variant ID does not match the planned job")
        outputs.append(metadata)
    return outputs


def prepare(*, vcpkg_root: Path, cache_dir: Path,
            triplet: str, download_only: bool = False) -> None:
    """Prewarm dependency cache, matching the old per-feature seed semantics."""
    from scripts.ffport.deps_port import generate_deps_port

    generate_deps_port()
    exe = bootstrap(vcpkg_root)
    manifest = json.loads((ROOT / "ports" / "ffmpeg-deps" / "vcpkg.json").read_text(encoding="utf-8"))
    enabled = list(manifest.get("features", {}))
    if not enabled:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "VCPKG_OVERLAY_PORTS": str(ROOT / "ports"),
        "VCPKG_OVERLAY_TRIPLETS": str(ROOT / "triplets"),
        "VCPKG_BINARY_SOURCES": f"clear;files,{cache_dir},readwrite",
    })
    if download_only:
        _run([
            str(exe), "install", f"ffmpeg-deps[{','.join(enabled)}]",
            f"--triplet={triplet}", "--recurse", "--only-downloads",
            *INSTALL_OPTIONS,
        ], env=env)
        return
    if triplet == "arm-windows":
        patch_arm_sdk()
    install_root = vcpkg_root.parent / "ffbuild-seed-installed"
    for feature in enabled:
        try:
            _run([
                str(exe), "install", f"ffmpeg-deps[{feature}]",
                f"--triplet={triplet}", "--recurse",
                f"--x-install-root={install_root}", *INSTALL_OPTIONS,
            ], env=env)
        finally:
            shutil.rmtree(install_root, ignore_errors=True)


def submit_dependencies(*, vcpkg_root: Path, triplet: str) -> None:
    """Submit vcpkg's native SBOM/dependency graph without YAML shell logic."""
    from scripts.ffport.deps_port import generate_deps_port

    generate_deps_port()
    exe = bootstrap(vcpkg_root)
    manifest_dir = ROOT / "ports" / "ffmpeg-deps"
    manifest = json.loads((manifest_dir / "vcpkg.json").read_text(encoding="utf-8"))
    flags = [f"--x-feature={name}" for name in manifest.get("features", {})]
    if not flags:
        return
    env = os.environ.copy()
    env.pop("GITHUB_SERVER_URL", None)  # vcpkg dependency-graph workaround
    env["VCPKG_FEATURE_FLAGS"] = "dependencygraph"
    env["VCPKG_OVERLAY_PORTS"] = str(ROOT / "ports")
    env["VCPKG_OVERLAY_TRIPLETS"] = str(ROOT / "triplets")
    env["VCPKG_ROOT"] = str(vcpkg_root)
    env["GITHUB_WORKFLOW"] = f"Dependency Submission ({triplet})"
    _run([str(exe), "install", *flags, f"--triplet={triplet}", "--dry-run"],
         cwd=manifest_dir, env=env)
