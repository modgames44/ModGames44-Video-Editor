"""Sugerencias locales de eliminación de silencios, sin alterar medios.

El análisis requiere FFmpeg. No confundir silencios detectados con palabras o intención.
"""
from __future__ import annotations
import re
import subprocess
from timeline.model import end

START_RE = re.compile(r'silence_start:\s*([\d.]+)')
END_RE = re.compile(r'silence_end:\s*([\d.]+)')


def ffmpeg_binary():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, FileNotFoundError):
        return 'ffmpeg'


def read_silences(log, duration_ms):
    starts = []
    spans = []
    for line in log.splitlines():
        a = START_RE.search(line)
        b = END_RE.search(line)
        if a:
            starts.append(float(a.group(1)))
        if b and starts:
            t = starts.pop(0)
            spans.append((max(0,round(t*1000)),min(duration_ms,round(float(b.group(1))*1000))))
    for t in starts:
        spans.append((max(0,round(t*1000)),duration_ms))
    return [(a,b) for a,b in spans if b>a]


def analyze_silences(clip, min_silence_s=0.75, threshold_db=-34):
    """Devuelve intervalos de silencio en la fuente, no en la timeline."""
    if not -90 <= threshold_db <= -10 or not 0.2 <= min_silence_s <= 15:
        raise ValueError('Parámetros de silencio fuera de rango.')
    cmd = [ffmpeg_binary(), '-nostdin', '-hide_banner', '-i', clip['path'],
           '-vn', '-af', f'silencedetect=n={threshold_db}dB:d={min_silence_s}',
           '-f', 'null', '-']
    kwargs = {}
    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                errors='replace', timeout=180, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'No se pudo analizar el audio con FFmpeg: {exc}') from exc
    if result.returncode != 0:
        raise RuntimeError('FFmpeg no pudo analizar el audio del archivo.')
    source_end = clip.get('in_ms', 0) + clip['duration_ms']
    return read_silences(result.stderr, source_end)


def silence_plan(clip, detected, min_remove_ms=500, margin_ms=120):
    """Genera borrados de los silencios detectados, desde el final hacia el inicio.
    Usa sólo el clip original (con audio vinculado) y nunca borra todo.
    """
    in_point = clip.get('in_ms', 0)
    source_end = in_point + clip['duration_ms']
    intervals = []
    for raw_a, raw_b in detected:
        a = max(in_point, int(raw_a) + margin_ms)
        b = min(source_end, int(raw_b) - margin_ms)
        if b-a >= min_remove_ms:
            a = clip['start_ms'] + a - in_point
            b = clip['start_ms'] + b - in_point
            intervals.append((a,b))
    intervals.sort(reverse=True)
    if sum(b-a for a,b in intervals) >= clip['duration_ms']-1000:
        return {'explanation':'El audio parece mayormente silencioso. No eliminaré todo el contenido.', 'operations': []}
    ops = [{'type':'remove_range','clip_id':clip['id'], 'start_ms':a,'end_ms':b} for a,b in intervals[:75]]
    return {'explanation': f'Detecté {len(ops)} intervalos de silencio; se dejarán espacios y puedes cerrarlos después.',
            'operations': ops}
