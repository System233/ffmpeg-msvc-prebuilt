"""Find local dependency overlays affected by source changes."""

from __future__ import annotations

import json
from pathlib import Path

from .versions import ROOT


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
        if not port.is_dir() or name == "ffmpeg":
            continue  # generated ports are not authored overlays
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
