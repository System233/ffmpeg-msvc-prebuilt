"""Existing release publication, orchestrated from Python without schema changes."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

import yaml

from scripts.ops.naming import build_release_tag
from .versions import ROOT


def _legacy_modules():
    # The legacy db.py uses imports relative to its script directory.
    ops = str(ROOT / "scripts" / "ops")
    if ops not in sys.path:
        sys.path.insert(0, ops)
    from scripts.ops import db
    from scripts.ci import manage_release, push_data_branch
    return db, manage_release, push_data_branch


def publish(*, artifacts_dir: Path, data_dir: Path,
            expected_plan: Path | None = None, dry_run: bool = False) -> list[str]:
    artifacts_dir = artifacts_dir.resolve()
    metadata_files = sorted(artifacts_dir.glob("*.var.yaml"))
    if not metadata_files:
        if expected_plan and json.loads(expected_plan.read_text(encoding="utf-8"))["jobs"]:
            raise RuntimeError("Missing all planned build artifacts")
        return []

    groups: dict[str, list[dict]] = {}
    for file in metadata_files:
        entry = yaml.safe_load(file.read_text(encoding="utf-8"))
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid variant metadata: {file}")
        if not entry.get("variant_id"):
            raise ValueError(f"Missing variant_id: {file}")
        for asset in entry.get("assets", {}).values():
            if not (artifacts_dir / asset["file"]).is_file():
                raise FileNotFoundError(f"Missing archive: {asset['file']}")
        tag = build_release_tag(version=str(entry["version"]), revision=int(entry["revision"]))
        groups.setdefault(tag, []).append(entry)

    if expected_plan:
        plan = json.loads(expected_plan.read_text(encoding="utf-8"))
        expected_ids = {j["id"] for j in plan["jobs"]}
        found_ids = {entry["variant_id"] for group in groups.values() for entry in group}
        if not expected_ids.issubset(found_ids):
            raise RuntimeError(f"Missing planned variants: {sorted(expected_ids - found_ids)}")

    if dry_run:
        return sorted(groups)

    if not data_dir.is_dir() or not (data_dir / ".git").exists():
        raise FileNotFoundError("An authenticated data branch checkout is required to publish")
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise RuntimeError("GitHub release token is required to publish")

    db, manage_release, push_data_branch = _legacy_modules()
    # Preserve existing schema, revision, and URL conventions.
    db.DATA_DIR = data_dir.resolve()
    for file in metadata_files:
        db.cmd_import(Namespace(var_yaml_path=str(file)))
    push_data_branch.git_add_all(str(data_dir))
    if push_data_branch.has_staged_changes(str(data_dir)):
        push_data_branch.git_commit(str(data_dir), "ffbuild: publish compiled variants")
        push_data_branch.git_push(str(data_dir), "data", max_retries=3, delay=5)

    for tag, entries in sorted(groups.items()):
        # One invocation can build multiple FFmpeg versions. Never upload
        # archives for other versions to the current release tag.
        with tempfile.TemporaryDirectory(prefix="ffbuild-release-") as temp:
            release_assets = Path(temp)
            for entry in entries:
                for asset in entry.get("assets", {}).values():
                    source = artifacts_dir / asset["file"]
                    target = release_assets / source.name
                    if not target.exists():
                        shutil.copyfile(source, target)
            first = entries[0]
            ffmpeg_ref = str(first.get("ffmpeg_ref") or "")
            is_snapshot = "-g" in ffmpeg_ref
            manage_release.create_or_upload(
                tag=tag, artifacts_dir=release_assets,
                ref=ffmpeg_ref if is_snapshot else None,
                yaml_val=str(first["version"]),
            )
    return sorted(groups)
