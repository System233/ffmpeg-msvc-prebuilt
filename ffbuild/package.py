"""Produce immutable CI artifacts from vcpkg's installed package layout.

This module consumes vcpkg package metadata; it does not infer or silently
upgrade the requested FFmpeg license.  Build inputs and source identity come
from the verified plan, and the resulting YAML is written for the data branch.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .identity import is_lts, variant_name
from .fingerprint import variant_fingerprint
from .compliance import PACKAGE_FORMAT_VERSION, compliance_files


def _read_control(package: Path) -> tuple[str, int, set[str], set[str]]:
    file = package / "CONTROL"
    if not file.is_file():
        raise FileNotFoundError(f"Missing vcpkg CONTROL: {file}")
    version = ""
    revision = 0
    features: set[str] = set()
    dependencies: set[str] = set()
    for section in file.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n\n"):
        attributes: dict[str, str] = {}
        for line in section.splitlines():
            if ": " in line and not line.startswith(" "):
                key, value = line.split(": ", 1)
                attributes[key] = value.strip()
        version = version or attributes.get("Version", "")
        revision = int(attributes.get("Port-Version", revision))
        if attributes.get("Feature"):
            features.add(attributes["Feature"])
        if attributes.get("Depends"):
            for item in attributes["Depends"].split(","):
                dependencies.add(item.split("(", 1)[0].strip())
    if not version:
        raise ValueError(f"vcpkg CONTROL has no version: {file}")
    return version, revision, features, dependencies - {""}


def _layout(package: Path) -> str:
    info = package / "BUILD_INFO"
    if not info.is_file():
        raise FileNotFoundError(f"Missing vcpkg BUILD_INFO: {info}")
    for line in info.read_text(encoding="utf-8").splitlines():
        if line.startswith("LibraryLinkage:"):
            return "shared" if line.split(":", 1)[1].strip() == "dynamic" else "static"
    raise ValueError(f"Missing LibraryLinkage in {info}")


def _verify_native_package_abi(package: Path, port: str, expected: str) -> None:
    """Verify the ABI actually used by vcpkg, not merely the dry-run plan.

    The pinned vcpkg release puts the exact ABI input text in the package's
    share/<port>/vcpkg_abi_info.txt. Its SHA256 is the package ABI recorded
    in the install log and binary cache. Fail closed when absent or different.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("The full native vcpkg ABI is required")
    abi_input = package / "share" / port / "vcpkg_abi_info.txt"
    if not abi_input.is_file():
        raise FileNotFoundError(f"Actual installed vcpkg ABI inputs missing: {abi_input}")
    with abi_input.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(
            f"Built package ABI differs from planned vcpkg ABI: planned={expected}, actual={actual}"
        )


def _files(package: Path, linkage: str, *, develop: bool,
           port: str = "ffmpeg") -> dict[str, Path]:
    paths: dict[str, Path] = {}
    binaries = ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"]
    for name in binaries:
        for folder in (f"tools/{port}", "bin"):
            path = package / folder / name
            if path.is_file():
                paths[f"bin/{name}"] = path
                break
    # Preserve the existing scripts/package_release.py distribution contract.
    # Static variants contain applications only (not a copied static SDK).
    # Shared variants contain release SDK or full debug SDK respectively.
    # FFmpeg's original CMake builder ALWAYS installs consumer metadata under
    # share/ffmpeg, regardless of the version-qualified vcpkg Port identity.
    if linkage == "shared":
        folders = ["bin", "lib", "include", "share/ffmpeg"]
        if develop:
            folders.append("debug")
        for folder in folders:
            root = package / folder
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file() and (develop or path.suffix.lower() != ".pdb"):
                    paths[path.relative_to(package).as_posix()] = path
    for name in ("CONTROL", "BUILD_INFO"):
        path = package / name
        if path.is_file():
            paths[name] = path
    if linkage == "static":
        # The legacy static archive is flat: ffmpeg.exe, ffprobe.exe,
        # CONTROL and BUILD_INFO, without a bin/ prefix or SDK contents.
        return {Path(member).name: source for member, source in paths.items()}
    return paths


def _archive(target: Path, paths: dict[str, Path], copyright_file: Path,
             *, evidence: dict[str, bytes] | None = None) -> dict:
    if not paths and not evidence:
        raise ValueError(f"Empty FFmpeg artifact: {target}")
    if not copyright_file.is_file():
        raise FileNotFoundError(f"Copyright text missing: {copyright_file}")
    evidence = evidence or {}
    if set(paths).intersection(evidence) or "LICENSE.txt" in paths or "LICENSE.txt" in evidence:
        raise ValueError("Duplicate or conflicting compliance archive member")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for member, file in sorted(paths.items()):
            archive.write(file, member)
        archive.write(copyright_file, "LICENSE.txt")
        for member, data in sorted(evidence.items()):
            if member.startswith("/") or ".." in Path(member).parts or "\\" in member:
                raise ValueError(f"Unsafe compliance archive member: {member}")
            archive.writestr(member, data)
    with target.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"file": target.name, "size": target.stat().st_size, "digest": "sha256:" + digest}


def package_job(package: Path, job: dict, output: Path,
                *, installed_root: Path | None = None,
                source_tree: Path | None = None) -> Path:
    """Validate an already-built vcpkg package against its planned feature set."""
    port = job.get("port", "ffmpeg")
    if "abi_hash" in job:
        _verify_native_package_abi(package, port, job["abi_hash"])
    control_version, revision, features, deps = _read_control(package)
    linkage = _layout(package)
    actual_license = ("nonfree" if "license-nonfree" in features
                      else "gpl" if "license-gpl" in features else "lgpl")
    if actual_license != job["license"]:
        raise ValueError(f"FFmpeg license mismatch: planned {job['license']}, vcpkg enabled {actual_license}")
    if linkage != job["linkage"]:
        raise ValueError(f"FFmpeg linkage mismatch: planned {job['linkage']}, built {linkage}")
    actual_features = features - {"core"}  # vcpkg adds its implicit core Feature
    if actual_features != set(job["features"]):
        raise ValueError(f"vcpkg Feature closure differs from Build Plan: missing={sorted(set(job['features']) - actual_features)}, extra={sorted(actual_features - set(job['features']))}")
    if "abi_hash" not in job and variant_fingerprint(
            job["build_hash"], job["triplet"], job["feature_hash"]) != job["variant_hash"]:
        raise ValueError("Build Plan feature identity does not match the variant fingerprint")
    if int(job["revision"]) != revision:
        raise ValueError(f"FFmpeg revision mismatch: planned {job['revision']}, built {revision}")
    if job["yaml"] != "master" and job["yaml"] != control_version:
        raise ValueError(f"Unexpected FFmpeg upstream version: {control_version}")
    if "abi_hash" in job:
        identifier = variant_name(job["version"], revision, job["triplet"],
                                  linkage, actual_license, abi_hash=job["abi_hash"])
    else:
        identifier = variant_name(job["version"], revision, job["triplet"],
                                  linkage, actual_license, job["feature_hash"])
    if identifier != job["id"]:
        raise ValueError("Build Plan variant identity mismatch")
    if installed_root is None or source_tree is None:
        raise ValueError("Package-format v2 requires --installed-root and --source-tree "
                         "for license and upstream COPYING evidence")
    copyright_file = package / "share" / port / "copyright"
    evidence, evidence_summary = compliance_files(
        installed_root, job, ffmpeg_copyright=copyright_file, source_tree=source_tree)
    output.mkdir(parents=True, exist_ok=True)
    suffix = f"-pkg{PACKAGE_FORMAT_VERSION}"
    assets = {"binary": _archive(output / f"{identifier}{suffix}.zip",
                                 _files(package, linkage, develop=False, port=port),
                                 copyright_file, evidence=evidence)}
    if linkage == "shared":
        assets["develop"] = _archive(output / f"{identifier}{suffix}-develop.zip",
                                     _files(package, linkage, develop=True, port=port),
                                     copyright_file, evidence=evidence)
    assets["compliance"] = _archive(
        output / f"{identifier}{suffix}-compliance.zip", {},
        copyright_file, evidence=evidence)
    sums = output / f"{identifier}{suffix}.sha256"
    sums.write_text("".join(f"{value['digest'].removeprefix('sha256:')}  {value['file']}\n"
                            for value in assets.values()), encoding="ascii")
    checksum = {"file": sums.name, "size": sums.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(sums.read_bytes()).hexdigest()}
    sbom_path = output / f"{identifier}{suffix}.spdx.json"
    sbom_path.write_bytes(evidence["SBOM.spdx.json"])
    sbom_asset = {"file": sbom_path.name, "size": sbom_path.stat().st_size,
                  "digest": "sha256:" + hashlib.sha256(sbom_path.read_bytes()).hexdigest()}
    record = {
        "variant_id": identifier,
        "version": job["version"],
        "revision": revision,
        "arch": job["triplet"].split("-")[0],
        "triplet": job["triplet"], "linkage": linkage, "license": actual_license,
        "package_spec": job["package"],
        "lts": is_lts(job["version"]),
        "ffmpeg_ref": job.get("ref") or "n" + job.get("source_version", control_version),
        "build_date": datetime.now(timezone.utc).isoformat(),
        "package_format": PACKAGE_FORMAT_VERSION, "compliance": evidence_summary,
        "checksums": checksum, "sbom": sbom_asset,
        "assets": assets, "features": sorted(actual_features), "dependencies": sorted(deps),
    }
    if "abi_hash" in job:
        record.update({"port": port, "abi_hash": job["abi_hash"],
                       "expected_variants": job.get("expected_variants", 0)})
    else:
        record.update({"feature_hash": job["feature_hash"],
                       "build_hash": job["build_hash"],
                       "variant_hash": job["variant_hash"]})
    metadata = output / f"{identifier}.var.yaml"
    metadata.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")
    return metadata
