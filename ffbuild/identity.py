"""Release identity contract shared by the local data index and artifact writer."""

from __future__ import annotations

import re


def normalize_version(version: str) -> str:
    value = version.removeprefix("n").split("+", 1)[0]
    if not re.fullmatch(r"\d+\.[A-Za-z0-9.+-]+", value):
        raise ValueError(f"Invalid upstream/release version: {version!r}")
    return value


def version_dir(version: str, revision: int = 0) -> str:
    if revision < 0:
        raise ValueError("Negative vcpkg port revision")
    normalized = normalize_version(version)
    return normalized if revision == 0 else f"{normalized}-r{revision}"


def family_dir(version: str) -> str:
    return f"{int(normalize_version(version).split('.', 1)[0])}.x"


def variant_name(version: str, revision: int, triplet: str,
                 linkage: str, license_: str, feature_hash: str | None = None,
                 *, abi_hash: str | None = None) -> str:
    if linkage not in ("static", "shared") or license_ not in ("lgpl", "gpl", "nonfree"):
        raise ValueError("Invalid variant linkage or license")
    if triplet not in ("x64-windows", "x86-windows", "arm-windows", "arm64-windows"):
        raise ValueError(f"Unknown triplet: {triplet}")
    suffix = ""
    if feature_hash is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", feature_hash):
            raise ValueError("Invalid feature identity")
        suffix = "-f" + feature_hash[:12]
    if abi_hash is not None:
        if feature_hash is not None or not re.fullmatch(r"[0-9a-f]{64}", abi_hash):
            raise ValueError("Native ABI and Feature hashes cannot be mixed")
        suffix = "-a" + abi_hash[:12]
    return f"ffmpeg-{version_dir(version, revision)}_{triplet}-{linkage}-{license_}{suffix}"


def release_tag(version: str, revision: int = 0) -> str:
    return "ffmpeg-" + version_dir(version, revision)


def variant_path(version: str, revision: int, triplet: str,
                 linkage: str, license_: str, feature_hash: str | None = None,
                 *, abi_hash: str | None = None) -> str:
    suffix = ""
    if feature_hash is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", feature_hash):
            raise ValueError("Invalid feature identity")
        suffix = "-f" + feature_hash[:12]
    if abi_hash is not None:
        if feature_hash is not None or not re.fullmatch(r"[0-9a-f]{64}", abi_hash):
            raise ValueError("Native ABI and Feature hashes cannot be mixed")
        suffix = "-a" + abi_hash[:12]
    return (f"{family_dir(version)}/{version_dir(version, revision)}/variants/"
            f"{triplet}-{linkage}-{license_}{suffix}.yaml")


def is_lts(version: str) -> bool:
    """LTS releases: 4.4 and odd-minor .1 families; snapshots are never LTS."""
    clean = re.sub(r"-h[0-9a-f]{12,64}$", "", normalize_version(version))
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", clean):
        return False
    major, minor = map(int, clean.split(".")[:2])
    return (major, minor) == (4, 4) or minor == 1
