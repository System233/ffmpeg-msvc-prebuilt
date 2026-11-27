"""One-time offline conversion of the historical YAML index.

Not used by publication, planning, retention or Pages.
Remove after the coordinated production cutover.
"""
from pathlib import Path
import argparse
import re
import yaml

from .catalog import SCHEMA, TAG, _date, _slot, _variant, shard_path, write_json, load_shard
from .identity import ASSET_KINDS, is_lts, release_order

def migration_plan(source: Path) -> tuple[dict, dict, list[Path]]:
    """Read both v1 copies; reject discrepancies instead of losing assets."""
    if not source.is_dir():
        raise FileNotFoundError("Legacy Data source does not exist")
    if (source / "index.json").exists():
        raise ValueError("Source is already a catalog or contains mixed index formats")
    shards = {}
    manifest_data = {"schema": SCHEMA, "releases": [], "master": []}
    consumed = []
    tags = set()
    for path in sorted(source.glob("*.x/*/version.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tag = data["release_tag"]
        if not TAG.fullmatch(tag) or tag in tags:
            raise ValueError("Duplicate/invalid legacy release tag")
        tags.add(tag)
        master = data.get("channel") == "master" or bool(re.search(r"-\d+-g[0-9a-f]+$", data.get("ffmpeg_ref", "")))
        when = data.get("release_date")
        if not when:
            when = str(data["created"])[:10]
        when = _date(str(when))
        kind, key = ("master", int(when[:4])) if master else ("releases", str(data["version"]))
        shard_path(source, kind, key)  # validate key
        release = {"tag": tag, "date": when, "variants": {}}
        if master:
            release["version"] = str(data["version"])
            if data.get("source_commit"):
                release["commit"] = data["source_commit"]
        if data.get("ffmpeg_ref") and master and not release.get("commit"):
            release["ref"] = data["ffmpeg_ref"]
        files = sorted((path.parent / "variants").glob("*.yaml"))
        actual = {}
        for file in files:
            v = yaml.safe_load(file.read_text(encoding="utf-8"))
            slot = _slot(v)
            if slot in actual:
                raise ValueError("Duplicate legacy variant slot")
            actual[slot] = v
        embedded = {}
        for v in data["variants"]:
            slot = _slot(v)
            if slot in embedded:
                raise ValueError("Duplicate embedded variant slot")
            embedded[slot] = v
        if set(actual) != set(embedded) or not actual:
            raise ValueError(f"Legacy variant sets differ: {tag}")
        for slot, v in actual.items():
            def project(row):
                native = bool(row.get("abi_hash"))
                if native and not (row.get("release_date") and row.get("package_format")):
                    raise ValueError("Legacy native record lacks dated archive identity")
                return _variant(row, when, native=native)
            value = project(v)
            if value != project(embedded[slot]):
                raise ValueError(f"Legacy asset copies differ: {tag}/{slot}")
            release["variants"][slot] = value
        identity = (kind, key)
        if identity not in shards:
            shards[identity] = {("version" if kind == "releases" else "year"): key,
                                "lts": kind == "releases" and is_lts(str(key)), "releases": []}
            manifest_data[kind].append(key)
        shards[identity]["releases"].append(release)
        consumed.extend([path, *files])
    if not consumed:
        raise ValueError("No legacy Release index records")
    if set(source.glob("*.x/*/variants/*.yaml")) != {p for p in consumed if p.parent.name == "variants"}:
        raise ValueError("Orphan legacy variant records")
    manifest_data["releases"].sort(key=lambda v: tuple(map(int, v.split("."))), reverse=True)
    manifest_data["master"].sort(reverse=True)
    for s in shards.values():
        s["releases"].sort(key=lambda r: release_order(r["date"], r["tag"]), reverse=True)
    return manifest_data, shards, consumed


def migrate(source: Path, destination: Path) -> tuple[int, int, int]:
    """Explicit migration; destination must be empty. Source is never modified."""
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Migration destination must be empty")
    if source.resolve() == destination.resolve():
        raise ValueError("Use a separate destination for migration")
    m, shards, _ = migration_plan(source)
    for (kind, key), shard in shards.items():
        write_json(shard_path(destination, kind, key), shard)
        load_shard(destination, kind, key)
    write_json(destination / "index.json", m)
    releases = [r for s in shards.values() for r in s["releases"]]
    variants = [v for r in releases for v in r["variants"].values()]
    return len(releases), len(variants), sum(k in v for v in variants for k in ASSET_KINDS)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    releases, variants, assets = migrate(args.source, args.output)
    print(f"Migrated {releases} releases, {variants} variants, {assets} assets")
