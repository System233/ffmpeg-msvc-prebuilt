"""Deterministic build-input fingerprints; no timestamps or output artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .versions import ROOT, dependency_names, source_config


def _add_file(h: Any, path: Path) -> None:
    relative = path.relative_to(ROOT).as_posix()
    h.update(len(relative.encode("utf-8")).to_bytes(4, "big"))
    h.update(relative.encode("utf-8"))
    contents = path.read_bytes()
    h.update(len(contents).to_bytes(8, "big"))
    h.update(contents)


def _overlay_closure(names: set[str]) -> set[Path]:
    """Include directly selected ports and their local transitive dependencies."""
    found: set[Path] = set()
    visited: set[str] = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        port = ROOT / "ports" / name
        if not port.is_dir() or name in {"ffmpeg", "ffmpeg-deps"}:
            continue  # generated ports are never fingerprint inputs
        for file in port.rglob("*"):
            if file.is_file() and "__pycache__" not in file.parts:
                found.add(file)
        manifest = port / "vcpkg.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            deps = list(data.get("dependencies", []))
            for feature in data.get("features", {}).values():
                deps.extend(feature.get("dependencies", []))
            for dep in deps:
                pending.append(dep if isinstance(dep, str) else dep.get("name", ""))
    return found


def overlay_port_names(names: set[str]) -> set[str]:
    """All local ports reachable from selected build dependencies."""
    return {path.relative_to(ROOT).parts[1] for path in _overlay_closure(names)}


def fingerprint(name: str, triplet: str, license_: str, linkage: str,
                *, ref: str = "", sha512: str = "") -> str:
    """Hash all inputs that can change this variant's compiled output.

    The port's release revision is deliberately excluded; revision is an output
    identifier, not a build input. Platform-conditional dependency files are
    included conservatively to prevent false cache hits.
    """
    spec = source_config(name, ref, sha512)
    spec.pop("revision", None)
    h = hashlib.sha256()
    h.update(b"ffbuild-input-v1\0")
    payload = {"config": spec, "triplet": triplet, "license": license_, "linkage": linkage}
    h.update(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    paths: set[Path] = set()
    for patch in spec.get("patches", []):
        p = ROOT / "patches" / patch
        if not p.is_file():
            raise FileNotFoundError(f"Referenced patch is missing: {patch}")
        paths.add(p)
    paths.update(_overlay_closure(dependency_names(name, license_)))
    paths.update(p for p in (ROOT / "scripts" / "cmake").rglob("*") if p.is_file())
    paths.update(p for p in (ROOT / "scripts" / "ffport").rglob("*.py") if p.is_file())
    paths.update(p for p in (ROOT / "ffbuild").rglob("*.py") if p.is_file())
    for file in ("vcpkg-configuration.json", "requirements.txt", f"triplets/{triplet}.cmake"):
        p = ROOT / file
        if not p.is_file():
            raise FileNotFoundError(f"Missing build input: {file}")
        paths.add(p)
    for p in sorted(paths):
        _add_file(h, p)
    return h.hexdigest()
