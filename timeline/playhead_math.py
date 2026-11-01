"""Conversión y detección del cabezal (sin dependencias Qt)."""

def playhead_time(scene_x, header, pixels_per_second, duration_ms):
    if pixels_per_second<=0:
        raise ValueError("pixels_per_second debe ser positivo")
    milliseconds=round((scene_x-header)/pixels_per_second*1000)
    return max(0,min(milliseconds,max(0,int(duration_ms))))


def hit_playhead(pointer_x, playhead_x, tolerance=9):
    return abs(pointer_x-playhead_x)<=tolerance
