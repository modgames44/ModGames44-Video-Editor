"""Regresiones reales de los métodos de censura, sin requerir un monitor Qt.

Los métodos probados se extraen del código de producción (no duplicados).
Una segunda prueba con PySide6 en Windows sigue siendo necesaria para la UI.
"""
import ast
import copy
import pathlib
import unittest
from effects.model import merged_effects, change_speed
from timeline.history import History

ROOT = pathlib.Path(__file__).resolve().parents[1]


def production_method(file, cls, name, namespace):
    tree = ast.parse((ROOT / file).read_text(encoding='utf-8'))
    owner = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == cls)
    method = next(x for x in owner.body if isinstance(x, ast.FunctionDef) and x.name == name)
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    scope = dict(namespace)
    exec(compile(module, str(ROOT / file), 'exec'), scope)
    return scope[name]


class StubSignal:
    def __init__(self):
        self.calls = []
    def emit(self, *args):
        self.calls.append(args)


class StubTimeline:
    clear_effects = production_method('ui/timeline_panel.py', 'TimelinePanel',
                                      'clear_effects', {'merged_effects': merged_effects,
                                                        'change_speed': change_speed})
    def __init__(self):
        effects = merged_effects(None)
        effects['censor'].update(enabled=True, mode='mosaic', strength=44,
                                 mask={'x': .15, 'y': .1, 'w': .4, 'h': .3},
                                 keys=[{'time_ms': 200, 'x': .2, 'y': .2,
                                        'w': .3, 'h': .3}])
        effects['zoom']['enabled'] = True
        self.clips = [{'id': 'clip-1', 'kind': 'video', 'speed': 1.,
                       'duration_ms': 5000, 'effects': effects}]
        self.history = History()
        self.changed = StubSignal()
        self.refresh_count = 0
    def get_clip(self, clip_id):
        return next((c for c in self.clips if c['id'] == clip_id), None)
    def selected(self):
        return self.clips[0]
    def refresh(self):
        self.refresh_count += 1


class StubCheck:
    def __init__(self): self.checked = True
    def isChecked(self): return self.checked
    def setChecked(self, v): self.checked = bool(v)


class CensorRemovalTests(unittest.TestCase):
    def test_removing_censor_removes_keyframes_but_preserves_other_effects(self):
        timeline = StubTimeline()
        previous = copy.deepcopy(timeline.clips)
        self.assertTrue(timeline.clear_effects('clip-1', 'censor'))
        fx = merged_effects(timeline.clips[0]['effects'])
        self.assertFalse(fx['censor']['enabled'])
        self.assertEqual(fx['censor']['keys'], [])
        self.assertEqual(fx['censor']['mask'], merged_effects(None)['censor']['mask'])
        self.assertTrue(fx['zoom']['enabled'])
        self.assertEqual(timeline.history.undo(timeline.clips), previous)
        self.assertEqual(timeline.refresh_count, 1)

    def test_disabling_mask_editing_unchecks_cursor_mode(self):
        stop = production_method('ui/effects_panel.py', 'EffectsPanel',
                                 'stop_mask_editing', {})
        class Panel:
            edit_mask = StubCheck()
        panel = Panel()
        stop(panel)
        self.assertFalse(panel.edit_mask.isChecked())

    def test_main_window_removal_cancels_edit_and_refreshes_views(self):
        method = production_method('ui/main_window.py', 'MainWindow', '_effect_clear', {})
        timeline = StubTimeline()
        events = []
        class FakeEffectPanel:
            def stop_mask_editing(self): events.append('stop_mouse')
            def set_selected(self, c): events.append('refresh_effects')
        class FakeVideo:
            def set_mask_editing(self, enabled): events.append(('mask_mode', enabled))
            def update(self): events.append('redraw')
        class FakeProperties:
            def set_selected(self, c): events.append('refresh_properties')
        class FakeStatus:
            def showMessage(self, message, timeout): events.append('status')
        class FakeSelf:
            def __init__(self):
                self.timeline = timeline
                self.effects_panel = FakeEffectPanel()
                self.monitor = type('Monitor', (), {'video': FakeVideo()})()
                self.properties_panel = FakeProperties()
                self.sequence = type('Seq', (), {'pause': lambda s: events.append('pause')})()
            def _selected_video(self): return timeline.clips[0]
            def _sync_effects_view(self): events.append('refresh_monitor')
            def statusBar(self): return FakeStatus()
        self.assertIsNone(method(FakeSelf(), 'censor'))
        self.assertEqual(events[0:3], ['stop_mouse', ('mask_mode', False), 'pause'])
        self.assertIn('refresh_monitor', events)
        self.assertIn('redraw', events)
        self.assertFalse(merged_effects(timeline.clips[0]['effects'])['censor']['enabled'])


if __name__ == '__main__':
    unittest.main()
