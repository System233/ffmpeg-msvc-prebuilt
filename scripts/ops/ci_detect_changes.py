#!/usr/bin/env python3
"""
Detect changed FFmpeg YAML versions between two git commits.

Compares YAML files under ffmpeg/ at two git refs and reports which
versions need a CI build.  A version is considered changed when:

  - Its YAML file is new (doesn't exist in the base commit), OR
  - The ``revision`` field differs between base and head, OR
  - Its family YAML (e.g. 8.1.yaml → 8.1.x children) was modified.

Usage as CLI:

    python scripts/ops/ci_detect_changes.py \\
        --base <before-sha> --head <after-sha> \\
        --json

Defaults to HEAD~1 .. HEAD when neither --base nor --head is given.
The zero-SHA ``0000...`` is accepted and produces an empty result.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA = "0" * 40


# ── Data types ──────────────────────────────────────────────────────────────

@dataclass
class VersionChange:
    version: str
    revision: int


@dataclass
class DetectionResult:
    changed: list[VersionChange] = field(default_factory=list)
    found: bool = False

    @staticmethod
    def empty() -> DetectionResult:
        return DetectionResult()

    def add(self, version: str, revision: int) -> None:
        self.changed.append(VersionChange(version=version, revision=revision))
        self.found = True


# ── Git helpers ─────────────────────────────────────────────────────────────

def version_key(v: str) -> tuple[int, ...]:
    """Sortable version tuple, e.g. '8.1.1' → (8, 1, 1).

    Non-numeric stems (e.g. ``master``) are placed after all numeric ones.
    """
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (999,)


def git_show(ref: str, path: str) -> str:
    """Return file *content* at *ref*:*path*, or empty string if not found."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    return result.stdout if result.returncode == 0 else ""


def git_diff_names(before: str, after: str, pattern: str) -> list[str]:
    """Return list of changed file paths between two refs matching *pattern*."""
    result = subprocess.run(
        ["git", "diff", "--name-only", before, after, "--", pattern],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# ── YAML analysis ───────────────────────────────────────────────────────────

def get_revision(content: str) -> int:
    """Extract ``revision`` field from YAML content, default 0."""
    m = re.search(r"^revision:\s*(\d+)", content, re.MULTILINE)
    return int(m.group(1)) if m else 0


def get_child_versions(family_stem: str) -> list[str]:
    """List all X.Y.Z.yaml children of a family X.Y."""
    ffmpeg_dir = REPO_ROOT / "ffmpeg"
    prefix = family_stem + "."
    children = []
    for f in ffmpeg_dir.iterdir():
        if f.suffix != ".yaml" or f.stem == "base":
            continue
        if f.stem.startswith(prefix) and f.stem.count(".") == 2:
            children.append(f.stem)
    return sorted(children, key=version_key)


# ── Core detection ──────────────────────────────────────────────────────────

def detect_changes(before: str, after: str) -> DetectionResult:
    """Return which versions need a rebuild between *before* and *after*."""
    changed_files = git_diff_names(before, after, "ffmpeg/*.yaml")

    SKIP_STEMS = {"base", "master"}
    changed_stems: set[str] = set()
    for line in changed_files:
        m = re.match(r"ffmpeg/(.+)\.yaml$", line)
        if m and m.group(1) not in SKIP_STEMS:
            changed_stems.add(m.group(1))

    if not changed_stems:
        return DetectionResult.empty()

    result = DetectionResult()

    for stem in sorted(changed_stems, key=version_key):
        old_content = git_show(before, f"ffmpeg/{stem}.yaml")
        new_content = git_show(after, f"ffmpeg/{stem}.yaml")
        is_new = (old_content == "" and new_content != "")
        parts = stem.split(".")
        is_family = len(parts) == 2

        if is_family:
            children = get_child_versions(stem)
            if children:
                for child in children:
                    child_file = REPO_ROOT / "ffmpeg" / f"{child}.yaml"
                    rev = get_revision(child_file.read_text()) if child_file.exists() else 0
                    result.add(child, rev)
            else:
                old_rev = get_revision(old_content)
                new_rev = get_revision(new_content)
                if old_rev != new_rev or is_new:
                    result.add(stem, new_rev)
        else:
            old_rev = get_revision(old_content)
            new_rev = get_revision(new_content)
            if old_rev != new_rev or is_new:
                result.add(stem, new_rev)

    return result


# ── Output ──────────────────────────────────────────────────────────────────

def print_result(result: DetectionResult, use_json: bool, empty_msg: str = "No YAML revision changes detected.") -> None:
    if not result.found:
        if use_json:
            print(json.dumps(asdict(result)))
        else:
            print(empty_msg)
        return

    if use_json:
        print(json.dumps(asdict(result)))
    else:
        for c in result.changed:
            print(f"{c.version} {c.revision}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect changed FFmpeg YAML versions between two git commits.",
    )
    parser.add_argument(
        "--base", default=None,
        help="Base (old) commit (default: HEAD~1).  Pass a SHA or '0000…' for empty result.",
    )
    parser.add_argument(
        "--head", default=None,
        help="Head (new) commit (default: HEAD).",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON.")
    return parser


def resolve_ref(ref: str | None, default: str) -> str | None:
    """Return *ref* if it is a valid-ish SHA, *default* if None, or ``None`` if zero-SHA."""
    if ref is None:
        return default
    if ref == ZERO_SHA:
        return None
    return ref


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve base / head with defaults
    base = resolve_ref(args.base, "HEAD~1")
    head = resolve_ref(args.head, "HEAD")

    # Zero-SHA or missing base — nothing to compare
    if base is None or head is None:
        print_result(DetectionResult.empty(), args.json)
        return

    try:
        result = detect_changes(base, head)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print_result(result, args.json)


if __name__ == "__main__":
    main()
