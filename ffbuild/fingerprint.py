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
    # A Windows Git checkout can contain CRLF while Linux CI uses LF.
    # Normalize text representations for one content-addressed release tag.
    if b"\0" not in contents:
        contents = contents.replace(b"\r\n", b"\n")
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


def recipe_fingerprint(name: str, *, ref: str = "", sha512: str = "") -> str:
    """Stable source+dependency recipe identity shared by all build variants.

    A release hash conservatively includes every architecture and license
    configuration to keep the release version consistent across its variants.
    It does not depend on release publication code, CI workflows or timestamps.
    """
    spec = source_config(name, ref, sha512)
    spec.pop("revision", None)
    h = hashlib.sha256()
    h.update(b"ffbuild-recipe-v3\0vcpkg-2026.06.01\0")
    h.update(json.dumps({"yaml": name, "config": spec},
                        sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False).encode("utf-8"))
    paths: set[Path] = set()
    for patch in spec.get("patches", []):
        file = ROOT / "patches" / patch
        if not file.is_file():
            raise FileNotFoundError(f"Missing FFmpeg patch: {patch}")
        paths.add(file)
    for mode in ("lgpl", "gpl", "nonfree"):
        paths.update(_overlay_closure(dependency_names(name, mode)))
    for directory in ("ports/ffmpeg-tester", "ffvcpkg"):
        paths.update(file for file in (ROOT / directory).rglob("*") if file.is_file()
                     and "__pycache__" not in file.parts)
    paths.update((ROOT / "triplets").glob("*.cmake"))
    for name_ in ("vcpkg-configuration.json", "requirements.txt",
                  "ffbuild/spec.py", "ffbuild/port.py", "ffbuild/identity.py",
                  "ffbuild/versions.py", "ffbuild/builder.py"):
        paths.add(ROOT / name_)
    for file in sorted(paths):
        _add_file(h, file)
    return h.hexdigest()


def variant_fingerprint(recipe_hash: str, triplet: str, feature_hash: str) -> str:
    """One *selected vcpkg feature closure*, not a license/linkage label."""
    if len(feature_hash) != 64 or any(c not in "0123456789abcdef" for c in feature_hash):
        raise ValueError("The canonical feature SHA256 is required")
    payload = json.dumps([recipe_hash, triplet, feature_hash], separators=(",", ":"))
    return hashlib.sha256(b"ffbuild-variant-v3\0" + payload.encode()).hexdigest()


def fingerprint(name: str, triplet: str, package: str,
                *, ref: str = "", sha512: str = "") -> str:
    """Compute the configured vcpkg package identity for a source version."""
    from .targets import Target, compile_target, parse_package
    from .versions import config

    canonical, roots = parse_package(package)
    resolved = compile_target(config(name), name if name != "master" else "9.1",
                              Target(canonical, triplet, roots))
    return variant_fingerprint(recipe_fingerprint(name, ref=ref, sha512=sha512),
                               triplet, resolved["feature_hash"])
