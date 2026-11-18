import unittest
from timeline.model import make_clip,split,active,source_position,close_gap
from timeline.history import History
class TimelineTests(unittest.TestCase):
 def test_split_and_source(self):
  clips=[make_clip('a.mp4',10000,2000)]
  self.assertTrue(split(clips,clips[0]['id'],6000))
  self.assertEqual([c['duration_ms'] for c in clips],[4000,6000])
  self.assertEqual(source_position(clips[1],7000),5000)
 def test_active(self):
  clips=[make_clip('a',1000,1000),make_clip('b',1000,2000)]
  self.assertIsNone(active(clips,500));self.assertEqual(active(clips,2100)['path'],'b')
 def test_gaps(self):
  clips=[make_clip('a',1000,1000),make_clip('b',2000,5000)]
  close_gap(clips,0,'video');self.assertEqual([c['start_ms'] for c in clips],[0,1000])
 def test_history(self):
  h=History();clips=[make_clip('a',1000)];h.record(clips);clips.clear()
  self.assertEqual(len(h.undo(clips)),1)
if __name__=='__main__':unittest.main()
