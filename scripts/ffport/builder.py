"""Copy ffmpeg-builder files into a generated port directory."""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER_SRC = REPO_ROOT / "scripts" / "cmake"
BUILDER_FILES = [
    "ffmpeg-portfile.cmake",
    "build.sh.in",
    "FindFFmpeg.cmake.in",
    "vcpkg-cmake-wrapper.cmake",
]


def copy_builder_files(port_dir: Path):
    """Copy builder scripts into port_dir/builder/."""
    builder_dst = port_dir / "builder"
    builder_dst.mkdir(parents=True, exist_ok=True)
    for fname in BUILDER_FILES:
        src = BUILDER_SRC / fname
        if src.is_file():
            shutil.copy2(str(src), str(builder_dst / fname))
    # Copy usage file to port root (not builder/)
    usage_src = BUILDER_SRC / "usage.in"
    if usage_src.is_file():
        shutil.copy2(str(usage_src), str(port_dir / "usage"))
