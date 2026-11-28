"""Read vcpkg's own ABI graph for a single selected FFmpeg version Port.

The pinned vcpkg tool supports `install --dry-run` together with the
experimental `--x-write-nuget-packages-config`.  NuGet's vcpkg-suffixed
package version contains the *native* package ABI, including dependency ABIs.
No second dependency hash algorithm is implemented here. vcpkg still runs
compiler-detection CMake probes during this dry run, which can compile tiny
compiler identification programs without compiling an actual package.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ffvcpkg import executable, command as vcpkg_command, environment

from .identity import variant_name, utc_release_date
from .port import ffmpeg_port_name
from .targets import Target, compile_target, load_targets
from .versions import GENERATED_PORTS, ROOT, config, has_source, latest_per_family, versions


_ABI_SUFFIX = re.compile(r"-vcpkg([0-9a-f]{64})$")


def read_nuget_abis(path: Path) -> dict[str, str]:
    """Return vcpkg ABI hashes by NuGet package ID; reject missing/ambiguous ABI."""
    result: dict[str, str] = {}
    for package in ET.parse(path).getroot().findall("package"):
        identifier = package.get("id", "")
        match = _ABI_SUFFIX.search(package.get("version", ""))
        if not identifier or not match or identifier in result:
            raise ValueError(f"Missing or duplicate vcpkg ABI in {path}: {identifier}")
        result[identifier] = match.group(1)
    if not result:
        raise ValueError(f"vcpkg did not emit any native ABI hashes: {path}")
    return result


_PLAN_SPEC = re.compile(r"^\s*(?:\*\s+)?([a-z0-9][a-z0-9-]*)(?:\[([a-z0-9,-]+)\])?:([a-z0-9-]+)@[^\s]+(?:\s.*)?$")


def planned_specs(transcript: str) -> dict[str, str]:
    """Read the pinned native classic install plan, not dependency metadata guesses."""
    result = {}
    active = False
    for line in transcript.splitlines():
        if line == "The following packages will be built and installed:":
            active = True
            continue
        if active and not line.startswith((" ", "\t")):
            active = False
        if not active:
            continue
        match = _PLAN_SPEC.fullmatch(line)
        if not match:
            raise ValueError("Unrecognized native vcpkg installation plan row")
        name, features, triplet = match.groups()
        roots = sorted({"core", *((features or "").split(",") if features else [])})
        key = f"{name}_{triplet}"
        if key in result:
            raise ValueError("Duplicate native vcpkg installation plan row")
        result[key] = f"{name}[{','.join(roots)}]:{triplet}"
    if not result:
        raise ValueError("Missing native vcpkg installation plan")
    return result


def native_abi_query(packages: list[str], triplet: str, *,
                     port_overlay: Path | None = None,
                     binary: Path | None = None,
                     env: dict[str, str] | None = None, specs: dict[str, str] | None = None,
                     evidence: Path | None = None) -> dict[str, str]:
    """Scan one dependency graph using one explicitly selected FFmpeg Port.

    Never supply the generated-ports parent: multiple version directories all
    define the same vcpkg package name, and only one may be visible per graph.
    """
    if not packages:
        return {}
    if len(packages) != len(set(packages)):
        raise ValueError("Duplicate package specifications in vcpkg ABI query")
    env = environment(env)
    tool = (binary or executable(env)).resolve()
    if not tool.is_file():
        raise FileNotFoundError(tool)
    overlays = []
    if port_overlay is not None:
        manifest = port_overlay / "vcpkg.json"
        if not manifest.is_file():
            raise FileNotFoundError(f"Select a generated FFmpeg Port directory: {manifest}")
        if json.loads(manifest.read_text(encoding="utf-8")).get("name") != "ffmpeg":
            raise ValueError(f"Expected stable ffmpeg package in {manifest}")
        overlays.append(f"--overlay-ports={port_overlay.resolve()}")
    elif any(p.split("[", 1)[0].split(":", 1)[0] in {"ffmpeg", "ffmpeg-tester"}
             for p in packages):
        raise ValueError("Direct dependency ABI queries cannot request FFmpeg target packages")
    with tempfile.TemporaryDirectory(prefix="ffbuild-native-abi-") as scratch:
        base = Path(scratch)
        output = base / "packages.config"
        args = ["install", *packages, f"--triplet={triplet}",
                *overlays,
                f"--overlay-ports={(ROOT / 'ports').resolve()}",
                f"--overlay-triplets={(ROOT / 'triplets').resolve()}",
                f"--x-install-root={base / 'installed'}", "--dry-run",
                f"--x-write-nuget-packages-config={output}", "--no-print-usage"]
        # Keep compiler detection cached in vcpkg's normal buildtrees. ABI
        # files are checked against the exact native hashes before copying.
        finished = subprocess.run(vcpkg_command(args, binary=tool, env=env), cwd=ROOT,
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", env=env)
        if finished.returncode != 0:
            raise RuntimeError(f"Native vcpkg ABI query failed for {triplet}: "
                               f"{(finished.stderr + finished.stdout)[-4500:]}")
        if not output.is_file():
            raise RuntimeError("Pinned vcpkg did not emit NuGet ABI information")
        abis = read_nuget_abis(output)
        if specs is not None:
            selected = planned_specs(finished.stdout)
            if set(selected) != set(abis):
                raise ValueError("Native vcpkg plan and ABI graph differ")
            specs.update(selected)
        if evidence is not None:
            collect_abi_evidence(abis, tool.parent / "buildtrees", evidence)
        return abis


def graph_digest(graph: dict) -> str:
    """Checksum a native graph for equality checks, never a substitute for package ABI."""
    return hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def collect_abi_evidence(abis: dict[str, str], buildtrees: Path, destination: Path) -> None:
    """Retain every native ABI input file, verifying its SHA256 before use."""
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "graph.json").unlink(missing_ok=True)
    for identifier, abi in sorted(abis.items()):
        port, triplet = abi_identifier(identifier)
        source = buildtrees / port / (triplet + ".vcpkg_abi_info.txt")
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != abi:
            raise RuntimeError(f"Native ABI input file differs from emitted ABI: {identifier}")
        (destination / (identifier + ".txt")).write_bytes(content)
    (destination / "graph.json").write_text(json.dumps(abis, sort_keys=True, indent=2) + "\n",
                                            encoding="utf-8")


def abi_identifier(value: str) -> tuple[str, str]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*_[a-z0-9][a-z0-9-]*", value):
        raise ValueError("Invalid native package ABI identity")
    return tuple(value.rsplit("_", 1))


def load_abi_evidence(directory: Path) -> tuple[dict, dict]:
    graph = json.loads((directory / "graph.json").read_text(encoding="utf-8"))
    if not isinstance(graph, dict) or not graph:
        raise ValueError("Invalid or empty native ABI graph")
    entries = {}
    for identifier, digest in graph.items():
        abi_identifier(identifier)
        content = (directory / (identifier + ".txt")).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Native ABI evidence hash mismatch: {identifier}")
        components: dict[str, list[str]] = {}
        for line in content.decode("utf-8").splitlines():
            key, value = line.split(" ", 1)
            components.setdefault(key, []).append(value)
        entries[identifier] = components
    return graph, entries


def compare_abi_evidence(before: Path, after: Path) -> dict:
    """Compare all recorded vcpkg ABI entries, including transitive packages."""
    left, left_entries = load_abi_evidence(before)
    right, right_entries = load_abi_evidence(after)
    changed = {}
    for package in sorted(left.keys() & right.keys()):
        if left[package] == right[package]:
            continue
        old, new = left_entries[package], right_entries[package]
        changed[package] = {
            "before": left[package], "after": right[package],
            "entries": {key: {"before": old.get(key), "after": new.get(key)}
                        for key in sorted(old.keys() | new.keys())
                        if old.get(key) != new.get(key)},
        }
    return {"added": {key: right[key] for key in sorted(right.keys() - left.keys())},
            "removed": {key: left[key] for key in sorted(left.keys() - right.keys())},
            "changed": changed,
            "unchanged": sum(left[key] == right[key] for key in left.keys() & right.keys())}


def build_requests(*, version: str = "", history: bool = False,
                   targets: tuple[Target, ...] | None = None,
                   snapshot: dict[str, str] | None = None,
                   selected_versions: list[str] | None = None, release_date: str | None = None) -> tuple[list[dict], list[dict]]:
    """Expand vcpkg ffmpeg[...] targets across version-selected Port directories."""
    targets = targets if targets is not None else load_targets()
    if selected_versions is not None and version:
        raise ValueError("Cannot combine selected versions with one explicit version")
    candidates = (list(selected_versions) if selected_versions is not None else
                  ([version] if version else [v for v in versions() if has_source(v)]))
    if not version and not history and selected_versions is None:
        candidates = latest_per_family(candidates)
    if "master" in candidates and snapshot is None:
        from .master import master_metadata
        snapshot = master_metadata()
    release_date = release_date or utc_release_date()
    from .identity import date_suffix
    date_suffix(release_date)
    requests: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for name in candidates:
        if name != "master" and not has_source(name):
            raise ValueError(f"FFmpeg {name} is a YAML template without a source checksum")
        release = snapshot["ref"].removeprefix("n") if name == "master" else name
        source_ref = snapshot["commit"] if name == "master" else ""
        source_sha512 = snapshot["sha512"] if name == "master" else ""
        port = "ffmpeg"
        for target in targets:
            try:
                resolved = compile_target(config(name),
                                          name if name != "master" else release.split("-", 1)[0],
                                          target)
                if resolved["license"] == "nonfree":
                    raise ValueError("Nonfree artifacts must not be published")
            except (KeyError, ValueError) as error:
                blocked.append({"yaml": name, "triplet": target.triplet,
                                "package": f"{port}[{','.join(target.roots)}]",
                                "errors": [str(error)]})
                continue
            requests.append({
                "yaml": name, "version": release, "source_version": release,
                "source_ref": source_ref, "ref": snapshot["ref"] if name == "master" else "",
                "sha512": source_sha512, "release_date": release_date,
                "port": port, "tester_port": "ffmpeg-tester",
                "triplet": target.triplet, "package": resolved["package"],
                "features": resolved["features"],
                "license": resolved["license"], "linkage": resolved["linkage"],
                "requested_features": sorted(target.roots),
            })
    for item in requests:
        item["expected_variants"] = sum(1 for other in requests
                                         if other["yaml"] == item["yaml"])
    return requests, blocked


def scan_native_abis(requests: list[dict], *, overlay: Path = GENERATED_PORTS,
                     binary: Path | None = None, evidence: Path | None = None,
                     dependency_batches: dict | None = None) -> list[dict]:
    """Resolve each variant with its corresponding version-directory overlay.

    Every query uses one ffmpeg identity and one selected recipe. Never combine
    versions or feature profiles into the same vcpkg dependency graph.
    """
    results: list[dict] = []
    for request in requests:
        triplet = request["triplet"]
        specs = {} if dependency_batches is not None else None
        all_abis = native_abi_query([request["package"], request["tester_port"]], triplet,
                                    port_overlay=overlay / ffmpeg_port_name(request["yaml"]),
                                    binary=binary, specs=specs, evidence=(evidence / request["yaml"] /
                                        triplet / (request["license"] + "-" + request["linkage"]))
                                    if evidence is not None else None)
        key = f"{request['port']}_{triplet}"
        if not {key, f"{request['tester_port']}_{triplet}"}.issubset(all_abis):
            raise RuntimeError(f"Native vcpkg ABI missing FFmpeg or Tester for {triplet}")
        if dependency_batches is not None:
            from .seed import external_batch
            dependency_batches[(request["yaml"], triplet, request["package"])] = external_batch(
                all_abis, specs, triplet)
        abi = all_abis[key]
        result = dict(request)
        result["abi_hash"] = abi
        result["native_graph_sha256"] = graph_digest(all_abis)
        result["id"] = variant_name(request["version"], 0,
                                    triplet, request["linkage"], request["license"],
                                    abi_hash=abi)
        results.append(result)
    return sorted(results, key=lambda record: (record["yaml"], record["triplet"], record["package"]))


def verify_job_abi(job: dict, *, overlay: Path = GENERATED_PORTS,
                   binary: Path | None = None, evidence: Path | None = None) -> str:
    """Fail before installing if worker-resolved native ABI differs from plan."""
    require_planned_abi(job)
    abis = native_abi_query([job["package"], job["tester_port"]], job["triplet"],
                            port_overlay=overlay / ffmpeg_port_name(job["yaml"]),
                            binary=binary, evidence=evidence)
    actual = abis.get(f"{job['port']}_{job['triplet']}")
    if actual != job["abi_hash"]:
        raise ValueError(f"vcpkg ABI changed between planning and building: "
                         f"planned {job['abi_hash']}, current {actual}")
    verify_graph_digest(job["native_graph_sha256"], abis)
    return actual



def require_planned_abi(job: dict) -> None:
    for field in ("abi_hash", "native_graph_sha256"):
        value = job.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"Missing or invalid planned {field}")

def verify_graph_digest(expected: str, abis: dict[str, str]) -> None:
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Missing or invalid planned native graph SHA256")
    actual = graph_digest(abis)
    if actual != expected:
        raise ValueError(f"vcpkg ABI graph changed between planning and building: "
                         f"planned {expected}, current {actual}")
