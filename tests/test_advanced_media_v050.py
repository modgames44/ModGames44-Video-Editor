"""Regresiones para exportación animada, composición y audio continuo."""
import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from effects.compositor import active_layers, composite_frame
from exporter.animated_effects import local_keys, zoompan_filter
from exporter.render import build_export_command, ExportProfile
from services.continuous_audio import build_stream_command, pcm_stereo_peaks
from timeline.model import make_clip
from effects.model import default_effects


class AnimatedExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.profile=ExportProfile('tiny','h264','mp4',160,90,10,'600k')
        self.ffmpeg=shutil.which('ffmpeg')
        if not self.ffmpeg:self.skipTest('ffmpeg no está disponible')
        self.media=str(self.root/'sample.mp4')
        r=subprocess.run([self.ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i',
                 'testsrc2=s=160x90:r=10:d=3','-f','lavfi','-i',
                 'sine=frequency=440:sample_rate=48000:d=3',
                 '-c:v','mpeg4','-c:a','aac','-shortest',self.media],capture_output=True,timeout=20)
        if r.returncode:raise AssertionError(r.stderr.decode()[-900:])
        self.clip=make_clip(self.media,3000)
        self.clip['effects']=default_effects()

    def tearDown(self):self.tmp.cleanup()

    def test_zoom_keys_interpolated_source_time(self):
        c=dict(self.clip,in_ms=1000,speed=2,duration_ms=1000)
        zoom=dict(scale=1,cx=.5,cy=.5,keys=[
             dict(time_ms=1000,scale=1,cx=.5,cy=.5),
             dict(time_ms=3000,scale=2,cx=.6,cy=.5)])
        pts=local_keys(c,zoom,('scale','cx','cy'))
        self.assertAlmostEqual(pts[0][0],0)
        self.assertAlmostEqual(pts[-1][0],1)
        self.assertAlmostEqual(pts[-1][1]['scale'],2)
        self.assertIn('in_time',zoompan_filter(c,{'zoom':{'enabled':True,**zoom}},self.profile))

    def test_render_real_animated_mask_and_zoom(self):
        fx=copy.deepcopy(self.clip['effects'])
        fx['zoom'].update(enabled=True,keys=[
            dict(time_ms=0,scale=1,cx=.5,cy=.5),
            dict(time_ms=2900,scale=2,cx=.65,cy=.5)])
        fx['censor'].update(enabled=True,mode='blur',strength=20,feather=.02,keys=[
            dict(time_ms=0,x=.1,y=.2,w=.25,h=.4),
            dict(time_ms=2900,x=.55,y=.2,w=.25,h=.4)])
        c={**self.clip,'effects':fx}
        path=str(self.root/'render.mp4')
        args,warnings=build_export_command([c],self.profile,path,
                         {'ffmpeg':self.ffmpeg,'encoder':'libx264'})
        graph=args[args.index('-filter_complex')+1]
        self.assertIn('zoompan=',graph)
        self.assertIn('maskedmerge',graph)
        self.assertFalse(any('estátic' in x for x in warnings))
        result=subprocess.run(args,capture_output=True,timeout=80)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace')[-800:])
        self.assertGreater(Path(path).stat().st_size,1000)
        # Los fotogramas reales generados en distintos instantes deben diferir.
        import cv2
        cap=cv2.VideoCapture(path)
        frames=[]
        for frame_no in (2,25):
            cap.set(cv2.CAP_PROP_POS_FRAMES,frame_no)
            ok,frame=cap.read()
            self.assertTrue(ok)
            frames.append(frame)
        cap.release()
        import numpy as np
        self.assertGreater(np.abs(frames[0].astype('i2')-frames[1].astype('i2')).mean(),5)

    def test_continuous_pcm_spans_clip_boundary(self):
        c1=make_clip(self.media,1200,kind='audio')
        c2=make_clip(self.media,1200,start_ms=1200,kind='audio',in_ms=500)
        cmd=build_stream_command([c1,c2],0,2400,self.ffmpeg)
        self.assertNotIn('.wav',str(cmd))
        result=subprocess.run(cmd,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace')[-400:])
        self.assertEqual(len(result.stdout),2400*48*4)
        first=result.stdout[400*48*4:500*48*4]
        second=result.stdout[1700*48*4:1800*48*4]
        self.assertGreater(pcm_stereo_peaks(first)[0],0.02)
        self.assertGreater(pcm_stereo_peaks(second)[0],0.02)


class CompositorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)
        Image.new('RGB',(64,36),'red').save(self.path/'red.png')
        Image.new('RGB',(64,36),'blue').save(self.path/'blue.png')
        self.bottom=make_clip(str(self.path/'red.png'),2000,kind='video',track=0)
        self.top=make_clip(str(self.path/'blue.png'),2000,kind='video',track=1)
        self.top['fade_in_ms']=1000
    def tearDown(self):self.tmp.cleanup()
    def test_multiple_layers_and_alpha_fade(self):
        self.assertEqual(len(active_layers([self.bottom,self.top],500)),2)
        a=composite_frame([self.bottom,self.top],0,(64,36))
        middle=composite_frame([self.bottom,self.top],500,(64,36))
        b=composite_frame([self.bottom,self.top],1200,(64,36))
        self.assertEqual(a.getpixel((32,18)),(255,0,0))
        self.assertTrue(110<middle.getpixel((32,18))[0]<140)
        self.assertEqual(b.getpixel((32,18)),(0,0,255))


if __name__=='__main__':unittest.main()

class DynamicMaskPositions(unittest.TestCase):
    def test_mask_moves_in_encoded_output(self):
        if not shutil.which('ffmpeg'):
            self.skipTest('Sin FFmpeg')
        with tempfile.TemporaryDirectory() as folder:
            import numpy as np
            import cv2
            frame=np.zeros((90,160,3),dtype=np.uint8)
            # Ruido determinista contrastado en imagen inmóvil.
            rng=np.random.default_rng(12)
            frame=rng.integers(20,240,size=(90,160,3),dtype=np.uint8)
            path=Path(folder)/'noise.png'
            cv2.imwrite(str(path),frame)
            clip=make_clip(str(path),3000)
            fx=default_effects()
            fx['censor'].update(enabled=True,mode='blur',strength=60,feather=.015,
                keys=[dict(time_ms=0,x=.05,y=.25,w=.3,h=.5),
                      dict(time_ms=2900,x=.6,y=.25,w=.3,h=.5)])
            clip['effects']=fx
            prof=ExportProfile('s','h264','mp4',160,90,10,'1M')
            out=str(Path(folder)/'encoded.mp4')
            cmd,w=build_export_command([clip],prof,out,
                       {'ffmpeg':'ffmpeg','encoder':'libx264'})
            result=subprocess.run(cmd,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace')[-900:])
            cap=cv2.VideoCapture(out)
            images=[]
            for frame_number in (0,29):
                cap.set(cv2.CAP_PROP_POS_FRAMES,frame_number)
                ok,decoded=cap.read()
                self.assertTrue(ok)
                images.append(decoded)
            cap.release()
            # La varianza (detalle) de la región censurada cambia de izquierda a derecha.
            def variance(im,x0,x1):
                return float(im[26:62,x0:x1].var())
            self.assertLess(variance(images[0],12,48),variance(images[0],105,141)*.65)
            self.assertLess(variance(images[1],105,141),variance(images[1],12,48)*.65)
