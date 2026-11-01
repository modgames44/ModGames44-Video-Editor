"""Posición de fotograma para una tira de miniaturas independiente del playhead."""


def thumbnail_source_time(clip, x_pixels, cell_width, pixels_per_second):
    if pixels_per_second <= 0:
        raise ValueError('Zoom inválido')
    duration = max(1, clip['duration_ms'])
    # El fotograma representa el CENTRO de la celda visible, y cambia al zoom.
    local_ms = max(0,min(duration-1,
               (max(0,x_pixels)+cell_width/2)*1000/pixels_per_second))
    return max(0,clip.get('in_ms',0)+local_ms*float(clip.get('speed',1)))
