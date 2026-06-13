#!/usr/bin/env python3
"""
generate_port.py - Generate vcpkg port directories for a given FFmpeg version.

Creates ``ports/ffmpeg-<major>-<minor>-<patch>-shared/`` and
``ports/ffmpeg-<major>-<minor>-<patch>-static/`` each containing a
``vcpkg.json``, ``portfile.cmake``, and ``usage`` file.

Usage
-----
    python scripts/generate_port.py --version 7.1.2
    python scripts/generate_port.py --version 8.1.1 --force
    python scripts/generate_port.py --version 7.1.2 --sha512 abc123...
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

import patchers

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
FFMPEG_SCRIPTS_DIR = SCRIPTS_DIR / "ffmpeg"
EXTRACT_DIR = REPO_ROOT / "_work" / "extracted"
PORTS_DIR = REPO_ROOT / "ports"

# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------

ParsedVersion = Tuple[int, int, int, str, str, str]


def parse_version(version: str) -> ParsedVersion:
    """Parse ``X.Y`` or ``X.Y.Z`` into (major, minor, patch, family, port_version_dashed)."""
    parts = version.split(".")
    if len(parts) not in (2, 3):
        print(f"ERROR: version must be in X.Y or X.Y.Z format, got '{version}'", file=sys.stderr)
        sys.exit(1)
    major_s, minor_s = parts[0], parts[1]
    patch_s = parts[2] if len(parts) == 3 else "0"
    try:
        major = int(major_s)
        minor = int(minor_s)
        patch = int(patch_s)
    except ValueError:
        print(f"ERROR: version parts must be numeric, got '{version}'", file=sys.stderr)
        sys.exit(1)
    family = f"{major}.{minor}"
    # For X.Y versions, omit patch in port name (e.g. ffmpeg-7-0, not ffmpeg-7-0-0)
    if len(parts) == 2:
        port_version_dashed = f"ffmpeg-{major}-{minor}"
    else:
        port_version_dashed = f"ffmpeg-{major}-{minor}-{patch}"
    return major, minor, patch, family, port_version_dashed, version


# ---------------------------------------------------------------------------
# Family directory management
# ---------------------------------------------------------------------------

def ensure_family_dir(major: int, minor: int, family: str, version: str) -> Path:
    """Ensure ``scripts/ffmpeg/{family}/`` exists.

    If the family directory already exists, it is returned as-is.
    Otherwise, try to populate it from ``_work/extracted/{version}/``.
    """
    family_dir = FFMPEG_SCRIPTS_DIR / family

    if family_dir.is_dir():
        print(f"Family dir scripts/ffmpeg/{family}/ already exists")
        return family_dir

    # Try to create from extracted files
    extracted_dir = EXTRACT_DIR / version
    if not extracted_dir.is_dir():
        print(
            f"ERROR: family directory scripts/ffmpeg/{family}/ does not exist, "
            f"and extracted version directory _work/extracted/{version}/ was not found.\n"
            f"Run 'python scripts/sync_from_vcpkg.py' first, or manually create "
            f"scripts/ffmpeg/{family}/ with the required template files.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Family dir scripts/ffmpeg/{family}/ not found — bootstrapping from "
          f"_work/extracted/{version}/")

    # Create family directory
    family_dir.mkdir(parents=True, exist_ok=True)

    # Collect extracted patches (may be at root or in patches/ subdir)
    patch_files = sorted(extracted_dir.glob("*.patch"))
    if patch_files:
        patches_dir = family_dir / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        for pf in patch_files:
            shutil.copy2(str(pf), str(patches_dir / pf.name))
        print(f"  Copied {len(patch_files)} patches")

    # Copy template files
    for template in ("build.sh.in", "FindFFMPEG.cmake.in", "vcpkg-cmake-wrapper.cmake"):
        src = extracted_dir / template
        if src.is_file():
            shutil.copy2(str(src), str(family_dir / template))
        else:
            print(f"  WARNING: {template} not found in _work/extracted/{version}/",
                  file=sys.stderr)

    print(f"  -> Created scripts/ffmpeg/{family}/ with files from "
          f"_work/extracted/{version}/")
    return family_dir


# ---------------------------------------------------------------------------
# SHA512 resolution
# ---------------------------------------------------------------------------

def resolve_sha512(version: str, sha512_arg: str | None) -> str:
    """Resolve the SHA512 checksum for the FFmpeg source tarball.

    Priority:
      1. ``--sha512`` argument
      2. Extract from ``_work/extracted/{version}/portfile.cmake``
      3. Fallback to placeholder ``"TODO"`` with a warning.
    """
    if sha512_arg:
        return sha512_arg

    portfile = EXTRACT_DIR / version / "portfile.cmake"
    if portfile.is_file():
        content = portfile.read_text(encoding="utf-8")
        match = re.search(r"SHA512\s+([a-f0-9]{128})", content)
        if match:
            sha = match.group(1)
            print(f"SHA512: {sha[:16]}... (from _work/extracted/{version}/portfile.cmake)")
            return sha

    print(f"WARNING: SHA512 not found for version {version} — using placeholder 'TODO'",
          file=sys.stderr)
    return "TODO"


# ---------------------------------------------------------------------------
# Feature extraction from original vcpkg port definition
# ---------------------------------------------------------------------------

def extract_features_from_original(version: str) -> dict:
    """Extract features from the original vcpkg port definition.

    Reads ``_work/extracted/{version}/vcpkg.json`` (v4.4+ format) or
    ``_work/extracted/{version}/CONTROL`` (3.x–4.3.x format) and returns
    a dict of non-meta feature names → ``{"description": "..."}``.

    Meta-features (``all``, ``all-gpl``, ``all-nonfree``, ``default``) are
    excluded.
    """
    extracted_dir = EXTRACT_DIR / version

    # Try vcpkg.json first (v4.4+)
    vcpkg_json = extracted_dir / "vcpkg.json"
    if vcpkg_json.is_file():
        data = json.loads(vcpkg_json.read_text(encoding="utf-8"))
        features = data.get("features", {})
    else:
        # Fallback: CONTROL file (3.x–4.3.x)
        control = extracted_dir / "CONTROL"
        if control.is_file():
            features = _parse_control_features(control)
        else:
            print(f"  WARNING: neither vcpkg.json nor CONTROL found in "
                  f"_work/extracted/{version}/", file=sys.stderr)
            return {}

    # Filter: keep only standalone features, exclude meta-features
    # Meta-features bundle many sub-features together and are not meaningful
    # for our per-feature CMake toggle pattern.
    exclude = {"all", "all-gpl", "all-nonfree", "default"}
    standalone_features = {}
    for name, feat in features.items():
        if name in exclude:
            continue
        desc = feat.get("description", "")
        standalone_features[name] = {"description": desc}

    # Ensure core library features are always present (the ffmpeg-port-base.cmake
    # ffmpeg_feature_core macro requires these to exist as features)
    CORE_FEATURES = ["avcodec", "avdevice", "avformat", "avfilter", "swresample", "swscale"]
    for cf in CORE_FEATURES:
        if cf not in standalone_features:
            standalone_features[cf] = {"description": f"Build the {cf} library"}

    return standalone_features


def _parse_control_features(control_path: Path) -> dict:
    """Parse old-style CONTROL format for ``Feature:`` sections.

    Returns a dict mapping feature name → ``{"description": "..."}``.
    """
    content = control_path.read_text(encoding="utf-8")
    features = {}
    current_feature = None
    for line in content.splitlines():
        if line.startswith("Feature:"):
            current_feature = line.split(":", 1)[1].strip()
            features[current_feature] = {"description": ""}
        elif current_feature and line.startswith("Description:"):
            features[current_feature]["description"] = line.split(":", 1)[1].strip()
    return features


# ---------------------------------------------------------------------------
# Host dependencies
# ---------------------------------------------------------------------------

def get_host_deps(major: int, minor: int) -> list[dict]:
    """Determine the list of host dependencies for a given version."""
    deps = [
        {"name": "vcpkg-cmake-get-vars", "host": True},
        {"name": "vcpkg-pkgconfig-get-modules", "host": True},
    ]
    # 8.1+ needs prebuilt-bin2c patch → ffmpeg-bin2c host tool
    if (major, minor) >= (8, 1):
        deps.insert(0, {"name": "ffmpeg-bin2c", "host": True})
    return deps


# ---------------------------------------------------------------------------
# Patch list
# ---------------------------------------------------------------------------

def get_patches(family_dir: Path) -> List[str]:
    """Return sorted list of ``.patch`` filenames from the patches directory."""
    patches_dir = family_dir / "patches"
    if not patches_dir.is_dir():
        print(f"WARNING: patches directory not found at {patches_dir}", file=sys.stderr)
        return []
    patches = sorted(
        f.name for f in patches_dir.iterdir()
        if f.is_file() and f.suffix == ".patch"
    )
    return patches


# ---------------------------------------------------------------------------
# portfile.cmake generation
# ---------------------------------------------------------------------------

def generate_portfile(
    version: str,
    family: str,
    sha512: str,
    patches: List[str],
    ffmpeg_opts: dict | None = None,
) -> str:
    """Generate the ``portfile.cmake`` content."""
    lines = [
        f'set(FFMPEG_VERSION "{version}")',
        f"set(FFMPEG_SHA512 {sha512})",
        f'set(FFMPEG_SHARED_DIR "${{CMAKE_CURRENT_LIST_DIR}}/../../scripts/ffmpeg/{family}")',
    ]
    if ffmpeg_opts:
        base = ffmpeg_opts.get("base", "")
        debug = ffmpeg_opts.get("debug", "")
        lines.append(f'set(FFMPEG_BASE_OPTIONS "{base}")')
        lines.append(f'set(FFMPEG_OPTIONS_DEBUG "{debug}")')
    lines.append("set(FFMPEG_PATCHES")
    for p in patches:
        lines.append(f"    {p}")
    lines.append(")")
    lines.append('set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")')
    lines.append('include("${CMAKE_CURRENT_LIST_DIR}/../../scripts/cmake/ffmpeg-port-base.cmake")')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# vcpkg.json generation
# ---------------------------------------------------------------------------

def generate_vcpkg_json(
    port_name: str,
    version: str,
    linkage: str,
    linkage_desc: str,
    host_deps: list[dict],
    features: dict,
    ctx: dict,
) -> str:
    """Generate the ``vcpkg.json`` content with per-version feature list."""
    # Build feature definitions from extracted features
    feature_defs = {}
    for fname, finfo in features.items():
        feature_defs[fname] = {
            "description": finfo.get("description", f"Enable {fname} support"),
        }

    # Add license meta-features (overrides extracted ones if present)
    feature_defs["gpl"] = {
        "description": "GPL license build — includes x264, x265",
        "dependencies": [
            {"name": port_name, "features": ["x264", "x265"]},
        ],
    }
    feature_defs["nonfree"] = {
        "description": "Non-free license build — includes fdk-aac",
        "dependencies": [
            {"name": port_name, "features": ["gpl", "fdk-aac"]},
        ],
    }

    # default-features = all standalone features (no license features)
    default_features = list(features.keys())

    # Hook 3: pre_defaults — filter default features list
    patchers.run("pre_defaults", default_features, ctx)

    deps = [{"name": "ffmpeg-base-deps"}, *host_deps]
    # Hook: post_deps — add/remove version-specific dependencies
    patchers.run("post_deps", deps, ctx)

    json_data = {
        "name": port_name,
        "version": version,
        "port-version": 0,
        "description": [
            f"FFmpeg {version} {linkage_desc} build for MSVC. "
            f"Includes ffmpeg.exe, ffplay.exe, ffprobe.exe.",
            "All codec dependencies are provided by ffmpeg-base-deps virtual port.",
        ],
        "homepage": "https://ffmpeg.org",
        "license": None,
        "default-features": default_features,
        "dependencies": deps,
        "features": feature_defs,
    }
    return json.dumps(json_data, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# usage generation
# ---------------------------------------------------------------------------

DEFAULT_USAGE = """\
ffmpeg provides cmake integration:

    find_package(FFMPEG REQUIRED)
    target_link_libraries(main PRIVATE FFMPEG::ffmpeg)
"""


def resolve_usage(family_dir: Path) -> str:
    """Return the usage file content.

    Priority:
      1. Copy from ``scripts/ffmpeg/{family}/usage`` if it exists.
      2. Use the default content.
    """
    usage_src = family_dir / "usage"
    if usage_src.is_file():
        return usage_src.read_text(encoding="utf-8")
    return DEFAULT_USAGE


# ---------------------------------------------------------------------------
# Port generation
# ---------------------------------------------------------------------------

def generate_port(
    version: str,
    family: str,
    port_version_dashed: str,
    linkage: str,
    sha512: str,
    patches: List[str],
    host_deps: list[dict],
    features: dict,
    family_dir: Path,
    ctx: dict,
    force: bool,
    opts: dict | None = None,
) -> None:
    """Generate a single port directory (shared or static)."""
    port_dir = PORTS_DIR / f"{port_version_dashed}-{linkage}"

    # Check if already exists
    if port_dir.is_dir():
        if not force:
            print(f"  SKIP {port_dir.name} (already exists, use --force to overwrite)")
            return
        shutil.rmtree(str(port_dir))

    # Create directory
    port_dir.mkdir(parents=True, exist_ok=True)

    linkage_desc = "shared (dynamic)" if linkage == "shared" else "static"
    port_name = f"{port_version_dashed}-{linkage}"

    if features:
        feature_names = list(features.keys())
        print(f"  Features: {len(features)} ({', '.join(feature_names[:6])}"
              f"{'…' if len(feature_names) > 6 else ''})")
    else:
        print(f"  Features: none extracted")

    # portfile.cmake
    portfile_content = generate_portfile(version, family, sha512, patches, ffmpeg_opts=opts)
    (port_dir / "portfile.cmake").write_text(portfile_content, encoding="utf-8")

    # vcpkg.json
    vcpkg_content = generate_vcpkg_json(port_name, version, linkage, linkage_desc, host_deps, features, ctx)
    (port_dir / "vcpkg.json").write_text(vcpkg_content, encoding="utf-8")

    # usage
    usage_content = resolve_usage(family_dir)
    (port_dir / "usage").write_text(usage_content, encoding="utf-8")

    # Hook 4: post_generate — optional modification of port directory
    patchers.run("post_generate", str(port_dir), ctx)

    # Count files written
    file_count = len(list(port_dir.iterdir()))
    print(f"Generated ports/{port_dir.name}/ ({file_count} files)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate vcpkg port directories for a given FFmpeg version.",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="FFmpeg version in X.Y.Z format (e.g. 7.1.2)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing port directories",
    )
    parser.add_argument(
        "--sha512",
        default=None,
        help="SHA512 checksum of the FFmpeg source tarball "
             "(128 hex chars; auto-detected if omitted)",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    version = args.version
    force = args.force
    sha512_arg = args.sha512

    # ---- Step 1: Version parsing ----
    major, minor, patch, family, port_version_dashed, _ = parse_version(version)
    print(f"Version: {version} → family={family}, name={port_version_dashed}")

    # ---- Step 1b: Feature extraction from original port ----
    features = extract_features_from_original(version)

    # Ensure core library features are always present
    CORE_FEATURES = ["avcodec", "avdevice", "avformat", "avfilter", "swresample", "swscale"]
    for cf in CORE_FEATURES:
        if cf not in features:
            features[cf] = {"description": f"Build the {cf} library"}

    # Context for patcher hooks
    ctx = {
        "version": version,
        "family": family,
        "major": major,
        "minor": minor,
        "patch": patch,
    }

    # Hook 1: post_extract — clean up / filter features
    patchers.run("post_extract", features, ctx)

    if features:
        feature_names = list(features.keys())
        print(f"Features: {len(features)} from _work/extracted/{version}/"
              f" ({', '.join(feature_names[:6])}"
              f"{'…' if len(feature_names) > 6 else ''})")
    else:
        print(f"Features: none found in _work/extracted/{version}/")

    # ---- Step 2: Family directory ----
    family_dir = ensure_family_dir(major, minor, family, version)

    # ---- Step 3: SHA512 ----
    sha512 = resolve_sha512(version, sha512_arg)
    if sha512 != "TODO" and len(sha512) != 128:
        print(f"ERROR: SHA512 must be 128 hex characters, got {len(sha512)}", file=sys.stderr)
        sys.exit(1)

    # ---- Step 4: Host dependencies ----
    host_deps = get_host_deps(major, minor)

    # Hook 2: pre_deps — modify host dependencies
    patchers.run("pre_deps", host_deps, ctx)

    # ---- Step 5: Patches ----
    patches = get_patches(family_dir)

    # Hook: pre_patches — filter / modify patch list
    patchers.run("pre_patches", patches, ctx)

    print(f"Patches: {len(patches)} files")

    # ---- Step 5b: Debug options via post_options hook ----
    opts = {"base": "", "debug": ""}
    patchers.run("post_options", opts, ctx)
    print(f"Debug options: base='{opts['base']}', debug='{opts['debug']}'")

    # ---- Step 6-8: Port generation ----
    for linkage in ("shared", "static"):
        generate_port(
            version=version,
            family=family,
            port_version_dashed=port_version_dashed,
            linkage=linkage,
            sha512=sha512,
            patches=patches,
            host_deps=host_deps,
            features=features,
            family_dir=family_dir,
            ctx=ctx,
            force=force,
            opts=opts,
        )


if __name__ == "__main__":
    main()
