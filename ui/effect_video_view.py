"""Monitor de video con efectos activos durante Play y máscara editable.

Pillow trabaja fuera del hilo gráfico; si no alcanza la tasa de cuadros,
se descartan fotogramas obsoletos en lugar de congelar Qt.
"""
from copy import deepcopy
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QPainter, QPen, QColor, QImage
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QVideoSink
from effects.model import merged_effects, censor_mask, valid_mask
from effects.renderer import render_frame

try:
    from PIL import Image
except ImportError:
    Image = None


class _RenderSignals(QObject):
    finished = Signal(object, object)


class _RenderTask(QRunnable):
    """Sólo usa QImage/Pillow; no accede a QWidget/QPixmap desde el worker."""
    def __init__(self, image, effects, source_ms, key, signals):
        super().__init__()
        self.image=image
        self.effects=effects
        self.source_ms=source_ms
        self.key=key
        self.signals=signals

    def run(self):
        processed = QImage()
        try:
            rgb=self.image.convertToFormat(QImage.Format.Format_RGB888)
            bitmap=Image.frombytes('RGB', (rgb.width(),rgb.height()),
                                   bytes(rgb.bits()), 'raw', 'RGB',rgb.bytesPerLine(),1)
            result=render_frame(bitmap,self.effects,self.source_ms,960)
            data=result.tobytes()
            processed=QImage(data,result.width,result.height,
                             result.width*3,QImage.Format.Format_RGB888).copy()
        except Exception:
            # La señal se usa incluso en error para desbloquear el siguiente frame.
            processed=QImage()
        self.signals.finished.emit(self.key,processed)


class EffectVideoView(QWidget):
    maskCommitted = Signal(str, object)  # clip_id, rect normalizado
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320,180)
        self.setMouseTracking(True)
        self.setStyleSheet('background:#07090d')
        self.video_sink=QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self._new_frame)
        self._frame=QImage()
        self._frame_serial=0
        self._cached=None
        self._cache_key=None
        self._cached_clip=None
        self._rendering=False
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

    def clear_frame(self):
        """Los huecos de la Timeline muestran negro, no el último frame."""
        if not self._frame.isNull():
            self._frame=QImage()
            self._frame_serial+=1
            self._cached=None
            self._cached_clip=None
            self._cache_key=None
            self.update()

    def _new_frame(self, frame):
        if not frame.isValid():return
        image=frame.toImage()
        if image.isNull():return
        self._frame=image
        self._frame_serial+=1
        self._cache_key=None
        self.update()

    def set_active_clip(self, clip_id, effects=None, source_ms=0, fade_alpha=1.0):
        if (self._clip_id==clip_id and self._effects==(effects or {})
                and abs(self._source_ms-source_ms)<15
                and abs(self._fade_alpha-fade_alpha)<.0001):
            return
        if self._clip_id != clip_id:
            self._drag = None
            self._preview_mask = None
            self.unsetCursor()
        if self._clip_id!=clip_id or abs(self._source_ms-source_ms)>500:
            self._cached=None
            self._cached_clip=None
        self._clip_id=clip_id
        self._effects=deepcopy(effects or {})
        self._source_ms=max(0,int(source_ms))
        self._fade_alpha=max(0.0,min(1.0,float(fade_alpha)))
        self._cache_key=None
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
        if self._frame.isNull():return QRectF()
        fw=max(1,self._frame.width());fh=max(1,self._frame.height())
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
                repr(self._preview_mask),self._source_ms)

    def _effect_image(self):
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
            # Reducir en hilo GUI evita transferir muchos MB a cada worker.
            image=self._frame
            if image.width()>960:
                image=image.scaledToWidth(960,Qt.TransformationMode.FastTransformation)
            self._rendering=True
            task=_RenderTask(image.copy(),fx,self._source_ms,key,self._signals)
            self._pool.start(task)
        # Mostrar último fotograma procesado (mismo clip) mientras llega otro.
        if self._cached is not None and self._cached_clip==self._clip_id:
            return self._cached
        return self._frame

    def _render_done(self,key,image):
        self._rendering=False
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
                    key[4]==now_key[4] and abs(key[5]-now_key[5])<=500)
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
        if self._frame.isNull():return
        target=self._video_rect()
        img=self._effect_image()
        painter.setOpacity(self._fade_alpha)
        painter.drawImage(target,img)
        painter.setOpacity(1.0)
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
        if not (self._edit_mask and self._clip_id and
                event.button()==Qt.MouseButton.LeftButton):return
        hit=self._hit_mask(event.position())
        if hit:
            self._drag=(hit,event.position(),censor_mask(self._effects,self._source_ms))
            self._preview_mask=dict(self._drag[2])
            event.accept()

    def mouseMoveEvent(self,event):
        if self._drag is None:
            if self._edit_mask and self._hit_mask(event.position()):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
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
            # Mantener el borde opuesto inmóvil y un mínimo arrastrable.
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
        if self._drag is not None and event.button()==Qt.MouseButton.LeftButton:
            result=self._preview_mask
            self._drag=None
            self._preview_mask=None
            self._cache_key=None
            if result is not None and self._clip_id is not None:
                self.maskCommitted.emit(self._clip_id,result)
            self.update()
            event.accept()
