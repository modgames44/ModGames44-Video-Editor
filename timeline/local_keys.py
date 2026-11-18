"""Keyframes guardados en tiempo LOCAL del clip (ms desde su inicio).

`transform_keys` (títulos, subtítulos, imágenes) y `volume_keys` (audio) se
miden desde el comienzo del clip en la Timeline. Cuando se corta o se recorta
el inicio, ese origen cambia y los keyframes deben desplazarse; si no, la
animación o la curva de volumen quedan descolocadas.

Los efectos de video (zoom/censura) usan tiempo de ARCHIVO y no necesitan esto.
"""
from effects.keyframe_expressions import sample

LOCAL_KEY_LISTS = ('transform_keys', 'volume_keys')


def _value_at(clip, list_name, local_ms):
    """Estado interpolado en `local_ms`, con los mismos valores por defecto."""
    if list_name == 'transform_keys':
        from effects.title_overlay import transform_at
        return transform_at(clip, clip['start_ms'] + local_ms)
    return {'volume': sample(clip.get('volume_keys') or [], local_ms, 'volume', 1)}


def split_local_keys(clip, left, right, relative_ms):
    """Reparte los keyframes de `clip` entre las dos mitades de un corte."""
    for name in LOCAL_KEY_LISTS:
        keys = clip.get(name) or []
        if not keys:
            continue
        at_cut = _value_at(clip, name, relative_ms)
        left[name] = ([dict(k) for k in keys if k['time_ms'] < relative_ms]
                      + [dict(time_ms=relative_ms, **at_cut)])
        right[name] = ([dict(time_ms=0, **at_cut)]
                       + [dict(k, time_ms=k['time_ms'] - relative_ms)
                          for k in keys if k['time_ms'] > relative_ms])


def shift_local_keys(clip, delta_ms):
    """Recorte de inicio: el origen local avanza (delta>0) o retrocede (delta<0).

    Debe llamarse ANTES de modificar `start_ms`. Los keyframes que quedan
    fuera se sustituyen por el valor interpolado en el nuevo inicio.
    """
    delta_ms = int(delta_ms)
    if not delta_ms:
        return
    for name in LOCAL_KEY_LISTS:
        keys = clip.get(name) or []
        if not keys:
            continue
        if delta_ms > 0:
            at_start = _value_at(clip, name, delta_ms)
            kept = [dict(k, time_ms=k['time_ms'] - delta_ms)
                    for k in keys if k['time_ms'] > delta_ms]
            clip[name] = [dict(time_ms=0, **at_start)] + kept
        else:
            clip[name] = [dict(k, time_ms=k['time_ms'] - delta_ms) for k in keys]
