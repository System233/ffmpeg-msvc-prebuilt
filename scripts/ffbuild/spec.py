"""Declarative FFmpeg build configuration and policy model.

This is a CI-facing compiler for the project's YAML schema.  It owns no
legacy ffport interfaces and performs no vcpkg dependency resolution: vcpkg
remains responsible for package features, transitive deps, and ABI caching.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


SPEC_ROOT = Path(__file__).resolve().parents[2] / "ffmpeg"
_RELEASE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_CONDITION = re.compile(r"^(>=|<=|>|<)(\d+(?:\.\d+){1,2})$")
_RULE = re.compile(r"^(feature|package):([A-Za-z0-9_.+-]+)$")


def _platform_applies(expression: str, triplet: str) -> bool:
    """Evaluate the vcpkg platform expressions used by our feature edges.

    The 'arm' predicate intentionally covers both arm32 and arm64, matching
    vcpkg's platform vocabulary; 'arm32' excludes arm64.
    Unknown predicates and unsupported syntax fail closed rather than
    silently producing a different feature closure.
    """
    architecture = triplet.split("-", 1)[0]
    flags = {
        "x86": architecture == "x86",
        "x64": architecture == "x64",
        "arm": architecture in ("arm", "arm64"),
        "arm32": architecture == "arm",
        "arm64": architecture == "arm64",
        "windows": "windows" in triplet,
        "uwp": "uwp" in triplet,
        "xbox": "xbox" in triplet,
    }
    tokens = re.findall(r"\s*(!|&|\||\(|\)|[a-z][a-z0-9]*)", expression)
    if "".join(tokens) != re.sub(r"\s+", "", expression):
        raise ValueError(f"Unsupported vcpkg platform expression: {expression!r}")
    index = 0

    def atom() -> bool:
        nonlocal index
        if index >= len(tokens):
            raise ValueError(f"Incomplete vcpkg platform expression: {expression!r}")
        token = tokens[index]
        index += 1
        if token == "!":
            return not atom()
        if token == "(":
            value = disjunction()
            if index >= len(tokens) or tokens[index] != ")":
                raise ValueError(f"Unclosed vcpkg platform expression: {expression!r}")
            index += 1
            return value
        if token not in flags:
            raise ValueError(f"Unknown vcpkg platform predicate: {token!r}")
        return flags[token]

    def conjunction() -> bool:
        nonlocal index
        value = atom()
        while index < len(tokens) and tokens[index] == "&":
            index += 1
            rhs = atom()
            value = value and rhs
        return value

    def disjunction() -> bool:
        nonlocal index
        value = conjunction()
        while index < len(tokens) and tokens[index] == "|":
            index += 1
            rhs = conjunction()
            value = value or rhs
        return value

    answer = disjunction()
    if index != len(tokens):
        raise ValueError(f"Unexpected vcpkg platform token in {expression!r}")
    return answer


def _merge(current: dict, changes: dict) -> dict:
    merged = dict(current)
    for key, value in changes.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _version_match(expression: str | None, version: str) -> bool:
    if not expression:
        return True
    try:
        actual = tuple(int(x) for x in version.split("."))
    except ValueError:
        return False

    def matches(token: str) -> bool:
        result = _CONDITION.fullmatch(token)
        if not result:
            raise ValueError(f"Invalid version condition: {token}")
        compare = tuple(int(x) for x in result.group(2).split("."))
        size = max(len(actual), len(compare))
        lhs, rhs = actual + (0,) * (size - len(actual)), compare + (0,) * (size - len(compare))
        operator = result.group(1)
        return {">=": lhs >= rhs, ">": lhs > rhs, "<=": lhs <= rhs,
                "<": lhs < rhs}[operator]

    return any(all(matches(term) for term in clause.split())
               for clause in expression.split(","))


def _items(value: Any) -> list:
    return value if isinstance(value, list) else ([] if value is None else [value])


def read_spec(name: str, *, directory: Path = SPEC_ROOT) -> tuple[dict, tuple[Path, ...]]:
    """Resolve YAML inheritance exactly once; return normalized configuration and provenance.

    An X.Y.Z patch document is optional, while its X.Y family is required.
    Explicit `extends` is followed for master and custom configurations.
    Cycles, missing parents, and malformed YAML are rejected immediately.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError(f"Invalid configuration name: {name!r}")
    names: list[str] = []

    def visit(stem: str) -> None:
        if stem in names:
            raise ValueError(f"Cyclic YAML inheritance at {stem}")
        file = directory / f"{stem}.yaml"
        if not file.is_file():
            raise FileNotFoundError(f"Missing version configuration: {file}")
        doc = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        if not isinstance(doc, dict):
            raise ValueError(f"Expected YAML mapping: {file}")
        if stem != "base":
            parent = doc.get("extends", "base")
            if parent == stem:
                raise ValueError(f"Cyclic YAML inheritance at {stem}")
            if parent not in names:
                visit(parent)
        names.append(stem)

    if _RELEASE.fullmatch(name) and len(name.split(".")) == 3:
        family = ".".join(name.split(".")[:2])
        visit(family)
        if (directory / f"{name}.yaml").is_file():
            visit_patch = yaml.safe_load((directory / f"{name}.yaml").read_text(encoding="utf-8")) or {}
            if not isinstance(visit_patch, dict):
                raise ValueError(f"Expected YAML mapping: {name}")
            # Snapshot-derived full patch documents can still declare `base`;
            # the explicit release family is loaded first by design.
            names.append(name)
    else:
        visit(name)

    merged: dict = {}
    files: list[Path] = []
    for stem in names:
        file = directory / f"{stem}.yaml"
        document = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        if "revision" in document:
            raise ValueError(f"Manual FFmpeg revision is no longer supported: {file.name}")
        merged = _merge(merged, document)
        files.append(file)
    return merged, tuple(files)


@dataclass(frozen=True)
class FeatureSet:
    definitions: dict[str, dict]
    defaults: tuple[str, ...]
    packages: dict[str, tuple[str | dict, ...]]
    references: dict[str, tuple[tuple[str, str | None], ...]]
    host_packages: tuple[str | dict, ...]

    def closure(self, roots: list[str] | tuple[str, ...],
                triplet: str | None = None) -> set[str]:
        selected: set[str] = set()
        stack = list(roots) + list(self.defaults)
        while stack:
            current = stack.pop()
            if current in selected:
                continue
            if current not in self.definitions:
                raise ValueError(f"Missing FFmpeg feature: {current}")
            selected.add(current)
            for name, platform in self.references.get(current, ()):
                effective = platform or self.definitions[name].get("platform")
                if triplet is None or not effective or _platform_applies(effective, triplet):
                    stack.append(name)
        return selected

    def policy_errors(self, selected: set[str]) -> list[str]:
        packages = {p if isinstance(p, str) else p.get("name", "")
                    for feature in selected for p in self.packages.get(feature, ())}
        packages.update(p if isinstance(p, str) else p.get("name", "")
                        for p in self.host_packages)
        errors: list[str] = []
        for feature in sorted(selected):
            info = self.definitions[feature]
            license_ = info.get("license")
            if license_ not in (None, "lgpl", "gpl", "nonfree"):
                errors.append(f"{feature}: unsupported license requirement {license_!r}")
            if license_ in ("gpl", "nonfree") and f"license-{license_}" not in selected:
                errors.append(f"{feature}: requires explicitly selected {license_} mode")
            for relation in ("requires", "conflicts"):
                for value in _items(info.get(relation)):
                    match = _RULE.fullmatch(value) if isinstance(value, str) else None
                    if not match:
                        errors.append(f"{feature}: invalid {relation}: {value!r}")
                        continue
                    kind, name = match.groups()
                    if kind == "feature" and name not in self.definitions:
                        errors.append(f"{feature}: unknown referenced feature {name}")
                        continue
                    present = name in (selected if kind == "feature" else packages)
                    if (relation == "requires" and not present) or (relation == "conflicts" and present):
                        errors.append(f"{feature}: {relation} {value}")
        return errors


def resolve_features(config: dict, version: str) -> FeatureSet:
    registry = config.get("features", {})
    aliases = config.get("define", {})

    def expand(values: Any, seen: frozenset[str] = frozenset()) -> set[str]:
        expanded: set[str] = set()
        for entry in _items(values):
            if not isinstance(entry, str):
                raise ValueError(f"Invalid feature expression: {entry!r}")
            for token in entry.split(","):
                token = token.strip()
                if not token:
                    continue
                if token.startswith("@"):
                    alias = token[1:]
                    if alias in seen:
                        raise ValueError(f"Recursive feature alias: {alias}")
                    if alias in aliases:
                        expanded.update(expand(aliases[alias], seen | {alias}))
                    elif alias in registry:
                        expanded.add(alias)
                else:
                    expanded.add(token)
        return expanded

    excluded = expand(aliases.get("exclude", []))
    requested = expand(aliases.get("include", list(registry)))
    for info in registry.values():
        for item in _items(info.get("depends")):
            ref = item if isinstance(item, str) else item.get("name", "")
            if ref.startswith("@") and ref[1:] in registry:
                requested.add(ref[1:])
    for alias, values in aliases.items():
        if alias not in {"include", "exclude", "defaults"}:
            requested.update(x for x in expand(values) if x in registry)
    matched = {key: registry[key] for key in sorted(registry)
               if key in requested and not any(fnmatch.fnmatch(key, e) for e in excluded)
               and _version_match(registry[key].get("version"), version)}
    defaults = tuple(sorted(expand(aliases.get("defaults", [])) & matched.keys()))
    deps: dict[str, tuple[str | dict, ...]] = {}
    refs: dict[str, tuple[tuple[str, str | None], ...]] = {}
    replacements = config.get("dep_overrides", {})
    for feature, info in matched.items():
        external: list[str | dict] = []
        internal: list[tuple[str, str | None]] = []
        for entry in _items(info.get("depends")):
            value = entry if isinstance(entry, str) else entry.get("name", "")
            if not value:
                continue
            platform = entry.get("platform") if isinstance(entry, dict) else None
            if value.startswith("@"):
                target = value[1:]
                if target in matched:
                    internal.append((target, platform))
                elif target not in registry:
                    raise ValueError(f"{feature}: unknown Feature @{target}")
            else:
                replacement = replacements.get(feature, value)
                dep = {**entry, "name": replacement} if isinstance(entry, dict) else replacement
                external.append(dep)
        deps[feature] = tuple(external)
        refs[feature] = tuple(internal)
    # A version may tighten an inherited dependency's license (e.g. FFmpeg
    # 3.4 OpenSSL).  Meta-feature closures must follow the *effective* license,
    # not silently pull nonfree components through an LGPL aggregate.
    for aggregate in ("lgpl", "gpl"):
        if aggregate not in refs:
            continue
        keep: list[tuple[str, str | None]] = []
        for target, platform in refs[aggregate]:
            required = matched.get(target, {}).get("license")
            if required == "nonfree" or (aggregate == "lgpl" and required == "gpl"):
                owner = required
                if owner in refs and (target, platform) not in refs[owner]:
                    refs[owner] = (*refs[owner], (target, platform))
            else:
                keep.append((target, platform))
        refs[aggregate] = tuple(keep)
    return FeatureSet(matched, defaults, deps, refs,
                      tuple(config.get("build", {}).get("host_deps", [])))
