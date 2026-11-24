"""One-version-per-day release scheduling without a persistent queue.

The scheduler selects a single source-backed version for each UTC calendar
day. GitHub Actions retries on the same date select the same version, while
unpublished native vcpkg ABIs remain the authoritative rebuild decision.
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timezone
from pathlib import Path

from .versions import has_source, versions


# A fixed origin makes rotation deterministic and independent of run IDs.
_ROTATION_EPOCH = date(2026, 1, 1)


def release_cycle() -> tuple[str, ...]:
    """Published stable versions plus the independently pinned upstream master."""
    stable = [name for name in versions() if has_source(name)]
    if not stable:
        raise ValueError("No source-backed FFmpeg versions available for daily builds")
    return tuple(stable) + ("master",)


def select_daily_version(day: date, *, cycle: tuple[str, ...] | None = None) -> str:
    """Select one and only one version, including master once per cycle."""
    candidates = release_cycle() if cycle is None else cycle
    if not candidates or len(candidates) != len(set(candidates)):
        raise ValueError("Release rotation needs unique, nonempty version names")
    if day < _ROTATION_EPOCH:
        raise ValueError("Daily release date is before the rotation epoch")
    return candidates[(day - _ROTATION_EPOCH).days % len(candidates)]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Select one daily FFmpeg release")
    parser.add_argument("--date", default=None, help="UTC date YYYY-MM-DD (default today)")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)
    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    candidates = release_cycle()
    version = select_daily_version(day, cycle=candidates)
    if args.github_output:
        location = os.environ.get("GITHUB_OUTPUT")
        if not location:
            raise ValueError("GITHUB_OUTPUT is required")
        with Path(location).open("a", encoding="utf-8") as stream:
            stream.write(f"version={version}\n")
            stream.write(f"date={day.isoformat()}\n")
            stream.write(f"cycle_size={len(candidates)}\n")
    print(f"UTC {day.isoformat()} → FFmpeg {version} (1/{len(candidates)} versions scheduled)")


if __name__ == "__main__":
    main()
