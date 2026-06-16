"""LTS detection for FFmpeg version series.

FFmpeg LTS releases:
- Odd.minor.1 series (e.g. 5.1, 7.1)
- 4.4 (special case, even-even LTS)
"""


def is_lts(major: int, minor: int) -> bool:
    """Return True if (major, minor) is an LTS series."""
    if major == 4 and minor == 4:
        return True
    return major % 2 == 1 and minor == 1
