"""Read-only published state, independent of GitHub Actions or the runner."""

from __future__ import annotations

import re
from pathlib import Path


from .compliance import PACKAGE_FORMAT_VERSION
from . import catalog
from .identity import record_release_tag, release_order, public_version, archive_name, expected_asset_kinds
from .versions import ROOT


class PublishedState:
    def __init__(self, *, directory: Path | None = None):
        # Local data is the authoritative build database.  Network sync is
        # an explicit CI/user responsibility; never fetch from a read query.
        self.directory = directory if directory is not None else ROOT / "data"
        self._catalog = None
        self._shards = {}
        self._abi = {}
        self._latest = {}

    def refresh(self) -> None:
        """Reload local DB after an external synchronization."""
        self._catalog = None
        self._shards.clear()
        self._abi.clear()
        self._latest.clear()

    def _catalog_shards(self, name: str):
        if self._catalog is None:
            self._catalog = catalog.manifest(self.directory)
        keys = self._catalog["master"] if name == "master" else ([name] if name in self._catalog["releases"] else [])
        kind = "master" if name == "master" else "releases"
        for key in keys:
            identity = (kind, key)
            if identity not in self._shards:
                if not catalog.shard_path(self.directory, kind, key).is_file():
                    raise ValueError("Catalog manifest references missing shard")
                self._shards[identity] = catalog.load_shard(self.directory, kind, key)
            yield kind, key, self._shards[identity]

    def _catalog_lookup(self, name: str):
        if name in self._abi:
            return
        lookup = {}
        latest = None
        for kind, key, shard in self._catalog_shards(name):
            for release in shard["releases"]:
                rows = catalog.expanded(kind, key, release)
                if not rows or any(not row.get("abi_hash") for row in rows):
                    continue
                if latest is None or release_order(release["date"], release["tag"]) > release_order(latest["release_date"], record_release_tag(latest["variants"][0])):
                    latest = {"release_date": release["date"], "variants": rows}
                for row in rows:
                    if row.get("package_format") != PACKAGE_FORMAT_VERSION:
                        continue
                    try:
                        kinds = expected_asset_kinds(row["linkage"], PACKAGE_FORMAT_VERSION)
                        if set(row["assets"]) != kinds or any(
                            asset["file"] != archive_name(row, kind=k)
                            for k, asset in row["assets"].items()):
                            continue
                    except (KeyError, ValueError):
                        continue
                    identity = (row["version"], row["triplet"], row["abi_hash"], row.get("source_commit"))
                    old = lookup.get(identity)
                    if old is not None and (old["linkage"], old["license"]) != (row["linkage"], row["license"]):
                        raise ValueError("One native ABI maps to different public slots")
                    if old is None or release_order(row["publication_date"], record_release_tag(row)) > release_order(old["publication_date"], record_release_tag(old)):
                        lookup[identity] = row
        self._abi[name] = lookup
        self._latest[name] = latest

    def find_abi(self, version: str, triplet: str, abi_hash: str, *,
                 channel: str | None = None, source_commit: str | None = None) -> dict | None:
        """Find an indexed, current-format published asset by full native ABI."""
        if not re.fullmatch(r"[0-9a-f]{64}", abi_hash):
            raise ValueError("Full native vcpkg ABI required")
        name = "master" if channel == "master" else version
        self._catalog_lookup(name)
        return self._abi[name].get((version, triplet, abi_hash, source_commit))

    def latest_release(self, job: dict) -> dict | None:
        """Find the latest complete dated batch for the public version/channel."""
        name = public_version(job)
        self._catalog_lookup(name)
        return self._latest[name]

    def abi_exists(self, version: str, triplet: str, abi_hash: str) -> bool:
        return self.find_abi(version, triplet, abi_hash) is not None
