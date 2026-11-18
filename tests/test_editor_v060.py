"""v0.6: pruebas de funciones de montaje, títulos y recursos."""
import tempfile
import subprocess
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from core.autosave_recovery import save_recovery,load_recovery,clear_recovery
from core.project_manager import empty_project
from effects.title_overlay import title_clip,render_title_png,transform_at
from timeline.model import make_clip,split
from timeline.ripple import ripple_remove
from timeline.transitions import crossfade_adjacent
from services.proxy_manager import proxy_path,proxy_command
from services.thumb_cache import thumb_path,enforce_limit
from services.captioning import normalize_segments
from services.subtitles_srt import srt_text
from effects.keyframe_expressions import ffmpeg_expression
from exporter.render import build_export_command,ExportProfile
from services.preview_audio import build_audio_preview_command,audio_signature

class EditingTests(unittest.TestCase):
    def test_ripple_preserves_linked_synchrony(self):
        a=make_clip('one.mp4',1000,0,0,kind='video',link='a')
        b=make_clip('one.mp4',1000,0,0,kind='audio',link='a')
        c=make_clip('two.mp4',2000,1000,0,kind='video',link='b')
        d=make_clip('two.mp4',2000,1000,0,kind='audio',link='b')
        clips=[a,b,c,d]
        self.assertEqual(ripple_remove(clips,{a['id']}),2)
        self.assertEqual(len(clips),2)
        self.assertEqual((c['start_ms'],d['start_ms']),(0,0))
    def test_ripple_keeps_unaffected_other_tracks(self):
        a=make_clip('one.mp4',1000)
        b=make_clip('two.mp4',1000,1000)
        other=make_clip('overlay.mp4',2000,1000,track=1)
        items=[a,b,other]
        ripple_remove(items,{a['id']})
        self.assertEqual((b['start_ms'],other['start_ms']),(0,1000))
    def test_transition_blends_and_keeps_audio_links(self):
        a=make_clip('one.mp4',2000,link='a')
        aa=make_clip('one.mp4',2000,kind='audio',link='a')
        b=make_clip('two.mp4',2000,start_ms=2000,link='b')
        bb=make_clip('two.mp4',2000,start_ms=2000,kind='audio',link='b')
        clips=[a,aa,b,bb]
        self.assertTrue(crossfade_adjacent(clips,a['id'],600))
        self.assertEqual(b['start_ms'],1400)
        self.assertEqual(bb['start_ms'],1400)
        self.assertEqual(b['fade_in_ms'],600)
        self.assertEqual(aa['fade_out_ms'],600)
        self.assertEqual(a['fade_out_ms'],0)
        self.assertFalse(crossfade_adjacent(clips,b['id']))
    def test_transition_continues_across_boundary(self):
        from timeline.playback_boundaries import limited_position
        a=make_clip('a.mp4',2000);b=make_clip('b.mp4',2000,start_ms=2000)
        self.assertTrue(crossfade_adjacent([a,b],a['id'],600))
        self.assertFalse(limited_position([a,b],a['id'],2050,True)[1])
    def test_transition_keeps_downstream_contiguous(self):
        a=make_clip('a.mp4',2000);b=make_clip('b.mp4',2000,start_ms=2000)
        c=make_clip('c.mp4',1000,start_ms=4000)
        clips=[a,b,c]
        self.assertTrue(crossfade_adjacent(clips,a['id'],600))
        self.assertEqual((b['start_ms'],c['start_ms']),(1400,3400))
    def test_title_split_remaps_keyframes(self):
        c=title_clip('Hola',0,2000)
        c['transform_keys']=[dict(time_ms=0,x=.2),dict(time_ms=2000,x=.8)]
        clips=[c]
        right=split(clips,c['id'],1000)
        self.assertIsNotNone(right)
        self.assertAlmostEqual(transform_at(clips[0],1000)['x'],.5)
        self.assertAlmostEqual(transform_at(clips[1],1000)['x'],.5)
        self.assertAlmostEqual(transform_at(clips[1],2000)['x'],.8)

class DataTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_recovery_without_project_file(self):
        data=empty_project();data['media']=['video.mp4']
        target=save_recovery(data,cache_root=self.root)
        self.assertTrue(target.exists())
        self.assertEqual(load_recovery(cache_root=self.root),data)
        clear_recovery(cache_root=self.root)
        self.assertIsNone(load_recovery(cache_root=self.root))
    def test_proxy_does_not_modify_original(self):
        original=self.root/'source.mp4';original.write_bytes(b'original')
        out=proxy_path(original,self.root)
        args=proxy_command(original,out)
        self.assertIn(str(original),args)
        self.assertIn('-crf',args)
        self.assertEqual(original.read_bytes(),b'original')
    def test_thumbnail_cache_invalidated_by_change(self):
        media=self.root/'source.mp4';media.write_bytes(b'a')
        first=thumb_path(media,500,160,90,self.root)
        media.write_bytes(b'changed')
        self.assertNotEqual(first,thumb_path(media,500,160,90,self.root))
    def test_thumbnail_cache_enforces_limit(self):
        for idx in range(4):
            (self.root/(str(idx)+'.jpg')).write_bytes(b'a'*50)
        enforce_limit(self.root,max_bytes=100)
        self.assertLessEqual(sum(p.stat().st_size for p in self.root.glob('*.jpg')),100)
    def test_caption_alignment_and_srt(self):
        segments=[SimpleNamespace(start=1.2,end=2.5,text=' hola   mundo '),
                  SimpleNamespace(start=2.7,end=3.2,text='  otro  ')]
        caps=normalize_segments(segments,3200)
        self.assertEqual(caps[0].start_ms,1200)
        self.assertEqual(caps[0].text,'hola mundo')
        c=title_clip(caps[0].text,caps[0].start_ms,caps[0].end_ms-caps[0].start_ms,subtitle=True)
        self.assertIn('00:00:01,200 --> 00:00:02,500',srt_text([c]))
    def test_title_png_and_transform(self):
        c=title_clip('ModGames44',0,2000)
        c['transform_keys']=[dict(time_ms=0,x=.2,scale=.8,rotation=0,opacity=.2),
                              dict(time_ms=2000,x=.8,scale=1.2,rotation=20,opacity=1)]
        self.assertAlmostEqual(transform_at(c,1000)['x'],.5)
        self.assertAlmostEqual(transform_at(c,1000)['scale'],1)
        output,size=render_title_png(c,320,180,cache_root=self.root)
        self.assertTrue(output.exists())
        with Image.open(output) as bitmap:
            self.assertEqual(bitmap.mode,'RGBA')
        self.assertIn('if(lt',ffmpeg_expression(c['transform_keys'],'scale',1))

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ffmpeg=shutil.which('ffmpeg')
        if not self.ffmpeg:self.skipTest('FFmpeg no disponible')
        self.profile=ExportProfile('small','h264','mp4',320,180,10,'450k')
    def tearDown(self):self.tmp.cleanup()
    def test_animated_title_video_real(self):
        c=title_clip('ModGames44',0,1500)
        c['transform_keys']=[dict(time_ms=0,x=.2,y=.3,scale=.7,rotation=0,opacity=0),
                             dict(time_ms=1400,x=.7,y=.7,scale=1.3,rotation=20,opacity=1)]
        dest=self.root/'title.mp4'
        command,warnings=build_export_command([c],self.profile,dest,
                                               {'ffmpeg':self.ffmpeg,'encoder':'libx264'})
        graph=command[command.index('-filter_complex')+1]
        for required in ('geq=', 'rotate=', 'scale=w=', 'overlay=x='):
            self.assertIn(required,graph)
        p=subprocess.run(command,capture_output=True,timeout=80)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace')[-1000:])
        self.assertGreater(dest.stat().st_size,1500)
    def test_title_over_real_clip_and_original_source(self):
        sample=self.root/'sample.mp4'
        subprocess.run([self.ffmpeg,'-loglevel','error','-y','-f','lavfi','-i',
                        'testsrc2=s=320x180:r=10:d=2','-c:v','mpeg4',str(sample)],
                       capture_output=True,check=True,timeout=20)
        c=make_clip(str(sample),2000)
        title=title_clip('Prueba',500,800)
        dest=self.root/'out.mp4'
        command,_=build_export_command([c,title],self.profile,dest,
                                       {'ffmpeg':self.ffmpeg,'encoder':'libx264'})
        self.assertIn(str(sample),command)
        result=subprocess.run(command,capture_output=True,timeout=70)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace')[-800:])
        self.assertGreater(dest.stat().st_size,2000)
    def test_audio_volume_keyframes_preview_and_export(self):
        media=self.root/'sample.wav'
        subprocess.run([self.ffmpeg,'-loglevel','error','-y','-f','lavfi','-i',
                        'sine=frequency=440:sample_rate=48000:d=2','-c:a','pcm_s16le',str(media)],
                       capture_output=True,check=True,timeout=20)
        clip=make_clip(str(media),2000,kind='audio')
        clip['volume_keys']=[dict(time_ms=0,volume=0.2),dict(time_ms=1500,volume=1)]
        cmd=build_audio_preview_command([clip],0,2000,'pipe:1',self.ffmpeg)
        graph=cmd[cmd.index('-filter_complex')+1]
        self.assertIn('volume=',graph)
        before=audio_signature([clip]);clip['volume_keys'][0]['volume']=.4
        self.assertNotEqual(before,audio_signature([clip]))
        from services.continuous_audio import build_stream_command
        cmd=build_stream_command([clip],300,2000,self.ffmpeg)
        p=subprocess.run(cmd,capture_output=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace')[-900:])
        export,_=build_export_command([clip],self.profile,self.root/'volume.mp4',
                                      {'ffmpeg':self.ffmpeg,'encoder':'libx264'})
        self.assertIn("volume='",export[export.index('-filter_complex')+1])

if __name__=='__main__':unittest.main()
