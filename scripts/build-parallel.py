#!/usr/bin/env python3
"""
build-parallel.py — topo-sort vcpkg dependency graph and build in parallel.

Usage:
  python build-parallel.py build [pkg[:triplet]] [-j N] [--keep] [--dry-run]
                [--triplet T] [--vcpkg PATH] [--tmp DIR] -- [vcpkg-opts...]
  python build-parallel.py export [pkg[:triplet]] [--triplet T]
                [--vcpkg PATH] [--tmp DIR] [-o FILE] -- [vcpkg-opts...]

Triplet priority: --triplet flag > pkg:triplet suffix > None (host).
"""

import argparse
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_DEFAULT_TMP = str(Path(os.environ.get("TMP") or os.environ.get("TEMP") or "/tmp") / "vcpkg-parallel")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    vcpkg_opts: list[str] = []
    try:
        idx = argv.index("--")
        vcpkg_opts = argv[idx + 1 :]
        argv = argv[:idx]
    except ValueError:
        pass

    parser = argparse.ArgumentParser(
        description="Build vcpkg ports in topologically-parallel layers."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("pkg", nargs="?", default=None)
    common.add_argument("--vcpkg", default="vcpkg")
    common.add_argument("--tmp", default=_DEFAULT_TMP)
    common.add_argument("--triplet", default=None)

    pbuild = sub.add_parser("build", parents=[common])
    pbuild.add_argument("-j", type=int, default=os.cpu_count() or 4)
    pbuild.add_argument("--keep", action="store_true")
    pbuild.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing")
    pbuild.add_argument("--fetch-first", action="store_true",
                        help="Download all sources sequentially before parallel build")

    pexport = sub.add_parser("export", parents=[common])
    pexport.add_argument("-o", default="Makefile")

    return parser.parse_args(argv), vcpkg_opts


def resolve_triplet(
    pkg: str | None, triplet: str | None, vcpkg_opts: list[str]
) -> tuple[str | None, str | None, list[str]]:
    resolved = triplet
    if resolved is None and pkg and ":" in pkg:
        pkg, resolved = pkg.rsplit(":", 1)
    if resolved:
        vcpkg_opts = ["--triplet", resolved] + vcpkg_opts
    return pkg, resolved, vcpkg_opts


# ---------------------------------------------------------------------------
# depend-info
# ---------------------------------------------------------------------------

LINE_RE = re.compile(r"^(\S+?)(?:\s*:\s*(.*))?$")
DEP_SPLIT_RE = re.compile(r",\s*")
HOST_RE = re.compile(r":host\b")


def run_depend_info(vcpkg: str, pkg: str | None, vcpkg_opts: list[str]) -> str:
    cmd = [vcpkg, "depend-info", "--sort=topological"]
    if pkg:
        cmd.append(pkg)
    cmd.extend(vcpkg_opts)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ERROR] depend-info failed (rc={proc.returncode}):\n{proc.stderr}", file=sys.stderr)
        sys.exit(proc.returncode)
    return proc.stdout or proc.stderr


def _strip_host(name: str) -> str:
    return HOST_RE.sub("", name).strip()


def parse_dag(raw: str) -> dict[str, list[str]]:
    dag: dict[str, list[str]] = {}

    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue

        target_raw = m.group(1).strip()
        deps_raw = m.group(2) or ""

        target = _strip_host(target_raw)

        deps: list[str] = []
        for d in DEP_SPLIT_RE.split(deps_raw):
            d = d.strip()
            if not d:
                continue
            dep = _strip_host(d)
            if dep:
                deps.append(dep)

        dag[target] = deps

    return dag


# ---------------------------------------------------------------------------
# shared
# ---------------------------------------------------------------------------

def port_safe(name: str) -> str:
    return name.replace("[", "-").replace("]", "").replace(",", "-")


def vcpkg_install_cmd(
    vcpkg: str, port: str, vcpkg_opts: list[str], tmp: str, keep: bool
) -> tuple[list[str], Path]:
    safe = port_safe(port)
    bt = Path(tmp) / "buildtrees" / safe
    pk = Path(tmp) / "packages" / safe
    installed = Path(tmp) / "installed" / safe
    cwd = Path(tmp) / safe
    cmd = [vcpkg, "install", port] + vcpkg_opts + [
        "--x-buildtrees-root", str(bt),
        "--x-packages-root", str(pk),
        "--x-install-root", str(installed),
    ]
    if not keep:
        cmd.append("--clean-after-build")
    return cmd, cwd


def makefile_escape(s: str) -> str:
    return s.replace("$", "$$")


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def cmd_build(
    vcpkg: str, pkg: str | None, vcpkg_opts: list[str],
    j: int, tmp: str, keep: bool, dry_run: bool = False,
    fetch_first: bool = False,
) -> None:
    print("=== build-parallel build ===")
    if dry_run:
        print("  (dry-run)")
    print(f"  parallel: {j}")
    print(f"  tmp: {tmp}")
    print(f"  keep: {keep}")
    print()

    raw = run_depend_info(vcpkg, pkg, vcpkg_opts)
    dag = parse_dag(raw)

    if not dag:
        print("[ERROR] empty dependency graph", file=sys.stderr)
        sys.exit(1)

    # Build in-degree and dependents maps
    pending: dict[str, int] = {}
    dependents: dict[str, list[str]] = defaultdict(list)
    for node, deps in dag.items():
        pending[node] = len(deps)
        for d in deps:
            dependents[d].append(node)

    # Ensure deps without own entry exist
    for deps in dag.values():
        for d in deps:
            if d not in pending:
                pending[d] = 0

    total = len(pending)
    print(f"  ports: {total}")

    ready: list[str] = [p for p, n in pending.items() if n == 0]
    if not ready:
        print("[ERROR] no leaf ports (circular dependency?)", file=sys.stderr)
        sys.exit(1)

    print(f"  ready: {len(ready)}")

    # Id -> cmd mapping (safe name → original for display)
    id_to_cmd: dict[str, tuple[list[str], Path]] = {}
    for port in dag:
        id_to_cmd[port_safe(port)] = vcpkg_install_cmd(vcpkg, port, vcpkg_opts, tmp, keep)
    for port in pending:
        if port_safe(port) not in id_to_cmd:
            id_to_cmd[port_safe(port)] = vcpkg_install_cmd(vcpkg, port, vcpkg_opts, tmp, keep)

    # ── Fetch-first: download sources sequentially ──────────────────────────
    if fetch_first:
        cmd = [vcpkg, "install"] + ([pkg] if pkg else []) + ["--only-downloads"] + vcpkg_opts
        if dry_run:
            print(" ".join(cmd))
        else:
            subprocess.run(cmd, check=True)

    if dry_run:
        print()
        for port, (cmd, _cwd) in id_to_cmd.items():
            print(" ".join(cmd))
        print(f"\n=== Dry-run: {total} port(s) ===")
        return

    fail = threading.Event()
    procs: set[subprocess.Popen] = set()
    procs_lock = threading.Lock()
    lock = threading.Lock()
    pending_local: dict[str, int] = dict(pending)
    done_count = 0

    def on_sigint(_sig, _frame):
        print("\n[ABORT] Ctrl+C — terminating vcpkg processes...", file=sys.stderr)
        fail.set()
        with procs_lock:
            for p in list(procs):
                p.terminate()

    signal.signal(signal.SIGINT, on_sigint)

    def task(port: str):
        nonlocal done_count
        if fail.is_set():
            return

        entry = id_to_cmd.get(port_safe(port))
        if not entry:
            with lock:
                done_count += 1
                print(f"  [{done_count}/{total}] MISS {port}")
            fail.set()
            return

        cmd, cwd = entry
        cwd.mkdir(parents=True, exist_ok=True)
        with lock:
            print(f"  [start] {port}")
        proc = subprocess.Popen(cmd, cwd=str(cwd))
        with procs_lock:
            procs.add(proc)
        rc = proc.wait()
        with procs_lock:
            procs.discard(proc)

        ok = rc == 0

        with lock:
            done_count += 1
            status = "OK" if ok else "FAIL"
            print(f"  [{done_count}/{total}] {status} {port}")

        if not ok:
            fail.set()
            return

        # Signal dependents
        for dep in dependents.get(port, []):
            with lock:
                pending_local[dep] -= 1
                if pending_local[dep] == 0 and not fail.is_set():
                    executor.submit(task, dep)

    executor = ThreadPoolExecutor(max_workers=j)
    for port in ready:
        executor.submit(task, port)

    try:
        while not fail.is_set() and not done_count >= total:
            time.sleep(0.1)
    except KeyboardInterrupt:
        fail.set()
        with procs_lock:
            for p in list(procs):
                p.terminate()

    executor.shutdown(wait=False, cancel_futures=True)
    time.sleep(1)
    with procs_lock:
        for p in list(procs):
            p.kill()

    if fail.is_set():
        print(f"\n[ABORT] aborted", file=sys.stderr)
        sys.exit(130)

    print(f"\n=== All {total} port(s) built successfully ===")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def cmd_export(
    vcpkg: str, pkg: str | None, vcpkg_opts: list[str],
    tmp: str, outfile: str,
) -> None:
    print(f"=== build-parallel export -> {outfile} ===")

    raw = run_depend_info(vcpkg, pkg, vcpkg_opts)
    dag = parse_dag(raw)

    if not dag:
        print("[ERROR] empty dependency graph", file=sys.stderr)
        sys.exit(1)

    all_targets = list(dag.keys())
    root = port_safe(pkg) if pkg else " ".join(port_safe(p) for p in all_targets)

    # Collect unique safe names (sort for determinism)
    safe_set: dict[str, str] = {}  # safe → original port name
    for port in all_targets:
        safe = port_safe(port)
        safe_set[safe] = port
    sorted_safes = sorted(safe_set)

    escaped_vcpkg = makefile_escape(vcpkg)
    escaped_tmp = makefile_escape(tmp)
    escaped_opts = " ".join(makefile_escape(o) for o in vcpkg_opts)

    lines: list[str] = []
    lines.append("# Generated by build-parallel.py")
    lines.append("")
    lines.append(f"VCPKG    ?= {escaped_vcpkg}")
    lines.append(f"TMP      ?= {escaped_tmp}")
    lines.append(f"VCPKG_OPTS = {escaped_opts}")
    lines.append("KEEP     ?= 0")
    lines.append("ifeq ($(KEEP),1)")
    lines.append("CLEAN = ")
    lines.append("else")
    lines.append("CLEAN = --clean-after-build")
    lines.append("endif")
    lines.append("")
    lines.append("BT = --x-buildtrees-root=$(TMP)/buildtrees/$(@F)")
    lines.append("PK = --x-packages-root=$(TMP)/packages/$(@F)")
    lines.append("INSTALL_DIR = --x-install-root=$(TMP)/installed/$(@F)")
    lines.append("")

    # TARGETS variable
    lines.append("TARGETS := \\")
    for i, safe in enumerate(sorted_safes):
        sep = " \\" if i < len(sorted_safes) - 1 else ""
        lines.append(f"           {safe}{sep}")
    lines.append("")

    lines.append(".PHONY: all $(TARGETS)")
    lines.append("")
    lines.append(f"all: {root}")
    lines.append("")

    # PORT mapping (safe → original, only where different)
    for safe in sorted_safes:
        orig = safe_set[safe]
        if safe != orig:
            lines.append(f"{safe}: PORT = {orig}")

    if any(safe != safe_set[safe] for safe in sorted_safes):
        lines.append("")

    # Static pattern rule
    lines.append("$(TARGETS): %:")
    lines.append("\t$(VCPKG) install '$(or $(PORT),$@)' $(VCPKG_OPTS) $(BT) $(PK) $(INSTALL_DIR) $(CLEAN)")
    lines.append("")

    # Dependencies only
    for port in all_targets:
        safe = port_safe(port)
        deps = dag.get(port, [])
        dep_list = " ".join(port_safe(d) for d in deps)
        if dep_list:
            lines.append(f"{safe}: {dep_list}")

    lines.append("")

    with open(outfile, "w") as f:
        f.write("\n".join(lines))

    print(f"  ports: {len(all_targets)}")
    print(f"  -> {outfile}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parsed, vcpkg_opts = parse_args(sys.argv[1:])
    pkg, triplet, vcpkg_opts = resolve_triplet(parsed.pkg, parsed.triplet, vcpkg_opts)

    if parsed.command == "build":
        cmd_build(
            vcpkg=parsed.vcpkg, pkg=pkg, vcpkg_opts=vcpkg_opts,
            j=parsed.j, tmp=parsed.tmp, keep=parsed.keep,
            dry_run=parsed.dry_run,
            fetch_first=parsed.fetch_first,
        )
    else:
        cmd_export(
            vcpkg=parsed.vcpkg, pkg=pkg, vcpkg_opts=vcpkg_opts,
            tmp=parsed.tmp, outfile=parsed.o,
        )


if __name__ == "__main__":
    main()
