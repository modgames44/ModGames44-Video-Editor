"""Pruebas de efectos sobre imágenes sintéticas y Timeline sin Qt."""
import unittest
from PIL import Image, ImageChops
from effects.model import (change_speed, merged_effects, default_effects, valid_mask,
                           add_keyframe, censor_mask, zoom_state)
from effects.renderer import render_frame
from timeline.model import make_clip, source_position, end
from timeline.editing import split_at, trim_linked


class EffectsModelTests(unittest.TestCase):
    def test_reset_censor_resets_all_settings(self):
        fx = merged_effects(None)
        fx['censor'].update(enabled=True, strength=70, mode='mosaic',
                            mask={'x':.1,'y':.2,'w':.3,'h':.4},
                            keys=[{'time_ms':100,'x':.1,'y':.2,'w':.3,'h':.4}])
        fx['censor'] = default_effects()['censor']
        self.assertFalse(fx['censor']['enabled'])
        self.assertEqual(fx['censor']['keys'], [])
        self.assertEqual(fx['censor']['mode'], 'blur')

    def test_rectangle_stays_inside_frame(self):
        m=valid_mask({'x':.95,'y':-.5,'w':.5,'h':.4})
        self.assertAlmostEqual(m['x'],.5)
        self.assertEqual(m['y'],0)
        self.assertTrue(m['x']+m['w']<=1)

    def test_keyframe_interpolates_mask(self):
        fx=merged_effects(None)
        fx['censor']['enabled']=True
        fx['censor']['keys']=[{'time_ms':0,'x':.1,'y':.1,'w':.2,'h':.2},
                              {'time_ms':1000,'x':.5,'y':.5,'w':.2,'h':.2}]
        self.assertAlmostEqual(censor_mask(fx,500)['x'],.3)
        self.assertAlmostEqual(censor_mask(fx,1000)['x'],.5)

    def test_keyframe_replace_at_same_time(self):
        keys=add_keyframe([],800,{'x':.1})
        keys=add_keyframe(keys,801,{'x':.8})
        self.assertEqual(len(keys),1)
        self.assertAlmostEqual(keys[0]['x'],.8)

    def test_slow_speed_keeps_source_duration_and_link(self):
        v=make_clip('a.mp4',10000,0,0,kind='video',link='abc')
        a=make_clip('a.mp4',10000,0,0,kind='audio',link='abc')
        clips=[v,a]
        self.assertTrue(change_speed(clips,v['id'],.5))
        self.assertEqual(end(v),20000)
        self.assertEqual(end(a),20000)
        self.assertEqual(source_position(v,10000),5000)
        self.assertEqual(source_position(a,10000),5000)

    def test_fast_speed_razor_and_trim_source_math(self):
        v=make_clip('a.mp4',12000,1000,0,kind='video',link='abc')
        a=make_clip('a.mp4',12000,1000,0,kind='audio',link='abc')
        clips=[v,a]
        change_speed(clips,v['id'],2)
        self.assertEqual(v['duration_ms'],6000)
        rid=split_at(clips,v['id'],4000)
        right=next(c for c in clips if c['id']==rid)
        self.assertEqual(right['in_ms'],6000)
        self.assertEqual(source_position(right,5000),8000)
        self.assertTrue(trim_linked(clips,right['id'],'inicio',500,{'a.mp4':12000}))
        self.assertEqual(right['in_ms'],7000)

    def test_zoom_interpolates(self):
        fx=merged_effects(None)
        fx['zoom']['keys']=[{'time_ms':0,'scale':1.,'cx':.5,'cy':.5},
                            {'time_ms':2000,'scale':2.,'cx':.3,'cy':.7}]
        self.assertAlmostEqual(zoom_state(fx,1000)['scale'],1.5)
        self.assertAlmostEqual(zoom_state(fx,1000)['cx'],.4)


class EffectsImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img=Image.new('RGB',(240,120),'white')
        for x in range(240):
            for y in range(120):
                cls.img.putpixel((x,y),(x%256,y*2%256,(x+y)%256))

    def test_no_effects_is_identical(self):
        self.assertIsNone(ImageChops.difference(self.img,render_frame(self.img,None)).getbbox())

    def test_blur_affects_only_mask_and_preserves_outside(self):
        fx=merged_effects(None)
        fx['censor'].update(enabled=True,mask={'x':.25,'y':.25,'w':.5,'h':.5},
                            feather=0,strength=20,mode='blur')
        # Patrón con detalle: un degradado lineal no cambia con un gaussiano.
        img=Image.new('RGB',(240,120))
        for x in range(240):
            for y in range(120):
                img.putpixel((x,y),(255,255,255) if (x//3+y//3)%2 else (0,0,0))
        edited=render_frame(img,fx)
        self.assertEqual(edited.getpixel((5,5)),img.getpixel((5,5)))
        self.assertNotEqual(edited.getpixel((70,40)),img.getpixel((70,40)))

    def test_mosaic_is_pixelated_inside_region(self):
        fx=merged_effects(None)
        fx['censor'].update(enabled=True,mask={'x':.1,'y':.1,'w':.7,'h':.7},
                            feather=0,strength=16,mode='mosaic')
        edited=render_frame(self.img,fx)
        self.assertEqual(edited.getpixel((0,0)),self.img.getpixel((0,0)))
        self.assertEqual(edited.getpixel((50,30)),edited.getpixel((51,30)))

    def test_zoom_differs_from_source(self):
        fx=merged_effects(None)
        fx['zoom'].update(enabled=True,scale=2.,cx=.5,cy=.5)
        edited=render_frame(self.img,fx)
        self.assertEqual(edited.size,self.img.size)
        self.assertNotEqual(edited.getpixel((0,0)),self.img.getpixel((0,0)))

    def test_color_grayscale(self):
        fx=merged_effects(None)
        fx['color'].update(enabled=True,grayscale=True)
        edited=render_frame(self.img,fx)
        self.assertEqual(len(set(edited.getpixel((80,50)))),1)

    def test_mirror(self):
        fx=merged_effects(None)
        fx['color'].update(enabled=True,mirror=True)
        edited=render_frame(self.img,fx)
        self.assertEqual(edited.getpixel((0,0)),self.img.getpixel((239,0)))

if __name__=='__main__':unittest.main()
