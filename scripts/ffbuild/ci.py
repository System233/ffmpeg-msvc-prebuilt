"""Internal GitHub Actions adapters; deliberately not part of the public CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from .builder import patch_arm_sdk, submit_dependencies



def cache_request(kind: str, *, tag: str, triplet: str = "", abi: str = "",
                  download_specs: str = "", recipe_hash: str = "") -> dict[str, str]:
    """Current cache identity and incremental reuse within the same namespace."""
    from .targets import configured_triplets
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tag):
        raise ValueError("Invalid VCPKG_TAG for cache identity")
    if kind == "seed":
        if triplet not in configured_triplets() or not re.fullmatch(r"[0-9a-f]{64}", abi):
            raise ValueError("Invalid native Seed ABI cache identity")
        prefix = f"ffbuild-seed-{tag}-{triplet}-"
        key = prefix + abi
    elif kind == "downloads":
        if not re.fullmatch(r"[0-9a-f]{64}", download_specs) or not re.fullmatch(r"[0-9a-f]{64}", recipe_hash):
            raise ValueError("Invalid source download cache identity")
        prefix = f"ffbuild-downloads-{tag}-"
        key = f"{prefix}{download_specs}-{recipe_hash}"
    else:
        raise ValueError("Unknown cache kind")
    return {"key": key, "prefix": prefix}


def _cache_outputs(request: dict, path: Path | None = None) -> None:
    with open(path or os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in request.items():
            if isinstance(value, list):
                value = "\n".join(value)
            if isinstance(value, str) and "\n" in value:
                output.write(key + "<<CACHE_KEYS\n" + value + "\nCACHE_KEYS\n")
            else:
                output.write(f"{key}={value}\n")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def seed_plans(triplets, *, evidence: Path, output: Path,
               target_evidence: Path | None = None, binary: Path | None = None,
               read_plan: bool = False, expected: str | None = None,
               cache_dir: Path | None = None) -> tuple[dict[str, str], str]:
    from .seed import seed_identity, verify_target_coverage, load_seed_plan, verify_batch, require_seed_archives
    from .native_abi import graph_digest
    plans = {}
    for triplet in triplets:
        if read_plan:
            plan = load_seed_plan(output, triplet, expected)
            for index, batch in enumerate(plan["batches"]):
                verify_batch(batch, triplet, binary=binary, evidence=evidence / triplet / f"direct-{index}")
        else:
            digest, plan = seed_identity(triplet=triplet, binary=binary, evidence=evidence / triplet)
            if expected and digest != expected:
                raise RuntimeError(f"Seed native ABI drift for {triplet}: planned {expected}, actual {digest}")
        if cache_dir is not None:
            require_seed_archives(plan, cache_dir)
        plans[triplet] = plan
    if target_evidence is not None:
        verify_target_coverage(plans, target_evidence)
    if not read_plan:
        write_json(output, plans)
    specs = sorted({spec for plan in plans.values() for batch in plan["batches"]
                    for spec in batch["specs"].values()})
    return {t: plan["key"] for t, plan in plans.items()}, graph_digest({"specs": specs})


def plan_release(environ=None) -> dict:
    """One source-bound CI plan, written once after every native check succeeds."""
    from .targets import configured_triplets, select_targets, require_complete_targets
    from .versions import generate_all, GENERATED_PORTS
    from .master import master_metadata
    from .native_abi import build_requests, scan_native_abis
    from .planner import plan_native, write_github_output
    from .state import PublishedState
    from .catalog import validate_catalog
    env = os.environ if environ is None else environ
    version = env["FFBUILD_VERSION"]
    if env["FFBUILD_PRODUCTION"] not in ("true", "false") or env["FFBUILD_FORCE"] not in ("true", "false"):
        raise ValueError("Invalid build mode")
    production = env["FFBUILD_PRODUCTION"] == "true"
    force = env["FFBUILD_FORCE"] == "true"
    if production and (force or env.get("FFBUILD_TARGET_ARCH") or env.get("FFBUILD_TARGET_LICENSE")):
        raise ValueError("Production requires the full configured matrix without force")
    targets = select_targets(arch=env.get("FFBUILD_TARGET_ARCH", ""), license_=env.get("FFBUILD_TARGET_LICENSE", ""))
    pin = {key: env["FFBUILD_" + key.upper()] for key in ("ref", "commit", "sha512")}
    if production:
        validate_catalog(Path("data"))
    master = pin if version == "master" else master_metadata()
    generate_all(master=master)
    triplets = configured_triplets()
    if "arm-windows" in triplets:
        patch_arm_sdk()
    requests, blocked = build_requests(version=version, targets=targets, snapshot=master,
                                       release_date=env["FFBUILD_DATE"])
    if blocked:
        raise ValueError(f"Unsupported native build targets: {blocked}")
    evidence = Path("abi-evidence")
    jobs = scan_native_abis(requests, evidence=evidence / "targets")
    require_complete_targets(jobs, version=version, targets=targets)
    result = plan_native({"schema": 3, "jobs": jobs, "blocked": blocked},
                         state=None if force else PublishedState(directory=Path("data")), force=force)
    if force:
        require_complete_targets(result["jobs"], version=version, targets=targets)
    result["request"] = dict(yaml=version, date=env["FFBUILD_DATE"],
                             repository_commit=env["GITHUB_SHA"], pr_head=env.get("PR_HEAD", ""),
                             pr_base=env.get("PR_BASE", ""), production=production,
                             plan_attempt=int(env["GITHUB_RUN_ATTEMPT"]), seed_master=master, **pin)
    keys, downloads = {}, ""
    if result["jobs"]:
        keys, downloads = seed_plans(triplets, evidence=evidence / "seed",
                                    output=GENERATED_PORTS / "seed-plan.json",
                                    target_evidence=evidence / "targets")
        result["request"]["download_specs"] = downloads
    result["seed_keys"] = keys
    result["request"]["vcpkg_tag"] = env["VCPKG_TAG"]
    seed_caches = {t: cache_request("seed", tag=env["VCPKG_TAG"], triplet=t, abi=abi)
                   for t, abi in keys.items()}
    download = (cache_request("downloads", tag=env["VCPKG_TAG"], download_specs=downloads,
                              recipe_hash=env["CACHE_RECIPE"]) if keys else {})
    for job in result["jobs"]:
        job["seed_key"] = seed_caches[job["triplet"]]["key"]
    result["download_cache"] = download.get("key", "")
    # Runner paths are intentionally not part of the immutable release plan.
    write_json(Path("ffbuild-plan.json"), result)
    write_github_output(result, Path(env["GITHUB_OUTPUT"]))
    _cache_outputs({"plan_attempt": result["request"]["plan_attempt"],
                    "seed_keys": json.dumps(keys, separators=(",", ":")),
                    "download_specs": downloads,
                    "download_key": download.get("key", ""),
                    "download_prefix": download.get("prefix", ""),
                    "prepare_matrix": json.dumps([{"triplet": t, "abi": keys[t],
                        "seed_key": seed_caches[t]["key"], "prefix": seed_caches[t]["prefix"]}
                        for t in sorted({j["triplet"] for j in result["jobs"]})], separators=(",", ":"))}, Path(env["GITHUB_OUTPUT"]))
    return result


def download_sources() -> None:
    from .targets import configured_triplets
    from .seed import load_seed_plan, prepare_seed, DEFAULT_PLAN
    triplets = configured_triplets()
    if "arm-windows" in triplets:
        patch_arm_sdk()
    for triplet in triplets:
        prepare_seed(triplet=triplet, plan=load_seed_plan(DEFAULT_PLAN, triplet), only_downloads=True)


def prepare_cache(triplet: str, expected: str, *, matched_key: str = "") -> str:
    from .seed import load_seed_plan, populate_cache, prune_seed_cache, DEFAULT_PLAN
    plan = load_seed_plan(DEFAULT_PLAN, triplet, expected)
    cache = Path(os.environ["FFBUILD_CACHE_DIR"])
    key = cache_request("seed", tag=os.environ["VCPKG_TAG"], triplet=triplet, abi=expected)["key"]
    same_identity = matched_key == key or matched_key.startswith(key + "-")
    if triplet == "arm-windows":
        patch_arm_sdk()
    refreshed = populate_cache(triplet=triplet, plan=plan, cache_dir=cache,
                               prefer_cache=same_identity, evidence=Path("abi-evidence/seed-verified"))
    prune_seed_cache(plan, cache)
    if not refreshed:
        return ""
    if same_identity:
        return f"{key}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    return key


def repair_cache_plan(triplets: list[str]) -> dict:
    from .targets import configured_triplets
    from .native_platform import PE_MACHINE
    from .versions import GENERATED_PORTS
    if (not triplets or len(set(triplets)) != len(triplets)
            or not set(triplets) <= set(configured_triplets())
            or len(triplets) > len(PE_MACHINE)):
        raise ValueError("Invalid incident Triplets")
    if "arm-windows" in triplets:
        patch_arm_sdk()
    keys, _ = seed_plans(triplets, evidence=Path(os.environ["FFBUILD_REPAIR_DIR"]) / "abi-evidence/seed",
                         output=GENERATED_PORTS / "seed-plan.json")
    tag = os.environ["VCPKG_TAG"]
    seeds = [cache_request("seed", tag=tag, triplet=t, abi=keys[t]) for t in triplets]
    return {"seeds": json.dumps(seeds, separators=(",", ":"))}



def worker_build() -> None:
    from .cache_guard import load_job, install_target
    from .versions import GENERATED_PORTS
    from .port import ffmpeg_port_name
    from ffvcpkg import environment
    job = load_job("FFBUILD_JOB")
    cache = Path(os.environ["FFBUILD_CACHE_DIR"])
    env = environment(dict(os.environ, VCPKG_BINARY_SOURCES=f"clear;files,{cache},read"))
    install_target(job, port=GENERATED_PORTS / ffmpeg_port_name(job["yaml"]), paths=[], env=env)


def worker_package() -> None:
    from .cache_guard import load_job
    from .package import package_job
    from .compliance import find_ffmpeg_source
    from .publication import publish
    root = Path(os.environ["VCPKG_ROOT"])
    job = load_job("FFBUILD_JOB")
    package_job(root / "packages" / f"{job['port']}_{job['triplet']}", job, Path("Release"),
                installed_root=root / "installed", source_tree=find_ffmpeg_source(root / "buildtrees"))
    publish(artifacts_dir=Path("Release"), data_dir=Path("data"), dry_run=True)

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ffbuild.ci")
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("configure")
    command.add_parser("plan")
    command.add_parser("download")
    command.add_parser("worker-build")
    command.add_parser("worker-package")
    repair = command.add_parser("repair-cache-plan")
    repair.add_argument("--triplets-env", required=True)
    seed_prepare = command.add_parser("prepare-cache")
    seed_prepare.add_argument("--triplet", required=True)
    seed_prepare.add_argument("--expected", required=True)
    seed_prepare.add_argument("--matched-key", default="")
    submission = command.add_parser("submit-dependencies")
    submission.add_argument("--triplet")
    prepare = command.add_parser("prepare-host")
    mode = prepare.add_mutually_exclusive_group(required=True)
    mode.add_argument("--triplet")
    mode.add_argument("--configured", action="store_true")
    seed = command.add_parser("seed-identity")
    seed.add_argument("--triplet", action="append", required=True)
    seed.add_argument("--evidence", type=Path, required=True)
    seed.add_argument("--github-output", action="store_true")
    seed.add_argument("--expected")
    seed.add_argument("--cache-dir", type=Path)
    seed.add_argument("--plan-file", type=Path, required=True)
    seed.add_argument("--read-plan", action="store_true", help="Verify a previously emitted dependency plan")
    seed.add_argument("--vcpkg-bin", type=Path)
    seed.add_argument("--target-evidence", type=Path)
    compare = command.add_parser("compare-abi")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output", type=Path)
    restore = command.add_parser("restore-dependencies")
    restore.add_argument("--job-env", default="FFBUILD_JOB")
    restore.add_argument("--cache-dir", type=Path)
    restore.add_argument("--abi-evidence", type=Path)
    audit = command.add_parser("audit-worker")
    audit.add_argument("--job-env", default="FFBUILD_JOB")
    audit.add_argument("--buildtrees", type=Path)
    sdk = command.add_parser("verify-sdk")
    sdk.add_argument("--artifacts-dir", required=True, type=Path)
    sdk.add_argument("--pkgconf", type=Path)
    sdk.add_argument("--generator", default="Visual Studio 17 2022")
    sdk.add_argument("--report", type=Path)
    installed = command.add_parser("verify-installed-sdk")
    installed.add_argument("--job-env", default="FFBUILD_JOB")
    installed.add_argument("--installed-root", type=Path)
    installed.add_argument("--pkgconf", type=Path)
    installed.add_argument("--report", type=Path)
    installed.add_argument("--generator", default="Visual Studio 17 2022")
    args = parser.parse_args(argv)
    if args.command == "configure":
        from .targets import workflow_defaults, ci_setting, matrix_axes
        matrix_axes()
        values = {name: ci_setting(name) for name in workflow_defaults()}
        from ffvcpkg import environment, install_options
        environment(values)
        install_options(values["VCPKG_INSTALL_OPTIONS"])
        # Keep the literal paths used by actions/cache: its cache version
        # includes the configured path and compression implementation.
        temp = os.environ["RUNNER_TEMP"]
        root = f"{temp}/ffbuild/vcpkg"
        values.update(VCPKG_ROOT=root, FFBUILD_CACHE_DIR=f"{temp}/ffbuild/vcpkg-cache",
                      FFBUILD_REPAIR_CACHE=f"{temp}/ffbuild/vcpkg-cache",
                      FFBUILD_DOWNLOADS_DIR=f"{root}/downloads",
                      FFBUILD_REPAIR_DIR=f"{temp}/ffheal")
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as output:
            for key, value in values.items():
                if "\n" in value or "\r" in value:
                    raise ValueError(f"Multiline CI setting: {key}")
                output.write(f"{key}={value}\n")
        if "GITHUB_OUTPUT" in os.environ:
            _cache_outputs({"vcpkg_tag": values["VCPKG_TAG"], "vcpkg_root": values["VCPKG_ROOT"],
                            "cache_dir": values["FFBUILD_CACHE_DIR"],
                            "downloads_dir": values["FFBUILD_DOWNLOADS_DIR"],
                            "repair_dir": values["FFBUILD_REPAIR_DIR"]})
    elif args.command == "plan":
        plan_release()
    elif args.command == "download":
        download_sources()
    elif args.command == "prepare-cache":
        _cache_outputs({"save_key": prepare_cache(args.triplet, args.expected, matched_key=args.matched_key)})
    elif args.command == "worker-build":
        worker_build()
    elif args.command == "worker-package":
        worker_package()
    elif args.command == "repair-cache-plan":
        _cache_outputs(repair_cache_plan(json.loads(os.environ[args.triplets_env])))
    elif args.command == "submit-dependencies":
        runtime = Path(os.environ.get("RUNNER_TEMP", str(Path(__file__).resolve().parents[2] / "_work"))) / "ffbuild"
        submit_dependencies(vcpkg_root=Path(os.environ.get("VCPKG_ROOT", str(runtime / "vcpkg"))), triplet=args.triplet)
    elif args.command == "prepare-host":
        from .targets import configured_triplets
        triplets = configured_triplets() if args.configured else (args.triplet,)
        if "arm-windows" in triplets:
            patch_arm_sdk()
    elif args.command == "seed-identity":
        keys, downloads = seed_plans(args.triplet, evidence=args.evidence, output=args.plan_file,
                                     target_evidence=args.target_evidence, binary=args.vcpkg_bin,
                                     read_plan=args.read_plan, expected=args.expected, cache_dir=args.cache_dir)
        print(json.dumps(keys, sort_keys=True))
        if args.github_output:
            _cache_outputs({"seed_keys": json.dumps(keys, separators=(",", ":")), "download_specs": downloads})
    elif args.command == "compare-abi":
        from .native_abi import compare_abi_evidence
        report = json.dumps(compare_abi_evidence(args.before, args.after), indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report + "\n", encoding="utf-8")
        print(report)
    elif args.command == "restore-dependencies":
        from .cache_guard import load_job, restore_dependencies
        from .port import ffmpeg_port_name
        from .versions import GENERATED_PORTS
        from .native_abi import require_planned_abi
        job = load_job(args.job_env)
        require_planned_abi(job)
        root = Path(os.environ["VCPKG_ROOT"])
        cache = args.cache_dir or Path(os.environ["FFBUILD_CACHE_DIR"])
        env = dict(os.environ, VCPKG_BINARY_SOURCES=f"clear;files,{cache.resolve()},read")
        restore_dependencies(job, cache, port=GENERATED_PORTS / ffmpeg_port_name(job["yaml"]),
                             installed=root / "installed", paths=[f"--x-install-root={root / 'installed'}"], env=env,
                             evidence=args.abi_evidence)
    elif args.command == "audit-worker":
        from .cache_guard import load_job, verify_no_dependency_builds
        verify_no_dependency_builds(load_job(args.job_env), args.buildtrees or Path(os.environ["VCPKG_ROOT"]) / "buildtrees")
    elif args.command in ("verify-sdk", "verify-installed-sdk"):
        from .sdk_validation import validate_directory, validate_installed
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.unlink(missing_ok=True)
        try:
            if args.command == "verify-sdk":
                pkgconf = args.pkgconf
                if pkgconf is None and os.environ.get("GITHUB_ACTIONS") == "true":
                    pkgconf = Path(os.environ["VCPKG_ROOT"]) / "installed/x64-windows/tools/pkgconf/pkgconf.exe"
                results = validate_directory(args.artifacts_dir, generator=args.generator, pkgconf=pkgconf)
            else:
                from .cache_guard import load_job
                job = load_job(args.job_env)
                installed_root = args.installed_root or Path(os.environ["VCPKG_ROOT"]) / "installed"
                pkgconf = args.pkgconf or installed_root / "x64-windows/tools/pkgconf/pkgconf.exe"
                results = validate_installed(installed_root / job["triplet"], triplet=job["triplet"],
                                             linkage=job["linkage"], features=job["features"],
                                             generator=args.generator, pkgconf=pkgconf)
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
