"""Geometría temporal de la Timeline. Independiente de PySide6 para pruebas."""
import math


def ruler_spacing(scale):
    """Marcas mayores adaptadas a la escala temporal, en segundos."""
    candidates=(.1,.2,.5,1,2,5,10,15,30,60,120,300,600,900,1800,3600,7200,14400)
    return next((interval for interval in candidates if interval*scale>=105),candidates[-1])


def format_ruler(seconds, interval):
    millis=round(seconds*1000)
    h, remainder=divmod(millis,3600000)
    m, remainder=divmod(remainder,60000)
    s, rest=divmod(remainder,1000)
    if interval<1:return f'{h:02}:{m:02}:{s:02}.{rest//100:01}'
    if h:return f'{h:02}:{m:02}:{s:02}'
    return f'{m:02}:{s:02}'


def zoom_scroll_value(scene_x, old_scale, new_scale, cursor_x, header=76):
    """Scroll necesario para conservar el mismo instante bajo cursor_x."""
    seconds=max(0,(scene_x-header)/old_scale)
    return max(0,round(header+seconds*new_scale-cursor_x))


def clamp_clip_start(milliseconds):
    """00:00 es la cota izquierda absoluta, no se desplaza el clip a negativo."""
    return max(0,round(milliseconds))
