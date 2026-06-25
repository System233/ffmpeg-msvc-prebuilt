#!/usr/bin/env python3
"""Compute a deterministic SHA-256 hash over all files in the ports/ directory.

Walks recursively through *ports_dir*, concatenating the relative path
(UTF-8 bytes) + raw file content for every file, then hashes the
combined byte stream.  The resulting hex digest is used as a cache key
in CI to skip port-generation steps when nothing changed.

Usage::

    python scripts/ci/compute_port_hash.py
    python scripts/ci/compute_port_hash.py --ports-dir some/other/dir
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Sequence


def compute_port_hash(ports_dir: Path) -> str:
    """Return uppercase SHA-256 hex digest of all files under *ports_dir*."""
    sha = hashlib.sha256()

    for file_path in sorted(ports_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(ports_dir)
        sha.update(str(rel).replace("\\", "/").encode("utf-8"))
        sha.update(file_path.read_bytes())

    return sha.hexdigest().upper()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute a SHA-256 hash over all files in the ports directory.",
    )
    parser.add_argument(
        "--ports-dir",
        type=Path,
        default=Path("ports"),
        help="Directory to hash (default: ports/)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    ports_dir: Path = args.ports_dir

    if not ports_dir.is_dir():
        print(f"error: not a directory: {ports_dir}", file=sys.stderr)
        raise SystemExit(1)

    digest = compute_port_hash(ports_dir)
    print(digest)


if __name__ == "__main__":
    main()
