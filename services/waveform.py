"""Ondas PCM estéreo multirresolución para la Timeline.

El archivo original NO se modifica. Los picos firmados (mínimo y máximo) se
conservan independientemente para L/R. La pirámide se calcula una sola vez,
no durante el zoom. Las coordenadas de edición siguen en milisegundos.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np

SAMPLE_RATE = 12000
BASE_SAMPLES = 16  # 1,33 ms por grupo: ~0,93 px a 700 px/s
CHUNK_GROUPS = 8192
CACHE_VERSION = 5


def _cache_path(path: str, cache_dir: str | None = None, effect_key: str = "") -> Path:
    p = Path(path)
    st = p.stat()
    key = hashlib.sha256(f'{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|{CACHE_VERSION}|{effect_key}'.encode()).hexdigest()
    base = Path(cache_dir) if cache_dir else Path(os.getenv('LOCALAPPDATA') or Path.home() / '.cache') / 'ModGames44' / 'VideoEditor' / 'waves'
    return base / f'{key}.npz'


def _levels_from_base(base: np.ndarray) -> list[np.ndarray]:
    """Array de shape (grupos, canales L/R, mínimo/máximo)."""
    levels = [np.ascontiguousarray(base, dtype=np.int16)]
    previous = levels[0]
    while len(previous) > 1:
        if len(previous) % 2:
            previous = np.concatenate([previous, previous[-1:]], axis=0)
        pairs = previous.reshape(-1, 2, 2, 2)
        next_level = np.empty((len(pairs), 2, 2), dtype=np.int16)
        next_level[:, :, 0] = pairs[:, :, :, 0].min(axis=1)
        next_level[:, :, 1] = pairs[:, :, :, 1].max(axis=1)
        levels.append(next_level)
        previous = next_level
    return levels


class StereoWaveform:
    def __init__(self, base: np.ndarray, sample_rate: int = SAMPLE_RATE, base_samples: int = BASE_SAMPLES):
        if base.ndim != 3 or base.shape[1:] != (2, 2):
            raise ValueError('Se requieren picos estéreo [tiempo, canal, min/max]')
        self.levels = _levels_from_base(base)
        self.sample_rate = int(sample_rate)
        self.base_samples = int(base_samples)
        peak = max(abs(int(self.levels[0][:, :, 0].min(initial=0))),
                   abs(int(self.levels[0][:, :, 1].max(initial=0)))) if len(base) else 0
        self.peak = peak / 32768.0
        # Solo presentación: no altera volumen ni valores PCM almacenados.
        self.display_gain = min(12.0, 0.94 / self.peak) if self.peak > 0.001 else 1.0

    @property
    def duration_ms(self) -> float:
        return len(self.levels[0]) * self.base_samples * 1000 / self.sample_rate

    def peaks(self, start_ms: float, end_ms: float, columns: int) -> np.ndarray:
        """Para cada píxel, extremos de AMBOS canales sin perder picos.

        Si el píxel abarca muchos grupos, elegimos un nivel agregado; si
        abarca menos de uno, recuperamos el grupo más preciso disponible.
        """
        columns = max(0, int(columns))
        out = np.zeros((columns, 2, 2), dtype=np.float32)
        if not columns or not len(self.levels[0]) or end_ms <= start_ms:
            return out
        groups_per_pixel = (end_ms - start_ms) / columns / 1000 * self.sample_rate / self.base_samples
        level_index = min(len(self.levels) - 1, max(0, int(math.floor(math.log2(max(1, groups_per_pixel))))))
        data = self.levels[level_index]
        group_ms = 1000.0 * self.base_samples * (2 ** level_index) / self.sample_rate
        edges = np.linspace(start_ms / group_ms, end_ms / group_ms, columns + 1)
        for x in range(columns):
            left = max(0, min(len(data), math.floor(edges[x])))
            right = max(left + 1, math.ceil(edges[x+1]))
            right = min(len(data), right)
            if left >= right:
                continue
            section = data[left:right]
            out[x, :, 0] = section[:, :, 0].min(axis=0) / 32768.0
            out[x, :, 1] = section[:, :, 1].max(axis=0) / 32768.0
        return out


def decode_pcm_peaks(path: str, ffmpeg_executable: str, *, timeout: float = 600, audio_filters=None) -> StereoWaveform:
    """Decodifica por streaming: nunca carga el PCM completo en memoria.

    FFmpeg escribe s16le estéreo a SAMPLE_RATE, convertido desde cualquier
    códec que soporte. Solo almacenamos valores mínimo/máximo agrupados.
    """
    import time
    args = [ffmpeg_executable, '-hide_banner', '-nostdin', '-loglevel', 'error',
            '-i', str(path), '-vn', '-map', '0:a:0']
    if audio_filters:
        args += ['-af', ','.join(audio_filters)]
    args += ['-ac', '2', '-ar', str(SAMPLE_RATE), '-f', 's16le', 'pipe:1']
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    blocks = []
    leftover = b''
    started = time.monotonic()
    read_bytes = BASE_SAMPLES * 2 * 2 * CHUNK_GROUPS
    try:
        while True:
            if time.monotonic() - started > timeout:
                raise TimeoutError('Tiempo máximo de análisis de audio excedido')
            piece = proc.stdout.read(read_bytes)
            if not piece:
                break
            data = leftover + piece
            usable = len(data) // (BASE_SAMPLES * 4) * (BASE_SAMPLES * 4)
            leftover = data[usable:]
            if not usable:
                continue
            pcm = np.frombuffer(data[:usable], dtype='<i2').reshape(-1, BASE_SAMPLES, 2)
            peaks = np.empty((len(pcm), 2, 2), dtype=np.int16)
            peaks[:, :, 0] = pcm.min(axis=1)
            peaks[:, :, 1] = pcm.max(axis=1)
            blocks.append(peaks)
        status = proc.wait(timeout=5)
        if status != 0:
            raise RuntimeError(f'FFmpeg no pudo decodificar audio (código {status})')
        return StereoWaveform(np.concatenate(blocks) if blocks else np.empty((0, 2, 2), dtype=np.int16))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stdout:
            proc.stdout.close()


def get_waveform(path: str, ffmpeg_executable: str, cache_dir: str | None = None) -> StereoWaveform:
    cached = _cache_path(path, cache_dir)
    if cached.exists():
        try:
            with np.load(cached, allow_pickle=False) as obj:
                base = obj['peaks']
            return StereoWaveform(base)
        except (OSError, ValueError, KeyError):
            pass
    wave = decode_pcm_peaks(path, ffmpeg_executable)
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        # Archivo temporal en el mismo directorio para sustitución atómica.
        with tempfile.NamedTemporaryFile(dir=cached.parent, suffix='.npz', delete=False) as temporary:
            temp_path = Path(temporary.name)
        try:
            np.savez_compressed(temp_path, peaks=wave.levels[0])
            temp_path.replace(cached)
        finally:
            temp_path.unlink(missing_ok=True)
    except OSError:
        pass  # caché opcional, nunca debe impedir editar
    return wave


# La caché de ondas procesadas usa la MISMA cadena FFmpeg que la escucha
# y la exportación. El efecto se calcula fuera del hilo de Qt.
def effect_signature(settings) -> str:
    import json
    from effects.audio import validated_audio_effects
    canonical = validated_audio_effects(settings)
    packed = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(packed.encode('utf8')).hexdigest()[:20]


def needs_processed_waveform(settings) -> bool:
    """La ganancia aislada se dibuja de inmediato multiplicando amplitudes."""
    from effects.audio import validated_audio_effects
    fx = validated_audio_effects(settings)
    return bool(fx['voice'] != 'none' or fx['noise'] > 0 or fx['normalize'])


def get_effect_waveform(path: str, ffmpeg_executable: str, settings,
                        cache_dir: str | None = None) -> StereoWaveform:
    from effects.audio import audio_filter_chain
    if not needs_processed_waveform(settings):
        return get_waveform(path, ffmpeg_executable, cache_dir)
    signature = effect_signature(settings)
    cached = _cache_path(path, cache_dir, effect_key=signature)
    if cached.exists():
        try:
            with np.load(cached, allow_pickle=False) as obj:
                return StereoWaveform(obj['peaks'])
        except (OSError, ValueError, KeyError):
            pass
    filters = audio_filter_chain(settings, speed=1.0)
    wave = decode_pcm_peaks(path, ffmpeg_executable, audio_filters=filters)
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cached.parent, suffix='.npz', delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            np.savez_compressed(temporary_path, peaks=wave.levels[0])
            temporary_path.replace(cached)
        finally:
            temporary_path.unlink(missing_ok=True)
    except OSError:
        pass
    return wave


def waveform_gain_linear(db: float) -> float:
    """Factor de amplitud para una forma de onda con ganancia de clip."""
    db = float(db)
    if not math.isfinite(db):
        raise ValueError('Ganancia no finita')
    return 10.0 ** (db / 20.0)
