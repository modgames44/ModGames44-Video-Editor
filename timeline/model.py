"""Modelo de secuencia no destructiva. Tiempo en milisegundos."""
import copy
import uuid


def make_clip(path, duration_ms, start_ms=0, track=0, in_ms=0, kind='video', link=None):
    return dict(id=uuid.uuid4().hex, path=str(path), start_ms=max(0,int(start_ms)),
                in_ms=max(0,int(in_ms)), duration_ms=max(1,int(duration_ms)),
                track=int(track), kind=kind, link=link,
                fade_in_ms=0, fade_out_ms=0)


def end(clip):
    return clip['start_ms'] + clip['duration_ms']


def source_position(clip, timeline_ms):
    return clip['in_ms'] + (timeline_ms - clip['start_ms']) * float(clip.get('speed', 1.0))


def active(clips, time_ms, kind='video'):
    matches = [c for c in clips if c.get('kind','video') == kind and c['start_ms'] <= time_ms < end(c)]
    return max(matches, key=lambda c: c.get('track', 0), default=None)


def split(clips, clip_id, time_ms):
    for index, c in enumerate(clips):
        if c['id'] == clip_id and c['start_ms'] < time_ms < end(c):
            # Copias profundas: las dos mitades no deben compartir los
            # diccionarios anidados (effects, audio_fx, listas de keyframes).
            left = copy.deepcopy(c)
            right = copy.deepcopy(c)
            right.update(id=uuid.uuid4().hex, start_ms=time_ms,
                         in_ms=c['in_ms'] + (time_ms - c['start_ms']) * float(c.get('speed', 1.0)),
                         duration_ms=end(c) - time_ms)
            left['duration_ms'] = time_ms - c['start_ms']
            from timeline.local_keys import split_local_keys
            split_local_keys(c, left, right, time_ms - c['start_ms'])
            from timeline.fades import split_fade
            split_fade(left, right, c)
            clips[index:index+1] = [left, right]
            return right['id']
    return None


OVERLAY_KINDS = ('title', 'subtitle', 'image')


def close_gap(clips, track, kind):
    """Elimina los espacios vacíos de una pista y devuelve los huecos quitados.

    Sólo se eliminan HUECOS: los solapes existentes (transiciones de
    disolución/barrido/deslizamiento) se conservan intactos. El resultado es
    una lista de intervalos (inicio, fin) en coordenadas originales.
    """
    items = sorted((c for c in clips if c.get('track', 0) == track and c.get('kind', 'video') == kind),
                   key=lambda c: c['start_ms'])
    gaps, shifts, reach = [], [], 0
    for c in items:
        if c['start_ms'] > reach:
            gaps.append((reach, c['start_ms']))
        shifts.append(sum(b - a for a, b in gaps))
        reach = max(reach, end(c))
    for c, shift in zip(items, shifts):
        c['start_ms'] -= shift
    return gaps


def map_time_after_gaps(time_ms, gaps):
    """Posición equivalente tras quitar `gaps`; dentro de un hueco, su inicio."""
    shift = 0
    for a, b in gaps:
        if b <= time_ms:
            shift += b - a
        elif a < time_ms:
            shift += time_ms - a
    return max(0, time_ms - shift)


def close_all_gaps(clips):
    """«Cerrar huecos» de toda la secuencia, manteniendo la sincronía.

    - V1-V3 se compactan conservando las transiciones.
    - El audio vinculado sigue a su video.
    - El audio independiente se compacta en su pista.
    - Títulos, subtítulos e imágenes siguen al contenido de la pista de video
      principal (la más baja con clips), para no quedar desincronizados.
    """
    reference = None
    for track in range(3):
        gaps = close_gap(clips, track, 'video')
        if reference is None and any(c.get('kind') == 'video' and c.get('track', 0) == track for c in clips):
            reference = gaps
    for clip in clips:
        if clip.get('kind') == 'video' and clip.get('link'):
            for other in clips:
                if other is not clip and other.get('link') == clip['link'] and other.get('kind') == 'audio':
                    other['start_ms'] = clip['start_ms']
    for track in range(3):
        independent = [c for c in clips if c.get('kind') == 'audio' and not c.get('link')
                       and c.get('track', 0) == track]
        close_gap(independent, track, 'audio')
    for clip in clips:
        if clip.get('kind') in OVERLAY_KINDS and reference:
            clip['start_ms'] = map_time_after_gaps(clip['start_ms'], reference)
