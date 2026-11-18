"""Geometría independiente de Qt para interacción directa con superposiciones."""
from math import cos, hypot, radians, sin


def local_point(px, py, center_x, center_y, rotation_degrees=0):
    """Posición de pantalla convertida a coordenadas locales rotadas."""
    angle = radians(rotation_degrees)
    dx, dy = px - center_x, py - center_y
    return dx * cos(angle) + dy * sin(angle), -dx * sin(angle) + dy * cos(angle)


def overlay_hit(px, py, cx, cy, width, height, rotation=0, handle_px=10):
    """Identifica esquina de tamaño o interior; admite títulos e imágenes rotados."""
    if width <= 0 or height <= 0:
        return None
    x, y = local_point(px, py, cx, cy, rotation)
    for handle, hx, hy in (('nw', -width/2, -height/2), ('ne', width/2, -height/2),
                           ('sw', -width/2, height/2), ('se', width/2, height/2)):
        if abs(x-hx) <= handle_px and abs(y-hy) <= handle_px:
            return handle
    if abs(x) <= width/2 and abs(y) <= height/2:
        return 'move'
    return None


def drag_overlay_transform(initial, handle, origin, current, canvas_size, center, size):
    """Arrastrar: centro normalizado; esquinas: escala proporcional (sin deformación)."""
    x, y = origin
    u, v = current
    cw, ch = canvas_size
    if cw <= 0 or ch <= 0:
        return dict(initial)
    changed = dict(initial)
    if handle == 'move':
        changed['x'] = min(1., max(0., initial['x'] + (u-x)/cw))
        changed['y'] = min(1., max(0., initial['y'] + (v-y)/ch))
    else:
        cx, cy = center
        before = max(1., hypot(x-cx,y-cy))
        after = hypot(u-cx,v-cy)
        changed['scale'] = min(5., max(.15, initial['scale'] * after/before))
    return changed
