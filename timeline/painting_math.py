"""Geometría del texto de clips, independiente de repintados parciales.

El cabezal de reproducción actualiza pequeñas franjas del viewport.
El texto debe tener la misma posición aunque cambie la franja repintada.
"""


def stable_visible_label(clip_scene_x, clip_width, viewport_left, viewport_right,
                         *, max_width=260, padding=5):
    """Devuelve (x_local, ancho) o None si no hay lugar suficiente.

    El ancla queda al inicio del tramo VISIBLE del clip y es independiente
    del área sucia que Qt entrega a QGraphicsItem.paint().
    """
    if clip_width <= 0 or viewport_right <= viewport_left:
        return None
    visible_left = max(0.0, float(viewport_left) - float(clip_scene_x))
    visible_right = min(float(clip_width), float(viewport_right) - float(clip_scene_x))
    if visible_right <= visible_left:
        return None
    x = visible_left + padding
    width = min(float(max_width), visible_right - x - padding)
    if width < 12:
        return None
    return x, width
