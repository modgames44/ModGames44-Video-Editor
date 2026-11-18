"""Composición de V1/V2/V3 para previsualización, sin usar QWidget.

Cada capa se representa en la misma geometría que la exportación:
letterbox, efectos propios, máscara propia y desvanecimiento alfa por clip.
La capa superior tapa las anteriores; fades descubren las inferiores.
"""
from PIL import Image, ImageDraw
from timeline.model import source_position, end
from timeline.fades import fade_factor
from effects.renderer import render_frame
from services.video_frames import FrameReader


def active_layers(clips,timeline_ms):
    layers=[c for c in clips if c.get('kind')=='video'
            and c['start_ms']<=timeline_ms<end(c)]
    return sorted(layers,key=lambda c:(int(c.get('track',0)),float(c['start_ms']),c['id']))


def fit_frame(image,size):
    if image is None:return None
    w,h=size
    width,height=image.size
    scale=min(w/max(1,width),h/max(1,height))
    target=image.resize((max(1,round(width*scale)),max(1,round(height*scale))),
                        Image.Resampling.BILINEAR)
    layer=Image.new('RGB',size,'black')
    layer.paste(target,((w-target.width)//2,(h-target.height)//2))
    return layer


def composite_frame(clips,timeline_ms,size=(960,540),reader=None):
    if reader is None:reader=FrameReader()
    result=Image.new('RGB',size,(0,0,0))
    for c in active_layers(clips,timeline_ms):
        frame=reader.read(c['path'],source_position(c,timeline_ms),width=size[0],max_height=size[1])
        if frame is None:continue
        # Efectos sobre la imagen FUENTE (coordenadas normalizadas de la fuente,
        # igual que el monitor de un clip y la exportación) y después letterbox.
        processed=render_frame(frame,c.get('effects'),source_position(c,timeline_ms),
                               max_width=size[0])
        processed=fit_frame(processed,size)
        transition=c.get('transition_in') or {}
        kind=transition.get('kind')
        length=max(1,int(transition.get('duration_ms') or 1))
        if kind in ('wipe','slide'):
            progress=max(0,min(1,(timeline_ms-c['start_ms'])/length))
            if kind=='wipe':
                mask=Image.new('L',size,0)
                ImageDraw.Draw(mask).rectangle((0,0,max(0,round(size[0]*progress)),size[1]),fill=255)
                result=Image.composite(processed,result,mask)
            else:
                move=round(size[0]*(1-progress))
                result.paste(processed,(move,0))
            continue
        alpha=fade_factor(c,timeline_ms)
        if alpha>=.999:
            result=processed
        elif alpha>0:
            result=Image.blend(result,processed,alpha)
    return result
