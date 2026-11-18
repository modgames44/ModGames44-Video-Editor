"""Prueba del motor de secuencia sin requerir escritorio ni PySide6 en CI.

La API mínima de QMediaPlayer se simula para comprobar que no se llama
engine.load(), que usa stop(), en cada corte del mismo archivo.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from timeline.model import make_clip


class _Signal:
    def __init__(self, *args):
        self.handlers=[]
    def connect(self, fn):
        self.handlers.append(fn)
    def emit(self, *args):
        for fn in self.handlers:
            fn(*args)


class _Timer:
    def __init__(self, parent=None):
        self.timeout=_Signal()
        self.running=False
    def setInterval(self, n):
        pass
    def start(self):
        self.running=True
    def stop(self):
        self.running=False


class _Clock:
    def __init__(self):
        self.elapsed_ms=0
    def start(self):
        self.elapsed_ms=0
    def restart(self):
        self.elapsed_ms=0
    def elapsed(self):
        return self.elapsed_ms


class _Player:
    def __init__(self):
        self.positionChanged=_Signal()
        self._source=None
        self._position=0
        self.play_count=0
        self.pause_count=0
    def source(self):
        return self._source
    def position(self):
        return self._position
    def setPlaybackRate(self, rate):
        self.rate=rate
    def play(self):
        self.play_count+=1
    def pause(self):
        self.pause_count+=1


class _Engine:
    def __init__(self):
        self.player=_Player()
        self.loads=[]
        self.seeks=[]
    def load(self, path):
        self.loads.append(path)
        self.player._source=path
        self.player._position=0
    def seek(self, ms):
        self.seeks.append(round(ms))
        self.player._position=round(ms)


def _load_sequence_player():
    qtcore=types.ModuleType('PySide6.QtCore')
    qtcore.QObject=type('QObject',(),{'__init__':lambda self:None})
    qtcore.Signal=_Signal
    qtcore.QTimer=_Timer
    qtcore.QElapsedTimer=_Clock
    qtcore.QUrl=type('QUrl',(),{'fromLocalFile':staticmethod(lambda path:path)})
    pyside=types.ModuleType('PySide6')
    pyside.QtCore=qtcore
    module_path=Path(__file__).resolve().parents[1]/'core'/'sequence_player.py'
    spec=importlib.util.spec_from_file_location('_test_sequence_player_v063',module_path)
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'PySide6':pyside,'PySide6.QtCore':qtcore}):
        spec.loader.exec_module(module)
    return module.SequencePlayer


class SequenceContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.SequencePlayer=_load_sequence_player()

    def player_with_clips(self, second_start=4000, right_source='video.mp4',
                          right_in_ms=6000):
        a=make_clip('video.mp4',4000,start_ms=0,kind='video')
        b=make_clip(right_source,4000,start_ms=second_start,
                    in_ms=right_in_ms,kind='video')
        timeline=types.SimpleNamespace(clips=[a,b])
        engine=_Engine()
        seq=self.SequencePlayer(engine,timeline)
        seq.stop_at_cuts=True
        seq.play()
        return seq,engine,a,b

    def test_same_source_cut_does_not_pause_or_reload(self):
        seq,engine,a,b=self.player_with_clips()
        self.assertEqual(engine.loads,['video.mp4'])
        seq.clock.elapsed_ms=4060
        seq.tick()
        self.assertTrue(seq.running)
        self.assertEqual(seq.position,4060)
        self.assertEqual(seq.current_id,b['id'])
        self.assertEqual(engine.loads,['video.mp4'])
        self.assertEqual(engine.seeks[-1],6060)
        self.assertEqual(engine.player.pause_count,0)

    def test_same_source_contiguous_offset_skips_seek_if_already_playing(self):
        seq,engine,a,b=self.player_with_clips(right_in_ms=4000)
        engine.player._position=4030
        previous=len(engine.seeks)
        seq.clock.elapsed_ms=4060
        seq.tick()
        self.assertEqual(len(engine.seeks),previous)
        self.assertEqual(engine.loads,['video.mp4'])
        self.assertTrue(seq.running)

    def test_manual_seek_is_exact_even_if_difference_is_under_120_ms(self):
        seq,engine,a,b=self.player_with_clips()
        seq.seek(75)
        self.assertEqual(seq.position,75)
        self.assertEqual(engine.seeks[-1],75)

    def test_true_gap_pauses_at_start_of_gap(self):
        seq,engine,a,b=self.player_with_clips(second_start=4800)
        seq.clock.elapsed_ms=4100
        seq.tick()
        self.assertFalse(seq.running)
        self.assertEqual(seq.position,4000)
        self.assertEqual(seq.current_id,a['id'])
        self.assertGreaterEqual(engine.player.pause_count,1)

    def test_two_different_files_need_to_change_source_without_pausing_sequence(self):
        seq,engine,a,b=self.player_with_clips(right_source='b.mp4',right_in_ms=0)
        seq.clock.elapsed_ms=4020
        seq.tick()
        self.assertTrue(seq.running)
        self.assertEqual(engine.loads,['video.mp4','b.mp4'])
        self.assertEqual(seq.current_id,b['id'])

    def test_gap_stop_can_be_disabled(self):
        seq,engine,a,b=self.player_with_clips(second_start=4500)
        seq.stop_at_cuts=False
        seq.clock.elapsed_ms=4050
        seq.tick()
        self.assertTrue(seq.running)
        self.assertEqual(seq.position,4050)

    def fast_clip_player(self, speed):
        clip=make_clip('video.mp4',1000,start_ms=0,kind='video')
        clip['speed']=speed
        timeline=types.SimpleNamespace(clips=[clip])
        engine=_Engine()
        seq=self.SequencePlayer(engine,timeline)
        seq.play()
        return seq,engine,clip

    def test_high_speed_uses_step_preview_instead_of_fast_decoding(self):
        seq,engine,clip=self.fast_clip_player(16)
        self.assertTrue(seq.stepping)
        self.assertEqual(engine.player.rate,1.0)      # nunca 16× en el decodificador
        self.assertEqual(engine.player.play_count,0)  # pausado: sólo seeks
        seeks=len(engine.seeks)
        with patch('time.monotonic',return_value=1e6):
            seq.clock.elapsed_ms=500
            seq.tick()
        self.assertEqual(engine.seeks[-1],8000)       # 500 ms de Timeline × 16
        self.assertEqual(len(engine.seeks),seeks+1)
        with patch('time.monotonic',return_value=1e6+0.05):
            seq.clock.elapsed_ms=550
            seq.tick()
        self.assertEqual(len(engine.seeks),seeks+1)   # intervalo mínimo entre pasos
        with patch('time.monotonic',return_value=1e6+0.2):
            seq.clock.elapsed_ms=700
            seq.tick()
        self.assertEqual(engine.seeks[-1],11200)
        seq.on_position(123)                          # posiciones de seek no mueven el reloj
        self.assertEqual(seq.position,700)

    def test_normal_and_slow_speeds_keep_real_playback(self):
        for speed in (0.1,1.0,4.0):
            seq,engine,clip=self.fast_clip_player(speed)
            self.assertFalse(seq.stepping,speed)
            self.assertEqual(engine.player.rate,speed)
            self.assertEqual(engine.player.play_count,1)


if __name__=='__main__':unittest.main()
