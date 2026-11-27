"""Auditable vcpkg license evidence for one concrete FFmpeg installation.

Package Status is the source of dependency *reachability*, not evidence that
each archive is physically linked into the final executable. Per-Port SPDX and
copyright files are copied without attempting to reinterpret their legal
effect. Missing evidence fails closed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .versions import ROOT, GENERATED_PORTS, config
from .spec import resolve_features
from .port import ffmpeg_port_name
from .license_policy import POLICY_VERSION, scoped_compatibility, same_expression
from .identity import PACKAGE_FORMAT_VERSION

_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
# A publication format identifies both the public layout and the qualification
# gate that accepted its bytes. Advance the format when the policy changes;
# Data needs no separate compliance report or policy metadata for reuse.
if POLICY_VERSION != 1:
    raise RuntimeError("Update the publication format when changing the license policy")
LICENSE_DECLARATIONS = ROOT / "licenses"


def supplemental_license(name: str, version: str, revision: int, copyright_data: bytes) -> dict | None:
    """Read the supplemental SPDX 2.3 document for the exact Port version."""
    if not _NAME.fullmatch(name):
        raise ValueError(f"Invalid license declaration name: {name}")
    path = LICENSE_DECLARATIONS / f"{name}.spdx.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    packages = document.get("packages") if isinstance(document, dict) else None
    if (not isinstance(document, dict) or document.get("spdxVersion") != "SPDX-2.3"
            or document.get("SPDXID") != "SPDXRef-DOCUMENT" or document.get("dataLicense") != "CC0-1.0"
            or not isinstance(packages, list) or len(packages) != 1 or not isinstance(packages[0], dict)):
        raise ValueError(f"Invalid supplemental SPDX document: {name}")
    package = packages[0]
    if (package.get("name") != name or package.get("SPDXID") != "SPDXRef-port"
            or not isinstance(package.get("sourceInfo"), str) or not package["sourceInfo"].startswith("https://")
            or not isinstance(package.get("licenseDeclared"), str)
            or not package["licenseDeclared"].strip()):
        raise ValueError(f"Invalid supplemental SPDX package: {name}")
    expected_version = version + (f"#{revision}" if revision else "")
    if package.get("versionInfo") != expected_version:
        return None
    expression = package.get("licenseConcluded")
    if not isinstance(expression, str) or not expression.strip() or expression in ("NONE", "NOASSERTION"):
        return None
    references = set(re.findall(r"(?<![A-Za-z0-9.-])LicenseRef-[A-Za-z0-9.-]+", expression))
    extracted = document.get("hasExtractedLicensingInfos", [])
    if not isinstance(extracted, list) or any(not isinstance(item, dict) for item in extracted):
        raise ValueError(f"Invalid extracted licensing info: {name}")
    if ({item.get("licenseId") for item in extracted} != references
            or len(extracted) != len(references)
            or any(not isinstance(item.get("extractedText"), str) or not item["extractedText"].strip() for item in extracted)):
        raise ValueError(f"Missing or invalid extracted licensing text: {name}")
    # When a declaration describes an exact notice, verify the standard SPDX
    # file checksums against the actual installed copyright.
    if package["licenseDeclared"] != "NOASSERTION" and not document.get("files"):
        raise ValueError(f"Correction requires exact copyright evidence: {name}")
    for file in document.get("files", []):
        if file.get("fileName") != "./copyright":
            raise ValueError(f"Unsupported supplemental SPDX evidence file: {name}")
        hashes = {item["algorithm"]:item["checksumValue"] for item in file["checksums"]}
        if hashes.get("SHA256") != _sha256(copyright_data):
            return None
    return document


@dataclass
class InstalledPort:
    name: str
    triplet: str
    version: str = ""
    revision: int = 0
    abi: str = ""
    dependencies: set[str] = field(default_factory=set)
    features: set[str] = field(default_factory=set)
    dependency_keys: set[tuple[str, str]] = field(default_factory=set)


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


def _dependency_keys(raw: str, triplet: str) -> set[tuple[str, str]]:
    """vcpkg serializes same-triplet dependencies as name, others as name:triplet."""
    result = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        match = re.fullmatch(r"([a-z0-9][a-z0-9+.-]*)(?::([a-z0-9][a-z0-9-]*))?", item)
        if not match:
            raise ValueError(f"Invalid vcpkg status dependency: {item}")
        result.add((match[1], match[2] or triplet))
    return result


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
        edges = _dependency_keys(row.get("Depends", ""), triplet)
        port.dependency_keys.update(edges)
        port.dependencies.update(name for name, _ in edges)
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
        for dependency in port.dependency_keys:
            if dependency not in ports:
                raise ValueError(f"Referenced dependency not installed: {dependency[0]}:{dependency[1]}")
            stack.append(dependency)
    return sorted(selected.values(), key=lambda x: (x.name, x.triplet))


def declared_root_hosts(job: dict) -> set[str]:
    """Explicit root host flags from the version-specific generated recipe."""
    version = str(job["version"]).split("-", 1)[0]
    spec = resolve_features(config(job["yaml"]), version)
    dependencies = list(spec.host_packages)
    for feature in job["features"]:
        dependencies.extend(spec.packages.get(feature, ()))
    host, target = set(), set()
    for entry in dependencies:
        if isinstance(entry, dict) and entry.get("host") is True:
            host.add(entry["name"])
        else:
            target.add(entry if isinstance(entry, str) else entry["name"])
    return host - target


def manifest_sha256(spdx: dict) -> str | None:
    """Get the native recipe manifest hash, never a source-resource hash."""
    refs = {r["spdxElementId"] for r in spdx.get("relationships", [])
            if r.get("relationshipType") == "DEPENDENCY_MANIFEST_OF"
            and r.get("relatedSpdxElement") == "SPDXRef-port"}
    hashes = {c["checksumValue"] for file in spdx.get("files", [])
              if file.get("SPDXID") in refs and file.get("fileName") == "./vcpkg.json"
              for c in file.get("checksums", []) if c.get("algorithm") == "SHA256"}
    if len(hashes) == 1:
        digest = next(iter(hashes))
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            return digest
    return None


def verified_manifest_hosts(raw: bytes, spdx: dict, name: str,
                            features: set[str]) -> set[str]:
    if manifest_sha256(spdx) != _sha256(raw):
        raise ValueError(f"Port manifest hash differs from original SPDX: {name}")
    document = json.loads(raw)
    if document.get("name") != name:
        raise ValueError(f"Port manifest identity differs: {name}")
    deps = list(document.get("dependencies", []))
    for feature in features:
        deps.extend(document.get("features", {}).get(feature, {}).get("dependencies", []))
    hosts, targets = set(), set()
    for entry in deps:
        if isinstance(entry, dict) and entry.get("host") is True:
            hosts.add(entry["name"])
        else:
            targets.add(entry if isinstance(entry, str) else entry["name"])
    # Platform conditions can remove edges, but must never convert an
    # unverified target edge to a host edge.
    return hosts - targets


def verified_role_manifests(installed_root: Path, selected: list[InstalledPort],
                            job: dict, documents: dict[tuple[str, str], dict]) -> dict[str, str]:
    """Find only exact recipe manifests; retain bytes only when needed for role proof."""
    wanted = {}
    for port in selected:
        key = (port.name, port.triplet)
        if digest := manifest_sha256(documents[key]):
            wanted.setdefault(digest, []).append(port)
    if not wanted:
        return {}

    candidates = set()
    for port in selected:
        candidates.add(ROOT / "ports" / port.name / "vcpkg.json")
        candidates.add(installed_root.parent / "ports" / port.name / "vcpkg.json")
        if os.environ.get("VCPKG_ROOT"):
            candidates.add(Path(os.environ["VCPKG_ROOT"]) / "ports" / port.name / "vcpkg.json")
    candidates.add(GENERATED_PORTS / ffmpeg_port_name(job["yaml"]) / "vcpkg.json")
    cache_roots = []
    if os.environ.get("X_VCPKG_REGISTRIES_CACHE"):
        cache_roots.append(Path(os.environ["X_VCPKG_REGISTRIES_CACHE"]))
    if os.environ.get("LOCALAPPDATA"):
        cache_roots.append(Path(os.environ["LOCALAPPDATA"]) / "vcpkg/registries")
    if os.environ.get("XDG_CACHE_HOME"):
        cache_roots.append(Path(os.environ["XDG_CACHE_HOME"]) / "vcpkg/registries")
    cache_roots.append(Path.home() / ".cache/vcpkg/registries")
    for root in cache_roots:
        candidates.update(root.glob("git-trees/*/vcpkg.json"))
    result = {}
    for path in sorted(candidates):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = _sha256(raw)
        if digest not in wanted:
            continue
        for port in wanted.pop(digest):
            key = (port.name, port.triplet)
            hosts = verified_manifest_hosts(raw, documents[key], port.name, port.features)
            if any(name in hosts and arch == "x64-windows" for name, arch in port.dependency_keys):
                result[":".join(key)] = base64.b64encode(raw).decode("ascii")
        if not wanted:
            break
    return result


def manifest_host_edges(encoded: dict[str, str], documents: dict[tuple[str, str], dict],
                        features: dict[tuple[str, str], set[str]]) -> dict[tuple[str, str], set[str]]:
    result = {}
    for package, content in encoded.items():
        key = tuple(package.split(":", 1))
        if key not in documents or key not in features:
            raise ValueError(f"Unknown recipe role evidence: {package}")
        raw = base64.b64decode(content, validate=True)
        result[key] = verified_manifest_hosts(raw, documents[key], key[0], features[key])
    return result


def dependency_scopes(edges: dict[tuple[str, str], set[tuple[str, str]]],
                      root: tuple[str, str], root_hosts: set[str],
                      host_edges: dict[tuple[str, str], set[str]] | None = None) -> dict[tuple[str, str], str]:
    """Propagate target/build roles; any target path dominates a host-only path.

    Different triplet edges are explicit in status. Same-triplet transitive
    edges require verified manifest host flags, or remain target candidates.
    """
    scopes = {}
    seen = set()
    stack = [(root, False)]
    while stack:
        key, build_only = stack.pop()
        if (key, build_only) in seen:
            continue
        seen.add((key, build_only))
        if key not in edges:
            raise ValueError(f"Missing dependency graph node: {key}")
        if not build_only or key not in scopes:
            scopes[key] = "build-only" if build_only else "target-candidate"
        for child in edges[key]:
            # CI host is x64-windows. Explicit cross-triplet host edges
            # are distinguishable; unexpected other cross edges are not.
            cross_host = child[1] != key[1] and child[1] == "x64-windows"
            manifest_hosts = (host_edges or {}).get(key, root_hosts if key == root else set())
            declared_host = child[1] == "x64-windows" and child[0] in manifest_hosts
            stack.append((child, build_only or cross_host or declared_host))
    return scopes


def _spdx_license(source: dict, name: str, *,
                  reviewed: tuple[str, str] | None = None) -> tuple[str, str]:
    """Read the license of the installed binary, not unrelated source resources.

    vcpkg emits SPDXRef-port and SPDXRef-binary with the manifest/feature
    expression in licenseConcluded and NOASSERTION in licenseDeclared.
    Resource packages appended by vcpkg are not independent installed Ports.
    Keep the original document for their separate evidence.
    """
    if not isinstance(source, dict) or not str(source.get("spdxVersion", "")).startswith("SPDX-2."):
        raise ValueError(f"Invalid SPDX document for {name}")
    packages = source.get("packages")
    if not isinstance(packages, list) or not packages or any(not isinstance(p, dict) for p in packages):
        raise ValueError(f"SPDX packages missing or invalid for {name}")
    port_name, _, _ = name.partition(":")
    binary = [p for p in packages if p.get("SPDXID") == "SPDXRef-binary"]
    recipe = [p for p in packages if p.get("SPDXID") == "SPDXRef-port"]
    if binary or recipe:
        if len(binary) != 1 or len(recipe) != 1:
            raise ValueError(f"Missing or ambiguous vcpkg SPDX primary packages for {name}")
        if binary[0].get("name") != name or recipe[0].get("name") != port_name:
            raise ValueError(f"vcpkg SPDX package identity differs for {name}")
        primary = binary + recipe
    else:
        # Older/non-native documents may have a single package record.
        primary = [p for p in packages if p.get("name") in (name, port_name)]
        if len(primary) != 1:
            raise ValueError(f"Missing or ambiguous SPDX package identity for {name}")

    def expression(row, field):
        value = row.get(field)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"Invalid SPDX {field} for {name}")
        value = value.strip()
        if value == "NONE":
            raise ValueError(f"Explicit SPDX NONE license assertion for {name}")
        if value in ("", "NOASSERTION"):
            return None
        if re.search(r"\bLicenseRef-vcpkg-null\b", value, re.IGNORECASE):
            raise ValueError(f"Unknown/NOASSERTION vcpkg license component for {name}")
        return value

    # Only replace a completely absent assertion. Never override a known
    # license or an expression containing an unknown component.
    empty = (None, "", "NOASSERTION", "LicenseRef-vcpkg-null")
    if reviewed and all(row.get(field) in empty
                        for row in primary for field in ("licenseConcluded", "licenseDeclared")):
        return reviewed[0], "local-declaration"

    effective = []
    for row in primary:
        concluded = expression(row, "licenseConcluded")
        declared = expression(row, "licenseDeclared")
        if concluded and declared and concluded != declared:
            raise ValueError(f"Conflicting SPDX license assertions for {name}: {concluded} vs {declared}")
        if not (concluded or declared):
            raise ValueError(f"Unknown/NOASSERTION SPDX license for {name}")
        effective.append((concluded or declared, "licenseConcluded" if concluded else "licenseDeclared"))
    if len({value for value, _ in effective}) != 1:
        raise ValueError(f"Conflicting vcpkg Port and binary license assertions for {name}")
    return effective[0]


# Exact vcpkg 2026.06.01 OpenGL Port recipe, which only copies Windows SDK
# import libraries/headers; it does not build an OpenGL implementation.
# Both newline encodings of the same reviewed recipe are supported.
_OPENGL_PORT_SHA256 = frozenset((
    "be1ddde13da8627b55b39b1a94aa14d69c87e191fadc1134cc2e9011a1ba6032",
    "fbfc6b55956aaf12781ce6e55b8cc5f62a42f63518bd3c94757f285f4b566f39",
))
_OPENGL_SDK_FILES = frozenset((
    "include/gl/gl.h", "include/gl/glu.h", "lib/opengl32.lib", "lib/glu32.lib",
    "debug/lib/opengl32.lib", "debug/lib/glu32.lib",
))
_OPENGL_SDK_BASENAMES = frozenset(("opengl32.lib", "glu32.lib", "opengl32.dll", "glu32.dll"))


def external_system_declaration(document: dict, name: str, version: str,
                                revision: int, copyright_data: bytes) -> dict | None:
    """Recognize only the reviewed external Windows SDK import Port.

    This is scope classification, not an SDK redistribution license.
    The original package remains NOASSERTION in the SBOM.
    """
    port, _, triplet = name.partition(":")
    if port != "opengl" or (version, revision) != ("2022-12-04", 3) or triplet not in (
            "x86-windows", "x64-windows", "arm-windows", "arm64-windows"):
        return None
    if copyright_data != b"See https://developer.microsoft.com/windows/downloads/windows-10-sdk for the Windows 10 SDK license.":
        return None
    # Identity and wholly missing original assertions still have to match.
    try:
        value, source = _spdx_license(document, name, reviewed=("NOASSERTION", "system"))
    except ValueError:
        return None
    if (value, source) != ("NOASSERTION", "local-declaration"):
        return None
    files = {entry.get("SPDXID"): entry for entry in document.get("files", [])}
    relationships = document.get("relationships", [])
    def owned_by(owner):
        return [files.get(r.get("relatedSpdxElement"), {}) for r in relationships
                if r.get("spdxElementId") == owner and r.get("relationshipType") == "CONTAINS"]
    recipe = [f for f in owned_by("SPDXRef-port") if f.get("fileName") == "./portfile.cmake"]
    if len(recipe) != 1 or not any(c.get("algorithm") == "SHA256" and c.get("checksumValue") in _OPENGL_PORT_SHA256
                                    for c in recipe[0].get("checksums", [])):
        return None
    # Native SPDX lists installed files. Exclude all executable or library
    # payload other than the known SDK imports; pkgconfig metadata is fine.
    owned = {f.get("fileName", "").removeprefix("./").lower() for f in owned_by("SPDXRef-binary")}
    if not {"include/gl/gl.h", "include/gl/glu.h", "lib/opengl32.lib", "lib/glu32.lib"} <= owned:
        return None
    allowed_metadata = {"control", "build_info", "share/opengl/copyright", "share/opengl/usage",
                        "share/opengl/vcpkg_abi_info.txt", "share/opengl/vcpkg.spdx.json"}
    if any(f not in _OPENGL_SDK_FILES and f not in allowed_metadata
           and not (f.endswith(".pc") and f.startswith(("lib/pkgconfig/", "debug/lib/pkgconfig/", "share/pkgconfig/")))
           for f in owned):
        return None
    declaration_path = LICENSE_DECLARATIONS / "opengl.spdx.json"
    if not declaration_path.is_file():
        return None
    declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    package = declaration["packages"][0]
    if (declaration.get("spdxVersion") != "SPDX-2.3" or package.get("name") != port
            or package.get("versionInfo") != "2022-12-04#3"
            or package.get("licenseDeclared") != "NOASSERTION"
            or package.get("licenseConcluded") != "NOASSERTION"):
        return None
    return declaration


def verify_system_archive_members(members, *, system_dependency: bool) -> None:
    """Never ship the SDK headers, import libraries or system DLLs themselves."""
    if not system_dependency:
        return
    for member in members:
        normalized = member.lower().replace("\\", "/")
        if (normalized.rsplit("/", 1)[-1] in _OPENGL_SDK_BASENAMES
                or normalized.endswith(("/gl/gl.h", "/gl/glu.h"))):
            raise ValueError(f"System SDK file must not be redistributed in FFmpeg archive: {member}")


def resolve_port_license(document: dict, name: str, version: str, revision: int,
                         copyright_data: bytes) -> tuple[str, str, dict | None]:
    # Native declarations win except for a reviewed correction explicitly
    # matching the original expression, version, and installed notice.
    try:
        expression, source = _spdx_license(document, name)
    except ValueError as error:
        if "Unknown/NOASSERTION" not in str(error):
            raise
        system = external_system_declaration(document, name, version, revision, copyright_data)
        if system is not None:
            return "NOASSERTION", "external-system", system
        declaration = supplemental_license(name.split(":", 1)[0], version, revision, copyright_data)
        if declaration is None or declaration["packages"][0]["licenseDeclared"] != "NOASSERTION":
            raise
        package = declaration["packages"][0]
        expression, source = _spdx_license(document, name, reviewed=(package["licenseConcluded"], package["sourceInfo"]))
        return expression, source, declaration
    # Only inspect a correction file for a known declared expression, not
    # for arbitrary package-name overrides or missing-only declarations.
    path = LICENSE_DECLARATIONS / f"{name.split(':', 1)[0]}.spdx.json"
    if path.is_file():
        local = json.loads(path.read_text(encoding="utf-8"))
        packages = local.get("packages", [])
        if (len(packages) == 1 and isinstance(packages[0].get("licenseDeclared"), str)
                and packages[0]["licenseDeclared"] not in ("NONE", "NOASSERTION")
                and same_expression(packages[0]["licenseDeclared"], expression)):
            declaration = supplemental_license(name.split(":", 1)[0], version, revision, copyright_data)
            if declaration is not None:
                return declaration["packages"][0]["licenseConcluded"], "local-correction", declaration
    return expression, source, None


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
        "upstream_ref": job.get("source_ref") or job.get("ref") or source.get("ref", f"n{job['version']}").replace(
            "${VERSION}", job["version"]),
        "source_sha512": job.get("sha512") or source.get("sha512", ""),
        "patches": files,
    }


def compliance_files(installed_root: Path, job: dict, *,
                     ffmpeg_copyright: Path,
                     source_tree: Path | None = None) -> tuple[dict[str, bytes], dict[str, bytes], dict]:
    """Return public license files, internal raw evidence and compliance summary.

    Exact installed target packages are discovered from vcpkg's status graph.
    Host tools, if reachable, are identified as such. This documents the
    resolved build dependency graph, not physical object-file attribution.
    """
    triplet = job["triplet"]
    selected = reachable_ports(installed_root, triplet)
    root_hosts = declared_root_hosts(job)
    original_documents = {}
    original_bytes = {}
    for port in selected:
        key = (port.name, port.triplet)
        spdx_file = installed_root / port.triplet / "share" / port.name / "vcpkg.spdx.json"
        if not spdx_file.is_file():
            raise ValueError(f"Missing vcpkg SPDX for {port.name}:{port.triplet}")
        raw = spdx_file.read_bytes()
        try:
            document = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Invalid vcpkg SPDX JSON for {port.name}:{port.triplet}") from exc
        if not isinstance(document, dict):
            raise ValueError(f"Invalid vcpkg SPDX document for {port.name}:{port.triplet}")
        original_documents[key] = document
        original_bytes[key] = raw
    role_manifests = verified_role_manifests(installed_root, selected, job, original_documents)
    host_edges = manifest_host_edges(role_manifests, original_documents,
                                     {(p.name, p.triplet): p.features for p in selected})
    scopes = dependency_scopes({(p.name, p.triplet): p.dependency_keys for p in selected},
                               ("ffmpeg", triplet), root_hosts, host_edges)
    if not ffmpeg_copyright.is_file():
        raise FileNotFoundError("Missing FFmpeg license text")
    main_expression, primary_license = _ffmpeg_license(
        ffmpeg_copyright.read_bytes(), job["license"])
    contents: dict[str, bytes] = {}
    summary: list[dict] = []
    failures = []
    for port in selected:
        key = (port.name, port.triplet)
        try:
            folder = installed_root / port.triplet / "share" / port.name
            copyright_file = ffmpeg_copyright if port.name == "ffmpeg" and port.triplet == triplet else folder / "copyright"
            if not copyright_file.is_file() or not copyright_file.stat().st_size:
                raise ValueError(f"Missing/nonempty copyright notice for {port.name}:{port.triplet}")
            copyright_data = copyright_file.read_bytes()
            contents[f"LICENSES/{port.name}-{port.triplet}/copyright"] = copyright_data
            original_spdx = original_bytes[key]
            parsed = original_documents[key]
            declaration = None
            if port.name == "ffmpeg":
                # The actual GNU terms selected at configure time override the
                # generated Port's generic license metadata.
                if not isinstance(parsed, dict) or not str(parsed.get("spdxVersion", "")).startswith("SPDX-2."):
                    raise ValueError("Invalid FFmpeg vcpkg SPDX document")
                declared, license_source = main_expression, "ffmpeg-copyright"
            else:
                declared, license_source, declaration = resolve_port_license(
                    parsed, f"{port.name}:{port.triplet}", port.version, port.revision, copyright_data)
            scope = "system-dependency" if license_source == "external-system" else scopes[key]
            decision = scoped_compatibility(declared, main_expression, f"{port.name}:{port.triplet}",
                name=port.name, version=port.version, port_revision=port.revision,
                copyright_sha256=_sha256(copyright_data), linkage=job["linkage"],
                build_only=scope == "build-only", system_dependency=scope == "system-dependency")
            contents[f"LICENSES/{port.name}-{port.triplet}/vcpkg.spdx.json"] = original_spdx
            summary.append({
                "name": port.name, "triplet": port.triplet,
                "version": port.version, "port_revision": port.revision,
                "abi": port.abi, "features": sorted(port.features),
                "license_expression": declared, "license_source": license_source,
                "license_declaration": declaration,
                "dependencies": sorted(port.dependencies),
                "scope": scope, "compatibility": decision,
                "dependency_keys": [f"{name}:{arch}" for name, arch in sorted(port.dependency_keys)],
                "copyright_sha256": _sha256(copyright_data),
                "original_spdx_sha256": _sha256(original_spdx),
            })
        except (ValueError, FileNotFoundError) as exc:
            failures.append(f"{port.name}:{port.triplet}: {exc}")
    if failures:
        raise ValueError(f"License compliance rejected {len(failures)} installed Ports:\n" +
                         "\n".join(failures))
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

    provenance = {
        "schema": 1,
        "variant_id": job["id"],
        "abi_hash": job.get("abi_hash"),
        "release_date": job.get("release_date"),
        "package_spec": job["package"],
        "triplet": triplet,
        "features": sorted(job["features"]),
        "source": _source_provenance(job),
        "ci_commit": os.environ.get("GITHUB_SHA"),
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "installed_packages": summary,
        "license_policy": POLICY_VERSION,
        "ffmpeg_license": main_expression,
        "declared_root_hosts": sorted(root_hosts),
        "verified_role_manifests": role_manifests,
        "dependency_evidence": "installed vcpkg status and per-package copyright/SPDX",
        "not_a_link_map": True,
    }
    contents["metadata/BUILD_PROVENANCE.json"] = _json(provenance)
    public = distribution_evidence(contents.__getitem__, provenance)
    return public, contents, {"package_count": len(summary), "license_policy": POLICY_VERSION,
                      "ffmpeg_license": main_expression,
                      "packages": [
                          {key: item[key] for key in (
                              "name", "triplet", "version", "port_revision",
                              "abi", "scope", "license_expression", "license_source", "compatibility")}
                          for item in summary
                      ],
                      "spdx_sha256": _sha256(public[PUBLIC_SPDX]),
                      "copyright_sha256": _sha256(public[PUBLIC_COPYRIGHT])}


PUBLIC_COPYRIGHT = "share/ffmpeg/copyright"
PUBLIC_SPDX = "share/ffmpeg/sbom.spdx.json"


def distribution_evidence(read: Callable[[str], bytes], provenance: dict) -> dict[str, bytes]:
    """Reproduce the two public files from unmodified audit evidence.

    No linked-object attribution is inferred. Keep all target-candidate
    notices, and omit only verified build-only/external system notices.
    Original SPDX documents remain in the internal audit archive.
    """
    installed = provenance["installed_packages"]
    root = ("ffmpeg", provenance["triplet"])
    ids = {(p["name"], p["triplet"]): f"SPDXRef-vcpkg-{i}"
           for i, p in enumerate(installed, 1)}
    if len(ids) != len(installed) or root not in ids:
        raise ValueError("Invalid installed package identities")
    by_key = {(p["name"], p["triplet"]): p for p in installed}
    main = read(f"LICENSES/ffmpeg-{root[1]}/copyright")
    _, primary = _ffmpeg_license(main, "lgpl" if provenance["ffmpeg_license"].startswith("LGPL-") else "gpl")
    sections = []
    def append(title, data):
        if not data:
            raise ValueError(f"Empty license text: {title}")
        # Delimit but never decode, trim, or rewrite original license bytes.
        sections.append(title.encode("utf-8") + b"\n" + b"=" * 64 + b"\n" + data + b"\n\n")
    append(f"FFmpeg {by_key[root]['version']}", main)
    required = [primary] + (["COPYING.GPLv3"] if primary == "COPYING.LGPLv3" else [])
    for name in required:
        raw = read(f"LICENSES/ffmpeg/upstream/{name}")
        if raw != main:
            append(f"FFmpeg upstream {name}", raw)
    packages = []
    extracted = {}
    relationships = [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES",
                      "relatedSpdxElement": ids[root]}]
    for key, p in by_key.items():
        base = f"LICENSES/{p['name']}-{p['triplet']}/"
        native = json.loads(read(base + "vcpkg.spdx.json"))
        binary = next((row for row in native.get("packages", []) if row.get("SPDXID") == "SPDXRef-binary"), {})
        if key != root and p["scope"] == "target-candidate":
            append(f"{p['name']} {p['version']}#{p['port_revision']} ({p['triplet']})", read(base + "copyright"))
        local = p.get("license_declaration")
        declared = p["license_expression"] if p["license_source"] == "licenseDeclared" else "NOASSERTION"
        if p["license_source"] == "local-correction":
            declared = local["packages"][0]["licenseDeclared"]
        concluded = p["license_expression"] if p["license_source"] != "licenseDeclared" else "NOASSERTION"
        references = set(re.findall(r"\bLicenseRef-[A-Za-z0-9.-]+", declared + " " + concluded))
        for reference in sorted(references):
            candidates = [item for doc in (local or {}, native)
                          for item in doc.get("hasExtractedLicensingInfos", [])
                          if item.get("licenseId") == reference]
            if not candidates or any(item != candidates[0] for item in candidates[1:]):
                raise ValueError(f"Missing or conflicting extracted license: {reference}")
            item = candidates[0]
            if reference in extracted and extracted[reference] != item:
                raise ValueError(f"Conflicting extracted license: {reference}")
            extracted[reference] = item
        packages.append({"SPDXID": ids[key], "name": p["name"],
                         "versionInfo": p["version"] + (f"#{p['port_revision']}" if p["port_revision"] else ""),
                         "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
                         "licenseDeclared": declared, "licenseConcluded": concluded,
                         "copyrightText": binary.get("copyrightText") or "NOASSERTION",
                         "comment": f"Triplet: {p['triplet']}; scope: {p['scope']}. Installed dependency graph, not a link map."})
        if key == root:
            source = provenance["source"]
            packages[-1]["sourceInfo"] = f"Upstream: {source['upstream_repository']} @ {source['upstream_ref']}"
        elif local and local["packages"][0].get("sourceInfo"):
            packages[-1]["sourceInfo"] = local["packages"][0]["sourceInfo"]
        for edge in sorted(p["dependency_keys"]):
            child = tuple(edge.split(":", 1))
            if child not in ids:
                raise ValueError(f"Missing installed dependency edge {key} -> {child}")
            if by_key[child]["scope"] == "build-only":
                relationships.append({"spdxElementId": ids[child], "relationshipType": "BUILD_DEPENDENCY_OF", "relatedSpdxElement": ids[key]})
            else:
                relationships.append({"spdxElementId": ids[key], "relationshipType": "DEPENDS_ON", "relatedSpdxElement": ids[child]})
    spdx = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"FFmpeg {by_key[root]['version']} ({root[1]})",
            "creationInfo": {"creators": ["Tool: ffbuild-compliance-3"], "created": provenance["created"]},
            "packages": packages, "relationships": relationships,
            "comment": "Installed vcpkg dependency graph, not a link map. Distributed license texts: share/ffmpeg/copyright. Build-only and external system dependencies are not distributed as separate packages."}
    if extracted:
        spdx["hasExtractedLicensingInfos"] = list(extracted.values())
    # Namespace changes if either the actual build identity or SBOM content changes.
    spdx["documentNamespace"] = "https://github.com/System233/ffmpeg-msvc-prebuilt/spdx/" + _sha256(
        _json({"variant": provenance["variant_id"], "date": provenance["release_date"], "document": spdx}))
    return {PUBLIC_COPYRIGHT: b"".join(sections), PUBLIC_SPDX: _json(spdx)}


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
