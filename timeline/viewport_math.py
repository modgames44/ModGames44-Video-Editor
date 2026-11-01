"""Geometría de navegación de la Timeline, sin depender de Qt.

Los valores son píxeles lógicos del viewport, no posiciones del archivo fuente.
En todo momento, los tiempos y longitudes del modelo permanecen intactos.
"""


def playhead_scene_x(position_ms, pixels_per_second, header=76):
    """Coordenada X del cabezal en la escena."""
    return float(header) + max(0, int(position_ms)) / 1000 * float(pixels_per_second)


def viewport_scroll_for_time(position_ms, scale, viewport_width, *,
                             alignment='end', header=76, current_scroll=0):
    """Scroll horizontal para encuadrar el cabezal, sin tocar el vertical.

    alignment='start' coloca 00:00 en la izquierda; 'end' deja el final
    cerca del borde derecho; 'center' centra el instante seleccionado.
    """
    if float(scale) <= 0 or int(viewport_width) <= 0:
        return max(0, round(current_scroll))
    if alignment == 'start' or int(position_ms) <= 0:
        return 0
    position_x = playhead_scene_x(position_ms, scale, header)
    usable_width = max(1, int(viewport_width) - int(header))
    if alignment == 'center':
        target_x = int(header) + usable_width / 2
    elif alignment == 'end':
        target_x = int(header) + usable_width * .88
    elif alignment == 'playback':
        target_x = int(header) + usable_width * .22
    else:
        raise ValueError('Alineación desconocida: ' + str(alignment))
    return max(0, round(position_x - target_x))


def needs_playback_follow(playhead_x_in_viewport, viewport_width, header=76):
    """Seguir la reproducción solo cuando sobrepasa la región visible."""
    width = max(1, int(viewport_width))
    if width <= header + 30:
        return False
    return playhead_x_in_viewport >= header + (width - header) * .92 or playhead_x_in_viewport < header


def timeline_scene_width(end_ms, scale, viewport_width, *, header=76,
                         future_seconds=45, minimum_seconds=20):
    """Ancho total con espacio editable DESPUÉS de la última toma.

    La cola es al menos una ventana y cuarto y 45 segundos a escala real;
    esto permite scroll, encuadrar el cabezal y soltar un nuevo clip incluso
    con zoom máximo. No cambia la duración real de la secuencia.
    """
    scale = max(.001, float(scale))
    viewport_width = max(1, int(viewport_width))
    content_seconds = max(float(end_ms) / 1000, float(minimum_seconds))
    tail_px = max(viewport_width * 1.25, float(future_seconds) * scale)
    return int(round(header + content_seconds * scale + tail_px))


def maximum_horizontal_scroll(scene_width, viewport_width):
    """Rango máximo teórico de scroll con escena sin transformaciones."""
    return max(0, round(float(scene_width)-max(1,int(viewport_width))))


def scroll_correction(actual_view_x, desired_view_x, current_scroll):
    """Corrección a partir del cabezal realmente proyectado por QGraphicsView."""
    return max(0, round(float(current_scroll) + float(actual_view_x) - float(desired_view_x)))


def minimum_scene_width_for_scroll(scroll_value, viewport_width, *, margin=64):
    """Límite inferior del ancho necesario para un scroll horizontal dado."""
    return max(1, round(max(0,float(scroll_value))+max(1,int(viewport_width))+margin))
