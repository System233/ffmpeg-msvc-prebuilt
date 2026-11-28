"""Version, content identity and release orchestration around native vcpkg."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .targets import select_targets
from .versions import GENERATED_PORTS, ROOT, TRIPLETS, config, generate, generate_all, has_source, versions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ffbuild", description="FFmpeg CI version and release manager")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Query native vcpkg ABI hashes without building")
    scan.add_argument("--local", action="store_true", help="List local FFmpeg source configurations")
    scan.add_argument("--upstream", action="store_true", help="Discover upstream releases")
    scan.add_argument("--release-date", default=None, help="Immutable UTC date of the build tag")
    scan.add_argument("--version", default="", help="One configured FFmpeg version, or master")
    scan.add_argument("--history", action="store_true", help="Scan every source-backed release")
    scan.add_argument("--master-snapshot-file", type=Path, help="Pinned source metadata shared with port generation")
    scan.add_argument("--describe", default="", help="Pinned master git describe")
    scan.add_argument("--commit", default="", help="Pinned upstream master commit")
    scan.add_argument("--sha512", default="", help="Pinned master SHA512")
    scan.add_argument("--target-arch", default="", help="Limit native scan to one Triplet")
    scan.add_argument("--target-license", choices=("", "lgpl", "gpl"), default="",
                      help="Limit native scan to one license")
    scan.add_argument("--abi-evidence", type=Path, help="Retain all native ABI input files")
    scan.add_argument("--job-env", default="", help="Preflight one planned vcpkg job's ABI")
    scan.add_argument("--generated-root", type=Path, default=GENERATED_PORTS)
    scan.add_argument("--vcpkg-bin", type=Path)
    scan.add_argument("--output", type=Path, default=Path("ffbuild-abi.json"))

    generate_parser = sub.add_parser("generate", help="Generate one native vcpkg overlay port")
    generate_parser.add_argument("version", nargs="?", help="FFmpeg version YAML or master")
    generate_parser.add_argument("--all", action="store_true", help="Generate every source-backed release Port")
    generate_parser.add_argument("--include-master", action="store_true",
                                 help="Also generate an upstream-pinned master Port")
    generate_parser.add_argument("--master-snapshot-file", type=Path,
                                 help="Write the pinned master source metadata")
    generate_parser.add_argument("--describe", help="Pinned upstream master describe version")
    generate_parser.add_argument("--commit", help="Pinned 40-character upstream commit")
    generate_parser.add_argument("--sha512", help="Pinned source tarball SHA512")
    generate_parser.add_argument("--output", type=Path, default=GENERATED_PORTS)

    prepare_parser = sub.add_parser("prepare", help="Prebuild the shared vcpkg dependency Seed")
    prepare_parser.add_argument("--triplet", required=True, choices=TRIPLETS)
    prepare_parser.add_argument("--generated-root", type=Path, default=GENERATED_PORTS)
    prepare_parser.add_argument("--vcpkg-bin", type=Path)
    prepare_parser.add_argument("--install-root", type=Path)
    prepare_parser.add_argument("--only-downloads", action="store_true")
    prepare_parser.add_argument("--plan-file", type=Path)
    prepare_parser.add_argument("--expected")
    prepare_parser.add_argument("--cache-dir", type=Path)
    prepare_parser.add_argument("--cache-only", action="store_true")
    prepare_parser.add_argument("--finalize-cache", action="store_true",
                                help="After cache-only validation, discard obsolete ABI archives in this CI cache")
    prepare_parser.add_argument("--abi-evidence", type=Path)

    plan = sub.add_parser("plan", help="Schedule unpublished native vcpkg ABIs from a scan")
    plan.add_argument("--force", action="store_true", help="Schedule even when data contains this ABI")
    plan.add_argument("--abi-file", required=True, type=Path,
                      help="JSON produced by native vcpkg ABI scan")
    plan.add_argument("--state-dir", type=Path, default=None)
    plan.add_argument("--output", type=Path, default=Path("ffbuild-plan.json"))
    plan.add_argument("--github-output", action="store_true")

    package = sub.add_parser("package", help="Verify and package an already compiled vcpkg port")
    identity = package.add_mutually_exclusive_group(required=True)
    identity.add_argument("--job-env", help="Environment variable containing one planned job JSON")
    identity.add_argument("--job-file", type=Path, help="JSON file containing one planned job")
    package.add_argument("--port-dir", required=True, type=Path,
                         help="Actual vcpkg packages/<versioned-port>_<triplet> directory")
    package.add_argument("--output-dir", type=Path, default=Path("Release"))
    package.add_argument("--installed-root", type=Path,
                         help="vcpkg/installed containing actual status and share/<port>/copyright")
    package.add_argument("--source-tree", type=Path,
                         help="The unpacked FFmpeg source directory containing COPYING.*")
    package.add_argument("--buildtrees", type=Path,
                         help="vcpkg/buildtrees used to discover the unpacked FFmpeg source")

    publish = sub.add_parser("publish", help="Verify release assets and update data branch")
    publish.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    publish.add_argument("--data-dir", type=Path, default=Path("data"))
    publish.add_argument("--plan-file", type=Path)
    publish.add_argument("--dry-run", action="store_true")

    recovery = sub.add_parser("recover-index", help="Recover Data from a verified existing public Release")
    recovery.add_argument("--tag", required=True)
    recovery.add_argument("--data-dir", type=Path, default=Path("data"))

    refresh = sub.add_parser("refresh-lts", help="Refresh explicit LTS metadata in catalog shards")
    refresh.add_argument("--data-dir", type=Path, default=Path("data"))

    sub.add_parser("validate", help="Check configuration, feature and generated port validity")
    autoheal = sub.add_parser("autoheal", help="Guarded FFmpeg CI Auto-Heal")
    autoheal.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def _plan(args: argparse.Namespace) -> None:
    from .planner import plan_native, write_github_output
    from .state import PublishedState

    scan = json.loads(args.abi_file.read_text(encoding="utf-8"))
    result = plan_native(scan, state=PublishedState(directory=args.state_dir),
                         force=args.force)
    if result["blocked"]:
        raise ValueError(f"Unsupported FFmpeg target combinations: {len(result['blocked'])}; "
                         "fix feature/license policy instead of silently skipping builds")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Planned {len(result['versions'])} versions, {len(result['jobs'])} work units",
          file=sys.stderr)
    if args.github_output:
        location = os.environ.get("GITHUB_OUTPUT")
        if not location:
            raise RuntimeError("GITHUB_OUTPUT is required")
        write_github_output(result, Path(location))
    else:
        print(json.dumps(result["jobs"]))


def _validate() -> None:
    from .spec import read_spec, resolve_features

    with tempfile.TemporaryDirectory(prefix="ffbuild-validate-") as temporary:
        count = 0
        templates = 0
        for name in versions():
            configuration, _ = read_spec(name)
            resolve_features(configuration, name)
            if has_source(name):
                generate(name, output=Path(temporary))
                count += 1
            else:
                templates += 1
    print(f"Validated {count} source-backed FFmpeg ports and {templates} YAML-only templates")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "autoheal":
        from .autoheal.cli import main as autoheal_main
        autoheal_main(argv[1:])
        return
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        if args.local:
            print("\n".join(versions()))
        elif args.upstream:
            from .updates import discover
            print(json.dumps(discover()))
        else:
            from .native_abi import build_requests, scan_native_abis, verify_job_abi

            if args.job_env:
                raw = os.environ.get(args.job_env, "")
                if not raw:
                    raise ValueError(f"Missing planned job environment variable {args.job_env}")
                job = json.loads(raw)
                print(verify_job_abi(job, overlay=args.generated_root, binary=args.vcpkg_bin, evidence=args.abi_evidence))
            else:
                snapshot = None
                if args.version == "master" and any((args.describe, args.commit, args.sha512)):
                    if not all((args.describe, args.commit, args.sha512)):
                        raise ValueError("Master requires --describe, --commit and --sha512 together")
                    snapshot = {"ref": args.describe, "commit": args.commit,
                                "sha512": args.sha512}
                if args.master_snapshot_file and args.master_snapshot_file.is_file():
                    pinned = json.loads(args.master_snapshot_file.read_text(encoding="utf-8"))
                    if snapshot is not None and pinned != snapshot:
                        raise ValueError("Master snapshot disagrees with explicit build inputs")
                    snapshot = pinned
                targets = select_targets(arch=args.target_arch, license_=args.target_license)
                requests, blocked = build_requests(version=args.version, history=args.history,
                                                   targets=targets,
                                                   snapshot=snapshot, release_date=args.release_date)
                jobs = scan_native_abis(requests, overlay=args.generated_root,
                                        binary=args.vcpkg_bin, evidence=args.abi_evidence)
                result = {"schema": 3, "jobs": jobs, "blocked": blocked}
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print(f"Native vcpkg ABI scan: {len(jobs)} variants, "
                      f"{len(blocked)} unsupported variants")
    elif args.command == "generate":
        if args.all:
            if args.version:
                raise ValueError("Specify either a version or --all")
            snapshot = None
            if args.include_master:
                if any((args.describe, args.commit, args.sha512)):
                    if not all((args.describe, args.commit, args.sha512)):
                        raise ValueError("Master requires --describe, --commit and --sha512")
                    snapshot = {"ref": args.describe, "commit": args.commit,
                                "sha512": args.sha512}
                else:
                    from .master import master_metadata
                    snapshot = master_metadata()
            ports = generate_all(output=args.output, master=snapshot)
            if args.master_snapshot_file and snapshot is not None:
                args.master_snapshot_file.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
            print(f"Generated {len(ports)} version-qualified FFmpeg Ports "
                  f"with stable ffmpeg package identities; Tester remains ports/ffmpeg-tester")
        else:
            if not args.version:
                raise ValueError("A version or --all is required")
            print(generate(args.version, source_version=args.describe, ref=args.commit,
                           sha512=args.sha512, output=args.output))
    elif args.command == "prepare":
        from .seed import prepare_seed, load_seed_plan, prune_seed_cache
        if args.finalize_cache and not (args.cache_only and args.cache_dir and args.plan_file):
            raise ValueError("--finalize-cache requires --cache-only, --cache-dir and --plan-file")
        if args.expected and not args.plan_file:
            raise ValueError("--expected requires --plan-file")
        plan = load_seed_plan(args.plan_file, args.triplet, args.expected) if args.plan_file else None
        completed = prepare_seed(triplet=args.triplet, overlay=args.generated_root,
                                 binary=args.vcpkg_bin, install_root=args.install_root,
                                 only_downloads=args.only_downloads, plan=plan,
                                 cache_only=args.cache_only, cache_dir=args.cache_dir,
                                 evidence=args.abi_evidence)
        if args.finalize_cache:
            removed = prune_seed_cache(plan, args.cache_dir)
            print(f"Removed {removed} obsolete native ABI archives from the dedicated CI cache")
        print(f"Prepared {len(completed)} shared dependency batches for {args.triplet}")
    elif args.command == "plan":
        _plan(args)
    elif args.command == "package":
        from .package import package_job
        from .compliance import find_ffmpeg_source
        if args.job_env:
            content = os.environ.get(args.job_env)
            if not content:
                raise ValueError(f"Missing build job environment variable: {args.job_env}")
            job = json.loads(content)
        else:
            job = json.loads(args.job_file.read_text(encoding="utf-8"))
        source_tree = args.source_tree
        if source_tree is None and args.buildtrees is not None:
            source_tree = find_ffmpeg_source(args.buildtrees)
        metadata = package_job(args.port_dir, job, args.output_dir,
                               installed_root=args.installed_root, source_tree=source_tree)
        print(metadata)
    elif args.command == "publish":
        from .publication import publish
        for tag in publish(artifacts_dir=args.artifacts_dir,
                           data_dir=args.data_dir, dry_run=args.dry_run,
                           expected_plan=args.plan_file):
            print(f"Published/validated: {tag}")
    elif args.command == "recover-index":
        from .publication import recover_index
        recover_index(args.tag, args.data_dir)
    elif args.command == "refresh-lts":
        from .catalog import refresh_lts
        print(f"Updated {refresh_lts(args.data_dir)} catalog shards")
    elif args.command == "validate":
        _validate()
    elif args.command == "autoheal":
        from .autoheal.cli import main as autoheal_main
        autoheal_main(args.args)


if __name__ == "__main__":
    main()
