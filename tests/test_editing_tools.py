"""Regresión de la cuchilla, cortes sincronizados y recorte interactivo."""
import copy
import unittest
from timeline.model import make_clip, end, source_position
from timeline.editing import linked_group, split_at, trim_bounds, trim_linked, remove_linked, unlink
from timeline.history import History


class EditingToolsTests(unittest.TestCase):
    def setUp(self):
        self.video=make_clip('video.mp4',10000,2000,track=0,kind='video',link='pair1')
        self.audio=make_clip('video.mp4',10000,2000,track=0,kind='audio',link='pair1')
        self.clips=[self.video,self.audio]
        self.durations={'video.mp4':10000}

    def test_razor_exact_clicked_time(self):
        right_id=split_at(self.clips,self.video['id'],7311)
        self.assertIsNotNone(right_id)
        self.assertEqual(len(self.clips),4)
        self.assertEqual(sorted(c['duration_ms'] for c in self.clips),[4689,4689,5311,5311])
        right=next(c for c in self.clips if c['id']==right_id)
        self.assertEqual(right['start_ms'],7311)
        self.assertEqual(right['in_ms'],5311)
        self.assertEqual(source_position(right,8000),6000)

    def test_right_and_left_segments_stay_pairwise_linked(self):
        split_at(self.clips,self.audio['id'],7000)
        left=[c for c in self.clips if c['start_ms']==2000]
        right=[c for c in self.clips if c['start_ms']==7000]
        self.assertEqual({c['link'] for c in left},{'pair1'})
        self.assertEqual(len({c['link'] for c in right}),1)
        self.assertNotEqual(right[0]['link'],'pair1')
        self.assertEqual({c['kind'] for c in right},{'video','audio'})

    def test_no_cuts_on_edges_or_empty_space(self):
        old=copy.deepcopy(self.clips)
        for time in (100,1999,2000,12000,12001):
            self.assertIsNone(split_at(self.clips,self.video['id'],time))
            self.assertEqual(self.clips,old)

    def test_trim_in_preserves_end_and_source_mapping(self):
        previous_end=end(self.video)
        self.assertTrue(trim_linked(self.clips,self.audio['id'],'inicio',1300,self.durations))
        self.assertEqual(end(self.video),previous_end)
        self.assertEqual(self.video['start_ms'],3300)
        self.assertEqual(self.audio['in_ms'],1300)
        self.assertEqual(self.video['duration_ms'],8700)

    def test_trim_in_cannot_go_before_time_zero(self):
        self.assertEqual(trim_bounds(self.clips,self.video['id'],'inicio',self.durations)[0],0)
        self.assertFalse(trim_linked(self.clips,self.video['id'],'inicio',-10,self.durations))
        self.assertEqual(len(self.clips),2)

    def test_trim_out_cannot_exceed_media_length(self):
        self.assertEqual(trim_bounds(self.clips,self.video['id'],'final',self.durations),(-9999,0))
        self.assertFalse(trim_linked(self.clips,self.video['id'],'final',100,self.durations))
        self.assertTrue(trim_linked(self.clips,self.video['id'],'final',-2400,self.durations))
        self.assertEqual(self.video['duration_ms'],7600)
        self.assertEqual(self.audio['duration_ms'],7600)
        self.assertTrue(trim_linked(self.clips,self.video['id'],'final',1100,self.durations))
        self.assertEqual(self.video['duration_ms'],8700)

    def test_trim_cannot_reduce_duration_to_zero(self):
        self.assertFalse(trim_linked(self.clips,self.video['id'],'inicio',10000,self.durations))
        self.assertFalse(trim_linked(self.clips,self.video['id'],'final',-10000,self.durations))

    def test_delete_linked_pair(self):
        self.assertEqual(remove_linked(self.clips,{self.audio['id']}),2)
        self.assertEqual(self.clips,[])

    def test_unlink_allows_independent_delete_and_trim(self):
        self.assertEqual(unlink(self.clips,{self.video['id']}),2)
        self.assertTrue(all(not c['link'] for c in self.clips))
        self.assertEqual(len(linked_group(self.clips,self.video['id'])),1)
        self.assertEqual(remove_linked(self.clips,{self.video['id']}),1)
        self.assertEqual(self.clips[0]['kind'],'audio')

    def test_undo_restores_before_razor(self):
        h=History()
        h.record(self.clips)
        split_at(self.clips,self.video['id'],5000)
        before=h.undo(self.clips)
        self.assertEqual(len(before),2)
        self.assertEqual([c['duration_ms'] for c in before],[10000,10000])
        after=h.redo(before)
        self.assertEqual(len(after),4)

    def test_split_after_trim(self):
        trim_linked(self.clips,self.video['id'],'inicio',1500,self.durations)
        split_at(self.clips,self.video['id'],6000)
        segments=sorted((c for c in self.clips if c['kind']=='video'),key=lambda c:c['start_ms'])
        self.assertEqual([c['duration_ms'] for c in segments],[2500,6000])
        self.assertEqual(segments[1]['in_ms'],4000)


if __name__=='__main__':unittest.main()
