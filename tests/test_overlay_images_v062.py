"""Regresiones de imágenes en Timeline, geometría del mouse y exportación."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image,ImageDraw
from effects.image_overlay import image_clip,render_image_png
from effects.overlay_geometry import overlay_hit,drag_overlay_transform
from effects.title_overlay import title_clip,render_title_png,transform_at,active_titles
from exporter.render import ExportProfile,build_export_command,validate_project
from timeline.model import split
from core.project_manager import save_project,load_project


class OverlayImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/'marca.png'
        image=Image.new('RGBA',(200,80),(0,0,0,0))
        ImageDraw.Draw(image).rectangle((10,5,190,75),fill=(230,20,30,180))
        image.save(self.source)

    def test_image_clip_valid_and_default_track(self):
        clip=image_clip(self.source,1500)
        self.assertEqual(clip['kind'],'image')
        self.assertEqual(clip['track'],2)
        self.assertEqual(clip['duration_ms'],5000)
        self.assertEqual(validate_project([clip]),6500)
        self.assertEqual(transform_at(clip,1500)['x'],.5)

    def test_image_png_preserves_transparency_and_aspect(self):
        clip=image_clip(self.source,0)
        path,size=render_image_png(clip,320,180,cache_root=self.root/'cache')
        self.assertEqual(size,(128,51))
        with Image.open(path) as image:
            self.assertEqual(image.mode,'RGBA')
            self.assertEqual(image.getpixel((0,0))[3],0)
            self.assertGreater(image.getpixel((30,20))[3],0)

    def test_image_cache_changes_when_source_updated(self):
        clip=image_clip(self.source,0)
        p1,_=render_image_png(clip,320,180,cache_root=self.root/'cache')
        Image.new('RGBA',(250,40),'blue').save(self.source)
        p2,_=render_image_png(clip,320,180,cache_root=self.root/'cache')
        self.assertNotEqual(p1,p2)

    def test_invalid_image_rejected(self):
        bad=self.root/'not_an_image.png'
        bad.write_text('invalid',encoding='utf8')
        with self.assertRaises(OSError):image_clip(bad,0)
        with self.assertRaises(ValueError):image_clip(self.root/'none.jpg',0)

    def test_screen_hit_and_drag_clamp(self):
        self.assertEqual(overlay_hit(100,100,100,100,80,40),'move')
        self.assertEqual(overlay_hit(140,120,100,100,80,40),'se')
        self.assertIsNone(overlay_hit(160,160,100,100,80,40))
        start={'x':.5,'y':.5,'scale':1.,'rotation':0.,'opacity':1.}
        moved=drag_overlay_transform(start,'move',(100,100),(160,130),(200,100),(100,100),(80,40))
        self.assertAlmostEqual(moved['x'],.8)
        self.assertAlmostEqual(moved['y'],.8)
        limited=drag_overlay_transform(start,'move',(100,100),(-300,-100),(200,100),(100,100),(80,40))
        self.assertEqual((limited['x'],limited['y']),(0.,0.))
        scaled=drag_overlay_transform(start,'se',(140,120),(180,140),(200,100),(100,100),(80,40))
        self.assertGreater(scaled['scale'],1.)
        self.assertLessEqual(scaled['scale'],5.)

    def test_hit_rotated_overlay(self):
        self.assertEqual(overlay_hit(80,140,100,100,80,40,90),'se')

    def test_image_split_preserves_transform(self):
        clip=image_clip(self.source,0,4000)
        clip['transform_keys']=[{'time_ms':0,'x':.3,'scale':1},
                                {'time_ms':4000,'x':.7,'scale':2}]
        clips=[clip]
        right_id=split(clips,clip['id'],2000)
        right=next(c for c in clips if c['id']==right_id)
        self.assertAlmostEqual(right['transform_keys'][0]['x'],.5)
        self.assertEqual(right['transform_keys'][0]['time_ms'],0)

    def test_font_family_changes_cache_and_project_roundtrip(self):
        text=title_clip('ModGames44',0)
        a,_=render_title_png(text,320,180,cache_root=self.root/'titles')
        text['title_style']['font_family']='DejaVu Sans'
        b,_=render_title_png(text,320,180,cache_root=self.root/'titles')
        self.assertNotEqual(a,b)
        clip=image_clip(self.source,500)
        project={'version':1,'clips':[text,clip],'media':[],'fps':30}
        dest=self.root/'project.mg44'
        save_project(dest,project)
        loaded=load_project(dest)
        self.assertEqual(loaded['clips'][0]['title_style']['font_family'],'DejaVu Sans')
        self.assertEqual(loaded['clips'][1]['kind'],'image')

    def test_active_overlay_selects_text_and_images(self):
        clips=[title_clip('a',0),image_clip(self.source,0)]
        self.assertEqual(len(active_titles(clips,500)),2)
        self.assertEqual(len(active_titles(clips,5500)),0)

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg no disponible')
    def test_actual_ffmpeg_export_preserves_image_position(self):
        clip=image_clip(self.source,0,800)
        clip['transform_keys']=[{'time_ms':0,'x':.75,'y':.5,'scale':1,'rotation':0,'opacity':1}]
        profile=ExportProfile('prueba','h264','mp4',160,90,12,'350k')
        dest=self.root/'export.mp4'
        command,_=build_export_command([clip],profile,dest,
                                        {'ffmpeg':shutil.which('ffmpeg'),'encoder':'libx264'})
        completed=subprocess.run(command,capture_output=True,text=True,timeout=25)
        self.assertEqual(completed.returncode,0,completed.stderr[-1000:])
        self.assertGreater(dest.stat().st_size,1000)
        # Se comprueba el punto rojo del gráfico, situado a la derecha del lienzo.
        frame=self.root/'frame.png'
        grab=subprocess.run([shutil.which('ffmpeg'),'-hide_banner','-loglevel','error',
            '-ss','0.3','-i',str(dest),'-frames:v','1','-y',str(frame)],capture_output=True,text=True,timeout=10)
        self.assertEqual(grab.returncode,0,grab.stderr)
        with Image.open(frame) as image:
            rgb=image.convert('RGB')
            red=[x for x in range(rgb.width) for y in range(rgb.height)
                 if (lambda c:c[0]>110 and c[0]>c[1]*2)(rgb.getpixel((x,y)))]
            self.assertTrue(red)
            self.assertGreater(sum(red)/len(red),rgb.width*.61)


if __name__=='__main__':unittest.main()
