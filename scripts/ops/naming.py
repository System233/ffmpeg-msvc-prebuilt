#!/usr/bin/env python3
"""
Centralized naming for FFmpeg MSVC prebuilt CI.

All variant IDs, filenames, release tags, and data branch paths
are built and parsed here to ensure consistency.

Usage as CLI:
    python scripts/ops/naming.py variant-id --version 8.1.1 --revision 2 --triplet x64-windows --linkage shared --license gpl
    python scripts/ops/naming.py release-tag --version 8.1.1 --revision 2
    python scripts/ops/naming.py data-path --version 8.1.1 --revision 2 --triplet x64-windows --linkage shared --license gpl
    python scripts/ops/naming.py parse --variant-id "ffmpeg-8.1.1-r2_x64-windows-shared-gpl"
    python scripts/ops/naming.py major --version 8.1.1
    python scripts/ops/naming.py clean --version "7.1-20260101+dev-10-gabcd"
    python scripts/ops/naming.py version-dir --version 8.1.1 --revision 2
    python scripts/ops/naming.py zip-name --variant-id "ffmpeg-8.1.1-r2_x64-windows-shared-gpl" [--dev]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARCH_NAMES = {"x64", "x86", "arm64", "arm"}
VALID_LINKAGES = {"shared", "static"}
VALID_LICENSES = {"gpl", "lgpl", "nonfree"}

VERSION_DIR_RE = re.compile(r"^(.+?)(?:-r(\d+))?$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_version(version: str) -> str:
    """Remove ``+dev...`` suffix from a version string.

    ``"7.1-20260101+dev-10-gabcd"`` → ``"7.1-20260101"``
    ``"8.1.1"`` → ``"8.1.1"``
    """
    return version.split("+", 1)[0]


def major_version(version: str) -> str:
    """Extract the ``"X.x"`` major version from a version string.

    Strips leading ``"n"`` if present, then extracts the first dotted
    component as the major number.

    * ``"8.1.1"`` → ``"8.x"``
    * ``"7.1-20260101"`` → ``"7.x"``
    * ``"n8.1.1"`` → ``"8.x"``
    """
    s = version.lstrip("n")
    major = s.split("-")[0].split(".")[0]
    return f"{major}.x"


def build_variant_prefix(*, version: str, revision: int = 0) -> str:
    """Build the artifact download prefix for all variants of a version.

    ``ffmpeg-{version}[-r{rev}]_`` — matches every variant ID
    (e.g. ``ffmpeg-8.1.1-r2_x64-windows-shared-gpl``).
    """
    ver = make_version_dir(version=version, revision=revision)
    return f"ffmpeg-{ver}_"


def build_variant_id(
    *,
    version: str,
    revision: int = 0,
    triplet: str,
    linkage: str,
    license: str,
) -> str:
    """Build a variant ID string.

    Format: ``ffmpeg-{version}[-r{rev}]_{triplet}-{linkage}-{license}``

    Note the ``_`` separator between the version part and the triplet.
    """
    ver = make_version_dir(version=version, revision=revision)
    return f"ffmpeg-{ver}_{triplet}-{linkage}-{license}"


def build_release_tag(*, version: str, revision: int = 0) -> str:
    """Build a release tag string.

    ``ffmpeg-{version}[-r{rev}]``

    Example: ``version="8.1.1"``, ``revision=2`` → ``"ffmpeg-8.1.1-r2"``
    Example: ``version="7.1-20260101"``, ``revision=0`` → ``"ffmpeg-7.1-20260101"``
    """
    ver = make_version_dir(version=version, revision=revision)
    return f"ffmpeg-{ver}"


def build_zip_name(variant_id: str, dev: bool = False) -> str:
    """Build the ZIP archive filename for a variant.

    Returns ``{variant_id}.zip`` or ``{variant_id}-develop.zip``.
    """
    if dev:
        return f"{variant_id}-develop.zip"
    return f"{variant_id}.zip"


def build_var_yaml_name(variant_id: str) -> str:
    """Build the ``.var.yaml`` filename for a variant."""
    return f"{variant_id}.var.yaml"


def build_data_path(
    *,
    version: str,
    revision: int = 0,
    triplet: str,
    linkage: str,
    license: str,
) -> str:
    """Build the data branch relative path for a variant.

    Format: ``{major}/{version}[-r{rev}]/variants/{triplet}-{linkage}-{license}.yaml``
    """
    major = major_version(version)
    ver = make_version_dir(version=version, revision=revision)
    return f"{major}/{ver}/variants/{triplet}-{linkage}-{license}.yaml"


def make_version_dir(*, version: str, revision: int = 0) -> str:
    """Build the version directory name used on the data branch.

    Strips leading ``"n"`` if present (same as :func:`major_version`).

    ``{version}-r{rev}`` if revision is non-zero, otherwise just ``{version}``.

    Example: ``"8.1.1"``, ``revision=2`` → ``"8.1.1-r2"``
    Example: ``"7.1-20260101"``, ``revision=0`` → ``"7.1-20260101"``
    Example: ``"n8.2-dev-10-gabc1234"``, ``revision=0`` → ``"8.2-dev-10-gabc1234"``
    """
    version = version.lstrip("n")
    if revision:
        return f"{version}-r{revision}"
    return version


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_variant_id(variant_id: str) -> dict[str, Any]:
    """Parse a variant_id string into its components.

    Supports **two formats**:

    * **New format** (with ``_`` separator)::

        ffmpeg-{version}[-r{rev}]_{triplet}-{linkage}-{license}

      Example: ``ffmpeg-8.1.1-r2_x64-windows-shared-gpl``

    * **Legacy format** (all ``-`` separators)::

        ffmpeg-{ffmpeg_ref}-r{rev}-{triplet}-{linkage}-{license}

      Example: ``ffmpeg-n8.1.1-r2-x64-windows-shared-gpl``

    Returns:
        dict with keys: version, revision, version_id, clean_version,
        ffmpeg_ref, triplet, linkage, license, arch, variant_key, major.
    """
    if not variant_id.startswith("ffmpeg-"):
        raise ValueError(f"variant_id must start with 'ffmpeg-': {variant_id!r}")
    body = variant_id[len("ffmpeg-"):]

    if "_" in body:
        return _parse_variant_id_new(body, variant_id)
    else:
        return _parse_variant_id_legacy(body, variant_id)


def _parse_variant_id_new(body: str, variant_id: str) -> dict[str, Any]:
    """Parse a new-format variant_id (with ``_`` separator)."""
    # Split on first underscore
    version_part, right = body.split("_", 1)

    # Parse right: last segment = license, second-to-last = linkage, rest = triplet
    right_parts = right.split("-")
    license_val = right_parts[-1]
    linkage = right_parts[-2]
    if linkage not in VALID_LINKAGES:
        raise ValueError(
            f"Invalid linkage {linkage!r} in variant_id {variant_id!r} "
            f"(expected one of {VALID_LINKAGES})"
        )
    if license_val not in VALID_LICENSES:
        raise ValueError(
            f"Invalid license {license_val!r} in variant_id {variant_id!r} "
            f"(expected one of {VALID_LICENSES})"
        )
    triplet = "-".join(right_parts[:-2])

    # Parse version_part: extract revision from trailing -r{N}
    rev_match = re.search(r"-r(\d+)$", version_part)
    if rev_match:
        revision = int(rev_match.group(1))
        version_clean = version_part[:rev_match.start()]
    else:
        revision = 0
        version_clean = version_part

    # version_clean is the clean version (no "n" prefix expected in new format)
    version = version_clean
    ffmpeg_ref = version_clean
    clean_ver = version
    version_id = version_part

    # Arch is the first segment of triplet
    arch = triplet.split("-")[0]
    variant_key = f"{triplet}-{linkage}-{license_val}"
    major = major_version(version)

    return {
        "version": version,
        "revision": revision,
        "version_id": version_id,
        "clean_version": clean_ver,
        "ffmpeg_ref": ffmpeg_ref,
        "triplet": triplet,
        "linkage": linkage,
        "license": license_val,
        "arch": arch,
        "variant_key": variant_key,
        "major": major,
    }


def _parse_variant_id_legacy(body: str, variant_id: str) -> dict[str, Any]:
    """Parse a legacy-format variant_id (all ``-`` separators).

    Replicates the logic from ``db.py`` ``parse_variant_id``.
    """
    parts = body.split("-")
    if len(parts) < 6:
        raise ValueError(
            f"variant_id has too few segments after splitting: {variant_id!r}"
        )

    # Validate from the end: last = license, second-to-last = linkage
    license_val = parts[-1]
    linkage = parts[-2]
    if linkage not in VALID_LINKAGES:
        raise ValueError(
            f"Invalid linkage {linkage!r} in variant_id {variant_id!r} "
            f"(expected one of {VALID_LINKAGES})"
        )
    if license_val not in VALID_LICENSES:
        raise ValueError(
            f"Invalid license {license_val!r} in variant_id {variant_id!r} "
            f"(expected one of {VALID_LICENSES})"
        )

    # Find arch anchor in the remaining parts (before linkage)
    arch_index = None
    for i, p in enumerate(parts[:-2]):
        if p in ARCH_NAMES:
            arch_index = i
            break
    if arch_index is None:
        raise ValueError(
            f"variant_id missing arch segment (one of {ARCH_NAMES}): {variant_id!r}"
        )

    # triplet = from arch to linkage
    triplet = "-".join(parts[arch_index:-2])

    # version_part = "{ffmpeg_ref}-r{revision}" = everything before arch
    version_part = "-".join(parts[:arch_index])

    # Split version_part into ffmpeg_ref and revision
    m = re.match(r"^(.*)-r(\d+)$", version_part)
    if not m:
        raise ValueError(
            f"Cannot parse revision from version_part {version_part!r} "
            f"in variant_id {variant_id!r}"
        )
    ffmpeg_ref = m.group(1)
    revision = int(m.group(2))

    # Determine major from ffmpeg_ref (strip leading "n", take first dot segment)
    ref_stripped = ffmpeg_ref.lstrip("n")
    version = ref_stripped
    clean_ver = version
    major_ver = ref_stripped.split("-")[0].split(".")[0]
    major = f"{major_ver}.x"

    arch = parts[arch_index]
    variant_key = f"{triplet}-{linkage}-{license_val}"

    return {
        "version": version,
        "revision": revision,
        "version_id": version_part,
        "clean_version": clean_ver,
        "ffmpeg_ref": ffmpeg_ref,
        "triplet": triplet,
        "linkage": linkage,
        "license": license_val,
        "arch": arch,
        "variant_key": variant_key,
        "major": major,
    }


def parse_version_dir(dirname: str) -> dict[str, Any]:
    """Parse a version directory name into its components.

    Uses ``VERSION_DIR_RE`` which matches:

    * ``"8.1.1-r2"`` → ``{"version": "8.1.1", "revision": 2}``
    * ``"7.1-20260101"`` → ``{"version": "7.1-20260101", "revision": 0}``
    """
    m = VERSION_DIR_RE.match(dirname)
    if not m:
        raise ValueError(f"Cannot parse version directory name: {dirname!r}")
    version = m.group(1)
    revision = int(m.group(2)) if m.group(2) is not None else 0
    return {"version": version, "revision": revision}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", required=True, help="FFmpeg version (e.g. 8.1.1)")
    parser.add_argument("--revision", type=int, default=0, help="Build revision number")


def _add_variant_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--triplet", required=True, help="vcpkg triplet (e.g. x64-windows)")
    parser.add_argument("--linkage", required=True, choices=sorted(VALID_LINKAGES),
                        help="Library linkage")
    parser.add_argument("--license", required=True, choices=sorted(VALID_LICENSES),
                        help="License variant")


def _cli_var_version(args):
    import yaml
    with open(args.file) as f:
        data = yaml.safe_load(f)
    ver = data.get("version", "")
    if ver:
        print(ver)
    else:
        print("ERROR: missing 'version' field", file=sys.stderr)
        sys.exit(1)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Centralized naming for FFmpeg MSVC prebuilt CI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # variant-prefix
    p = sub.add_parser("variant-prefix", help="Build a variant download prefix")
    _add_common_args(p)

    # variant-id
    p = sub.add_parser("variant-id", help="Build a variant ID")
    _add_common_args(p)
    _add_variant_args(p)

    # release-tag
    p = sub.add_parser("release-tag", help="Build a release tag")
    _add_common_args(p)

    # data-path
    p = sub.add_parser("data-path", help="Build a data branch relative path")
    _add_common_args(p)
    _add_variant_args(p)

    # parse
    p = sub.add_parser("parse", help="Parse a variant ID into components")
    p.add_argument("--variant-id", required=True, help="Variant ID to parse")

    # major
    p = sub.add_parser("major", help="Extract major version (X.x)")
    p.add_argument("--version", required=True, help="FFmpeg version")

    # clean
    p = sub.add_parser("clean", help="Clean version string (+dev suffix removal)")
    p.add_argument("--version", required=True, help="Version string to clean")

    # version-dir
    p = sub.add_parser("version-dir", help="Build version directory name")
    _add_common_args(p)

    # zip-name
    p = sub.add_parser("zip-name", help="Build ZIP archive filename")
    p.add_argument("--variant-id", required=True, help="Variant ID")
    p.add_argument("--dev", action="store_true", help="Generate develop variant name")

    # var-version
    p = sub.add_parser("var-version", help="Read version from .var.yaml")
    p.add_argument("file", help="Path to .var.yaml file")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_cli()
    args = parser.parse_args(argv)

    if args.command == "variant-prefix":
        print(build_variant_prefix(version=args.version, revision=args.revision))

    elif args.command == "variant-id":
        result = build_variant_id(
            version=args.version,
            revision=args.revision,
            triplet=args.triplet,
            linkage=args.linkage,
            license=args.license,
        )
        print(result)

    elif args.command == "release-tag":
        result = build_release_tag(version=args.version, revision=args.revision)
        print(result)

    elif args.command == "data-path":
        result = build_data_path(
            version=args.version,
            revision=args.revision,
            triplet=args.triplet,
            linkage=args.linkage,
            license=args.license,
        )
        print(result)

    elif args.command == "parse":
        result = parse_variant_id(args.variant_id)
        print(json.dumps(result, indent=2))

    elif args.command == "major":
        print(major_version(args.version))

    elif args.command == "clean":
        print(clean_version(args.version))

    elif args.command == "version-dir":
        print(make_version_dir(version=args.version, revision=args.revision))

    elif args.command == "zip-name":
        print(build_zip_name(args.variant_id, dev=args.dev))

    elif args.command == "var-version":
        _cli_var_version(args)


if __name__ == "__main__":
    main()
