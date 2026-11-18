import unittest
from timeline.zoom_math import ruler_spacing, zoom_scroll_value, clamp_clip_start, format_ruler


class ZoomMathTests(unittest.TestCase):
    def test_ruler_spacing_changes_with_scale(self):
        self.assertGreater(ruler_spacing(10),ruler_spacing(700))
        self.assertGreaterEqual(ruler_spacing(70)*70,105)

    def test_zoom_keeps_cursor_time(self):
        old_scale,new_scale,header=60,240,76
        sec=75
        cursor=680
        old_scroll=header+sec*old_scale-cursor
        scene_x=old_scroll+cursor
        new_scroll=zoom_scroll_value(scene_x,old_scale,new_scale,cursor,header)
        self.assertAlmostEqual((new_scroll+cursor-header)/new_scale,sec,places=2)

    def test_zero_is_hard_boundary(self):
        self.assertEqual(clamp_clip_start(-999),0)
        self.assertEqual(clamp_clip_start(0),0)
        self.assertEqual(clamp_clip_start(195.5),196)

    def test_timecode_for_small_and_large_zoom(self):
        self.assertEqual(format_ruler(65,5),'01:05')
        self.assertEqual(format_ruler(3661,5),'01:01:01')
        self.assertIn('00:00:01.',format_ruler(1.2,.2))

if __name__=='__main__':unittest.main()
