"""Seguimiento de rectángulo con patrón contrastado en video sintético."""
import tempfile
from pathlib import Path
import unittest
import numpy as np
try:import cv2
except ImportError:cv2=None
from timeline.model import make_clip
from effects.model import default_effects
from services.object_tracking import track_censor,_compress


@unittest.skipIf(cv2 is None,'Se requiere OpenCV')
class TrackerTests(unittest.TestCase):
    def test_tracking_moving_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'pattern.avi')
            writer=cv2.VideoWriter(path,cv2.VideoWriter_fourcc(*'MJPG'),20,(160,100))
            self.assertTrue(writer.isOpened())
            rng=np.random.default_rng(7)
            texture=rng.integers(30,240,size=(25,30,3),dtype=np.uint8)
            for frame_no in range(40):
                frame=np.zeros((100,160,3),dtype=np.uint8)+20
                x=20+frame_no
                frame[30:55,x:x+30]=texture
                writer.write(frame)
            writer.release()
            clip=make_clip(path,2000)
            effects=default_effects()
            effects['censor'].update(enabled=True,mask={'x':20/160,'y':.3,'w':30/160,'h':.25})
            clip['effects']=effects
            result=track_censor(clip,0,max_seconds=1.8)
            self.assertGreaterEqual(len(result),2)
            self.assertLessEqual(result[-1]['x']-result[0]['x'],.30)
            self.assertGreater(result[-1]['x']-result[0]['x'],.08)
            self.assertGreater(result[-1]['time_ms'],700)
    def test_simplification(self):
        points=[dict(time_ms=i*50,x=.1+i*.001,y=.2,w=.3,h=.2) for i in range(200)]
        result=_compress(points)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0],points[0])
        self.assertEqual(result[-1],points[-1])

if __name__=='__main__':unittest.main()
