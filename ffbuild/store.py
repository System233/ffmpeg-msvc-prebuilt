"""Small local data-branch writer for immutable content-addressed variants."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .identity import is_lts, release_tag, variant_name, variant_path, version_dir
from .targets import load_targets


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_yaml(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".ffbuild-", suffix=".yaml", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            yaml.safe_dump(record, file, sort_keys=False, allow_unicode=True)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def register_variant(root: Path, record: dict) -> Path:
    """Verify canonical identity and update one release's variant index."""
    version = str(record["version"])
    revision = int(record.get("revision", 0))
    common = (version, revision, str(record["triplet"]),
              str(record["linkage"]), str(record["license"]))
    native = bool(record.get("abi_hash"))
    if native:
        abi = str(record["abi_hash"])
        if not re.fullmatch(r"[0-9a-f]{64}", abi):
            raise ValueError("The full native vcpkg ABI is required")
        expected_id = variant_name(*common, abi_hash=abi)
        path = root / variant_path(*common, abi_hash=abi)
    else:
        feature_hash = str(record["feature_hash"])
        expected_id = variant_name(*common, feature_hash)
        path = root / variant_path(*common, feature_hash)
    if record["variant_id"] != expected_id:
        raise ValueError(f"Inconsistent variant identity: {record['variant_id']} != {expected_id}")
    if not native and not re.fullmatch(r"[0-9a-f]{64}", str(record.get("variant_hash", ""))):
        raise ValueError("Missing canonical variant hash")
    if path.exists():
        previous = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        identity_fields = ("abi_hash",) if native else ("build_hash", "variant_hash")
        if any(previous.get(field) != record.get(field) for field in identity_fields):
            raise ValueError(f"Existing release identity has a different Build Hash: {path}")
        if previous.get("assets") == record.get("assets"):
            # Same content-addressed package already published: immutable.
            return path
        old_format = int(previous.get("package_format", 1))
        new_format = int(record.get("package_format", 1))
        if not native or new_format <= old_format:
            raise ValueError(f"Same ABI/build identity changed archives without "
                             f"a package-format revision: {path}")
        # New filenames preserve old GitHub Release assets. A strictly higher
        # package-format version may update the index after verified publication.
    if not native and not re.fullmatch(r"[0-9a-f]{64}", str(record.get("build_hash", ""))):
        raise ValueError("Cannot publish without full verified Build Hash")
    _atomic_yaml(path, record)
    variant_files = sorted(path.parent.glob("*.yaml"))
    variants = [yaml.safe_load(file.read_text(encoding="utf-8")) for file in variant_files]
    index = path.parent.parent / "version.yaml"
    old = yaml.safe_load(index.read_text(encoding="utf-8")) if index.is_file() else {}
    old = old or {}
    tag = release_tag(version, revision)
    github_repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = f"https://github.com/{github_repo}/releases/tag/{tag}" if github_repo else old.get("release_url")
    expected = int(record.get("expected_variants") or len(load_targets()))
    native_count = sum(1 for variant in variants if variant.get("abi_hash"))
    updated = {
        "version": version, "revision": revision, "lts": is_lts(version),
        "schema_version": 1, "ffmpeg_ref": record.get("ffmpeg_ref", ""),
        "release_tag": tag, "release_id": old.get("release_id"),
        "release_url": url, "created": old.get("created") or _utc_now(),
        "updated": _utc_now(), "variant_count": len(variants),
        "total_variants": expected,
        "complete": (native_count if native else len(variants)) >= expected,
        "variants": variants,
    }
    _atomic_yaml(index, updated)
    return path
