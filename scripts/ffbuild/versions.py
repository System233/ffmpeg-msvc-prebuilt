"""One source of truth for FFmpeg YAML inheritance and port generation."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .port import ffmpeg_port_name, generate_port
from .spec import read_spec, resolve_features

ROOT = Path(__file__).resolve().parents[2]
GENERATED_PORTS = ROOT / "_work" / "ffbuild" / "generated-ports"
from .native_platform import PE_MACHINE

# Supported binary architectures, not the configured CI selection.
TRIPLETS = tuple(sorted(PE_MACHINE))
LICENSE_PROFILES = ("lgpl", "gpl", "nonfree")


def versions() -> list[str]:
    return sorted(
        (p.stem for p in (ROOT / "ffmpeg").glob("*.yaml") if p.stem not in {"base", "master"}),
        key=lambda s: tuple(int(x) for x in s.split(".")),
    )


def config(name: str) -> dict[str, Any]:
    return read_spec(name)[0]


def spec_files(name: str) -> set[str]:
    return {path.relative_to(ROOT).as_posix() for path in read_spec(name)[1]}


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


def generate(name: str, *, ref: str | None = None, sha512: str | None = None,
             source_version: str | None = None,
             output: Path | None = None) -> Path:
    return generate_port(name, destination=output or GENERATED_PORTS,
                         source_version=source_version, ref=ref or "",
                         sha512=sha512 or "")


def generate_all(*, output: Path | None = None, master: dict[str, str] | None = None) -> list[Path]:
    """Generate every buildable release and, if pinned, the master snapshot."""
    destination = output or GENERATED_PORTS
    if destination.is_symlink():
        raise ValueError("Generated Port directory cannot be a symlink")
    destination = destination.resolve()
    if destination == ROOT or destination in ROOT.parents or (destination.exists() and not destination.is_dir()):
        raise ValueError("Invalid generated Port directory")
    if destination != GENERATED_PORTS.resolve() and destination.exists():
        # Explicit local output may not overwrite unrelated user files.
        for entry in destination.iterdir():
            if entry.is_symlink() or (entry.name != "seed-plan.json" and
                    not (entry.is_dir() and (entry / "vcpkg.json").is_file()
                         and (entry / "policy.cmake").is_file()
                         and (entry / "portfile.cmake").is_file())):
                raise ValueError(f"Output directory contains non-generated content: {entry.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".generated-ports-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        results = [generate(name, output=stage) for name in versions() if has_source(name)]
        if master is not None:
            results.append(generate("master", output=stage, source_version=master["ref"],
                                    ref=master["commit"], sha512=master["sha512"]))
        # The destination is exclusively generated output. Do not retain
        # stale recipes or the previous dependency plan.
        if destination.exists():
            shutil.rmtree(destination)
        stage.rename(destination)
    return [destination / port.name for port in results]


def feature_version(name: str, source_version: str | None = None) -> str:
    if name != "master":
        return name
    if not source_version:
        raise ValueError("Master feature resolution requires a pinned source version")
    version = source_version.removeprefix("n").split("-", 1)[0]
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise ValueError("Invalid pinned Master source version")
    return version


def dependency_names(name: str, license_: str, *, source_version: str | None = None) -> set[str]:
    compiled = resolve_features(config(name), feature_version(name, source_version))
    active = compiled.closure([f"all-{license_}"])
    all_packages = (entry for feature in active for entry in compiled.packages.get(feature, ()))
    names = {p if isinstance(p, str) else p.get("name", "") for p in all_packages}
    names.update(p if isinstance(p, str) else p.get("name", "")
                 for p in compiled.host_packages)
    return (names - {""}) | {"ffmpeg-tester"}


def validate_variant(name: str, license_: str, *, source_version: str | None = None) -> list[str]:
    try:
        compiled = resolve_features(config(name), feature_version(name, source_version))
        return compiled.policy_errors(compiled.closure([f"all-{license_}"]))
    except (ValueError, KeyError) as error:
        return [str(error)]
