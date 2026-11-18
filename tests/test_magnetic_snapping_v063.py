"""Imán sensible al zoom y protección frente a solapamientos en pistas A/V."""
import copy
import unittest
from timeline.model import make_clip, end
from timeline.snapping import plan_magnetic_move


class MagneticSnappingTests(unittest.TestCase):
    def setUp(self):
        self.a=make_clip('a.mp4',5000,start_ms=0,track=0)
        self.b=make_clip('b.mp4',4000,start_ms=13000,track=0)
        self.clips=[self.a,self.b]

    def move(self, clip, wanted, *, track=None, enabled=True, scale=70,
             playhead=None, collection=None):
        collection=collection if collection is not None else self.clips
        delta, new_track=plan_magnetic_move(collection,clip['id'],wanted,
                 clip['track'] if track is None else track,
                 enabled=enabled,pixels_per_second=scale,playhead_ms=playhead)
        return clip['start_ms']+delta,new_track

    def test_front_of_clip_magnet_to_end_of_previous(self):
        self.assertEqual(self.move(self.b,5100)[0],5000)

    def test_end_of_clip_magnet_to_start_of_next(self):
        self.b['start_ms']=11000
        # A dura 5000; al moverla a 6100 terminaría en 11100.
        self.assertEqual(self.move(self.a,6110)[0],6000)

    def test_no_overlaps_even_if_magnet_distance_exceeded(self):
        self.assertEqual(self.move(self.b,4400)[0],5000)
        # Al querer poner A sobre B desde la izquierda, se detiene en su borde.
        self.assertEqual(self.move(self.a,10000)[0],8000)

    def test_disabled_magnet_permits_overlap(self):
        self.assertEqual(self.move(self.b,4400,enabled=False)[0],4400)

    def test_zoom_is_pixel_based(self):
        self.assertEqual(self.move(self.b,5160,scale=70)[0],5000)
        self.assertEqual(self.move(self.b,5160,scale=700)[0],5160)
        self.assertEqual(self.move(self.b,5010,scale=700)[0],5000)

    def test_different_track_does_not_block_move(self):
        self.assertEqual(self.move(self.b,2000,track=1)[0],2000)

    def test_can_snap_to_edge_of_another_track(self):
        other=make_clip('background.mp4',2000,start_ms=8000,track=2)
        self.clips.append(other)
        self.assertEqual(self.move(self.b,8120,track=1)[0],8000)

    def test_snap_to_playhead(self):
        self.assertEqual(self.move(self.b,8060,track=1,playhead=8000)[0],8000)

    def test_no_negative_start(self):
        self.assertEqual(self.move(self.b,-2000)[0],5000) # vecino A ocupa origen
        self.assertEqual(self.move(self.a,-2000)[0],0)

    def test_keeps_linked_pair_synchronized(self):
        self.a['link']='p'
        audio=make_clip('a.mp4',5000,start_ms=0,kind='audio',link='p')
        self.clips.append(audio)
        start,_=self.move(self.a,7200)
        self.assertEqual(start,7200)
        delta=start-self.a['start_ms']
        self.assertEqual(audio['start_ms']+delta,7200)

    def test_does_not_snap_to_linked_audio_itself(self):
        self.a['link']='p'
        audio=make_clip('a.mp4',5000,start_ms=0,kind='audio',link='p')
        self.clips.append(audio)
        self.assertEqual(self.move(self.a,1800)[0],1800)

    def test_linked_audio_prevents_overlap_on_audio_track(self):
        self.b['link']='b'
        ba=make_clip('b.mp4',4000,start_ms=13000,kind='audio',track=0,link='b')
        music=make_clip('music.wav',5000,start_ms=6000,kind='audio',track=0)
        self.clips.extend((ba,music))
        # Vídeo A no bloquea a B en V2, pero el audio en A1 sí.
        self.assertEqual(self.move(self.b,7500,track=1)[0],11000)

    def test_titles_can_overlap_video(self):
        title=make_clip('texto',2000,start_ms=13000,track=0,kind='title')
        self.clips.append(title)
        self.assertEqual(self.move(title,3000)[0],3000)

    def test_undo_history_can_restore_original(self):
        before=copy.deepcopy(self.clips)
        self.move(self.b,5005)
        self.assertEqual(self.clips,before)

    def test_exact_touch_no_collision(self):
        self.assertEqual(self.move(self.b,5000)[0],5000)
        self.assertEqual(end(self.a),5000)

    def test_very_many_nonoverlapping_clips(self):
        clips=[make_clip(f'{i}.mp4',1000,start_ms=i*1500) for i in range(200)]
        target=clips[-1]
        start,_=self.move(target,1900,collection=clips)
        # Escoge un espacio válido sin pisar ningún clip intermedio.
        self.assertTrue(all(start>=end(c) or start+1000<=c['start_ms']
                            for c in clips[:-1]))


if __name__=='__main__':unittest.main()
