"""Seguimiento local de una zona rectangular para censura.

Usa OpenCV template matching para videos con movimiento moderado. No usa
servicios externos ni identifica personas. El resultado es EDITABLE: puntos
de control con formato idéntico a los fotogramas clave manuales del editor.
"""
from math import isfinite
from timeline.model import source_position,end
from effects.model import censor_mask


class TrackingError(RuntimeError):
    pass


def _compress(points,tolerance=.008,max_keys=72):
    if len(points)<=2:return points
    preserved={0,len(points)-1}
    def segment(a,b):
        if b-a<=1:return
        l,r=points[a],points[b]
        span=max(1,float(r['time_ms']-l['time_ms']))
        maximum=0
        index=None
        for k in range(a+1,b):
            ratio=(points[k]['time_ms']-l['time_ms'])/span
            error=max(abs(points[k][field]-(l[field]+ratio*(r[field]-l[field])))
                      for field in ('x','y','w','h'))
            if error>maximum:maximum,index=error,k
        if index is not None and maximum>tolerance:
            preserved.add(index)
            segment(a,index);segment(index,b)
    segment(0,len(points)-1)
    result=[points[i] for i in sorted(preserved)]
    if len(result)>max_keys:
        # Submuestreo uniforme: conserva el primer/último estado.
        indices=sorted(set(round(i*(len(result)-1)/(max_keys-1)) for i in range(max_keys)))
        result=[result[i] for i in indices]
    return result


def track_censor(clip,timeline_start_ms,max_seconds=20,cancel=None,progress=None):
    try:import cv2
    except ImportError as e:
        raise TrackingError('Instala opencv-python para activar el seguimiento') from e
    if clip.get('kind')!='video':raise TrackingError('Selecciona un clip de video')
    effects=clip.get('effects') or {}
    if not effects.get('censor',{}).get('enabled'):
        raise TrackingError('Aplica primero una máscara de desenfoque o mosaico')
    start=max(float(clip['start_ms']),min(float(timeline_start_ms),end(clip)-1))
    source_ms=source_position(clip,start)
    mask=censor_mask(effects,source_ms)
    capture=cv2.VideoCapture(clip['path'])
    if not capture.isOpened():raise TrackingError('No se pudo abrir el archivo de video')
    try:
        fps=capture.get(cv2.CAP_PROP_FPS)
        if not isfinite(fps) or fps<=0:fps=30
        step=max(1,round(fps/6))
        starting_frame=max(0,round(source_ms/1000*fps))
        capture.set(cv2.CAP_PROP_POS_FRAMES,starting_frame)
        ok,frame=capture.read()
        if not ok:raise TrackingError('No se pudo obtener el fotograma inicial')
        height,width=frame.shape[:2]
        bw=max(8,min(width,round(width*mask['w'])))
        bh=max(8,min(height,round(height*mask['h'])))
        x=max(0,min(width-bw,round(width*mask['x'])))
        y=max(0,min(height-bh,round(height*mask['y'])))
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        template=gray[y:y+bh,x:x+bw].copy()
        if float(template.std())<7:
            raise TrackingError('La región tiene poco contraste para seguirla automáticamente')
        points=[dict(time_ms=round(source_ms),x=x/width,y=y/height,w=bw/width,h=bh/height)]
        remaining_source_ms=min(max_seconds*1000*float(clip.get('speed',1)),
                                 (end(clip)-start)*float(clip.get('speed',1)))
        total_steps=max(1,round(remaining_source_ms/1000*fps/step))
        for number in range(1,total_steps+1):
            if cancel is not None and cancel.is_set():raise TrackingError('Seguimiento cancelado')
            for _ in range(step-1):
                if not capture.grab():break
            ok,frame=capture.read()
            if not ok:break
            gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            margin=max(18,int(max(bw,bh)*.55))
            x0=max(0,x-margin);x1=min(width,x+bw+margin)
            y0=max(0,y-margin);y1=min(height,y+bh+margin)
            search=gray[y0:y1,x0:x1]
            if search.shape[0]<bh or search.shape[1]<bw:break
            similarity=cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED)
            _,quality,_,location=cv2.minMaxLoc(similarity)
            if not isfinite(quality) or quality<.35:break
            x=x0+location[0];y=y0+location[1]
            new_template=gray[y:y+bh,x:x+bw]
            # No actualizar agresivamente la plantilla: evita deriva acumulada.
            template=cv2.addWeighted(template,.94,new_template,.06,0)
            instant=source_ms+1000*number*step/fps
            points.append(dict(time_ms=round(instant),x=x/width,y=y/height,
                               w=bw/width,h=bh/height))
            if progress:progress(min(100,round(number*100/total_steps)))
        if len(points)<2:raise TrackingError('No se pudo seguir el objeto; ajusta el recuadro e inténtalo de nuevo')
        return _compress(points)
    finally:
        capture.release()
