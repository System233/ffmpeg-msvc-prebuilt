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
import shlex
import shutil
from pathlib import Path

from .spec import FeatureSet, _items, read_spec, resolve_features


ROOT = Path(__file__).resolve().parents[1]

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
                 revision: int, package_name: str = "ffmpeg") -> dict:
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
        "name": package_name, "version": version, "port-version": revision,
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


# Retained experimental native CMake recipe for migration comparison only.
# Never emitted or executed: the generated Port must run the original builder
# from scripts/cmake. Do not switch back without proving full parity first.
_CMAKE_BUILD = r'''
include("${CMAKE_CURRENT_LIST_DIR}/policy.cmake")
if("static" IN_LIST FEATURES)
    set(VCPKG_LIBRARY_LINKAGE static)
else()
    set(VCPKG_LIBRARY_LINKAGE dynamic)
endif()

vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO FFmpeg/FFmpeg
    REF "${FFBUILD_SOURCE_REF}"
    SHA512 "${FFBUILD_SOURCE_SHA512}"
    PATCHES ${FFBUILD_PATCHES}
)

if(NOT VCPKG_TARGET_IS_WINDOWS OR VCPKG_TARGET_IS_MINGW)
    message(FATAL_ERROR "This overlay port targets native Windows/MSVC")
endif()

vcpkg_acquire_msys(MSYS_ROOT PACKAGES automake)
set(_bash "${MSYS_ROOT}/usr/bin/bash.exe")
set(_make "${MSYS_ROOT}/usr/bin/make.exe")
vcpkg_cmake_get_vars(_vars)
include("${_vars}")
# FFmpeg 8.1+ embeds frontend assets by invoking the host bin2c binary.
# The helper Port installs it under manual-tools, not the normal tools PATH.
vcpkg_add_to_path(PREPEND "${CURRENT_HOST_INSTALLED_DIR}/manual-tools/ffmpeg-bin2c")
# Directly invoking MSYS Bash does not automatically put the MSYS coreutils
# in PATH. FFmpeg's configure needs uname, sed, tr, mkdir, dirname and more.
vcpkg_add_to_path(PREPEND "${MSYS_ROOT}/usr/bin")
# On Windows FFmpeg's x86 assembler is a separate host-side executable.
# Acquire it using vcpkg's native verified tool helper, rather than silently
# falling back to --disable-x86asm for a reduced-performance build.
if(VCPKG_TARGET_ARCHITECTURE MATCHES "^(x64|x86)$")
    vcpkg_find_acquire_program(NASM)
    get_filename_component(_nasm_dir "${NASM}" DIRECTORY)
    vcpkg_add_to_path("${_nasm_dir}")
endif()
# Use the same pkg-config tool and Release/Debug module paths as the vcpkg
# FFmpeg Port; optional libraries such as SDL2 are not discoverable merely
# because vcpkg installed their .pc files.
vcpkg_find_acquire_program(PKGCONFIG)

set(_options ${FFBUILD_BASE_OPTIONS})
foreach(_item IN LISTS FFBUILD_ACTIVE_FLAGS)
    list(APPEND _options "${_item}")
endforeach()
list(APPEND _options --toolchain=msvc --target-os=win32 "--pkg-config=${PKGCONFIG}")
if(VCPKG_TARGET_ARCHITECTURE STREQUAL "x64")
    list(APPEND _options --arch=x86_64)
elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "x86")
    list(APPEND _options --arch=x86)
elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm64")
    list(APPEND _options --arch=aarch64 --disable-x86asm)
elseif(VCPKG_TARGET_ARCHITECTURE STREQUAL "arm")
    list(APPEND _options --arch=arm --disable-x86asm)
else()
    message(FATAL_ERROR "Unsupported FFmpeg architecture: ${VCPKG_TARGET_ARCHITECTURE}")
endif()

if(VCPKG_LIBRARY_LINKAGE STREQUAL "static")
    list(APPEND _options --enable-static --disable-shared)
else()
    list(APPEND _options --enable-shared --disable-static)
endif()

foreach(_mode IN ITEMS release debug)
    if(_mode STREQUAL "debug")
        set(_prefix "${CURRENT_PACKAGES_DIR}/debug")
        set(_mode_options ${FFBUILD_DEBUG_OPTIONS})
    else()
        set(_prefix "${CURRENT_PACKAGES_DIR}")
        set(_mode_options ${FFBUILD_RELEASE_OPTIONS})
    endif()
    set(_work "${CURRENT_BUILDTREES_DIR}/${TARGET_TRIPLET}-${_mode}")
    file(MAKE_DIRECTORY "${_work}")
    string(TOUPPER "${_mode}" _pkgconfig_mode)
    z_vcpkg_setup_pkgconfig_path(CONFIG ${_pkgconfig_mode})
    vcpkg_execute_required_process(
        COMMAND "${_bash}" "${SOURCE_PATH}/configure"
            "--prefix=${_prefix}" ${_options} ${_mode_options}
        WORKING_DIRECTORY "${_work}"
        LOGNAME "configure-${_mode}"
    )
    vcpkg_execute_required_process(
        COMMAND "${_make}" "-j${VCPKG_CONCURRENCY}"
        WORKING_DIRECTORY "${_work}"
        LOGNAME "compile-${_mode}"
    )
    vcpkg_execute_required_process(
        COMMAND "${_make}" install
        WORKING_DIRECTORY "${_work}"
        LOGNAME "install-${_mode}"
    )
    z_vcpkg_restore_pkgconfig_path()
endforeach()

# Normalize the files produced by FFmpeg's make install to the vcpkg binary
# package layout. A DLL's MSVC import .lib belongs in lib/, not alongside the
# runtime DLL in bin/. The non-library applications belong in tools/${PORT}.
if(VCPKG_LIBRARY_LINKAGE STREQUAL "dynamic")
    foreach(_subdir IN ITEMS "" "/debug")
        file(GLOB _import_libs "${CURRENT_PACKAGES_DIR}${_subdir}/bin/*.lib")
        foreach(_import IN LISTS _import_libs)
            get_filename_component(_libname "${_import}" NAME)
            file(RENAME "${_import}" "${CURRENT_PACKAGES_DIR}${_subdir}/lib/${_libname}")
        endforeach()
    endforeach()
endif()

foreach(_app IN ITEMS ffmpeg ffprobe ffplay)
    if("${_app}" IN_LIST FEATURES)
        vcpkg_copy_tools(TOOL_NAMES "${_app}" AUTO_CLEAN)
    endif()
endforeach()

file(REMOVE_RECURSE "${CURRENT_PACKAGES_DIR}/debug/include"
                    "${CURRENT_PACKAGES_DIR}/debug/share")
vcpkg_fixup_pkgconfig()

if(EXISTS "${SOURCE_PATH}/COPYING.LGPLv2.1")
    file(INSTALL "${SOURCE_PATH}/COPYING.LGPLv2.1"
         DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}" RENAME copyright)
elseif(EXISTS "${SOURCE_PATH}/COPYING.LGPLv3")
    file(INSTALL "${SOURCE_PATH}/COPYING.LGPLv3"
         DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}" RENAME copyright)
endif()
vcpkg_copy_pdbs()
'''


def _flag_options(text: str) -> list[str]:
    return shlex.split(text) if text else []


def generate_port(config_name: str, *, destination: Path, ref: str = "",
                  sha512: str = "", source_version: str | None = None,
                  revision: int | None = None) -> Path:
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
    effective_revision = int(config.get("revision", 0) if revision is None else revision)
    features = resolve_features(config, config_name if config_name != "master" else version.split("-", 1)[0])
    port_name = ffmpeg_port_name(config_name)
    manifest = manifest_for(config, features, version, effective_revision, "ffmpeg")

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
                 "vcpkg-cmake-wrapper.cmake"):
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
               f"set(FFMPEG_SHA512 {_cmake(checksum)})",
               f"set(FFMPEG_PORT_REVISION {effective_revision})"]
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


def generate_seed_port(directory: Path | None = None) -> Path:
    """Generate the shared dependency Seed while preserving platform constraints.

    A single ``all`` feature covers compatible dependencies. Alternate ports
    selected by different FFmpeg versions are built as separate features,
    using isolated vcpkg install roots, as in the original CI Seed workflow.
    The inputs are the *actual* compiled version manifests, not a guessed list
    of dependency names; host tools and per-version overrides are retained.
    """
    from .versions import GENERATED_PORTS, config, has_source, revision, versions

    destination = directory if directory is not None else GENERATED_PORTS
    target = destination / "ffmpeg-deps"
    target.mkdir(parents=True, exist_ok=True)
    baseline, _ = read_spec("base")
    conflicts: set[str] = set()
    names = [name for name in versions() if has_source(name)] + ["master"]
    # A version override can replace a different external dependency. Both
    # sides must not be requested together by the virtual Seed's all feature.
    for name in names:
        source, _ = read_spec(name)
        for feature, override in source.get("dep_overrides", {}).items():
            conflicts.add(str(override))
            for entry in _items(baseline.get("features", {}).get(feature, {}).get("depends")):
                package = _entry_name(entry)
                if not package.startswith("@"):
                    conflicts.add(package)

    # An entry's absent platform means unconditional. Otherwise combine the
    # conditions from all versions by OR, preserving restrictions such as !arm.
    grouped: dict[tuple[str, bool, tuple[str, ...], bool], set[str | None]] = {}
    for name in names:
        source, _ = read_spec(name)
        resolved = resolve_features(source, name)
        dependencies = [(entry, None) for entry in resolved.host_packages]
        for feature, packages in resolved.packages.items():
            condition = resolved.definitions[feature].get("platform")
            dependencies.extend((entry, condition) for entry in packages)
        for raw, fallback_platform in dependencies:
            entry = {"name": raw} if isinstance(raw, str) else dict(raw)
            dep_name = entry["name"]
            if dep_name in {"ffmpeg", "ffmpeg-deps"} or dep_name.startswith("ffmpeg-tester-"):
                continue
            if dep_name == ffmpeg_port_name(name):
                continue  # Recursive FFmpeg Feature, not a third-party dep.
            key = (dep_name, bool(entry.get("host", False)),
                   tuple(sorted(entry.get("features", ()))),
                   entry.get("default-features", True) is not False)
            grouped.setdefault(key, set()).add(entry.get("platform") or fallback_platform or None)

    candidates: dict[str, list[tuple[tuple, dict]]] = {}
    for key, platforms in sorted(grouped.items()):
        dep_name, host, features, default_features = key
        entry: dict = {"name": dep_name}
        if host:
            entry["host"] = True
        if features:
            entry["features"] = list(features)
        if not default_features:
            entry["default-features"] = False
        if None not in platforms:
            conditions = sorted(platforms)
            entry["platform"] = (conditions[0] if len(conditions) == 1 else
                                 " | ".join(f"({condition})" for condition in conditions))
        candidates.setdefault(dep_name, []).append((key, entry))

    compatible: list[dict] = []
    alternatives: dict[str, list[dict]] = {}
    for dep_name, choices in sorted(candidates.items()):
        # Different requested vcpkg dependency features must also be isolated
        # instead of accidentally being merged by one all-feature install.
        if dep_name in conflicts or len(choices) > 1:
            for index, (_, entry) in enumerate(choices):
                label = dep_name if len(choices) == 1 else f"{dep_name}-variant-{index + 1}"
                alternatives[label] = [entry]
        else:
            compatible.append(choices[0][1])

    seed_features = {"all": {"description": "Compatible dependencies for all FFmpeg versions",
                              "dependencies": compatible}}
    seed_features.update({name: {"description": f"Alternative dependency {name}",
                                 "dependencies": entries}
                          for name, entries in sorted(alternatives.items())})
    manifest = {"name": "ffmpeg-deps", "version": "1.0.0",
                "description": "Shared FFmpeg dependency binary-cache Seed",
                "default-features": [], "features": seed_features}
    (target / "vcpkg.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (target / "portfile.cmake").write_text(
        'set(VCPKG_POLICY_EMPTY_PACKAGE enabled)\n', encoding="utf-8")
    return target
