"""Bounded subprocess execution for SDK and native contract validation."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile


def run_bounded(args, *, env=None, cwd=None, check=False, timeout=None):
    """Run a non-interactive command with bounded process-tree lifetime."""
    args = [str(a) for a in args]
    env = dict(os.environ if env is None else env)
    env["MSBUILDDISABLENODEREUSE"] = "1"
    if timeout is None:
        timeout = 120 if "--build" in args else 60
    # Files, not pipes: an exited MSBuild child cannot keep communicate()
    # blocked by retaining a pipe handle. Disable node reuse as well.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        p = subprocess.Popen(args, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                             stdout=stdout, stderr=stderr,
                             start_new_session=(os.name != "nt"))
        expired = False
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            expired = True
            if os.name == "nt":
                try:
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            else:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if p.poll() is None:
                p.kill()
            p.wait(timeout=10)
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if expired:
            raise subprocess.TimeoutExpired(args, timeout, output=out, stderr=err)
        result = subprocess.CompletedProcess(args, p.returncode, out, err)
        if check:
            result.check_returncode()
        return result
