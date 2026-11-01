"""Desvanecimientos lineales independientes de video y audio.

Modelo no destructivo. Las duraciones se expresan en milisegundos del clip
(en tiempo de Timeline, no de archivo). No depende de Qt ni FFmpeg.
"""
from __future__ import annotations

import math


def fade_durations(clip):
    duration = max(1, int(clip.get('duration_ms', 1)))
    inside = max(0, min(duration, int(clip.get('fade_in_ms', 0) or 0)))
    outside = max(0, min(duration - inside, int(clip.get('fade_out_ms', 0) or 0)))
    return inside, outside


def fade_factor(clip, timeline_ms):
    """Envolvente entre 0 y 1 para el instante absoluto solicitado."""
    duration = max(1, int(clip['duration_ms']))
    position = max(0., min(float(duration), float(timeline_ms) - float(clip['start_ms'])))
    fade_in, fade_out = fade_durations(clip)
    level = 1.
    if fade_in:
        level = min(level, position / fade_in)
    if fade_out:
        level = min(level, (duration - position) / fade_out)
    return max(0., min(1., level))


def clamp_fades(clip):
    """Normaliza duraciones almacenadas tras recortar/importar un clip."""
    fi, fo = fade_durations(clip)
    clip['fade_in_ms'] = fi
    clip['fade_out_ms'] = fo
    return clip


def change_fade(clip, side, duration_ms):
    """Actualiza un solo extremo sin modificar el otro ni la longitud del clip."""
    if side not in ('in', 'out'):
        return False
    clamp_fades(clip)
    field = 'fade_in_ms' if side == 'in' else 'fade_out_ms'
    opposite = 'fade_out_ms' if side == 'in' else 'fade_in_ms'
    max_ms = max(0, int(clip['duration_ms']) - int(clip[opposite]))
    value = max(0, min(max_ms, int(round(duration_ms))))
    if clip[field] == value:
        return False
    clip[field] = value
    return True


def split_fade(left, right, original):
    """Los fades quedan ligados a los bordes exteriores del clip original.

    Un corte no introduce nuevos desvanecimientos en el punto de división.
    """
    fi, fo = fade_durations(original)
    left['fade_in_ms'] = min(fi, left['duration_ms'])
    left['fade_out_ms'] = 0
    right['fade_in_ms'] = 0
    right['fade_out_ms'] = min(fo, right['duration_ms'])
    clamp_fades(left)
    clamp_fades(right)


def audio_fade_filters(clip, *, offset_ms=0):
    """Envolvente real FFmpeg, compatible con previsualización por ventanas.

    En el render completo se usa afade (preciso en muestras). Si una ventana
    comienza después del inicio del clip usamos una función de volumen
    absoluta: afade no admite st negativo y reiniciaría mal la curva.
    """
    fi, fo = fade_durations(clip)
    if not (fi or fo):
        return []
    offset = max(0, int(offset_ms))
    duration = int(clip['duration_ms'])
    if offset:
        factors = []
        if fi:
            factors.append(f'min(1\\,max(0\\,(t+{offset/1000:.6f})/{fi/1000:.6f}))')
        if fo:
            factors.append(f'min(1\\,max(0\\,({duration/1000:.6f}-t-{offset/1000:.6f})/{fo/1000:.6f}))')
        expression = '*'.join(factors)
        return [f"volume='{expression}':eval=frame"]
    out = []
    if fi:
        out.append(f'afade=t=in:st=0:d={fi/1000:.6f}:curve=tri')
    if fo:
        st = (duration - fo) / 1000
        out.append(f'afade=t=out:st={st:.6f}:d={fo/1000:.6f}:curve=tri')
    return out


def video_fade_filters(clip):
    """FFmpeg: alpha (no fundido de color) para respetar capas inferiores."""
    fi, fo = fade_durations(clip)
    if not (fi or fo):
        return []
    duration = int(clip['duration_ms']) / 1000
    commands = ['format=rgba']
    if fi:
        commands.append(f'fade=t=in:st=0:d={fi/1000:.6f}:alpha=1')
    if fo:
        commands.append(f'fade=t=out:st={duration-fo/1000:.6f}:d={fo/1000:.6f}:alpha=1')
    return commands
