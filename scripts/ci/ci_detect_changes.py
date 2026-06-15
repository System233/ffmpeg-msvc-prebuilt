#!/usr/bin/env python3
"""
Detect changed FFmpeg YAML files and determine which versions to rebuild.

Detects YAML files (ffmpeg/*.yaml) whose revision field changed between two
git commits. Family YAMLs (e.g. 8.1.yaml) trigger rebuild of all child patch
versions. Outputs VERSION REVISION pairs for downstream dispatch.

Usage:
    python scripts/ci/ci_detect_changes.py <before_sha> <after_sha>
    python scripts/ci/ci_detect_changes.py --json <before_sha> <after_sha>

Output (default):
    Prints "VERSION REVISION" lines, one per version to build.
    Example:
        8.1.1 2
        7.1.2 1

Output (--json):
    JSON object with 'changed' array and 'found' boolean.
"""

import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def version_key(v: str):
    """Sortable version tuple for comparison."""
    return tuple(int(x) for x in v.split('.'))


def _git_show(ref: str, path: str) -> str:
    """Return file content at a given git ref, or empty string if not found."""
    result = subprocess.run(
        ['git', 'show', f'{ref}:{path}'],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        return ''
    return result.stdout


def _get_revision(content: str) -> int:
    """Extract revision field from YAML content, defaulting to 0."""
    m = re.search(r'^revision:\s*(\d+)', content, re.MULTILINE)
    return int(m.group(1)) if m else 0


def _get_child_versions(family_stem: str):
    """Find all child patch versions (X.Y.Z) for a family YAML stem (X.Y).

    Scans ffmpeg/ on disk for files matching X.Y.Z.yaml.
    Returns sorted list of version strings.
    """
    ffmpeg_dir = REPO_ROOT / "ffmpeg"
    prefix = family_stem + '.'
    children = []
    for f in ffmpeg_dir.iterdir():
        if f.suffix != '.yaml' or f.stem == 'base':
            continue
        if f.stem.startswith(prefix) and f.stem.count('.') == 2:
            children.append(f.stem)
    return sorted(children, key=version_key)


def get_changed_versions(before: str, after: str):
    """Return dict mapping version string to new revision for changed YAMLs.

    Runs git diff to find changed ffmpeg/*.yaml files, then checks whether
    the revision field changed for each. Family YAMLs (X.Y.yaml) trigger
    rebuild of all child patch versions regardless of revision change.
    """
    result = subprocess.run(
        ['git', 'diff', '--name-only', before, after, '--', 'ffmpeg/*.yaml'],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print(f'Error running git diff: {result.stderr}', file=sys.stderr)
        sys.exit(1)

    # Collect stems of changed YAMLs, skipping base.yaml
    changed_stems = set()
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # Expected: ffmpeg/8.1.1.yaml
        m = re.match(r'ffmpeg/(.+)\.yaml$', line)
        if m:
            stem = m.group(1)
            if stem != 'base':
                changed_stems.add(stem)

    if not changed_stems:
        return {}

    versions_to_build = {}  # version -> new_revision

    for stem in sorted(changed_stems, key=version_key):
        parts = stem.split('.')
        is_family = len(parts) == 2

        if is_family:
            # Family YAML (X.Y) — if it has children, rebuild all of them
            children = _get_child_versions(stem)
            if children:
                for child in children:
                    child_path = REPO_ROOT / "ffmpeg" / f"{child}.yaml"
                    rev = _get_revision(child_path.read_text()) if child_path.exists() else 0
                    versions_to_build[child] = rev
            else:
                # No children — treat the family version itself as buildable
                old = _get_revision(_git_show(before, f'ffmpeg/{stem}.yaml'))
                new = _get_revision(_git_show(after, f'ffmpeg/{stem}.yaml'))
                if old != new:
                    versions_to_build[stem] = new
        else:
            # Patch YAML (X.Y.Z) — build only if revision changed
            old = _get_revision(_git_show(before, f'ffmpeg/{stem}.yaml'))
            new = _get_revision(_git_show(after, f'ffmpeg/{stem}.yaml'))
            if old != new:
                versions_to_build[stem] = new

    return versions_to_build


def main():
    argv = sys.argv[1:]
    use_json = False

    if argv and argv[0] == '--json':
        use_json = True
        argv = argv[1:]

    if len(argv) != 2:
        print('Usage: ci_detect_changes.py [--json] <before_sha> <after_sha>', file=sys.stderr)
        sys.exit(1)

    before, after = argv[0], argv[1]

    # Skip if this is the first push (before is all zeros)
    if before == '0000000000000000000000000000000000000000':
        if use_json:
            json.dump({"changed": [], "found": False}, sys.stdout)
            print()
        else:
            print('No previous commit to diff against (initial push)')
        return

    versions = get_changed_versions(before, after)
    if not versions:
        if use_json:
            json.dump({"changed": [], "found": False}, sys.stdout)
            print()
        else:
            print('No YAML revision changes detected.')
        return

    if use_json:
        changed = [{"version": ver, "revision": rev}
                   for ver, rev in sorted(versions.items(), key=lambda x: version_key(x[0]))]
        json.dump({"changed": changed, "found": True}, sys.stdout)
        print()
    else:
        for ver, rev in sorted(versions.items(), key=lambda x: version_key(x[0])):
            print(f'{ver} {rev}')


if __name__ == '__main__':
    main()
