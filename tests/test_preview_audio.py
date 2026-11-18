"""Tests funcionales con PCM real: la escucha debe USAR los efectos del exportador."""
import math
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from services.preview_audio import (audio_signature, window_bounds,
                                    audio_clips_in_window,
                                    build_audio_preview_command, render_audio_window)
from timeline.model import make_clip


class PreviewLogicTests(unittest.TestCase):
    def test_window_in_middle_and_end(self):
        self.assertEqual(window_bounds(31000,65000),(30000,30000))
        self.assertEqual(window_bounds(64000,65000),(60000,5000))
        self.assertEqual(window_bounds(0,0),(0,0))

    def test_audio_signature_changes_only_audio(self):
        audio=make_clip('voz.wav',3000,kind='audio')
        video=make_clip('video.mp4',3000,kind='video')
        initial=audio_signature([audio,video])
        video['effects']={'color':{'brightness':50}}
        self.assertEqual(initial,audio_signature([audio,video]))
        audio['audio_fx']={'volume_db':12}
        self.assertNotEqual(initial,audio_signature([audio,video]))

    def test_clip_overlap_correctly_bounded(self):
        clip=make_clip('voz.wav',2000,start_ms=4500,kind='audio')
        self.assertEqual(audio_clips_in_window([clip],5000,5000)[0][1:],(5000,6500))
        self.assertEqual(audio_clips_in_window([clip],0,2000),[])

    def test_export_audio_chain_shared(self):
        clip=make_clip(__file__,1000,kind='audio')
        clip['audio_fx']={'volume_db':-15,'noise':.2,'voice':'podcast','normalize':False}
        cmd=build_audio_preview_command([clip],0,1000,'any.wav')
        graph=cmd[cmd.index('-filter_complex')+1]
        self.assertIn('volume=-15.000dB',graph)
        self.assertIn('afftdn=',graph)
        self.assertIn('acompressor=',graph)
        self.assertIn('alimiter=',graph)


@unittest.skipUnless(shutil.which('ffmpeg'), 'Se necesita FFmpeg')
class PreviewRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.file=Path(cls.temp.name)/'voz.wav'
        cmd=[shutil.which('ffmpeg'),'-v','error','-y','-f','lavfi',
             '-i','sine=frequency=440:sample_rate=48000:duration=5',
             '-af','volume=0.8','-c:a','pcm_s16le',str(cls.file)]
        subprocess.run(cmd,check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def _render(cls, fx, start_ms=0, duration_ms=1500, offset_ms=0, speed=1):
        clip=make_clip(cls.file, 4000,start_ms=offset_ms,kind='audio')
        clip['speed']=speed
        clip['audio_fx']=fx
        path=Path(cls.temp.name)/f'render{len(list(Path(cls.temp.name).glob("render*")))}.wav'
        render_audio_window([clip],start_ms,duration_ms,path,ffmpeg=shutil.which('ffmpeg'))
        with wave.open(str(path),'rb') as wf:
            channels=wf.getnchannels();rate=wf.getframerate()
            pcm=np.frombuffer(wf.readframes(wf.getnframes()),dtype='<i2').reshape(-1,2)
        return pcm,channels,rate

    def test_volume_changes_actual_samples(self):
        original, _, _ = self._render({})
        quieter, _, _ = self._render({'volume_db':-12})
        loud=np.sqrt(np.mean(original.astype(float)**2))
        soft=np.sqrt(np.mean(quieter.astype(float)**2))
        self.assertAlmostEqual(20*math.log10(soft/loud),-12,delta=1)

    def test_volume_noise_voice_export_filt_chain(self):
        pcm,channels,rate=self._render({'volume_db':3,'noise':.25,'voice':'podcast'})
        self.assertEqual(channels,2)
        self.assertEqual(rate,48000)
        self.assertTrue(pcm.size>1000)

    def test_silence_before_and_after_clip(self):
        audio,_,_=self._render({},start_ms=0,duration_ms=3000,offset_ms=1000)
        self.assertLess(np.max(np.abs(audio[:48000].astype(np.int32))),4)
        self.assertGreater(np.max(np.abs(audio[48000:96000].astype(np.int32))),20)

    def test_2x_speed_is_not_double_length(self):
        audio,_,_=self._render({},0,2500,speed=2)
        self.assertEqual(len(audio),120000)
        # duración de clip de timeline=4000ms; fuente de 5s deja silencio tras 2.5
        self.assertGreater(np.max(np.abs(audio[1000:10000].astype(np.int32))),20)

    def test_two_tracks_are_mixed_not_replaced(self):
        a=make_clip(self.file,3000,kind='audio',track=0)
        b=make_clip(self.file,3000,kind='audio',track=1)
        path=Path(self.temp.name)/'two_tracks.wav'
        render_audio_window([a,b],0,1500,path,ffmpeg=shutil.which('ffmpeg'))
        with wave.open(str(path),'rb') as wf:
            mixed=np.frombuffer(wf.readframes(wf.getnframes()),dtype='<i2').astype(float)
        single,_,_=self._render({})
        self.assertGreater(np.sqrt(np.mean(mixed**2)),
                           np.sqrt(np.mean(single.astype(float)**2))*1.4)

    def test_seeking_inside_trimmed_clip(self):
        clip=make_clip(self.file,3000,start_ms=2000,in_ms=500,kind='audio')
        path=Path(self.temp.name)/'seektrim.wav'
        render_audio_window([clip],3000,1000,path,ffmpeg=shutil.which('ffmpeg'))
        with wave.open(str(path),'rb') as wf:
            data=np.frombuffer(wf.readframes(wf.getnframes()),dtype='<i2')
        self.assertGreater(np.max(np.abs(data.astype('i4'))),20)

    def test_all_voice_presets_and_normalize_render(self):
        for preset in ('podcast','high','low'):
            with self.subTest(voice=preset):
                pcm,_,_=self._render({'voice':preset,'noise':.1,'normalize':True},
                                     duration_ms=500)
                self.assertTrue(np.max(np.abs(pcm.astype('i4')))>20)

    def test_video_file_intact(self):
        length=self.file.stat().st_size
        self._render({'voice':'high','volume_db':2})
        self.assertEqual(length,self.file.stat().st_size)

if __name__=='__main__':unittest.main()
