"""Interpreta keyframes sin ejecutar código del proyecto del usuario."""
from math import isfinite


def sample(keys,local_ms,field,default):
    pairs=sorted((max(0,int(k['time_ms'])),float(k[field])) for k in keys if field in k)
    if not pairs:return float(default)
    if local_ms<=pairs[0][0]:return pairs[0][1]
    for (t1,v1),(t2,v2) in zip(pairs,pairs[1:]):
        if local_ms<=t2:return v2 if t1==t2 else v1+(v2-v1)*(local_ms-t1)/(t2-t1)
    return pairs[-1][1]


def ffmpeg_expression(keys,field,default,time='t',offset=0):
    """Expresión FFmpeg con comas escapadas. El tiempo se mide en segundos."""
    points=sorted((max(0,int(k['time_ms']))/1000, float(k[field])) for k in keys if field in k)
    if not points:return f'{float(default):.6f}'
    if any(not isfinite(v) for _,v in points):raise ValueError('Keyframe no finito')
    result=f'{points[-1][1]:.6f}'
    for (a,x),(b,y) in reversed(list(zip(points,points[1:]))):
        time_expr=f'({time}-{offset:.6f})' if offset else time
        if b<=a:continue
        interp=f'({x:.6f}+({y-x:.6f})*({time_expr}-{a:.6f})/{b-a:.6f})'
        result=f'if(lt({time_expr}\\,{b:.6f})\\,{interp}\\,{result})'
    t0,v0=points[0]
    if t0>0:
        time_expr=f'({time}-{offset:.6f})' if offset else time
        result=f'if(lt({time_expr}\\,{t0:.6f})\\,{v0:.6f}\\,{result})'
    return result
