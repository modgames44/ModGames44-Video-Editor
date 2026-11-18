"""Regresiones sobre los límites de reproducción de clips cortados."""
import unittest
from timeline.playback_boundaries import playback_end, limited_position
from timeline.model import make_clip, split, close_gap


class TestPlaybackBoundaries(unittest.TestCase):
    def setUp(self):
        self.clips=[make_clip('video.mp4',10000,kind='video')]
        self.left_id=self.clips[0]['id']
        self.right_id=split(self.clips,self.left_id,4000)

    def test_cut_creates_two_contiguous_segments(self):
        self.assertEqual(self.clips[0]['start_ms'],0)
        self.assertIsNone(playback_end(self.clips,self.left_id))
        self.assertEqual(self.clips[1]['start_ms'],4000)
        self.assertEqual(playback_end(self.clips,self.right_id),10000)

    def test_continue_at_exact_contiguous_cut(self):
        self.assertEqual(limited_position(self.clips,self.left_id,4000),(4000,False))

    def test_advance_into_contiguous_next_clip(self):
        self.assertEqual(limited_position(self.clips,self.left_id,4062),(4062,False))

    def test_keep_playing_before_cut(self):
        self.assertEqual(limited_position(self.clips,self.left_id,3980),(3980,False))

    def test_play_from_cut_plays_next_segment(self):
        self.assertEqual(limited_position(self.clips,self.right_id,4010),(4010,False))
        self.assertEqual(limited_position(self.clips,self.right_id,10050),(10000,True))

    def test_normal_continuous_mode(self):
        self.assertEqual(limited_position(self.clips,self.left_id,4062,False),(4062,False))

    def test_no_current_clip(self):
        self.assertEqual(limited_position(self.clips,None,5000),(5000,False))

    def test_limit_not_before_00(self):
        self.assertEqual(limited_position(self.clips,None,-200),(0,False))

    def test_missing_id(self):
        self.assertEqual(limited_position(self.clips,'removed',8000),(8000,False))

    def test_cut_with_nonzero_source_offset(self):
        self.clips=[make_clip('test.mp4',8000,start_ms=2000,in_ms=3500)]
        self.assertEqual(playback_end(self.clips,self.clips[0]['id']),10000)
        self.assertEqual(limited_position(self.clips,self.clips[0]['id'],10100),(10000,True))

    def test_stop_on_true_gap_after_cut(self):
        # Ejemplo de quitar silencios: la segunda mitad mantiene un hueco.
        self.clips[1]['start_ms']=4500
        self.clips[1]['in_ms']=5000
        self.assertEqual(playback_end(self.clips,self.left_id),4000)
        self.assertEqual(limited_position(self.clips,self.left_id,4080),(4000,True))

    def test_after_close_gaps_play_is_continuous(self):
        self.clips[1]['start_ms']=4800
        self.clips[1]['in_ms']=5500
        close_gap(self.clips,0,'video')
        self.assertEqual(self.clips[1]['start_ms'],4000)
        self.assertEqual(limited_position(self.clips,self.left_id,4070),(4070,False))

    def test_video_overlap_transition_does_not_stop(self):
        self.clips[1]['start_ms']=3700
        self.assertEqual(limited_position(self.clips,self.left_id,4120),(4120,False))

    def test_other_video_track_continuation_does_not_stop(self):
        self.clips[1]['track']=2
        self.assertEqual(limited_position(self.clips,self.left_id,4050),(4050,False))

    def test_no_audio_video_after_last_segment_stops(self):
        self.assertEqual(limited_position(self.clips,self.right_id,10040),(10000,True))

    def test_only_text_after_video_is_not_av_continuation(self):
        self.clips[1]['start_ms']=5000
        self.clips.append(make_clip('title',4000,start_ms=4000,kind='title'))
        self.assertEqual(limited_position(self.clips,self.left_id,4030),(4000,True))

    def test_audio_continuation_is_valid(self):
        self.clips[1]['start_ms']=4800
        self.clips.append(make_clip('music.wav',3000,start_ms=3500,kind='audio'))
        self.assertEqual(limited_position(self.clips,self.left_id,4050),(4050,False))

    def test_pause_mode_disabled_allows_gaps(self):
        self.clips[1]['start_ms']=4800
        self.assertEqual(limited_position(self.clips,self.left_id,4050,False),(4050,False))

    def test_no_link_required(self):
        self.clips.append(make_clip('same.mp4',4000,start_ms=4000,kind='audio'))
        self.assertEqual(limited_position(self.clips,self.left_id,4500),(4500,False))


if __name__=='__main__':
    unittest.main()
