"""Stable ffbuild CLI: all CI decisions live in Python, not YAML scripts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .versions import LICENSES, LINKAGES, ROOT, TRIPLETS, generate, versions


def _choice_tuple(value: str, available: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return available
    choices = tuple(v.strip() for v in value.split(",") if v.strip())
    if not choices or not set(choices).issubset(available):
        raise ValueError(f"Expected comma-separated choices from {available}, got: {value}")
    return choices


def _add_plan_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=("all", "changed"), default="all")
    p.add_argument("--event", action="store_true",
                   help="Derive mode, version and refs from GITHUB_EVENT_PATH")
    p.add_argument("--version", default="", help="One YAML version (or master)")
    p.add_argument("--base", default="", help="Base Git ref for --mode changed")
    p.add_argument("--head", default="", help="Head Git ref for --mode changed")
    p.add_argument("--ref", default="", help="Pinned FFmpeg snapshot describe ref")
    p.add_argument("--sha512", default="", help="Pinned FFmpeg source SHA512")
    p.add_argument("--history", action="store_true", help="Include all supported historical versions")
    p.add_argument("--force", action="store_true", help="Rebuild even when fingerprints match")
    p.add_argument("--triplets", default="", help="Comma-separated target triplets")
    p.add_argument("--licenses", default="", help="Comma-separated license variants")
    p.add_argument("--linkages", default="", help="Comma-separated linkage variants")
    p.add_argument("--state-dir", type=Path, default=None, help="Read data YAMLs locally")
    p.add_argument("--no-fetch", action="store_true", help="Do not refresh origin/data")
    p.add_argument("--output", type=Path, default=Path("ffbuild-plan.json"))
    p.add_argument("--github-output", action="store_true")
    p.add_argument("--shard-index", type=int, default=0)
    p.add_argument("--shard-count", type=int, default=1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ffbuild", description="FFmpeg MSVC build and release automation")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_plan_options(sub.add_parser("plan", help="Compute dependency-aware build matrix"))
    build = sub.add_parser("build", help="Compile, test and package all variants in a work unit")
    build.add_argument("--plan-file", type=Path, default=Path("ffbuild-plan.json"))
    source = build.add_mutually_exclusive_group(required=True)
    source.add_argument("--job-id")
    source.add_argument("--job-env", help="Environment variable containing planned job JSON")
    build.add_argument("--vcpkg-root", type=Path, default=None)
    build.add_argument("--cache-dir", type=Path, default=None)
    build.add_argument("--output-dir", type=Path, default=Path("Release"))
    build.add_argument("--no-bootstrap", action="store_true")
    prepare = sub.add_parser("prepare", help="Optionally prewarm vcpkg dependency downloads/builds")
    prepare.add_argument("--triplet", required=True, choices=TRIPLETS)
    prepare.add_argument("--vcpkg-root", type=Path, default=None)
    prepare.add_argument("--cache-dir", type=Path, default=None)
    prepare.add_argument("--download-only", action="store_true")
    submit = sub.add_parser("submit-dependencies", help="Submit vcpkg dependency graph")
    submit.add_argument("--triplet", required=True, choices=TRIPLETS)
    submit.add_argument("--vcpkg-root", type=Path, default=None)
    publish = sub.add_parser("publish", help="Publish verified assets to GitHub and data branch")
    publish.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    publish.add_argument("--data-dir", type=Path, default=Path("data"))
    publish.add_argument("--plan-file", type=Path)
    publish.add_argument("--dry-run", action="store_true")
    sub.add_parser("master-metadata", help="Resolve upstream FFmpeg master and SHA512")
    updates = sub.add_parser("updates", help="Discover upstream releases and optionally create PRs")
    updates.add_argument("--version", default="", help="Only process one specified upstream version")
    updates.add_argument("--sha512", default="", help="Precomputed source checksum (single version)")
    updates.add_argument("--apply", action="store_true", help="Create version branches and PRs")
    validate = sub.add_parser("validate", help="Validate every configuration and optional unit tests")
    validate.add_argument("--tests", action="store_true")
    sub.add_parser("list", help="List configured FFmpeg versions")
    return parser


def _runtime_dir() -> Path:
    return Path(os.environ.get("RUNNER_TEMP", str(ROOT / "_work"))) / "ffbuild"


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print("\n".join(versions()))
    elif args.command == "plan":
        from .planner import plan, write_github_output
        from .state import PublishedState

        include_master = False
        if args.event:
            from .events import event_options
            options = event_options()
            args.mode = options["mode"]
            args.base = options["base"]
            args.head = options["head"]
            args.force = options["force"]
            args.history = options["history"]
            args.shard_count = options["shard_count"]
            args.shard_index = options["shard_index"]
            args.version = args.version or options["version"]
            args.ref = args.ref or options["ref"]
            args.sha512 = args.sha512 or options["sha512"]
            include_master = options["include_master"]
        state = PublishedState(directory=args.state_dir)
        if not args.no_fetch and args.state_dir is None and not args.force:
            state.refresh()
        result = plan(
            mode=args.mode, version=args.version, base=args.base, head=args.head,
            ref=args.ref, sha512=args.sha512, history=args.history,
            triplets=_choice_tuple(args.triplets, TRIPLETS),
            licenses=_choice_tuple(args.licenses, LICENSES),
            linkages=_choice_tuple(args.linkages, LINKAGES),
            state=state, force=args.force, include_master=include_master,
        )
        if args.shard_count <= 0 or not 0 <= args.shard_index < args.shard_count:
            raise ValueError("Shard count must be positive and index must be in range")
        if args.shard_count > 1:
            result["jobs"] = [
                job for i, job in enumerate(result["jobs"])
                if i % args.shard_count == args.shard_index
            ]
            result["matrix"] = result["jobs"]
        if len(result["jobs"]) > 256 and args.github_output:
            raise ValueError("GitHub matrix supports at most 256 jobs; set --shard-count")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Planned {len(result['versions'])} versions, {len(result['jobs'])} work units",
              file=sys.stderr)
        if args.github_output:
            output = os.environ.get("GITHUB_OUTPUT")
            if not output:
                raise RuntimeError("GITHUB_OUTPUT is required")
            write_github_output(result, Path(output))
        else:
            print(json.dumps(result["matrix"]))
    elif args.command == "build":
        from .builder import build_job

        if args.job_env:
            raw = os.environ.get(args.job_env)
            if not raw:
                raise ValueError(f"Missing build job environment variable {args.job_env!r}")
            job = json.loads(raw)
        else:
            data = json.loads(args.plan_file.read_text(encoding="utf-8"))
            selected = [job for job in data["jobs"] if job["id"] == args.job_id]
            if len(selected) != 1:
                raise ValueError(f"Expected exactly one job with id={args.job_id!r}")
            job = selected[0]
        runtime = _runtime_dir()
        outputs = build_job(
            job,
            vcpkg_root=args.vcpkg_root or runtime / "vcpkg",
            cache_dir=args.cache_dir or runtime / "vcpkg-cache",
            output_dir=args.output_dir,
            bootstrap_tool=not args.no_bootstrap,
        )
        print(f"Packaged {len(outputs)} verified variants")
    elif args.command == "prepare":
        from .builder import prepare
        runtime = _runtime_dir()
        prepare(
            triplet=args.triplet,
            vcpkg_root=args.vcpkg_root or runtime / "vcpkg",
            cache_dir=args.cache_dir or runtime / "vcpkg-cache",
            download_only=args.download_only,
        )
    elif args.command == "submit-dependencies":
        from .builder import submit_dependencies
        submit_dependencies(
            triplet=args.triplet,
            vcpkg_root=args.vcpkg_root or _runtime_dir() / "vcpkg",
        )
    elif args.command == "publish":
        from .legacy_release import publish
        for tag in publish(
            artifacts_dir=args.artifacts_dir, data_dir=args.data_dir,
            dry_run=args.dry_run, expected_plan=args.plan_file,
        ):
            print(f"Published/validated: {tag}")
    elif args.command == "master-metadata":
        from .master import master_metadata, write_github_output
        result = master_metadata()
        if os.environ.get("GITHUB_OUTPUT"):
            write_github_output(result, Path(os.environ["GITHUB_OUTPUT"]))
        print(json.dumps(result))
    elif args.command == "updates":
        from .updates import discover, apply_versions
        versions_found = [args.version] if args.version else discover()
        print(json.dumps(versions_found), flush=True)
        if args.apply:
            apply_versions(versions_found, sha512=args.sha512)
    elif args.command == "validate":
        # All YAML generations use the same ffport API as actual builds.
        with tempfile.TemporaryDirectory(prefix="ffbuild-validate-") as tmp:
            for name in versions():
                generate(name, output=Path(tmp), sha512="0" * 128)
            print(f"Validated {len(versions())} FFmpeg configurations")
        if args.tests:
            import unittest
            suite = unittest.TestLoader().discover(str(ROOT / "tests"))
            result = unittest.TextTestRunner(verbosity=1).run(suite)
            if not result.wasSuccessful():
                raise SystemExit(1)


if __name__ == "__main__":
    main()
