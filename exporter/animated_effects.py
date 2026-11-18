"""Expresiones temporales FFmpeg para zoom y máscaras animadas.

Los fotogramas clave están guardados en tiempo FUENTE (ms). FFmpeg recibe
fotogramas desde el comienzo de cada clip recortado, por lo que convertimos
la marca al tiempo LOCAL de la Timeline (teniendo en cuenta la velocidad).
"""
from math import isfinite
from effects.model import merged_effects


def n(value):
    return f'{float(value):.7f}'.rstrip('0').rstrip('.') or '0'


def local_keys(clip, effect, names):
    speed = float(clip.get('speed', 1))
    source_start = float(clip.get('in_ms', 0))
    duration_s = float(clip['duration_ms']) / 1000
    raw = effect.get('keys', []) or []
    if not raw:
        raw = [dict(time_ms=source_start, **{key: effect[key] for key in names})]
    pts = []
    for key in raw:
        if not isinstance(key, dict) or any(p not in key for p in names):
            continue
        ts = (float(key['time_ms']) - source_start) / speed / 1000
        if not isfinite(ts):
            continue
        pts.append((max(0., min(duration_s, ts)), {p: float(key[p]) for p in names}))
    pts.sort(key=lambda pair:pair[0])
    # Límites: los valores antes y después del rango se interpolan en la fuente.
    from effects.model import interpolate_keys
    actual=[]
    for ts in (0.,duration_s):
        source_ms=source_start+ts*speed*1000
        actual.append((ts,interpolate_keys(raw, source_ms, names, effect)))
    actual.extend((ts,v) for ts,v in pts if 0 < ts < duration_s)
    return sorted(actual,key=lambda item:item[0])


def piecewise(keys, prop, var='T'):
    """Expresión AVExpr de interpolación lineal, sin eval de Python."""
    if not keys:
        raise ValueError('Se requieren fotogramas clave')
    if len(keys)==1:
        return n(keys[0][1][prop])
    last = n(keys[-1][1][prop])
    for left,right in reversed(list(zip(keys,keys[1:]))):
        t0, t1 = left[0],right[0]
        a,b=left[1][prop],right[1][prop]
        if t1 - t0 < .00001:
            expr = n(b)
        elif abs(a-b)<1e-9:
            expr = n(a)
        else:
            expr = f'({n(a)}+({n(b-a)})*({var}-{n(t0)})/{n(t1-t0)})'
        last = f'if(lte({var}\\,{n(t1)})\\,{expr}\\,{last})'
    return last


def zoompan_filter(clip,fx,profile):
    fx=merged_effects(fx)['zoom']
    keys=local_keys(clip,fx,('scale','cx','cy'))
    z=piecewise(keys,'scale',var='in_time')
    x=piecewise(keys,'cx',var='in_time')
    y=piecewise(keys,'cy',var='in_time')
    # Para los clips que cambian velocidad, in_time ya refleja el tiempo de la Timeline.
    return (f"zoompan=z='{z}':x='max(0\\,min(iw-iw/zoom\\,({x})*iw-iw/zoom/2))':"
            f"y='max(0\\,min(ih-ih/zoom\\,({y})*ih-ih/zoom/2))':"
            f'd=1:s={profile.width}x{profile.height}:fps={profile.fps}')


def mask_geq(clip,fx,profile):
    """Máscara gris por fotograma: 255 dentro del ROI y 0 fuera.

    Geq evalúa X/Y/T sobre fotogramas de la secuencia. Feather produce
    transición suavizada en bordes con la misma definición normalizada de UI.
    """
    fx=merged_effects(fx)['censor']
    base = dict(fx['mask'])
    keys=local_keys(clip,{'keys':fx.get('keys',[]),**base},('x','y','w','h'))
    x=f'({piecewise(keys,"x")})*{profile.width}'
    y=f'({piecewise(keys,"y")})*{profile.height}'
    w=f'({piecewise(keys,"w")})*{profile.width}'
    h=f'({piecewise(keys,"h")})*{profile.height}'
    feather = min(profile.width,profile.height)*max(0,float(fx.get('feather',0)))
    # 4 distancias interiores, negativo fuera de la máscara.
    distances=(f'min(min(X-({x})\\,({x})+({w})-X)\\,'
               f'min(Y-({y})\\,({y})+({h})-Y))')
    if feather>.001:
        # Cero en los bordes; 1 después de una distancia feather.
        return f'255*clip(({distances})/{n(feather)}\\,0\\,1)'
    return f'255*gte({distances}\\,0)'
