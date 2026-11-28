"""Generate version-directory FFmpeg overlays from declarative metadata.

Each version has its own directory but the vcpkg manifest always names the
package ``ffmpeg``. CI selects exactly one *port directory* per vcpkg graph;
versioned directories must never be supplied together as an overlay parent.
The compiler emits the original FFmpeg CMake builder unmodified into its Port.
No build flags, source patches or ARM/MSVC handling are reimplemented.
vcpkg still owns the dependency graph and native ABI cache.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .spec import FeatureSet, _items, read_spec, resolve_features


ROOT = Path(__file__).resolve().parents[2]

def ffmpeg_port_name(version: str) -> str:
    """Unique generated directory name, NOT a vcpkg package identity."""
    if version == "master":
        return "ffmpeg-master"
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise ValueError(f"Invalid FFmpeg version for vcpkg Port: {version!r}")
    return "ffmpeg-" + version.replace(".", "-")


def _cmake(value: object) -> str:
    # Our YAML configuration is trusted, but never allow malformed CMake output.
    text = str(value)
    if "\n" in text or "\r" in text or "]=" in text:
        raise ValueError(f"Unsafe CMake value: {text!r}")
    return '"' + text.replace("\\", "/").replace('"', '\\"').replace(";", "\\;") + '"'


def _entry_name(entry: str | dict) -> str:
    return entry if isinstance(entry, str) else entry["name"]


def manifest_for(config: dict, spec: FeatureSet, version: str,
                 package_name: str = "ffmpeg") -> dict:
    """Translate feature edges into vcpkg's native additive feature schema."""
    output: dict[str, dict] = {}
    for name, info in spec.definitions.items():
        external = list(spec.packages.get(name, ()))
        refs: dict[tuple[str, str], set[str]] = {}
        for target, platform in spec.references.get(name, ()):
            actual_platform = platform or spec.definitions[target].get("platform", "")
            refs.setdefault((package_name, actual_platform), set()).add(target)
        for (port, platform), children in sorted(refs.items()):
            item: dict = {"name": port, "features": sorted(children)}
            if platform:
                item["platform"] = platform
            external.append(item)
        node = {"description": info.get("description") or f"Enable {name}"}
        if external:
            node["dependencies"] = external
        output[name] = node
    return {
        "name": package_name, "version": version,
        "description": f"FFmpeg {version} build for MSVC",
        "homepage": "https://ffmpeg.org", "license": None,
        "dependencies": list(spec.host_packages),
        "default-features": list(spec.defaults),
        "features": output,
    }


def _policy_script(spec: FeatureSet) -> str:
    lines = ["# Generated build-policy assertions; vcpkg features remain additive.",
             'set(_FFBUILD_REQUIRED_PACKAGES "")']
    for dep in spec.host_packages:
        lines.append(f"list(APPEND _FFBUILD_REQUIRED_PACKAGES {_cmake(_entry_name(dep))})")
    for name, dependencies in spec.packages.items():
        if dependencies:
            lines.append(f"if({_cmake(name)} IN_LIST FEATURES)")
            for dep in dependencies:
                lines.append(f"  list(APPEND _FFBUILD_REQUIRED_PACKAGES {_cmake(_entry_name(dep))})")
            lines.append("endif()")
    for name, info in spec.definitions.items():
        conditions: list[tuple[str, str]] = []
        mode = info.get("license")
        if mode not in (None, "lgpl", "gpl", "nonfree"):
            raise ValueError(f"{name}: invalid license {mode!r}")
        if mode in ("gpl", "nonfree"):
            conditions.append((f"NOT {_cmake('license-' + mode)} IN_LIST FEATURES",
                               f"{name} requires explicit {mode} license mode"))
        for relation in ("requires", "conflicts"):
            for rule in _items(info.get(relation)):
                result = re.fullmatch(r"(feature|package):([A-Za-z0-9_.+-]+)", rule) if isinstance(rule, str) else None
                if not result:
                    raise ValueError(f"{name}: invalid {relation}: {rule!r}")
                kind, target = result.groups()
                if kind == "feature" and target not in spec.definitions:
                    raise ValueError(f"{name}: unknown feature {target}")
                group = "FEATURES" if kind == "feature" else "_FFBUILD_REQUIRED_PACKAGES"
                condition = f"{_cmake(target)} IN_LIST {group}"
                conditions.append((f"NOT {condition}" if relation == "requires" else condition,
                                   f"{name}: {relation} {rule}"))
        if conditions:
            lines.append(f"if({_cmake(name)} IN_LIST FEATURES)")
            for condition, reason in conditions:
                lines.extend([f"  if({condition})",
                              f"    message(FATAL_ERROR {_cmake('FFmpeg policy: ' + reason)})",
                              "  endif()"])
            lines.append("endif()")
    return "\n".join(lines) + "\n"


def generate_port(config_name: str, *, destination: Path, ref: str = "",
                  sha512: str = "", source_version: str | None = None) -> Path:
    """Compile one source configuration to a clean, standalone overlay port."""
    config, _ = read_spec(config_name)
    if config_name == "master":
        if not (source_version and re.fullmatch(r"n?\d+\.\d+[A-Za-z0-9.+-]*", source_version)):
            raise ValueError("Master requires an upstream describe version")
        version = source_version.removeprefix("n")
        if not re.fullmatch(r"[0-9a-f]{40}", ref):
            raise ValueError("Master must be pinned to a full 40-digit commit")
    else:
        version = config_name
    source = config.get("source", {})
    source_ref = ref or str(source.get("ref", f"n{version}")).replace("${VERSION}", version)
    checksum = sha512 or source.get("sha512", "")
    if not re.fullmatch(r"[0-9a-f]{128}", checksum):
        raise ValueError(f"FFmpeg {config_name} requires a SHA512 source checksum")
    features = resolve_features(config, config_name if config_name != "master" else version.split("-", 1)[0])
    port_name = ffmpeg_port_name(config_name)
    manifest = manifest_for(config, features, version, "ffmpeg")

    port = destination / port_name
    port.mkdir(parents=True, exist_ok=True)
    for old in port.iterdir():
        if old.is_dir():
            shutil.rmtree(old)
        else:
            old.unlink()
    patch_dir = port / "patches"
    patch_dir.mkdir()
    patch_refs: list[str] = []
    for index, name in enumerate(config.get("patches", [])):
        file = ROOT / "patches" / name
        if not file.is_file():
            raise FileNotFoundError(f"Missing FFmpeg patch: {file}")
        target = f"{index:03d}-{file.name}"
        shutil.copyfile(file, patch_dir / target)
        patch_refs.append(f"patches/{target}")
    (port / "vcpkg.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    policy = _policy_script(features)
    (port / "policy.cmake").write_text(policy, encoding="utf-8")
    # The original builder includes ../constraints.cmake itself. Keep the
    # version-qualified policy byte-identical and never bypass that guard.
    (port / "constraints.cmake").write_text(policy, encoding="utf-8")

    # Preserve the original build engine byte-for-byte. This also preserves
    # ARM gas-preprocessor handling, native SDK/CRT flags, host bin2c/opstool,
    # Release+Debug execution, DEF-to-LIB conversion and generated metadata.
    builder_source = ROOT / "scripts" / "cmake"
    builder_dir = port / "builder"
    builder_dir.mkdir()
    for name in ("ffmpeg-portfile.cmake", "build.sh.in", "FindFFmpeg.cmake.in",
                 "vcpkg-cmake-wrapper.cmake", "package-config.cmake"):
        source_file = builder_source / name
        if not source_file.is_file():
            raise FileNotFoundError(f"Original FFmpeg builder missing: {source_file}")
        shutil.copyfile(source_file, builder_dir / name)
    usage_file = builder_source / "usage.in"
    if not usage_file.is_file():
        raise FileNotFoundError(f"Original FFmpeg usage missing: {usage_file}")
    shutil.copyfile(usage_file, port / "usage")

    # Generate only the version's metadata and the original feature macro
    # calls. The original CMake script still owns all build-side decisions.
    feature_lines = ["# Original ffport feature macro ABI; sourced by builder/ffmpeg-portfile.cmake"]
    for feature, info in config.get("features", {}).items():
        if not isinstance(info, dict):
            continue
        flag = info.get("flag", "")
        pkgconfig = info.get("pkgconfig", "")
        if not flag and not pkgconfig:
            continue
        if pkgconfig:
            feature_lines.append(f"ffmpeg_feature_core({feature} {_cmake(flag)} {pkgconfig})")
        else:
            feature_lines.append(f"ffmpeg_feature({feature} {_cmake(flag)})")
    (port / "features.cmake").write_text("\n".join(feature_lines) + "\n", encoding="utf-8")

    build = config.get("build", {})
    options = [f"set(FFMPEG_VERSION {_cmake(version)})",
               f"set(FFMPEG_SHA512 {_cmake(checksum)})"]
    for key, value in (("FFMPEG_BASE_OPTIONS", build.get("base_options")),
                       ("FFMPEG_OPTIONS_DEBUG", build.get("debug", {}).get("options"))):
        if value:
            options.append(f"set({key} {_cmake(value)})")
    for name, value in build.get("cmake_defines", {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name):
            raise ValueError(f"Unsafe FFmpeg CMake variable: {name}")
        options.append(f"set({name} {_cmake(value)})")
    # A version-qualified Port requires concrete refs, not template variables.
    source_ref = source_ref.replace("${VERSION}", version)
    if source_ref != f"n{version}":
        options.append(f"set(FFMPEG_REF {_cmake(source_ref)})")
    options.append("set(FFMPEG_PATCHES")
    options.extend(f'    "${{CMAKE_CURRENT_LIST_DIR}}/{name}"' for name in patch_refs)
    options.extend([")", 'set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")',
                    'include("${CMAKE_CURRENT_LIST_DIR}/builder/ffmpeg-portfile.cmake")'])
    (port / "portfile.cmake").write_text("\n".join(options) + "\n", encoding="utf-8")
    # Keep the original ports/ffmpeg-tester manifest and CMake tests unchanged.
    # Its native dependency on ffmpeg resolves the selected version directory
    # through --overlay-ports=<generated-version-port>.
    return port
