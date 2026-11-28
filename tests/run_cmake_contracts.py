"""Strict local/CI-ready CMake contract test runner; no silent prerequisite skips.

All tiers require native Windows. Native tier requires VS 2022,
pinned vcpkg helpers, GNU bash/make and native lib.exe. Real tier also
requires a previously compiled shared package and its installed prefix.
"""
import argparse
import contextlib
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
import sys
import subprocess
import tempfile
import time
import fnmatch
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ffbuild.process import run_bounded

QUICK = (
    "test_cmake_test_process", "test_cmake_test_runner",
    "test_cmake_consumer", "test_cmake_dependencies", "test_cmake_blackbox",
    "test_cmake_sdk_contract", "test_shared_pkgconfig", "test_debug_addon",
    "test_build_recipe_parity", "test_build_system_boundary",
)
NATIVE = ("test_cmake_msvc", "test_cmake_port_contract", "test_cmake_blackbox_msvc")
REAL = ("test_cmake_real_sdk",)
REAL_STATIC = ("test_cmake_real_static_sdk",)


class ContractResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failed_methods = set()
        self.skipped_methods = set()
        self.durations = {}
        self.started_methods = set()

    def startTest(self, test):
        self._started = time.monotonic()
        self.started_methods.add(test.id())
        super().startTest(test)

    def stopTest(self, test):
        elapsed = round(time.monotonic() - self._started, 3)
        self.durations[test.id()] = elapsed
        self.stream.writeln(f"  [{elapsed:.3f}s]")
        super().stopTest(test)

    def addFailure(self, test, err):
        self.failed_methods.add(test.id())
        super().addFailure(test, err)

    def addError(self, test, err):
        self.failed_methods.add(test.id())
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        if err:
            self.failed_methods.add(test.id())
        super().addSubTest(test, subtest, err)

    def addSkip(self, test, reason):
        self.skipped_methods.add(test.id())
        super().addSkip(test, reason)

    def addUnexpectedSuccess(self, test):
        self.failed_methods.add(test.id())
        super().addUnexpectedSuccess(test)

    def addExpectedFailure(self, test, err):
        self.failed_methods.add(test.id())
        super().addExpectedFailure(test, err)



def iter_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def group_tests(suite):
    """Keep class/module-scoped fixtures together, otherwise shard by method.

    Each group is run in a separate process (not threads). Tests may mutate
    their own environment, redirect streams or use unittest fixture state.
    """
    groups = {}
    for test in iter_tests(suite):
        cls = type(test)
        module = sys.modules.get(cls.__module__)
        name = test.id()
        if module and any(callable(getattr(module, attr, None))
                          for attr in ("setUpModule", "tearDownModule")):
            key = ("module", cls.__module__)
        elif (cls.setUpClass.__func__ is not unittest.TestCase.setUpClass.__func__
              or cls.tearDownClass.__func__ is not unittest.TestCase.tearDownClass.__func__):
            key = ("class", cls.__module__, cls.__qualname__)
        else:
            key = ("test", name)
        groups.setdefault(key, []).append(name)
    return list(groups.values())


def run_group(names):
    """Return serializable unittest evidence; never share fixture state."""
    started = time.monotonic()
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        suite = unittest.defaultTestLoader.loadTestsFromNames(names)
        result = unittest.TextTestRunner(stream=stream, verbosity=2,
                                         resultclass=ContractResult).run(suite)
    failed = result.failed_methods
    skipped = result.skipped_methods
    return {
        "tests": names,
        "executed_methods": result.testsRun,
        "started_methods": sorted(result.started_methods),
        "failed_methods": sorted(failed),
        "skipped_methods": sorted(skipped),
        "passed_methods": len(result.started_methods - failed - skipped),
        "failure_assertions": len(result.failures),
        "errors": len(result.errors),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "skips": len(result.skipped),
        "test_durations_seconds": result.durations,
        "worker_pid": os.getpid(),
        "started": started,
        "finished": time.monotonic(),
        "log": stream.getvalue(),
    }


def is_native(group):
    return any(name.split(".", 1)[0] in NATIVE + REAL + REAL_STATIC for name in group)


def run_group_isolated(names, timeout):
    """Run one fixture group in a bounded, independently killable process."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ffmpeg-contract-worker-") as directory:
        result_file = Path(directory) / "result.json"
        command = [sys.executable, str(Path(__file__).resolve()), "--_worker",
                   str(result_file), *names]
        try:
            process = run_bounded(command, timeout=timeout)
            if process.returncode or not result_file.is_file():
                raise RuntimeError(f"worker exit {process.returncode}: "
                                   + process.stdout + process.stderr)
            result = json.loads(result_file.read_text(encoding="utf-8"))
            if result["tests"] != names:
                raise RuntimeError("worker returned a different test group")
            return result
        except subprocess.TimeoutExpired as exc:
            error = f"Worker group timed out after {timeout:g}s: {', '.join(names)}"
            log = (exc.output or "") + (exc.stderr or "")
        except Exception as exc:
            error = f"Worker failed: {exc!r}"
            log = ""
        return {"tests": names, "worker_error": error,
                "started": started, "finished": time.monotonic(),
                "log": error + "\n" + log}


def execute_groups(groups, jobs, native_jobs, group_timeout=300):
    """Separate capacity for lightweight probes and compiler/Port workloads."""
    if jobs == 1:
        for group in groups:
            yield run_group_isolated(group, group_timeout)
        return

    native = [g for g in groups if is_native(g)]
    # Start expensive real SDK and native compiler cases before short Port
    # probes. Otherwise the longest tests become a serial tail.
    priority = {module: i for i, module in enumerate(REAL + REAL_STATIC + ("test_cmake_blackbox_msvc", "test_cmake_msvc", "test_cmake_port_contract"))}
    native.sort(key=lambda g: min(priority[name.split(".", 1)[0]] for name in g))
    quick = [g for g in groups if not is_native(g)]
    n = min(native_jobs, jobs - bool(quick), len(native))
    q = min(jobs - n, len(quick))
    n = min(native_jobs, jobs - q, len(native))
    # Threads only supervise subprocesses. Every test group gets a fresh
    # interpreter and its own deadline; no ProcessPool shutdown can wait
    # indefinitely on a stuck Python fixture.
    with contextlib.ExitStack() as stack:
        futures = {}
        for shards, workers in ((quick, q), (native, n)):
            if not shards:
                continue
            pool = stack.enter_context(ThreadPoolExecutor(max_workers=workers))
            for group in shards:
                futures[pool.submit(run_group_isolated, group, group_timeout)] = group
        for future in as_completed(futures):
            group = futures[future]
            try:
                yield future.result()
            except Exception as exc:
                yield {"tests": group, "worker_error": repr(exc),
                       "log": f"Worker failed for {group!r}: {exc!r}\n"}


def peak_parallel(results):
    events = [(r[key], delta) for r in results if "started" in r
              for key, delta in (("started", 1), ("finished", -1))]
    current = peak = 0
    for _, delta in sorted(events):
        current += delta
        peak = max(peak, current)
    return peak


def aggregate(results, planned):
    report = {key: sum(r.get(key, 0) for r in results) for key in
              ("executed_methods", "passed_methods", "failure_assertions", "errors",
               "expected_failures", "unexpected_successes", "skips")}
    for key in ("failed_methods", "skipped_methods"):
        report[key] = sorted({name for r in results for name in r.get(key, [])})
    started = {name for r in results for name in r.get("started_methods", [])}
    report["not_run_methods"] = sorted(set(planned) - started)
    report["worker_errors"] = [r["worker_error"] for r in results if "worker_error" in r]
    report["test_durations_seconds"] = {
        name: seconds for r in results for name, seconds in r.get("test_durations_seconds", {}).items()
    }
    report["planned_methods"] = len(planned)
    report["parallel_peak"] = peak_parallel(results)
    report["native_parallel_peak"] = peak_parallel([r for r in results if is_native(r["tests"])])
    report["passed"] = (report["executed_methods"] == len(planned)
                        and report["passed_methods"] == len(planned)
                        and not report["not_run_methods"] and not report["worker_errors"]
                        and not any(report[key] for key in
                                    ("failure_assertions", "errors", "expected_failures",
                                     "unexpected_successes", "skips")))
    return report


def main():
    # Private entry point used only by the isolated group supervisor.
    if len(sys.argv) >= 4 and sys.argv[1] == "--_worker":
        result_file = Path(sys.argv[2])
        result = run_group(sys.argv[3:])
        result_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("quick", "native", "real", "real-static"), default="quick")
    parser.add_argument("--module", action="append", choices=QUICK + NATIVE + REAL + REAL_STATIC,
                        help="Run only selected modules within the tier; repeatable")
    parser.add_argument("--match", help="Select test IDs by shell wildcard within selected modules")
    parser.add_argument("--jobs", "-j", type=int, default=min(8, os.cpu_count() or 1),
                        help="Total concurrent test processes (default: up to 8)")
    parser.add_argument("--native-jobs", type=int, default=2,
                        help="Maximum concurrent native/Port test processes (default: 2)")
    parser.add_argument("--group-timeout", type=float, default=300,
                        help="Hard deadline for each isolated test group in seconds (default: 300)")
    parser.add_argument("--report", type=Path, help="Optional JSON result report")
    args = parser.parse_args()
    if args.jobs < 1 or args.native_jobs < 1 or not 0 < args.group_timeout < float("inf"):
        parser.error("Concurrency and finite group timeout must be positive")

    if os.name != "nt":
        parser.error("MSVC SDK contracts require a native Windows host")
    pkgconf = os.environ.get("FFBUILD_TEST_PKGCONF") or shutil.which("pkgconf")
    if not pkgconf or not Path(pkgconf).is_file() or not shutil.which("cmake") or not shutil.which("ninja"):
        parser.error("CMake, Ninja and real pkgconf are required; set FFBUILD_TEST_PKGCONF if necessary")
    os.environ["FFBUILD_TEST_PKGCONF"] = str(Path(pkgconf).resolve())
    modules = list(QUICK)
    if args.tier != "quick":
        if os.name != "nt":
            parser.error("Native contracts require Windows and Visual Studio 2022")
        os.environ["FFBUILD_TEST_MSVC"] = "1"
        modules += NATIVE
    if args.tier == "real":
        for name in ("FFBUILD_TEST_REAL_PACKAGE", "FFBUILD_TEST_REAL_INSTALLED"):
            if not os.environ.get(name) or not Path(os.environ[name]).is_dir():
                parser.error(name + " must point to an existing native build")
        modules += REAL
    if args.tier == "real-static":
        for name in ("FFBUILD_TEST_REAL_STATIC_PACKAGE", "FFBUILD_TEST_REAL_STATIC_INSTALLED"):
            if not os.environ.get(name) or not Path(os.environ[name]).is_dir():
                parser.error(name + " must point to an existing locally built static Port installation")
        modules += REAL_STATIC

    if args.module:
        if not set(args.module).issubset(modules):
            parser.error("Selected module is outside the requested tier")
        modules = list(dict.fromkeys(args.module))
    # Only require tooling used by the selected tests. Real installed SDK
    # acceptance requires actual compiler and pkgconf, not a Port mock shell.
    if any(module in NATIVE for module in modules):
        from test_cmake_port_contract import BASH, HAVE_HELPERS, NATIVE_LIB
        if not HAVE_HELPERS or not BASH or not Path(BASH).is_file() or not NATIVE_LIB or not Path(NATIVE_LIB).is_file():
            parser.error("Set FFBUILD_TEST_VCPKG_ROOT, FFBUILD_TEST_LIB_EXE and, if needed, FFBUILD_TEST_BASH")
        if not Path(NATIVE_LIB).with_name("dumpbin.exe").is_file():
            parser.error("Native dumpbin.exe must be available alongside lib.exe")
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    if args.match:
        suite = unittest.TestSuite(test for test in iter_tests(suite)
                                   if fnmatch.fnmatchcase(test.id(), args.match))
    if not suite.countTestCases():
        parser.error("No matching tests")
    if unittest.defaultTestLoader.errors:
        parser.error("\n".join(unittest.defaultTestLoader.errors))
    os.environ["MSBUILDDISABLENODEREUSE"] = "1"
    planned = [test.id() for test in iter_tests(suite)]
    groups = group_tests(suite)
    print(f"Running {len(planned)} tests in {len(groups)} independent groups "
          f"(jobs={args.jobs}, native-jobs={args.native_jobs})", flush=True)
    started = time.monotonic()
    results = []
    for result in execute_groups(groups, args.jobs, args.native_jobs, args.group_timeout):
        results.append(result)
        print(result.pop("log"), end="", flush=True)
    report = {
        "tier": args.tier,
        "modules": modules,
        "match": args.match,
        "jobs": args.jobs,
        "native_jobs": args.native_jobs,
        "group_timeout": args.group_timeout,
        "duration_seconds": round(time.monotonic() - started, 3),
        **aggregate(results, planned),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
