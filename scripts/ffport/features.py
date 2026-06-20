"""Feature resolution and dependency collection."""

import fnmatch


def expand_items(items: list, defines: dict, registry: dict | None = None) -> set:
    """Expand @aliases into a flat set of feature names.

    *defines* holds alias groups (``include``, ``exclude``, ``defaults``).
    *registry* (optional) holds feature definitions; when an ``@`` reference is
    not found in *defines*, the feature name itself is used (not expanded).
    """
    result = set()
    for item in items:
        if isinstance(item, str):
            item = item.strip()
            if item.startswith("@"):
                alias = item[1:]
                if alias in defines:
                    result.update(expand_items(defines[alias], defines, registry))
                elif registry and alias in registry:
                    result.add(alias)
                continue
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

    Syntax: comma-separated OR groups, each group has space-separated AND.
    Operators: >= > <= <
    """
    if not gate:
        return True
    try:
        target = tuple(int(x) for x in target_version.split('.'))
    except ValueError:
        return False
    groups = [g.strip() for g in gate.split(',')]
    for group in groups:
        conditions = group.split()
        ok = True
        for cond in conditions:
            for op in ('>=', '<=', '>', '<'):
                if cond.startswith(op):
                    ver_str = cond[len(op):]
                    try:
                        ver = tuple(int(x) for x in ver_str.split('.'))
                    except ValueError:
                        ok = False
                        break
                    if op == '>=' and not target >= ver:
                        ok = False
                    elif op == '<=' and not target <= ver:
                        ok = False
                    elif op == '>' and not target > ver:
                        ok = False
                    elif op == '<' and not target < ver:
                        ok = False
                    break
            else:
                ok = False
            if not ok:
                break
        if ok:
            return True
    return False


def resolve_features(merged: dict, version_str: str | None = None) -> dict:
    """Resolve feature include/exclude/defaults from a single merged dict.

    Returns:
        features: dict     {name: info, ...}  — filtered feature registry
        defaults: list     sorted default feature names
    """
    registry = merged.get("features", {})
    defines = merged.get("define", {})

    include_raw = defines.get("include", list(registry.keys()))
    included = expand_items(include_raw, defines)

    exclude_raw = defines.get("exclude", [])
    excluded = expand_items(exclude_raw, defines)
    included = apply_exclusions(included, excluded)

    if version_str:
        for name in list(included):
            gate = registry.get(name, {}).get("version")
            if gate and not version_gate_match(gate, version_str):
                included.discard(name)

    # Auto-include @ref targets
    for name, info in registry.items():
        for dep in _normalise_list(info.get("depends", [])):
            if isinstance(dep, str) and dep.startswith("@") and dep[1:] in registry:
                included.add(dep[1:])

    # Auto-include features referenced by alias definitions
    for alias_name, alias_items in defines.items():
        if alias_name in ("include", "exclude", "defaults"):
            continue
        for item in alias_items:
            if isinstance(item, str) and not item.startswith("@") and item in registry:
                included.add(item)

    # Re-apply exclusions after auto-includes
    included = apply_exclusions(included, excluded)

    # Re-apply version-gate
    if version_str:
        for name in list(included):
            gate = registry.get(name, {}).get("version")
            if gate and not version_gate_match(gate, version_str):
                included.discard(name)

    # Intersect with registry
    included = {f for f in included if f in registry}

    # Defaults — expand @references against defines first, then features
    defaults = expand_items(defines.get("defaults", []), defines, registry)
    defaults = apply_exclusions(defaults, excluded)
    defaults = {f for f in defaults if f in registry}
    defaults &= included

    return {
        "features": {k: dict(registry[k]) for k in sorted(included)},
        "defaults": sorted(defaults),
    }


def collect_deps(features: dict, dep_overrides: dict, host_deps: list,
                 all_registry_names: set | None = None):
    """Build per-feature dependency and feature-reference maps.

    Returns (feature_deps, feature_refs, host_deps).
    """
    if all_registry_names is None:
        all_registry_names = set(features.keys())

    feature_deps = {}
    feature_refs = {}

    for name, info in features.items():
        raw = _normalise_list(info.get("depends", []))
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
                        if ref_name not in all_registry_names:
                            print(f"WARNING: depends @{ref_name} in feature '{name}' — not found",
                                  file=__import__('sys').stderr)
                        continue
                    refs.append({"name": ref_name})
                else:
                    pkg_deps.append(override if override else item)
            elif isinstance(item, dict):
                n = item.get("name", "")
                if n.startswith("@"):
                    ref_name = n[1:]
                    if ref_name not in features:
                        if ref_name not in all_registry_names:
                            print(f"WARNING: depends @{ref_name} in feature '{name}' — not found",
                                  file=__import__('sys').stderr)
                        continue
                    refs.append({"name": ref_name, "platform": item.get("platform")})
                else:
                    if override and isinstance(item.get("name"), str):
                        item = dict(item)
                        item["name"] = override
                    pkg_deps.append(item)
            else:
                continue

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


def _normalise_list(raw):
    """Normalise a value to a list."""
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, dict):
        return [raw]
    return list(raw) if raw else []
