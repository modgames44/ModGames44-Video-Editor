"""Render incremental del audio de la Timeline para escucharlo ANTES de exportar.

No depende de Qt: se puede probar con FFmpeg/FFprobe y WAV reales.
La misma cadena audio_filter_chain() se usa tanto aquí como al exportar.
Se renderizan ventanas pequeñas para no procesar horas de video al pulsar Play.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from effects.audio import audio_filter_chain
from timeline.model import end, source_position
from timeline.fades import audio_fade_filters

SAMPLE_RATE = 48000
CHANNELS = 2
WINDOW_MS = 30000


def _sec(value):
    return f'{max(0.0, float(value)) / 1000:.6f}'


def audio_clips_in_window(clips, start_ms, duration_ms):
    """Intersecciones (clip, inicio absoluto, fin absoluto), sin cambiar el modelo."""
    finish = start_ms + duration_ms
    return [(c, max(start_ms, c['start_ms']), min(finish, end(c)))
            for c in clips if c.get('kind') == 'audio'
            and c['start_ms'] < finish and end(c) > start_ms]


def audio_signature(clips):
    """Solo el audio: editar color o máscara no fuerza a regenerar WAV."""
    fields = ('path', 'start_ms', 'in_ms', 'duration_ms', 'speed', 'audio_fx',
              'kind', 'track', 'fade_in_ms', 'fade_out_ms')
    audio = [{k: c.get(k) for k in fields} for c in clips
             if c.get('kind') == 'audio']
    payload = json.dumps(audio, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode('utf8')).hexdigest()[:20]


def window_bounds(timeline_ms, total_ms, window_ms=WINDOW_MS):
    total = max(0, int(total_ms))
    pos = max(0, min(int(timeline_ms), max(0, total - 1)))
    start = (pos // window_ms) * window_ms
    return start, min(window_ms, max(0, total - start))


def build_audio_preview_command(clips, start_ms, duration_ms, destination,
                                ffmpeg='ffmpeg'):
    """FFmpeg crea mezcla estéreo de UN tramo. Reutiliza filtros de exportación.

    El seek es por archivo ANTES del input para que un clip de 90 minutos no
    requiera decodificar toda su duración al situar el cabezal en 01:10:00.
    La pista base silenciosa preserva los huecos de la secuencia.
    """
    if not 0 <= start_ms or duration_ms <= 0:
        raise ValueError('Ventana de audio inválida')
    args = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-f', 'lavfi', '-i',
            f'anullsrc=r={SAMPLE_RATE}:cl=stereo:d={_sec(duration_ms)}']
    graph = []
    inputs = []
    for c, begin, finish in audio_clips_in_window(clips, start_ms, duration_ms):
        source_start = source_position(c, begin)
        speed = float(c.get('speed', 1.))
        if not math.isfinite(speed) or not .25 <= speed <= 4.:
            raise ValueError('Velocidad fuera de rango')
        length_ms = finish - begin
        source_ms = length_ms * speed
        if source_start < 0 or source_ms <= 0:
            continue
        path = Path(c['path'])
        if not path.is_file():
            raise FileNotFoundError(str(path))
        index = len(inputs) + 1
        args += ['-ss', _sec(source_start), '-t', _sec(source_ms + 250),
                 '-i', str(path)]
        filters = [f'atrim=duration={_sec(source_ms)}', 'asetpts=PTS-STARTPTS']
        filters += audio_filter_chain(c.get('audio_fx'), speed)
        filters += audio_fade_filters(c, offset_ms=begin-c['start_ms'])
        filters += ['aresample=48000', 'aformat=channel_layouts=stereo',
                    f'atrim=duration={_sec(length_ms)}',
                    f'apad=whole_dur={_sec(length_ms)}',
                    f'atrim=duration={_sec(length_ms)}',
                    f'adelay={begin-start_ms}:all=1']
        name = f'part{index}'
        graph.append(f'[{index}:a:0]' + ','.join(filters) + f'[{name}]')
        inputs.append(name)
    graph.append(f'[0:a]atrim=duration={_sec(duration_ms)},asetpts=PTS-STARTPTS[base]')
    streams = '[base]' + ''.join(f'[{name}]' for name in inputs)
    graph.append(f'{streams}amix=inputs={len(inputs)+1}:duration=first:normalize=0,'
                 f'atrim=duration={_sec(duration_ms)},alimiter=limit=0.95,'
                 f'aresample={SAMPLE_RATE},aformat=sample_fmts=s16:channel_layouts=stereo[aout]')
    args += ['-filter_complex', ';'.join(graph), '-map', '[aout]',
             '-ac', str(CHANNELS), '-ar', str(SAMPLE_RATE),
             '-c:a', 'pcm_s16le', '-t', _sec(duration_ms), str(destination)]
    return args


def render_audio_window(clips, start_ms, duration_ms, destination, ffmpeg='ffmpeg', timeout=150):
    """Render atómico: un WAV parcial nunca se presenta al reproductor."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.stem + '.partial.wav')
    try:
        cmd = build_audio_preview_command(clips, start_ms, duration_ms,
                                          temporary, ffmpeg)
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                timeout=timeout, check=False,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            message = result.stderr.decode('utf8', errors='replace')[-1600:]
            raise RuntimeError('FFmpeg no pudo preparar la escucha: ' + message)
        if not temporary.is_file() or temporary.stat().st_size < 44:
            raise RuntimeError('La ventana de audio salió vacía')
        os.replace(temporary, target)
        return str(target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
