"""CI build targets expressed as native vcpkg package specifications.

The declared features are compiled against the current version's feature
graph to form a deterministic *requested* feature closure.  The packager
checks that vcpkg actually produced this closure before publication.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .spec import FeatureSet, resolve_features
from .versions import ROOT


DEFAULT_TARGETS = ROOT / "ffbuild" / "targets.yaml"
_PACKAGE = re.compile(r"^ffmpeg(?:\[([a-z0-9+._-]+(?:,[a-z0-9+._-]+)*)\])?$")
_TRIPLET = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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


def load_targets(path: Path = DEFAULT_TARGETS) -> tuple[Target, ...]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"targets"} or not isinstance(document["targets"], list):
        raise ValueError(f"Expected a targets list in {path}")
    targets: list[Target] = []
    seen: set[tuple[str, str]] = set()
    for row in document["targets"]:
        if not isinstance(row, dict) or set(row) != {"package", "triplet"}:
            raise ValueError(f"Target must contain only package and triplet: {row!r}")
        package, roots = parse_package(row["package"])
        triplet = row["triplet"]
        if not isinstance(triplet, str) or not _TRIPLET.fullmatch(triplet) or not (ROOT / "triplets" / f"{triplet}.cmake").is_file():
            raise ValueError(f"Unknown vcpkg triplet: {triplet!r}")
        if (package, triplet) in seen:
            raise ValueError(f"Duplicate build target: {package}:{triplet}")
        seen.add((package, triplet))
        targets.append(Target(package, triplet, roots))
    if not targets:
        raise ValueError("The CI target list is empty")
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
    # Include both requested roots and their current resolved closure.  This
    # intentionally changes if a version adds or removes dependent features.
    identity = {"package": target.package, "features": features}
    feature_hash = hashlib.sha256(json.dumps(identity, separators=(",", ":"),
                                             sort_keys=True).encode("utf-8")).hexdigest()
    mode = "nonfree" if "license-nonfree" in selected else ("gpl" if "license-gpl" in selected else "lgpl")
    linkage = "static" if "static" in selected else "shared"
    return {"package": target.package, "triplet": target.triplet,
            "features": features, "feature_hash": feature_hash,
            "license": mode, "linkage": linkage}
