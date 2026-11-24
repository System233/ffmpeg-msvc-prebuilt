"""Internal GitHub Actions adapters; deliberately not part of the public CLI."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .builder import patch_arm_sdk, submit_dependencies


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ffbuild.ci")
    command = parser.add_subparsers(dest="command", required=True)
    submission = command.add_parser("submit-dependencies")
    submission.add_argument("--triplet", required=True)
    prepare = command.add_parser("prepare-host")
    prepare.add_argument("--triplet", required=True)
    args = parser.parse_args(argv)
    if args.command == "submit-dependencies":
        runtime = Path(os.environ.get("RUNNER_TEMP", str(Path(__file__).resolve().parents[1] / "_work"))) / "ffbuild"
        submit_dependencies(vcpkg_root=runtime / "vcpkg", triplet=args.triplet)
    elif args.command == "prepare-host" and args.triplet == "arm-windows":
        patch_arm_sdk()


if __name__ == "__main__":
    main()
