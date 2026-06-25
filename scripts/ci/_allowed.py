"""Shared allowed-file scope for auto-heal scripts.

Usage::

    from _allowed import find_violations

    violations = find_violations(files, yaml="8.1.1")
    if violations:
        ...
"""

from __future__ import annotations

import re
from typing import Sequence

DEFAULT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^ffmpeg/.*\.yaml$"),
    re.compile(r"^patches/.*\.patch$"),
]


def find_violations(
    files: Sequence[str],
    yaml: str | None = None,
) -> list[str]:
    """Return filenames that are NOT within the allowed scope.

    When *yaml* is given, the ffmpeg pattern is narrowed to only
    ``ffmpeg/{yaml}.yaml`` (exact match).  Without it the generic
    ``ffmpeg/*.yaml`` is used.
    """
    if yaml:
        patterns: list[re.Pattern[str]] = [
            re.compile(rf"^ffmpeg/{re.escape(yaml)}\.yaml$"),
            re.compile(r"^patches/.*\.patch$"),
        ]
    else:
        patterns = list(DEFAULT_PATTERNS)
    return [
        f
        for f in files
        if not any(p.search(f) for p in patterns)
    ]
