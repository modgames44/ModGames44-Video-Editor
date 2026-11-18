import unittest
from timeline.playback_clock import projected_time
class PlaybackRateTests(unittest.TestCase):
    def test_slow_motion_realtime_clock(self):
        self.assertEqual(projected_time(1000,2000,.5,10000),2000)
    def test_fast_motion_realtime_clock(self):
        self.assertEqual(projected_time(1000,2000,2.,10000),5000)
    def test_clamp_to_clip_duration(self):
        self.assertEqual(projected_time(9000,2000,4.,10000),10000)
