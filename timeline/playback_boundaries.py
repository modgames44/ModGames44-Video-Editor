"""Límites temporales de clips para reproducir segmentos cortados.

No depende de Qt. La continuidad entre clips consecutivos no debe
provocar un salto sobre el borde de edición cuando stop_at_cuts=True.
"""
from timeline.model import end


def playback_end(clips, current_id):
    """Devuelve el instante exacto del final del segmento actual, o None.

    Se utiliza el ID del clip en reproducción, no el fin de la secuencia:
    un corte divide el clip en dos IDs, aunque sus bordes sean contiguos.
    """
    if current_id is None:
        return None
    for clip in clips:
        if clip['id'] == current_id:
            return end(clip)
    return None


def limited_position(clips, current_id, proposed_ms, stop_at_cuts=True):
    """Limita el tiempo al siguiente borde de corte sin sobrepasarlo.

    Devuelve (tiempo_nuevo, detener). Nunca recorta en modo continuo.
    """
    proposed_ms = max(0, int(proposed_ms))
    if not stop_at_cuts:
        return proposed_ms, False
    boundary = playback_end(clips, current_id)
    if boundary is not None and proposed_ms >= boundary:
        return boundary, True
    return proposed_ms, False
