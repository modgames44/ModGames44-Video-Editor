import unittest
from services.media_probe import probe
from timeline.model import make_clip

class MediaProbeTests(unittest.TestCase):
    def test_missing(self):
        self.assertFalse(probe('/file/does/not/exist.mp4')['has_audio'])
    def test_link_model(self):
        video=make_clip('a.mp4',2000,kind='video',link='same')
        audio=make_clip('a.mp4',2000,kind='audio',link='same')
        self.assertEqual(video['link'],audio['link'])

if __name__=='__main__':unittest.main()
