"""Pruebas de regresión de la representación de audio FX y perfiles ModGames44."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np

from effects.audio import audio_filter_chain
from services.waveform import (effect_signature, get_waveform, get_effect_waveform,
                               needs_processed_waveform, waveform_gain_linear)


class AudioFXWaveformTests(unittest.TestCase):
    def test_gain_maps_to_linear_amplitude(self):
        self.assertAlmostEqual(waveform_gain_linear(0), 1)
        self.assertAlmostEqual(waveform_gain_linear(6.0206), 2, places=4)
        self.assertAlmostEqual(waveform_gain_linear(-6.0206), 0.5, places=4)

    def test_only_gain_updates_immediately(self):
        self.assertFalse(needs_processed_waveform({'volume_db': 12}))
        self.assertTrue(needs_processed_waveform({'voice': 'podcast'}))
        self.assertTrue(needs_processed_waveform({'noise': 0.4}))
        self.assertTrue(needs_processed_waveform({'normalize': True}))
        self.assertNotEqual(effect_signature({'voice': 'high'}),
                            effect_signature({'voice': 'low'}))

    def test_noise_reduction_is_measured_in_db(self):
        chain = ','.join(audio_filter_chain({'noise': 1.0}))
        self.assertIn('afftdn=nr=20.00:nf=-50:tn=1', chain)
        chain = ','.join(audio_filter_chain({'noise': 0.5}))
        self.assertIn('afftdn=nr=11.50:nf=-50:tn=1', chain)

    def test_voice_presets_have_individual_eq(self):
        podcast = ','.join(audio_filter_chain({'voice': 'podcast'}))
        high = ','.join(audio_filter_chain({'voice': 'high'}))
        low = ','.join(audio_filter_chain({'voice': 'low'}))
        self.assertIn('equalizer=f=250:', podcast)
        self.assertIn('equalizer=f=3200:', podcast)
        self.assertIn('equalizer=f=180:', high)
        self.assertIn('equalizer=f=5500:', high)
        self.assertIn('equalizer=f=220:', low)
        self.assertIn('equalizer=f=3000:', low)

    def test_real_processed_wave_and_cache(self):
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            self.skipTest('FFmpeg no disponible')
        with tempfile.TemporaryDirectory() as td:
            source = str(Path(td) / 'entrada.wav')
            command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                       '-i', 'aevalsrc=0.06*sin(2*PI*220*t)|0.08*sin(2*PI*3000*t):s=48000:d=1',
                       '-ac', '2', source]
            result = subprocess.run(command, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            original = get_waveform(source, ffmpeg, td)
            fx = {'voice': 'podcast', 'volume_db': 5, 'noise': 0}
            processed = get_effect_waveform(source, ffmpeg, fx, td)
            cached = get_effect_waveform(source, ffmpeg, fx, td)
            self.assertEqual(len(list(Path(td).glob('*.npz'))), 2)
            self.assertEqual(len(original.levels[0]), len(processed.levels[0]))
            self.assertFalse(np.array_equal(original.levels[0], processed.levels[0]))
            self.assertTrue(np.array_equal(cached.levels[0], processed.levels[0]))
            self.assertTrue(np.isfinite(processed.peaks(0, 900, 300)).all())


if __name__ == '__main__':
    unittest.main()
