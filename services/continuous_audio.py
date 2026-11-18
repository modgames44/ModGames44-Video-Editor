"""Audio PCM continuo de toda la secuencia, sin división WAV en fragmentos.

FFmpeg produce bytes s16le estéreo a 48 kHz. El consumidor (Qt QAudioSink)
los reproduce en una sola salida sin saltos en los límites de 30 segundos.
El proceso puede reiniciarse en cualquier posición del tiempo.
"""
from services.preview_audio import build_audio_preview_command

SAMPLE_RATE = 48000
CHANNELS = 2
BYTES_PER_SAMPLE = 2
FRAME_BYTES = CHANNELS * BYTES_PER_SAMPLE


def build_stream_command(clips, start_ms, total_ms, ffmpeg='ffmpeg'):
    start = max(0, int(start_ms))
    duration = max(1, int(total_ms)-start)
    command = build_audio_preview_command(clips, start, duration, 'pipe:1', ffmpeg)
    # Últimas opciones del muxer de salida de render_audio_window.
    assert command[-1] == 'pipe:1' and '-c:a' in command
    command[-1:] = ['-f','s16le','pipe:1']
    return command


def pcm_stereo_peaks(chunk):
    """Picos normalizados L/R desde PCM s16le intercalado, independiente de Qt.

    Se ejecuta en el hilo de la interfaz cada 15 ms: numpy es ~7x más rápido
    que recorrer las muestras en Python.
    """
    if not chunk:
        return 0., 0.
    size = len(chunk) // FRAME_BYTES * FRAME_BYTES
    if not size:
        return 0., 0.
    import numpy as np
    samples = np.frombuffer(chunk, dtype='<i2', count=size // BYTES_PER_SAMPLE).reshape(-1, CHANNELS)
    peaks = np.abs(samples.astype(np.int32)).max(axis=0) / 32768.
    return min(1., float(peaks[0])), min(1., float(peaks[1]))
