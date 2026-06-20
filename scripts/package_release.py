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

from ops.lts import is_lts

from ops.naming import (
    build_variant_id, build_zip_name, build_var_yaml_name, clean_version,
)


# ---------------------------------------------------------------------------
# Constants – FFmpeg library names (without version suffix)
# ---------------------------------------------------------------------------

# .lib / .dll base names that belong to FFmpeg itself
FFMPEG_LIB_NAMES: Set[str] = {
    "avcodec",
    "avdevice",
    "avfilter",
    "avformat",
    "avutil",
    "swresample",
    "swscale",
}

# Fixed tool & share subdirectory name (CMake uses this consistently)
TOOL_DIR = "ffmpeg"

# Sub-directories under include/ that belong to FFmpeg
FFMPEG_INCLUDE_DIRS: Set[str] = {
    "libavcodec",
    "libavdevice",
    "libavfilter",
    "libavformat",
    "libavutil",
    "libswresample",
    "libswscale",
}


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


def is_ffmpeg_lib(name: str) -> bool:
    """Check if a .lib base name is an FFmpeg library (handles debug suffixes)."""
    stem = Path(name).stem  # e.g. "avcodec" or "avcodec.lib" → "avcodec"
    # Strip version suffix if present: "avcodec-62" → "avcodec"
    if "-" in stem:
        stem = stem.split("-")[0]
    # Strip "d" debug suffix: "avcodecd" → "avcodec"
    if stem.endswith("d"):
        stem = stem[:-1]
    return stem in FFMPEG_LIB_NAMES


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


def find_dlls(
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover av*.dll and sw*.dll (shared linkage only).

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []
    bin_dir = (pkg_dir / "bin") if pkg_dir is not None else None

    if bin_dir is not None and bin_dir.is_dir():
        for dll in sorted(bin_dir.glob("*.dll")):
            stem = dll.stem
            base = stem.split("-")[0]
            if base in FFMPEG_LIB_NAMES:
                found.append((dll, f"bin/{dll.name}"))

    return found


def find_pdbs(
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover ffmpeg/ffplay/ffprobe and av*/sw* PDB files (shared linkage).

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    pdb_exe_names = {"ffmpeg", "ffplay", "ffprobe"}
    found: List[Tuple[Path, str]] = []
    bin_dir = (pkg_dir / "bin") if pkg_dir is not None else None

    if bin_dir is not None and bin_dir.is_dir():
        for pdb in sorted(bin_dir.glob("*.pdb")):
            stem = pdb.stem
            base = stem.split("-")[0]
            if base in FFMPEG_LIB_NAMES or stem in pdb_exe_names:
                found.append((pdb, f"bin/{pdb.name}"))

    return found


def find_includes(
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover FFmpeg header files from the standard include directories.

    Only collects headers under FFmpeg-owned subdirectories
    (libavcodec/, libavdevice/, libavfilter/, libavformat/,
     libavutil/, libswresample/, libswscale/).

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []
    inc_root = (pkg_dir / "include") if pkg_dir is not None else None

    if inc_root is None or not inc_root.is_dir():
        print("  WARNING: include directory not found")
        return found

    for subdir_name in sorted(FFMPEG_INCLUDE_DIRS):
        subdir = inc_root / subdir_name
        if not subdir.is_dir():
            print(f"  WARNING: include subdirectory '{subdir_name}' not found")
            continue
        for src_path in sorted(subdir.rglob("*.h")):
            if src_path.is_file():
                relative = src_path.relative_to(inc_root)
                found.append((src_path, f"include/{relative}"))

    return found


def find_libs(
    pkg_dir: Optional[Path],
    linkage: str,
    include_debug: bool = False,
) -> List[Tuple[Path, str]]:
    """Discover FFmpeg .lib files.

    For *shared* linkage with *include_debug=True* this collects both
    release and debug import libs.  Otherwise only release libs.

    Only collects FFmpeg-owned libraries (avcodec, avdevice, avfilter,
    avformat, avutil, swresample, swscale).

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []
    if pkg_dir is None:
        return found

    seen: Set[str] = set()
    lib_dir = pkg_dir / "lib"

    if lib_dir.is_dir():
        for lib_file in sorted(lib_dir.glob("*.lib")):
            if is_ffmpeg_lib(lib_file.name):
                arcname = f"lib/{lib_file.name}"
                if arcname not in seen:
                    found.append((lib_file, arcname))
                    seen.add(arcname)

    if linkage == "shared" and include_debug:
        debug_lib = pkg_dir / "debug" / "lib"
        if debug_lib.is_dir():
            for lib_file in sorted(debug_lib.glob("*.lib")):
                if is_ffmpeg_lib(lib_file.name):
                    arcname = f"debug/lib/{lib_file.name}"
                    if arcname not in seen:
                        found.append((lib_file, arcname))
                        seen.add(arcname)

    if not found:
        print("  WARNING: FFmpeg library files not found")

    return found


def find_share_files(
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover usage / copyright files from share/ffmpeg/.

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []
    wanted = ("usage", "copyright")
    share_dir = (pkg_dir / "share" / TOOL_DIR) if pkg_dir is not None else None

    if share_dir is not None and share_dir.is_dir() and any((share_dir / f).is_file() for f in wanted):
        for fname in wanted:
            src = share_dir / fname
            if src.is_file():
                found.append((src, f"share/{TOOL_DIR}/{fname}"))
    else:
        print("  WARNING: share directory with usage/copyright not found")

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
        # 2. DLLs
        dlls = find_dlls(pkg_dir)
        collected.extend(dlls)
        if dlls:
            dll_names = [Path(a).name for _, a in dlls]
            print(f"  Collected {len(dlls)} DLL(s): {', '.join(dll_names)}")

        if variant_type == "develop":
            # 3. PDBs (develop only)
            pdbs = find_pdbs(pkg_dir)
            collected.extend(pdbs)
            if pdbs:
                pdb_names = [Path(a).name for _, a in pdbs]
                print(f"  Collected {len(pdbs)} PDB(s): {', '.join(pdb_names)}")

        # 4. Headers
        includes = find_includes(pkg_dir)
        collected.extend(includes)
        inc_subdirs: Set[str] = set()
        for _, arc in includes:
            parts = Path(arc).parts
            if len(parts) >= 2:
                inc_subdirs.add(parts[1])
        if inc_subdirs:
            print(f"  Collected headers from: {', '.join(sorted(inc_subdirs))}")

        # 5. Libraries (debug libs only in develop)
        libs = find_libs(pkg_dir, linkage, include_debug=(variant_type == "develop"))
        collected.extend(libs)
        if libs:
            lib_names = sorted(set(Path(a).name for _, a in libs))
            print(f"  Collected {len(libs)} library file(s): {', '.join(lib_names)}")

        if variant_type == "develop" and pkg_dir:
            # 6. Debug bin/ (DLLs + PDBs)
            debug_bin = pkg_dir / "debug" / "bin"
            if debug_bin.is_dir():
                for f in sorted(debug_bin.iterdir()):
                    if f.is_file():
                        collected.append((f, f"debug/bin/{f.name}"))
                print(f"  Collected debug/bin/ files")

        if variant_type == "develop":
            print("  Shared develop – full debug SDK")
        else:
            print("  Shared binary – release SDK")

    else:
        print("  Static – executables only")

    # 7. Share files (always included)
    share_files = find_share_files(pkg_dir)
    collected.extend(share_files)
    if share_files:
        share_names = [Path(a).name for _, a in share_files]
        print(f"  Collected share files: {', '.join(share_names)}")

    # 8. BUILD_INFO / CONTROL (all linkage types)
    if pkg_dir:
        for fname in ("BUILD_INFO", "CONTROL"):
            p = pkg_dir / fname
            if p.is_file():
                collected.append((p, fname))
                print(f"  Added {fname}")

    if linkage == "static":
        # Flatten arcnames to root directory
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
        "--ffmpeg-ref",
        default=None,
        help="FFmpeg git describe ref (for master builds)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    pkg_dir = Path(args.port_dir).resolve()
    output_dir = Path(args.output_dir)
    generate_var_yaml = args.generate_var_yaml
    ffmpeg_ref = args.ffmpeg_ref

    if not pkg_dir.is_dir():
        print(f"ERROR: port directory not found at {pkg_dir}", file=sys.stderr)
        sys.exit(1)

    # ---- Auto-detect from CONTROL + BUILD_INFO + dirname ----
    ctrl = parse_control(pkg_dir)
    version = ctrl["version"]
    revision = ctrl["revision"]
    license_variant = args.license or detect_license(ctrl["features"])
    linkage = parse_build_info(pkg_dir)
    triplet = triplet_from_dirname(pkg_dir)

    in_license = f" (auto: {license_variant})" if not args.license else ""
    print(f"Packaging FFmpeg {version} ({triplet}, {linkage}, {license_variant}{in_license})")
    print(f"  Package dir: {pkg_dir}")
    print(f"  Revision: {revision}")
    print()

    # ---- Build ZIP basename ----
    # version is always the actual version number (never "master").
    # ffmpeg_ref is always set (tag like "n8.1.1" or git describe).
    # revision is always an int (0 for master builds).
    ffmpeg_ref_val = ffmpeg_ref or f"n{version}"
    revision_val = revision if revision is not None else 0
    version_final = version
    clean_ver = clean_version(version)
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
