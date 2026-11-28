"""CI build targets expressed as native vcpkg package specifications.

The declared features are compiled against the current version's feature
graph to form a deterministic *requested* feature closure.  The packager
checks that vcpkg actually produced this closure before publication.
"""

from __future__ import annotations

import re
import os
from itertools import product
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path


from .spec import FeatureSet, resolve_features
from .versions import ROOT


_PACKAGE = re.compile(r"^ffmpeg(?:\[([a-z0-9+._-]+(?:,[a-z0-9+._-]+)*)\])?$")


@dataclass(frozen=True)
class Target:
    package: str
    triplet: str
    roots: tuple[str, ...]


def parse_package(value: str) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, str) or not (match := _PACKAGE.fullmatch(value)):
        raise ValueError(f"Expected an FFmpeg vcpkg[features] package spec, got {value!r}")
    roots = tuple(sorted(set((match.group(1) or "").split(",")) - {""}))
    if not roots:
        raise ValueError("An explicit FFmpeg feature selection is required")
    return f"{value.split('[', 1)[0]}[{','.join(roots)}]", roots


def parse_ci_env(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or name in values or not value.strip():
            raise ValueError(f"Invalid CI environment declaration: {line!r}")
        values[name] = value.strip()
    return values


@lru_cache(maxsize=1)
def workflow_defaults() -> dict[str, str]:
    """The shared version-controlled environment is also the local default."""
    return parse_ci_env((ROOT / ".github/ci.env").read_text(encoding="utf-8"))


def ci_setting(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        value = workflow_defaults()[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Empty CI setting: {name}")
    return value


def matrix_axes(environ: dict[str, str] | None = None) -> dict[str, tuple[str, ...]]:
    from .native_platform import PE_MACHINE
    allowed = {"TRIPLETS": set(PE_MACHINE), "LICENSES": {"lgpl", "gpl"},
               "LINKAGES": {"shared", "static"}}
    axes = {}
    for key, supported in allowed.items():
        value = ci_setting(key) if environ is None else environ.get(key)
        if not isinstance(value, str):
            raise ValueError(f"Missing matrix declaration: {key}")
        values = tuple(value.split())
        if not values or len(values) != len(set(values)) or not set(values) <= supported:
            raise ValueError(f"Invalid {key}: {values!r}")
        axes[key] = values
    return axes


def configured_triplets() -> tuple[str, ...]:
    return matrix_axes()["TRIPLETS"]


def load_targets(*, environ: dict[str, str] | None = None) -> tuple[Target, ...]:
    axes = matrix_axes(environ)
    targets = []
    for triplet, license_, linkage in product(axes["TRIPLETS"], axes["LICENSES"], axes["LINKAGES"]):
        if not (ROOT / "triplets" / f"{triplet}.cmake").is_file():
            raise ValueError(f"Missing vcpkg triplet: {triplet}")
        package, roots = parse_package(f"ffmpeg[all-{license_}{',static' if linkage == 'static' else ''}]")
        targets.append(Target(package, triplet, roots))
    return tuple(targets)


def compile_target(config: dict, version: str, target: Target) -> dict:
    graph: FeatureSet = resolve_features(config, version)
    # Match the platform-conditioned self-dependency edges in the generated
    # vcpkg manifest, rather than expecting disabled Features in CONTROL.
    selected = graph.closure(target.roots, triplet=target.triplet)
    failures = graph.policy_errors(selected)
    if failures:
        raise ValueError("; ".join(failures))
    features = sorted(selected)
    mode = "nonfree" if "license-nonfree" in selected else ("gpl" if "license-gpl" in selected else "lgpl")
    linkage = "static" if "static" in selected else "shared"
    return {"package": target.package, "triplet": target.triplet,
            "features": features,
            "license": mode, "linkage": linkage}


def select_targets(*, arch: str = "", license_: str = "") -> tuple[Target, ...]:
    targets = tuple(t for t in load_targets()
                    if (not arch or t.triplet == arch) and
                    (not license_ or f"all-{license_}" in t.roots))
    if not targets:
        raise ValueError("No matching native targets")
    return targets


def require_complete_targets(rows: list[dict], *, version: str,
                             targets: tuple[Target, ...]) -> None:
    expected = {(t.triplet, t.package) for t in targets}
    identities = [(r.get("triplet"), r.get("package")) for r in rows]
    actual = set(identities)
    if (not expected or len(identities) != len(actual) or actual != expected
            or any(r.get("yaml") != version for r in rows)):
        raise ValueError(f"Incomplete CI target matrix: missing={sorted(expected-actual, key=str)}, "
                         f"unexpected={sorted(actual-expected, key=str)}, "
                         f"duplicates={len(identities)-len(actual)}")
