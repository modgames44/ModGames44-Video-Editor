"""Timeline multipista de Qt: tiempo absoluto, zoom alrededor del cursor,
miniaturas reales y formas de onda PCM L/R multirresolución.

Las operaciones de edición siguen en milisegundos, sin cambios en los medios.
"""
import copy
import math
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QRect, QEvent, QTimer
from PySide6.QtGui import QColor, QBrush, QPen, QPainter, QCursor, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem,
    QGraphicsTextItem, QMenu, QSlider, QCheckBox,
)

from timeline.model import make_clip, end, close_gap, source_position
from timeline.editing import split_at, trim_bounds, trim_linked, remove_linked, unlink
from timeline.history import History
from timeline.zoom_math import ruler_spacing, format_ruler, zoom_scroll_value, clamp_clip_start
from timeline.playhead_math import playhead_time, hit_playhead
from timeline.thumbnail_math import thumbnail_source_time
from timeline.painting_math import stable_visible_label
from timeline.fades import fade_durations, fade_factor, clamp_fades, change_fade
from timeline.track_layout import TRACK_LABELS, row_for_clip, track_for_row
from timeline.viewport_math import (playhead_scene_x, viewport_scroll_for_time,
                                    needs_playback_follow, timeline_scene_width, scroll_correction,
                                    minimum_scene_width_for_scroll)
from services.media_probe import probe
from services.media_visuals import VisualCache
from ui.tools_panel import ICON_DIR
from effects.model import merged_effects, add_keyframe, change_speed, valid_mask
from effects.audio import validated_audio_effects
from services.waveform import needs_processed_waveform, waveform_gain_linear

PX_SEC = 70
HEADER = 76
RULER_H = 32
MIN_ZOOM = 5
MAX_ZOOM = 700
MIN_TRACK_HEIGHT = 42
MAX_TRACK_HEIGHT = 280




class ClipItem(QGraphicsRectItem):
    def __init__(self,panel,clip):
        self.panel=panel
        self.clip_id=clip['id']
        self.kind=clip.get('kind','video')
        row=panel.row_of(clip)
        super().__init__(0,0,max(1,clip['duration_ms']/1000*panel.scale),panel.track_heights[row]-7)
        self.setBrush(QBrush(QColor('#075a87' if self.kind=='video' else '#075a57')))
        self.setPen(QPen(QColor('#22c5e9')))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption)
        self.setPos(HEADER+clip['start_ms']/1000*panel.scale,panel.row_y(row)+3)
        self.old=None
        self._trim_side=None
        self._trim_origin=None
        self._trim_delta_ms=0
        self._fade_side=None
        self._fade_start_ms=0
        self._fade_preview_ms=None
        self._fade_anchor=0.0
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{Path(clip['path']).name}\n{self.kind.upper()} | {clip['duration_ms']/1000:.2f} s | {clip.get('speed',1):.2f}×")

    def paint(self,painter,option,widget=None):
        """Pintar el clip sin heredar pinceles de los manejadores de fade.

        El brush amarillo de los triángulos podía contaminar el fondo de V1.
        Dibujar explícitamente la base elimina ese acoplamiento accidental.
        """
        clip=self.panel.get_clip(self.clip_id)
        if clip is None:
            return
        r=self.rect()
        painter.save()
        painter.setClipRect(r.adjusted(1,1,-1,-1))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.fillRect(r, QColor('#075a87' if self.kind=='video' else '#075a57'))
        painter.setPen(QPen(QColor('#22c5e9'), 1))
        painter.drawRect(r.adjusted(0.5,0.5,-0.5,-0.5))
        # Sólo dibujar el tramo visible: clips de horas no generan millones de dibujos.
        exposed=option.exposedRect
        left=max(1,int(exposed.left())-2)
        right=min(int(r.width())-1,int(exposed.right())+3)
        if right>left:
            if self.kind=='audio':self._draw_audio(painter,clip,r,left,right)
            else:self._draw_video(painter,clip,r,left,right)
        # IMPORTANTE: el texto NO puede depender de option.exposedRect ni de
        # «left». Qt solo repinta una banda estrecha bajo el cabezal cada tick.
        # Anclar el nombre a esa banda provocaba letras repetidas al reproducir,
        # mover el cabezal o utilizar la cuchilla.
        label = self._stable_label(max_width=260)
        if label is not None:
            label_x, label_width = label
            metrics = painter.fontMetrics()
            title = Path(clip['path']).name
            if self.kind == 'audio':
                fx = validated_audio_effects(clip.get('audio_fx'))
                if (fx['volume_db'] or fx['noise'] or fx['normalize'] or
                        fx['voice'] != 'none'):
                    title += '  · FX'
            filename = metrics.elidedText(
                title, Qt.TextElideMode.ElideRight, int(label_width))
            if filename:
                painter.fillRect(QRectF(label_x-3, 1, label_width+6, 18),
                                 QColor(6,34,50,225))
                painter.setPen(QColor('#edf6fb'))
                painter.drawText(QRectF(label_x,1,label_width,17),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 filename)
        self._draw_fades(painter, clip, r)
        if self.isSelected():
            painter.setPen(QPen(QColor('#e6f4fb'),2))
            painter.drawRect(r.adjusted(1,1,-1,-1))
        painter.restore()

    def _draw_fades(self, painter, clip, rect):
        """Puntos superiores + curva de fade; siempre en coordenadas LOCALES.

        No usar option.exposedRect: así el cabezal no deja rastros visuales.
        """
        fi, fo = fade_durations(clip)
        if self._fade_side == 'in':
            fi = self._fade_preview_ms
        elif self._fade_side == 'out':
            fo = self._fade_preview_ms
        width = rect.width()
        in_x = min(width, fi/1000*self.panel.scale)
        out_x = max(0, width-fo/1000*self.panel.scale)
        height = rect.height()
        painter.save()  # El amarillo sólo puede existir dentro del dibujo de fades.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#f7c56b'), 1.5))
        ytop = 5
        ybottom = max(ytop+4, height-5)
        if fi > 0:
            painter.drawLine(QPointF(0,ybottom),QPointF(in_x,ytop))
        if fo > 0:
            painter.drawLine(QPointF(out_x,ytop),QPointF(width,ybottom))
        painter.setBrush(QColor('#ffd477'))
        painter.setPen(QPen(QColor('#172335'),1))
        # Los triángulos se agarran en la esquina de entrada/salida; cuando
        # hay fade, el extremo amarillo también indica su duración.
        for x,side in ((in_x,'in'),(out_x,'out')):
            if side == 'in':
                pts=[QPointF(x,3),QPointF(x+9,3),QPointF(x,12)]
            else:
                pts=[QPointF(x,3),QPointF(x-9,3),QPointF(x,12)]
            painter.drawPolygon(QPolygonF(pts))
        painter.restore()  # No contaminar fondo, miniaturas ni ondas.

    def _fade_handle(self, pos):
        """Zona superior de la esquina o del límite de fade; no confundir con trim."""
        if self.panel.tool != 'select' or pos.y() > 15:
            return None
        clip = self.panel.get_clip(self.clip_id)
        if clip is None:
            return None
        fi, fo=fade_durations(clip)
        left=fi/1000*self.panel.scale
        right=self.rect().width()-fo/1000*self.panel.scale
        tolerance=12
        if abs(pos.x()-left)<=tolerance or (fi==0 and pos.x()<=tolerance):
            return 'in'
        if abs(pos.x()-right)<=tolerance or (fo==0 and pos.x()>=self.rect().width()-tolerance):
            return 'out'
        return None

    def _stable_label(self, max_width=260):
        """Posición del texto estable entre repintados parciales del cabezal.

        Depende solo de la geometría del clip y del scroll del viewport;
        nunca de la región sucia (`option.exposedRect`) de Qt.
        """
        view = self.panel.view
        viewport_left = view.mapToScene(0, 0).x()
        viewport_right = view.mapToScene(view.viewport().width(), 0).x()
        return stable_visible_label(self.scenePos().x(), self.rect().width(),
                                    viewport_left, viewport_right, max_width=max_width)

    def _draw_video(self,painter,clip,r,left,right):
        cell=150
        img_top=21
        img_h=max(8,r.height()-img_top-3)
        first=max(0,left//cell)
        last=min(math.ceil(right/cell),first+64)
        cache=self.panel.visuals
        for idx in range(first,last):
            x=idx*cell+2
            if x>=r.width()-2:break
            # Cada celda consulta un MOMENTO DIFERENTE del archivo.
            # El muestreo central reduce imágenes repetidas en el borde de un corte.
            if x>=r.width():break
            # Cada celda tiene un instante fuente propio. El cabezal NO tiene
            # que modificar la tira estática durante Play, igual que Premiere.
            source_ms=thumbnail_source_time(clip,x,min(cell,r.width()-x),self.panel.scale)
            key=cache.frame_key(clip['path'],source_ms)
            img=cache.frames.get(key)
            if img is None:
                cache.request_frame(clip['path'],source_ms)
            # Mientras se decodifican los distintos fotogramas, mostrar una
            # miniatura provisional del medio (no una franja amarilla).
            # En cuanto llega el fotograma correcto, el caché lo sustituye.
            if img is None or img.isNull():
                img=cache.images.get(clip['path'])
            image_rect=QRectF(x,img_top,max(1,min(cell-3,r.width()-x-2)),img_h)
            if img is not None and not img.isNull():
                painter.drawImage(image_rect,img)
            else:
                painter.fillRect(image_rect,QColor('#162a3e'))
                if idx == first:
                    painter.setPen(QColor('#9fb9c9'))
                    painter.drawText(image_rect, Qt.AlignmentFlag.AlignCenter,
                                     'Generando fotogramas...')

    def _draw_audio(self,painter,clip,r,left,right):
        top=21
        available=max(8,r.height()-top-2)
        mid1=top+available*0.25
        mid2=top+available*0.75
        half=max(2,available*0.245)
        painter.setPen(QPen(QColor('#3c988e'),1))
        painter.drawLine(QPointF(left,mid1),QPointF(right,mid1))
        painter.drawLine(QPointF(left,mid2),QPointF(right,mid2))
        # Igual que el nombre: etiquetas fijas respecto al viewport, nunca
        # respecto a la franja de repintado parcial del playhead.
        channel_label = self._stable_label(max_width=18)
        if channel_label is not None:
            channel_x, _ = channel_label
            painter.setPen(QColor('#b2dfec'))
            painter.drawText(QPointF(channel_x,mid1-half+11),'L')
            painter.drawText(QPointF(channel_x,mid2-half+11),'R')
        raw_wave=self.panel.visuals.waves.get(clip['path'])
        if raw_wave is None:return
        fx=validated_audio_effects(clip.get('audio_fx'))
        wave=raw_wave
        processed=False
        if self.panel.show_processed_waves and needs_processed_waveform(fx):
            ready=self.panel.visuals.request_effect_wave(clip['path'],fx)
            if ready is not None:
                wave=ready
                processed=True
        start_ms=clip.get('in_ms',0)+left/self.panel.scale*1000*float(clip.get('speed',1.))
        end_ms=clip.get('in_ms',0)+right/self.panel.scale*1000*float(clip.get('speed',1.))
        peaks=wave.peaks(start_ms,end_ms,right-left)
        painter.setPen(QPen(QColor('#33e2b9' if self.panel.show_processed_waves else '#6daea4'),1))
        # Misma escala de visualización para original/procesado, nunca
        # autonormalizar cada una por separado (ocultaría cambios de volumen).
        gain=raw_wave.display_gain
        if self.panel.show_processed_waves and not processed:
            gain *= waveform_gain_linear(fx['volume_db'])
        for col, values in enumerate(peaks):
            x=left+col
            for ch,mid in ((0,mid1),(1,mid2)):
                low,high=values[ch]
                center_timeline_ms=clip['start_ms']+(x+0.5)/self.panel.scale*1000
                envelope=fade_factor(clip,center_timeline_ms)
                y1=mid-max(-half,min(half,float(high)*gain*envelope*half))
                y2=mid-max(-half,min(half,float(low)*gain*envelope*half))
                painter.drawLine(QPointF(x,y1),QPointF(x,y2))

    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() is not None:
            # Nunca permitir tiempo negativo. La posición del clip es la del modelo.
            return QPointF(max(HEADER,float(value.x())),float(value.y()))
        return super().itemChange(change,value)

    def _edge_under_pointer(self, local_x):
        """Seleccionar también permite recortar tirando de los bordes visibles."""
        if local_x <= 9:
            return 'inicio'
        if local_x >= self.rect().width()-9:
            return 'final'
        return None

    def hoverMoveEvent(self,event):
        if self._fade_handle(event.pos()):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self.setToolTip('Desvanecimiento: arrastra el triángulo para ajustar duración')
            event.accept()
            return
        mode=self.panel.tool
        if mode in ('trim_start','trim_end') or (mode=='select' and self._edge_under_pointer(event.pos().x())):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif mode=='select':
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self,event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            fade_side=self._fade_handle(event.pos())
            if fade_side:
                clip=self.panel.get_clip(self.clip_id)
                self._fade_side=fade_side
                fi,fo=fade_durations(clip)
                self._fade_start_ms=fi if fade_side=='in' else fo
                self._fade_preview_ms=self._fade_start_ms
                self._fade_anchor=event.scenePos().x()
                self.setSelected(True)
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return
            mode=self.panel.tool
            side={'trim_start':'inicio','trim_end':'final'}.get(mode)
            if mode=='select':
                side=self._edge_under_pointer(event.pos().x())
            if side in ('inicio','final'):
                clip=next((c for c in self.panel.clips if c['id']==self.clip_id),None)
                if clip is not None:
                    self._trim_side=side
                    self._trim_origin=(self.pos(),self.rect())
                    self._trim_delta_ms=0
                    self._trim_anchor=event.scenePos().x()
                    self.setSelected(True)
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                    event.accept()
                    return
        self.old=self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._fade_side is not None:
            delta=round((event.scenePos().x()-self._fade_anchor)/self.panel.scale*1000)
            change=delta if self._fade_side=='in' else -delta
            clip=self.panel.get_clip(self.clip_id)
            fi,fo=fade_durations(clip)
            other=fo if self._fade_side=='in' else fi
            self._fade_preview_ms=max(0,min(clip['duration_ms']-other,self._fade_start_ms+change))
            self.update()
            event.accept()
            return
        if self._trim_side is not None:
            delta_ms=round((event.scenePos().x()-self._trim_anchor)/self.panel.scale*1000)
            delta_ms=self.panel.preview_trim_delta(self.clip_id,self._trim_side,delta_ms)
            self._trim_delta_ms=delta_ms
            old_pos,old_rect=self._trim_origin
            dx=self.panel.scale*delta_ms/1000
            if self._trim_side=='inicio':
                self.setPos(old_pos.x()+dx,old_pos.y())
                self.setRect(0,0,max(1,old_rect.width()-dx),old_rect.height())
            else:
                self.setRect(0,0,max(1,old_rect.width()+dx),old_rect.height())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self._fade_side is not None:
            side=self._fade_side
            ms=self._fade_preview_ms
            self._fade_side=None
            self._fade_preview_ms=None
            self.panel.set_clip_fade(self.clip_id,side,ms)
            event.accept()
            return
        if self._trim_side is not None:
            side=self._trim_side
            delta=self._trim_delta_ms
            self._trim_side=None
            self._trim_origin=None
            self._trim_delta_ms=0
            self.panel.trim_item(self.clip_id,side,delta)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.old is not None and self.pos()!=self.old:
            self.panel.move_item(self)
        self.old=None


class TimelineView(QGraphicsView):
    seek=Signal(int)                    # Seek definitivo al soltar el mouse
    scrubStarted=Signal()               # Detener la reproducción durante arrastre
    scrubPreview=Signal(int)            # Actualización inmediata, decodificación diferida
    def __init__(self,panel):
        super().__init__()
        self.panel=panel
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        # QGraphicsView puede delegar los eventos DnD en QGraphicsScene (que
        # no acepta drops por defecto). El viewport recibe y resuelve los
        # eventos antes de que la escena los descarte.
        self.viewport().installEventFilter(self)
        self.setMouseTracking(True)
        self.hover_line=None
        self._scrubbing=False
        self._scrub_previous_cursor=None
        self.setRenderHint(QPainter.RenderHint.Antialiasing,False)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        # Los encabezados de las pistas y la regla se dibujan como overlay fijo.
        # El render parcial + scroll acelerado de Qt copiaba píxeles antiguos,
        # duplicando textos (V1/V2/A1, horas y nombres) sobre las pistas.
        # FullViewportUpdate repinta las capas coherentemente tras cada scroll.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheNone)
        self.horizontalScrollBar().valueChanged.connect(self._scroll_redraw)
        self.verticalScrollBar().valueChanged.connect(self._scroll_redraw)

    def _scroll_redraw(self, value):
        """El desplazamiento no puede reciclar una imagen vieja del overlay."""
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Un cambio de resolución/espacio de trabajo modifica el scroll útil.
        # Posponer para evitar reentradas mientras Qt cambia sus scrollbars.
        if self.scene() is not None:
            QTimer.singleShot(0, self.panel.ensure_scroll_extent)

    def eventFilter(self, watched, event):
        if watched is self.viewport():
            kind = event.type()
            if kind == QEvent.Type.DragEnter:
                self.dragEnterEvent(event)
                return True
            if kind == QEvent.Type.DragMove:
                self.dragMoveEvent(event)
                return True
            if kind == QEvent.Type.Drop:
                self.dropEvent(event)
                return True
        return super().eventFilter(watched, event)

    def _scene_time(self, point):
        """Calcula tiempo desde el cursor, limitado a la secuencia real."""
        scene_x=self.mapToScene(point).x()
        return playhead_time(scene_x,HEADER,self.panel.scale,self.panel.timeline_duration())

    def _head_hit(self, point):
        """La línea se puede agarrar en TODA su altura, no sólo en la regla."""
        if point.x()<HEADER:
            return False
        head_x=HEADER+self.panel.playhead*self.panel.scale/1000
        viewport_x=self.mapFromScene(QPointF(head_x,RULER_H)).x()
        return hit_playhead(point.x(), viewport_x, tolerance=9)

    def _begin_scrub(self, point):
        self._clear_razor_preview()
        self._scrubbing=True
        self._scrub_previous_cursor=self.viewport().cursor()
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        self.scrubStarted.emit()
        self._update_scrub(point)

    def _update_scrub(self, point):
        ms=self._scene_time(point)
        self.panel.set_playhead(ms)
        self.scrubPreview.emit(ms)

    def _end_scrub(self, point):
        self._update_scrub(point)
        self._scrubbing=False
        if self._scrub_previous_cursor is not None:
            self.viewport().setCursor(self._scrub_previous_cursor)
        self._scrub_previous_cursor=None
        self.seek.emit(self.panel.playhead)

    def wheelEvent(self,event):
        delta=event.angleDelta().y()
        if not delta:return super().wheelEvent(event)
        cursor=event.position().toPoint()
        if cursor.x()<HEADER and cursor.y()>RULER_H:
            row=self.panel.row_at(self.mapToScene(cursor).y())
            if row is not None:
                self.panel.resize_track(row,12 if delta>0 else -12)
                event.accept();return
        # Rueda sobre V/A o la regla = zoom horizontal de toda la secuencia.
        if cursor.x()>=HEADER:
            factor=1.18 ** (delta/120)
            self.panel.zoom_at(factor,cursor)
            event.accept();return
        super().wheelEvent(event)

    @staticmethod
    def _paths_from_mime(mime):
        from services.media_drop import existing_media_paths
        raw = []
        # Formato propio y URI de Windows, con respaldo texto para arrastres
        # desde ventanas que solo ofrecen texto o desde el Explorador.
        if mime.hasFormat('application/x-modgames44-media-paths'):
            raw.extend(bytes(mime.data('application/x-modgames44-media-paths'))
                       .decode('utf-8', errors='replace').splitlines())
        if mime.hasUrls():
            raw.extend(u.toLocalFile() for u in mime.urls() if u.isLocalFile())
        if mime.hasText():
            raw.extend(mime.text().splitlines())
        return existing_media_paths(raw)

    def dragEnterEvent(self,event):
        if self._paths_from_mime(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self,event):
        if self._paths_from_mime(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self,event):
        paths=self._paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        pos=self.mapToScene(event.position().toPoint())
        start=max(0,int((pos.x()-HEADER)/self.panel.scale*1000))
        row=self.panel.row_at(pos.y())
        imported=0
        for path in paths:
            meta=probe(path)
            if not meta['has_video'] and not meta['has_audio']:
                self.panel.info.emit(f'Archivo no reconocido: {Path(path).name}')
                continue
            kind='video' if meta['has_video'] else 'audio'
            track=track_for_row(kind,row)
            self.panel.add_clip(path,start_ms=start,track=track,kind=kind)
            start+=self.panel.default_duration(path)
            imported+=1
        if imported:
            self.panel.info.emit(f'{imported} archivo(s) añadidos a la Timeline')
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def _clip_under_pointer(self,point):
        # El indicador de la cuchilla es una línea no interactiva encima del clip.
        return next((item for item in self.items(point) if isinstance(item,ClipItem)),None)

    def _clear_razor_preview(self):
        if self.hover_line is not None:
            if self.hover_line.scene() is not None:
                self.hover_line.scene().removeItem(self.hover_line)
            self.hover_line=None

    def set_tool(self,tool):
        self._clear_razor_preview()
        if tool=='select':
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        elif tool=='razor':
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            icon=QPixmap(str(ICON_DIR/'razor.png'))
            if not icon.isNull():
                icon=icon.scaled(28,28,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                self.viewport().setCursor(QCursor(icon,3,25))
            else:
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.SizeHorCursor)
        for item in self.scene().items():
            if isinstance(item,ClipItem):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,tool=='select')
                item.unsetCursor()
        self.viewport().update()

    def mouseMoveEvent(self,event):
        if self._scrubbing:
            self._update_scrub(event.position().toPoint())
            event.accept()
            return
        # Resaltar la posibilidad de agarrar la línea de reproducción.
        if self.panel.tool=='select' and self._head_hit(event.position().toPoint()):
            self.viewport().setCursor(Qt.CursorShape.SizeHorCursor)
        elif self.panel.tool=='select':
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        if self.panel.tool=='razor':
            clip=self._clip_under_pointer(event.position().toPoint())
            if clip is not None:
                model=next((c for c in self.panel.clips if c['id']==clip.clip_id),None)
                if model is not None:
                    x=self.mapToScene(event.position().toPoint()).x()
                    time_ms=round((x-HEADER)/self.panel.scale*1000)
                    if model['start_ms']<time_ms<end(model):
                        group=self.panel._linked(model)+[model]
                        group=[c for c in group if c['start_ms']<time_ms<end(c)]
                        y1=min(self.panel.row_y(self.panel.row_of(c))+3 for c in group)
                        y2=max(self.panel.row_y(self.panel.row_of(c))+self.panel.track_heights[self.panel.row_of(c)]-3 for c in group)
                        if self.hover_line is None:
                            self.hover_line=self.scene().addLine(x,y1,x,y2,
                                QPen(QColor('#fff0a3'),2,Qt.PenStyle.DashLine))
                            self.hover_line.setZValue(30)
                            self.hover_line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                        else:
                            self.hover_line.setLine(x,y1,x,y2)
                        event.accept()
                        return
            self._clear_razor_preview()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def leaveEvent(self,event):
        self._clear_razor_preview()
        super().leaveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            point=event.position().toPoint()
            scene_pos=self.mapToScene(point)
            clip=self._clip_under_pointer(point)
            # Regla, cabezal o espacio vacío: desplazamiento y arrastre continuo.
            # No propagar a QGraphicsView: evitamos que objetos gráficos intercepten el mouse.
            if point.x()>=HEADER and (
                point.y()<RULER_H or self._head_hit(point)
                or (clip is None and self.panel.tool=='select')
            ):
                self._begin_scrub(point)
                event.accept()
                return
            if self.panel.tool=='razor':
                if clip is not None:
                    time_ms=round((scene_pos.x()-HEADER)/self.panel.scale*1000)
                    self._clear_razor_preview()
                    self.panel.cut_at(clip.clip_id,time_ms)
                event.accept()
                return
            if point.x()<HEADER:
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if self._scrubbing and event.button()==Qt.MouseButton.LeftButton:
            self._end_scrub(event.position().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawForeground(self,painter,rect):
        """Regla y encabezados anclados al viewport durante scroll horizontal."""
        super().drawForeground(painter,rect)
        p=self.panel
        # Overlay fijo en coordenadas de la escena correspondiente al viewport.
        # Con FullViewportUpdate no quedan marcas copiadas de una posición anterior.
        origin=self.mapToScene(0,0)
        ox=origin.x(); oy=origin.y()
        right=self.mapToScene(self.viewport().width(),0).x()
        bottom=self.mapToScene(0,self.viewport().height()).y()
        painter.save()
        # Ruler fijo arriba, pero sus marcas se calculan en tiempo REAL.
        painter.fillRect(QRectF(ox,oy,max(1,right-ox),RULER_H),QColor('#0d1c2b'))
        painter.setPen(QColor('#9bb1c1'))
        interval=ruler_spacing(p.scale)
        visible_start=max(0,(ox-HEADER)/p.scale)
        visible_end=max(0,(right-HEADER)/p.scale)
        start_tick=max(0,math.floor(visible_start/interval))
        for index in range(start_tick,min(start_tick+600,math.ceil(visible_end/interval)+2)):
            seconds=index*interval
            x=HEADER+seconds*p.scale
            if x<ox or x>right:continue
            painter.drawLine(QPointF(x,oy+RULER_H-10),QPointF(x,oy+RULER_H))
            painter.drawText(QPointF(x+3,oy+17),format_ruler(seconds,interval))
        # Marca 00:00 y borde izquierdo de edición siempre legibles.
        painter.fillRect(QRectF(ox,oy,HEADER,max(1,bottom-oy)),QColor('#0d2033'))
        for row,label in enumerate(TRACK_LABELS):
            ry=p.row_y(row)
            if ry+p.track_heights[row]<oy or ry>bottom:continue
            painter.fillRect(QRectF(ox,ry,HEADER-1,p.track_heights[row]-1),QColor('#132c45'))
            painter.setPen(QColor('#9caebe'))
            painter.drawLine(QPointF(ox,ry),QPointF(ox+HEADER,ry))
            painter.setPen(QColor('#def0fb'))
            painter.drawText(QRectF(ox+8,ry,HEADER-16,p.track_heights[row]-1),
                             Qt.AlignmentFlag.AlignVCenter,label)
        painter.fillRect(QRectF(ox,oy,HEADER,RULER_H),QColor('#0e2438'))
        painter.setPen(QColor('#85a6ba'))
        painter.drawText(QRectF(ox+4,oy,HEADER-8,RULER_H),Qt.AlignmentFlag.AlignCenter,'00:00')
        # Cabezal dibujado como capa superior: no es un QGraphicsItem y nunca
        # intercepta clics ni genera removeItem/addLine al avanzar el video.
        head_x=playhead_scene_x(p.playhead,p.scale,HEADER)
        if ox-12<=head_x<=right+12:
            painter.setPen(QPen(QColor('#ffbb43'),2))
            painter.drawLine(QPointF(head_x,oy+4),QPointF(head_x,bottom))
            painter.setBrush(QBrush(QColor('#ffbb43')))
            painter.setPen(QPen(QColor('#ffe9b6'),1))
            painter.drawPolygon(QPolygonF([
                QPointF(head_x-7,oy+3),QPointF(head_x+7,oy+3),
                QPointF(head_x+7,oy+12),QPointF(head_x,oy+19),
                QPointF(head_x-7,oy+12)
            ]))
        painter.restore()


class TimelinePanel(QWidget):
    changed=Signal()
    clip_selected=Signal(str)
    seek_requested=Signal(int)
    scrub_started=Signal()
    scrub_preview=Signal(int)
    info=Signal(str)
    cutPerformed=Signal(int)  # corte interactivo: detener reproducción y situar cabezal
    modeChanged=Signal(str)
    def __init__(self):
        super().__init__()
        self.clips=[];self.history=History();self.scale=PX_SEC;self.playhead=0
        self._row_backgrounds=[]
        self.durations={};self.snap=True;self.tool='select'
        self.show_processed_waves=True
        self.track_heights=[48,48,86,125,65,65]
        self.visuals=VisualCache(self)
        self.visuals.updated.connect(self._visual_updated)
        self.visuals.error.connect(self._visual_error)
        layout=QVBoxLayout(self)
        bar=QHBoxLayout()
        self.tool_hint=QLabel('V: Seleccionar · C: Cuchilla · Ctrl+K: cortar en cabezal')
        bar.addWidget(self.tool_hint)
        bar.addWidget(QLabel('Zoom'))
        slider=QSlider(Qt.Orientation.Horizontal)
        slider.setRange(MIN_ZOOM,MAX_ZOOM);slider.setValue(PX_SEC)
        slider.valueChanged.connect(self.set_zoom)
        self.zoom_slider=slider
        bar.addWidget(slider)
        self.zoom_info=QLabel(f'{PX_SEC} px/s');bar.addWidget(self.zoom_info)
        self.processed_wave_toggle=QCheckBox('Onda FX')
        self.processed_wave_toggle.setChecked(True)
        self.processed_wave_toggle.setToolTip('Comparar las ondas originales con las procesadas. La ganancia se visualiza inmediatamente; los demás efectos se calculan en segundo plano.')
        self.processed_wave_toggle.toggled.connect(self._set_processed_waves)
        bar.addWidget(self.processed_wave_toggle)
        layout.addLayout(bar)
        self.scene=QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.view=TimelineView(self)
        self.view.setScene(self.scene)
        layout.addWidget(self.view)
        self.view.seek.connect(self.seek_requested)
        self.view.scrubStarted.connect(self.scrub_started)
        self.view.scrubPreview.connect(self.scrub_preview)
        self.refresh()

    def _set_processed_waves(self, state):
        self.show_processed_waves=bool(state)
        self.scene.update()

    def _on_selection_changed(self):
        clip=self.selected()
        self.clip_selected.emit(clip['id'] if clip else '')

    def get_clip(self,clip_id):
        return next((c for c in self.clips if c['id']==clip_id),None)

    def update_effects(self,clip_id,changes):
        """Actualiza un efecto con un solo paso de deshacer."""
        clip=self.get_clip(clip_id)
        if clip is None or clip.get('kind')!='video':return False
        if not isinstance(changes,dict):return False
        self.history.record(self.clips)
        if 'speed' in changes:
            change_speed(self.clips,clip_id,changes['speed'])
        fx=merged_effects(clip.get('effects'))
        for key in ('zoom','censor','color'):
            if key in changes and isinstance(changes[key],dict):
                fx[key].update(copy.deepcopy(changes[key]))
        clip['effects']=fx
        self.refresh();self.changed.emit()
        self.info.emit('Efectos actualizados · Ctrl+Z para deshacer')
        return True

    def set_effect_keyframe(self,clip_id,kind,position_ms):
        clip=self.get_clip(clip_id)
        if clip is None or kind not in ('zoom','censor'):return False
        self.history.record(self.clips)
        fx=merged_effects(clip.get('effects'))
        source_ms=round(source_position(clip,position_ms))
        if kind=='zoom':
            data={k:float(fx[kind][k]) for k in ('scale','cx','cy')}
        else:
            data=valid_mask(fx[kind]['mask'])
        fx[kind]['keys']=add_keyframe(fx[kind].get('keys',[]),source_ms,data)
        fx[kind]['enabled']=True
        clip['effects']=fx
        self.refresh();self.changed.emit()
        self.info.emit(f'Fotograma clave de {kind} añadido en {source_ms} ms de origen')
        return True

    def update_audio_effects(self,clip_id,settings):
        """Modifica efectos del clip de audio; compatible con deshacer/rehacer."""
        from effects.audio import validated_audio_effects
        clip=self.get_clip(clip_id)
        if clip is None or clip.get('kind')!='audio':return False
        self.history.record(self.clips)
        clip['audio_fx']=validated_audio_effects(settings)
        self.refresh();self.changed.emit()
        return True

    def set_mask(self,clip_id,rect,position_ms):
        clip=self.get_clip(clip_id)
        if clip is None:return False
        self.history.record(self.clips)
        fx=merged_effects(clip.get('effects'))
        mask=valid_mask(rect)
        fx['censor']['mask']=mask
        fx['censor']['enabled']=True
        if fx['censor'].get('keys'):
            # Tras activar animación, cada nueva posición crea un keyframe.
            source_ms=round(source_position(clip,position_ms))
            fx['censor']['keys']=add_keyframe(fx['censor']['keys'],source_ms,mask)
        clip['effects']=fx
        self.refresh();self.changed.emit()
        return True

    def clear_effects(self,clip_id,kind):
        clip=self.get_clip(clip_id)
        if clip is None:return False
        self.history.record(self.clips)
        fx=merged_effects(clip.get('effects'))
        if kind=='all':
            fx=merged_effects(None)
            change_speed(self.clips,clip_id,1.)
        elif kind in fx:
            # Quitar significa retirar el efecto COMPLETO, incluyendo la
            # animación y la máscara. Ctrl+Z recupera la configuración previa.
            fx[kind]=merged_effects(None)[kind]
        clip['effects']=fx
        self.refresh();self.changed.emit()
        return True

    def _visual_updated(self,path):
        # Evitar repintar toda la escena, incluidos clips no visibles.
        for item in self.scene.items():
            if isinstance(item,ClipItem):
                clip=next((c for c in self.clips if c['id']==item.clip_id),None)
                if clip and clip['path']==path:item.update()

    def _visual_error(self,path,message):
        self.setToolTip(f'No se pudo analizar el audio de {Path(path).name}: {message}')

    def row_y(self,row):return RULER_H+sum(self.track_heights[:row])

    def row_of(self,clip):
        return row_for_clip(clip)

    def row_at(self,y):
        for row in range(6):
            if self.row_y(row)<=y<self.row_y(row)+self.track_heights[row]:return row
        return None

    def resize_track(self,row,delta):
        current=self.track_heights[row]
        self.track_heights[row]=max(MIN_TRACK_HEIGHT,min(MAX_TRACK_HEIGHT,current+delta))
        if current!=self.track_heights[row]:self.refresh()

    def zoom_at(self,factor,cursor):
        old=self.scale
        new=max(MIN_ZOOM,min(MAX_ZOOM,round(old*factor)))
        if new==old:return
        before=self.view.mapToScene(cursor)
        self._apply_zoom(new)
        # El mismo instante permanece bajo el puntero después de ampliar.
        self.view.horizontalScrollBar().setValue(zoom_scroll_value(before.x(),old,new,cursor.x(),HEADER))
        self.view.viewport().update()

    def _apply_zoom(self,value):
        self.scale=int(value)
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(self.scale)
        self.zoom_slider.blockSignals(False)
        self.zoom_info.setText(f'{self.scale} px/s')
        self.refresh()

    def set_zoom(self,value):
        if value==self.scale:return
        viewport_center=self.view.viewport().rect().center()
        self.zoom_at(value/self.scale,viewport_center)

    def timeline_duration(self):
        return max((end(c) for c in self.clips),default=0)

    def set_playhead(self,ms):
        """Actualizar únicamente las franjas del cabezal, sin mutar la escena.

        Eliminar y recrear un QGraphicsLineItem en cada tick podía provocar
        bloqueos gráficos y hacía imposible arrastrar el cabezal con el mouse.
        """
        new_ms=max(0,int(ms))
        if self.playhead==new_ms:
            return
        old_ms=self.playhead
        self.playhead=new_ms
        viewport=self.view.viewport()
        height=viewport.height()
        for time_ms in (old_ms,new_ms):
            x=playhead_scene_x(time_ms,self.scale,HEADER)
            px=self.view.mapFromScene(QPointF(x,RULER_H)).x()
            if -15<=px<=viewport.width()+15:
                viewport.update(QRect(px-11,0,23,height))

    def _navigation_target_x(self, alignment):
        width=max(1,self.view.viewport().width())
        usable=max(1,width-HEADER)
        if alignment=='start':
            return HEADER
        if alignment=='center':
            return round(HEADER+usable*.50)
        if alignment=='end':
            return round(HEADER+usable*.88)
        if alignment=='playback':
            return round(HEADER+usable*.22)
        raise ValueError('Alineación desconocida: '+str(alignment))

    def _adjust_horizontal_to_time(self, alignment):
        """Mover según la posición REAL que informa Qt, no un máximo supuesto.

        Si el valor se clampa en un extremo, ampliar la escena en ese momento
        y repetir. No tocar el desplazamiento vertical ni cambiar el zoom.
        """
        view=self.view
        bar=view.horizontalScrollBar()
        viewport=view.viewport()
        position_x=playhead_scene_x(self.playhead,self.scale,HEADER)
        wanted_x=self._navigation_target_x(alignment)
        if alignment=='start' or self.playhead==0:
            bar.setValue(bar.minimum())
            viewport.update()
            return
        # Un resize o refresh puede dejar a QGraphicsView con un rango antiguo.
        self.ensure_scroll_extent(at_least_ms=self.playhead)
        scroll_target=viewport_scroll_for_time(
            self.playhead,self.scale,viewport.width(),alignment=alignment,
            header=HEADER,current_scroll=bar.value())
        # Forzar geometría del view; la sincronización es idempotente.
        required=minimum_scene_width_for_scroll(scroll_target,viewport.width())
        if self.scene.sceneRect().width()<required:
            self._extend_scene_to(required)
        bar.setValue(max(bar.minimum(),min(bar.maximum(),scroll_target)))
        # El origen real puede diferir del valor de la barra por alineaciones
        # internas de QGraphicsView: ajustar con mapFromScene directamente.
        for _ in range(3):
            actual_x=view.mapFromScene(QPointF(position_x,RULER_H)).x()
            correction=scroll_correction(actual_x,wanted_x,bar.value())
            if abs(actual_x-wanted_x)<=2 or correction==bar.value():
                break
            if correction>bar.maximum():
                self._extend_scene_to(minimum_scene_width_for_scroll(
                    correction,viewport.width()))
            bar.setValue(max(bar.minimum(),min(bar.maximum(),correction)))
        viewport.update()

    def reveal_playhead(self, position_ms=None, *, alignment='end'):
        """Llevar cabezal Y vista al instante, incluso a zoom alto.

        La primera aplicación mueve el scroll; una segunda comprobación en el
        siguiente evento Qt corrige rangos desactualizados del QGraphicsView.
        """
        if position_ms is not None:
            self.set_playhead(position_ms)
        self._navigation_generation=getattr(self,'_navigation_generation',0)+1
        generation=self._navigation_generation
        self._adjust_horizontal_to_time(alignment)
        if alignment!='playback':
            intended_ms=self.playhead
            def finish():
                if (generation!=self._navigation_generation
                        or intended_ms!=self.playhead):
                    return
                self._adjust_horizontal_to_time(alignment)
            QTimer.singleShot(0,finish)

    def navigation_diagnostics(self):
        """Datos para diagnosticar el máximo de scroll de Qt en Windows."""
        view=self.view
        bar=view.horizontalScrollBar()
        scene_x=playhead_scene_x(self.playhead,self.scale,HEADER)
        real_x=view.mapFromScene(QPointF(scene_x,RULER_H)).x()
        return dict(duration_ms=self.timeline_duration(),playhead_ms=self.playhead,
                    scale=self.scale,viewport_width=view.viewport().width(),
                    scene_width=round(self.scene.sceneRect().width()),
                    view_scene_width=round(view.sceneRect().width()),
                    scroll=bar.value(),scroll_max=bar.maximum(),
                    playhead_view_x=real_x)

    def follow_playhead(self):
        """Autoscroll solo durante Play y cuando sale de la zona visible."""
        if self.view._scrubbing:
            return
        viewport=self.view.viewport()
        x=playhead_scene_x(self.playhead,self.scale,HEADER)
        visible_x=self.view.mapFromScene(QPointF(x,RULER_H)).x()
        if needs_playback_follow(visible_x,viewport.width(),HEADER):
            self.reveal_playhead(alignment='playback')

    def set_clips(self,clips):
        self.clips=copy.deepcopy(clips)
        for clip in self.clips:
            clip.setdefault('id',uuid.uuid4().hex)
            clip.setdefault('track',0)
            clip.setdefault('kind','video')
            clip.setdefault('in_ms',0)
            clip.setdefault('speed',1.)
            clip.setdefault('effects',{})
            clamp_fades(clip)
            clip['duration_ms']=clip.get('duration_ms') or 10000
            clamp_fades(clip)
        self.history=History()
        self.refresh()

    def refresh(self):
        chosen={item.clip_id for item in self.scene.selectedItems() if isinstance(item,ClipItem)}
        self.view._clear_razor_preview()
        self.scene.blockSignals(True)
        self.scene.clear()
        width=timeline_scene_width(self.timeline_duration(), self.scale,
                                   self.view.viewport().width(), header=HEADER)
        self._row_backgrounds=[]
        for row in range(6):
            y=self.row_y(row)
            color='#0e1d30' if row%2==0 else '#111f32'
            item=self.scene.addRect(0,y,width,self.track_heights[row],
                                    QPen(QColor('#253d56')),QBrush(QColor(color)))
            self._row_backgrounds.append(item)
        for clip in self.clips:
            item=ClipItem(self,clip)
            self.scene.addItem(item)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable,self.tool=='select')
            if clip['id'] in chosen:item.setSelected(True)
            self.visuals.request(clip['path'],need_wave=(clip.get('kind')=='audio'))
        self.scene.setSceneRect(0,0,width,RULER_H+sum(self.track_heights)+5)
        # QGraphicsView mantiene su propio rectángulo y rango de barras.
        # Sin sincronizarlo, Qt puede conservar un máximo de scroll antiguo
        # después de un zoom o una carga de video de mayor duración.
        self.view.setSceneRect(self.scene.sceneRect())
        self.scene.blockSignals(False)
        selected=self.selected()
        self.clip_selected.emit(selected['id'] if selected else '')
        self.view.viewport().update()

    def _extend_scene_to(self,width):
        """Extender la escena sin reconstruir clips o perder el zoom.

        Es imprescindible sincronizar QGraphicsScene y QGraphicsView. El view
        puede seguir usando un sceneRect anterior tras varios zoom y resize.
        """
        rect=self.scene.sceneRect()
        width=max(float(width),rect.width())
        if abs(width-rect.width())>1:
            for item in self._row_backgrounds:
                r=item.rect()
                item.setRect(r.x(),r.y(),width,r.height())
            self.scene.setSceneRect(0,0,width,rect.height())
        if abs(self.view.sceneRect().width()-width)>1:
            self.view.setSceneRect(self.scene.sceneRect())
        self.view.viewport().update()

    def ensure_scroll_extent(self, at_least_ms=None):
        """Sincronizar rangos scene/view sin modificar el tiempo del proyecto."""
        if self.scene is None or self.view.scene() is None:
            return
        duration=max(self.timeline_duration(),int(at_least_ms or 0))
        width=timeline_scene_width(duration,self.scale,
                                   self.view.viewport().width(),header=HEADER)
        self._extend_scene_to(width)

    def selected(self):
        ids={item.clip_id for item in self.scene.selectedItems() if isinstance(item,ClipItem)}
        return next((clip for clip in self.clips if clip['id'] in ids),None)

    def default_duration(self,path):
        if path not in self.durations:self.durations[path]=probe(path)['duration_ms'] or 10000
        return self.durations[path]

    def add_clip(self,path,start_ms=None,track=0,kind=None):
        meta=probe(path)
        if kind is None:kind='video' if meta['has_video'] else 'audio'
        if start_ms is None:
            start_ms=max([end(c) for c in self.clips if c.get('track',0)==track and c.get('kind','video')==kind]+[0])
        self.history.record(self.clips)
        duration=self.default_duration(path)
        link=uuid.uuid4().hex if kind=='video' and meta['has_audio'] else None
        clip=make_clip(path,duration,start_ms,track,kind=kind,link=link)
        self.clips.append(clip)
        if link:self.clips.append(make_clip(path,duration,start_ms,track,kind='audio',link=link))
        self.refresh()
        for item in self.scene.items():
            if isinstance(item,ClipItem) and item.clip_id==clip['id']:
                item.setSelected(True);break
        self.changed.emit()

    def set_clip_fade(self,clip_id,side,duration_ms):
        """Los fades pertenecen al clip individual, aunque esté vinculado."""
        clip=self.get_clip(clip_id)
        if clip is None:return False
        before=fade_durations(clip)
        proposed=copy.deepcopy(clip)
        if not change_fade(proposed,side,duration_ms):
            self.refresh()
            return False
        self.history.record(self.clips)
        clip['fade_in_ms']=proposed['fade_in_ms']
        clip['fade_out_ms']=proposed['fade_out_ms']
        self.refresh();self.changed.emit()
        self.info.emit(f"Fade {'In' if side=='in' else 'Out'}: {duration_ms/1000:.2f} s · Ctrl+Z para deshacer")
        return True

    def _linked(self,clip):
        link=clip.get('link')
        return [other for other in self.clips if other['id']!=clip['id'] and other.get('link')==link] if link else []

    def remove_media(self,paths):
        targets=set(paths)
        removed=[clip for clip in self.clips if clip['path'] in targets]
        if removed:
            self.history.record(self.clips)
            self.clips=[clip for clip in self.clips if clip['path'] not in targets]
            self.refresh();self.changed.emit()
        return len(removed)

    def move_item(self,item):
        clip=next((clip for clip in self.clips if clip['id']==item.clip_id),None)
        if clip is None:return
        start=clamp_clip_start((item.x()-HEADER)/self.scale*1000)
        if self.snap:
            edges=[0]+[value for other in self.clips
                       if other['id']!=clip['id'] and other not in self._linked(clip)
                       for value in (other['start_ms'],end(other))]
            nearest=min(edges,key=lambda value:abs(value-start))
            if abs(nearest-start)<150:start=nearest
        row=self.row_at(item.y()+item.rect().height()/2)
        target_row=row if row is not None else self.row_of(clip)
        track=track_for_row(clip.get('kind','video'),target_row,clip['track'])
        partners=self._linked(clip)
        delta=start-clip['start_ms']
        delta=max(delta,-min([clip['start_ms']]+[other['start_ms'] for other in partners]))
        if delta==0 and track==clip['track']:
            self.refresh();return
        self.history.record(self.clips)
        clip['start_ms']+=delta;clip['track']=track
        for other in partners:
            # El movimiento horizontal sigue vinculado. La asignación de
            # pistas es independiente: V1 no obliga a colocar audio en A1.
            other['start_ms']+=delta
        self.refresh();self.changed.emit()

    def set_tool(self,tool):
        if tool not in ('select','razor','trim_start','trim_end'):
            return
        self.tool=tool
        self.view.set_tool(tool)
        texts={
            'select':'V: mover · Esquinas superiores: fades · Bordes: recortar',
            'razor':'Cuchilla (C) · Haz clic sobre un clip · Esc o V para salir',
            'trim_start':'Recortar inicio ([) · Arrastra sobre un clip',
            'trim_end':'Recortar final (]) · Arrastra sobre un clip',
        }
        self.tool_hint.setText(texts[tool])
        self.modeChanged.emit(tool)
        self.info.emit(texts[tool])
        self.view.setFocus()

    def select_tool(self):
        self.set_tool('select')

    def cut_at(self,clip_id,time_ms):
        """Cuchilla: corta exactamente donde se hace clic sobre el clip."""
        if not any(c['id']==clip_id and c['start_ms']<time_ms<end(c) for c in self.clips):
            self.info.emit('Cuchilla: selecciona un punto dentro del clip, no en sus bordes')
            return False
        self.history.record(self.clips)
        new_id=split_at(self.clips,clip_id,time_ms)
        if new_id is None:
            self.history.past.pop()
            return False
        self.refresh()
        self.scene.clearSelection()
        for item in self.scene.items():
            if isinstance(item,ClipItem) and item.clip_id==new_id:
                item.setSelected(True)
                break
        # La cuchilla posiciona el cabezal exactamente en el nuevo corte.
        # El controlador principal pausará el motor si estaba reproduciendo.
        self.set_playhead(time_ms)
        self.cutPerformed.emit(int(time_ms))
        self.changed.emit()
        self.info.emit(f'Corte realizado en {time_ms/1000:.3f} s · reproducción detenida · Ctrl+Z para deshacer')
        return True

    def cut_selected(self):
        """Acción independiente Ctrl+K: corte en cabezal sobre el clip elegido."""
        clip=self.selected()
        return self.cut_at(clip['id'],self.playhead) if clip else False

    def remove_selected(self):
        ids={item.clip_id for item in self.scene.selectedItems() if isinstance(item,ClipItem)}
        if not ids:
            return False
        self.history.record(self.clips)
        if remove_linked(self.clips,ids):
            self.refresh();self.changed.emit()
            self.info.emit('Clips eliminados · Ctrl+Z para deshacer')
            return True
        self.history.past.pop()
        return False

    def unlink_selected(self):
        ids={item.clip_id for item in self.scene.selectedItems() if isinstance(item,ClipItem)}
        if not ids or not any(c['id'] in ids and c.get('link') for c in self.clips):
            return False
        self.history.record(self.clips)
        unlink(self.clips,ids)
        self.refresh();self.changed.emit()
        self.info.emit('Audio y vídeo desvinculados')
        return True

    def preview_trim_delta(self,clip_id,side,delta_ms):
        group=self._linked(next((c for c in self.clips if c['id']==clip_id),{}))
        for c in [x for x in self.clips if x['id']==clip_id]+group:
            if c['path'] not in self.durations:
                self.default_duration(c['path'])
        low,high=trim_bounds(self.clips,clip_id,side,self.durations)
        delta=max(low,min(high,int(delta_ms)))
        if self.snap:
            main=next((c for c in self.clips if c['id']==clip_id),None)
            if main:
                edge=main['start_ms'] if side=='inicio' else end(main)
                targets=[0]+[p for c in self.clips if c not in [main]+group
                             for p in (c['start_ms'],end(c))]
                closest=min(targets,key=lambda t:abs(t-(edge+delta)))
                tolerance=8/self.scale*1000
                if abs(closest-(edge+delta))<=tolerance:
                    delta=max(low,min(high,closest-edge))
        return int(delta)

    def trim_item(self,clip_id,side,delta_ms):
        """Recorte interactivo de ambos canales vinculados, no destructivo."""
        delta_ms=self.preview_trim_delta(clip_id,side,delta_ms)
        if not delta_ms:
            self.refresh()
            return False
        self.history.record(self.clips)
        if trim_linked(self.clips,clip_id,side,delta_ms,self.durations):
            self.refresh();self.changed.emit()
            self.info.emit(f'Recorte de {side}: {delta_ms:+d} ms')
            return True
        self.history.past.pop()
        self.refresh()
        return False

    def trim_selected(self,side):
        """Compatibilidad: activa la herramienta de recorte en vez de abrir un diálogo."""
        self.set_tool('trim_start' if side=='inicio' else 'trim_end')

    def close_gaps(self):
        self.history.record(self.clips)
        for track in range(3):close_gap(self.clips,track,'video')
        for clip in self.clips:
            if clip.get('kind')=='video':
                for other in self._linked(clip):other['start_ms']=clip['start_ms']
        for track in range(3):
            independent=[c for c in self.clips if c.get('kind')=='audio' and not c.get('link') and c.get('track')==track]
            close_gap(independent,track,'audio')
        self.refresh();self.changed.emit()

    def undo(self):
        previous=self.history.undo(self.clips)
        if previous is not None:self.clips=previous;self.refresh();self.changed.emit()

    def redo(self):
        following=self.history.redo(self.clips)
        if following is not None:self.clips=following;self.refresh();self.changed.emit()

    def contextMenuEvent(self,event):
        menu=QMenu(self)
        menu.addAction('Seleccionar (V)',self.select_tool)
        menu.addAction('Cuchilla (C)',lambda:self.set_tool('razor'))
        menu.addAction('Cortar en cabezal (Ctrl+K)',self.cut_selected)
        selected=self.selected()
        if selected is not None:
            menu.addSeparator()
            menu.addAction('Fade In 1 segundo',lambda clip_id=selected['id']:self.set_clip_fade(clip_id,'in',1000))
            menu.addAction('Fade Out 1 segundo',lambda clip_id=selected['id']:self.set_clip_fade(clip_id,'out',1000))
            menu.addAction('Quitar Fade In',lambda clip_id=selected['id']:self.set_clip_fade(clip_id,'in',0))
            menu.addAction('Quitar Fade Out',lambda clip_id=selected['id']:self.set_clip_fade(clip_id,'out',0))
        menu.addSeparator()
        menu.addAction('Recortar inicio ([)',lambda:self.set_tool('trim_start'))
        menu.addAction('Recortar final (])',lambda:self.set_tool('trim_end'))
        menu.addAction('Desvincular vídeo / audio',self.unlink_selected)
        menu.addSeparator()
        menu.addAction('Eliminar (Supr)',self.remove_selected)
        menu.addAction('Cerrar huecos',self.close_gaps)
        menu.addAction('Deshacer (Ctrl+Z)',self.undo)
        menu.addAction('Rehacer (Ctrl+Y)',self.redo)
        menu.exec(event.globalPos())
