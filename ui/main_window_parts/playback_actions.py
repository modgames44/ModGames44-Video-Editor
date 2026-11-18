"""Transporte: reproducir, buscar, avanzar fotogramas y scrub.

Métodos movidos sin cambios desde ui/main_window.py (v0.6.6).
"""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QMessageBox)
from PySide6.QtMultimedia import QMediaPlayer
from timeline.model import active



class PlaybackActionsMixin:
    def _audio_preview_status(self,message):
        self.statusBar().showMessage(message,6000)
        if self.mode=='timeline':
            self.monitor.set_fx_state(
                'FX · Preparando audio…' if 'Preparando' in message else
                'FX · Activos' if 'audio y video' in message else
                'FX · Listos para reproducir')

    def _preview_volume(self,volume):
        self.engine.audio.setVolume(volume)
        self.audio_preview.output.setVolume(volume)

    def _playback_state(self,state):
        if state!=QMediaPlayer.PlaybackState.PlayingState:self.meter.clear()
    def duration(self):
        return self.sequence.duration() if self.mode=='timeline' else self.engine.player.duration()
    def _position(self,pos):
        if self.mode=='project':self.monitor.update_position(pos)
    def _sequence_position(self,pos):
        if self.mode=='timeline':
            # Qt Multimedia y QTimer emiten posiciones independientemente.
            # Redibujar Timeline y efectos por duplicado a 60+ veces/s causa
            # tirones. Mantener ~30 actualizaciones/s, sin retrasar seeks.
            from time import monotonic
            now=monotonic()
            last=getattr(self,'_last_preview_ui_position',None)
            previous=getattr(self,'_last_preview_ui_time',0.0)
            if (self.sequence.running and last is not None
                    and abs(pos-last)<120 and now-previous<0.028):
                return
            self._last_preview_ui_time=now if self.sequence.running else 0.0
            self._last_preview_ui_position=pos
            self.monitor.update_position(pos)
            self.timeline.set_playhead(pos)
            if hasattr(self,'_docks') and 'Keyframes' in self._docks and self._docks['Keyframes'].isVisible():
                self.keyframe_panel.set_context(self.timeline.selected(),pos)
            # Durante Play, la vista acompaña al cabezal cuando llega al borde.
            # El usuario puede seguir desplazándose manualmente al estar pausado.
            if self.sequence.running or pos >= self.sequence.duration():
                self.timeline.follow_playhead()
            self._sync_effects_view()
            if not self.sequence.running and not self.audio_preview.is_waiting:
                self.monitor.set_fx_state('FX · Listos para reproducir')
            self.audio_preview.follow(pos, self.sequence.running,
                                      resume_video=self.sequence.play,
                                      pause_video=self.sequence.pause)
    def _duration(self,duration):
        if self.mode=='project':self.monitor.update_duration(duration)
        if self.current_media:self.timeline.durations[self.current_media]=duration
    def _media_error(self,error,message):
        if message:self.statusBar().showMessage('Error multimedia: '+message,10000)
    def _media_status(self,status):
        if status==QMediaPlayer.MediaStatus.LoadedMedia:
            if self.mode=='project':self.engine.seek(0)
            elif self.sequence.current_id:
                from timeline.model import source_position
                clip=next((c for c in self.timeline.clips if c['id']==self.sequence.current_id),None)
                if clip:
                    self.engine.seek(source_position(clip,self.sequence.position))
                    if self.sequence.running:self.engine.player.play()
    def toggle(self):
        if self.mode!='timeline':
            self.engine.toggle()
            return
        if self.sequence.running or self.audio_preview.is_waiting:
            self.sequence.pause()
            self.audio_preview.pause()
            self.statusBar().showMessage('Reproducción pausada',2500)
            return
        total=self.sequence.duration()
        if not total:
            return
        pos=0 if self.sequence.position>=total else self.sequence.position
        if pos!=self.sequence.position:
            self.sequence.seek(pos)
        self.engine.audio.setMuted(True)
        self.meter.set_mode('timeline')
        self.monitor.set_fx_state('FX · Preparando audio…')
        self.audio_preview.play(pos, self.timeline.clips, total, self.sequence.play)

    def jump_to_start(self):
        """Inicio: mover el tiempo y la ventana horizontal al origen."""
        self.seek(0)
        if self.mode=='timeline':
            self.timeline.reveal_playhead(0, alignment='start')

    def jump_to_end(self):
        """Final: mostrar el último fotograma y desplazar el viewport con él."""
        destination=self.duration()
        self.seek(destination)
        if self.mode=='timeline':
            self.timeline.reveal_playhead(destination, alignment='end')
            # Diagnóstico optativo: habilitar MODGAMES_TIMELINE_DEBUG=1 en Windows.
            import os
            if os.getenv('MODGAMES_TIMELINE_DEBUG')=='1':
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: print(
                    'TIMELINE_END_NAVIGATION',self.timeline.navigation_diagnostics(),
                    flush=True))

    def seek(self,ms):
        if self.mode=='timeline':
            self.monitor.video.invalidate_seek()
            self.audio_preview.pause()
            self.sequence.pause()
            self.sequence.seek(ms)
            self.timeline.reveal_playhead(ms, alignment='center')
            self._sync_effects_view()
        else:self.engine.seek(ms)
    def _frame_rate(self):
        """FPS real de la fuente bajo el cabezal (antes siempre 30)."""
        from services.media_probe import probe
        path=None
        if self.mode=='timeline':
            clip=active(self.timeline.clips,self.sequence.position,'video')
            path=clip['path'] if clip else None
        else:
            path=self.current_media
        fps=probe(path).get('fps') if path else 0
        return float(fps) if fps and fps>1 else float(max(1,self.project.get('fps',30)))
    def step(self,frames):
        delta=round(frames*1000/self._frame_rate())
        self.seek((self.sequence.position if self.mode=='timeline' else self.engine.player.position())+delta)
    def _begin_timeline_scrub(self):
        self.audio_preview.pause()
        # La reproducción se pausa una sola vez por gesto, como Premiere.
        if self.mode=='timeline':
            self.sequence.pause()
        else:
            self.engine.player.pause()

    def _preview_timeline_scrub(self,ms):
        # Respuesta visual inmediata sin solicitar miles de decodificaciones
        # al motor FFmpeg. Si el usuario deja el cursor quieto, previsualizar.
        ms=int(ms)
        self.mode='timeline'
        self._pending_timeline_seek=ms
        self.monitor.update_duration(self.sequence.duration())
        self.monitor.update_position(ms)
        self._scrub_timer.start()

    def _flush_scrub(self):
        if self._pending_timeline_seek is None:
            return
        ms=self._pending_timeline_seek
        self._pending_timeline_seek=None
        self.seek_timeline(ms)

    def seek_timeline(self,ms):
        self.monitor.video.invalidate_seek()
        self.audio_preview.pause()
        self.sequence.pause()
        self.engine.audio.setMuted(True)
        self.meter.set_mode('timeline')
        self._scrub_timer.stop()
        self._pending_timeline_seek=None
        self.monitor.set_fx_state('FX · Listos para reproducir')
        self.mode='timeline';self.sequence.seek(ms);self.monitor.update_duration(self.sequence.duration())
        self._sync_effects_view()
        if hasattr(self,'keyframe_panel'):
            self.keyframe_panel.set_context(self.timeline.selected(),self.timeline.playhead)
    def preview(self,path):
        if not Path(path).is_file():QMessageBox.warning(self,'Archivo no encontrado',path);return
        self.audio_preview.pause()
        self.engine.audio.setMuted(False)
        self.meter.set_mode('project')
        self.monitor.set_fx_state(None)
        self.sequence.pause();self.sequence.enabled=False
        self.timeline.set_playhead(0)
        self.mode='project';self.current_media=path;self.monitor.video.set_composition(None,0);self.monitor.video.set_active_clip(None);self.engine.load(path)
    def add_selected_to_timeline(self):
        """Ctrl+Enter también usa la misma ruta que doble clic."""
        paths=self.project_panel.selected_paths()
        if not paths:
            item=self.project_panel.list.currentItem()
            if item:
                paths=[item.data(Qt.ItemDataRole.UserRole)]
        self.insert_project_media(paths)
