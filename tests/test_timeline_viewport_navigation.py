"""Regresión para barras de desplazamiento y transporte en Timeline.

Las pruebas de geometría funcionan sin un servidor gráfico, y verifican que
el código Qt aplique estas reglas (el mouse real se prueba en Windows).
"""
import unittest
from pathlib import Path

from timeline.viewport_math import (
    playhead_scene_x, viewport_scroll_for_time, needs_playback_follow,
)


ROOT = Path(__file__).resolve().parents[1]


class ViewportNavigationTests(unittest.TestCase):
    def test_scene_position_is_temporal(self):
        self.assertEqual(playhead_scene_x(0, 70), 76)
        self.assertEqual(playhead_scene_x(120000, 70), 8476)
        self.assertEqual(playhead_scene_x(-100, 70), 76)

    def test_start_always_scrolls_to_zero(self):
        for width in (780, 1280, 1920, 2560):
            for scale in (5, 70, 400, 700):
                self.assertEqual(viewport_scroll_for_time(
                    0, scale, width, alignment='start', current_scroll=19000), 0)

    def test_end_is_visible_near_right_edge(self):
        for scale in (10, 70, 400):
            for width in (768, 1024, 1400):
                ms = 160000
                scroll = viewport_scroll_for_time(ms, scale, width, alignment='end')
                viewport_x = playhead_scene_x(ms, scale) - scroll
                self.assertGreaterEqual(viewport_x, 76)
                self.assertLessEqual(viewport_x, width)

    def test_center_seek_is_visible(self):
        for scale in (5, 70, 400):
            width = 1000
            position = 500000
            scroll = viewport_scroll_for_time(position, scale, width, alignment='center')
            self.assertAlmostEqual(playhead_scene_x(position, scale) - scroll,
                                   76+(width-76)/2, delta=1)

    def test_autoscroll_when_reaching_edge(self):
        self.assertFalse(needs_playback_follow(200, 1000))
        self.assertTrue(needs_playback_follow(978, 1000))
        self.assertTrue(needs_playback_follow(60, 1000))

    def test_invalid_alignment_rejected(self):
        with self.assertRaises(ValueError):
            viewport_scroll_for_time(10000, 70, 1000, alignment='bogus')

    def test_qt_uses_full_redraw_to_avoid_ghosts(self):
        text = (ROOT/'ui'/'timeline_panel.py').read_text(encoding='utf-8')
        self.assertIn('FullViewportUpdate', text)
        self.assertIn('horizontalScrollBar().valueChanged.connect(self._scroll_redraw)', text)
        self.assertIn('verticalScrollBar().valueChanged.connect(self._scroll_redraw)', text)
        self.assertIn('def reveal_playhead(', text)
        self.assertIn('def follow_playhead(', text)

    def test_transport_is_wired_to_view_follow(self):
        text = (ROOT/'ui'/'main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.monitor.start_requested.connect(self.jump_to_start)', text)
        self.assertIn('self.monitor.end_requested.connect(self.jump_to_end)', text)
        self.assertIn("self.timeline.reveal_playhead(0, alignment='start')", text)
        self.assertIn("self.timeline.reveal_playhead(destination, alignment='end')", text)
        self.assertIn('self.timeline.follow_playhead()', text)


if __name__ == '__main__':
    unittest.main()
