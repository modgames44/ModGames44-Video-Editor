"""Pruebas de PCM real, estéreo, zoom, caché y silencio; sin interfaz Qt."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from services.waveform import StereoWaveform, get_waveform


class WaveformTests(unittest.TestCase):
    def test_stereo_is_independent(self):
        groups=200
        peaks=np.empty((groups,2,2), dtype=np.int16)
        peaks[:,0,:]=[-23000,23000]
        peaks[:,1,:]=[-200,200]
        wave=StereoWaveform(peaks)
        far=wave.peaks(0,wave.duration_ms,10)
        close=wave.peaks(0,wave.duration_ms,80)
        for view in (far,close):
            self.assertGreater(float(view[:,0,1].max()),0.6)
            self.assertLess(float(view[:,1,1].max()),0.01)

    def test_peaks_preserved_across_scales(self):
        data=np.zeros((256,2,2), dtype=np.int16)
        data[100,0,:]=[-32000,31000]
        wave=StereoWaveform(data)
        for columns in (1,8,32,256,512):
            pixels=wave.peaks(0,wave.duration_ms,columns)
            self.assertAlmostEqual(float(pixels[:,:,1].max()),31000/32768,places=4)
            self.assertAlmostEqual(float(pixels[:,:,0].min()),-32000/32768,places=4)

    def test_silence_and_outside_range(self):
        wave=StereoWaveform(np.zeros((200,2,2),np.int16))
        self.assertEqual(wave.peak,0)
        self.assertEqual(float(wave.peaks(-500,-100,10).sum()),0)
        self.assertEqual(float(wave.peaks(0,wave.duration_ms,10).sum()),0)

    def test_decode_audio_and_cache(self):
        try:
            import imageio_ffmpeg
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            self.skipTest('FFmpeg no disponible')
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            source=str(Path(td)/'stereo.wav')
            # Canal L intenso, R tenue: prueba de la decodificación independiente.
            proc=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-f','lavfi',
                '-i','aevalsrc=0.7*sin(2*PI*440*t)|0.04*sin(2*PI*220*t):s=48000:d=1',
                '-ac','2',source],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            self.assertEqual(proc.returncode,0,proc.stderr.decode(errors='replace'))
            wave=get_waveform(source,ffmpeg,td)
            cached=get_waveform(source,ffmpeg,td)
            a=wave.peaks(0,500,200)
            b=cached.peaks(0,500,200)
            self.assertTrue(np.allclose(a,b))
            self.assertGreater(float(a[:,0,1].max()),float(a[:,1,1].max())*8)
            self.assertEqual(len(list(Path(td).glob('*.npz'))),1)

if __name__=='__main__':unittest.main()
