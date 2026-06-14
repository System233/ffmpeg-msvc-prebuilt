#!/usr/bin/env python3
"""
package_release.py - Extract FFmpeg build artifacts from vcpkg and package
them into a standard zip distribution archive.

Usage
-----
    python scripts/package_release.py \\
        --version 8.1.1 \\
        --triplet x64-windows-mixed \\
        --license gpl \\
        --linkage shared \\
        --vcpkg-root D:/Repos/vcpkg

Output
------
    Release/ffmpeg-8.1.1-x64-windows-mixed-shared-gpl.zip
        ├── bin/
        │   ├── ffmpeg.exe
        │   ├── ffplay.exe
        │   ├── ffprobe.exe
        │   ├── avcodec-62.dll          (shared only)
        │   └── ...
        ├── include/
        │   └── libavcodec/, libavformat/, ...
        ├── lib/
        │   ├── avcodec.lib
        │   └── ...
        ├── share/
        │   └── ffmpeg-<version>-<linkage>/
        │       ├── usage
        │       └── copyright
        └── LICENSE.txt
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path
from typing import List, Optional, Set, Tuple


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
# Package directory resolution
# ---------------------------------------------------------------------------

def resolve_package_dir(
    packages_dir: Path,
    triplet: str,
    port_name: str,
) -> Optional[Path]:
    """Find the actual package directory for the given port+triplet.

    Tries, in order:
      1. ``{port_name}_{triplet}``        (custom port, e.g. ffmpeg-8-1-1-shared)
      2. ``{port_name_wo_linkage}_{triplet}``  (no linkage suffix)
      3. ``ffmpeg_{triplet}``             (generic ffmpeg port)
      4. ``ffmpeg-{v}_{triplet}``         (versioned, no linkage)

    Returns the package Path or None.
    """
    # port_name is already versioned (no linkage suffix), use as-is
    versioned = port_name

    candidates = [
        f"{port_name}_{triplet}",
        f"{versioned}_{triplet}",
        f"ffmpeg_{triplet}",
    ]

    for cand in candidates:
        pkg_dir = packages_dir / cand
        if pkg_dir.is_dir():
            return pkg_dir

    return None


# ---------------------------------------------------------------------------
# File discovery helpers
# ---------------------------------------------------------------------------

def find_exes(
    installed_dir: Path,
    packages_dir: Path,
    triplet: str,
    port_name: str,
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover ffmpeg/ffplay/ffprobe executables.

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    exe_names = ["ffmpeg.exe", "ffplay.exe", "ffprobe.exe"]
    found: List[Tuple[Path, str]] = []

    # Determine the tool-subdir name to search under tools/
    # For custom ports: port_name (ffmpeg-8-1-1-shared)
    # For legacy vcpkg ports it could be "ffmpeg" or "ffmpeg-8-1-1"
    tool_subdirs: List[str] = [port_name]

    if pkg_dir is not None:
        # If we found a package dir, check what tools/ subdirs actually exist
        pkg_tools = pkg_dir / "tools"
        if pkg_tools.is_dir():
            existing = sorted(d.name for d in pkg_tools.iterdir() if d.is_dir())
            if existing:
                tool_subdirs = existing

    # Build search locations (in priority order)
    search_dirs: List[Path] = []
    if pkg_dir is not None:
        for ts in tool_subdirs:
            search_dirs.append(pkg_dir / "tools" / ts)
        # Also check bin/ in the package dir
        search_dirs.append(pkg_dir / "bin")
    # Fallback to installed/tools/{port_name}/
    for ts in tool_subdirs:
        search_dirs.append(installed_dir / "tools" / ts)

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
    installed_dir: Path,
) -> List[Tuple[Path, str]]:
    """Discover av*.dll and sw*.dll (shared linkage only).

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []

    # Check package dir bin/ first, then installed/bin/
    bin_candidates = []
    if pkg_dir is not None:
        bin_candidates.append(pkg_dir / "bin")
    bin_candidates.append(installed_dir / "bin")

    for bin_dir in bin_candidates:
        if not bin_dir.is_dir():
            continue
        for dll in sorted(bin_dir.glob("*.dll")):
            # Only collect FFmpeg DLLs (not dependency DLLs)
            stem = dll.stem  # e.g. "avcodec-62"
            base = stem.split("-")[0]  # e.g. "avcodec"
            if base in FFMPEG_LIB_NAMES:
                found.append((dll, f"bin/{dll.name}"))
        if found:
            break  # stop at first directory that yields results

    return found


def find_includes(
    installed_dir: Path,
    pkg_dir: Optional[Path],
) -> List[Tuple[Path, str]]:
    """Discover FFmpeg header files from the standard include directories.

    Only collects headers under FFmpeg-owned subdirectories
    (libavcodec/, libavdevice/, libavfilter/, libavformat/,
     libavutil/, libswresample/, libswscale/).

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []

    candidates = [installed_dir / "include"]
    if pkg_dir is not None:
        candidates.append(pkg_dir / "include")

    inc_root: Optional[Path] = None
    for cand in candidates:
        if cand.is_dir():
            inc_root = cand
            break

    if inc_root is None:
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
    installed_dir: Path,
    pkg_dir: Optional[Path],
    linkage: str,
) -> List[Tuple[Path, str]]:
    """Discover FFmpeg .lib files.

    For *shared* linkage this collects both release and debug import libs.
    For *static*  linkage only release .lib files are collected.

    Only collects FFmpeg-owned libraries (avcodec, avdevice, avfilter,
    avformat, avutil, swresample, swscale).

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []

    # Scan package dir first (most complete), fall back to installed/
    base_dirs: List[Path] = [installed_dir]
    if pkg_dir is not None:
        base_dirs.insert(0, pkg_dir)

    seen: Set[str] = set()

    for base in base_dirs:
        lib_dir = base / "lib"
        if not lib_dir.is_dir():
            continue

        # Release libs
        for lib_file in sorted(lib_dir.glob("*.lib")):
            if is_ffmpeg_lib(lib_file.name):
                arcname = f"lib/{lib_file.name}"
                if arcname not in seen:
                    found.append((lib_file, arcname))
                    seen.add(arcname)

        # Debug libs (shared linkage only)
        if linkage == "shared":
            debug_lib = base / "debug" / "lib"
            if debug_lib.is_dir():
                for lib_file in sorted(debug_lib.glob("*.lib")):
                    if is_ffmpeg_lib(lib_file.name):
                        arcname = f"debug/lib/{lib_file.name}"
                        if arcname not in seen:
                            found.append((lib_file, arcname))
                            seen.add(arcname)

        # If pkg_dir had everything we need, skip scanning installed_dir
        if found and base == base_dirs[0]:
            break

    if not found:
        print("  WARNING: FFmpeg library files not found")

    return found


def find_share_files(
    installed_dir: Path,
    pkg_dir: Optional[Path],
    triplet: str,
    port_name: str,
) -> List[Tuple[Path, str]]:
    """Discover usage / copyright files from share directories.

    Searches all candidate share directories (in priority order) and uses
    the first one that actually contains the requested files.

    Returns list of (source_path, arcname_in_zip) tuples.
    """
    found: List[Tuple[Path, str]] = []
    wanted = ("usage", "copyright")

    # Possible share subdirectory names (in priority order)
    share_names = [
        port_name,                     # ffmpeg-8-1-1
        "ffmpeg",                      # generic
    ]

    # Search root directories (package dir first, then installed)
    search_roots: List[Path] = []
    if pkg_dir is not None:
        search_roots.append(pkg_dir / "share")
    search_roots.append(installed_dir / "share")

    # Collect all (root, sname) candidates, respecting priority order
    candidates: List[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        for sname in share_names:
            cand = root / sname
            if cand.is_dir():
                candidates.append(cand)

    # Find the first candidate that has at least one of the wanted files
    chosen_dir: Optional[Path] = None
    for cand in candidates:
        if any((cand / f).is_file() for f in wanted):
            chosen_dir = cand
            break

    if chosen_dir is None:
        print("  WARNING: share directory with usage/copyright not found")
        return found

    for fname in wanted:
        src = chosen_dir / fname
        if src.is_file():
            arcname = f"share/{port_name}/{fname}"
            found.append((src, arcname))
        else:
            print(f"  WARNING: '{fname}' not found in {chosen_dir}")

    return found


def find_license(
    installed_dir: Path,
    pkg_dir: Optional[Path],
    port_name: str,
) -> Optional[Tuple[bytes, str]]:
    """Read or generate LICENSE.txt content.

    Returns (content_bytes, arcname) tuple if successful, None otherwise.
    """
    # Search in priority order
    copyright_candidates: List[Path] = []
    if pkg_dir is not None:
        copyright_candidates.append(pkg_dir / "share" / port_name / "copyright")
        copyright_candidates.append(pkg_dir / "share" / "ffmpeg" / "copyright")
    copyright_candidates.append(installed_dir / "share" / port_name / "copyright")
    copyright_candidates.append(installed_dir / "share" / "ffmpeg" / "copyright")

    for src in copyright_candidates:
        if src.is_file():
            return (src.read_bytes(), "LICENSE.txt")

    # Fallback generic license note
    text = (
        "FFmpeg\n"
        "======\n"
        "FFmpeg is licensed under the GNU Lesser General Public License (LGPL) version 2.1\n"
        "or later. Some components are licensed under the GNU General Public License (GPL)\n"
        "version 2 or later. See https://ffmpeg.org/legal.html for details.\n"
        "\n"
        "This distribution was built using MSVC via vcpkg.\n"
        "The full copyright text can be found in share/<port>/copyright within this archive.\n"
    )
    return (text.encode("utf-8"), "LICENSE.txt")


# ---------------------------------------------------------------------------
# Main packaging logic
# ---------------------------------------------------------------------------

def collect_files(
    installed_dir: Path,
    packages_dir: Path,
    port_name: str,
    triplet: str,
    linkage: str,
) -> List[Tuple[Path, str]]:
    """Collect all files to be included in the release zip.

    Each entry is (source_path, arcname_in_zip).
    """
    collected: List[Tuple[Path, str]] = []

    # Resolve package directory (may be None for legacy ports)
    pkg_dir = resolve_package_dir(packages_dir, triplet, port_name)

    print(f"  Package dir: {pkg_dir or '(none – using installed/ only)'}")
    print()

    # 1. Executables
    exes = find_exes(installed_dir, packages_dir, triplet, port_name, pkg_dir)
    collected.extend(exes)
    exe_names = [Path(a).name for _, a in exes]
    if exe_names:
        print(f"  Collected executables: {', '.join(exe_names)}")

    # 2. DLLs (shared linkage only)
    dll_count = 0
    if linkage == "shared":
        dlls = find_dlls(pkg_dir, installed_dir)
        collected.extend(dlls)
        dll_count = len(dlls)
        if dlls:
            dll_names = [Path(a).name for _, a in dlls]
            print(f"  Collected {dll_count} DLL(s): {', '.join(dll_names)}")
    else:
        print("  Static linkage – skipping DLL collection")

    # 3. Headers
    includes = find_includes(installed_dir, pkg_dir)
    collected.extend(includes)
    inc_subdirs: Set[str] = set()
    for _, arc in includes:
        parts = Path(arc).parts
        if len(parts) >= 2:
            inc_subdirs.add(parts[1])
    if inc_subdirs:
        print(f"  Collected headers from: {', '.join(sorted(inc_subdirs))}")

    # 4. Libraries
    libs = find_libs(installed_dir, pkg_dir, linkage)
    collected.extend(libs)
    if libs:
        lib_names = sorted(set(Path(a).name for _, a in libs))
        print(f"  Collected {len(libs)} library file(s): {', '.join(lib_names)}")

    # 5. Share files (usage + copyright)
    share_files = find_share_files(installed_dir, pkg_dir, triplet, port_name)
    collected.extend(share_files)
    if share_files:
        share_names = [Path(a).name for _, a in share_files]
        print(f"  Collected share files: {', '.join(share_names)}")

    return collected


def create_zip(
    collected: List[Tuple[Path, str]],
    output_path: Path,
    installed_dir: Path,
    pkg_dir: Optional[Path],
    port_name: str,
) -> None:
    """Create the zip archive from collected file entries.

    Also embeds LICENSE.txt directly from copyright or fallback text.
    """
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for src_path, arcname in collected:
            zf.write(str(src_path), arcname)

        # LICENSE.txt
        license_data = find_license(installed_dir, pkg_dir, port_name)
        if license_data is not None:
            content_bytes, lic_arcname = license_data
            zf.writestr(lic_arcname, content_bytes)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package FFmpeg vcpkg build artifacts into a release zip.",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="FFmpeg version, e.g. 8.1.1",
    )
    parser.add_argument(
        "--triplet",
        required=True,
        help="vcpkg triplet, e.g. x64-windows-mixed",
    )
    parser.add_argument(
        "--license",
        required=True,
        choices=["lgpl", "gpl", "nonfree"],
        help="License variant",
    )
    parser.add_argument(
        "--linkage",
        required=True,
        choices=["shared", "static"],
        help="Linkage type (shared → DLLs, static → static libs)",
    )
    parser.add_argument(
        "--vcpkg-root",
        default=r"D:\Repos\vcpkg",
        help="Vcpkg repository root (default: D:/Repos/vcpkg)",
    )
    parser.add_argument(
        "--output-dir",
        default="Release",
        help="Output directory for the zip archive (default: Release)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    version = args.version
    triplet = args.triplet
    license_variant = args.license
    linkage = args.linkage
    vcpkg_root = Path(args.vcpkg_root)
    output_dir = Path(args.output_dir)

    # ---- Derived paths ----
    installed_dir = vcpkg_root / "installed" / triplet
    packages_dir = vcpkg_root / "packages"
    version_dashed = dashed(version)  # "8.1.1" → "8-1-1"
    port_name = f"ffmpeg-{version_dashed}"  # e.g. ffmpeg-8-1-1

    # ---- Validate environment ----
    if not vcpkg_root.is_dir():
        print(f"ERROR: vcpkg root not found at {vcpkg_root}", file=sys.stderr)
        sys.exit(1)

    if not installed_dir.is_dir():
        print(f"ERROR: installed directory not found at {installed_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Collect files ----
    print(f"Packaging FFmpeg {version} ({triplet}, {linkage}, {license_variant})")
    print(f"  Port name: {port_name}")
    print(f"  Installed: {installed_dir}")

    collected = collect_files(installed_dir, packages_dir, port_name, triplet, linkage)

    if not collected:
        print("ERROR: no files collected – nothing to package", file=sys.stderr)
        sys.exit(1)

    # ---- Create zip ----
    pkg_dir = resolve_package_dir(packages_dir, triplet, port_name)
    zip_name = f"ffmpeg-{version}-{triplet}-{linkage}-{license_variant}.zip"
    zip_path = output_dir / zip_name

    print()
    print(f"Creating {zip_path} ...")
    create_zip(collected, zip_path, installed_dir, pkg_dir, port_name)

    # ---- Report ----
    zip_size = zip_path.stat().st_size
    zip_sha256 = sha256_file(zip_path)

    # Count entries by category
    bin_count = sum(1 for _, a in collected if a.startswith("bin/"))
    inc_count = sum(1 for _, a in collected if a.startswith("include/"))
    lib_count = sum(1 for _, a in collected if a.startswith("lib/") or a.startswith("debug/lib/"))

    print(f"Done! {bin_count} binary/{inc_count} header/{lib_count} library files in archive")
    print(f"  {zip_path}  ({format_size(zip_size)}, SHA256: {zip_sha256})")


if __name__ == "__main__":
    main()
