"""Read-only published state, independent of GitHub Actions or the runner."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

from scripts.ops.naming import build_data_path, major_version, make_version_dir
from .versions import ROOT


class PublishedState:
    def __init__(self, *, directory: Path | None = None, git_ref: str = "origin/data"):
        self.directory = directory
        self.git_ref = git_ref
        self._cache: dict[str, dict | None] = {}
        self._paths: set[str] | None = None

    def refresh(self) -> None:
        """Fetch is performed at most once by the caller, not per variant."""
        if self.directory is not None:
            return
        result = subprocess.run(["git", "fetch", "origin", "data"],
                                cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Unable to fetch published state: {result.stderr.strip()}")
        self._paths = None

    def paths(self) -> set[str]:
        if self._paths is not None:
            return self._paths
        if self.directory:
            self._paths = {
                p.relative_to(self.directory).as_posix()
                for p in self.directory.rglob("*.yaml") if p.is_file()
            } if self.directory.is_dir() else set()
        else:
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", self.git_ref],
                cwd=ROOT, capture_output=True, text=True,
            )
            if result.returncode:
                raise RuntimeError(f"Could not read {self.git_ref}: {result.stderr.strip()}")
            self._paths = set(result.stdout.splitlines())
        return self._paths

    def variant_exists(self, version: str, revision: int,
                       triplet: str, license_: str, linkage: str) -> bool:
        return build_data_path(
            version=version, revision=revision, triplet=triplet,
            license=license_, linkage=linkage,
        ) in self.paths()

    def revisions(self, version: str) -> list[int]:
        prefix = f"{major_version(version)}/"
        base_name = make_version_dir(version=version)
        regex = re.compile(rf"^{re.escape(prefix + base_name)}(?:-r(\d+))?/variants/[^/]+\.yaml$")
        values = {int(m.group(1) or 0)
                  for path in self.paths() if (m := regex.fullmatch(path))}
        return sorted(values, reverse=True)

    def variant(self, version: str, revision: int,
                triplet: str, license_: str, linkage: str) -> dict | None:
        path = build_data_path(
            version=version, revision=revision,
            triplet=triplet, license=license_, linkage=linkage,
        )
        if path in self._cache:
            return self._cache[path]
        if path not in self.paths():
            return None
        if self.directory:
            data = (self.directory / path).read_text(encoding="utf-8")
        else:
            proc = subprocess.run(
                ["git", "show", f"{self.git_ref}:{path}"],
                cwd=ROOT, capture_output=True, text=True,
            )
            if proc.returncode:
                raise RuntimeError(f"Could not read published variant {path}")
            data = proc.stdout
        self._cache[path] = yaml.safe_load(data) or {}
        return self._cache[path]
