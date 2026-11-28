"""Regression for bounded execution and non-interactive native test processes."""
import os
import subprocess
import sys
import time
import unittest

from cmake_blackbox_fixture import run


class TestCommandContract(unittest.TestCase):
    def test_exit_code_output_and_stdin(self):
        result = run([sys.executable, "-c",
                      "import os,sys; assert sys.stdin.read()==''; "
                      "assert os.environ['MSBUILDDISABLENODEREUSE']=='1'; "
                      "print('stdout'); print('stderr',file=sys.stderr); sys.exit(7)"])
        self.assertEqual(7, result.returncode)
        self.assertEqual("stdout", result.stdout.strip())
        self.assertEqual("stderr", result.stderr.strip())

    def test_timeout_is_bounded_and_retains_output(self):
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            run([sys.executable, "-u", "-c",
                 "import time; print('started',flush=True); time.sleep(60)"], timeout=1)
        self.assertIn("started", caught.exception.output)
        self.assertLess(time.monotonic() - started, 15)

    def test_inherited_child_output_handle_cannot_block_parent_exit(self):
        # The child deliberately outlives the command and inherits stdout.
        # An ordinary pipe reader waits for EOF from both processes.
        started = time.monotonic()
        result = run([sys.executable, "-c",
                      "import subprocess,sys; subprocess.Popen([sys.executable,"
                      "'-c','import time; time.sleep(5)']); print('parent exited')"],
                     timeout=3)
        self.assertEqual(0, result.returncode)
        self.assertIn("parent exited", result.stdout)
        self.assertLess(time.monotonic() - started, 4)
