"""Regresión del procesamiento de audio, render y detección de codificadores."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from effects.audio import audio_filter_chain, validated_audio_effects
from exporter.hardware import (available_encoders, select_encoder, vendor)
from exporter.render import (ExportProfile, PROFILES, build_export_command,
                             validate_project)
from timeline.model import make_clip


class AudioExportTests(unittest.TestCase):
    def setUp(self):
        self.path = __file__
        self.video = make_clip(self.path, 1500, kind='video', link='a')
        self.audio = make_clip(self.path, 1500, kind='audio', link='a')
        self.profile=ExportProfile('test','h264','mp4',320,180,25,'600k')
        self.cpu={'ffmpeg':'ffmpeg','vendor':'CPU','encoder':'libx264'}

    def test_default_audio(self):
        self.assertEqual(audio_filter_chain({},1), [])
    def test_invalid_profile(self):
        with self.assertRaises(ValueError):validated_audio_effects({'voice':'AdobeExact'})
    def test_nonfinite_gain(self):
        with self.assertRaises(ValueError):validated_audio_effects({'volume_db':float('nan')})
    def test_volume_limits(self):
        self.assertEqual(validated_audio_effects({'volume_db':35})['volume_db'],24)
        self.assertEqual(validated_audio_effects({'volume_db':-40})['volume_db'],-36)
    def test_podcast_chain(self):
        data=audio_filter_chain({'voice':'podcast','noise':.3,'volume_db':6},1)
        joined=','.join(data)
        self.assertIn('afftdn',joined)
        self.assertIn('equalizer',joined)
        self.assertIn('acompressor',joined)
        self.assertIn('volume=6.000dB',joined)
    def test_high_low_differ(self):
        self.assertNotEqual(audio_filter_chain({'voice':'high'}),
                            audio_filter_chain({'voice':'low'}))
    def test_speed_quarter(self):
        self.assertEqual(audio_filter_chain({},.25),['atempo=0.5','atempo=0.5'])
    def test_speed_quadruple(self):
        self.assertEqual(audio_filter_chain({},4.),['atempo=2.0','atempo=2.0'])
    def test_noise_none(self):
        self.assertFalse(any('afftdn' in x for x in audio_filter_chain({'noise':0})))
    def test_normalization(self):
        self.assertIn('loudnorm=I=-16:TP=-1.5:LRA=11',audio_filter_chain({'normalize':True}))
    def test_empty_project(self):
        with self.assertRaises(ValueError):validate_project([])
    def test_missing_media(self):
        bad=make_clip('no_file_not_here.mp4',1000)
        with self.assertRaises(FileNotFoundError):validate_project([bad])
    def test_video_audio_timeline_map(self):
        v=self.video
        a=self.audio
        v['start_ms']=300
        a['start_ms']=300
        a['audio_fx']={'voice':'high','volume_db':3}
        args,w=build_export_command([v,a],self.profile,'out.mp4',self.cpu)
        f=args[args.index('-filter_complex')+1]
        self.assertIn('adelay=300:all=1', f)
        self.assertIn('acompressor',f)
        self.assertIn('overlay=0:0',f)
    def test_censor_and_zoom_commands(self):
        self.video['effects']={'censor':{'enabled':True,'mode':'mosaic','strength':12},
                               'zoom':{'enabled':True,'scale':2,'cx':.5,'cy':.5}}
        args,w=build_export_command([self.video],self.profile,'out.mp4',self.cpu)
        f=args[args.index('-filter_complex')+1]
        self.assertIn('crop=',f)
        self.assertIn('flags=neighbor',f)
    def test_animation_warned(self):
        self.video['effects']={'censor':{'enabled':True,'keys':[{'time_ms':0,'x':.1,'y':.1,'w':.3,'h':.3},
                 {'time_ms':100,'x':.2,'y':.2,'w':.3,'h':.3}]}}
        args,w=build_export_command([self.video],self.profile,'out.mp4',self.cpu)
        self.assertIn('maskedmerge',args[args.index('-filter_complex')+1])
        self.assertFalse(any('posición estática' in text for text in w))
    def test_formats(self):
        self.assertEqual(PROFILES['MOV ProRes 422 1080p'].extension,'mov')
        self.assertEqual(PROFILES['WebM VP9 1080p'].codec,'vp9')
    def test_vendor(self):
        self.assertEqual(vendor('NVIDIA GeForce RTX 4060'),'NVIDIA')
        self.assertEqual(vendor('AMD Radeon RX 6800'),'AMD')
        self.assertEqual(vendor('Intel Iris Xe'),'Intel')
        self.assertIsNone(vendor('Microsoft Basic Display Adapter'))
    def test_encoder_selection(self):
        x={'options':[self.cpu]}
        self.assertEqual(select_encoder('h264','auto',x),self.cpu)
        with self.assertRaises(RuntimeError):select_encoder('h264','NVIDIA',x)
    def test_encoder_parse(self):
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg:self.skipTest('Sin FFmpeg de sistema')
        self.assertIn('libx264',available_encoders(ffmpeg))


class IntegrationExportTests(unittest.TestCase):
    def test_real_export_two_tracks(self):
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg or 'libx264' not in available_encoders(ffmpeg):
            self.skipTest('No existe FFmpeg con libx264')
        with tempfile.TemporaryDirectory() as work:
            src=Path(work)/'clip.mp4';dst=Path(work)/'result.mp4'
            subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi',
                 '-i','testsrc2=size=128x72:rate=25:duration=1.5','-f','lavfi',
                 '-i','sine=frequency=440:duration=1.5','-c:v','libx264','-c:a','aac',
                 '-shortest',str(src)],check=True,timeout=20)
            a=make_clip(str(src),650,start_ms=250,kind='audio')
            a['audio_fx']={'noise':.2,'voice':'podcast','volume_db':4}
            v=make_clip(str(src),650,start_ms=250,kind='video')
            profile=ExportProfile('test','h264','mp4',160,90,25,'300k')
            args,_=build_export_command([v,a],profile,dst,
                                        {'ffmpeg':ffmpeg,'vendor':'CPU','encoder':'libx264'})
            p=subprocess.run(args,capture_output=True,timeout=25)
            self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace')[-1500:])
            self.assertGreater(dst.stat().st_size,1000)


if __name__ == '__main__':unittest.main()
