import unittest
from timeline.track_layout import TRACK_LABELS, row_for_clip, track_for_row
from timeline.model import make_clip

class TrackLayoutTests(unittest.TestCase):
    def test_premiere_order(self):
        self.assertEqual(TRACK_LABELS,('V3','V2','V1','A1','A2','A3'))
        for kind,labels in (('video',['V1','V2','V3']),('audio',['A1','A2','A3'])):
            for track,label in enumerate(labels):
                self.assertEqual(TRACK_LABELS[row_for_clip({'kind':kind,'track':track})],label)

    def test_position_audio_track_independently(self):
        video=make_clip('x.mp4',2000,kind='video',link='g')
        audio=make_clip('x.mp4',2000,kind='audio',link='g')
        audio['track']=track_for_row('audio',5,audio['track'])
        self.assertEqual(TRACK_LABELS[row_for_clip(video)],'V1')
        self.assertEqual(TRACK_LABELS[row_for_clip(audio)],'A3')
        self.assertEqual(video['link'],audio['link'])

    def test_dont_move_audio_into_video_row(self):
        self.assertEqual(track_for_row('audio',1,2),2)
        self.assertEqual(track_for_row('video',4,1),1)

if __name__=='__main__':unittest.main()
