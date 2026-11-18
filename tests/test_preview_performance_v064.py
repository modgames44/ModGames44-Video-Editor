"""Regresiones de fluidez, sin interfaz Qt (caché, frames y reloj)."""
import unittest
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from services.preview_performance import (AdaptivePreview, is_discontinuous,
                                          timeline_frame_cache_key)
import services.video_frames as frames
from tests.test_sequence_continuity_v063 import SequenceContinuityTests
from tests.test_preview_integration import FakePlayback


class PolicyTests(unittest.TestCase):
    def test_quality_is_reduced_when_processing_cannot_keep_up(self):
        budget=AdaptivePreview()
        self.assertEqual(budget.size(1920,1080),(960,540))
        budget.observe(90);budget.observe(90)
        self.assertEqual(budget.size(1920,1080),(720,405))
        budget.observe(90);budget.observe(90)
        self.assertEqual(budget.size(1920,1080),(480,270))
        for _ in range(24):budget.observe(15)
        self.assertEqual(budget.level,1)
        for _ in range(24):budget.observe(15)
        self.assertEqual(budget.level,0)

    def test_quality_never_renders_larger_than_viewport(self):
        budget=AdaptivePreview()
        self.assertEqual(budget.size(570,355),(560,315))
        self.assertEqual(budget.size(1000,300),(528,297))
        self.assertEqual(budget.size(5000,5000),(960,540))

    def test_video_seek_invalidates_old_image(self):
        self.assertFalse(is_discontinuous(1000,1040))
        self.assertTrue(is_discontinuous(1000,3000))
        self.assertFalse(is_discontinuous(None,3000))
        self.assertNotEqual(timeline_frame_cache_key('a.mp4',2,480),
                            timeline_frame_cache_key('b.mp4',2,480))


class FakeCapture:
    def __init__(self,path):
        self.path=path;self.position=0;self.sets=[];self.grabs=0;self.reads=0
        self.open=True
    def isOpened(self):return self.open
    def get(self,kind):return 60.0
    def set(self,kind,value):
        self.sets.append(round(value));self.position=round(value)
    def grab(self):
        self.grabs+=1;self.position+=1;return True
    def read(self):
        self.reads+=1
        image=np.full((36,64,3),self.position % 256,dtype=np.uint8)
        self.position+=1
        return True,image
    def release(self):self.open=False


class FakeCV2:
    CAP_PROP_FPS=5
    CAP_PROP_POS_FRAMES=1
    COLOR_BGR2RGB=4
    def __init__(self):self.instances=[]
    def VideoCapture(self,path):
        c=FakeCapture(path);self.instances.append(c);return c
    @staticmethod
    def cvtColor(data,code):return data[:,:,::-1]


class FrameReaderTests(unittest.TestCase):
    def setUp(self):
        self.fake=FakeCV2()
        self.patcher=patch.object(frames,'cv2',self.fake)
        self.patcher.start()
        self.reader=frames.FrameReader()
    def tearDown(self):
        self.reader.close()
        self.patcher.stop()

    def test_repeated_requested_frame_uses_cached_copy(self):
        image=self.reader.read('sample.mp4',0,480)
        second=self.reader.read('sample.mp4',0,480)
        self.assertEqual(self.fake.instances[0].reads,1)
        second.putpixel((0,0),(255,0,0))
        self.assertNotEqual(second.getpixel((0,0)),image.getpixel((0,0)))

    def test_60fps_sequential_decoding_skips_not_seeks(self):
        self.reader.read('sample.mp4',0,480)
        self.reader.read('sample.mp4',round(2*1000/60),480)
        capture=self.fake.instances[0]
        self.assertEqual(capture.sets,[0])
        self.assertEqual(capture.grabs,1)
        self.assertEqual(capture.reads,2)
        # Regreso deliberado al inicio ya cacheado tampoco hace seek.
        self.reader.read('sample.mp4',0,480)
        self.assertEqual(capture.sets,[0])

    def test_cache_lru_and_open_decoder_limit(self):
        self.reader._cache_limit=3
        self.reader._capture_limit=2
        for path in ['one.mp4','two.mp4','three.mp4']:
            self.reader.read(path,0,480)
        self.assertLessEqual(len(self.reader._recent),3)
        self.assertLessEqual(len(self.reader._captures),2)
        self.assertFalse(self.fake.instances[0].open)

    def test_close_frees_cache_and_captures(self):
        self.reader.read('sample.mp4',0)
        self.reader.close()
        self.assertFalse(self.reader._captures)
        self.assertFalse(self.reader._recent)
        self.assertFalse(self.fake.instances[0].open)


class RealPlaybackDecodeTests(unittest.TestCase):
    def test_actual_60fps_media_and_reverse_seek(self):
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg or frames.cv2 is None:
            self.skipTest('FFmpeg / OpenCV no disponibles')
        with tempfile.TemporaryDirectory() as tmp:
            video=str(Path(tmp)/'motion.mp4')
            command=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi',
                     '-i','testsrc2=size=160x90:rate=60:duration=1.5',
                     '-c:v','mpeg4',video]
            subprocess.run(command,check=True,capture_output=True,timeout=20)
            reader=frames.FrameReader()
            try:
                first=reader.read(video,0,160,max_height=90)
                middle=reader.read(video,700,160,max_height=90)
                earlier=reader.read(video,100,160,max_height=90)
                self.assertEqual(first.size,(160,90))
                self.assertEqual(middle.size,(160,90))
                self.assertEqual(earlier.size,(160,90))
                self.assertNotEqual(first.tobytes(),middle.tobytes())
            finally:
                reader.close()

    def test_real_multilayer_composition_with_shared_frame_reader(self):
        import tempfile
        from PIL import Image
        from timeline.model import make_clip
        from effects.compositor import composite_frame
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'blue.png'
            Image.new('RGB',(64,36),'blue').save(path)
            base=make_clip(str(path),1500,kind='video',track=0)
            top=make_clip(str(path),1500,kind='video',track=1)
            top['fade_in_ms']=500
            reader=frames.FrameReader()
            try:
                result=composite_frame([base,top],250,(480,270),reader)
                self.assertEqual(result.getpixel((240,135)),(0,0,255))
                self.assertLessEqual(len(reader._recent),14)
            finally:
                reader.close()


class PlaybackFlowTests(unittest.TestCase):
    def test_play_after_pause_avoids_redundant_seek(self):
        class Holder(SequenceContinuityTests):pass
        player=Holder.SequencePlayer if hasattr(Holder,'SequencePlayer') else None
        if player is None:
            Holder.setUpClass()
        seq,engine,_,_=Holder().player_with_clips()
        previous=len(engine.seeks)
        seq.pause();seq.play()
        self.assertEqual(len(engine.seeks),previous)
        seq.seek(20)
        self.assertEqual(engine.seeks[-1],20)

    def test_two_fast_position_events_do_not_repaint_twice(self):
        ui=FakePlayback()
        ui.sequence.running=True
        ui._sequence_position(4000)
        count=len(ui.timeline.calls)
        ui._sequence_position(4004)
        self.assertEqual(len(ui.timeline.calls),count)
        ui._sequence_position(8000)
        self.assertGreater(len(ui.timeline.calls),count)


if __name__=='__main__':unittest.main()
