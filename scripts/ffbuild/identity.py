"""Release identity contract shared by the local data index and artifact writer."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone


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
                 linkage: str, license_: str, *, abi_hash: str | None = None) -> str:
    if linkage not in ("static", "shared") or license_ not in ("lgpl", "gpl", "nonfree"):
        raise ValueError("Invalid variant linkage or license")
    if triplet not in ("x64-windows", "x86-windows", "arm-windows", "arm64-windows"):
        raise ValueError(f"Unknown triplet: {triplet}")
    suffix = ""
    if abi_hash is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", abi_hash):
            raise ValueError("Invalid native ABI")
        suffix = "-a" + abi_hash[:12]
    return f"ffmpeg-{version_dir(version, revision)}_{triplet}-{linkage}-{license_}{suffix}"


def release_tag(version: str, revision: int = 0) -> str:
    return "ffmpeg-" + version_dir(version, revision)


def is_lts(version: str) -> bool:
    """LTS releases: 4.4 and odd-minor .1 families; snapshots are never LTS."""
    clean = re.sub(r"-h[0-9a-f]{12,64}$", "", normalize_version(version))
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", clean):
        return False
    major, minor = map(int, clean.split(".")[:2])
    return (major, minor) == (4, 4) or minor == 1

def utc_release_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def date_suffix(value: str) -> str:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value or not 2000 <= parsed.year <= 2099:
        raise ValueError("Release date must be an ISO date in 2000-2099")
    return parsed.strftime("%y%m%d")


def public_version(record: dict) -> str:
    return "master" if record.get("yaml") == "master" or record.get("channel") == "master" else normalize_version(str(record["version"]))


ASSET_KINDS = ("binary", "develop", "debug")
DIFFERENTIAL_FORMAT = 4


def expected_asset_kinds(linkage: str, package_format: int) -> set[str]:
    if linkage == "static":
        return {"binary"}
    if linkage != "shared":
        raise ValueError("Invalid asset linkage")
    return {"binary", "debug" if package_format >= DIFFERENTIAL_FORMAT else "develop"}


def archive_name(record: dict, *, kind: str = "binary") -> str:
    version = public_version(record)
    # Reuse canonical validation of target dimensions, never its hash suffix.
    stem = variant_name("1.0" if version == "master" else version, 0,
                        record["triplet"], record["linkage"], record["license"])
    if version == "master":
        stem = stem.replace("ffmpeg-1.0_", "ffmpeg-master_", 1)
    if kind not in ASSET_KINDS or (kind != "binary" and record["linkage"] != "shared"):
        raise ValueError("Invalid archive asset kind for linkage")
    suffix = "" if kind == "binary" else "-" + kind
    return f"{stem}{suffix}-{date_suffix(record['release_date'])}.zip"


def record_release_tag(record: dict) -> str:
    if record.get("release_date"):
        canonical = f"ffmpeg-{public_version(record)}-{date_suffix(record.get('publication_date', record['release_date']))}"
        actual = record.get("publication_tag", canonical)
        if not re.fullmatch(re.escape(canonical) + r"(?:R(?:[2-9]|[1-9][0-9]))?", actual):
            raise ValueError("Release tag differs from its version/date")
        return actual
    return release_tag(str(record["version"]), int(record.get("revision", 0)))


def dated_variant_path(record: dict) -> str:
    tag = record_release_tag(record)
    # Keep the existing family/version/variants layout for historical readers.
    return (f"{family_dir(str(record['version']))}/{tag.removeprefix('ffmpeg-')}/variants/"
            f"{record['triplet']}-{record['linkage']}-{record['license']}.yaml")


def audit_name(record: dict) -> str:
    identifier = record["variant_id"]
    if not re.fullmatch(r"ffmpeg-[A-Za-z0-9._+-]+", identifier):
        raise ValueError("Invalid audit variant identity")
    return identifier + ".audit.zip"


def release_order(day: str, tag: str) -> tuple[str, int, str]:
    """Chronological batch order, including numeric same-day revisions."""
    date_suffix(day)
    match = re.search(r"(?:R|-r)([1-9][0-9]*)$", tag)
    return day, int(match[1]) if match else 1, tag
