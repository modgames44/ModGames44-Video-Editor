"""Operaciones de edición no destructivas sin dependencia de Qt.

Las coordenadas y duraciones están en milisegundos de Timeline.
Las parejas de audio y vídeo comparten `link` y cada segmento dividido
recibe una nueva pareja de identificadores de vínculo.
"""

import uuid
from timeline.model import end, split
from timeline.fades import clamp_fades


def linked_group(clips, clip_id):
    main = next((clip for clip in clips if clip['id'] == clip_id), None)
    if main is None:
        return []
    link = main.get('link')
    if not link:
        return [main]
    return [clip for clip in clips if clip.get('link') == link]


def split_at(clips, clip_id, time_ms):
    """Divide clip y pareja enlazada en el tiempo pulsado.

    Devuelve el ID del nuevo segmento derecho del clip pulsado, o None
    cuando no existe un corte válido (no modifica `clips` entonces).
    """
    group = linked_group(clips, clip_id)
    if not group:
        return None
    time_ms = int(time_ms)
    if not any(c['id'] == clip_id and c['start_ms'] < time_ms < end(c) for c in group):
        return None

    # Si hay compañeros enlazados, sólo se mantienen enlazados los segmentos
    # efectivamente divididos. Nunca dejar un vínculo a un segmento distinto.
    right_ids = {}
    for clip in group:
        if clip['start_ms'] < time_ms < end(clip):
            new_id = split(clips, clip['id'], time_ms)
            if new_id:
                right_ids[clip['id']] = new_id
    if len(right_ids) > 1:
        new_link = uuid.uuid4().hex
        for right_id in right_ids.values():
            next(c for c in clips if c['id'] == right_id)['link'] = new_link
    else:
        for right_id in right_ids.values():
            next(c for c in clips if c['id'] == right_id)['link'] = None
    return right_ids.get(clip_id)


def trim_bounds(clips, clip_id, side, media_durations, minimum_ms=1):
    """Calcula deltas admisibles sin dejar el inicio negativo ni leer más allá del archivo.

    Positivo significa desplazar el borde hacia la derecha, para ambos bordes.
    `media_durations` es un mapa path -> duración original del medio.
    """
    group = linked_group(clips, clip_id)
    if not group or side not in ('inicio', 'final'):
        return (0, 0)
    if side == 'inicio':
        low = max(-c['start_ms'] for c in group)
        low = max(low, max(-c.get('in_ms', 0)/float(c.get('speed', 1.)) for c in group))
        high = min(c['duration_ms'] - minimum_ms for c in group)
    else:
        low = max(minimum_ms - c['duration_ms'] for c in group)
        high = min(max(0, media_durations.get(c['path'],
                   c.get('in_ms', 0) + c['duration_ms']*float(c.get('speed',1.))) -
                   (c.get('in_ms', 0) + c['duration_ms']*float(c.get('speed',1.))))/float(c.get('speed',1.)) for c in group)
    return (int(low), int(max(low, high)))


def trim_linked(clips, clip_id, side, delta_ms, media_durations, minimum_ms=1):
    """Desplaza el borde y su pareja vinculada, si el cambio es válido."""
    delta_ms = int(delta_ms)
    if not delta_ms:
        return False
    low, high = trim_bounds(clips, clip_id, side, media_durations, minimum_ms)
    if not low <= delta_ms <= high:
        return False
    for clip in linked_group(clips, clip_id):
        if side == 'inicio':
            clip['start_ms'] += delta_ms
            clip['in_ms'] = clip.get('in_ms', 0) + delta_ms*float(clip.get('speed',1.))
            clip['duration_ms'] -= delta_ms
        else:
            clip['duration_ms'] += delta_ms
        clamp_fades(clip)
    return True


def remove_linked(clips, selected_ids):
    """Elimina todos los seleccionados y sus compañeros enlazados."""
    chosen = set(selected_ids)
    for clip_id in tuple(chosen):
        chosen.update(c['id'] for c in linked_group(clips, clip_id))
    before = len(clips)
    clips[:] = [c for c in clips if c['id'] not in chosen]
    return before - len(clips)


def unlink(clips, selected_ids):
    """Separa las parejas de los segmentos elegidos para editar audio/vídeo por separado."""
    group_ids = set()
    for clip_id in selected_ids:
        group_ids.update(c['id'] for c in linked_group(clips, clip_id))
    altered = 0
    for clip in clips:
        if clip['id'] in group_ids and clip.get('link'):
            clip['link'] = None
            altered += 1
    return altered
