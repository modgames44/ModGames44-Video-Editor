"""Reloj maestro de reproducción (audio como referencia)."""
import unittest

from timeline.playback_clock import MasterClock, needs_video_resync


class FakeTime:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class MasterClockTests(unittest.TestCase):
    def setUp(self):
        self.time = FakeTime()
        self.clock = MasterClock(now=self.time)
        self.clock.restart(5000)

    def test_without_audio_follows_system_clock(self):
        self.time.t = 1.5
        self.assertAlmostEqual(self.clock.time(), 6500)

    def test_small_drift_is_slewed(self):
        self.time.t = 1.0
        value = self.clock.time(audio_ms=5900)  # audio 100 ms atrás
        self.assertTrue(5900 < value < 6000)
        for step in range(2, 40):
            self.time.t = step * .05 + 1
            last = self.clock.time(audio_ms=5900 + (step * 50))
        self.assertAlmostEqual(last, 5900 + 39 * 50, delta=5)

    def test_large_error_resyncs_at_once(self):
        self.time.t = 1.0
        self.assertAlmostEqual(self.clock.time(audio_ms=5200), 5200)

    def test_never_goes_back_on_small_corrections(self):
        self.time.t = 1.0
        first = self.clock.time()
        self.time.t = 1.01
        self.assertGreaterEqual(self.clock.time(audio_ms=first - 100), first)

    def test_duration_limit(self):
        self.time.t = 10
        self.assertEqual(self.clock.time(duration_ms=7000), 7000)

    def test_resync_rules(self):
        self.assertTrue(needs_video_resync(1000, 1300, 10, 0))
        self.assertFalse(needs_video_resync(1000, 1100, 10, 0))
        self.assertFalse(needs_video_resync(1000, 1300, 10, 8))
        self.assertFalse(needs_video_resync(None, 1300, 10, 0))


if __name__ == '__main__':
    unittest.main()
