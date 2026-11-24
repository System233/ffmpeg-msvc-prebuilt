"""Independent, final-stage file and FFmpeg patch-ownership checks."""
from __future__ import annotations

import re
from pathlib import Path

import yaml as pyyaml

from .models import version_name


def _patch_list(document: object) -> set[str]:
    if not isinstance(document, dict):
        raise ValueError("Invalid FFmpeg version YAML")
    patches = document.get("patches", [])
    if not isinstance(patches, list) or any(not isinstance(p, str) for p in patches):
        raise ValueError("Invalid version patch list")
    return set(patches)


def _inherits_from(root: Path, child: str, ancestor: str) -> bool:
    """Conservatively reject repairing a YAML inherited by another version."""
    seen: set[str] = set()
    current = child
    while current and current != "base":
        if current in seen:
            raise ValueError("Cyclic FFmpeg inheritance")
        seen.add(current)
        path = root / "ffmpeg" / f"{current}.yaml"
        if not path.is_file():
            raise ValueError(f"Unresolved FFmpeg inheritance: {current}")
        document = pyyaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            raise ValueError("Invalid FFmpeg inheritance document")
        parent = document.get("extends") or (
            ".".join(current.split(".")[:2]) if len(current.split(".")) == 3
            else "base")
        if parent == ancestor:
            return True
        current = parent
    return False


def validate_changes(target: str, changed: list[tuple[str, str]],
                     root: Path, before: str | None = None) -> list[str]:
    """Check (git status, path) and target-exclusive patch references.

    Only additions of new FFmpeg source patch files are accepted.  Patch names
    under an already shared family are NOT implicitly writable.
    """
    target = version_name(target)
    yaml_path = f"ffmpeg/{target}.yaml"
    if not changed:
        raise ValueError("Empty auto-heal change set")
    paths = []
    patch_paths = []
    for status, path in changed:
        if not isinstance(path, str) or not path or "\\" in path or ".." in path.split("/"):
            raise ValueError("Unsafe patch file path")
        if status not in ("A", "M"):
            raise ValueError(f"Disallowed git change kind: {status}")
        if path == yaml_path and status == "M":
            paths.append(path)
            continue
        if not re.fullmatch(r"patches/[0-9]+\.x/[A-Za-z0-9._-]+\.patch", path):
            raise ValueError(f"Out of scope: {path}")
        if status != "A":
            raise ValueError(f"Existing or shared patches cannot be modified: {path}")
        if target != "master" and path.split("/")[1] != f"{target.split('.')[0]}.x":
            raise ValueError(f"Source patch is outside the target major family: {path}")
        patch_paths.append(path)
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate paths in repair patch")
    if yaml_path not in paths:
        raise ValueError("Repair must modify its target YAML")
    for other in (root / "ffmpeg").glob("*.yaml"):
        if other.stem != target and _inherits_from(root, other.stem, target):
            raise ValueError(f"Cannot auto-repair inherited/shared YAML: {target}")
    path = root / yaml_path
    current = _patch_list(pyyaml.safe_load(path.read_text(encoding="utf-8")))
    original = _patch_list(pyyaml.safe_load(before)) if before is not None else set()
    for name in patch_paths:
        short = name.removeprefix("patches/")
        patch = root / name
        if not patch.is_file() or patch.is_symlink():
            raise ValueError(f"Missing, invalid or symlink source patch: {name}")
        if short not in current or short in original:
            raise ValueError(f"Added patch must be exclusively newly referenced: {name}")
        for other in (root / "ffmpeg").glob("*.yaml"):
            if other.stem == target:
                continue
            others = _patch_list(pyyaml.safe_load(other.read_text(encoding="utf-8")))
            if short in others:
                raise ValueError(f"New patch is referenced by another version: {name}")
    for name in current:
        if name.startswith("/") or ".." in name.split("/") or "\\" in name:
            raise ValueError("Unsafe FFmpeg patch reference")
    return paths


def check_pr(target: str, base: str, head: str, root: Path) -> list[str]:
    """Validate the entire candidate PR diff, not just the latest bot commit."""
    import subprocess
    from .models import commit_sha

    commit_sha(base)
    commit_sha(head)
    merge_base = subprocess.run(["git", "merge-base", base, head], cwd=root,
                                capture_output=True, text=True, check=True).stdout.strip()
    result = subprocess.run(["git", "diff", "--name-status", "--no-renames",
                             merge_base, head], cwd=root, capture_output=True,
                            text=True, check=True)
    delta = []
    for line in result.stdout.splitlines():
        columns = line.split("\t")
        if len(columns) != 2:
            raise ValueError("Unexpected PR change kind")
        delta.append((columns[0], columns[1]))
    before = subprocess.run(["git", "show", f"{merge_base}:ffmpeg/{version_name(target)}.yaml"],
                            cwd=root, capture_output=True, text=True, check=True).stdout
    return validate_changes(target, delta, root, before=before)
