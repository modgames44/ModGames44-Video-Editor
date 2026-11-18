"""Onda única en la Timeline (envolvente de L y R; el audio sigue estéreo)."""
import unittest
from pathlib import Path

import numpy as np

from services.waveform import combined_peaks

ROOT = Path(__file__).resolve().parents[1]


class CombinedPeaksTests(unittest.TestCase):
    def test_takes_most_extreme_value_of_both_channels(self):
        # (columnas, canal, [mín, máx])
        peaks = np.array([[[-.2, .3], [-.6, .1]],
                          [[-.1, .9], [0., .2]]], dtype=np.float32)
        np.testing.assert_allclose(combined_peaks(peaks), [[-.6, .3], [-.1, .9]])

    def test_sound_only_on_one_side_is_not_lost(self):
        peaks = np.zeros((3, 2, 2), dtype=np.float32)
        peaks[1, 1] = (-.8, .8)  # golpe sólo en el canal derecho
        self.assertEqual(combined_peaks(peaks)[1].tolist(), [-.800000011920929, .800000011920929])

    def test_empty(self):
        self.assertEqual(combined_peaks(np.zeros((0, 2, 2))).shape, (0, 2))

    def test_timeline_draws_single_wave_by_default_and_keeps_toggle(self):
        source = (ROOT / 'ui' / 'timeline_panel.py').read_text(encoding='utf-8')
        self.assertIn("value('timeline/stereo_waves',False,type=bool)", source)
        self.assertIn("QCheckBox('L/R')", source)
        self.assertIn('combined_peaks(peaks)', source)


if __name__ == '__main__':
    unittest.main()
