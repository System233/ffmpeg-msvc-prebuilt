"""Static Release catalog. One authoritative JSON shard per version/year."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


from .identity import archive_name, date_suffix, record_release_tag, variant_name, release_order, ASSET_KINDS, expected_asset_kinds, is_lts, PACKAGE_FORMAT_VERSION

SCHEMA = 1
LEGACY_LGPL_NOTE = "legacy-lgpl-licensing"
VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")
SLOT = re.compile(r"(x64|x86|arm|arm64)-windows-(static|shared)-(lgpl|gpl|nonfree)")
HASH = re.compile(r"[0-9a-f]{64}")
TAG = re.compile(r"ffmpeg-[A-Za-z0-9.+_-]+")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate catalog key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)


def write_json(path: Path, value: dict) -> None:
    # Keep one complete release per line for readable, small Git diffs.
    if "releases" in value and "schema" not in value:
        fields = [json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False)
                  for k, v in value.items() if k != "releases"]
        lines = ["  " + f + "," for f in fields]
        lines.append('  "releases": [')
        lines.extend("    " + json.dumps(r, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                     + ("," if i < len(value["releases"]) - 1 else "")
                     for i, r in enumerate(value["releases"]))
        lines.append("  ]")
        text = "{\n" + "\n".join(lines) + "\n}\n"
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".catalog-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        Path(tmp).replace(path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def manifest(root: Path) -> dict:
    path = root / "index.json"
    if not path.is_file():
        if any(root.glob("*.x/*/version.yaml")) or any(root.glob("*.x/*/variants/*.yaml")):
            raise ValueError("Unsupported catalog layout: expected index.json")
        if any(root.glob("releases/*.json")) or any(root.glob("master/*.json")):
            raise ValueError("Missing release catalog index.json with existing shards")
        return {"schema": SCHEMA, "releases": [], "master": []}
    result = read_json(path)
    if (set(result) != {"schema", "releases", "master"} or result["schema"] != SCHEMA
            or not isinstance(result["releases"], list) or not isinstance(result["master"], list)
            or any(not isinstance(v, str) or not VERSION.fullmatch(v) for v in result["releases"])
            or any(type(y) is not int or not 2000 <= y <= 2099 for y in result["master"])
            or len(set(result["releases"])) != len(result["releases"])
            or len(set(result["master"])) != len(result["master"])):
        raise ValueError("Invalid catalog manifest")
    return result


def require_manifest(root: Path) -> dict:
    """A production catalog must already exist; never interpret missing data as empty."""
    if not (root / "index.json").is_file():
        raise ValueError("Missing release catalog index.json")
    return manifest(root)


def validate_catalog(root: Path) -> dict:
    """Validate every indexed shard and globally unique release tag."""
    m = require_manifest(root)
    if any(root.glob("*.x/*/version.yaml")) or any(root.glob("*.x/*/variants/*.yaml")):
        raise ValueError("Unexpected legacy YAML alongside release catalog")
    tags = set()
    for kind in ("releases", "master"):
        for key in m[kind]:
            if not shard_path(root, kind, key).is_file():
                raise ValueError("Catalog manifest references missing shard")
            shard = load_shard(root, kind, key)
            if not shard["releases"]:
                raise ValueError("Empty indexed catalog shard")
            for r in shard["releases"]:
                if r["tag"] in tags:
                    raise ValueError("Duplicate catalog release tag")
                tags.add(r["tag"])
    return m


def shard_path(root: Path, kind: str, key: str | int) -> Path:
    if kind == "releases" and isinstance(key, str) and VERSION.fullmatch(key):
        return root / kind / f"{key}.json"
    if kind == "master" and type(key) is int and 2000 <= key <= 2099:
        return root / kind / f"{key}.json"
    raise ValueError("Invalid catalog shard")


def _date(value: str) -> str:
    date_suffix(value)
    return value


def _slot(record: dict) -> str:
    slot = "-".join(record[k] for k in ("triplet", "linkage", "license"))
    if not SLOT.fullmatch(slot):
        raise ValueError(f"Invalid release slot: {slot}")
    return slot


def _asset(value: dict) -> dict:
    name, size, digest = value["file"], value["size"], value["digest"]
    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.+\-]+\.zip", name)
            or type(size) is not int or size <= 0 or not isinstance(digest, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
        raise ValueError("Invalid catalog asset")
    return {"file": name, "size": size, "sha256": digest[7:]}


def _variant(record: dict, release_date: str, *, native: bool) -> dict:
    result = {}
    if native:
        abi = record["abi_hash"]
        if not isinstance(abi, str) or not HASH.fullmatch(abi):
            raise ValueError("Invalid catalog ABI")
        fmt = record["package_format"]
        if type(fmt) is not int or fmt != PACKAGE_FORMAT_VERSION:
            raise ValueError("Invalid catalog archive format")
        result.update(abi=abi, format=fmt)
        original = _date(record["release_date"])
        if original > release_date:
            raise ValueError("Asset date is later than its release")
        if original != release_date:
            result["date"] = original
    for kind, asset in record["assets"].items():
        if kind not in ASSET_KINDS:
            raise ValueError("Unexpected asset kind")
        result[kind] = _asset(asset)
    if "binary" not in result:
        raise ValueError("Missing binary asset")
    kinds = set(record["assets"])
    if native and kinds != expected_asset_kinds(record["linkage"], record["package_format"]):
        raise ValueError("Incomplete native asset set")
    if not native and ("debug" in kinds or (record["linkage"] == "static" and kinds != {"binary"})):
        raise ValueError("Invalid historical asset set")
    if not native and record["license"] == "lgpl":
        result["note"] = LEGACY_LGPL_NOTE
    return result


def release_from_records(records: list[dict], *, require_complete: bool = True) -> tuple[str, str | int, dict]:
    if not records:
        raise ValueError("Empty release")
    first = records[0]
    version = first["version"]
    when = _date(first.get("publication_date", first["release_date"]))
    tag = record_release_tag(first)
    channel = first["channel"]
    if channel not in ("release", "master") or not TAG.fullmatch(tag):
        raise ValueError("Invalid release identity")
    kind, key = ("master", int(when[:4])) if channel == "master" else ("releases", version)
    if kind == "releases" and not VERSION.fullmatch(version):
        raise ValueError("Invalid stable version")
    if require_complete and any(r.get("expected_variants") != len(records) for r in records):
        raise ValueError("Incomplete dated release matrix")
    release = {"tag": tag, "date": when, "variants": {}}
    if kind == "master":
        commit = first.get("source_commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Master requires full commit")
        release.update(version=version, commit=commit)
    for row in records:
        if (row["version"], row["channel"], row.get("source_commit"), record_release_tag(row)) != (
                version, channel, first.get("source_commit"), tag):
            raise ValueError("Mixed release identities")
        slot = _slot(row)
        if slot in release["variants"]:
            raise ValueError("Duplicate release slot")
        variant = _variant(row, when, native=True)
        for k in ASSET_KINDS:
            if k in variant and variant[k]["file"] != archive_name(row, kind=k):
                raise ValueError("Noncanonical dated archive")
        release["variants"][slot] = variant
    return kind, key, release


def load_shard(root: Path, kind: str, key: str | int) -> dict:
    path = shard_path(root, kind, key)
    identity = {"version": key} if kind == "releases" else {"year": key}
    if not path.is_file():
        return {**identity, "lts": kind == "releases" and is_lts(str(key)), "releases": []}
    result = read_json(path)
    required = {*identity, "releases", "lts"}
    if set(result) != required or any(result.get(k) != v for k, v in identity.items()):
        raise ValueError("Catalog shard identity differs")
    if type(result["lts"]) is not bool or (kind == "master" and result["lts"]):
        raise ValueError("Invalid catalog LTS classification")
    if not isinstance(result["releases"], list):
        raise ValueError("Invalid release list")
    tags = set()
    for r in result["releases"]:
        allowed = {"tag", "date", "variants"} | ({"version", "commit", "ref"} if kind == "master" else set())
        if set(r) - allowed or not TAG.fullmatch(r["tag"]) or r["tag"] in tags or not r["variants"]:
            raise ValueError("Invalid/duplicate catalog release")
        tags.add(r["tag"])
        _date(r["date"])
        if kind == "master" and int(r["date"][:4]) != key:
            raise ValueError("Master shard year differs")
        if kind == "master" and not r.get("version"):
            raise ValueError("Missing master version")
        if "commit" in r and not re.fullmatch(r"[0-9a-f]{40}", r["commit"]):
            raise ValueError("Invalid master commit")
        for slot, v in r["variants"].items():
            if not SLOT.fullmatch(slot) or set(v) - {"abi", "format", "date", "note", *ASSET_KINDS}:
                raise ValueError("Invalid catalog variant")
            if ("abi" in v) != ("format" in v) or ("abi" in v and (
                    not HASH.fullmatch(v["abi"]) or type(v["format"]) is not int or v["format"] != PACKAGE_FORMAT_VERSION)):
                raise ValueError("Invalid catalog ABI or format")
            if "abi" in v:
                expected_tag = "ffmpeg-" + ("master" if kind == "master" else key) + "-" + date_suffix(r["date"])
                if not re.fullmatch(re.escape(expected_tag) + r"(?:R(?:[2-9]|[1-9][0-9]))?", r["tag"]):
                    raise ValueError("Invalid native release tag")
                if kind == "master" and not re.fullmatch(r"[0-9a-f]{40}", r.get("commit", "")):
                    raise ValueError("Native master requires full commit")
            if "date" in v and ("abi" not in v or _date(v["date"]) > r["date"]):
                raise ValueError("Invalid original asset date")
            if "note" in v and (v["note"] != LEGACY_LGPL_NOTE or "abi" in v or not slot.endswith("-lgpl")):
                raise ValueError("Invalid historical LGPL notice")
            if "binary" not in v:
                raise ValueError("Missing binary asset")
            kinds = set(v).intersection(ASSET_KINDS)
            linkage = slot.split("-")[2]
            if "debug" in kinds and "abi" not in v:
                raise ValueError("Debug add-on requires native package metadata")
            if "abi" in v and kinds != expected_asset_kinds(linkage, v["format"]):
                raise ValueError("Incomplete native asset set")
            if linkage == "static" and kinds != {"binary"}:
                raise ValueError("Static variant has unexpected add-on")
            for asset in (v[k] for k in ASSET_KINDS if k in v):
                if set(asset) != {"file", "size", "sha256"}:
                    raise ValueError("Invalid catalog asset fields")
                _asset({"file": asset["file"], "size": asset["size"], "digest": "sha256:" + asset["sha256"]})
    return result


def expanded(kind: str, key: str | int, release: dict) -> list[dict]:
    """Reconstruct only the identity required by the CI native-ABI path."""
    result = []
    version = release["version"] if kind == "master" else key
    for slot, v in release["variants"].items():
        arch, _, linkage, license_ = slot.split("-")
        triplet = arch + "-windows"
        assets = {k: {"file": a["file"], "size": a["size"], "digest": "sha256:" + a["sha256"]}
                  for k in ASSET_KINDS if (a := v.get(k))}
        row = {"version": version, "triplet": triplet, "arch": arch, "linkage": linkage,
               "license": license_, "channel": "master" if kind == "master" else "release",
               "release_date": v.get("date", release["date"]), "assets": assets,
               "publication_date": release["date"]}
        expected_tag = "ffmpeg-" + ("master" if kind == "master" else key) + "-" + date_suffix(release["date"])
        if "abi" in v and release["tag"] != expected_tag:
            row["publication_tag"] = release["tag"]
        if "commit" in release:
            row["source_commit"] = release["commit"]
        if "abi" in v:
            row.update(abi_hash=v["abi"], package_format=v["format"], port="ffmpeg",
                       variant_id=variant_name(version, 0, triplet, linkage, license_, abi_hash=v["abi"]))
        result.append(row)
    return result


def preflight(root: Path, records: list[dict], *, require_complete: bool = True):
    m = manifest(root)
    if any(root.glob("*.x/*/version.yaml")) or any(root.glob("*.x/*/variants/*.yaml")):
        raise ValueError("Unexpected legacy YAML alongside release catalog")
    kind, key, release = release_from_records(records, require_complete=require_complete)
    path = shard_path(root, kind, key)
    if key in m[kind] and not path.is_file():
        raise ValueError("Catalog manifest references missing shard")
    shard = load_shard(root, kind, key)
    old = next((r for r in shard["releases"] if r["tag"] == release["tag"]), None)
    if old is not None and old != release:
        raise ValueError(f"Dated release already contains a different build: {release['tag']}")
    return m, kind, key, shard, release, old


def register_release(root: Path, records: list[dict]) -> Path:
    m, kind, key, shard, release, old = preflight(root, records)
    if old is None:
        shard["releases"].append(release)
        shard["releases"].sort(key=lambda r: release_order(r["date"], r["tag"]), reverse=True)
    path = shard_path(root, kind, key)
    write_json(path, shard)
    if key not in m[kind]:
        m[kind].append(key)
        m[kind].sort(key=(lambda v: tuple(map(int, v.split(".")))) if kind == "releases" else None, reverse=True)
    write_json(root / "index.json", m)
    return path


def refresh_lts(root: Path) -> int:
    """Refresh explicit LTS classifications. Validate all shards before writing."""
    m = manifest(root)
    changes = []
    for kind in ("releases", "master"):
        for key in m[kind]:
            path = shard_path(root, kind, key)
            if not path.is_file():
                raise ValueError("Catalog manifest references missing shard")
            shard = load_shard(root, kind, key)
            lts = kind == "releases" and is_lts(str(key))
            if shard.get("lts") is not lts:
                shard["lts"] = lts
                changes.append((path, shard))
    for path, shard in changes:
        write_json(path, shard)
    return len(changes)


def stage_index(root: Path) -> None:
    """Stage only index paths, including tracked deletions and first publication."""
    if not (root / "index.json").is_file():
        raise ValueError("Missing release catalog index.json")
    manifest(root)
    pattern = re.compile(r"(?:index\.json|releases/\d+\.\d+(?:\.\d+)?\.json|master/\d{4}\.json)")
    def git_paths(*args):
        return subprocess.check_output(["git", *args], cwd=root).decode("utf-8").split("\0")
    if any(not pattern.fullmatch(p) for p in git_paths("diff", "--cached", "--name-only", "-z") if p):
        raise ValueError("Unrelated files already staged in Data")
    paths = sorted({p for p in git_paths("ls-files", "-z", "--cached", "--others", "--exclude-standard")
                    if pattern.fullmatch(p)})
    if paths:
        # stdin pathspecs avoid Windows command-line limits on long histories.
        subprocess.run(["git", "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul"],
                       cwd=root, input="\0".join(paths).encode("utf-8") + b"\0", check=True)
