"""Exportación por GPU: detección, ajustes de NVENC, 10 bits y reintentos."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from exporter import hardware
from exporter.encoder_settings import nvenc_args, video_codec_args
from exporter.render import PROFILES, ExportProfile, build_export_command, export_attempts, encoder_label
from timeline.model import make_clip

NV = {'ffmpeg': 'ffmpeg', 'vendor': 'NVIDIA', 'encoder': 'h264_nvenc', 'tuned': 'full', 'ten_bit': False}
CPU = {'ffmpeg': 'ffmpeg', 'vendor': 'CPU', 'encoder': 'libx264'}


_TMP = tempfile.TemporaryDirectory()
MEDIA = Path(_TMP.name) / 'video.mp4'
MEDIA.write_bytes(b'x')


def value(args, flag):
    return args[args.index(flag) + 1]


class SmokeTestTests(unittest.TestCase):
    def test_smoke_test_is_above_nvenc_minimum_size(self):
        width, height = (int(x) for x in hardware.SMOKE_SIZE.split('x'))
        self.assertGreaterEqual(width, 145)   # mínimo H.264 en RTX 20+
        self.assertGreaterEqual(height, 145)
        with patch('subprocess.run') as run:
            run.return_value.returncode = 0
            hardware.encoder_smoke_test('ffmpeg', 'h264_nvenc')
            argv = run.call_args[0][0]
        self.assertIn(f'testsrc2=size={hardware.SMOKE_SIZE}:rate=30', argv)


class DiscoveryTests(unittest.TestCase):
    def test_gpu_is_tested_even_if_windows_does_not_name_it(self):
        with patch.object(hardware, 'detect_gpus', return_value=[]), \
             patch.object(hardware, 'ffmpeg_candidates', return_value=['ffmpeg']), \
             patch.object(hardware, 'available_encoders', return_value={'h264_nvenc', 'libx264'}), \
             patch.object(hardware, 'gpu_capabilities', return_value={'tuned': 'full', 'ten_bit': False}):
            result = hardware.discover('h264')
        self.assertEqual([o['encoder'] for o in result['options']], ['h264_nvenc', 'libx264'])
        self.assertEqual(hardware.select_encoder('h264', 'auto', result)['vendor'], 'NVIDIA')

    def test_named_gpu_goes_first_and_failed_gpu_is_skipped(self):
        def caps(ffmpeg, encoder, codec):
            return None if encoder == 'h264_qsv' else {'tuned': False, 'ten_bit': False}
        with patch.object(hardware, 'detect_gpus', return_value=['NVIDIA GeForce RTX 4080', 'Intel UHD Graphics']), \
             patch.object(hardware, 'ffmpeg_candidates', return_value=['a', 'b']), \
             patch.object(hardware, 'available_encoders', return_value={'h264_nvenc', 'h264_qsv', 'libx264'}), \
             patch.object(hardware, 'gpu_capabilities', side_effect=caps):
            result = hardware.discover('h264')
        # Sin duplicados aunque haya dos FFmpeg; la Intel que falló no aparece.
        self.assertEqual([(o['vendor'], o['ffmpeg']) for o in result['options']], [('NVIDIA', 'a'), ('CPU', 'a')])

    def test_capabilities_pick_best_working_level(self):
        def smoke(ffmpeg, encoder, codec='h264', extra_args=(), pix_fmt='yuv420p'):
            # La GPU rechaza AQ temporal pero acepta el resto y 10 bits.
            return '-temporal-aq' not in extra_args
        with patch.object(hardware, 'encoder_smoke_test', side_effect=smoke):
            caps = hardware.gpu_capabilities('ffmpeg', 'av1_nvenc', 'av1')
        self.assertEqual(caps, {'tuned': 'safe', 'ten_bit': True})


class NvencSettingsTests(unittest.TestCase):
    def test_full_quality_settings(self):
        args = video_codec_args('h264_nvenc', PROFILES['YouTube 1080p 60'])
        for flag, expected in (('-rc', 'vbr'), ('-cq', '19'), ('-b:v', '0'), ('-maxrate', '40M'),
                               ('-bufsize', '80M'), ('-preset', 'p5'), ('-tune', 'hq'),
                               ('-multipass', 'fullres'), ('-spatial-aq', '1'), ('-temporal-aq', '1'),
                               ('-rc-lookahead', '32'), ('-b_ref_mode', 'middle'), ('-g', '120'),
                               ('-pix_fmt', 'yuv420p')):
            self.assertEqual(value(args, flag), expected, flag)

    def test_levels(self):
        profile = PROFILES['YouTube 1080p 30']
        self.assertNotIn('-temporal-aq', nvenc_args('h264_nvenc', profile, 'safe'))
        self.assertIn('-cq', nvenc_args('h264_nvenc', profile, 'safe'))
        self.assertEqual(nvenc_args('h264_nvenc', profile, False), ['-preset', 'p5', '-b:v', '24M', '-g', '60'])

    def test_ten_bit_profiles(self):
        hevc = video_codec_args('hevc_nvenc', PROFILES['MP4 H.265 10-bit 4K 60'])
        self.assertEqual((value(hevc, '-pix_fmt'), value(hevc, '-profile:v')), ('p010le', 'main10'))
        self.assertEqual(value(video_codec_args('av1_nvenc', PROFILES['MP4 AV1 10-bit 1440p 60']), '-pix_fmt'), 'p010le')
        self.assertEqual(value(video_codec_args('libx265', PROFILES['MP4 H.265 10-bit 4K 60']), '-pix_fmt'), 'yuv420p10le')
        # H.264 NVENC no tiene 10 bits: nunca se pide.
        ten_bit_h264 = ExportProfile('x', 'h264', 'mp4', 1920, 1080, 60, '40M', True)
        self.assertEqual(value(video_codec_args('h264_nvenc', ten_bit_h264), '-pix_fmt'), 'yuv420p')

    def test_ten_bit_falls_back_to_eight_bit_with_warning(self):
        clip = make_clip(MEDIA, 1000)
        option = dict(NV, encoder='hevc_nvenc', ten_bit=False)
        args, warnings = build_export_command([clip], PROFILES['MP4 H.265 10-bit 4K 60'], 'o.mp4', option)
        self.assertEqual(value(args, '-pix_fmt'), 'yuv420p')
        self.assertTrue(any('10 bits' in w for w in warnings))

    def test_profiles_raise_youtube_bitrates(self):
        self.assertEqual(PROFILES['YouTube 1080p 60'].bitrate, '40M')
        self.assertEqual(PROFILES['YouTube 4K 60'].bitrate, '100M')
        self.assertTrue(PROFILES['MP4 AV1 10-bit 4K 60'].ten_bit)


class AttemptTests(unittest.TestCase):
    def test_gpu_first_then_lower_levels_then_cpu(self):
        clip = make_clip(MEDIA, 1000)
        attempts = export_attempts([clip], PROFILES['YouTube 1080p 60'], 'o.mp4', {'options': [NV, CPU]})
        labels = [label for label, _, _ in attempts]
        self.assertEqual(labels, ['NVIDIA · h264_nvenc (calidad máxima)',
                                  'NVIDIA · h264_nvenc (calidad optimizada)',
                                  'NVIDIA · h264_nvenc (modo compatible)',
                                  'CPU · libx264'])
        self.assertIn('h264_nvenc', attempts[0][1])
        self.assertIn('libx264', attempts[-1][1])

    def test_explicit_cpu_choice_has_single_attempt(self):
        clip = make_clip(MEDIA, 1000)
        attempts = export_attempts([clip], PROFILES['YouTube 1080p 60'], 'o.mp4', {'options': [NV, CPU]}, 'CPU')
        self.assertEqual([a[0] for a in attempts], ['CPU · libx264'])

    def test_label(self):
        self.assertEqual(encoder_label(dict(NV, tuned=False)), 'NVIDIA · h264_nvenc (modo compatible)')


if __name__ == '__main__':
    unittest.main()
