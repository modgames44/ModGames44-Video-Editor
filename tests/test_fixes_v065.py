"""Regresiones de las correcciones de v0.6.5 (revisión de código)."""
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from core.project_manager import save_project, load_project, missing_media, relink_media
from effects.keyframe_expressions import sample
from effects.title_overlay import title_clip
from exporter.render import ExportProfile, build_export_command
from exporter.encoder_settings import video_codec_args
from services.continuous_audio import pcm_stereo_peaks
from services.media_probe import parse_probe_output
from timeline.editing import trim_linked
from timeline.history import History
from timeline.model import make_clip, split, close_all_gaps
from timeline.ripple import ripple_remove
from timeline.transitions import crossfade_adjacent

FFMPEG = shutil.which('ffmpeg')
if FFMPEG is None:
    try:
        import imageio_ffmpeg
        FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        FFMPEG = None


class LocalKeyframeTests(unittest.TestCase):
    def test_split_keeps_volume_curve(self):
        a = make_clip('x.wav', 10000, kind='audio')
        a['volume_keys'] = [{'time_ms': 0, 'volume': 1.0}, {'time_ms': 8000, 'volume': 0.0}]
        expected = sample(a['volume_keys'], 6000, 'volume', 1)
        clips = [a]
        split(clips, a['id'], 5000)
        left, right = clips
        self.assertAlmostEqual(sample(right['volume_keys'], 1000, 'volume', 1), expected)
        self.assertAlmostEqual(sample(left['volume_keys'], 2000, 'volume', 1),
                               sample(a['volume_keys'], 2000, 'volume', 1))

    def test_split_does_not_share_nested_dicts(self):
        v = make_clip('v.mp4', 10000)
        v['effects'] = {'zoom': {'enabled': True, 'scale': 2, 'keys': []}}
        clips = [v]
        split(clips, v['id'], 5000)
        self.assertIsNot(clips[0]['effects'], clips[1]['effects'])
        clips[0]['effects']['zoom']['scale'] = 3
        self.assertEqual(clips[1]['effects']['zoom']['scale'], 2)

    def test_trim_start_shifts_local_keys(self):
        b = make_clip('y.wav', 10000, kind='audio', in_ms=2000)
        b['volume_keys'] = [{'time_ms': 0, 'volume': 1.0}, {'time_ms': 5000, 'volume': 0.2}]
        before = sample(b['volume_keys'], 6000, 'volume', 1)
        self.assertTrue(trim_linked([b], b['id'], 'inicio', 2000, {'y.wav': 20000}))
        self.assertAlmostEqual(sample(b['volume_keys'], 4000, 'volume', 1), before)

    def test_trim_start_shifts_title_animation(self):
        t = title_clip('hola', 1000, 4000)
        t['transform_keys'] = [{'time_ms': 0, 'x': 0.2}, {'time_ms': 4000, 'x': 0.8}]
        trim_linked([t], t['id'], 'inicio', 1000, {'': 10 ** 7})
        self.assertAlmostEqual(sample(t['transform_keys'], 0, 'x', .5), 0.35)


class GapTests(unittest.TestCase):
    def test_close_gaps_keeps_transition_overlap(self):
        a = make_clip('a.mp4', 4000)
        b = make_clip('b.mp4', 4000, start_ms=4000)
        c = make_clip('c.mp4', 3000, start_ms=12000)
        clips = [a, b, c]
        crossfade_adjacent(clips, a['id'], 1000)
        close_all_gaps(clips)
        self.assertEqual(b['start_ms'], 3000)  # solape de 1 s intacto
        self.assertEqual(c['start_ms'], 7000)  # hueco cerrado

    def test_close_gaps_moves_subtitles_with_content(self):
        a = make_clip('a.mp4', 2000)
        b = make_clip('b.mp4', 2000, start_ms=5000)
        sub = title_clip('dentro de b', 5500, 1000, subtitle=True)
        clips = [a, b, sub]
        close_all_gaps(clips)
        self.assertEqual(b['start_ms'], 2000)
        self.assertEqual(sub['start_ms'] - b['start_ms'], 500)

    def test_ripple_moves_overlays_and_titles_do_not_ripple_each_other(self):
        x = make_clip('x.mp4', 2000)
        y = make_clip('y.mp4', 2000, start_ms=2000)
        t = title_clip('sobre y', 2500, 500)
        clips = [x, y, t]
        ripple_remove(clips, {x['id']})
        self.assertEqual((y['start_ms'], t['start_ms']), (0, 500))
        t1, t2 = title_clip('a', 0, 500), title_clip('b', 3000, 500)
        clips = [t1, t2]
        ripple_remove(clips, {t1['id']})
        self.assertEqual(t2['start_ms'], 3000)


class ProbeParsingTests(unittest.TestCase):
    def test_mp3_cover_art_is_not_video(self):
        info = ('  Duration: 00:00:03.03, start: 0.025057, bitrate: 72 kb/s\n'
                '  Stream #0:0: Audio: mp3, 44100 Hz, mono, fltp, 64 kb/s\n'
                '  Stream #0:1: Video: mjpeg (Baseline), yuvj444p(pc), 300x300 '
                '[SAR 1:1 DAR 1:1], 90k tbr, 90k tbn (attached pic)\n')
        meta = parse_probe_output(info)
        self.assertTrue(meta['has_audio'])
        self.assertFalse(meta['has_video'])

    def test_rotated_phone_video_reports_visible_size(self):
        info = ('  Duration: 00:00:02.00\n'
                '  Stream #0:0[0x1](und): Video: h264, yuv420p, 1920x1080, 30 fps, 30 tbr\n'
                '    Side data:\n'
                '      displaymatrix: rotation of -90.00 degrees\n')
        meta = parse_probe_output(info)
        self.assertEqual((meta['width'], meta['height'], meta['fps']), (1080, 1920, 30.0))


class HistoryTests(unittest.TestCase):
    def test_failed_operation_keeps_redo(self):
        h = History()
        h.record([{'id': 1}])
        previous = h.undo([{'id': 2}])
        self.assertEqual(previous, [{'id': 1}])
        h.record(previous)
        h.cancel_last()
        self.assertEqual(h.redo(previous), [{'id': 2}])


class ProjectPathTests(unittest.TestCase):
    def test_moved_project_folder_resolves_relative_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'original'
            (original / 'media').mkdir(parents=True)
            video = original / 'media' / 'clip.mp4'
            video.write_bytes(b'x')
            project = {'version': 1, 'media': [str(video)],
                       'clips': [dict(make_clip(video, 1000))], 'fps': 30}
            save_project(original / 'p.mg44', project, relative_paths=True)
            moved = root / 'moved'
            shutil.move(str(original), str(moved))
            data = load_project(moved / 'p.mg44', resolve_relative=True)
            self.assertEqual(Path(data['clips'][0]['path']), (moved / 'media' / 'clip.mp4').resolve())
            self.assertEqual(missing_media(data), [])
            self.assertNotIn('path_rel', data['clips'][0])

    def test_relink_by_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            found = Path(tmp) / 'sub' / 'video.mp4'
            found.parent.mkdir()
            found.write_bytes(b'x')
            project = {'media': ['/no/existe/video.mp4'],
                       'clips': [{'path': '/no/existe/video.mp4', 'kind': 'video'}]}
            self.assertEqual(relink_media(project, tmp), 1)
            self.assertEqual(project['clips'][0]['path'], str(found))


class SmallFixTests(unittest.TestCase):
    def test_numpy_peaks_match_reference(self):
        import array
        import random
        rng = random.Random(4)
        samples = array.array('h', [rng.randint(-32768, 32767) for _ in range(4096)])
        chunk = samples.tobytes()
        left = max(abs(n) for n in samples[0::2]) / 32768.
        right = max(abs(n) for n in samples[1::2]) / 32768.
        self.assertEqual(pcm_stereo_peaks(chunk), (min(1., left), min(1., right)))

    def test_software_encoders_use_crf(self):
        profile = ExportProfile('t', 'h264', 'mp4', 1920, 1080, 30, '12M')
        args = video_codec_args('libx264', profile)
        self.assertEqual(args[args.index('-crf') + 1], '20')
        self.assertIn('-maxrate', args)
        self.assertIn('-b:v', video_codec_args('h264_amf', profile))


@unittest.skipIf(FFMPEG is None, 'FFmpeg no disponible')
class ExportMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.long = cls.root / 'long.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=40',
                        '-f', 'lavfi', '-i', 'sine=d=40', '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-c:a', 'aac', '-shortest', str(cls.long)], check=True, capture_output=True)
        cls.pattern = cls.root / 'vertical.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=s=180x320:r=30:d=1',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(cls.pattern)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_inputs_are_seeked_and_segments_are_correct(self):
        clips = []
        for i in range(4):
            v = make_clip(self.long, 1000, i * 1000, 0, i * 9000, 'video', f'l{i}')
            a = make_clip(self.long, 1000, i * 1000, 0, i * 9000, 'audio', f'l{i}')
            clips += [v, a]
        profile = ExportProfile('t', 'h264', 'mp4', 320, 180, 30, '1M')
        dest = self.root / 'segments.mp4'
        argv, _ = build_export_command(clips, profile, dest, {'ffmpeg': FFMPEG, 'encoder': 'libx264'})
        self.assertEqual(argv.count('-ss'), 8)
        self.assertNotIn('trim=start=9', ';'.join(argv))
        run = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr[-800:])
        # Cada segmento debe mostrar el instante de origen correcto: se compara
        # con el fotograma extraído directamente de la fuente.
        for i in range(4):
            exported = subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{i + .5}', '-i', str(dest),
                                       '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                                      capture_output=True, timeout=30).stdout
            source = subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{i * 9 + .5}', '-i', str(self.long),
                                     '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                                    capture_output=True, timeout=30).stdout
            diff = sum(abs(x - y) for x, y in zip(exported, source, strict=True)) / len(source)
            self.assertLess(diff, 6, f'segmento {i}')

    def _gray_frame(self, path, width, height):
        raw = subprocess.run([FFMPEG, '-v', 'error', '-ss', '0.5', '-i', str(path), '-frames:v', '1',
                              '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                             capture_output=True, timeout=30).stdout
        self.assertEqual(len(raw), width * height)
        return raw

    def test_vertical_video_censor_matches_monitor_area(self):
        """La máscara es relativa a la FUENTE (como el monitor), no al lienzo 16:9."""
        profile = ExportProfile('t', 'h264', 'mp4', 640, 360, 30, '1M')
        outputs = {}
        for name, enabled in (('plain', False), ('censored', True)):
            clip = make_clip(self.pattern, 1000)
            clip['effects'] = {'censor': {'enabled': enabled, 'mode': 'blur', 'strength': 80,
                                          'feather': 0, 'mask': {'x': .25, 'y': .25, 'w': .5, 'h': .5}}}
            dest = self.root / f'vertical_{name}.mp4'
            argv, _ = build_export_command([clip], profile, dest, {'ffmpeg': FFMPEG, 'encoder': 'libx264'})
            run = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr[-800:])
            outputs[name] = self._gray_frame(dest, 640, 360)
        columns = [x for x in range(640) for y in range(0, 360, 4)
                   if abs(outputs['plain'][y * 640 + x] - outputs['censored'][y * 640 + x]) > 24]
        self.assertTrue(columns)
        # Fuente 180x320 encajada en 202x360, centrada en x=219..421.
        # Máscara 25%..75% de la FUENTE => x≈269..370 (antes: 160..480).
        self.assertGreaterEqual(min(columns), 262)
        self.assertLessEqual(max(columns), 378)


@unittest.skipIf(FFMPEG is None, 'FFmpeg no disponible')
class ProxyCancelTests(unittest.TestCase):
    def test_cancel_stops_ffmpeg(self):
        from services.proxy_manager import generate_proxy, ProxyCancelled
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'src.mp4'
            subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1280x720:r=30:d=120',
                            '-c:v', 'libx264', '-preset', 'ultrafast', str(source)],
                           check=True, capture_output=True)
            cancel = threading.Event()
            threading.Timer(.4, cancel.set).start()
            with self.assertRaises(ProxyCancelled):
                generate_proxy(source, FFMPEG, root=Path(tmp) / 'proxies', cancel=cancel)
            self.assertEqual(list((Path(tmp) / 'proxies').glob('*.mp4')), [])


if __name__ == '__main__':
    unittest.main()
