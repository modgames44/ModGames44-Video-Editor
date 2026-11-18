"""Pruebas de límites, selección y conversión de coordenadas del cabezal."""
import unittest
from timeline.playhead_math import hit_playhead, playhead_time


class PlayheadTests(unittest.TestCase):
    def test_drag_exact_time(self):
        self.assertEqual(playhead_time(76+5*70,76,70,20000),5000)

    def test_no_negative_times(self):
        self.assertEqual(playhead_time(-100,76,70,20000),0)
        self.assertEqual(playhead_time(70,76,70,20000),0)

    def test_cannot_seek_past_sequence(self):
        self.assertEqual(playhead_time(100000,76,70,9000),9000)
        self.assertEqual(playhead_time(100000,76,70,0),0)

    def test_high_zoom_precision(self):
        self.assertEqual(playhead_time(76+350,76,700,8000),500)

    def test_hittest_on_grab_handle(self):
        self.assertTrue(hit_playhead(105,112,9))
        self.assertTrue(hit_playhead(112,112,9))
        self.assertFalse(hit_playhead(130,112,9))

    def test_invalid_zoom(self):
        with self.assertRaises(ValueError):
            playhead_time(300,76,0,10000)

    def test_drag_not_affected_by_zoom(self):
        target_ms=6400
        for zoom in (5,70,300,700):
            xpos=76+target_ms*zoom/1000
            self.assertEqual(playhead_time(xpos,76,zoom,10000),target_ms)

if __name__ == '__main__':unittest.main()
