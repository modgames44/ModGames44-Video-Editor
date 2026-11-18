"""El monitor convierte como mucho ~30 fotogramas/s, a cualquier velocidad."""
import unittest
from pathlib import Path

from services.preview_performance import FRAME_INTERVAL_MS, frame_delay_ms

ROOT = Path(__file__).resolve().parents[1]


class FrameThrottleTests(unittest.TestCase):
    def test_delay(self):
        self.assertEqual(FRAME_INTERVAL_MS, 33)
        self.assertEqual(frame_delay_ms(10.0, 0.0), 0)        # fotograma suelto: inmediato
        self.assertEqual(frame_delay_ms(10.010, 10.0), 23)    # faltan 23 ms
        self.assertEqual(frame_delay_ms(10.033, 10.0), 0)

    def test_conversions_per_second_do_not_grow_with_speed(self):
        # Simula la llegada de fotogramas a 60, 240 y 960 por segundo
        # (60 fps a 1×, 4× y 16×) y cuenta conversiones en 1 s.
        for arrivals in (60, 240, 960):
            now, last, pending_until, conversions = 0.0, -1.0, None, 0
            for i in range(arrivals):
                now = i / arrivals
                if pending_until is not None and now >= pending_until:
                    conversions += 1
                    last, pending_until = pending_until, None
                if pending_until is None:
                    pending_until = now + frame_delay_ms(now, last) / 1000
            self.assertLessEqual(conversions, 31, arrivals)

    def test_monitor_converts_only_latest_frame_on_timer(self):
        source = (ROOT / 'ui' / 'effect_video_view.py').read_text(encoding='utf-8')
        new_frame = source[source.index('    def _new_frame'):source.index('    def _consume_frame')]
        self.assertNotIn('toImage', new_frame)
        self.assertIn('_frame_timer.start(frame_delay_ms(', new_frame)


if __name__ == '__main__':
    unittest.main()
