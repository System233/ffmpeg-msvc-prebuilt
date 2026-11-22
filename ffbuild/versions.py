"""One source of truth for FFmpeg YAML inheritance and port generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.ffport import _generate, features, merge, yaml_utils

ROOT = Path(__file__).resolve().parents[1]
TRIPLETS = ("arm-windows", "arm64-windows", "x86-windows", "x64-windows")
LICENSES = ("lgpl", "gpl")
LINKAGES = ("shared", "static")


def versions() -> list[str]:
    return sorted(
        (p.stem for p in (ROOT / "ffmpeg").glob("*.yaml") if p.stem not in {"base", "master"}),
        key=lambda s: tuple(int(x) for x in s.split(".")),
    )


def config(name: str) -> dict[str, Any]:
    chain, _ = yaml_utils.resolve_chain(name)
    resolved: dict[str, Any] = {}
    for item in chain:
        resolved = merge.deep_merge(resolved, item)
    return resolved


def spec_files(name: str) -> set[str]:
    """All YAML sources consumed by ffport when resolving this version."""
    result = {"ffmpeg/base.yaml"}
    seen: set[str] = set()

    def visit(stem: str) -> None:
        if stem in seen or stem == "base":
            return
        seen.add(stem)
        parts = stem.split(".")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            visit(".".join(parts[:2]))
            patch = ROOT / "ffmpeg" / f"{stem}.yaml"
            if patch.is_file():
                result.add(f"ffmpeg/{stem}.yaml")
            return
        doc = yaml_utils.load_yaml(stem)
        visit(doc.get("extends", "base"))
        result.add(f"ffmpeg/{stem}.yaml")

    visit(name)
    return result


def revision(name: str) -> int:
    return int(config(name).get("revision", 0))


def has_source(name: str) -> bool:
    source = config(name).get("source", {})
    return bool(source.get("ref") and source.get("sha512"))


def latest_per_family(items: list[str]) -> list[str]:
    latest: dict[str, str] = {}
    for version in items:
        if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
            continue
        family = ".".join(version.split(".")[:2])
        if family not in latest or tuple(map(int, version.split("."))) > tuple(map(int, latest[family].split("."))):
            latest[family] = version
    return [latest[key] for key in sorted(latest, key=lambda s: tuple(map(int, s.split("."))))]


def generate(name: str, *, revision_override: int | None = None,
             ref: str | None = None, sha512: str | None = None,
             output: Path | None = None) -> Path:
    """Reuse ffport's library API; no nested Python CLI is spawned."""
    dest = output or ROOT / "ports"
    _generate(name, sha512=sha512, ref=ref, output=str(dest))
    generated = dest / "ffmpeg"
    if revision_override is not None:
        import json

        path = generated / "vcpkg.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["port-version"] = revision_override
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        portfile = generated / "portfile.cmake"
        original = portfile.read_text(encoding="utf-8")
        patched, count = re.subn(
            r"(?m)^set\(FFMPEG_PORT_REVISION \d+\)$",
            f"set(FFMPEG_PORT_REVISION {revision_override})",
            original,
        )
        if count != 1:
            raise ValueError("FFmpeg generated port is missing its revision marker")
        portfile.write_text(patched, encoding="utf-8")
    return generated


def source_config(name: str, ref: str = "", sha512: str = "") -> dict[str, Any]:
    resolved = config(name)
    if ref:
        resolved.setdefault("source", {})["ref"] = ref
    if sha512:
        resolved.setdefault("source", {})["sha512"] = sha512
    return resolved


def dependency_names(name: str, license_: str) -> set[str]:
    """Resolve recursive FFmpeg feature references into vcpkg dependency names."""
    resolved = config(name)
    available = features.resolve_features(resolved, name if name != "master" else None)["features"]
    package_names: set[str] = set()
    visited: set[str] = set()
    stack = [f"all-{license_}"]
    override = resolved.get("dep_overrides", {})
    while stack:
        feature = stack.pop()
        if feature in visited or feature not in available:
            continue
        visited.add(feature)
        for dep in features._normalise_list(available[feature].get("depends", [])):
            dep_name = dep if isinstance(dep, str) else dep.get("name", "")
            if not dep_name:
                continue
            if dep_name.startswith("@"):
                stack.append(dep_name[1:])
            else:
                package_names.add(override.get(feature, dep_name))
    for entry in resolved.get("build", {}).get("host_deps", []):
        package_names.add(entry if isinstance(entry, str) else entry.get("name", ""))
    package_names.add("ffmpeg-tester")
    return package_names - {""}
