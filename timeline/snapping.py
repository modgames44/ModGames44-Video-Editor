"""Arrastre magnético de clips no destructivo (puro, sin Qt).

- Ajusta inicio e instante final a límites de otros clips y al cabezal.
- Tolera unos 12 píxeles, independientemente del nivel de zoom.
- Con el imán habilitado evita solapes accidentales en la misma pista AV.
- Traslada audio/vídeo vinculados exactamente el mismo delta.
- Títulos, imágenes y subtítulos siguen pudiendo superponerse a otras capas.
"""
from timeline.model import end


AV_KINDS = ('video', 'audio')


def plan_magnetic_move(clips, clip_id, requested_start_ms, target_track, *,
                       enabled=True, pixels_per_second=70, playhead_ms=None,
                       tolerance_px=12):
    """Devuelve (delta_ms, target_track). Nunca modifica la lista original.

    Si imán está desactivado no limita colisiones (solapamiento intencional).
    Con imán, se acopla al borde más cercano y cualquier colisión no deseada
    se resuelve moviendo el grupo hasta la separación legal más próxima.
    """
    main = next((c for c in clips if c['id'] == clip_id), None)
    if main is None:
        return 0, int(target_track)
    target_track = int(target_track)
    link = main.get('link')
    moving = ([c for c in clips if c.get('link') == link] if link else [main])
    ids = {c['id'] for c in moving}
    others = [c for c in clips if c['id'] not in ids]
    min_delta = -min(int(c['start_ms']) for c in moving)
    desired = max(min_delta, int(round(requested_start_ms)) - int(main['start_ms']))
    if not enabled:
        return desired, target_track

    def track_of(c):
        return target_track if c['id'] == main['id'] else int(c.get('track', 0))

    obstacles = []
    for moving_clip in moving:
        if moving_clip.get('kind') not in AV_KINDS:
            continue
        start = int(moving_clip['start_ms'])
        finish = end(moving_clip)
        for other in others:
            if (other.get('kind') != moving_clip.get('kind') or
                    int(other.get('track', 0)) != track_of(moving_clip)):
                continue
            # Intervalo abierto de deltas que producirían un solapamiento.
            obstacles.append((int(other['start_ms'])-finish,
                              end(other)-start))

    def legal(delta):
        return delta >= min_delta and all(
            not (low < delta < high) for low, high in obstacles)

    # Ajustes del imán: inicio a final y final a inicio. También límites de
    # otras pistas (edición multipista), origen y opcionalmente el cabezal.
    magnets = [0]
    if playhead_ms is not None:
        magnets.append(max(0, int(playhead_ms)))
    for other in others:
        magnets.extend((int(other['start_ms']), end(other)))

    tolerance = 1000.0 * max(1, float(tolerance_px)) / max(1.0, float(pixels_per_second))
    snap_candidates = []
    for clip in moving:
        start = int(clip['start_ms'])
        for target in magnets:
            for suggested in (target-start, target-end(clip)):
                if (abs(suggested-desired) <= tolerance and legal(suggested)):
                    snap_candidates.append(suggested)
    if snap_candidates:
        return min(snap_candidates, key=lambda d: (abs(d-desired), abs(d))), target_track

    # Evitar que el clip se «monte» sobre su vecino cuando la posición
    # solicitada queda dentro de él. Cada obstáculo se resuelve en sus dos
    # bordes, y se escoge el delta legal más cercano al mouse.
    if legal(desired):
        return desired, target_track
    candidates = {min_delta}
    for low, high in obstacles:
        candidates.add(max(min_delta, low))
        candidates.add(max(min_delta, high))
    possible = [d for d in candidates if legal(d)]
    if not possible:
        return 0, target_track
    return min(possible, key=lambda d: (abs(d-desired), abs(d))), target_track
