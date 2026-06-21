#!/usr/bin/env python3
"""
find_closest_yaml.py - Find the closest existing YAML config for a target version.

Returns ``master`` when the target is a new major or a new minor on the
currently-active major.  For legacy majors the latest same-major YAML is used.
"""
import argparse
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
YAML_DIR = REPO_ROOT / "ffmpeg"


def version_tuple(stem: str) -> tuple[int, ...]:
    return tuple(int(x) for x in stem.split("."))


def is_valid_version(stem: str) -> bool:
    return bool(re.match(r"^\d+(\.\d+){1,2}$", stem))


def find_closest_yaml(version: str) -> str:
    parts = version.split(".")
    target = tuple(int(x) for x in parts)

    # 收集所有版本 YAML
    all_versions: list[tuple[int, ...]] = []
    for f in YAML_DIR.glob("*.yaml"):
        stem = f.stem
        if not is_valid_version(stem):
            continue
        all_versions.append(version_tuple(stem))

    if not all_versions:
        return "master"

    highest_major = max(v[0] for v in all_versions)

    # 按 major 分组
    same_major: list[tuple[int, ...]] = []
    for v in all_versions:
        if v[0] == target[0]:
            same_major.append(v)

    # target 的 major 没有 YAML → 全新 major
    if not same_major:
        return "master"

    # target 是当前最高 major 的新 minor → master
    if target[0] == highest_major:
        max_minor = max(v[1] for v in same_major)
        if target[1] > max_minor:
            return "master"

    # 同 minor 内找最新 patch，否则取该 major 最新
    same_minor = [v for v in same_major if v[1] == target[1]]
    if same_minor:
        best = max(same_minor)
    else:
        best = max(same_major)

    return ".".join(str(x) for x in best)


def main():
    parser = argparse.ArgumentParser(
        description="Find the closest existing YAML for a target version."
    )
    parser.add_argument("--version", required=True, help="Target version (e.g. 6.5)")
    args = parser.parse_args()
    print(find_closest_yaml(args.version))


if __name__ == "__main__":
    main()
