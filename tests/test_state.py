import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wox_stopwatch.state import StateStore, Stopwatch, format_duration  # noqa: E402


class StopwatchTest(unittest.TestCase):
    def test_start_pause_resume_accumulates(self):
        sw = Stopwatch()
        sw.start(now=100.0)
        self.assertAlmostEqual(sw.elapsed(now=105.0), 5.0)
        sw.pause(now=105.0)
        self.assertAlmostEqual(sw.elapsed(now=200.0), 5.0)
        sw.start(now=200.0)
        self.assertAlmostEqual(sw.elapsed(now=202.5), 7.5)

    def test_laps_and_splits(self):
        sw = Stopwatch()
        sw.start(now=0.0)
        sw.lap(now=3.0)
        sw.lap(now=10.0)
        self.assertEqual(sw.laps, [3.0, 10.0])
        self.assertEqual(sw.lap_splits(), [3.0, 7.0])

    def test_lap_ignored_when_paused(self):
        sw = Stopwatch()
        sw.lap(now=1.0)
        self.assertEqual(sw.laps, [])

    def test_reset(self):
        sw = Stopwatch()
        sw.start(now=0.0)
        sw.lap(now=1.0)
        sw.reset()
        self.assertEqual(sw.status, "idle")
        self.assertEqual(sw.elapsed(), 0.0)
        self.assertEqual(sw.laps, [])

    def test_status(self):
        sw = Stopwatch()
        self.assertEqual(sw.status, "idle")
        sw.start(now=0.0)
        self.assertEqual(sw.status, "running")
        sw.pause(now=1.0)
        self.assertEqual(sw.status, "paused")


class FormatTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_duration(0), "00:00.00")
        self.assertEqual(format_duration(61.239), "01:01.23")
        self.assertEqual(format_duration(3723.5, 1), "1:02:03.5")
        self.assertEqual(format_duration(59.99, 0), "00:59")
        self.assertEqual(format_duration(-3), "00:00.00")


class StateStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = StateStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        self.store.update(lambda sw: (sw.start(now=10.0), sw.lap(now=12.0)))
        loaded = self.store.load()
        self.assertTrue(loaded.running)
        self.assertEqual(loaded.started_at, 10.0)
        self.assertEqual(loaded.laps, [2.0])

    def test_missing_or_corrupt_file_gives_fresh_stopwatch(self):
        self.assertEqual(self.store.load(), Stopwatch())
        with open(self.store.state_path, "w") as f:
            f.write("{not json")
        self.assertEqual(self.store.load(), Stopwatch())

    def test_window_heartbeat(self):
        self.assertFalse(self.store.is_window_open())
        self.store.write_heartbeat(123)
        self.assertTrue(self.store.is_window_open())
        self.store.clear_heartbeat()
        self.assertFalse(self.store.is_window_open())

    def test_window_command(self):
        self.store.send_window_command("raise")
        self.assertEqual(self.store.read_window_command()["command"], "raise")


if __name__ == "__main__":
    unittest.main()
