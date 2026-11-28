"""Verify parallel runner planning and strict aggregate evidence."""
import sys
import time
import unittest
from unittest.mock import patch

from run_cmake_contracts import aggregate, execute_groups, group_tests, peak_parallel


class ParallelRunnerContract(unittest.TestCase):
    def test_independent_methods_are_separate_groups(self):
        class Independent(unittest.TestCase):
            def test_a(self): pass
            def test_b(self): pass
        tests = [Independent("test_a"), Independent("test_b")]
        self.assertEqual([[t.id()] for t in tests], group_tests(unittest.TestSuite(tests)))

    def test_shared_class_fixture_remains_one_group(self):
        class Shared(unittest.TestCase):
            @classmethod
            def setUpClass(cls): pass
            def test_a(self): pass
            def test_b(self): pass
        tests = [Shared("test_a"), Shared("test_b")]
        self.assertEqual([[t.id() for t in tests]], group_tests(unittest.TestSuite(tests)))

    def test_module_fixture_remains_one_group(self):
        class First(unittest.TestCase):
            def test_a(self): pass
        class Second(unittest.TestCase):
            def test_b(self): pass
        tests = [First("test_a"), Second("test_b")]
        with patch.object(sys.modules[__name__], "setUpModule", lambda: None, create=True):
            self.assertEqual([[t.id() for t in tests]], group_tests(unittest.TestSuite(tests)))

    def test_overlapping_intervals_measure_actual_parallelism(self):
        self.assertEqual(2, peak_parallel([
            {"started": 0, "finished": 2},
            {"started": 1, "finished": 3},
            {"started": 2, "finished": 4},
        ]))

    def test_aggregation_rejects_missing_tests_and_worker_errors(self):
        passed = {"tests": ["a"], "started_methods": ["a"],
                  "executed_methods": 1, "passed_methods": 1}
        report = aggregate([passed, {"tests": ["b"], "worker_error": "crash"}], ["a", "b"])
        self.assertFalse(report["passed"])
        self.assertEqual(["b"], report["not_run_methods"])
        self.assertEqual(["crash"], report["worker_errors"])
        self.assertEqual(1, report["passed_methods"])

    def test_aggregation_preserves_subtest_failures_and_skips(self):
        results = [
            {"tests": ["a"], "started_methods": ["a"], "executed_methods": 1,
             "passed_methods": 0, "failed_methods": ["a"], "failure_assertions": 3},
            {"tests": ["b"], "started_methods": ["b"], "executed_methods": 1,
             "passed_methods": 0, "skipped_methods": ["b"], "skips": 1},
        ]
        report = aggregate(results, ["a", "b"])
        self.assertFalse(report["passed"])
        self.assertEqual(3, report["failure_assertions"])
        self.assertEqual(["a"], report["failed_methods"])
        self.assertEqual(["b"], report["skipped_methods"])
        self.assertEqual([], report["not_run_methods"])

    def test_aggregation_accepts_complete_success(self):
        report = aggregate([{"tests": ["a"], "started_methods": ["a"],
                             "executed_methods": 1, "passed_methods": 1}], ["a"])
        self.assertTrue(report["passed"])


    def test_hung_worker_does_not_block_parallel_success_or_report_pass(self):
        slow = "fixtures.cmake_runner_probe.WorkerProbe.test_hangs"
        fast = "fixtures.cmake_runner_probe.WorkerProbe.test_succeeds"
        started = time.monotonic()
        results = list(execute_groups([[slow], [fast]], jobs=2, native_jobs=1, group_timeout=4))
        report = aggregate(results, [slow, fast])
        self.assertFalse(report["passed"])
        self.assertEqual(1, report["passed_methods"])
        self.assertEqual([slow], report["not_run_methods"])
        self.assertEqual(1, len(report["worker_errors"]))
        self.assertIn("timed out", report["worker_errors"][0])
        self.assertLess(time.monotonic() - started, 20)
