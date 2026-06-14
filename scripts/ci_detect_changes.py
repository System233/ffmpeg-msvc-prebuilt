#!/usr/bin/env python3
"""
Detect changed FFmpeg port directories and determine which versions to rebuild.

Groups changed versions by major family (e.g. 8.x, 7.x) and outputs only
the latest patch version per family, avoiding redundant builds.

Usage:
    python scripts/ci_detect_changes.py <before_sha> <after_sha>

Output:
    Prints "VERSION PORT_NAME" lines, one per version to build.
    Example:
        8.1.1 ffmpeg-8-1-1
        7.1.2 ffmpeg-7-1-2
"""

import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PORTS_DIR = REPO_ROOT / "ports"


def version_key(v: str):
    """Sortable version tuple for comparison."""
    return tuple(int(x) for x in v.split('.'))


def scan_ports_for_versions():
    """Scan all existing port directories and return known versions.
    
    Returns a dict mapping version string (e.g. '8.1.1') to port base name
    (e.g. 'ffmpeg-8-1-1'), for all ports that currently exist on disk.
    """
    known = {}
    for d in sorted(PORTS_DIR.iterdir()):
        if not d.is_dir() or not d.name.startswith('ffmpeg-'):
            continue
        # ffmpeg-8-1-1-static or ffmpeg-8-1-shared
        m = re.match(r'ffmpeg-(\d+-\d+(?:-\d+)?)-(?:static|shared)', d.name)
        if m:
            base = m.group(1)      # e.g. '8-1-1' or '8-1'
            ver = base.replace('-', '.')
            known[ver] = f'ffmpeg-{base}'
    return known


def get_changed_versions(before: str, after: str):
    """Return sorted list of version strings whose port files changed."""
    result = subprocess.run(
        ['git', 'diff', '--name-only', before, after, '--', 'ports/ffmpeg-*/'],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    versions = set()
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        m = re.match(r'ports/ffmpeg-(\d+)-(\d+)(?:-(\d+))?-(?:static|shared)/', line)
        if m:
            major, minor, patch = m.groups()
            ver = f'{major}.{minor}.{patch}' if patch else f'{major}.{minor}'
            versions.add(ver)
    return sorted(versions, key=version_key)


def pick_latest_per_family(versions):
    """Group by major version, keep only the latest patch per family."""
    families = {}
    for v in versions:
        major = v.split('.')[0]
        if major not in families or version_key(v) > version_key(families[major]):
            families[major] = v
    # Also consult filesystem: if a newer patch port exists on disk, prefer it
    known = scan_ports_for_versions()
    for major, v in families.items():
        # Find the latest patch in this family that exists as a port directory
        latest_in_family = v
        for kver in known:
            if kver.startswith(major + '.') and version_key(kver) > version_key(latest_in_family):
                latest_in_family = kver
        families[major] = latest_in_family
    return sorted(families.values(), key=version_key)


def main():
    if len(sys.argv) != 3:
        print('Usage: ci_detect_changes.py <before_sha> <after_sha>', file=sys.stderr)
        sys.exit(1)

    before, after = sys.argv[1], sys.argv[2]

    # Skip if this is the first push (before is all zeros)
    if before == '0000000000000000000000000000000000000000':
        print('No previous commit to diff against (initial push)')
        return

    changed = get_changed_versions(before, after)
    if not changed:
        print('No port changes detected.')
        return

    print(f'Changed versions: {", ".join(changed)}')
    to_build = pick_latest_per_family(changed)
    print(f'Building latest per family: {", ".join(to_build)}')

    known = scan_ports_for_versions()
    for ver in to_build:
        port_base = known.get(ver)
        if port_base is None:
            port_base = 'ffmpeg-' + ver.replace('.', '-')
        print(f'{ver} {port_base}')


if __name__ == '__main__':
    main()
