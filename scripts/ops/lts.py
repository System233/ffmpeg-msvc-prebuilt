"""LTS detection for FFmpeg version series.

FFmpeg LTS releases:
- Odd.minor.1 series (e.g. 5.1, 7.1)
- 4.4 (special case, even-even LTS)
"""

import re

# A version string that can be an official FFmpeg release tag:
# optional leading "n", then X.Y or X.Y.Z with no extra suffixes.
# Dev snapshots (e.g. 9.1-dev-829-g6092f06) and dated builds
# (e.g. 7.1-20260101) intentionally do NOT match.
_RELEASE_VERSION_RE = re.compile(r"^n?\d+\.\d+(?:\.\d+)?$")


def is_lts(major: int, minor: int) -> bool:
    """Return True if (major, minor) is an LTS series."""
    if major == 4 and minor == 4:
        return True
    return major % 2 == 1 and minor == 1


def is_release_version(version: str) -> bool:
    """Return True if *version* is a plain ``X.Y`` / ``X.Y.Z`` release."""
    return bool(_RELEASE_VERSION_RE.match(version))


def is_lts_version(version: str) -> bool:
    """Return True only if *version* is an official release in an LTS series.

    Dev snapshots (e.g. ``9.1-dev-829-g6092f06``) and dated builds
    (e.g. ``7.1-20260101``) are never LTS even when their leading numbers
    match an LTS series — only actual release versions qualify.
    """
    if not is_release_version(version):
        return False
    parts = version.lstrip("n").split(".")
    return is_lts(int(parts[0]), int(parts[1]))
