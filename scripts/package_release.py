#!/usr/bin/env python3
"""
package_release.py - Package FFmpeg vcpkg build artifacts into release ZIPs.

For each build variant, ``main()`` produces one or two ZIP archives
(depending on linkage) plus a single ``.var.yaml`` metadata file.

Most metadata is automatically detected from CONTROL / BUILD_INFO and
the directory name.  ``--license`` and ``--ffmpeg-ref`` can override
auto-detection (CI uses them as single source of truth).

Usage
-----
    # CI — explicit overrides
    python scripts/package_release.py \\
        --port-dir packages/ffmpeg-8-1-1_x64-windows \\
        --license gpl

    # Local — fully automatic
    python scripts/package_release.py \\
        --port-dir packages/ffmpeg-8-1-1_x64-windows

    # master build
    python scripts/package_release.py \\
        --port-dir packages/ffmpeg-master_x64-windows \\
        --license gpl --ffmpeg-ref n8.0-1234-abc
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path
from typing import List, Optional, Set, Tuple

import yaml
from datetime import datetime, timezone

from ffport.version import parse_version

from ops.lts import is_lts

from ops.naming import (
    build_variant_id, build_zip_name, build_var_yaml_name, clean_version,
)


# Fixed tool & share subdirectory name (CMake uses this consistently)
TOOL_DIR = "ffmpeg"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dashed(version: str) -> str:
    """Convert '8.1.1' to '8-1-1'."""
    return version.replace(".", "-")


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string (KB / MB)."""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Auto-detection helpers
# ---------------------------------------------------------------------------

def triplet_from_dirname(pkg_dir: Path) -> str:
    """Extract triplet from directory name like ``ffmpeg-8-1-1_x64-windows``."""
    name = pkg_dir.name
    if "_" in name:
        return name.split("_", 1)[1]
    return ""


def parse_build_info(pkg_dir: Path) -> str:
    """Return ``"shared"`` or ``"static"`` from BUILD_INFO ``LibraryLinkage``."""
    info = pkg_dir / "BUILD_INFO"
    if info.is_file():
        for line in info.read_text(encoding="utf-8").splitlines():
            if line.startswith("LibraryLinkage:"):
                val = line.split(":", 1)[1].strip()
                return "shared" if val == "dynamic" else "static"
    return "shared"


def detect_license(features: List[str]) -> str:
    if "license-nonfree" in features:
        return "nonfree"
    if "license-gpl" in features:
        return "gpl"
    return "lgpl"


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------

def find_exes(
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover ffmpeg/ffplay/ffprobe executables.

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    exe_names = ["ffmpeg.exe", "ffplay.exe", "ffprobe.exe"]
    found: List[Tuple[Path, str]] = []

    search_dirs: List[Path] = []
    if pkg_dir is not None:
        search_dirs.append(pkg_dir / "tools" / TOOL_DIR)
        search_dirs.append(pkg_dir / "bin")

    for exe in exe_names:
        for base in search_dirs:
            candidate = base / exe
            if candidate.is_file():
                found.append((candidate, f"bin/{exe}"))
                break
        else:
            print(f"  WARNING: {exe} not found in any expected location")

    return found


def copy_dir_recursively(
    pkg_dir: Optional[Path],
    subdir: str,
    exclude_suffixes: Optional[Set[str]] = None,
) -> List[Tuple[Path, str]]:
    """Recursively collect all files from pkg_dir/subdir/.

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []
    root = (pkg_dir / subdir) if pkg_dir is not None else None
    if root is not None and root.is_dir():
        for f in sorted(root.rglob("*")):
            if f.is_file():
                if exclude_suffixes and f.suffix.lower() in exclude_suffixes:
                    continue
                arcname = str(f.relative_to(pkg_dir))
                found.append((f, arcname))
    return found


def find_share_files(
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover all files from share/ffmpeg/, including CMake find module,
    presets, ffprobe XSD, examples, and SPDX metadata.

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []
    share_dir = (pkg_dir / "share" / TOOL_DIR) if pkg_dir is not None else None

    if share_dir is not None and share_dir.is_dir():
        for src_path in sorted(share_dir.rglob("*")):
            if not src_path.is_file():
                continue
            arcname = str(src_path.relative_to(pkg_dir))
            found.append((src_path, arcname))
    else:
        print("  WARNING: share directory not found")

    return found


def find_license(
    pkg_dir: Optional[Path],
) -> Optional[Tuple[bytes, str]]:
    """Read or generate LICENSE.txt content.

    Returns (content_bytes, arcname) tuple if successful, None otherwise.
    """
    if pkg_dir is not None:
        src = pkg_dir / "share" / TOOL_DIR / "copyright"
        if src.is_file():
            return (src.read_bytes(), "LICENSE.txt")

    print(f"  WARNING: copyright file not found in {pkg_dir} — LICENSE.txt will not be included in archive", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# CONTROL parsing
# ---------------------------------------------------------------------------

def parse_control(pkg_dir: Path) -> dict:
    """Parse CONTROL and return metadata dict.

    Returns {
        "version": str,
        "revision": int,
        "features": List[str],
        "dependencies": List[str],
    }
    """
    control_path = pkg_dir / "CONTROL"
    info: dict = {"version": "", "revision": 0, "features": [], "dependencies": []}
    if not control_path.is_file():
        return info

    features: List[str] = []
    deps_set: Set[str] = set()
    version = ""
    revision = 0

    text = control_path.read_text(encoding="utf-8")
    stanzas = text.strip().split("\n\n")

    for stanza in stanzas:
        feature_name = None
        dep_line = None
        for line in stanza.split("\n"):
            if line.startswith("Version: ") and not version:
                version = line[len("Version: "):].strip()
            elif line.startswith("Port-Version: "):
                revision = int(line[len("Port-Version: "):].strip())
            elif line.startswith("Feature: "):
                feature_name = line[len("Feature: "):].strip()
            elif line.startswith("Depends: "):
                dep_line = line[len("Depends: "):].strip()

        if feature_name:
            features.append(feature_name)
            if dep_line:
                for dep in dep_line.split(","):
                    dep = dep.strip()
                    idx = dep.find("(")
                    if idx != -1:
                        dep = dep[:idx].strip()
                    if dep:
                        deps_set.add(dep)

    info["version"] = version
    info["revision"] = revision
    info["features"] = sorted(features)
    info["dependencies"] = sorted(deps_set)
    return info


# ---------------------------------------------------------------------------
# Main packaging logic
# ---------------------------------------------------------------------------

def collect_files(
    pkg_dir: Optional[Path],
    linkage: str,
    variant_type: str = "binary",
) -> List[Tuple[Path, str]]:
    """Collect files for one variant type.

    *variant_type="binary"*  — release binaries + SDK (no PDBs, no debug)
    *variant_type="develop"* — everything including PDBs and debug/ (shared only)

    Each entry is (source_path, arcname_in_zip).
    """
    collected: List[Tuple[Path, str]] = []

    # 1. Executables (all linkage types, all variants)
    exes = find_exes(pkg_dir)
    collected.extend(exes)
    exe_names = [Path(a).name for _, a in exes]
    if exe_names:
        print(f"  Collected executables: {', '.join(exe_names)}")

    if linkage == "shared":
        if variant_type == "binary":
            collected.extend(copy_dir_recursively(pkg_dir, "bin", exclude_suffixes={'.pdb'}))
            collected.extend(copy_dir_recursively(pkg_dir, "lib"))
            collected.extend(copy_dir_recursively(pkg_dir, "include"))
            print("  Shared binary – release SDK (no PDBs, no debug)")
        else:
            collected.extend(copy_dir_recursively(pkg_dir, "bin"))
            collected.extend(copy_dir_recursively(pkg_dir, "lib"))
            collected.extend(copy_dir_recursively(pkg_dir, "include"))
            collected.extend(copy_dir_recursively(pkg_dir, "debug"))
            print("  Shared develop – full debug SDK")

        share_files = find_share_files(pkg_dir)
        collected.extend(share_files)
        if share_files:
            share_names = [Path(a).name for _, a in share_files]
            print(f"  Collected share files: {', '.join(share_names)}")

    else:
        print("  Static – executables only")

    # BUILD_INFO / CONTROL (all linkage types)
    if pkg_dir:
        for fname in ("BUILD_INFO", "CONTROL"):
            p = pkg_dir / fname
            if p.is_file():
                collected.append((p, fname))
                print(f"  Added {fname}")

    if linkage == "static":
        collected = [(src, Path(arc).name) for src, arc in collected]

    return collected


def create_zip(
    collected: List[Tuple[Path, str]],
    output_path: Path,
    pkg_dir: Optional[Path],
) -> None:
    """Create the zip archive from collected file entries.

    Also embeds LICENSE.txt directly from copyright or fallback text.
    """
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for src_path, arcname in collected:
            zf.write(str(src_path), arcname)

        license_data = find_license(pkg_dir)
        if license_data is not None:
            content_bytes, lic_arcname = license_data
            zf.writestr(lic_arcname, content_bytes)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package FFmpeg vcpkg build artifacts into a release zip.",
    )
    parser.add_argument(
        "--port-dir",
        required=True,
        help="Package directory, e.g. packages/ffmpeg-8-1-1_x64-windows",
    )
    parser.add_argument(
        "--license",
        default=None,
        choices=["lgpl", "gpl", "nonfree"],
        help="License variant (auto-detected from CONTROL if omitted)",
    )
    parser.add_argument(
        "--output-dir",
        default="Release",
        help="Output directory for the zip archive (default: Release)",
    )
    parser.add_argument(
        "--generate-var-yaml",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate variant .var.yaml alongside the zip (default: true)",
    )
    parser.add_argument(
        "--ref",
        default=None,
        help="Git ref (e.g. n8.1.1, n8.0-1234-gabc). Used as-is for ffmpeg_ref; version parsed from it.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Pure version string (e.g. 8.1.1). Prepended 'n' for ffmpeg_ref. Overrides CONTROL.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    pkg_dir = Path(args.port_dir).resolve()
    output_dir = Path(args.output_dir)
    generate_var_yaml = args.generate_var_yaml
    if not pkg_dir.is_dir():
        print(f"ERROR: port directory not found at {pkg_dir}", file=sys.stderr)
        sys.exit(1)

    # ---- Auto-detect from CONTROL + BUILD_INFO + dirname ----
    ctrl = parse_control(pkg_dir)
    control_version = ctrl["version"]
    revision = ctrl["revision"]
    license_variant = args.license or detect_license(ctrl["features"])
    linkage = parse_build_info(pkg_dir)
    triplet = triplet_from_dirname(pkg_dir)

    in_license = f" (auto: {license_variant})" if not args.license else ""
    print(f"Packaging FFmpeg {control_version} ({triplet}, {linkage}, {license_variant}{in_license})")
    print(f"  Package dir: {pkg_dir}")
    print(f"  Revision: {revision}")
    print()

    # ---- Version resolution (priority: --version > --ref > CONTROL) ----
    if args.ref:
        parsed = parse_version(args.ref)
        version_final = parsed["version"]
        ffmpeg_ref_val = args.ref
    elif args.version:
        version_final = args.version
        ffmpeg_ref_val = f"n{args.version}"
    else:
        version_final = control_version
        ffmpeg_ref_val = f"n{control_version}"

    revision_val = revision if revision is not None else 0
    clean_ver = clean_version(version_final)
    zip_base = build_variant_id(
        version=clean_ver, revision=revision_val,
        triplet=triplet, linkage=linkage, license=license_variant,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Binary variant (all linkage types) ----
    print(f"-- Binary variant --")
    bin_collected = collect_files(pkg_dir, linkage, variant_type="binary")
    if not bin_collected:
        print("ERROR: no files collected for binary variant", file=sys.stderr)
        sys.exit(1)

    bin_zip_name = build_zip_name(zip_base)
    bin_zip_path = output_dir / bin_zip_name
    print(f"Creating {bin_zip_path} ...")
    create_zip(bin_collected, bin_zip_path, pkg_dir)
    bin_size = bin_zip_path.stat().st_size
    bin_digest = f"sha256:{sha256_file(bin_zip_path)}"

    assets: dict = {
        "binary": {
            "file": bin_zip_name,
            "size": bin_size,
            "digest": bin_digest,
        }
    }

    bin_count = sum(1 for _, a in bin_collected if a.startswith("bin/"))
    inc_count = sum(1 for _, a in bin_collected if a.startswith("include/"))
    lib_count = sum(1 for _, a in bin_collected if a.startswith("lib/") or a.startswith("debug/lib/"))
    print(f"Done! {bin_count} binary/{inc_count} header/{lib_count} library files in archive")
    print(f"  {bin_zip_path}  ({format_size(bin_size)}, {bin_digest})")
    print()

    # ---- 2. Develop variant (shared only) ----
    if linkage == "shared":
        print(f"-- Develop variant --")
        dev_collected = collect_files(pkg_dir, linkage, variant_type="develop")
        if not dev_collected:
            print("ERROR: no files collected for develop variant", file=sys.stderr)
            sys.exit(1)

        dev_zip_name = build_zip_name(zip_base, dev=True)
        dev_zip_path = output_dir / dev_zip_name
        print(f"Creating {dev_zip_path} ...")
        create_zip(dev_collected, dev_zip_path, pkg_dir)
        dev_size = dev_zip_path.stat().st_size
        dev_digest = f"sha256:{sha256_file(dev_zip_path)}"

        assets["develop"] = {
            "file": dev_zip_name,
            "size": dev_size,
            "digest": dev_digest,
        }

        dev_count = sum(1 for _, a in dev_collected if a.startswith("bin/"))
        inc2 = sum(1 for _, a in dev_collected if a.startswith("include/"))
        lib2 = sum(1 for _, a in dev_collected if a.startswith("lib/") or a.startswith("debug/lib/"))
        print(f"Done! {dev_count} binary/{inc2} header/{lib2} library files in archive")
        print(f"  {dev_zip_path}  ({format_size(dev_size)}, {dev_digest})")
        print()

    # ---- Variant YAML ----
    if generate_var_yaml:
        variant_id = zip_base  # zip_base is already the correct variant_id

        arch = triplet.split("-")[0]

        ref_ver = clean_ver.split("-")[0].split(".")
        major_num = int(ref_ver[0])
        minor_num = int(ref_ver[1])
        lts = is_lts(major_num, minor_num)

        build_date = datetime.now(timezone.utc).isoformat()

        var_data = {
            "variant_id": variant_id,
            "version": version_final,
            "revision": revision_val,
            "arch": arch,
            "triplet": triplet,
            "linkage": linkage,
            "license": license_variant,
            "lts": lts,
            "ffmpeg_ref": ffmpeg_ref_val,
            "build_date": build_date,
            "assets": assets,
            "features": ctrl["features"],
            "dependencies": ctrl["dependencies"],
        }

        var_yaml_path = output_dir / build_var_yaml_name(variant_id)
        with open(var_yaml_path, "w", encoding="utf-8") as fh:
            yaml.dump(var_data, fh, default_flow_style=False, sort_keys=False)
        print(f"  Variant YAML: {var_yaml_path}")

    print(bin_digest)


if __name__ == "__main__":
    main()
