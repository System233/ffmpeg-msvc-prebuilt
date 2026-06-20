"""Patch copying — flatten version-prefixed paths into a flat directory."""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PATCHES_SRC = REPO_ROOT / "patches"


def copy_patches(patches_list: list[str], port_dir: Path) -> list[str]:
    """Copy patches flat into port_dir/patches/, handling name conflicts.

    Input patches_list entries:  "8.x/0002-fix-msvc-link-8.1.patch"
    Output: list of destination filenames, e.g. ["0002-fix-msvc-link-8.1.patch"]

    On conflict, the first keeps its name, subsequent entries get a
    ``_{parent_dir}`` suffix (e.g. ``fix-nasm_8.x.patch``).
    """
    patches_dst = port_dir / "patches"
    patches_dst.mkdir(parents=True, exist_ok=True)

    seen = {}
    result = []

    for patch_path in patches_list:
        src = PATCHES_SRC / patch_path
        fname = Path(patch_path).name

        if fname in seen:
            stem = Path(fname).stem
            ext = Path(fname).suffix
            parent_dir = Path(patch_path).parent.name
            fname = f"{stem}_{parent_dir}{ext}"

        seen[fname] = True
        dst = patches_dst / fname
        shutil.copy2(str(src), str(dst))
        result.append(fname)

    return result
