"""Internal GitHub Actions adapters; deliberately not part of the public CLI."""

from __future__ import annotations

import argparse
import json
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
    cache = command.add_parser("verify-cache")
    cache.add_argument("--job-env", required=True)
    cache.add_argument("--cache-dir", required=True, type=Path)
    restore = command.add_parser("restore-dependencies")
    restore.add_argument("--job-env", required=True)
    restore.add_argument("--cache-dir", required=True, type=Path)
    audit = command.add_parser("audit-worker")
    audit.add_argument("--job-env", required=True)
    audit.add_argument("--buildtrees", required=True, type=Path)
    sdk = command.add_parser("verify-sdk")
    sdk.add_argument("--artifacts-dir", required=True, type=Path)
    sdk.add_argument("--pkgconf", type=Path)
    sdk.add_argument("--generator", default="Visual Studio 17 2022")
    sdk.add_argument("--report", type=Path)
    installed = command.add_parser("verify-installed-sdk")
    installed.add_argument("--job-env", required=True)
    installed.add_argument("--installed-root", required=True, type=Path)
    installed.add_argument("--pkgconf", required=True, type=Path)
    installed.add_argument("--report", type=Path)
    installed.add_argument("--generator", default="Visual Studio 17 2022")
    args = parser.parse_args(argv)
    if args.command == "submit-dependencies":
        runtime = Path(os.environ.get("RUNNER_TEMP", str(Path(__file__).resolve().parents[2] / "_work"))) / "ffbuild"
        submit_dependencies(vcpkg_root=runtime / "vcpkg", triplet=args.triplet)
    elif args.command == "prepare-host" and args.triplet == "arm-windows":
        patch_arm_sdk()
    elif args.command == "verify-cache":
        from .cache_guard import verify_from_environment
        verify_from_environment(job_env=args.job_env, cache_dir=args.cache_dir)
    elif args.command == "restore-dependencies":
        from .cache_guard import load_job, restore_dependencies
        from .port import ffmpeg_port_name
        from .versions import GENERATED_PORTS
        job = load_job(args.job_env)
        root = Path(os.environ["VCPKG_ROOT"])
        env = dict(os.environ, VCPKG_BINARY_SOURCES=f"clear;files,{args.cache_dir.resolve()},read")
        restore_dependencies(job, args.cache_dir, port=GENERATED_PORTS / ffmpeg_port_name(job["yaml"]),
                             installed=root / "installed", paths=[f"--x-install-root={root / 'installed'}"], env=env)
    elif args.command == "audit-worker":
        from .cache_guard import load_job, verify_no_dependency_builds
        verify_no_dependency_builds(load_job(args.job_env), args.buildtrees)
    elif args.command in ("verify-sdk", "verify-installed-sdk"):
        from .sdk_validation import validate_directory, validate_installed
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.unlink(missing_ok=True)
        try:
            if args.command == "verify-sdk":
                results = validate_directory(args.artifacts_dir, generator=args.generator, pkgconf=args.pkgconf)
            else:
                from .cache_guard import load_job
                job = load_job(args.job_env)
                results = validate_installed(args.installed_root / job["triplet"], triplet=job["triplet"],
                                             linkage=job["linkage"], features=job["features"],
                                             generator=args.generator, pkgconf=args.pkgconf)
            if not results or len({row["id"] for row in results}) != len(results):
                raise ValueError("Incomplete or duplicate SDK acceptance evidence")
        except Exception as exc:
            if args.report:
                args.report.write_text(json.dumps({"schema": 1, "suite": args.command,
                                                   "passed": False, "error": str(exc)[-8000:]},
                                                  indent=2) + "\n", encoding="utf-8")
            raise
        runtime_skipped = sum(row["runtime"] == "skipped" for row in results)
        if args.report:
            args.report.write_text(json.dumps({"schema": 1, "suite": args.command,
                                               "passed": True, "runtime_skipped": runtime_skipped,
                                               "results": results}, indent=2) + "\n",
                                   encoding="utf-8")
        suffix = f"; {runtime_skipped} runtime skips (host architecture incompatible)" if runtime_skipped else ""
        print(f"{args.command}: {len(results)} cases passed{suffix}", flush=True)


if __name__ == "__main__":
    main()
