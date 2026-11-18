"""Velocidad de clip sin el antiguo tope 0.25×–4× (ahora 0.01×–100×)."""
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from effects.audio import audio_filter_chain
from effects.model import SPEED_MAX, SPEED_MIN, change_speed, is_valid_speed
from exporter.render import ExportProfile, build_export_command
from timeline.model import make_clip

FFMPEG = shutil.which('ffmpeg')


def tempo_product(chain):
    return math.prod(float(f.split('=')[1]) for f in chain if f.startswith('atempo='))


class SpeedRangeTests(unittest.TestCase):
    def test_limits(self):
        self.assertEqual((SPEED_MIN, SPEED_MAX), (0.01, 100.0))
        for value in (0.01, 0.1, 8, 16, 50, 100):
            self.assertTrue(is_valid_speed(value), value)
        for value in (0, -1, 0.001, 101, float('nan'), float('inf'), 'x'):
            self.assertFalse(is_valid_speed(value), value)

    def test_change_speed_keeps_source_range_and_linked_audio(self):
        for rate, expected in ((16, 625), (100, 100), (0.1, 100000), (500, 100)):
            video = make_clip('a.mp4', 10000, link='L')
            audio = make_clip('a.mp4', 10000, kind='audio', link='L')
            clips = [video, audio]
            change_speed(clips, video['id'], rate)
            self.assertEqual([c['duration_ms'] for c in clips], [expected, expected], rate)
            self.assertEqual(video['speed'], min(rate, 100))

    def test_audio_tempo_chain_reaches_any_speed(self):
        for speed in (0.01, 0.05, 0.3, 7, 16, 100):
            chain = audio_filter_chain({}, speed)
            self.assertAlmostEqual(tempo_product(chain), speed, places=5)
            for f in chain:
                self.assertTrue(0.5 <= float(f.split('=')[1]) <= 2.0, f)

    def test_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            audio_filter_chain({}, 150)


@unittest.skipIf(FFMPEG is None, 'FFmpeg no disponible')
class SpeedExportTests(unittest.TestCase):
    def _duration(self, path):
        info = subprocess.run([FFMPEG, '-i', str(path)], capture_output=True, text=True).stderr
        h, m, s = info.split('Duration: ')[1].split(',')[0].split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)

    def test_export_at_extreme_speeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'src.mp4'
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=160x90:r=30:d=40',
                            '-f', 'lavfi', '-i', 'sine=f=440:d=40', '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-c:a', 'aac', '-shortest', str(src)], check=True)
            profile = ExportProfile('t', 'h264', 'mp4', 160, 90, 30, '1M')
            # 40 s a 20× = 2 s · 1 s de origen a 0.5× ... y a 0.1× = 10 s
            for speed, source_ms, expected_s in ((20, 40000, 2.0), (100, 40000, 0.4), (0.1, 1000, 10.0)):
                video = make_clip(src, source_ms, link='L')
                audio = make_clip(src, source_ms, kind='audio', link='L')
                clips = [video, audio]
                change_speed(clips, video['id'], speed)
                out = Path(tmp) / f'out_{speed}.mp4'
                argv, _ = build_export_command(clips, profile, out, {'ffmpeg': FFMPEG, 'encoder': 'libx264'})
                run = subprocess.run(argv, capture_output=True, text=True, timeout=180)
                self.assertEqual(run.returncode, 0, run.stderr[-800:])
                self.assertAlmostEqual(self._duration(out), expected_s, delta=0.15, msg=speed)


if __name__ == '__main__':
    unittest.main()
