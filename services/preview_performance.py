"""Política de previsualización adaptable, sin dependencia de Qt.

Limitamos trabajo por fotograma para priorizar respuesta del monitor.
La resolución elegida NUNCA modifica archivos fuente ni exportaciones.
"""


class AdaptivePreview:
    LEVEL_WIDTHS = (960, 720, 480)

    def __init__(self):
        self.level = 0
        self._slow = 0
        self._fast = 0

    def observe(self, duration_ms):
        """Degradación rápida ante sobrecarga, recuperación conservadora."""
        ms = max(0.0, float(duration_ms))
        if ms >= 55:
            self._slow += 1
            self._fast = 0
            if self._slow >= 2 and self.level < 2:
                self.level += 1
                self._slow = 0
        elif ms <= 21:
            self._fast += 1
            self._slow = 0
            if self._fast >= 24 and self.level > 0:
                self.level -= 1
                self._fast = 0
        else:
            self._slow = 0
            self._fast = 0
        return self.level

    def size(self, viewport_width, viewport_height):
        """Lienzo 16:9, múltiplos de 16; evita render a más píxeles que la vista."""
        available = min(self.LEVEL_WIDTHS[self.level],
                        max(1, int(viewport_width)),
                        max(1, int(viewport_height * 16 / 9)))
        width = max(160, int(available) // 16 * 16)
        return width, width * 9 // 16

    def reset(self):
        self._slow = 0
        self._fast = 0


def is_discontinuous(old_ms, new_ms, threshold_ms=550):
    """Salto de posición suficientemente grande para invalidar frames anteriores."""
    return old_ms is not None and abs(int(new_ms) - int(old_ms)) > threshold_ms


def timeline_frame_cache_key(path, frame_index, width, max_height=None):
    """La identidad depende del archivo (proxy incluido), del frame y de escala."""
    return (str(path), int(frame_index), int(width), max_height if max_height is None else int(max_height))


# Máximo de fotogramas por segundo que el monitor convierte a imagen.
# La conversión QVideoFrame -> QImage ocurre en el hilo de la interfaz:
# limitarla mantiene la ventana fluida a cualquier velocidad de clip.
FRAME_INTERVAL_MS = 33


def frame_delay_ms(now_s, last_convert_s, interval_ms=FRAME_INTERVAL_MS):
    """Milisegundos que esperar antes de convertir el siguiente fotograma.

    0 si ya pasó el intervalo (un fotograma suelto al pausar o buscar se
    muestra de inmediato); si no, lo que falta para completarlo.
    """
    elapsed_ms = max(0.0, (now_s - last_convert_s) * 1000.0)
    return int(max(0.0, interval_ms - elapsed_ms))
