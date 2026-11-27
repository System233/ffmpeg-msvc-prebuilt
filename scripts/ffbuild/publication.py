"""Publish verified release assets, then record them in the local data checkout."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

import yaml

from .identity import record_release_tag, archive_name, variant_name, date_suffix, audit_name, expected_asset_kinds
from .store import release_index
from .symbols import verify_symbols, verify_debug_layout
from . import catalog
from .license_policy import POLICY_VERSION, scoped_compatibility
from .compliance import _ffmpeg_license, resolve_port_license, dependency_scopes, declared_root_hosts, manifest_host_edges, verify_system_archive_members, distribution_evidence, PUBLIC_COPYRIGHT, PUBLIC_SPDX, PACKAGE_FORMAT_VERSION


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
            # Authenticated release listing also includes unpublished drafts.
            listed = subprocess.run(
                ["gh", "api", "--paginate", "--slurp",
                 f"repos/{repo}/releases?per_page=100"],
                capture_output=True, text=True, check=True,
            )
            pages = json.loads(listed.stdout)
            if not isinstance(pages, list) or not all(isinstance(page, list) for page in pages):
                raise ValueError("Invalid GitHub Release listing")
            matches = [release for page in pages for release in page
                       if release.get("tag_name") == tag]
            if len(matches) > 1 or any(type(release.get("id")) is not int for release in matches):
                raise ValueError(f"Ambiguous or invalid GitHub Release: {tag}")
            return matches[0] if matches else None
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


def _download_urls(assets: dict[str, dict], expected: set[str]) -> dict[str, str]:
    if set(assets) != expected:
        raise ValueError("Download URL asset set differs from verified release")
    urls = {name: info.get("browser_download_url") for name, info in assets.items()}
    for url in urls.values():
        catalog.validate_asset_url(url)
    return urls


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
                    snapshot: bool = False, strict_batch: bool = False,
                    records: list[dict] | None = None) -> dict[str, str] | None:
    """Idempotent incremental publication with remote content verification."""
    flags = ["--prerelease", "--latest=false"] if snapshot else []
    if not files:
        raise ValueError("A Release must contain at least one ZIP")
    if len({path.name for path in files}) != len(files):
        raise ValueError("Duplicate local asset filename")
    for file in files:
        if not file.is_file() or file.name in {".", ".."} or "/" in file.name or "\\" in file.name:
            raise ValueError("Invalid Release asset")
    release = _release_api(tag)
    if release is None:
        # A partly successful upload must not make the next attempt fail 422.
        from .messages import release_message
        title, notes = release_message(tag, upstream_version, snapshot=snapshot, records=records,
            repo=os.environ.get("GITHUB_REPOSITORY", ""), run_id=os.environ.get("GITHUB_RUN_ID", ""),
            attempt=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
        _run("gh", "release", "create", tag,
             "--title", title,
             "--notes", notes,
             *(["--draft", "--verify-tag"] if strict_batch else []), *flags)
        release = _release_api(tag)
        if release is None:
            raise RuntimeError("Created GitHub Release could not be verified")
    existing = _release_asset_list(release["id"])
    # Validate ALL collisions before writing any asset. A published dated
    # release is frozen; only a draft may be resumed after a partial upload.
    if strict_batch:
        wanted = {file.name for file in files}
        if set(existing) - wanted or (not release.get("draft") and set(existing) != wanted):
            raise ValueError(f"Immutable dated Release already exists with different assets: {tag}")
    for file in files:
        if file.name in existing:
            _confirm_asset(tag, file, existing[file.name])
    for file in files:
        if file.name not in existing:
            _run("gh", "release", "upload", tag, str(file))
    if strict_batch and release.get("draft"):
        # Verify complete remote contents before making the draft public.
        final = _release_asset_list(release["id"])
        if set(final) != {file.name for file in files}:
            raise ValueError(f"Release upload is incomplete: {tag}")
        for file in files:
            _confirm_asset(tag, file, final[file.name])
        _run("gh", "release", "edit", tag, "--draft=false", *flags)
    elif snapshot:
        _run("gh", "release", "edit", tag, *flags)
    if strict_batch:
        # Read the public asset URLs after the final tag and draft state are settled.
        public = _release_api(tag)
        if public is None or public.get("draft") is not False or public.get("tag_name") != tag:
            raise ValueError("Release is not public after upload")
        final = _release_asset_list(public["id"])
        urls = _download_urls(final, {file.name for file in files})
        for file in files:
            _confirm_asset(tag, file, final[file.name])
        return urls


def _push_data(checkout: Path) -> None:
    catalog.stage_index(checkout)
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


def _verify_compliance_archive(path: Path, record: dict, audit_file: Path, *, kind: str = "binary") -> None:
    """Revalidate original installed evidence and reproduce public license files."""
    summary = record["compliance"]
    if not audit_file.is_file() or _digest(audit_file) != summary.get("audit_sha256"):
        raise ValueError("Missing or invalid internal license audit archive")
    with zipfile.ZipFile(path) as public, zipfile.ZipFile(audit_file) as archive:
        names = set(archive.namelist())
        public_names = set(public.namelist())
        if len(names) != len(archive.namelist()) or len(public_names) != len(public.namelist()):
            raise ValueError(f"Duplicate ZIP members: {path.name}")
        if len({name.casefold() for name in public_names}) != len(public_names):
            raise ValueError("Case-insensitive ZIP member collision")
        static_members = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe", "LICENSE.txt", PUBLIC_COPYRIGHT, PUBLIC_SPDX}
        allowed_roots = {"bin", "lib", "include", "share"} | ({"debug"} if kind == "debug" else set())
        for name in public_names:
            parts = name.lower().split("/")
            if record["linkage"] == "static":
                if name not in static_members:
                    raise ValueError(f"Unexpected public archive member: {name}")
            elif name != "LICENSE.txt" and parts[0] not in allowed_roots:
                raise ValueError(f"Unexpected public archive member: {name}")
            if (name.startswith("/") or "\\" in name or ":" in name or any(part in ("", ".", "..") for part in parts) or
                    parts[0] in ("licenses", "metadata") or
                    (parts[0] == "share" and (len(parts) < 3 or parts[1] != "ffmpeg")) or
                    parts[-1] in ("control", "build_info", "vcpkg_abi_info.txt", "vcpkg.spdx.json")):
                raise ValueError(f"Unexpected public archive member: {name}")
        for name in public_names - {"LICENSE.txt", PUBLIC_COPYRIGHT, PUBLIC_SPDX}:
            lower = name.lower()
            if kind == "binary" and (lower.endswith(".pdb") or lower.startswith("debug/")):
                raise ValueError(f"Debug payload in Binary: {name}")
            if kind == "debug" and not (
                (lower.startswith("bin/") and lower.endswith(".pdb")) or
                (lower.startswith("debug/bin/") and lower.endswith((".dll", ".pdb", ".exe"))) or
                (lower.startswith("debug/lib/") and lower.endswith((".lib", ".def", ".pc")))
            ):
                raise ValueError(f"Unexpected Debug add-on payload: {name}")
        for name in ("LICENSE.txt", PUBLIC_COPYRIGHT, PUBLIC_SPDX):
            if name not in public_names:
                raise ValueError(f"Missing distribution license file {name}: {path.name}")
        for name, field in ((PUBLIC_SPDX, "spdx_sha256"), (PUBLIC_COPYRIGHT, "copyright_sha256")):
            if hashlib.sha256(public.read(name)).hexdigest() != summary.get(field):
                raise ValueError(f"Compliance metadata hash differs for {name}: {path.name}")
        provenance = json.loads(archive.read("metadata/BUILD_PROVENANCE.json"))
        if provenance.get("assets") != record["assets"]:
            raise ValueError("Audit evidence does not bind the distribution assets")
        if record.get("abi_hash") and hashlib.sha256(archive.read("native/share/ffmpeg/vcpkg_abi_info.txt")).hexdigest() != record["abi_hash"]:
            raise ValueError("Audit native ABI input differs")
        for field in ("abi_hash", "triplet", "features", "variant_id", "package_spec"):
            if field in record and provenance.get(field) != record[field]:
                raise ValueError(f"Archive provenance differs on {field}: {path.name}")
        if record.get("release_date") and provenance.get("release_date") != record["release_date"]:
            raise ValueError(f"Archive provenance differs on release_date: {path.name}")
        if record.get("source_commit") and provenance.get("source", {}).get("upstream_ref") != record["source_commit"]:
            raise ValueError(f"Archive provenance differs on source commit: {path.name}")
        installed = provenance.get("installed_packages", [])
        if len(installed) != summary["package_count"]:
            raise ValueError(f"Installed package evidence count differs: {path.name}")
        declared = [{key: item[key] for key in (
            "name", "triplet", "version", "port_revision", "abi", "scope", "license_expression", "license_source", "compatibility")}
            for item in installed]
        if declared != summary["packages"]:
            raise ValueError(f"Installed package evidence differs: {path.name}")
        if summary.get("license_policy") != POLICY_VERSION or provenance.get("license_policy") != POLICY_VERSION:
            raise ValueError("License policy version differs; repackaging required")
        main_expression, primary = _ffmpeg_license(public.read("LICENSE.txt"), record["license"])
        if main_expression != summary.get("ffmpeg_license") or main_expression != provenance.get("ffmpeg_license"):
            raise ValueError("FFmpeg GNU license differs from compatibility report")
        required = {primary}
        if primary == "COPYING.LGPLv3":
            required.add("COPYING.GPLv3")
        if any(f"LICENSES/ffmpeg/upstream/{name}" not in names for name in required):
            raise ValueError("Missing upstream GNU terms in archive")
        edges = {(p["name"], p["triplet"]): {tuple(edge.split(":", 1)) for edge in p["dependency_keys"]}
                 for p in installed}
        if len(edges) != len(installed):
            raise ValueError("Duplicate installed package identity")
        root_job = {"version": record["version"], "features": record["features"],
                    "yaml": "master" if record.get("channel") == "master" else record["version"]}
        root_hosts = declared_root_hosts(root_job)
        # Archived root flags cannot be used to relabel a target as a tool.
        if root_hosts != set(provenance["declared_root_hosts"]):
            raise ValueError("FFmpeg recipe host flags differ from provenance")
        documents = {(p["name"], p["triplet"]): json.loads(archive.read(
            f"LICENSES/{p['name']}-{p['triplet']}/vcpkg.spdx.json")) for p in installed}
        host_edges = manifest_host_edges(provenance["verified_role_manifests"], documents,
                                         {(p["name"], p["triplet"]): set(p["features"]) for p in installed})
        scopes = dependency_scopes(edges, ("ffmpeg", record["triplet"]), root_hosts, host_edges)
        if set(scopes) != set(edges):
            raise ValueError("Unreachable packages in compliance graph")
        for package in installed:
            base = f"LICENSES/{package['name']}-{package['triplet']}/"
            for filename, field in (("copyright", "copyright_sha256"),
                                    ("vcpkg.spdx.json", "original_spdx_sha256")):
                name = base + filename
                if name not in names or hashlib.sha256(archive.read(name)).hexdigest() != package[field]:
                    raise ValueError(f"Missing or invalid per-Port evidence {name}: {path.name}")
            key = (package["name"], package["triplet"])
            copyright = archive.read(base + "copyright")
            original = documents[key]
            declaration = None
            if key == ("ffmpeg", record["triplet"]):
                expression, source = main_expression, "ffmpeg-copyright"
                if copyright != public.read("LICENSE.txt"):
                    raise ValueError("FFmpeg license evidence differs")
            else:
                expression, source, declaration = resolve_port_license(
                    original, ":".join(key), package["version"], package["port_revision"], copyright)
            scope = "system-dependency" if source == "external-system" else scopes[key]
            if package["scope"] != scope:
                raise ValueError("Dependency scope differs from archived graph")
            verify_system_archive_members(public_names, system_dependency=scope == "system-dependency")
            if declaration != package.get("license_declaration"):
                raise ValueError("Supplemental license declaration differs")
            if (expression, source) != (package["license_expression"], package["license_source"]):
                raise ValueError("License expression differs from archived original evidence")
            decision = scoped_compatibility(expression, main_expression, ":".join(key),
                name=key[0], version=package["version"], port_revision=package["port_revision"],
                copyright_sha256=hashlib.sha256(copyright).hexdigest(), linkage=record["linkage"],
                build_only=scope == "build-only", system_dependency=scope == "system-dependency")
            if decision != package["compatibility"]:
                raise ValueError("License compatibility result differs")
        for name, expected in distribution_evidence(archive.read, provenance).items():
            if public.read(name) != expected:
                raise ValueError(f"Public license evidence differs from original audit: {name}")



def _validate_dated_record(record: dict) -> None:
    if not record.get("release_date"):
        raise ValueError("Native dated release metadata is required")
    abi = record.get("abi_hash")
    if not isinstance(abi, str) or not re.fullmatch(r"[0-9a-f]{64}", abi):
        raise ValueError("Native release requires a full ABI")
    if "revision" in record or record.get("channel") not in ("master", "release"):
        raise ValueError("Invalid dated release identity")
    if record.get("license") not in ("gpl", "lgpl") or record.get("port") != "ffmpeg":
        raise ValueError("Invalid native package or license")
    expected = variant_name(record["version"], 0, record["triplet"],
                            record["linkage"], record["license"], abi_hash=abi)
    if expected != record.get("variant_id"):
        raise ValueError("Dated record disagrees with native variant identity")
    if record.get("arch") != record["triplet"].split("-")[0]:
        raise ValueError("Dated record disagrees with architecture")
    date_suffix(record["release_date"])
    if record.get("publication_date"):
        date_suffix(record["publication_date"])
        if record["publication_date"] < record["release_date"]:
            raise ValueError("Publication date predates archive date")
    if record["channel"] == "master":
        if not re.fullmatch(r"[0-9a-f]{40}", record.get("source_commit", "")):
            raise ValueError("Master requires the full pinned upstream commit")
    elif not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", record["version"]):
        raise ValueError("Tagged release requires a numeric upstream version")


def _verify_distribution(record: dict, directory: Path, *, reused: bool = False) -> None:
    # Fresh artifacts always need the full CI evidence. Previously published
    # assets are trusted only by the current-format Data index and exact bytes.
    if int(record.get("package_format", 1)) != PACKAGE_FORMAT_VERSION or (not reused and not record.get("compliance")):
        raise ValueError("Missing required license evidence")
    if record.get("release_date"):
        _validate_dated_record(record)
    expected = expected_asset_kinds(record["linkage"], PACKAGE_FORMAT_VERSION)
    if set(record["assets"]) != expected:
        raise ValueError("Unexpected distribution asset types")
    for kind, asset in record["assets"].items():
        if record.get("release_date") and asset["file"] != archive_name(record, kind=kind):
            raise ValueError(f"Invalid dated archive name: {asset['file']}")
        if Path(asset["file"]).name != asset["file"]:
            raise ValueError("Invalid asset filename")
        path = directory / asset["file"]
        if not path.is_file() or path.stat().st_size != asset["size"] or "sha256:" + _digest(path) != asset["digest"]:
            raise ValueError(f"Distribution asset digest or size mismatch: {asset['file']}")
        if not reused:
            _verify_compliance_archive(path, record, directory / audit_name(record), kind=kind)

    if not reused and record["linkage"] == "shared":
        with zipfile.ZipFile(directory / record["assets"]["binary"]["file"]) as binary, \
                zipfile.ZipFile(directory / record["assets"]["debug"]["file"]) as debug:
            shared = {n.casefold() for n in binary.namelist()}.intersection(n.casefold() for n in debug.namelist())
            evidence = {"LICENSE.txt", PUBLIC_COPYRIGHT, PUBLIC_SPDX}
            if shared != {n.casefold() for n in evidence} or any(binary.read(n) != debug.read(n) for n in evidence):
                raise ValueError("Binary/Debug overlap or inconsistent compliance files")
            verify_debug_layout(binary.namelist(), debug.namelist())
            verify_symbols(binary.namelist(), debug.namelist(), binary.read, debug.read)


def _check_reuse(job: dict, record: dict) -> None:
    for field in ("version", "triplet", "linkage", "license", "abi_hash"):
        if job[field] != record.get(field):
            raise ValueError(f"Reuse record differs from planned {field}")
    _validate_dated_record(record)
    if int(record.get("package_format", 0)) != PACKAGE_FORMAT_VERSION:
        raise ValueError("Cannot reuse an undated or outdated distribution")
    if record["channel"] != ("master" if job.get("yaml") == "master" else "release"):
        raise ValueError("Reuse record differs from planned channel")
    if job.get("source_ref") and job["source_ref"] != record.get("source_commit"):
        raise ValueError("Reuse record differs from planned source commit")



def _fetch_reused(record: dict, directory: Path) -> None:
    source_tag = record_release_tag(record)
    for asset in record["assets"].values():
        name = asset["file"]
        if Path(name).name != name:
            raise ValueError("Invalid reused asset filename")
        path = directory / name
        if not path.exists():
            _run("gh", "release", "download", source_tag, "--repo",
                 os.environ["GITHUB_REPOSITORY"], "--pattern", name, "--dir", str(directory))
    _verify_distribution(record, directory, reused=True)


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
        if not record.get("release_date") or not record.get("abi_hash"):
            raise ValueError("Native dated release metadata is required")
        if record.get("abi_hash"):
            abi = record["abi_hash"]
            if (not isinstance(abi, str) or len(abi) != 64
                    or any(c not in "0123456789abcdef" for c in abi)):
                raise ValueError(f"Invalid native vcpkg ABI: {metadata}")
        if record["variant_id"] in records:
            raise ValueError(f"Duplicate FFmpeg variant: {record['variant_id']}")
        for asset in record.get("assets", {}).values():
            if Path(asset["file"]).name != asset["file"]:
                raise ValueError("Invalid asset filename")
            path = artifacts_dir / asset["file"]
            if not path.is_file():
                raise FileNotFoundError(f"Missing release archive: {path}")
            if asset.get("size") and path.stat().st_size != asset["size"]:
                raise ValueError(f"Archive size mismatch: {path}")
            if asset.get("digest") and asset["digest"] != "sha256:" + _digest(path):
                raise ValueError(f"Archive digest mismatch: {path}")
        if record.get("release_date") and record.get("publication_date"):
            raise ValueError("Fresh artifact cannot claim a reuse publication date")
        _verify_distribution(record, artifacts_dir)
        records[record["variant_id"]] = record

    reused = []
    if expected_plan is not None:
        plan = json.loads(expected_plan.read_text(encoding="utf-8"))
        planned = plan["jobs"]
        missing = {job["id"] for job in planned} - records.keys()
        if missing:
            raise RuntimeError(f"Missing planned variants: {sorted(missing)}" if records
                               else "Missing all planned build artifacts")
        for job in planned:
            for field in ("version", "abi_hash", "port", "release_date"):
                if job.get(field) and job[field] != records[job["id"]].get(field):
                    raise ValueError(f"Build Plan and artifact disagree on {field}: {job['id']}")
            record = records[job["id"]]
            for field in ("triplet", "features", "license", "linkage"):
                if field in job and job[field] != record.get(field):
                    raise ValueError(f"Build Plan and artifact disagree on {field}: {job['id']}")
            if job.get("package") and job["package"] != record.get("package_spec"):
                raise ValueError(f"Build Plan and artifact disagree on package spec: {job['id']}")
            if job.get("release_date"):
                if record.get("channel") != ("master" if job.get("yaml") == "master" else "release"):
                    raise ValueError("Build Plan and artifact disagree on channel")
                if job.get("source_ref") and job["source_ref"] != record.get("source_commit"):
                    raise ValueError("Build Plan and artifact disagree on source commit")
                if job.get("expected_variants") != record.get("expected_variants"):
                    raise ValueError("Build Plan and artifact disagree on matrix size")

        if set(records) - {job["id"] for job in planned}:
            raise ValueError("Unplanned build artifacts")
        for entry in plan.get("reuse", []):
            job, source = entry["job"], entry["record"]
            _check_reuse(job, source)
            # Original archive name/date and SHA remain unchanged.
            reused.append((source, dict(release_index(source), publication_date=job["release_date"],
                                        expected_variants=job.get("expected_variants", 0))))

    groups: dict[str, list[dict]] = {}
    for record in [*records.values(), *(target for _, target in reused)]:
        record.pop("publication_tag", None)
        tag = record_release_tag(record)
        groups.setdefault(tag, []).append(record)
    for tag, group in groups.items():
        slots = {(r["triplet"], r["linkage"], r["license"]) for r in group}
        if len(slots) != len(group):
            raise ValueError(f"Duplicate public variant slot in {tag}")
        if len({(r["version"], r.get("source_commit")) for r in group}) != 1:
            raise ValueError(f"Different FFmpeg source snapshots in {tag}")
        expected = {r.get("expected_variants", 0) for r in group}
        if not dry_run and expected_plan is not None and expected != {len(group)}:
            raise ValueError(f"Incomplete dated release matrix: {tag}")

    if dry_run:
        if expected_plan is None and not groups:
            raise ValueError("No packaged variants to validate")
        return sorted(groups)
    if not groups:
        return []

    production = os.environ.get("FFBUILD_PUBLISH") == "true"
    if expected_plan is not None and plan.get("request") is not None and not production:
        raise ValueError("CI publication requires explicit production authorization")
    if production:
        from .autoheal.models import commit_sha
        from .release_trigger import snapshot
        from .identity import public_version
        request = plan.get("request") if expected_plan is not None else None
        if (os.environ.get("GITHUB_REF") != "refs/heads/main" or
                os.environ.get("GITHUB_EVENT_NAME") not in ("workflow_dispatch", "schedule") or
                not request or request.get("production") is not True or
                request.get("yaml") != os.environ.get("FFBUILD_PUBLISH_VERSION") or
                request.get("date") != os.environ.get("FFBUILD_PUBLISH_DATE") or
                commit_sha(request.get("repository_commit")) != commit_sha(os.environ.get("GITHUB_SHA")) or
                len(groups) != 1):
            raise ValueError("Publication differs from verified production request")
        group = next(iter(groups.values()))
        from .native_abi import build_requests
        expected_rows, blocked = build_requests(version=request["yaml"],
            snapshot={k: request[k] for k in ("ref", "commit", "sha512")} if request["yaml"] == "master" else None,
            release_date=request["date"])
        if blocked:
            raise ValueError("Production target set contains blocked variants")
        expected_slots = {(r["triplet"], r["linkage"], r["license"]) for r in expected_rows}
        if ({(r["triplet"], r["linkage"], r["license"]) for r in group} != expected_slots or
                len(group) != len(expected_slots)) or any(public_version(r) != request["yaml"] or
                r.get("publication_date", r["release_date"]) != request["date"] for r in group):
            raise ValueError("Production requires all 16 variants of the selected version")
        if request["yaml"] == "master":
            pin = snapshot({k: request[k] for k in ("ref", "commit", "sha512")})
            if any(r.get("source_commit") != pin["commit"] for r in group):
                raise ValueError("Master source differs from verified plan")
        if not (data_dir / "index.json").is_file():
            raise ValueError("Production requires release catalog index.json")
    if not (data_dir / ".git").exists():
        raise FileNotFoundError("An authenticated local data branch checkout is required")
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        raise RuntimeError("GitHub token is required for release publication")

    # Preflight the data index before any upload; a date cannot silently
    # replace a previously published logical slot with another ABI.
    for group in groups.values():
        if not production:
            catalog.preflight(data_dir, group, require_complete=False)
        else:
            catalog.manifest(data_dir)
            catalog.release_from_records(group)
    if expected_plan is None:
        raise ValueError("A complete native build plan is required for dated publication")
    # Plan-time data is not enough: retention or concurrent publication may
    # have changed the current data checkout before the publisher acquired its lock.
    from .state import PublishedState
    current_state = PublishedState(directory=data_dir)
    for source, _ in reused:
        current = current_state.find_abi(source["version"], source["triplet"], source["abi_hash"],
                                         channel=source["channel"], source_commit=source.get("source_commit"))
        if current != source:
            raise ValueError("Reusable variant changed or disappeared from current data")
    with tempfile.TemporaryDirectory(prefix="ffbuild-reuse-") as scratch:
        reused_dir = Path(scratch)
        for source, target in reused:
            _fetch_reused(source, reused_dir)
        if production:
            from .release_trigger import publication_tag_candidate, write_publication_tag, git
            group = next(iter(groups.values()))
            _, _, batch_record = catalog.release_from_records(group)
            # Content identity binds every published slot, SHA256, ABI and source.
            batch = hashlib.sha256(json.dumps(batch_record, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            commit = request["repository_commit"]
            if git("rev-parse", "HEAD") != commit:
                raise ValueError("Publication checkout differs from verified build")
            tag, exists = publication_tag_candidate(request["yaml"], request["date"], commit, batch)
            for record in group:
                record["publication_tag"] = tag
            catalog.preflight(data_dir, group)
            # Refuse a release with no matching verified tag before writing anything.
            if not exists and _release_api(tag) is not None:
                raise ValueError("Release exists without the expected verified tag")
            if not exists:
                write_publication_tag(tag, commit, batch, release_record=batch_record)
            groups = {tag: group}
        # Never record success before GitHub accepted all release assets.
        urls_by_tag = {}
        for tag, group in sorted(groups.items()):
            paths = []
            for record in group:
                directory = reused_dir if any(record is target for _, target in reused) else artifacts_dir
                paths.extend(directory / asset["file"] for asset in record["assets"].values())
            first = group[0]
            urls_by_tag[tag] = _release_assets(tag, sorted(paths), upstream_version=first["version"],
                            snapshot=first.get("channel") == "master" or "-g" in str(first.get("ffmpeg_ref", "")),
                            strict_batch=True, records=group)
        for tag, group in groups.items():
            if not isinstance(urls_by_tag[tag], dict):
                raise ValueError("Missing verified release download URLs")
            catalog.register_release(data_dir, group, urls=urls_by_tag[tag])
    _push_data(data_dir)
    return sorted(groups)

def recover_index(tag: str, data_dir: Path) -> None:
    """Recover a published Release's exact catalog row without a compiler or CI ZIPs."""
    from .release_trigger import parse_tag, git
    from .autoheal.models import commit_sha
    version, day = parse_tag(tag)
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Index recovery is restricted to main")
    if not (data_dir / ".git").exists() or not (data_dir / "index.json").is_file():
        raise ValueError("Recovery requires an authenticated Data checkout")
    ref = f"refs/tags/{tag}"
    git("fetch", "--no-tags", "origin", f"{ref}:{ref}")
    annotation = json.loads(git("for-each-ref", "--format=%(contents)", ref))
    if not isinstance(annotation, dict) or set(annotation) != {"batch", "repository_commit", "release"}:
        raise ValueError("Tag does not contain a recoverable verified batch")
    commit = commit_sha(annotation["repository_commit"])
    if git("rev-parse", ref + "^{commit}") != commit:
        raise ValueError("Tag commit differs from publication evidence")
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], check=True)
    batch_record = annotation["release"]
    if (hashlib.sha256(json.dumps(batch_record, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            != annotation["batch"]):
        raise ValueError("Invalid immutable publication batch")
    stem = f"ffmpeg-{version}-{date_suffix(day)}"
    if batch_record["tag"] != stem or batch_record["date"] != day:
        raise ValueError("Recovery tag and batch date/version differ")
    kind, key = ("master", int(day[:4])) if version == "master" else ("releases", version)
    release = dict(batch_record, tag=tag)
    rows = catalog.expanded(kind, key, release)
    from .targets import load_targets
    wanted = {(t.triplet, "static" if "static" in t.roots else "shared",
               "gpl" if "all-gpl" in t.roots else "lgpl") for t in load_targets()}
    if len(rows) != len(wanted) or {(r["triplet"],r["linkage"],r["license"]) for r in rows} != wanted:
        raise ValueError("Incomplete recovery matrix")
    if any(r.get("package_format") != PACKAGE_FORMAT_VERSION for r in rows):
        raise ValueError("Unsupported archive format")
    for r in rows:
        r["expected_variants"] = len(rows)
    _, _, regenerated = catalog.release_from_records(rows)
    if regenerated != release:
        raise ValueError("Recovered batch is not canonical")
    catalog.preflight(data_dir, rows)
    remote = _release_api(tag)
    if (remote is None or remote.get("tag_name") != tag or remote.get("draft") is not False
            or remote.get("prerelease") is not (version == "master")):
        raise ValueError("Only an existing public Release can be recovered")
    expected = {a["file"]:a for r in rows for a in r["assets"].values()}
    found = _release_asset_list(remote["id"])
    if set(found) != set(expected):
        raise ValueError("Remote asset set differs from verified batch")
    for name, a in expected.items():
        info = found[name]
        if info.get("size") != a["size"]:
            raise ValueError("Recovery asset size mismatch")
        digest = info.get("digest")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            with tempfile.TemporaryDirectory(prefix="ffbuild-recovery-") as scratch:
                _run("gh", "release", "download", tag, "--repo", os.environ["GITHUB_REPOSITORY"],
                     "--pattern", name, "--dir", scratch)
                downloaded = Path(scratch) / name
                if not downloaded.is_file() or downloaded.stat().st_size != a["size"]:
                    raise ValueError("Recovery asset missing or truncated")
                digest = "sha256:" + _digest(downloaded)
        if digest != a["digest"]:
            raise ValueError("Recovery asset digest mismatch")
    catalog.register_release(data_dir, rows, urls=_download_urls(found, set(expected)))
    _push_data(data_dir)
