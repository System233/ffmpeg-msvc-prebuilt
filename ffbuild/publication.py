"""Publish verified release assets, then record them in the local data checkout."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import yaml

from .fingerprint import variant_fingerprint
from .identity import release_tag
from .store import register_variant


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=cwd, check=True, text=True)


def _release_api(tag: str) -> dict | None:
    """Fetch the authoritative REST release, distinguishing 404 from failures."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or repo.count("/") != 1:
        raise ValueError("GITHUB_REPOSITORY is required for verified publication")
    response = subprocess.run(
        ["gh", "api", f"repos/{repo}/releases/tags/{tag}"],
        capture_output=True, text=True,
    )
    if response.returncode:
        if "HTTP 404" in response.stderr:
            return None
        raise RuntimeError(f"Could not inspect GitHub Release {tag}: {response.stderr[-800:]}")
    parsed = json.loads(response.stdout)
    if not isinstance(parsed, dict) or type(parsed.get("id")) is not int:
        raise ValueError("Invalid GitHub Release response")
    return parsed


def _release_asset_list(release_id: int) -> dict[str, dict]:
    repo = os.environ["GITHUB_REPOSITORY"]
    indexed: dict[str, dict] = {}
    for page in range(1, 101):
        response = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases/{release_id}/assets"
             f"?per_page=100&page={page}"],
            capture_output=True, text=True, check=True,
        )
        batch = json.loads(response.stdout)
        if not isinstance(batch, list):
            raise ValueError("Malformed GitHub Release asset list")
        for asset in batch:
            if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
                raise ValueError("Malformed GitHub Release asset")
            name = asset["name"]
            if name in indexed:
                raise ValueError(f"Duplicate remote asset name: {name}")
            indexed[name] = asset
        if len(batch) < 100:
            return indexed
    raise ValueError("GitHub Release asset pagination limit exceeded")


def _confirm_asset(tag: str, file: Path, existing: dict) -> None:
    """Never trust an existing same-name release archive without equality."""
    if file.stat().st_size != existing.get("size"):
        raise ValueError(f"Immutable Release asset has different size: {file.name}")
    digest = existing.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        # Old GitHub assets may have no digest. Download only for this fallback.
        with tempfile.TemporaryDirectory(prefix="ffbuild-release-verify-") as scratch:
            _run("gh", "release", "download", tag, "--repo",
                 os.environ["GITHUB_REPOSITORY"], "--pattern", file.name,
                 "--dir", scratch)
            fetched = Path(scratch) / file.name
            if not fetched.is_file():
                raise ValueError("Release download omitted existing archive")
            digest = "sha256:" + _digest(fetched)
    if digest != "sha256:" + _digest(file):
        raise ValueError(f"Immutable Release asset content differs: {file.name}")


def _release_assets(tag: str, files: list[Path], *, upstream_version: str,
                    snapshot: bool = False) -> None:
    """Idempotent incremental publication with remote content verification."""
    flags = ["--prerelease", "--latest=false"] if snapshot else []
    if len({path.name for path in files}) != len(files):
        raise ValueError("Duplicate local asset filename")
    for file in files:
        if not file.is_file() or file.name in {".", ".."} or "/" in file.name or "\\" in file.name:
            raise ValueError("Invalid Release asset")
    release = _release_api(tag)
    if release is None:
        # A partly successful upload must not make the next attempt fail 422.
        _run("gh", "release", "create", tag,
             "--title", f"FFmpeg {upstream_version} (MSVC Prebuilt)",
             "--notes", f"MSVC/vcpkg build of FFmpeg {upstream_version}.", *flags)
        release = _release_api(tag)
        if release is None:
            raise RuntimeError("Created GitHub Release could not be verified")
    existing = _release_asset_list(release["id"])
    for file in files:
        if file.name in existing:
            _confirm_asset(tag, file, existing[file.name])
        else:
            _run("gh", "release", "upload", tag, str(file))
    if snapshot:
        _run("gh", "release", "edit", tag, *flags)


def _push_data(checkout: Path) -> None:
    _run("git", "add", "-A", cwd=checkout)
    has_staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=checkout)
    if has_staged.returncode == 0:
        return
    if has_staged.returncode != 1:
        raise RuntimeError("Could not inspect staged data branch changes")
    _run("git", "commit", "-m", "ffbuild: index content-addressed releases", cwd=checkout)
    for attempt in range(3):
        try:
            _run("git", "pull", "--rebase", "origin", "data", cwd=checkout)
            _run("git", "push", "origin", "HEAD:data", cwd=checkout)
            return
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _verify_v2_compliance_archive(path: Path, record: dict) -> None:
    """Require the actual uploaded ZIP to carry the declared license evidence."""
    summary = record["compliance"]
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for name in ("LICENSE.txt", "THIRD_PARTY_NOTICES.md",
                     "SBOM.spdx.json", "BUILD_PROVENANCE.json"):
            if name not in names:
                raise ValueError(f"Package-format v2 archive lacks {name}: {path.name}")
        if not any(name.startswith("LICENSES/") and name.endswith("/copyright")
                   for name in names):
            raise ValueError(f"Package-format v2 archive has no per-Port notices: {path.name}")
        for name, field in (("SBOM.spdx.json", "spdx_sha256"),
                            ("THIRD_PARTY_NOTICES.md", "notices_sha256")):
            if hashlib.sha256(archive.read(name)).hexdigest() != summary.get(field):
                raise ValueError(f"Compliance metadata hash differs for {name}: {path.name}")
        try:
            document = json.loads(archive.read("SBOM.spdx.json"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Unparseable compliance SPDX in {path.name}") from exc
        if len(document.get("packages", [])) != summary.get("package_count"):
            raise ValueError(f"Compliance package count differs in {path.name}")


def publish(*, artifacts_dir: Path, data_dir: Path,
            expected_plan: Path | None = None, dry_run: bool = False) -> list[str]:
    artifacts_dir = artifacts_dir.resolve()
    records = {}
    for metadata in sorted(artifacts_dir.glob("*.var.yaml")):
        record = yaml.safe_load(metadata.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or not record.get("variant_id"):
            raise ValueError(f"Invalid FFmpeg variant: {metadata}")
        if record.get("license") == "nonfree":
            raise ValueError("Nonfree FFmpeg artifacts must never be redistributed")
        if record.get("abi_hash"):
            abi = record["abi_hash"]
            if (not isinstance(abi, str) or len(abi) != 64
                    or any(c not in "0123456789abcdef" for c in abi)):
                raise ValueError(f"Invalid native vcpkg ABI: {metadata}")
        if record.get("feature_hash") and variant_fingerprint(
                record["build_hash"], record["triplet"], record["feature_hash"]) != record.get("variant_hash"):
            raise ValueError(f"Invalid vcpkg Feature/variant identity: {metadata}")
        if record["variant_id"] in records:
            raise ValueError(f"Duplicate FFmpeg variant: {record['variant_id']}")
        for asset in record.get("assets", {}).values():
            path = artifacts_dir / asset["file"]
            if not path.is_file():
                raise FileNotFoundError(f"Missing release archive: {path}")
            if asset.get("size") and path.stat().st_size != asset["size"]:
                raise ValueError(f"Archive size mismatch: {path}")
            if asset.get("digest") and asset["digest"] != "sha256:" + _digest(path):
                raise ValueError(f"Archive digest mismatch: {path}")
        if int(record.get("package_format", 1)) >= 2:
            if "compliance" not in record["assets"] or not record.get("compliance"):
                raise ValueError(f"Package-format v2 missing compliance asset: {metadata}")
            checksums = record.get("checksums")
            if not isinstance(checksums, dict) or not checksums.get("file"):
                raise ValueError(f"Package-format v2 missing checksum manifest: {metadata}")
            manifest = artifacts_dir / checksums["file"]
            if not manifest.is_file() or (
                checksums.get("size") != manifest.stat().st_size
                or checksums.get("digest") != "sha256:" + _digest(manifest)
            ):
                raise ValueError(f"Invalid package-format v2 checksum manifest: {metadata}")
            expected = "".join(
                f"{asset['digest'].removeprefix('sha256:')}  {asset['file']}\n"
                for asset in record["assets"].values()
            )
            if manifest.read_text(encoding="ascii") != expected:
                raise ValueError(f"Checksum manifest disagrees with release assets: {metadata}")
            sbom_asset = record.get("sbom")
            if not isinstance(sbom_asset, dict) or not sbom_asset.get("file"):
                raise ValueError(f"Package-format v2 missing public SPDX document: {metadata}")
            sbom_file = artifacts_dir / sbom_asset["file"]
            if (not sbom_file.is_file() or sbom_asset.get("size") != sbom_file.stat().st_size
                    or sbom_asset.get("digest") != "sha256:" + _digest(sbom_file)
                    or _digest(sbom_file) != record["compliance"].get("spdx_sha256")):
                raise ValueError(f"Public SPDX document does not match packaged evidence: {metadata}")
            for kind in ("binary", "develop", "compliance"):
                if kind in record["assets"]:
                    _verify_v2_compliance_archive(
                        artifacts_dir / record["assets"][kind]["file"], record)
        records[record["variant_id"]] = record

    if expected_plan is not None:
        planned = json.loads(expected_plan.read_text(encoding="utf-8"))["jobs"]
        missing = {job["id"] for job in planned} - records.keys()
        if missing:
            raise RuntimeError(f"Missing planned variants: {sorted(missing)}" if records
                               else "Missing all planned build artifacts")
        for job in planned:
            for field in ("version", "build_hash", "variant_hash", "abi_hash", "port"):
                if job.get(field) and job[field] != records[job["id"]].get(field):
                    raise ValueError(f"Build Plan and artifact disagree on {field}: {job['id']}")
            record = records[job["id"]]
            for field in ("triplet", "feature_hash", "features", "license", "linkage"):
                if field in job and job[field] != record.get(field):
                    raise ValueError(f"Build Plan and artifact disagree on {field}: {job['id']}")
            if job.get("package") and job["package"] != record.get("package_spec"):
                raise ValueError(f"Build Plan and artifact disagree on package spec: {job['id']}")

    groups: dict[str, list[dict]] = {}
    for record in records.values():
        tag = release_tag(str(record["version"]), int(record.get("revision", 0)))
        groups.setdefault(tag, []).append(record)
    if dry_run or not groups:
        return sorted(groups)

    if not (data_dir / ".git").exists():
        raise FileNotFoundError("An authenticated local data branch checkout is required")
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise RuntimeError("GitHub token is required for release publication")

    # Never record success before GitHub accepted the release assets.
    for tag, group in sorted(groups.items()):
        paths = {artifacts_dir / asset["file"]
                 for record in group for asset in record.get("assets", {}).values()}
        for record in group:
            if int(record.get("package_format", 1)) >= 2:
                paths.add(artifacts_dir / record["checksums"]["file"])
                paths.add(artifacts_dir / record["sbom"]["file"])
                paths.add(artifacts_dir / f"{record['variant_id']}.var.yaml")
        first = group[0]
        _release_assets(tag, sorted(paths), upstream_version=first["version"],
                        snapshot="-g" in str(first.get("ffmpeg_ref", "")))
    for record in records.values():
        if repository := os.environ.get("GITHUB_REPOSITORY"):
            binary = record["assets"]["binary"]["file"]
            tag = release_tag(str(record["version"]), int(record.get("revision", 0)))
            record["download_url"] = f"https://github.com/{repository}/releases/download/{tag}/{binary}"
        register_variant(data_dir, record)
    _push_data(data_dir)
    return sorted(groups)
