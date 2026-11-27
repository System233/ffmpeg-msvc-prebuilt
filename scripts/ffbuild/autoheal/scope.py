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


def _git(root: Path, *args: str) -> bytes:
    import subprocess
    return subprocess.check_output(["git", *args], cwd=root)


def _delta(root: Path, *args: str) -> list[tuple[str, str]]:
    fields = _git(root, "diff", "--name-status", "-z", "--no-renames", *args).decode("utf-8").split("\0")
    if fields[-1] != "" or len(fields[:-1]) % 2:
        raise ValueError("Unexpected Git delta")
    return list(zip(fields[0:-1:2], fields[1:-1:2]))


def _tree(root: Path, revision: str, dest: Path) -> None:
    """Read Git blobs without executing anything in the candidate revision."""
    import io
    import zipfile
    dest.mkdir()
    archive = _git(root, "archive", "--format=zip", revision, "ffmpeg", "patches")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        for info in z.infolist():
            name = info.filename
            if "\\" in name or ":" in name or name.startswith("/") or ".." in name.split("/"):
                raise ValueError("Unsafe candidate archive path")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlink in version configuration tree")
        z.extractall(dest)


def _rules(target: str, changed: list[tuple[str, str]], before: Path, after: Path,
           *, allow_new: bool = False) -> list[str]:
    from ..spec import read_spec
    target = version_name(target)
    target_path = f"ffmpeg/{target}.yaml"
    new = not (before / target_path).is_file()
    if new and not allow_new:
        raise ValueError("Repair cannot create a different version")
    if not changed:
        raise ValueError("Empty automatic version change set")
    paths = []
    new_patches = []
    family = ".".join(target.split(".")[:2]) if target != "master" else ""
    family_path = f"ffmpeg/{family}.yaml"
    for status, path in changed:
        if path in paths or "\\" in path or ".." in path.split("/"):
            raise ValueError(f"Unsafe or duplicate change: {path}")
        paths.append(path)
        if status not in ("A", "M"):
            raise ValueError(f"Disallowed change kind {status}: {path}")
        if path == target_path and status == ("A" if new else "M"):
            pass
        elif new and len(target.split(".")) == 3 and path == family_path and status == "A":
            if (before / path).exists() or pyyaml.safe_load((after / path).read_text(encoding="utf-8")) != {"extends": "base", "patches": []}:
                raise ValueError("New family must be an empty, previously nonexistent template")
        elif re.fullmatch(r"patches/[0-9]+\.x/[A-Za-z0-9._-]+\.patch", path) and status == "A":
            if (before / path).exists():
                raise ValueError(f"Existing patch cannot be changed: {path}")
            if target != "master" and path.split("/")[1] != target.split(".")[0] + ".x":
                raise ValueError(f"Patch outside target major family: {path}")
            new_patches.append(path.removeprefix("patches/"))
        else:
            raise ValueError(f"Out of scope: {path}")
        file = after / path
        if not file.is_file() or file.is_symlink() or any(p.is_symlink() for p in file.parents if p != after and after in p.parents):
            raise ValueError(f"Expected regular file: {path}")
    if target_path not in paths:
        raise ValueError("Automatic change must include target YAML")
    target_doc = pyyaml.safe_load((after / target_path).read_text(encoding="utf-8"))
    direct = _patch_list(target_doc)
    if not new:
        old_doc = pyyaml.safe_load((before / target_path).read_text(encoding="utf-8"))
        old_direct = _patch_list(old_doc)
        if new_patches and any(p in old_direct for p in new_patches):
            raise ValueError("New patch must be newly referenced")
        # The upstream stable source is immutable. Changing source is not a repair.
        old_source = read_spec(target, directory=before / "ffmpeg")[0].get("source") or {}
        new_source = read_spec(target, directory=after / "ffmpeg")[0].get("source") or {}
        # A source-less family template may acquire a pinned source only in a
        # new-version proposal. The semantic comparison below still protects all children.
        if old_source != new_source and not (allow_new and target != "master" and
                not (old_source.get("ref") and old_source.get("sha512"))):
            raise ValueError("Existing source identity must not change")
    for name in new_patches:
        if name not in direct:
            raise ValueError(f"New patch is not directly referenced by target: {name}")
    target_config, _ = read_spec(target, directory=after / "ffmpeg")
    if target != "master":
        source = target_config.get("source", {})
        if (source.get("method") != "git" or source.get("repo") != "ffmpeg/ffmpeg" or source.get("ref") not in ("n${VERSION}", "n"+target)
                or not re.fullmatch("[0-9a-f]{128}", str(source.get("sha512", "")))):
            raise ValueError("Target must retain a pinned upstream FFmpeg stable source")
    for name in target_config.get("patches", []):
        if not isinstance(name, str) or not re.fullmatch(r"[0-9]+\.x/[A-Za-z0-9._-]+\.patch", name):
            raise ValueError(f"Unsafe target patch reference: {name}")
        file = after / "patches" / name
        if not file.is_file() or file.is_symlink():
            raise ValueError(f"Missing target patch: {name}")
    # Exact semantic comparison using the same resolver as Port generation.
    # Unchanged generator/triplet/port code and patch bytes then imply unchanged
    # generated Port for every old version, without executing candidate code.
    for file in sorted((before / "ffmpeg").glob("*.yaml")):
        other = file.stem
        if other in (target, "base"):
            continue
        old, old_files = read_spec(other, directory=before / "ffmpeg")
        new_config, new_files = read_spec(other, directory=after / "ffmpeg")
        if old != new_config or [p.name for p in old_files] != [p.name for p in new_files]:
            raise ValueError(f"Target change affects existing version: {other}")
        if set(new_patches).intersection(new_config.get("patches", [])):
            raise ValueError(f"New patch is referenced by another version: {other}")
    return paths


def _regular_git_modes(root: Path, *args: str) -> None:
    # Reject type and executable-bit changes even if the file name is allowed.
    fields = _git(root, "diff", "--raw", "-z", "--no-renames", *args).decode("utf-8").split("\0")
    for header in fields[:-1:2]:
        columns = header.split()
        if len(columns) != 5 or columns[1] != "100644":
            raise ValueError("Only non-executable regular files may be changed")


def check_pr(target: str, base: str, head: str, root: Path, *, allow_new: bool = False) -> list[str]:
    import tempfile
    from .models import commit_sha
    base, head = commit_sha(base), commit_sha(head)
    merge_base = _git(root, "merge-base", base, head).decode().strip()
    delta = _delta(root, merge_base, head)
    _regular_git_modes(root, merge_base, head)
    with tempfile.TemporaryDirectory(prefix="ffbuild-scope-") as temp:
        before, after = Path(temp) / "before", Path(temp) / "after"
        _tree(root, merge_base, before)
        _tree(root, head, after)
        return _rules(target, delta, before, after, allow_new=allow_new)


def check_worktree(target: str, base: str, root: Path, *, allow_new: bool = False,
                   allow_empty: bool = False) -> list[str]:
    """Check current candidate, including uncommitted and newly created files."""
    import tempfile
    from .models import commit_sha
    base = commit_sha(base)
    delta = dict((path, status) for status, path in _delta(root, base))
    staged = _delta(root, "--cached", base)
    _regular_git_modes(root, "--cached", base)
    _regular_git_modes(root, base)
    # A staged change must not hide behind a worktree reversal.
    for status, path in staged:
        if path not in delta:
            raise ValueError(f"Staged change hidden by worktree: {path}")
    runtime_files = {"agent_context.json", "failed_steps_hint.txt", "fix_report.md", "autoheal-triage.json", "validation-plan.json"}
    runtime_dirs = {"error_logs"}
    for path in _git(root, "ls-files", "--others", "--exclude-standard", "-z").decode("utf-8").split("\0"):
        if not path or path in runtime_files or path.split("/")[0] in runtime_dirs:
            continue
        delta[path] = "A"
    if allow_empty and not delta and not staged:
        return []
    with tempfile.TemporaryDirectory(prefix="ffbuild-scope-") as temp:
        before = Path(temp) / "before"
        _tree(root, base, before)
        if staged:
            staged_tree = _git(root, "write-tree").decode().strip()
            staged_snapshot = Path(temp) / "staged"
            _tree(root, staged_tree, staged_snapshot)
            _rules(target, staged, before, staged_snapshot, allow_new=allow_new)
        return _rules(target, [(status, path) for path, status in sorted(delta.items())],
                      before, root, allow_new=allow_new)
