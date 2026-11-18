"""Regresión: fades independientes, cortes, audio real, exportación."""
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from timeline.fades import (fade_durations, fade_factor, change_fade,
                            video_fade_filters, audio_fade_filters)
from timeline.model import make_clip, split
from timeline.editing import trim_linked
from timeline.history import History
from exporter.render import ExportProfile, build_export_command
from services.preview_audio import render_audio_window, audio_signature


class FadeMathTests(unittest.TestCase):
    def setUp(self):
        self.v = make_clip('video.mp4', 6000, 1000, kind='video', link='both')
        self.a = make_clip('video.mp4', 6000, 1000, kind='audio', link='both')

    def test_initial_and_final_time(self):
        change_fade(self.v,'in',1200)
        change_fade(self.v,'out',1800)
        self.assertAlmostEqual(fade_factor(self.v,1000),0)
        self.assertAlmostEqual(fade_factor(self.v,1600),.5)
        self.assertAlmostEqual(fade_factor(self.v,3000),1)
        self.assertAlmostEqual(fade_factor(self.v,6100),.5)
        self.assertAlmostEqual(fade_factor(self.v,7000),0)

    def test_zero_fade(self):
        self.assertEqual(fade_factor(self.v,1000),1)
        self.assertEqual(fade_factor(self.v,4000),1)

    def test_fades_independent_of_link(self):
        change_fade(self.v,'in',2000)
        change_fade(self.a,'out',1000)
        self.assertEqual(fade_durations(self.v),(2000,0))
        self.assertEqual(fade_durations(self.a),(0,1000))
        self.assertEqual(self.v['link'],self.a['link'])

    def test_clamped_to_total_duration(self):
        change_fade(self.v,'in',6000)
        change_fade(self.v,'out',6000)
        self.assertEqual(fade_durations(self.v),(6000,0))
        change_fade(self.v,'in',1000)
        change_fade(self.v,'out',10000)
        self.assertEqual(fade_durations(self.v),(1000,5000))

    def test_cut_keeps_external_fades(self):
        change_fade(self.v,'in',500)
        change_fade(self.v,'out',1200)
        clips=[self.v]
        right_id=split(clips,self.v['id'],3500)
        left,right=clips
        self.assertEqual(left['fade_in_ms'],500)
        self.assertEqual(left['fade_out_ms'],0)
        self.assertEqual(right['fade_in_ms'],0)
        self.assertEqual(right['fade_out_ms'],1200)
        self.assertEqual(right['id'],right_id)

    def test_trim_never_leaves_invalid_fades(self):
        change_fade(self.v,'in',2500)
        change_fade(self.v,'out',1500)
        change_fade(self.a,'in',1800)
        clips=[self.v,self.a]
        self.assertTrue(trim_linked(clips,self.v['id'],'final',-2500,
                                    {'video.mp4':6000}))
        for c in clips:
            fi,fo=fade_durations(c)
            self.assertLessEqual(fi+fo,c['duration_ms'])

    def test_history_restores_independent_fades(self):
        hist=History()
        clips=[self.v,self.a]
        hist.record(clips)
        change_fade(clips[0],'in',900)
        old=hist.undo(clips)
        self.assertEqual(old[0]['fade_in_ms'],0)
        new=hist.redo(old)
        self.assertEqual(new[0]['fade_in_ms'],900)

    def test_absolute_preview_does_not_restart_fade(self):
        change_fade(self.a,'in',2000)
        change_fade(self.a,'out',1000)
        f=audio_fade_filters(self.a,offset_ms=1500)
        self.assertEqual(len(f),1)
        self.assertIn('t+1.500000',f[0])
        self.assertIn('volume=',f[0])
        self.assertEqual(len(audio_fade_filters(self.a)),2)

    def test_ffmpeg_filters_alpha(self):
        change_fade(self.v,'in',700)
        change_fade(self.v,'out',1100)
        f=video_fade_filters(self.v)
        self.assertEqual(f[0],'format=rgba')
        self.assertTrue(all('alpha=1' in x for x in f[1:]))

    def test_audio_signature_invalidated_by_fades(self):
        original=audio_signature([self.a])
        change_fade(self.a,'out',1000)
        self.assertNotEqual(original,audio_signature([self.a]))

    def test_video_track_and_audio_track_are_distinct(self):
        self.assertEqual(self.v['track'],self.a['track'])
        self.a['track']=2
        self.assertEqual(self.v['track'],0)
        self.assertEqual(self.a['track'],2)


class FadeMediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = shutil.which('ffmpeg')
        cls.ffprobe = shutil.which('ffprobe')
        if cls.ffmpeg is None:
            raise unittest.SkipTest('FFmpeg no disponible')
        cls.temp=tempfile.TemporaryDirectory()
        cls.source=Path(cls.temp.name)/'test.mp4'
        p=subprocess.run([cls.ffmpeg,'-hide_banner','-loglevel','error','-y',
                          '-f','lavfi','-i','color=c=red:size=160x90:rate=25:duration=3',
                          '-f','lavfi','-i','sine=frequency=500:sample_rate=48000:duration=3',
                          '-c:v','libx264','-c:a','aac','-shortest',str(cls.source)],
                         capture_output=True,timeout=30)
        if p.returncode:
            raise unittest.SkipTest('No se pudo fabricar MP4 de prueba')

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,'temp'):cls.temp.cleanup()

    def _rms(self, wav_path):
        # audioop se eliminó en Python 3.13: RMS de PCM 16 bits con numpy.
        import numpy as np
        with wave.open(str(wav_path),'rb') as w:
            samples=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64)
        return int(np.sqrt(np.mean(samples**2))) if samples.size else 0

    def test_preview_audio_fades_in_every_window(self):
        a=make_clip(str(self.source),3000,kind='audio')
        change_fade(a,'in',1000)
        change_fade(a,'out',1000)
        amps=[]
        for off in (0,300,1250,2200,2700):
            dst=Path(self.temp.name)/f'window{off}.wav'
            render_audio_window([a],off,200,dst,self.ffmpeg)
            amps.append(self._rms(dst))
        self.assertLess(amps[0],amps[1])
        self.assertLess(amps[1],amps[2])
        self.assertGreater(amps[2],amps[3])
        self.assertGreater(amps[3],amps[4])

    def test_export_actual_video_and_audio_fades(self):
        v=make_clip(str(self.source),3000,kind='video')
        a=make_clip(str(self.source),3000,kind='audio')
        for c in (v,a):
            change_fade(c,'in',800)
            change_fade(c,'out',800)
        dest=Path(self.temp.name)/'faded.mp4'
        args,warnings=build_export_command([v,a],
                   ExportProfile('test','h264','mp4',160,90,25,'400k'),dest,
                   {'ffmpeg':self.ffmpeg,'encoder':'libx264'})
        graph=args[args.index('-filter_complex')+1]
        self.assertIn('fade=t=in:',graph)
        self.assertIn('alpha=1',graph)
        self.assertIn('afade=t=in:',graph)
        self.assertIn('afade=t=out:',graph)
        p=subprocess.run(args,capture_output=True,timeout=35)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace')[-2000:])
        self.assertGreater(dest.stat().st_size,1500)
        # La imagen roja debe empezar negra, ser roja a mitad y volver a negro.
        def pixel(sec):
            z=subprocess.run([self.ffmpeg,'-v','error','-ss',str(sec),'-i',str(dest),
                '-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'],
                capture_output=True,timeout=10)
            self.assertEqual(z.returncode,0,z.stderr.decode())
            return z.stdout[0]
        first,mid,last=pixel(.04),pixel(1.5),pixel(2.96)
        self.assertLess(first,mid*.35)
        self.assertLess(last,mid*.35)

if __name__=='__main__':unittest.main()
