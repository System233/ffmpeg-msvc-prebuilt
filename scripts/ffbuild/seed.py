"""Prebuild shared vcpkg dependencies once per Triplet for the CI workers.

The seed is a virtual vcpkg Port generated from the full version matrix.
Each incompatible dependency alternative is installed in an isolated root,
while all results are written to one native vcpkg binary cache. ABI matching,
cache reuse and transitive dependency resolution remain vcpkg's responsibility.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ffvcpkg import command as vcpkg_command

from .versions import GENERATED_PORTS, ROOT, TRIPLETS


def seed_profiles(overlay: Path = GENERATED_PORTS) -> tuple[str, ...]:
    manifest_path = overlay / "ffmpeg-deps" / "vcpkg.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Generate FFmpeg dependency Seed first: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != "ffmpeg-deps":
        raise ValueError("Invalid generated FFmpeg dependency Seed manifest")
    features = manifest.get("features", {})
    if not isinstance(features, dict) or "all" not in features:
        raise ValueError("FFmpeg dependency Seed requires an all feature")
    return ("all",) + tuple(sorted(feature for feature in features if feature != "all"))


def prepare_seed(*, triplet: str, overlay: Path = GENERATED_PORTS,
                 binary: Path | None = None, install_root: Path | None = None,
                 only_downloads: bool = False) -> tuple[str, ...]:
    """Populate VCPKG_BINARY_SOURCES without building FFmpeg itself.

    Each feature is a separate vcpkg invocation and installation root, so
    conflicting version-specific alternatives cannot merge their Features.
    Never remove or overwrite the shared binary cache during preparation.
    """
    if triplet not in TRIPLETS:
        raise ValueError(f"Unsupported FFmpeg Triplet: {triplet}")
    profiles = seed_profiles(overlay)
    root = install_root or Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "ffbuild-seed-roots"
    root.mkdir(parents=True, exist_ok=True)
    for index, profile in enumerate(profiles):
        # The original CI used one clean install tree for each alternative;
        # keeping the same isolation also avoids accidentally unioning Features.
        with tempfile.TemporaryDirectory(prefix=f"seed-{index}-", dir=root) as temporary:
            arguments = ["install", f"ffmpeg-deps[{profile}]", f"--triplet={triplet}",
                         "--recurse", f"--x-install-root={temporary}",
                         f"--overlay-ports={(overlay / 'ffmpeg-deps').resolve()}",
                         f"--overlay-ports={(ROOT / 'ports').resolve()}",
                         f"--overlay-triplets={(ROOT / 'triplets').resolve()}",
                         "--no-print-usage"]
            if only_downloads:
                arguments.append("--only-downloads")
            else:
                # Do not use --clean-after-build: it ALSO deletes the shared
                # downloads directory and defeats the source-download cache.
                arguments.extend(("--clean-buildtrees-after-build",
                                  "--clean-packages-after-build"))
            print(f"vcpkg Seed {triplet}: {profile} ({index + 1}/{len(profiles)})", flush=True)
            subprocess.run(vcpkg_command(arguments, binary=binary), cwd=ROOT, check=True)
    return profiles
