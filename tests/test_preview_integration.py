"""Regresiones del conexionado Play/Pause/seek sin necesitar Qt en CI."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def method(name):
    module=ast.parse((ROOT/'ui'/'main_window.py').read_text(encoding='utf8'))
    cls=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='MainWindow')
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    isolated=ast.Module(body=[fn],type_ignores=[])
    ast.fix_missing_locations(isolated)
    scope={}
    exec(compile(isolated,'ui/main_window.py','exec'),scope)
    return scope[name]


class Recorder:
    def __init__(self): self.calls=[]
    def __getattr__(self,name):
        def callback(*args,**kwargs):self.calls.append((name,args))
        return callback


class FakePlayback:
    toggle=method('toggle')
    seek_timeline=method('seek_timeline')
    _sequence_position=method('_sequence_position')
    def __init__(self):
        self.mode='timeline'
        self.events=[]
        self.sequence=Recorder()
        self.sequence.running=False
        self.sequence.position=3000
        self.sequence.duration=lambda:8000
        self.sequence.play=lambda:self.events.append('play_video')
        self.sequence.pause=lambda:self.events.append('pause_video')
        self.timeline=Recorder()
        self.timeline.clips=[{'kind':'video','start_ms':0,'duration_ms':8000},
                             {'kind':'audio','start_ms':0,'duration_ms':8000}]
        self.engine=Recorder()
        self.engine.audio=Recorder()
        self.meter=Recorder()
        self.monitor=Recorder()
        self.monitor.video=Recorder()
        self.audio_preview=Recorder()
        self.audio_preview.is_waiting=False
        self.audio_preview.play=self._play_audio
        self._scrub_timer=Recorder()
        self._pending_timeline_seek=None
        self.status=Recorder()
    def statusBar(self):return self.status
    def _play_audio(self,position,clips,duration,callback):
        self.events.append(('audio_prepared',position,duration))
        callback()
    def _sync_effects_view(self):self.events.append('video_fx_synced')


class WiredPreviewTests(unittest.TestCase):
    def test_audio_is_prepared_before_starting_video(self):
        ui=FakePlayback()
        ui.toggle()
        self.assertEqual(ui.events[:2],[('audio_prepared',3000,8000),'play_video'])
        self.assertIn(('set_internal_audio',(False,)),ui.engine.calls)
        self.assertIn(('set_mode',('timeline',)),ui.meter.calls)

    def test_pause_cancels_waiting_audio(self):
        ui=FakePlayback()
        ui.audio_preview.is_waiting=True
        ui.toggle()
        self.assertEqual(ui.events,['pause_video'])
        self.assertIn(('pause',()),ui.audio_preview.calls)

    def test_scrubbing_always_pauses_and_seeks_processed_audio(self):
        ui=FakePlayback()
        ui.seek_timeline(4500)
        self.assertIn('pause_video',ui.events)
        self.assertIn(('pause',()),ui.audio_preview.calls)
        self.assertIn(('seek',(4500,)),ui.sequence.calls)
        self.assertIn(('invalidate_seek',()),ui.monitor.video.calls)
        self.assertIn('video_fx_synced',ui.events)
        self.assertIn(('set_mode',('timeline',)),ui.meter.calls)

    def test_playhead_drives_audio_alignment(self):
        ui=FakePlayback()
        ui.sequence.running=True
        ui._sequence_position(5500)
        self.assertIn(('follow',(5500,True)),
                      [(name,args[:2]) for name,args in ui.audio_preview.calls])
        self.assertIn('video_fx_synced',ui.events)

if __name__=='__main__': unittest.main()
