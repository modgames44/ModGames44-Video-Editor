import unittest
from timeline.thumbnail_math import thumbnail_source_time

class ThumbnailMathTests(unittest.TestCase):
    def test_frame_times_increase_across_strip(self):
        c={'in_ms':0,'duration_ms':10000,'speed':1.}
        times=[thumbnail_source_time(c,i*150,150,70) for i in range(4)]
        self.assertEqual(times,sorted(times))
        self.assertEqual(len(set(round(t) for t in times)),4)

    def test_source_offset_and_speed(self):
        c={'in_ms':3000,'duration_ms':10000,'speed':2.}
        self.assertAlmostEqual(thumbnail_source_time(c,0,100,100),4000)

    def test_last_thumbnail_is_inside_source(self):
        c={'in_ms':2000,'duration_ms':1000,'speed':.5}
        self.assertLess(thumbnail_source_time(c,1000,150,50),2500)

if __name__=='__main__': unittest.main()
