"""Modelo temporal de efectos; sin dependencias de interfaz.

Todas las coordenadas son normalizadas [0,1] respecto de la imagen fuente.
Los keyframes usan el tiempo ABSOLUTO del archivo fuente (ms), para que
cortar una pieza no desplace los efectos de los fragmentos resultantes.
"""
from copy import deepcopy
from math import isfinite


def clamp(value, low, high):
    value = float(value)
    if not isfinite(value):
        raise ValueError('Valor de efecto no finito')
    return max(low, min(high, value))


def default_mask():
    return {'x': .35, 'y': .35, 'w': .30, 'h': .30}


def valid_mask(mask):
    w = clamp(mask.get('w', .3), .025, 1)
    h = clamp(mask.get('h', .3), .025, 1)
    x = clamp(mask.get('x', .35), 0, 1-w)
    y = clamp(mask.get('y', .35), 0, 1-h)
    return {'x': x, 'y': y, 'w': w, 'h': h}


def default_effects():
    return {
        'zoom': {'enabled': False, 'scale': 1.0, 'cx': .5, 'cy': .5, 'keys': []},
        'censor': {'enabled': False, 'mode': 'blur', 'strength': 18,
                   'feather': .015, 'mask': default_mask(), 'keys': []},
        'color': {'enabled': False, 'brightness': 0, 'contrast': 1.,
                  'saturation': 1., 'grayscale': False, 'mirror': False},
    }


def merged_effects(raw):
    out = default_effects()
    if isinstance(raw, dict):
        for key in out:
            if isinstance(raw.get(key), dict):
                out[key].update(deepcopy(raw[key]))
    out['censor']['mask'] = valid_mask(out['censor']['mask'])
    return out


def interpolate_keys(keys, source_ms, properties, default):
    """Interpolación lineal en tiempo de archivo, independiente de la edición."""
    points = sorted((k for k in keys if all(p in k for p in properties) and
                     isinstance(k.get('time_ms'), (int, float))),
                    key=lambda k:k['time_ms'])
    if not points:
        return dict(default)
    if source_ms <= points[0]['time_ms']:
        return {p: float(points[0][p]) for p in properties}
    if source_ms >= points[-1]['time_ms']:
        return {p: float(points[-1][p]) for p in properties}
    for left, right in zip(points, points[1:]):
        if left['time_ms'] <= source_ms <= right['time_ms']:
            alpha = ((source_ms-left['time_ms']) /
                     max(1, right['time_ms']-left['time_ms']))
            return {p:float(left[p])*(1-alpha)+float(right[p])*alpha
                    for p in properties}
    return dict(default)


def censor_mask(effects, source_ms):
    effect = merged_effects(effects)['censor']
    rect = interpolate_keys(effect.get('keys', []), source_ms,
                            ('x','y','w','h'), effect['mask'])
    return valid_mask(rect)


def zoom_state(effects, source_ms):
    effect = merged_effects(effects)['zoom']
    raw = interpolate_keys(effect.get('keys', []), source_ms,
                           ('scale','cx','cy'), effect)
    return {'scale':clamp(raw['scale'], 1, 6),
            'cx':clamp(raw['cx'],0,1), 'cy':clamp(raw['cy'],0,1)}


def add_keyframe(keys, time_ms, values):
    updated = [deepcopy(k) for k in keys if abs(k['time_ms'] - time_ms) > 20]
    updated.append(dict(time_ms=int(time_ms), **values))
    return sorted(updated, key=lambda k:k['time_ms'])


def change_speed(clips, clip_id, new_speed, min_duration_ms=1):
    """Cambia velocidad sin perder el rango fuente, enlazando A/V.

    Al ajustar la duración se preservan los siguientes inicios; no se hace
    ripple-edit automático, evitando mover otros clips accidentalmente.
    """
    rate = clamp(new_speed, .25, 4.)
    clip = next((c for c in clips if c['id']==clip_id), None)
    if clip is None:
        return False
    link = clip.get('link')
    group = [c for c in clips if c['id']==clip_id or
             (link and c.get('link') == link)]
    for c in group:
        old = float(c.get('speed', 1.))
        source_length = c['duration_ms'] * old
        c['duration_ms'] = max(min_duration_ms,round(source_length/rate))
        c['speed'] = rate
        from timeline.fades import clamp_fades
        clamp_fades(c)
    return True
