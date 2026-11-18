"""Límites de reproducción entre clips: detener únicamente ante huecos reales.

El corte (incluido Quitar silencios) crea IDs distintos, pero no debe
interrumpir Play si existe material audiovisual inmediatamente después.
Funciones puras, independientes de Qt.
"""
from timeline.model import end


def playback_end(clips, current_id):
    """Final donde comienza un hueco real, o None si sigue material AV.

    Se considera continuidad cuando un clip de vídeo o audio, de la misma u
    otra pista, cubre el instante del borde. Las capas de texto/imagen por sí
    solas no obligan a detener la reproducción de audio/vídeo.
    """
    current = next((c for c in clips if c['id'] == current_id), None)
    if not current or current.get('kind') not in ('video', 'audio'):
        return None
    boundary = end(current)
    if any(other['id'] != current_id and
           other.get('kind') in ('video', 'audio') and
           other['start_ms'] <= boundary < end(other)
           for other in clips):
        return None
    return boundary


def limited_position(clips, current_id, proposed_ms, stop_at_cuts=True):
    """(nueva_posición, detener): limitar solamente ante un hueco.

    `stop_at_cuts` se mantiene como nombre por compatibilidad con proyectos y
    preferencias anteriores, pero ahora significa «detener en huecos».
    """
    proposed_ms = max(0, int(proposed_ms))
    if not stop_at_cuts:
        return proposed_ms, False
    boundary = playback_end(clips, current_id)
    if boundary is not None and proposed_ms >= boundary:
        return boundary, True
    return proposed_ms, False
