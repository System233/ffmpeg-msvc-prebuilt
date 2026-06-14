#!/usr/bin/env python3
"""
generate.py — Generate vcpkg port directories from YAML specification.

Usage:
  python scripts/generate.py --version 8.1.1
  python scripts/generate.py --version 8.1.1 --force
  python scripts/generate.py --list-families
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("ERROR: pip install pyyaml required")

REPO_ROOT = Path(__file__).resolve().parents[1]
YAML_DIR = REPO_ROOT / "ffmpeg"
PORTS_DIR = REPO_ROOT / "ports"
FFMPEG_SHARED = REPO_ROOT / "scripts" / "ffmpeg"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def load_yaml(name: str) -> dict:
    """Load a YAML file from the ffmpeg directory by name (without .yaml)."""
    path = YAML_DIR / f"{name}.yaml"
    if not path.is_file():
        print(f"ERROR: YAML file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_chain(version: str) -> tuple[list[dict], str]:
    """
    Resolve extends chain from base up to version-specific YAML.

    Returns (docs, family) where docs = [base, ..., <version>].
    """
    parts = version.split(".")
    if len(parts) not in (2, 3):
        print(f"ERROR: version must be X.Y or X.Y.Z, got '{version}'", file=sys.stderr)
        sys.exit(1)
    major, minor = parts[0], parts[1]
    family = f"{major}.{minor}"

    # Start with base
    docs = [load_yaml("base")]

    # Try family YAML
    family_doc = load_yaml(family)
    parent = family_doc.get("extends", "base")

    # Insert parent chain if not base
    if parent != "base":
        parent_docs, _ = resolve_chain(parent + ".0")
        # parent_docs already includes base; skip base since we already have it
        docs = [docs[0]] + parent_docs[1:]  # base + parent chain
    else:
        docs = [docs[0]]

    docs.append(family_doc)

    # Try patch version YAML (if version has 3 parts)
    if len(parts) == 3:
        patch_path = YAML_DIR / f"{version}.yaml"
        if patch_path.is_file():
            patch_doc = load_yaml(version)
            docs.append(patch_doc)

    return docs, family


# ---------------------------------------------------------------------------
# Feature resolution
# ---------------------------------------------------------------------------

def expand_items(items: list, defines: dict) -> set:
    """Expand @aliases into a flat set of feature names."""
    result = set()
    for item in items:
        if isinstance(item, str):
            item = item.strip()
            if item.startswith("@"):
                alias = item[1:]
                if alias not in defines:
                    print(f"WARNING: undefined alias '@{alias}' — skipping",
                          file=sys.stderr)
                    continue
                result.update(expand_items(defines[alias], defines))
            elif "," in item:
                for x in item.replace(" ", "").split(","):
                    if x:
                        result.add(x)
            elif item:
                result.add(item)
        elif isinstance(item, (list, tuple)):
            result.update(expand_items(item, defines))
    return result


def apply_exclusions(items: set, exclusions: set) -> set:
    """Apply fnmatch patterns to a set of feature names."""
    result = set(items)
    for pattern in exclusions:
        result = {f for f in result if not fnmatch.fnmatch(f, pattern)}
    return result


def version_gate_match(gate: str, target_version: str) -> bool:
    """Check if a target version satisfies a version-gate expression.
    
    Syntax: comma-separated OR groups, each group has space-separated AND conditions.
    Operators: >= > <= <
    Examples:
      ">=4.0"               — target >= 4.0
      "<5.0"                 — target < 5.0
      ">=4.3 <5.0,>=7.0"    — (4.3 <= target < 5.0) OR (target >= 7.0)
    """
    if not gate:
        return True  # no gate = all versions
    target = tuple(int(x) for x in target_version.split('.'))
    groups = [g.strip() for g in gate.split(',')]
    for group in groups:
        conditions = group.split()
        ok = True
        for cond in conditions:
            # cond is like ">=4.0" or "<5.0"
            for op in ('>=', '<=', '>', '<'):
                if cond.startswith(op):
                    ver_str = cond[len(op):]
                    ver = tuple(int(x) for x in ver_str.split('.'))
                    if op == '>=' and not target >= ver:
                        ok = False
                    elif op == '<=' and not target <= ver:
                        ok = False
                    elif op == '>' and not target > ver:
                        ok = False
                    elif op == '<' and not target < ver:
                        ok = False
                    break
            if not ok:
                break
        if ok:
            return True
    return False


def merge_features(docs: list[dict], version_str: str = None) -> dict:
    """Merge feature include/exclude/defaults along the chain."""
    registry = docs[0]["features"]
    defines = docs[0].get("define", {})

    # Seed: include ALL registry features, then filter by version-gate
    included = set(registry.keys())
    if version_str:
        for name in list(included):
            gate = registry.get(name, {}).get("version")
            if gate and not version_gate_match(gate, version_str):
                included.discard(name)
    defaults = set()
    default_aliases = []

    for doc in docs[1:]:
        feats = doc.get("features", {})
        if not feats:
            continue

        # Apply feature property overrides (e.g. nvcodec: { flag: ... })
        for name, override in feats.items():
            if name in ("include", "exclude", "defaults"):
                continue
            if isinstance(override, dict) and name in registry:
                for k, v in override.items():
                    if v is not None:
                        registry[name][k] = v

        # Record default aliases from the last doc that defines them
        raw_defaults = feats.get("defaults", [])
        if raw_defaults:
            default_aliases = []
            for item in raw_defaults:
                if isinstance(item, str) and item.startswith("@"):
                    default_aliases.append(item[1:])
                else:
                    default_aliases.append(item)

        include = expand_items(feats.get("include", []), defines)
        exclude = expand_items(feats.get("exclude", []), defines)
        dflt = expand_items(feats.get("defaults", []), defines)

        # Add new includes
        included.update(include)
        # Apply exclusions to cumulative set
        included = apply_exclusions(included, exclude)
        # Update defaults
        defaults.update(dflt)
        defaults = apply_exclusions(defaults, exclude)

    # Auto-include @ref targets from depends arrays so they exist in the
    # features block when referenced by other features (@gpl, @nonfree, etc.).
    for name, info in registry.items():
        raw = info.get("depends", [])
        if isinstance(raw, str):
            raw = [raw]
        elif isinstance(raw, dict):
            raw = [raw]
        for item in raw:
            ref = None
            if isinstance(item, str) and item.startswith("@"):
                ref = item[1:]
            elif isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].startswith("@"):
                ref = item["name"][1:]
            if ref and ref in registry:
                included.add(ref)

    # Auto-include features referenced by alias definitions so meta-features
    # built from defines have valid feature targets in the output.
    for alias_name, alias_items in defines.items():
        if alias_name == "defaults":
            continue
        for item in alias_items:
            if isinstance(item, str) and not item.startswith("@") and item in registry:
                included.add(item)

    # Re-apply all version YAML exclusions so they take effect after the
    # auto-include above (e.g. dvdnav excluded by 5.1.yaml).
    for doc in docs[1:]:
        feats = doc.get("features", {})
        if feats:
            exclude = expand_items(feats.get("exclude", []), defines)
            included = apply_exclusions(included, exclude)
            defaults = apply_exclusions(defaults, exclude)

    # Features listed in defines.defaults are passed to default-features,
    # so they must exist in the features block.
    for name in defines.get("defaults", []):
        if isinstance(name, str) and not name.startswith("@") and name in registry:
            included.add(name)

    # Re-apply version-gate filtering (auto-include and @ref resolution above
    # may have re-added features that were previously filtered out).
    if version_str:
        for name in list(included):
            gate = registry.get(name, {}).get("version")
            if gate and not version_gate_match(gate, version_str):
                included.discard(name)

    # Intersect with registry to remove unknown features
    included = {f for f in included if f in registry}
    defaults = {f for f in defaults if f in registry}

    return {
        "features": {k: registry[k] for k in sorted(included)},
        "defaults": sorted(defaults),
        "default_aliases": default_aliases,
    }


# ---------------------------------------------------------------------------
# Build / source / patches resolution
# ---------------------------------------------------------------------------

def merge_dict_chain(docs: list[dict], key: str) -> dict:
    """Deep-merge a key along the chain (child overrides parent)."""
    result = {}
    for doc in docs[1:]:
        val = doc.get(key, {})
        if isinstance(val, dict):
            # Shallow merge: child keys override parent keys
            for k, v in val.items():
                result[k] = v
        elif val is not None:
            result = val
    return result


def get_source(docs: list[dict]) -> dict:
    """Merge source blocks along the chain (child overrides parent)."""
    result = {}
    for doc in docs[1:]:
        if "source" in doc:
            src = doc["source"]
            if isinstance(src, dict):
                for k, v in src.items():
                    result[k] = v
    return result


def get_patches(docs: list[dict]) -> list[str]:
    """Return patches from the last doc that defines them (closest to leaf)."""
    for doc in reversed(docs[1:]):
        if "patches" in doc:
            return doc["patches"]
    return []


def collect_deps(features: dict, dep_overrides: dict, host_deps: list):
    """Build per-feature dependency and feature-reference maps.

    ``depends`` is a YAML array.  Each element is either:
    - a plain string: vcpkg package name
    - ``@name``: feature reference (transitive feature activation)
    - a dict ``{name, platform?}``: vcpkg dependency with optional platform

    Returns ``(feature_deps, feature_refs, host_deps)``.
    """
    feature_deps = {}
    feature_refs = {}

    for name, info in features.items():
        raw = info.get("depends", [])
        if isinstance(raw, str):
            raw = [raw]
        elif isinstance(raw, dict):
            raw = [raw]
        if not raw:
            continue

        override = dep_overrides.get(name)
        pkg_deps = []
        refs = []

        for item in raw:
            if isinstance(item, str):
                if item.startswith("@"):
                    ref_name = item[1:]
                    if ref_name not in features:
                        print(f"WARNING: depends @{ref_name} in feature '{name}' — not found",
                              file=sys.stderr)
                        continue
                    refs.append({"name": ref_name})
                else:
                    val = override if override else item
                    pkg_deps.append(val)
            elif isinstance(item, dict):
                n = item.get("name", "")
                if n.startswith("@"):
                    ref_name = n[1:]
                    if ref_name not in features:
                        print(f"WARNING: depends @{ref_name} in feature '{name}' — not found",
                              file=sys.stderr)
                        continue
                    refs.append({"name": ref_name, "platform": item.get("platform")})
                else:
                    if override and isinstance(item.get("name"), str):
                        item = dict(item)
                        item["name"] = override
                    pkg_deps.append(item)
            else:
                continue

        # Simplify pkg_deps: bare string if only name, else dict
        simplified = [
            d if isinstance(d, str) else
            (d["name"] if set(d.keys()) == {"name"} else d)
            for d in pkg_deps
        ]
        if simplified:
            feature_deps[name] = simplified
        if refs:
            feature_refs[name] = refs

    return feature_deps, feature_refs, host_deps


def generate_deps_port():
    """Generate the ffmpeg-deps virtual port from base.yaml.

    Scans ALL features in base.yaml, collects every ``depends`` value,
    deduplicates, and writes ``ports/ffmpeg-deps/vcpkg.json`` and
    ``ports/ffmpeg-deps/portfile.cmake``.
    """
    base = load_yaml("base")
    features = base.get("features", {})

    deps = []
    seen = set()
    for name, info in features.items():
        raw_deps = info.get("depends", [])
        if isinstance(raw_deps, str):
            raw_deps = [raw_deps]
        elif isinstance(raw_deps, dict):
            raw_deps = [raw_deps]
        if not raw_deps:
            continue
        for item in raw_deps:
            if isinstance(item, str):
                if item.startswith("@"):
                    continue  # skip feature references
                entry = {"name": item}
            elif isinstance(item, dict):
                if item.get("name", "").startswith("@"):
                    continue
                entry = {"name": item["name"]}
                if "platform" in item:
                    entry["platform"] = item["platform"]
            else:
                continue
            key = entry["name"]
            if key not in seen:
                seen.add(key)
                deps.append(key if len(entry) == 1 else entry)

    deps.sort(key=lambda d: d if isinstance(d,str) else d["name"])

    port_dir = PORTS_DIR / "ffmpeg-deps"
    port_dir.mkdir(parents=True, exist_ok=True)

    # vcpkg.json
    json_data = {
        "name": "ffmpeg-deps",
        "version": "1.0.0",
        "port-version": 0,
        "description": [
            "Auto-generated virtual port — union of all FFmpeg feature dependencies.",
            "Generated by scripts/generate.py --generate-deps",
        ],
        "dependencies": deps,
    }
    (port_dir / "vcpkg.json").write_text(
        json.dumps(json_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # portfile.cmake
    (port_dir / "portfile.cmake").write_text(
        'message(STATUS "[ffmpeg-deps] All dependencies resolved by vcpkg dependency graph")\n'
        '\n'
        'file(COPY "${CMAKE_CURRENT_LIST_DIR}/copyright"\n'
        '     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")\n'
        '\n'
        'file(INSTALL "${CMAKE_CURRENT_LIST_DIR}/copyright"\n'
        '     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"\n'
        '     RENAME copyright)\n',
        encoding="utf-8",
    )

    # copyright
    (port_dir / "copyright").write_text(
        "FFmpeg dependency packages — see individual package copyrights.\n",
        encoding="utf-8",
    )

    print(f"Generated ffmpeg-deps/ with {len(deps)} dependencies")


# ---------------------------------------------------------------------------
# Port file generation
# ---------------------------------------------------------------------------

def generate_features_cmake(feat_registry: dict | None = None) -> str:
    """Generate CMake feature-to-flag mappings from base.yaml registry.

    Args:
        feat_registry: Optional overridden feature registry.
                       If None, loads base.yaml directly.
    """
    if feat_registry is None:
        base = load_yaml("base")
        feat_registry = base.get("features", {})
    
    lines = []
    lines.append("# Auto-generated feature → configure flag mappings from base.yaml")
    lines.append("# DO NOT EDIT — regenerated by scripts/generate.py")
    lines.append("")

    for name, info in feat_registry.items():
        flag = info.get("flag", "")
        pkgconfig = info.get("pkgconfig", "")
        if not flag and not pkgconfig:
            continue
        if pkgconfig:
            lines.append(f'ffmpeg_feature_core({name} "{flag}" {pkgconfig})')
        else:
            lines.append(f'ffmpeg_feature({name} "{flag}")')
    
    return "\n".join(lines) + "\n"


def generate_portfile(version: str, family: str, patches: list[str],
                      base_options: str, debug_options: str, sha512: str) -> str:
    """Generate the portfile.cmake content."""
    major = family.split(".")[0]
    major_x = f"{major}.x"
    
    lines = []
    lines.append(f'set(FFMPEG_VERSION "{version}")')
    lines.append(f"set(FFMPEG_SHA512 {sha512})")
    lines.append(
        'set(FFMPEG_SHARED_DIR '
        f'"${{CMAKE_CURRENT_LIST_DIR}}/../../scripts/ffmpeg")'
    )
    lines.append(
        'set(FFMPEG_BUILDER_DIR '
        f'"${{CURRENT_INSTALLED_DIR}}/share/ffmpeg-builder")'
    )
    lines.append(
        'set(FFMPEG_PATCHES_DIR '
        f'"${{CMAKE_CURRENT_LIST_DIR}}/../../patches/{major_x}")'
    )
    if int(major) >= 8:
        lines.append('set(FFMPEG_NEED_BIN2C ON)')
    if base_options:
        lines.append(f'set(FFMPEG_BASE_OPTIONS "{base_options}")')
    if debug_options:
        lines.append(f'set(FFMPEG_OPTIONS_DEBUG "{debug_options}")')
    lines.append("set(FFMPEG_PATCHES")
    for p in patches:
        lines.append(f"    {p}")
    lines.append(")")
    lines.append('set(CURRENT_PORT_DIR "${CMAKE_CURRENT_LIST_DIR}")')
    lines.append(
        'include("${FFMPEG_BUILDER_DIR}/ffmpeg-portfile.cmake")'
    )
    return "\n".join(lines) + "\n"


def generate_vcpkg_json(version: str, port_name: str, features: dict,
                        defaults: list, feature_deps: dict, feature_refs: dict,
                        host_deps: list, base_registry: dict,
                        default_aliases: list, defines: dict) -> str:
    """Generate the vcpkg.json content."""
    feat_defs = {}
    for name, info in features.items():
        entry = {
            "description": info.get("description", f"Enable {name} support"),
        }
        deps = list(feature_deps.get(name, []))
        for ref in feature_refs.get(name, []):
            item = {"name": port_name, "features": [ref["name"]]}
            if ref.get("platform"):
                item["platform"] = ref["platform"]
            deps.append(item)
        if deps:
            entry["dependencies"] = deps
        feat_defs[name] = entry

    # --- Alias-based meta-features (from base.yaml define:) ---
    # All define aliases become vcpkg meta-features.
    # Features inside each alias are grouped by their platform condition
    # to reduce verbosity (same-platform features share one entry).

    # Helper: build alias dependency entries (no recursive expansion).
    # @ref entries become feature references, plain names are grouped by platform.
    def _build_alias_deps(alias_name):
        """Return merged dependency entries for an alias.

        Uses raw values from ``defines[alias_name]`` — ``@ref`` entries are
        kept as feature-name references instead of being expanded.
        """
        if alias_name not in defines:
            return None
        raw = defines[alias_name]
        no_platform = []
        platform_groups = {}
        alias_refs = set()

        for item in raw:
            if isinstance(item, str) and item.startswith("@"):
                ref = item[1:]
                if ref == "defaults":
                    continue  # handled by default-features
                if ref not in defines and ref not in features:
                    print(f"WARNING: @{ref} in alias '{alias_name}' — unknown target",
                          file=sys.stderr)
                    continue
                if ref != alias_name:
                    alias_refs.add(ref)
            elif item in features:
                info = base_registry.get(item, {})
                plat = info.get("platform")
                if plat:
                    platform_groups.setdefault(plat, []).append(item)
                else:
                    no_platform.append(item)

        items = []
        if no_platform:
            items.append({"name": port_name, "features": sorted(no_platform)})
        for plat in sorted(platform_groups):
            items.append({"name": port_name, "features": sorted(platform_groups[plat]),
                           "platform": plat})
        for ref in sorted(alias_refs):
            items.append({"name": port_name, "features": [ref]})
        return items

    for alias_name in sorted(defines):
        if alias_name in feat_defs or alias_name == "defaults":
            continue
        items = _build_alias_deps(alias_name)
        if items:
            feat_defs[alias_name] = {
                "description": f"{alias_name} feature group",
                "dependencies": items,
            }

    # License features (gpl / nonfree) are generated from YAML via the
    # per-feature loop above — no hardcoded definitions needed.

    # default-features: core features (avcodec, etc.), always active.
    # Meta-features never reference @core because vcpkg guarantees these.
    core_features = [f for f in defines.get("defaults", []) 
                     if isinstance(f, str) and not f.startswith("@")]
    if core_features:
        default_features = sorted(core_features)
    else:
        default_features = default_aliases if default_aliases else None

    json_data = {
        "name": port_name,
        "version": version,
        "port-version": 0,
        "description": [
            f"FFmpeg {version} build for MSVC (use 'static' feature for static libraries).",
        ],
        "homepage": "https://ffmpeg.org",
        "license": None,
        "dependencies": host_deps + [{"name": "ffmpeg-builder", "host": True}],
        "features": feat_defs,
    }
    if default_features:
        json_data["default-features"] = default_features

    return json.dumps(json_data, indent=2, ensure_ascii=False) + "\n"



# ---------------------------------------------------------------------------
# Usage file generation
# ---------------------------------------------------------------------------

def generate_usage():
    """Generate a concise vcpkg usage file with CMake targets."""
    lines = [
        "ffmpeg provides CMake targets:",
        "",
        "    # Modern imported targets (recommended)",
        "    find_package(FFMPEG REQUIRED)",
        "    target_link_libraries(main PRIVATE FFMPEG::ffmpeg)",
        "",
        "    # Or link individual modules",
        "    target_link_libraries(main PRIVATE",
        "        FFMPEG::avcodec",
        "        FFMPEG::avformat",
        "        FFMPEG::avutil",
        "        FFMPEG::avfilter",
        "        FFMPEG::avdevice",
        "        FFMPEG::swresample",
        "        FFMPEG::swscale",
        "    )",
        "",
        "    # Legacy variable-based usage",
        "    target_include_directories(main PRIVATE ${FFMPEG_INCLUDE_DIRS})",
        "    target_link_libraries(main PRIVATE ${FFMPEG_LIBRARIES})",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# README generation
# ---------------------------------------------------------------------------

def generate_readme(version, port_name, features, defines, default_aliases,
                    base_registry):
    """Generate a feature-documenting README.md for an FFmpeg port."""
    lines = []
    lines.append(f"# FFmpeg {version} — MSVC Prebuilt")
    lines.append("")
    lines.append("Built via [vcpkg](https://github.com/microsoft/vcpkg) ")
    lines.append("with MSVC on Windows.")
    lines.append("")
    lines.append("## Usage")
    lines.append("")
    lines.append("```cmake")
    lines.append("find_package(FFMPEG REQUIRED)")
    lines.append("target_link_libraries(main PRIVATE FFMPEG::ffmpeg)")
    lines.append("```")
    lines.append("")

    # Features table
    feat_list = sorted(features.items())
    lines.append(f"## Features ({len(feat_list)} total)")
    lines.append("")
    lines.append("| Feature | Flag | Description | Platform |")
    lines.append("|---------|------|-------------|----------|")
    for name, info in feat_list:
        flag = info.get("flag", "")
        desc = info.get("description", "")
        plat = info.get("platform", "")
        lines.append(f"| {name} | `{flag}` | {desc} | {plat} |")
    lines.append("")

    # Meta-features table
    meta_features = []
    for alias, raw in sorted(defines.items()):
        if alias == "defaults":
            continue
        expanded = []
        for item in raw:
            if item.startswith("@"):
                expanded.append(item)
            elif isinstance(item, str):
                expanded.append(item)
        meta_features.append((alias, ", ".join(expanded)))

    if meta_features:
        lines.append("## Meta-Features")
        lines.append("")
        lines.append("| Name | Includes |")
        lines.append("|------|----------|")
        for name, includes in meta_features:
            lines.append(f"| {name} | {includes} |")
        lines.append("")

    # Default features
    defaults = sorted(default_aliases) if default_aliases else []
    if not defaults:
        defaults = []
        for item in defines.get("defaults", []):
            if isinstance(item, str) and not item.startswith("@"):
                defaults.append(item)
    if defaults:
        lines.append("## Default Features")
        lines.append("")
        lines.append(", ".join(sorted(defaults)))
        lines.append("")

    # Find external dependencies (package deps)
    pkg_deps = set()
    for name, info in features.items():
        for dep in info.get("depends", []):
            if isinstance(dep, str) and not dep.startswith("@"):
                pkg_deps.add(dep)
    if pkg_deps:
        lines.append("## External Dependencies")
        lines.append("")
        lines.append(", ".join(sorted(pkg_deps)))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate(version_str: str, force: bool = False):
    """Generate port directories for a given FFmpeg version."""
    parts = version_str.split(".")
    if len(parts) not in (2, 3):
        print(f"ERROR: version must be X.Y or X.Y.Z, got '{version_str}'",
              file=sys.stderr)
        sys.exit(1)
    major = int(parts[0])

    # Resolve YAML chain
    docs, family = resolve_chain(version_str)

    # Merge features
    feats = merge_features(docs, version_str)
    print(f"  Features: {len(feats['features'])} resolved")

    # Merge source
    source = get_source(docs)
    sha512 = source.get("sha512", "TODO")

    # Merge build
    build = merge_dict_chain(docs, "build")
    base_opts = build.get("base_options", "")
    debug = build.get("debug", {})
    debug_opts = debug.get("options", "")
    host_deps = build.get("host_deps", [])

    # dep_overrides
    dep_overrides = merge_dict_chain(docs, "dep_overrides")
    feature_deps, feature_refs, _ = collect_deps(feats['features'], dep_overrides, host_deps)
    print(f"  Deps: {sum(len(v) for v in feature_deps.values())} packages")

    # Patches
    patches = get_patches(docs)
    print(f"  Patches: {len(patches)} files")

    # Verify patches exist
    patches_dir = REPO_ROOT / "patches" / f"{major}.x"
    for p in patches:
        if not (patches_dir / p).is_file():
            print(f"  WARNING: patch '{p}' not found at {patches_dir}",
                  file=sys.stderr)

    # Determine port name
    if len(parts) == 2:
        port_base = f"ffmpeg-{parts[0]}-{parts[1]}"
    else:
        port_base = f"ffmpeg-{parts[0]}-{parts[1]}-{parts[2]}"

    print(f"Version: {version_str} -> family={family}, port_base={port_base}")

    import shutil

    port_name = port_base
    port_dir = PORTS_DIR / port_name

    if port_dir.exists():
        if not force:
            print(f"  SKIP {port_dir.name} (exists, use --force to overwrite)")
            return
        shutil.rmtree(str(port_dir))

    port_dir.mkdir(parents=True, exist_ok=True)

    # portfile.cmake
    (port_dir / "portfile.cmake").write_text(
        generate_portfile(version_str, family, patches, base_opts, debug_opts, sha512),
        encoding="utf-8")

    # vcpkg.json
    (port_dir / "vcpkg.json").write_text(
        generate_vcpkg_json(version_str, port_name, feats["features"],
                            feats["defaults"], feature_deps, feature_refs,
                            host_deps, docs[0]["features"],
                            feats["default_aliases"], docs[0].get("define", {})),
        encoding="utf-8")

    # features.cmake  (use overridden registry so version YAML flag changes apply)
    (port_dir / "features.cmake").write_text(
        generate_features_cmake(feat_registry=docs[0]["features"]),
        encoding="utf-8")

    # --- README ---
    readme_content = generate_readme(
        version_str, port_name, feats["features"],
        docs[0].get("define", {}), feats["default_aliases"],
        docs[0]["features"])
    (port_dir / "README.md").write_text(readme_content, encoding="utf-8")

    # --- Usage ---
    usage_content = generate_usage()
    (port_dir / "usage").write_text(usage_content, encoding="utf-8")

    file_count = len(list(port_dir.iterdir()))
    print(f"  Generated {port_dir.name}/ ({file_count} files)")


def list_families():
    """List available version families and patch YAMLs (non-base files)."""
    found = False
    for f in sorted(YAML_DIR.glob("*.yaml")):
        if f.stem == "base":
            continue
        print(f.stem)
        found = True
    if not found:
        print("(no version YAML files found)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Generate vcpkg ports from YAML")
    parser.add_argument("--version", help="FFmpeg version (e.g. 8.1.1)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing port directories")
    parser.add_argument("--list-families", action="store_true",
                        help="List available version YAML files")
    parser.add_argument("--generate-deps", action="store_true",
                        help="Generate ffmpeg-deps virtual port from base.yaml")

    args = parser.parse_args()

    if args.list_families:
        list_families()
        return
    if args.generate_deps:
        generate_deps_port()
        return
    if args.version:
        generate(args.version, args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
