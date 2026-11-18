"""v0.6.6: Timeline incremental, análisis en segundo plano y reloj de audio."""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from services.media_probe import probe_many
from timeline.model import make_clip
from timeline.scene_sync import plan_scene_sync, clip_geometry

ROOT = Path(__file__).resolve().parents[1]


class ScenePlanTests(unittest.TestCase):
    def test_reuses_existing_items_and_creates_only_new(self):
        a, b, c = make_clip('a', 1000), make_clip('b', 1000), make_clip('c', 1000)
        plan = plan_scene_sync({a['id']: 'video', b['id']: 'video', 'gone': 'audio'}, [a, b, c])
        self.assertEqual(plan.remove, ['gone'])
        self.assertEqual([x['id'] for x in plan.update], [a['id'], b['id']])
        self.assertEqual([x['id'] for x in plan.create], [c['id']])

    def test_kind_change_recreates_item(self):
        a = make_clip('a', 1000, kind='audio')
        plan = plan_scene_sync({a['id']: 'video'}, [a])
        self.assertEqual((plan.remove, len(plan.create), plan.update), ([a['id']], 1, []))

    def test_no_change_means_no_creation(self):
        clips = [make_clip(str(i), 500, start_ms=i * 500) for i in range(300)]
        plan = plan_scene_sync({c['id']: 'video' for c in clips}, clips)
        self.assertEqual((plan.remove, plan.create, len(plan.update)), ([], [], 300))

    def test_geometry_matches_previous_formula(self):
        clip = make_clip('a', 2500, start_ms=4000)
        self.assertEqual(clip_geometry(clip, 80, 100, 48, 74), (74 + 4 * 80, 103, 2.5 * 80, 41))
        tiny = make_clip('a', 1, start_ms=0)
        self.assertEqual(clip_geometry(tiny, 80, 0, 48, 74)[2], 1)

    def test_panel_uses_incremental_refresh(self):
        source = (ROOT / 'ui' / 'timeline_panel.py').read_text(encoding='utf-8')
        start = source.index('    def refresh(self):')
        body = source[start:source.index('\n    def ', start + 10)]
        self.assertNotIn('self.scene.clear()', body)
        self.assertIn('plan_scene_sync(', body)
        self.assertIn('item.sync(clip)', body)


@unittest.skipIf(shutil.which('ffmpeg') is None, 'FFmpeg no disponible')
class ProbeManyTests(unittest.TestCase):
    def test_parallel_probe_returns_every_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i in range(3):
                path = Path(tmp) / f'{i}.wav'
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=d={i + 1}',
                                str(path)], check=True)
                paths.append(str(path))
            results = probe_many(paths + [paths[0], ''])
            self.assertEqual(list(results), paths)
            self.assertEqual([round(results[p]['duration_ms'] / 1000) for p in paths], [1, 2, 3])
            self.assertTrue(all(r['has_audio'] and not r['has_video'] for r in results.values()))


class _Signal:
    def __init__(self, *args):
        self.handlers = []

    def connect(self, fn):
        self.handlers.append(fn)

    def emit(self, *args):
        for fn in self.handlers:
            fn(*args)


class _Sink:
    def __init__(self, *args):
        self.processed = 0

    def setBufferSize(self, n):
        pass

    def setVolume(self, v):
        pass

    def processedUSecs(self):
        return self.processed

    def stop(self):
        pass


def _load_audio_preview():
    qtcore = types.ModuleType('PySide6.QtCore')
    qtcore.QObject = type('QObject', (), {'__init__': lambda self, parent=None: None})
    qtcore.Signal = _Signal
    qtcore.QTimer = type('QTimer', (), {'__init__': lambda self, p=None: setattr(self, 'timeout', _Signal()),
                                        'setInterval': lambda self, n: None,
                                        'start': lambda self: None, 'stop': lambda self: None})
    qtmm = types.ModuleType('PySide6.QtMultimedia')
    fmt = type('QAudioFormat', (), {'setSampleRate': lambda s, n: None, 'setChannelCount': lambda s, n: None,
                                     'setSampleFormat': lambda s, n: None})
    fmt.SampleFormat = types.SimpleNamespace(Int16=1)
    qtmm.QAudioFormat = fmt
    qtmm.QAudioSink = _Sink
    qtmm.QMediaDevices = types.SimpleNamespace(defaultAudioOutput=lambda: None)
    pyside = types.ModuleType('PySide6')
    spec = importlib.util.spec_from_file_location('_audio_preview_v066',
                                                  ROOT / 'core' / 'continuous_audio_preview.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'PySide6': pyside, 'PySide6.QtCore': qtcore,
                                  'PySide6.QtMultimedia': qtmm}):
        spec.loader.exec_module(module)
    return module.AudioPreview


class AudioClockTests(unittest.TestCase):
    def test_timeline_ms_uses_device_clock(self):
        preview = _load_audio_preview()()
        self.assertIsNone(preview.timeline_ms())  # sin iniciar
        preview._anchor = 12000
        preview._started = True
        preview._device = object()
        preview.output.processed = 1_500_000  # 1,5 s consumidos por la tarjeta
        self.assertEqual(preview.timeline_ms(), 13500)
        preview._finished = True  # flujo terminado y vacío: ya no es fiable
        self.assertIsNone(preview.timeline_ms())


if __name__ == '__main__':
    unittest.main()
