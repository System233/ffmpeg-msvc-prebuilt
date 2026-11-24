"""Minimal deterministic vcpkg install/status and upstream licensing fixtures."""
from __future__ import annotations

import json
from pathlib import Path


def make_compliance_fixture(root: Path, job: dict, copyright_file: Path) -> tuple[Path, Path]:
    triplet = job["triplet"]
    installed = root / "installed"
    status = installed / "vcpkg" / "status"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(
        f"Package: ffmpeg\nVersion: {job['version']}\n"
        f"Architecture: {triplet}\nDepends: zlib\n"
        "Status: install ok installed\n\n"
        f"Package: ffmpeg\nFeature: base\nArchitecture: {triplet}\n"
        "Status: install ok installed\n\n"
        f"Package: zlib\nVersion: 1.3.2\nArchitecture: {triplet}\n"
        "Abi: " + "a" * 64 + "\nStatus: install ok installed\n\n"
        f"Package: ffmpeg-tester\nVersion: 1.0\nArchitecture: {triplet}\n"
        "Depends: ffmpeg\nStatus: install ok installed\n\n"
        f"Package: extraneous\nVersion: 1.0\nArchitecture: {triplet}\n"
        "Status: install ok installed\n", encoding="utf-8",
    )
    for port, expression in (("ffmpeg", "NOASSERTION"), ("zlib", "Zlib")):
        folder = installed / triplet / "share" / port
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "copyright").write_bytes(
            copyright_file.read_bytes() if port == "ffmpeg" else b"zlib license text")
        (folder / "vcpkg.spdx.json").write_text(json.dumps({
            "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": f"vcpkg {port}",
            "packages": [
                {"name": port, "SPDXID": "SPDXRef-port",
                 "licenseDeclared": "NOASSERTION", "licenseConcluded": expression},
                {"name": f"{port}:{triplet}", "SPDXID": "SPDXRef-binary",
                 "licenseDeclared": "NOASSERTION", "licenseConcluded": expression},
                {"name": "upstream-source", "SPDXID": "SPDXRef-resource-0",
                 "licenseDeclared": "NOASSERTION", "licenseConcluded": "NOASSERTION"},
            ],
        }), encoding="utf-8")
    upstream = root / "buildtrees" / "ffmpeg" / "src" / "source"
    upstream.mkdir(parents=True, exist_ok=True)
    (upstream / "configure").write_text("# script", encoding="utf-8")
    for name in ("COPYING.LGPLv2.1", "COPYING.LGPLv3", "COPYING.GPLv2", "COPYING.GPLv3"):
        (upstream / name).write_text(f"upstream {name}\n", encoding="utf-8")
    return installed, upstream
