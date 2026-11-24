"""Auditable vcpkg license evidence for one concrete FFmpeg installation.

Package Status is the source of dependency *reachability*, not evidence that
each archive is physically linked into the final executable. Per-Port SPDX and
copyright files are copied without attempting to reinterpret their legal
effect. Missing evidence fails closed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .versions import ROOT, config

_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
_FORMAT = 2


@dataclass
class InstalledPort:
    name: str
    triplet: str
    version: str = ""
    revision: int = 0
    abi: str = ""
    dependencies: set[str] = field(default_factory=set)
    features: set[str] = field(default_factory=set)


def _paragraphs(source: str) -> list[dict[str, str]]:
    """Read Debian-style vcpkg status paragraphs, including folded fields."""
    result: list[dict[str, str]] = []
    for block in re.split(r"\r?\n\r?\n", source.strip()):
        fields: dict[str, str] = {}
        last = ""
        for line in block.splitlines():
            if line.startswith((" ", "\t")) and last:
                fields[last] += " " + line.strip()
            elif ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value.strip()
                last = key
        if fields:
            result.append(fields)
    return result


def _dependency_names(raw: str) -> set[str]:
    names: set[str] = set()
    for item in re.split(r",(?![^()]*\))", raw):
        match = re.match(r"\s*([a-z0-9][a-z0-9+.-]*)", item)
        if match:
            names.add(match.group(1))
    return names


def installed_status(root: Path) -> dict[tuple[str, str], InstalledPort]:
    status = root / "vcpkg" / "status"
    if not status.is_file():
        raise FileNotFoundError(f"Installed vcpkg status is missing: {status}")
    ports: dict[tuple[str, str], InstalledPort] = {}
    for row in _paragraphs(status.read_text(encoding="utf-8")):
        if row.get("Status") != "install ok installed":
            continue
        name, triplet = row.get("Package", ""), row.get("Architecture", "")
        if not _NAME.fullmatch(name) or not triplet:
            raise ValueError(f"Invalid installed vcpkg package name/architecture: {row}")
        port = ports.setdefault((name, triplet), InstalledPort(name, triplet))
        if "Feature" in row:
            port.features.add(row["Feature"])
        else:
            if not row.get("Version"):
                raise ValueError(f"Installed Port without version: {name}:{triplet}")
            port.version = row["Version"]
            port.revision = int(row.get("Port-Version", 0))
            port.abi = row.get("Abi", "")
        port.dependencies.update(_dependency_names(row.get("Depends", "")))
    if not ports:
        raise ValueError("vcpkg status lists no installed packages")
    return ports


def reachable_ports(root: Path, triplet: str, primary: str = "ffmpeg") -> list[InstalledPort]:
    ports = installed_status(root)
    if (primary, triplet) not in ports:
        raise ValueError(f"FFmpeg not installed in the actual vcpkg target root: {triplet}")
    selected: dict[tuple[str, str], InstalledPort] = {}
    stack = [(primary, triplet)]
    while stack:
        name, arch = stack.pop()
        if (name, arch) in selected:
            continue
        port = ports.get((name, arch))
        if port is None:
            raise ValueError(f"Missing installed dependency of FFmpeg: {name}:{arch}")
        if not port.version:
            raise ValueError(f"Package has no installed core status: {name}:{arch}")
        selected[(name, arch)] = port
        for dependency in port.dependencies:
            # vcpkg may select host-only tools under the host architecture.
            if (dependency, arch) in ports:
                stack.append((dependency, arch))
            else:
                candidates = [key for key in ports if key[0] == dependency]
                if len(candidates) == 1:
                    stack.append(candidates[0])
                elif len(candidates) > 1:
                    raise ValueError(f"Ambiguous installed triplet for {dependency}: {candidates}")
                else:
                    raise ValueError(f"Referenced dependency not installed: {dependency}")
    return sorted(selected.values(), key=lambda x: (x.name, x.triplet))


def _spdx_declared(source: dict, name: str) -> str:
    if not source.get("spdxVersion", "").startswith("SPDX-2."):
        raise ValueError(f"Invalid SPDX document for {name}")
    packages = source.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError(f"SPDX packages missing for {name}")
    expressions = {p.get("licenseDeclared", "NOASSERTION") for p in packages
                   if isinstance(p, dict)}
    expressions -= {"", "NOASSERTION", "NONE", None}
    if not expressions:
        raise ValueError(f"Unknown/NOASSERTION declared SPDX license for {name}")
    # Multiple SPDX package records can describe one vcpkg build; preserve
    # expressions rather than silently choosing one of them.
    return " AND ".join(sorted(expressions))


def _reject_unambiguous_gpl_only_license(declared: str, package: str,
                                         mode: str) -> None:
    """Reject a clearly GPL-only package under LGPL, without guessing OR choices.

    Complex expressions and exceptions still require an explicit legal audit:
    this conservative screen is not a general SPDX license solver.
    """
    if mode != "lgpl":
        return
    gpl = re.search(r"(?<![A-Za-z])(?:AGPL|GPL)-\d", declared)
    if gpl and " OR " not in declared.upper():
        raise ValueError(
            f"GPL-only installed dependency {package} is incompatible with "
            f"LGPL-mode publication without explicit review: {declared}")


def _ffmpeg_license(data: bytes, expected_mode: str) -> tuple[str, str]:
    """Match the actual GNU license text selected by FFmpeg configure."""
    header = data[:1500].decode("utf-8", errors="replace").upper()
    lesser = "GNU LESSER GENERAL PUBLIC LICENSE" in header
    general = lesser or "GNU GENERAL PUBLIC LICENSE" in header
    version = re.search(r"VERSION\s+(2\.1|2|3)\b", header)
    if not general or not version:
        raise ValueError("Cannot identify exact FFmpeg GNU license from installed copyright")
    family = "lgpl" if lesser else "gpl"
    if family != expected_mode:
        raise ValueError(f"FFmpeg copyright says {family} but planned {expected_mode}")
    value = version.group(1)
    expression = f"{'LGPL' if lesser else 'GPL'}-{value}.0-or-later" if value in {"2", "3"} else "LGPL-2.1-or-later"
    upstream = {
        ("lgpl", "2.1"): "COPYING.LGPLv2.1",
        ("lgpl", "3"): "COPYING.LGPLv3",
        ("gpl", "2"): "COPYING.GPLv2",
        ("gpl", "3"): "COPYING.GPLv3",
    }.get((family, value))
    if upstream is None:
        raise ValueError(f"Unsupported FFmpeg GNU license version: {family} {value}")
    return expression, upstream


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: dict) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _source_provenance(job: dict) -> dict:
    selected = config(job["yaml"]) if job.get("yaml") != "master" else config("master")
    source = selected.get("source", {})
    files = []
    for name in selected.get("patches", []):
        patch = ROOT / "patches" / name
        if not patch.is_file():
            raise FileNotFoundError(f"Provenance patch missing: {name}")
        files.append({"path": f"patches/{name}", "sha256": _sha256(patch.read_bytes())})
    return {
        "upstream_repository": source.get("repo", "ffmpeg/ffmpeg"),
        "upstream_ref": job.get("ref") or source.get("ref", f"n{job['version']}").replace(
            "${VERSION}", job["version"]),
        "source_sha512": job.get("sha512") or source.get("sha512", ""),
        "patches": files,
    }


def compliance_files(installed_root: Path, job: dict, *,
                     ffmpeg_copyright: Path,
                     source_tree: Path | None = None) -> tuple[dict[str, bytes], dict]:
    """Assemble actual Port evidence and consolidated SPDX, without copying libraries.

    Exact installed target packages are discovered from vcpkg's status graph.
    Host tools, if reachable, are identified as such. This documents the
    resolved build dependency graph, not physical object-file attribution.
    """
    triplet = job["triplet"]
    selected = reachable_ports(installed_root, triplet)
    if not ffmpeg_copyright.is_file():
        raise FileNotFoundError("Missing FFmpeg license text")
    main_expression, primary_license = _ffmpeg_license(
        ffmpeg_copyright.read_bytes(), job["license"])
    contents: dict[str, bytes] = {}
    summary: list[dict] = []
    id_by_name: dict[tuple[str, str], str] = {}
    for index, port in enumerate(selected, 1):
        key = (port.name, port.triplet)
        spdx_id = f"SPDXRef-vcpkg-{index}"
        id_by_name[key] = spdx_id
        folder = installed_root / port.triplet / "share" / port.name
        copyright_file = ffmpeg_copyright if port.name == "ffmpeg" and port.triplet == triplet else folder / "copyright"
        if not copyright_file.is_file() or not copyright_file.stat().st_size:
            raise ValueError(f"Missing/nonempty copyright notice for {port.name}:{port.triplet}")
        copyright_data = copyright_file.read_bytes()
        contents[f"LICENSES/{port.name}-{port.triplet}/copyright"] = copyright_data
        spdx_file = folder / "vcpkg.spdx.json"
        if not spdx_file.is_file():
            raise ValueError(f"Missing vcpkg SPDX for {port.name}:{port.triplet}")
        original_spdx = spdx_file.read_bytes()
        try:
            parsed = json.loads(original_spdx)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Invalid vcpkg SPDX JSON for {port.name}:{port.triplet}") from exc
        declared = (main_expression if port.name == "ffmpeg" else
                    _spdx_declared(parsed, f"{port.name}:{port.triplet}"))
        if port.name != "ffmpeg":
            _reject_unambiguous_gpl_only_license(
                declared, f"{port.name}:{port.triplet}", job["license"])
        contents[f"LICENSES/{port.name}-{port.triplet}/vcpkg.spdx.json"] = original_spdx
        summary.append({
            "name": port.name, "triplet": port.triplet,
            "version": port.version, "port_revision": port.revision,
            "abi": port.abi, "features": sorted(port.features),
            "declared_license": declared, "dependencies": sorted(port.dependencies),
            "scope": "target-install" if port.triplet == triplet else "host-install",
            "copyright_sha256": _sha256(copyright_data),
            "original_spdx_sha256": _sha256(original_spdx),
        })
    # FFmpeg upstream license files also include the companion GPL terms
    # required to interpret the LGPLv3 terms in the top-level LICENSE.txt.
    if source_tree is not None:
        if not source_tree.is_dir():
            raise FileNotFoundError(f"Missing upstream FFmpeg source tree: {source_tree}")
        upstream_files = [p for p in sorted(source_tree.glob("COPYING.*")) if p.is_file()]
        if not upstream_files:
            raise ValueError(f"No FFmpeg upstream COPYING files found: {source_tree}")
        upstream_names = {p.name for p in upstream_files}
        required = {primary_license}
        if primary_license == "COPYING.LGPLv3":
            required.add("COPYING.GPLv3")
        if not required.issubset(upstream_names):
            raise ValueError(f"Missing required upstream FFmpeg GNU terms: "
                             f"{sorted(required - upstream_names)}")
        for file in upstream_files:
            contents[f"LICENSES/ffmpeg/upstream/{file.name}"] = file.read_bytes()
    else:
        raise ValueError("The exact FFmpeg upstream COPYING terms are required")

    names = {(p.name, p.triplet): p for p in selected}
    relationships = [{"spdxElementId": "SPDXRef-DOCUMENT",
                      "relationshipType": "DESCRIBES",
                      "relatedSpdxElement": id_by_name[("ffmpeg", triplet)]}]
    for port in selected:
        for child in sorted(port.dependencies):
            candidates = [key for key in names if key[0] == child]
            if len(candidates) != 1:
                raise ValueError(f"Ambiguous or missing installed dependency edge {port.name} -> {child}")
            relationships.append({
                "spdxElementId": id_by_name[(port.name, port.triplet)],
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": id_by_name[candidates[0]],
            })
    packages = [{
        "SPDXID": id_by_name[(p["name"], p["triplet"])],
        "name": p["name"], "versionInfo": p["version"],
        "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": p["declared_license"],
        "copyrightText": "NOASSERTION",
        "comment": ("vcpkg installed status and attached original SPDX/copyright; "
                    "this is a package dependency graph, not proof of which "
                    "object files were linked into an executable."),
    } for p in summary]
    provenance = {
        "schema": 1,
        "variant_id": job["id"],
        "abi_hash": job.get("abi_hash"),
        "package_spec": job["package"],
        "triplet": triplet,
        "features": sorted(job["features"]),
        "source": _source_provenance(job),
        "ci_commit": None,  # filled from CI environment by packager when available
        "installed_packages": summary,
        "dependency_evidence": "installed vcpkg status and per-package copyright/SPDX",
        "not_a_link_map": True,
    }
    provenance["ci_commit"] = os.environ.get("GITHUB_SHA")
    spdx = {
        "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"FFmpeg vcpkg dependency closure {job['id']}",
        "documentNamespace": f"https://github.com/System233/ffmpeg-msvc-prebuilt/spdx/{job['id']}-pkg2",
        "creationInfo": {"creators": ["Tool: ffbuild-compliance-2"],
                         "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
        "packages": packages, "relationships": relationships,
        "comment": ("Generated from installed vcpkg package dependency relationships. "
                    "Per-package original vcpkg SPDX documents and notices are included "
                    "under LICENSES/. No claim of object-file-level attribution."),
    }
    lines = [
        "# Third-party notices — FFmpeg MSVC distribution",
        "",
        f"Variant: {job['id']}",
        "",
        "The following packages were reachable from the installed FFmpeg vcpkg "
        "dependency graph. Inclusion does not mean each package is physically "
        "linked into the executable. Consult original SPDX files and notices "
        "in LICENSES/ for authoritative legal terms.",
        "",
        "| Installed Port | Version | Triplet | Declared SPDX license |",
        "| --- | --- | --- | --- |",
    ]
    for p in summary:
        lines.append(f"| {p['name']} | {p['version']}#{p['port_revision']} | "
                     f"{p['triplet']} | {p['declared_license']} |")
    lines.extend(["", "License classifications are declarations from vcpkg SPDX metadata, "
                  "not an independent legal compatibility determination.", ""])
    contents["THIRD_PARTY_NOTICES.md"] = ("\n".join(lines) + "\n").encode("utf-8")
    contents["SBOM.spdx.json"] = _json(spdx)
    contents["BUILD_PROVENANCE.json"] = _json(provenance)
    return contents, {"package_count": len(summary),
                      "packages": [
                          {key: item[key] for key in (
                              "name", "triplet", "version", "port_revision",
                              "abi", "scope", "declared_license")}
                          for item in summary
                      ],
                      "spdx_sha256": _sha256(contents["SBOM.spdx.json"]),
                      "notices_sha256": _sha256(contents["THIRD_PARTY_NOTICES.md"])}


PACKAGE_FORMAT_VERSION = _FORMAT


def find_ffmpeg_source(buildtrees: Path) -> Path:
    """Locate the unpacked upstream source, never generated build outputs."""
    root = buildtrees / "ffmpeg" / "src"
    if not root.is_dir():
        raise FileNotFoundError(f"Unpacked FFmpeg source directory missing: {root}")
    candidates = {file.parent for file in root.rglob("COPYING.*")
                  if (file.parent / "configure").is_file()}
    if len(candidates) != 1:
        raise ValueError(f"Expected one unpacked FFmpeg source in {root}, got {len(candidates)}")
    return candidates.pop()
