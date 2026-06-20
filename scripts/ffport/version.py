"""Version string parsing.

Supports three input formats:
  1. Git describe:  n8.1.1-50-gabc1234  →  8.1.1-50-gabc1234  (strip n prefix)
  2. Version+tag:   X.Y.Z-tag           →  8.1-20260617       (tag: no dashes)
  3. Plain version: X.Y.Z               →  8.1.1
"""

import re


def parse_version(version_str: str, build_date: str | None = None) -> dict:
    """
    Parse a version string into its components.

    *build_date* is accepted for backward compatibility but no longer used
    — describe versions use the raw describe string directly.

    Returns:
        version: str       Vcpkg version string (semver)
        commit: str|None   Commit SHA extracted from describe
        ref: str|None      Ref for git checkout (describe string for describe)
        base_version: str  Base X.Y or X.Y.Z for YAML chain loading
        display_ver: str   Original input for display (e.g. ``n8.1.1-50-gabc1234``)
    """

    # Rule 1: Git describe — nX.Y.Z[...]-N-g<SHA>
    m = re.match(
        r'^n(\d+\.\d+(?:\.\d+)?)((?:-\w+)*-\d+-g[0-9a-f]+)$',
        version_str
    )
    if m:
        base = m.group(1)
        suffix = m.group(2).lstrip('-')
        version = f"{base}{m.group(2)}"
        commit = re.search(r'-g([0-9a-f]+)$', m.group(2)).group(1)
        return {
            'version': version,
            'commit': commit,
            'ref': version_str,
            'base_version': base,
            'display_ver': version_str,
        }

    # Rule 2: Version + tag — X.Y.Z-tag (tag has no dashes)
    m = re.match(r'^(\d+\.\d+(?:\.\d+)?)-([a-zA-Z0-9._]+)$', version_str)
    if m:
        return {
            'version': version_str,
            'commit': None,
            'ref': None,
            'base_version': m.group(1),
            'display_ver': version_str,
        }

    # Rule 3: Plain version — X.Y.Z
    m = re.match(r'^\d+\.\d+(?:\.\d+)?$', version_str)
    if m:
        return {
            'version': version_str,
            'commit': None,
            'ref': None,
            'base_version': version_str,
            'display_ver': version_str,
        }

    raise ValueError(f"Cannot parse version string: {version_str}")
