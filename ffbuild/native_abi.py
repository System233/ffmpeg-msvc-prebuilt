"""Read vcpkg's own dependency ABI graph without installing or building ports.

Pinned vcpkg 2026.06.01 supports `install --dry-run` together with the
experimental `--x-write-nuget-packages-config`.  NuGet's vcpkg-suffixed
package version contains the *native* package ABI, including dependency ABIs.
No second dependency hash algorithm is implemented here. vcpkg still runs
compiler-detection CMake probes during this dry run, which can compile tiny
compiler identification programs without compiling an actual package.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ffvcpkg import executable

from .identity import variant_name
from .port import ffmpeg_port_name
from .targets import Target, compile_target, load_targets
from .versions import GENERATED_PORTS, ROOT, config, has_source, latest_per_family, revision, versions


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


def native_abi_query(packages: list[str], triplet: str, *,
                     overlay: Path = GENERATED_PORTS,
                     binary: Path | None = None) -> dict[str, str]:
    """Scan a set of different Port names in one clean, read-only vcpkg plan."""
    if not packages:
        return {}
    if len(packages) != len(set(packages)):
        raise ValueError("Duplicate package specifications in vcpkg ABI query")
    tool = (binary or executable()).resolve()
    if not tool.is_file():
        raise FileNotFoundError(tool)
    if not overlay.is_dir():
        raise FileNotFoundError(f"Generate FFmpeg ports before scanning: {overlay}")
    with tempfile.TemporaryDirectory(prefix="ffbuild-native-abi-") as scratch:
        base = Path(scratch)
        output = base / "packages.config"
        args = [str(tool), "install", *packages, f"--triplet={triplet}",
                f"--overlay-ports={overlay.resolve()}",
                f"--overlay-ports={(ROOT / 'ports').resolve()}",
                f"--overlay-triplets={(ROOT / 'triplets').resolve()}",
                f"--x-install-root={base / 'installed'}", "--dry-run",
                f"--x-write-nuget-packages-config={output}", "--no-print-usage"]
        finished = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        if finished.returncode != 0:
            raise RuntimeError(f"Native vcpkg ABI query failed for {triplet}: "
                               f"{(finished.stderr + finished.stdout)[-4500:]}")
        if not output.is_file():
            raise RuntimeError("Pinned vcpkg did not emit NuGet ABI information")
        return read_nuget_abis(output)


def build_requests(*, version: str = "", history: bool = False,
                   targets: tuple[Target, ...] | None = None,
                   snapshot: dict[str, str] | None = None,
                   selected_versions: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Expand existing declarative targets onto each independently named Port."""
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
    requests: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for name in candidates:
        if name != "master" and not has_source(name):
            raise ValueError(f"FFmpeg {name} is a YAML template without a source checksum")
        release = snapshot["ref"].removeprefix("n") if name == "master" else name
        source_ref = snapshot["commit"] if name == "master" else ""
        source_sha512 = snapshot["sha512"] if name == "master" else ""
        port = ffmpeg_port_name(name)
        for target in targets:
            try:
                native_spec = Target(f"{port}[{','.join(target.roots)}]", target.triplet,
                                     target.roots)
                resolved = compile_target(config(name),
                                          name if name != "master" else release.split("-", 1)[0],
                                          native_spec)
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
                "sha512": source_sha512, "revision": revision(name),
                "port": port, "tester_port": port.replace("ffmpeg-", "ffmpeg-tester-", 1),
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
                     binary: Path | None = None) -> list[dict]:
    """Resolve each build variant in a separate vcpkg dependency graph.

    Even different FFmpeg Port names can pull different Features of the SAME
    transitive dependency. Scanning them together would merge dependency
    Features and could produce ABIs that differ from isolated builds.
    """
    results: list[dict] = []
    for request in requests:
        triplet = request["triplet"]
        all_abis = native_abi_query([request["package"]], triplet,
                                    overlay=overlay, binary=binary)
        key = f"{request['port']}_{triplet}"
        if key not in all_abis:
            raise RuntimeError(f"Native vcpkg ABI missing for {key}; refusing to invent one")
        abi = all_abis[key]
        result = dict(request)
        result["abi_hash"] = abi
        result["id"] = variant_name(request["version"], request["revision"],
                                    triplet, request["linkage"], request["license"],
                                    abi_hash=abi)
        results.append(result)
    return sorted(results, key=lambda record: (record["yaml"], record["triplet"], record["package"]))


def verify_job_abi(job: dict, *, overlay: Path = GENERATED_PORTS,
                   binary: Path | None = None) -> str:
    """Fail before installing if worker-resolved native ABI differs from plan."""
    abis = native_abi_query([job["package"]], job["triplet"],
                            overlay=overlay, binary=binary)
    actual = abis.get(f"{job['port']}_{job['triplet']}")
    if actual != job["abi_hash"]:
        raise ValueError(f"vcpkg ABI changed between planning and building: "
                         f"planned {job['abi_hash']}, current {actual}")
    return actual
