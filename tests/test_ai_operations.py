"""Pruebas de integración lógica de edición IA; no necesitan red ni Qt."""
import copy
import unittest
from timeline.model import make_clip, end
from ai.operations import simulate, prepare_plan, PlanError
from ai.local_commands import parse_local, parse_time
from ai.silence import silence_plan, read_silences
from ai.openai_planner import make_context


class TestAI(unittest.TestCase):
    def setUp(self):
        self.video = make_clip('D:/media/prueba.mp4', 30000, start_ms=0, kind='video',link='linked')
        self.audio = make_clip('D:/media/prueba.mp4', 30000, start_ms=0,kind='audio',link='linked')
        self.clips = [self.video, self.audio]

    def test_cut_both_tracks_non_destructive(self):
        before=copy.deepcopy(self.clips)
        out, seek, text=simulate(self.clips,[{'type':'cut','time_ms':10000}])
        self.assertEqual(len(out),4)
        self.assertEqual(sorted((c['start_ms'], c['duration_ms']) for c in out if c['kind']=='audio'), [(0,10000),(10000,20000)])
        self.assertEqual(sorted((c['start_ms'], c['duration_ms']) for c in out if c['kind']=='video'), [(0,10000),(10000,20000)])
        self.assertEqual(self.clips,before)
        self.assertEqual(out[0]['link'],out[2]['link'])

    def test_remove_middle_keeps_audio_and_links(self):
        out, _, _ = simulate(self.clips,[{'type':'remove_range','start_ms':5000,'end_ms':10000}])
        self.assertEqual(len(out),4)
        self.assertEqual(sorted((c['start_ms'],c['duration_ms']) for c in out if c['kind']=='video'), [(0,5000),(10000,20000)])
        self.assertEqual(sorted((c['start_ms'],c['duration_ms']) for c in out if c['kind']=='audio'), [(0,5000),(10000,20000)])

    def test_multiple_removals_descending(self):
        out, _, _ = simulate(self.clips,[{'type':'remove_range','clip_id':self.video['id'],'start_ms':20000,'end_ms':22000},
            {'type':'remove_range','clip_id':self.video['id'],'start_ms':5000,'end_ms':7000}])
        self.assertEqual(len(out),6)
        v=sorted((c['start_ms'], end(c)) for c in out if c['kind']=='video')
        self.assertEqual(v,[(0,5000),(7000,20000),(22000,30000)])

    def test_move_linked(self):
        out, _, _ = simulate(self.clips,[{'type':'move','clip_id':self.audio['id'],'start_ms':10000}])
        self.assertEqual([c['start_ms'] for c in out],[10000,10000])

    def test_invalid_action_is_atomic(self):
        copy_before=copy.deepcopy(self.clips)
        with self.assertRaises(PlanError):
            simulate(self.clips,[{'type':'cut','time_ms':5000},{'type':'shell','cmd':'rm'}])
        self.assertEqual(self.clips, copy_before)

    def test_reject_nan_and_negative(self):
        for t in (-1, float('nan'), True, '5000'):
            with self.assertRaises(PlanError):
                simulate(self.clips,[{'type':'cut','time_ms':t}])

    def test_reject_outside(self):
        with self.assertRaises(PlanError):
            simulate(self.clips,[{'type':'remove_range','start_ms':500,'end_ms':31000}])

    def test_seek_no_modification(self):
        out,t,_=simulate(self.clips,[{'type':'seek','time_ms':9000}])
        self.assertEqual(out,self.clips)
        self.assertEqual(t,9000)

    def test_local_commands(self):
        self.assertEqual(parse_local('Corta en 00:05')['operations'][0]['time_ms'],5000)
        self.assertEqual(parse_local('elimina desde 00:05 hasta 00:10')['operations'][0]['end_ms'],10000)
        self.assertEqual(parse_local('mueve el clip a 00:20',self.video['id'])['operations'][0]['start_ms'],20000)
        self.assertEqual(parse_time('00:05:10.5'),310500)
        self.assertEqual(parse_local('cierra huecos')['operations'][0]['type'],'close_gaps')

    def test_no_fake_semantic_ai(self):
        with self.assertRaises(PlanError):
            parse_local('elige las partes interesantes del video para YouTube')

    def test_silence_detection(self):
        log='[silencedetect @ 0] silence_start: 2.50\n[silencedetect @ 0] silence_end: 4.50 | silence_duration: 2.00\n'
        detected=read_silences(log,30000)
        self.assertEqual(detected,[(2500,4500)])
        plan=silence_plan(self.video,detected)
        self.assertEqual(plan['operations'][0]['start_ms'],2620)
        out,_,_=simulate(self.clips,plan['operations'])
        self.assertEqual(len(out),4)

    def test_no_remove_entire_silent_video(self):
        plan=silence_plan(self.video,[(0,30000)])
        self.assertEqual(plan['operations'],[])

    def test_proposal_validation(self):
        plan=prepare_plan({'explanation':'OK','operations':[{'type':'cut','time_ms':10000}]},self.clips)
        self.assertEqual(len(plan['preview_clips']),4)
        with self.assertRaises(PlanError):
            prepare_plan({'operations':[{'type':'delete_disk'}]},self.clips)

    def test_context_privacy(self):
        ctx=make_context(self.clips,self.video['id'],0)
        self.assertEqual(ctx['clips'][0]['file'],'prueba.mp4')
        self.assertNotIn('D:/media',str(ctx))

if __name__=='__main__':unittest.main()
