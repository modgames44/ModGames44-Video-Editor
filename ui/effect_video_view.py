"""Monitor de video con efectos activos durante Play y máscara editable.

Pillow trabaja fuera del hilo gráfico; si no alcanza la tasa de cuadros,
se descartan fotogramas obsoletos en lugar de congelar Qt.
"""
from copy import deepcopy
from time import monotonic
from services.preview_performance import AdaptivePreview, is_discontinuous, frame_delay_ms
from PySide6.QtCore import Qt, QRectF, Signal, QObject, QRunnable, QThreadPool, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QImage
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QVideoSink
from effects.model import merged_effects, censor_mask, valid_mask
from effects.renderer import render_frame
from core.error_log import get_logger, exception_throttled

_log = get_logger('monitor')

try:
    from PIL import Image
except ImportError:
    Image = None


class _RenderSignals(QObject):
    finished = Signal(object, object)


class _RenderTask(QRunnable):
    """Sólo usa QImage/Pillow; no accede a QWidget/QPixmap desde el worker."""
    def __init__(self, image, effects, source_ms, key, signals, max_size):
        super().__init__()
        self.image=image
        self.effects=effects
        self.source_ms=source_ms
        self.key=key
        self.signals=signals
        self.max_size=max_size

    def run(self):
        processed = QImage()
        try:
            if (self.image.width()>self.max_size[0] or
                    self.image.height()>self.max_size[1]):
                scaled=self.image.scaled(self.max_size[0],self.max_size[1],
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation)
            else:
                scaled=self.image
            rgb=scaled.convertToFormat(QImage.Format.Format_RGB888)
            bitmap=Image.frombytes('RGB', (rgb.width(),rgb.height()),
                                   bytes(rgb.bits()), 'raw', 'RGB',rgb.bytesPerLine(),1)
            result=render_frame(bitmap,self.effects,self.source_ms,self.max_size[0])
            data=result.tobytes()
            processed=QImage(data,result.width,result.height,
                             result.width*3,QImage.Format.Format_RGB888).copy()
        except Exception:  # noqa: BLE001 - nunca bloquear el monitor
            # La señal se usa incluso en error para desbloquear el siguiente frame.
            exception_throttled(_log,'effects','Error aplicando efectos en el monitor')
            processed=QImage()
        self.signals.finished.emit(self.key,processed)


class _CompositionTask(QRunnable):
    """Decodifica todas las capas fuera del hilo gráfico."""
    def __init__(self,clips,position,reader,signals,key,size):
        super().__init__()
        self.clips=clips
        self.position=position
        self.reader=reader
        self.signals=signals
        self.key=key
        self.size=size

    def run(self):
        image=QImage()
        try:
            from effects.compositor import composite_frame
            frame=composite_frame(self.clips,self.position,self.size,self.reader)
            data=frame.tobytes()
            image=QImage(data,frame.width,frame.height,frame.width*3,
                         QImage.Format.Format_RGB888).copy()
        except Exception:  # noqa: BLE001 - nunca bloquear el monitor
            exception_throttled(_log,'composition','Error componiendo capas de video en el monitor')
        self.signals.finished.emit(self.key,image)


class EffectVideoView(QWidget):
    maskCommitted = Signal(str, object)  # clip_id, rect normalizado
    overlaySelected = Signal(str)  # título/imagen pulsado sobre el monitor
    overlayTransformCommitted = Signal(str, object)  # clip_id, x/y/scale normalizados
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320,180)
        self.setMouseTracking(True)
        self.setStyleSheet('background:#07090d')
        self.video_sink=QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self._new_frame)
        # Sólo se convierte el ÚLTIMO fotograma recibido, como mucho cada
        # FRAME_INTERVAL_MS. Antes se convertía cada fotograma en el hilo de
        # la interfaz: a 4× o 16× eran cientos por segundo y la ventana se
        # colgaba o se cerraba.
        self._latest_video_frame=None
        self._last_frame_convert=0.0
        self._frame_timer=QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.timeout.connect(self._consume_frame)
        self._frame=QImage()
        self._frame_serial=0
        self._cached=None
        self._cache_key=None
        self._cached_clip=None
        self._rendering=False
        self._render_started=0.0
        self._effect_budget=AdaptivePreview()
        self._effect_revision=0
        self._composition_budget=AdaptivePreview()
        self._pool=QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._signals=_RenderSignals(self)
        self._signals.finished.connect(self._render_done)
        self._clip_id=None
        self._effects={}
        self._source_ms=0
        self._fade_alpha=1.0
        self._edit_mask=False
        self._drag=None
        self._preview_mask=None
        self._composition_layers=None
        self._composition_frame=QImage()
        self._composition_key=None
        self._composition_busy=False
        self._composition_signals=_RenderSignals(self)
        self._composition_signals.finished.connect(self._composition_ready)
        self._composition_pool=QThreadPool(self)
        self._composition_pool.setMaxThreadCount(1)
        from services.video_frames import FrameReader
        self._composition_reader=FrameReader()
        self._composition_latest=0
        self._composition_last_request=-100000
        self._composition_last_size=None
        self._composition_signature=None
        self._composition_revision=0
        self._composition_started=0.0
        self._title_overlays=[]
        self._title_last_signature=None
        self._title_time=0
        self._title_pixmaps={}
        self._title_assets={}
        self._selected_overlay_id=None
        self._overlay_drag=None
        self._overlay_preview=None

    @staticmethod
    def _layers_signature(clips):
        # La huella incluye campos que cambian la imagen resultante.
        return tuple((c['id'],c.get('path'),c['start_ms'],c['duration_ms'],
                      c.get('in_ms'),c.get('speed'),c.get('track'),
                      repr(c.get('effects')),c.get('fade_in_ms'),
                      c.get('fade_out_ms'),repr(c.get('transition_in')))
                     for c in clips)

    def set_composition(self,clips,position_ms):
        """Solicitud coalescente: un trabajo activo + sólo el tiempo más reciente.

        Los saltos y cambios de efectos invalidan el frame anterior; en Play
        no hacemos un seek por cada tick ni formamos colas de tareas viejas.
        """
        if not clips or len(clips)<2:
            if self._composition_layers is not None:
                self._composition_revision+=1
                self._composition_layers=None
                self._composition_signature=None
                self._composition_frame=QImage()
                self._composition_key=None
                self._composition_last_request=-100000
                self._composition_last_size=None
                self.update()
            return
        position=int(position_ms)
        signature=self._layers_signature(clips)
        changed=signature!=self._composition_signature
        jumped=is_discontinuous(self._composition_latest,position) if self._composition_layers is not None else True
        self._composition_layers=clips
        self._composition_latest=position
        if changed or jumped:
            self._composition_revision+=1
            self._composition_signature=signature
            self._composition_frame=QImage()
            self._composition_key=None
            self._composition_last_request=-100000
            self._composition_last_size=None
            self.update()
        self._queue_composition()

    def _queue_composition(self):
        if self._composition_busy or self._composition_layers is None:
            return
        position=self._composition_latest
        # Evitar trabajo duplicado cuando el reloj avanza menos de un frame.
        if (self._composition_key is not None
                and self._composition_key[1]==position
                and self._composition_key[2]==self._composition_budget.size(self.width(),self.height())):
            return
        size=self._composition_budget.size(self.width(),self.height())
        if (self._composition_last_request>=0
                and abs(position-self._composition_last_request)<28
                and size==self._composition_last_size):
            return
        key=(self._composition_revision,position,size)
        self._composition_last_request=position
        self._composition_last_size=size
        self._composition_busy=True
        self._composition_started=monotonic()
        task=_CompositionTask(deepcopy(self._composition_layers),position,
                     self._composition_reader,self._composition_signals,key,size)
        self._composition_pool.start(task)

    def _composition_ready(self,key,image):
        duration=(monotonic()-self._composition_started)*1000
        self._composition_busy=False
        self._composition_budget.observe(duration)
        if self._composition_layers is None:
            return
        same_generation=key[0]==self._composition_revision
        if same_generation and not image.isNull():
            # Aceptar cuadros ligeramente retrasados durante Play, pero nunca
            # de otra búsqueda o composición (revision cambió en el seek).
            self._composition_frame=image
            self._composition_key=key
            self.update()
        if same_generation and abs(self._composition_latest-key[1])>=28:
            # Una única solicitud de recuperación, con el tiempo más reciente;
            # no queda esperando a otro tick cuando el usuario ya soltó Play.
            self._queue_composition()
        elif not same_generation:
            self._queue_composition()

    def invalidate_seek(self):
        """Invalida workers obsoletos al mover manualmente el cabezal.

        Los workers no pueden cancelarse en mitad de una llamada a FFmpeg,
        pero sus resultados jamás pisan el fotograma del nuevo destino.
        """
        self._effect_revision+=1
        self._composition_revision+=1
        self._latest_video_frame=None
        self._frame_timer.stop()
        self._cached=None
        self._cached_clip=None
        self._cache_key=None
        self._composition_frame=QImage()
        self._composition_key=None
        self._composition_last_request=-100000
        self._composition_last_size=None
        self.update()

    def set_title_overlays(self,clips,position_ms):
        from effects.title_overlay import active_titles
        selected=active_titles(clips,int(position_ms))
        # Sólo el hilo Qt accede a los clips: no copiar todos sus diccionarios
        # 30 veces por segundo. Las tareas de composición sí reciben copias.
        signature=tuple((c['id'],c.get('text'),c.get('path'),
                         repr(c.get('title_style')),repr(c.get('transform_keys')),
                         c['start_ms'],c['duration_ms'],c.get('fade_in_ms'),
                         c.get('fade_out_ms')) for c in selected)
        changed=signature!=self._title_last_signature
        self._title_last_signature=signature
        self._title_overlays=selected
        self._title_time=int(position_ms)
        animated=any(c.get('transform_keys') or c.get('fade_in_ms')
                     or c.get('fade_out_ms') or
                     (c.get('title_style') or {}).get('animation','estatico')!='estatico'
                     for c in selected)
        # Cuando no hay overlays animados, QVideoSink ya repinta cada frame.
        # Evitar un segundo repaint completo de la ventana sin necesidad.
        if changed or animated:
            self.update()

    def set_selected_overlay(self,clip_id):
        if self._selected_overlay_id != clip_id:
            self._selected_overlay_id=clip_id
            self.update()

    def _overlay_area(self):
        """Lienzo real de exportación 16:9, incluso con medios verticales."""
        ratio=16/9
        width=min(float(self.width()),float(self.height())*ratio)
        height=width/ratio
        return QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)

    def _overlay_geometry(self,clip,target):
        from PySide6.QtGui import QPixmap
        from effects.title_overlay import render_title_png,default_style,transform_at
        from effects.image_overlay import render_image_png
        from timeline.fades import fade_factor
        try:
            if clip.get('kind')=='image':
                from pathlib import Path
                original=Path(clip['path'])
                info=original.stat()
                signature=('image',str(original),info.st_size,info.st_mtime_ns)
                entry=self._title_assets.get(clip['id'])
                if entry is not None and entry[0]==signature:
                    path=entry[1]
                else:
                    path,_=render_image_png(clip,960,540)
                    if len(self._title_assets)>80:self._title_assets.clear()
                    self._title_assets[clip['id']]=(signature,path)
            else:
                # No reabrir el mismo archivo PNG de título en cada paint.
                signature=('title',clip.get('text',''),repr(clip.get('title_style')))
                entry=self._title_assets.get(clip['id'])
                if entry is not None and entry[0]==signature:
                    path=entry[1]
                else:
                    path,_=render_title_png(clip,960,540)
                    if len(self._title_assets)>80:self._title_assets.clear()
                    self._title_assets[clip['id']]=(signature,path)
        except (OSError,ValueError):
            return None
        key=str(path)
        pix=self._title_pixmaps.get(key)
        if pix is None:
            pix=QPixmap(key)
            if len(self._title_pixmaps)>80:self._title_pixmaps.clear()
            self._title_pixmaps[key]=pix
        if pix.isNull():return None
        style=default_style(clip)
        state=transform_at(clip,self._title_time)
        if self._overlay_preview and self._overlay_preview[0]==clip['id']:
            state.update(self._overlay_preview[1])
        scale=min(target.width()/960,target.height()/540)*state['scale']
        w,h=pix.width()*scale,pix.height()*scale
        x=target.x()+state['x']*target.width()
        default_y=.87 if style['position']=='bottom' else (.12 if style['position']=='top' else .5)
        y=target.y()+(state['y'] if clip.get('transform_keys') or clip.get('kind')=='image'
                      or self._overlay_preview and self._overlay_preview[0]==clip['id']
                      else default_y)*target.height()
        local=(self._title_time-clip['start_ms'])/1000
        opacity=state['opacity']*fade_factor(clip,self._title_time)
        if style['animation'] in ('aparecer','subir','deslizar'):
            opacity*=min(1,max(0,local/.30))
        if style['animation']=='subir':y+=max(0,.35-local)*target.height()*.4
        elif style['animation']=='deslizar':x-=max(0,.35-local)*target.width()
        return pix,x,y,w,h,state['rotation'],max(0,min(1,opacity))

    def _paint_titles(self,painter,target):
        if target.isEmpty():target=self._overlay_area()
        for clip in self._title_overlays:
            geometry=self._overlay_geometry(clip,target)
            if geometry is None:continue
            pix,x,y,w,h,angle,opacity=geometry
            painter.save()
            painter.setOpacity(opacity)
            painter.translate(x,y)
            painter.rotate(angle)
            rect=QRectF(-w/2,-h/2,w,h)
            painter.drawPixmap(rect,pix,QRectF(pix.rect()))
            painter.setOpacity(1)
            if self._selected_overlay_id==clip['id']:
                painter.setPen(QPen(QColor('#00d5fc'),2,Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
                painter.setBrush(QColor('#e5fbff'))
                painter.setPen(QPen(QColor('#00d5fc'),1))
                for cx,cy in ((rect.left(),rect.top()),(rect.right(),rect.top()),
                              (rect.left(),rect.bottom()),(rect.right(),rect.bottom())):
                    painter.drawRect(QRectF(cx-4,cy-4,8,8))
            painter.restore()

    def _hit_overlay(self,pos):
        from effects.overlay_geometry import overlay_hit
        target=self._overlay_area()
        for clip in reversed(self._title_overlays):
            geometry=self._overlay_geometry(clip,target)
            if geometry is None:continue
            _,x,y,w,h,angle,opacity=geometry
            if opacity<=0.01 and self._selected_overlay_id!=clip['id']:continue
            hit=overlay_hit(pos.x(),pos.y(),x,y,w,h,angle)
            if hit:return clip,hit,(x,y,w,h)
        return None

    def clear_frame(self):
        """Los huecos de la Timeline muestran negro, no el último frame."""
        # Un fotograma pendiente de convertir no debe reaparecer en el hueco.
        self._latest_video_frame=None
        self._frame_timer.stop()
        if not self._frame.isNull():
            self._frame=QImage()
            self._frame_serial+=1
            self._cached=None
            self._cached_clip=None
            self._cache_key=None
            self.update()

    def _new_frame(self, frame):
        if not frame.isValid():return
        if self._composition_layers is not None:
            # El compositor ya genera la imagen final. Convertir además el
            # QVideoFrame 4K desperdicia CPU/memoria y provoca tirones.
            return
        # Guardar una referencia (barata) y programar la conversión.
        self._latest_video_frame=frame
        if not self._frame_timer.isActive():
            self._frame_timer.start(frame_delay_ms(monotonic(),self._last_frame_convert))

    def _consume_frame(self):
        frame,self._latest_video_frame=self._latest_video_frame,None
        if frame is None or not frame.isValid():return
        if self._composition_layers is not None:return
        self._last_frame_convert=monotonic()
        image=frame.toImage()
        if image.isNull():return
        self._frame=image
        self._frame_serial+=1
        self._cache_key=None
        self.update()

    def set_active_clip(self, clip_id, effects=None, source_ms=0, fade_alpha=1.0):
        effects=effects or {}
        fade_alpha=max(0.0,min(1.0,float(fade_alpha)))
        source_ms=max(0,int(source_ms))
        effects_changed=self._effects!=effects
        clip_changed=self._clip_id!=clip_id
        jumped=is_discontinuous(self._source_ms,source_ms) if not clip_changed else True
        if (not clip_changed and not effects_changed
                and abs(self._source_ms-source_ms)<15
                and abs(self._fade_alpha-fade_alpha)<.0001):
            return
        if clip_changed:
            self._drag=None
            self._preview_mask=None
            self.unsetCursor()
        if clip_changed or effects_changed or jumped:
            self._cached=None
            self._cached_clip=None
            self._cache_key=None
        self._clip_id=clip_id
        # Las propiedades suelen ser inmutables entre ticks: ahorrar deepcopy.
        if effects_changed:
            self._effects=deepcopy(effects)
        old_alpha=self._fade_alpha
        self._source_ms=source_ms
        self._fade_alpha=fade_alpha
        animated=any((effects.get(name) or {}).get('keys')
                     for name in ('zoom','censor'))
        if clip_changed or effects_changed or abs(old_alpha-fade_alpha)>.0001 or animated:
            self.update()

    def set_mask_editing(self, enabled):
        self._edit_mask = bool(enabled)
        # Cancelar operaciones pendientes: una máscara eliminada nunca debe
        # volver a guardarse cuando el mouse se suelte sobre el monitor.
        self._drag = None
        self._preview_mask = None
        self._cache_key = None
        if not self._edit_mask:
            self.unsetCursor()
        self.update()

    def _video_rect(self):
        frame=self._composition_frame if self._composition_layers is not None else self._frame
        if frame.isNull():return QRectF()
        fw=max(1,frame.width());fh=max(1,frame.height())
        scale=min(self.width()/fw,self.height()/fh)
        width=fw*scale;height=fh*scale
        return QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)

    def _screen_mask(self):
        area=self._video_rect()
        if area.isEmpty():return QRectF()
        mask=self._preview_mask or censor_mask(self._effects,self._source_ms)
        return QRectF(area.x()+mask['x']*area.width(),area.y()+mask['y']*area.height(),
                      mask['w']*area.width(),mask['h']*area.height())

    def _render_key(self,fx):
        # Solo los efectos con keyframes dependen del instante exacto.
        animation = bool(fx['zoom'].get('keys') or fx['censor'].get('keys'))
        time_key = self._source_ms//25 if animation else 0
        return (self._frame_serial,self._clip_id,repr(fx),time_key,
                repr(self._preview_mask),self._source_ms,
                self._effect_budget.size(self.width(),self.height()),
                self._effect_revision)

    def _effect_image(self):
        if self._composition_layers is not None:
            return self._composition_frame
        if not self._effects or Image is None:
            return self._frame
        fx=merged_effects(self._effects)
        if not any(fx[k]['enabled'] for k in ('zoom','censor','color')):
            return self._frame
        if self._preview_mask is not None:
            fx['censor']['mask']=dict(self._preview_mask)
            fx['censor']['keys']=[]
        key=self._render_key(fx)
        if key == self._cache_key and self._cached is not None:
            return self._cached
        if not self._rendering:
            # Escalar y procesar dentro del worker; pasar QImage con memoria
            # compartida (copy-on-write), sin duplicar un frame 4K en Qt.
            self._rendering=True
            self._render_started=monotonic()
            size=self._effect_budget.size(self.width(),self.height())
            task=_RenderTask(QImage(self._frame),fx,self._source_ms,key,self._signals,size)
            self._pool.start(task)
        # Mostrar último fotograma procesado (mismo clip) mientras llega otro.
        if self._cached is not None and self._cached_clip==self._clip_id:
            return self._cached
        return self._frame

    def _render_done(self,key,image):
        duration=(monotonic()-self._render_started)*1000
        self._rendering=False
        self._effect_budget.observe(duration)
        if self._frame.isNull():return
        current=merged_effects(self._effects)
        if self._preview_mask is not None:
            current['censor']['mask']=dict(self._preview_mask)
            current['censor']['keys']=[]
        now_key=self._render_key(current)
        # A 60 fps Qt recibe nuevos frames mientras Pillow procesa el anterior.
        # Aceptar un fotograma ligeramente retrasado evita que siempre se
        # descarte y que nunca aparezca el efecto en reproducción.
        compatible=(key[1]==now_key[1] and key[2]==now_key[2] and
                    key[4]==now_key[4] and key[7]==now_key[7] and
                    abs(key[5]-now_key[5])<=210)
        if compatible and not image.isNull():
            self._cache_key=key
            self._cached=image
            self._cached_clip=self._clip_id
        else:
            self._cache_key=None
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor('#07090d'))
        if ((self._composition_layers is not None and self._composition_frame.isNull())
                or (self._frame.isNull() and self._composition_frame.isNull())):
            self._paint_titles(painter,self._overlay_area())
            return
        target=self._video_rect()
        img=self._effect_image()
        painter.setOpacity(1.0 if self._composition_layers is not None else self._fade_alpha)
        if not img.isNull():
            painter.drawImage(target,img)
        painter.setOpacity(1.0)
        self._paint_titles(painter,self._overlay_area())
        if self._edit_mask and self._clip_id is not None:
            fx=merged_effects(self._effects)
            if fx['censor']['enabled']:
                box=self._screen_mask()
                painter.setPen(QPen(QColor('#ffd36b'),2,Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(box)
                painter.setPen(QPen(QColor('#15232e'),1))
                painter.setBrush(QColor('#fff0a8'))
                for pos in ((box.left(),box.top()),(box.right(),box.top()),
                            (box.left(),box.bottom()),(box.right(),box.bottom())):
                    painter.drawRect(QRectF(pos[0]-4,pos[1]-4,8,8))

    def _hit_mask(self,pos):
        box=self._screen_mask()
        if box.isEmpty():return None
        tolerance=12
        corners={'nw':box.topLeft(),'ne':box.topRight(),
                 'sw':box.bottomLeft(),'se':box.bottomRight()}
        for name,point in corners.items():
            if abs(pos.x()-point.x())<=tolerance and abs(pos.y()-point.y())<=tolerance:
                return name
        if box.contains(pos):return 'move'
        return None

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        # Al editar censura, sus manejadores tienen prioridad.
        if self._edit_mask and self._clip_id:
            hit=self._hit_mask(event.position())
            if hit:
                self._drag=(hit,event.position(),censor_mask(self._effects,self._source_ms))
                self._preview_mask=dict(self._drag[2])
                event.accept();return
        hit=self._hit_overlay(event.position())
        if hit is None:return
        from effects.title_overlay import transform_at
        clip,handle,(x,y,w,h)=hit
        state=transform_at(clip,self._title_time)
        self._overlay_drag=(clip['id'],handle,event.position(),state,(x,y),(w,h))
        self._selected_overlay_id=clip['id']
        self.overlaySelected.emit(clip['id'])
        self.update()
        event.accept()

    def mouseMoveEvent(self,event):
        if self._overlay_drag is not None:
            from effects.overlay_geometry import drag_overlay_transform
            clip_id,handle,origin,state,center,size=self._overlay_drag
            target=self._overlay_area()
            changed=drag_overlay_transform(state,handle,
                (origin.x(),origin.y()),(event.position().x(),event.position().y()),
                (target.width(),target.height()),center,size)
            self._overlay_preview=(clip_id,changed)
            self.update();event.accept();return
        if self._drag is None:
            if self._edit_mask and self._hit_mask(event.position()):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                hit=self._hit_overlay(event.position())
                if hit:
                    self.setCursor(Qt.CursorShape.SizeAllCursor if hit[1]=='move'
                                   else Qt.CursorShape.SizeFDiagCursor)
                else:self.unsetCursor()
            return
        hit,origin,original=self._drag
        area=self._video_rect()
        if area.isEmpty():return
        dx=(event.position().x()-origin.x())/area.width()
        dy=(event.position().y()-origin.y())/area.height()
        x,y,w,h=(original[key] for key in ('x','y','w','h'))
        if hit=='move':x+=dx;y+=dy
        else:
            if 'w' in hit:x+=dx;w-=dx
            if 'e' in hit:w+=dx
            if 'n' in hit:y+=dy;h-=dy
            if 's' in hit:h+=dy
        if hit!='move':
            if w<.025:
                if 'w' in hit:x-=(.025-w)
                w=.025
            if h<.025:
                if 'n' in hit:y-=(.025-h)
                h=.025
        self._preview_mask=valid_mask({'x':x,'y':y,'w':w,'h':h})
        self._cache_key=None
        self.update()
        event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        if self._overlay_drag is not None:
            clip_id,handle,_,state,_,_=self._overlay_drag
            result=self._overlay_preview[1] if self._overlay_preview else None
            self._overlay_drag=None
            self._overlay_preview=None
            if result is not None and any(abs(result[k]-state[k])>1e-5 for k in ('x','y','scale')):
                self.overlayTransformCommitted.emit(clip_id,
                    {key:result[key] for key in ('x','y','scale')})
            self.update();event.accept();return
        if self._drag is not None:
            result=self._preview_mask
            self._drag=None
            self._preview_mask=None
            self._cache_key=None
            if result is not None and self._clip_id is not None:
                self.maskCommitted.emit(self._clip_id,result)
            self.update();event.accept()
