"""Read-only published state, independent of GitHub Actions or the runner."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .license_policy import POLICY_VERSION
from .identity import family_dir, variant_path, version_dir, public_version, date_suffix, archive_name
from .versions import ROOT


class PublishedState:
    def __init__(self, *, directory: Path | None = None):
        # Local data is the authoritative build database.  Network sync is
        # an explicit CI/user responsibility; never fetch from a read query.
        self.directory = directory if directory is not None else ROOT / "data"
        self._cache: dict[str, dict | None] = {}
        self._paths: set[str] | None = None

    def refresh(self) -> None:
        """Reload local DB after an external synchronization."""
        self._paths = None
        self._cache.clear()

    def paths(self) -> set[str]:
        if self._paths is not None:
            return self._paths
        self._paths = {
            p.relative_to(self.directory).as_posix()
            for p in self.directory.rglob("*.yaml") if p.is_file()
        } if self.directory.is_dir() else set()
        return self._paths

    def variant_exists(self, version: str, revision: int,
                       triplet: str, license_: str, linkage: str,
                       build_hash: str | None = None) -> bool:
        path = variant_path(version, revision, triplet, linkage, license_)
        if build_hash is None:
            return path in self.paths()
        # Hash-based dedup also handles a manually changed legacy revision.
        # All records are read from local data; no network call is performed.
        candidates = [path] if path in self.paths() else []
        candidates.extend(p for p in self.paths()
                          if p != path and "/variants/" in p and p.endswith(
                              f"/{triplet}-{linkage}-{license_}.yaml"))
        for candidate in candidates:
            if candidate in self._cache:
                record = self._cache[candidate]
            else:
                file = self.directory / candidate
                record = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
                self._cache[candidate] = record
            if candidate == path and record.get("build_hash") and record["build_hash"] != build_hash:
                raise ValueError(f"Build hash prefix collision or corrupt DB record: {path}")
            candidate_version = str(record.get("version") or "")
            if candidate_version and candidate_version.split("-h", 1)[0] != version.split("-h", 1)[0]:
                continue
            if record.get("build_hash") == build_hash and record.get("assets"):
                return True
        # Old records without a verified build hash must not be reused.
        return False

    def target_exists(self, version: str, revision: int, triplet: str,
                      feature_hash: str, build_hash: str, variant_hash: str) -> bool:
        """Strict dedup: never infer Feature identity from an old license label.

        Earlier schema records remain readable, but cannot establish that a
        new arbitrary vcpkg Feature selection has already been published.
        """
        if not all(re.fullmatch(r"[0-9a-f]{64}", h)
                   for h in (feature_hash, build_hash, variant_hash)):
            raise ValueError("Full build, feature and variant hashes are required")
        for relative in self.paths():
            if "/variants/" not in relative or not relative.endswith(".yaml"):
                continue
            if "-f" + feature_hash[:12] + ".yaml" not in relative:
                continue
            filename = relative.rsplit("/", 1)[-1]
            if not filename.startswith(triplet + "-"):
                continue
            record = self._cache.get(relative)
            if record is None:
                record = yaml.safe_load((self.directory / relative).read_text(encoding="utf-8")) or {}
                self._cache[relative] = record
            if str(record.get("version", "")).split("-h", 1)[0] != version.split("-h", 1)[0]:
                continue
            if (record.get("feature_hash") == feature_hash
                and record.get("build_hash") == build_hash
                and record.get("variant_hash") == variant_hash
                and record.get("assets")):
                return True
        return False

    def find_abi(self, version: str, triplet: str, abi_hash: str, *,
                 channel: str | None = None, source_commit: str | None = None) -> dict | None:
        """Find a dated, compliant published asset by full native ABI."""
        if not re.fullmatch(r"[0-9a-f]{64}", abi_hash):
            raise ValueError("Full native vcpkg ABI required")
        prefix = f"{family_dir(version)}/"
        found = []
        for relative in self.paths():
            if not (relative.startswith(prefix) and "/variants/" in relative
                    and relative.endswith(".yaml")):
                continue
            if not relative.split("/variants/", 1)[1].startswith(triplet + "-"):
                continue
            record = self._cache.get(relative)
            if record is None:
                record = yaml.safe_load((self.directory / relative).read_text(encoding="utf-8")) or {}
                self._cache[relative] = record
            if (str(record.get("version")) == version
                    and record.get("triplet") == triplet
                    and record.get("abi_hash") == abi_hash
                    and record.get("release_date") and record.get("compliance")
                    and int(record.get("package_format", 0)) >= 2
                    and record["compliance"].get("license_policy") == POLICY_VERSION
                    and record.get("assets", {}).get("binary")
                    and (channel is None or record.get("channel") == channel)
                    and (source_commit is None or record.get("source_commit") == source_commit)):
                # Reuse only distributions written by the dated packaging flow,
                # with the complete set of archives for that target.
                try:
                    date_suffix(record["release_date"])
                    date_suffix(record.get("publication_date", record["release_date"]))
                    kinds = {"binary", "develop"} if record["linkage"] == "shared" else {"binary"}
                    if set(record["assets"]) != kinds:
                        continue
                    if any(asset["file"] != archive_name(record, develop=kind == "develop")
                           or not re.fullmatch(r"sha256:[0-9a-f]{64}", asset["digest"])
                           or asset["size"] <= 0 for kind, asset in record["assets"].items()):
                        continue
                except (KeyError, TypeError, ValueError):
                    continue
                found.append(record)
        return max(found, key=lambda row: row.get("publication_date", row["release_date"]), default=None)

    def latest_release(self, job: dict) -> dict | None:
        """Find the latest complete dated batch for the public version/channel."""
        name = public_version(job)
        candidates = []
        for relative in self.paths():
            if not relative.endswith("/version.yaml"):
                continue
            parent = relative.split("/")[-2]
            if not re.fullmatch(re.escape(name) + r"-[0-9]{6}", parent):
                continue
            record = self._cache.get(relative)
            if record is None:
                record = yaml.safe_load((self.directory / relative).read_text(encoding="utf-8")) or {}
                self._cache[relative] = record
            if record.get("release_date") and record.get("complete"):
                if parent != name + "-" + date_suffix(record["release_date"]):
                    continue
                candidates.append(record)
        return max(candidates, key=lambda record: record["release_date"], default=None)

    def abi_exists(self, version: str, triplet: str, abi_hash: str) -> bool:
        return self.find_abi(version, triplet, abi_hash) is not None

    def revisions(self, version: str) -> list[int]:
        prefix = f"{family_dir(version)}/"
        base_name = version_dir(version)
        regex = re.compile(rf"^{re.escape(prefix + base_name)}(?:-r(\d+))?/variants/[^/]+\.yaml$")
        values = {int(m.group(1) or 0)
                  for path in self.paths() if (m := regex.fullmatch(path))}
        return sorted(values, reverse=True)

    def variant(self, version: str, revision: int,
                triplet: str, license_: str, linkage: str) -> dict | None:
        path = variant_path(version, revision, triplet, linkage, license_)
        if path in self._cache:
            return self._cache[path]
        if path not in self.paths():
            return None
        data = (self.directory / path).read_text(encoding="utf-8")
        self._cache[path] = yaml.safe_load(data) or {}
        return self._cache[path]
