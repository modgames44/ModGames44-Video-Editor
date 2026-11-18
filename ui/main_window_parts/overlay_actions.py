"""Títulos, subtítulos, imágenes, transcripción y keyframes.

Métodos movidos sin cambios desde ui/main_window.py (v0.6.6).
"""
from pathlib import Path
from PySide6.QtWidgets import (QFileDialog,QMessageBox)
from ui.text_panel import CaptionWorker
from effects.title_overlay import title_clip



class OverlayActionsMixin:
    def _focus_title_panel(self):
        dock=self._docks['Texto y subtítulos'];dock.show();dock.raise_()
        self.text_panel.tabs.setCurrentIndex(0)
        self.text_panel.title_text.setFocus()

    def _add_title(self,text,style):
        if not text.strip():return
        clip=title_clip(text,self.timeline.playhead)
        clip['title_style']=style
        self.timeline.add_text_clip(clip)
        self.seek_timeline(self.timeline.playhead)

    def _insert_image(self):
        from effects.image_overlay import image_clip
        path,_=QFileDialog.getOpenFileName(self,'Insertar imagen superpuesta','',
            'Imágenes (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)')
        if not path:return
        try:
            clip=image_clip(path,self.timeline.playhead)
            self.timeline.add_text_clip(clip)
            self.seek_timeline(clip['start_ms'])
            self.text_panel.tabs.setCurrentIndex(2)
            self.statusBar().showMessage('Imagen añadida en V3 · arrástrala en el monitor',6000)
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,'Insertar imagen',str(exc))

    def _select_overlay(self,clip_id):
        self.sequence.pause()
        self.audio_preview.pause()
        if self.timeline.select_clip_id(clip_id):
            self.monitor.video.set_selected_overlay(clip_id)

    def _overlay_transform_committed(self,clip_id,changes):
        from effects.title_overlay import transform_at
        clip=self.timeline.get_clip(clip_id)
        if not clip or clip.get('kind') not in ('title','subtitle','image'):
            return
        local=max(0,min(clip['duration_ms'],self.timeline.playhead-clip['start_ms']))
        keys=clip.get('transform_keys') or []
        # Sin animación se guarda un único estado válido para todo el clip.
        time_ms=local if keys else 0
        current=transform_at(clip,self.timeline.playhead)
        current.update({k:float(changes[k]) for k in ('x','y','scale') if k in changes})
        self.timeline.history.record(self.timeline.clips)
        remaining=[dict(k) for k in keys if abs(int(k['time_ms'])-time_ms)>40]
        remaining.append(dict(time_ms=time_ms,**current))
        clip['transform_keys']=sorted(remaining,key=lambda k:k['time_ms'])
        self.timeline.refresh()
        self.timeline.select_clip_id(clip_id)
        self.timeline.changed.emit()
        self.statusBar().showMessage('Posición/tamaño actualizados · Ctrl+Z para deshacer',5000)

    def _add_subtitle(self,text):
        if not text.strip():return
        self.timeline.add_text_clip(title_clip(text,self.timeline.playhead,2500,subtitle=True))
        self.seek_timeline(self.timeline.playhead)

    def _update_title(self,clip_id,text,style):
        clip=self.timeline.get_clip(clip_id)
        if not clip or clip.get('kind') not in ('title','subtitle'):return
        self.timeline.history.record(self.timeline.clips)
        clip.update(text=text[:800],title_style=style)
        self.timeline.refresh();self.timeline.changed.emit()

    def _export_srt(self):
        from services.subtitles_srt import export_srt
        if not any(c.get('kind')=='subtitle' for c in self.timeline.clips):
            QMessageBox.information(self,'Exportar SRT','La Timeline no tiene subtítulos.');return
        target,_=QFileDialog.getSaveFileName(self,'Guardar subtítulos','','Subtítulos (*.srt)')
        if target:
            try:
                path=str(Path(target).with_suffix('.srt'))
                export_srt(path,self.timeline.clips)
                self.statusBar().showMessage('Subtítulos guardados: '+path,9000)
            except (OSError,ValueError) as exc:
                QMessageBox.warning(self,'Subtítulos',str(exc))

    def _transcribe_selected(self,language,model):
        clip=self._selected_video()
        if clip is None:
            QMessageBox.information(self,'Subtítulos','Selecciona primero el video que quieres transcribir.');return
        if self._caption_worker is not None and self._caption_worker.isRunning():return
        self.text_panel.busy(True)
        self._caption_target=(clip['id'],clip['path'],clip['start_ms'],clip['in_ms'],clip['duration_ms'],clip.get('speed',1))
        worker=CaptionWorker(clip['path'],language,model,self)
        self._caption_worker=worker
        worker.completed.connect(self._captions_ready)
        worker.failed.connect(self._caption_failed)
        worker.finished.connect(lambda:self.text_panel.busy(False))
        worker.start()
        self.statusBar().showMessage('Reconociendo voz localmente…',7000)

    def _caption_failed(self,message):
        self.text_panel.busy(False)
        QMessageBox.warning(self,'Subtítulos automáticos',message)

    def _captions_ready(self,captions):
        from effects.title_overlay import title_clip
        clip_id,path,start,source_in,duration,speed=self._caption_target
        current=self.timeline.get_clip(clip_id)
        if current is None or current['path']!=path:
            self._caption_failed('La Timeline cambió durante la transcripción.');return
        added=[]
        for c in captions:
            # La transcripción usa los tiempos del archivo fuente, no de Timeline.
            begin=max(0,round((c.start_ms-source_in)/speed))
            finish=min(duration,round((c.end_ms-source_in)/speed))
            if finish <= begin or begin >= duration:continue
            added.append(title_clip(c.text,start+begin,finish-begin,subtitle=True))
        if added:
            self.timeline.history.record(self.timeline.clips)
            self.timeline.clips.extend(added)
            self.timeline.refresh();self.timeline.changed.emit()
        self.text_panel.busy(False)
        self.statusBar().showMessage(f'{len(added)} subtítulos añadidos · Ctrl+Z para deshacer',9000)

    def _store_keyframe(self,clip_id,values):
        clip=self.timeline.get_clip(clip_id)
        if not clip:return
        key='volume_keys' if clip.get('kind')=='audio' else 'transform_keys'
        if key=='transform_keys' and clip.get('kind') not in ('title','subtitle','image'):return
        time_ms=max(0,min(clip['duration_ms'],self.timeline.playhead-clip['start_ms']))
        self.timeline.history.record(self.timeline.clips)
        keys=[k for k in clip.get(key,[]) if abs(k['time_ms']-time_ms)>40]
        keys.append({'time_ms':time_ms,**values})
        clip[key]=sorted(keys,key=lambda k:k['time_ms'])
        self.timeline.refresh();self.timeline.changed.emit()
        self.keyframe_panel.set_context(clip,self.timeline.playhead)

    def _delete_keyframe(self,clip_id):
        clip=self.timeline.get_clip(clip_id)
        if not clip:return
        key='volume_keys' if clip.get('kind')=='audio' else 'transform_keys'
        keys=clip.get(key,[])
        t=self.timeline.playhead-clip['start_ms']
        remaining=[k for k in keys if abs(k['time_ms']-t)>50]
        if len(remaining)==len(keys):return
        self.timeline.history.record(self.timeline.clips)
        clip[key]=remaining
        self.timeline.refresh();self.timeline.changed.emit()
