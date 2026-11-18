"""Regresiones de accesibilidad de Quitar silencios sin necesitar PySide6."""
import ast
import copy
from pathlib import Path
import unittest

from timeline.model import make_clip
from ai.silence import silence_plan
from ai.operations import prepare_plan

ROOT = Path(__file__).resolve().parents[1]


def file_ast(name):
    return ast.parse((ROOT / name).read_text(encoding='utf-8'))


def class_method(file, classname, method):
    cls = next(item for item in file_ast(file).body
               if isinstance(item, ast.ClassDef) and item.name == classname)
    return next(item for item in cls.body if isinstance(item, ast.FunctionDef)
                and item.name == method)


class SilenceRestoredRegressionTests(unittest.TestCase):
    def test_catalog_has_silence_in_audio(self):
        tree = file_ast('ui/effect_catalog_panel.py')
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == 'EffectCatalogPanel')
        categories = next(n.value for n in cls.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'CATEGORIES'
                                  for t in n.targets))
        groups = dict(ast.literal_eval(categories))
        self.assertIn(('Quitar silencios', 'silence'), groups['Efectos de audio'])

    def test_audio_panel_shows_action_and_signal(self):
        source = (ROOT / 'ui/audio_effects_panel.py').read_text(encoding='utf-8')
        self.assertIn('silenceRequested = Signal()', source)
        self.assertIn("QPushButton('Detectar y quitar silencios…')", source)
        self.assertIn('self.silence_button.clicked.connect(self.silenceRequested.emit)', source)
        self.assertIn('self.silence_button =', source)
        self.assertIn('self.set_selected(None)', source)

    def test_window_routes_both_entries_to_existing_analyzer(self):
        source = (ROOT / 'ui/main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.audio_effects_panel.silenceRequested.connect(self._ai_silence)', source)
        self.assertIn('self.ai_assistant.silenceRequested.connect(self._ai_silence)', source)
        self.assertIn("('noise','voice','silence')", source)
        self.assertIn('self.audio_effects_panel.silence_button.setFocus()', source)
        self.assertIsNotNone(class_method('ui/main_window.py', 'MainWindow', '_ai_silence'))

    def test_silence_cuts_audio_and_video_and_undoable(self):
        video = make_clip('test.mp4', 15000, kind='video', link='linked')
        audio = make_clip('test.mp4', 15000, kind='audio', link='linked')
        clips = [video, audio]
        originals = copy.deepcopy(clips)
        proposal = silence_plan(video, [(4000, 6500)])
        validated = prepare_plan(proposal, clips)
        result = validated['preview_clips']
        self.assertEqual(clips, originals)
        self.assertEqual(len([x for x in result if x['kind']=='audio']), 2)
        self.assertEqual(len([x for x in result if x['kind']=='video']), 2)
        self.assertEqual(sorted((x['start_ms'], x['duration_ms']) for x in result if x['kind']=='video'),
                         sorted((x['start_ms'], x['duration_ms']) for x in result if x['kind']=='audio'))

    def test_silent_whole_clip_never_removed(self):
        audio = make_clip('test.wav', 12000, kind='audio')
        self.assertEqual(silence_plan(audio, [(0, 12000)])['operations'], [])


if __name__ == '__main__':
    unittest.main()
