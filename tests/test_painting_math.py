"""Regresión: textos sin rastro al mover cabezal, cuchilla o reproducir."""
import unittest
from timeline.painting_math import stable_visible_label


class LabelPaintingTests(unittest.TestCase):
    def test_fixed_title_does_not_follow_playhead(self):
        # Mismo viewport; cada actualización del cabezal repinta otra banda.
        # El anclaje NO recibe esa banda y jamás cambia mientras no haya scroll.
        positions = [81, 120, 195, 640, 750]
        anchors = [stable_visible_label(76, 900, 0, 800) for _ in positions]
        self.assertEqual(anchors, [anchors[0]] * len(positions))
        self.assertEqual(anchors[0][0], 5)

    def test_label_follows_viewport_scroll_not_dirty_region(self):
        self.assertEqual(stable_visible_label(76, 900, 0, 800)[0], 5)
        self.assertEqual(stable_visible_label(76, 900, 300, 1100)[0], 229)

    def test_labels_do_not_render_offscreen(self):
        self.assertIsNone(stable_visible_label(2000, 500, 0, 900))
        self.assertIsNone(stable_visible_label(50, 500, 900, 1600))

    def test_short_clip_label_is_bounded(self):
        x, width = stable_visible_label(76, 80, 0, 800)
        self.assertLessEqual(x + width, 80)
        self.assertGreaterEqual(width, 12)
        self.assertIsNone(stable_visible_label(76, 10, 0, 800))

    def test_audio_channel_labels_have_stable_anchor(self):
        header = stable_visible_label(76, 900, 0, 800, max_width=260)
        channels = stable_visible_label(76, 900, 0, 800, max_width=18)
        self.assertEqual(header[0], channels[0])
        self.assertEqual(channels[1], 18)


if __name__ == '__main__':
    unittest.main()
