"""Non-discovered probes used to test hard worker deadlines."""
import time
import unittest


class WorkerProbe(unittest.TestCase):
    def test_hangs(self):
        time.sleep(60)

    def test_succeeds(self):
        self.assertTrue(True)
