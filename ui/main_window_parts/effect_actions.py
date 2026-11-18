"""Efectos de video/audio, proxies y seguimiento de objetos.

Métodos movidos sin cambios desde ui/main_window.py (v0.6.6).
"""
from pathlib import Path
import copy
from PySide6.QtWidgets import (QMessageBox,QProgressDialog)
from services.proxy_manager import generate_proxy
from exporter.hardware import ffmpeg_candidates
from core.error_log import get_logger
from timeline.model import source_position

_log = get_logger('main')


class EffectActionsMixin:
    def _toggle_proxies(self,enabled):
        self.use_proxies=bool(enabled)
        self.settings.setValue('editing/proxy_preview',self.use_proxies)
        self.monitor.video._composition_reader.use_proxies=self.use_proxies
        self.sequence.use_proxies=self.use_proxies
        self.sequence.current_id=None
        if self.mode=='timeline':self.seek_timeline(self.timeline.playhead)

    def _generate_selected_proxy(self):
        clip=self._selected_video()
        if not clip or self._proxy_busy:
            self.statusBar().showMessage('Selecciona un video o termina el proxy anterior.',5000);return
        self._proxy_busy=True
        path=clip['path']
        ffmpeg=next(iter(ffmpeg_candidates()),'ffmpeg')
        self.statusBar().showMessage('Creando proxy 540p en segundo plano…',9000)
        cancel=self._proxy_cancel
        def work():
            from services.proxy_manager import ProxyCancelled
            try:self._proxy_signals.finished.emit(path,str(generate_proxy(path,ffmpeg,cancel=cancel)),'')
            except ProxyCancelled:pass
            except Exception as exc:  # noqa: BLE001 - se informa al usuario
                _log.exception('Error generando proxy')
                self._proxy_signals.failed.emit(str(exc))
        self._proxy_pool.submit(work)

    def _proxy_ready(self,path,output,_):
        self._proxy_busy=False
        self.statusBar().showMessage('Proxy preparado: '+Path(output).name,9000)
        if self.mode=='timeline' and self.use_proxies:
            self.sequence.current_id=None
            self.seek_timeline(self.timeline.playhead)

    def _proxy_error(self,message):
        self._proxy_busy=False
        QMessageBox.warning(self,'Proxy',message)

    def _selected_video(self):
        c=self.timeline.selected()
        if c and c.get('kind')=='audio' and c.get('link'):
            c=next((x for x in self.timeline.clips
                    if x.get('kind')=='video' and x.get('link')==c['link']),None)
        return c if c and c.get('kind')=='video' else None

    def _selected_audio(self):
        clip=self.timeline.selected()
        if clip and clip.get('kind')=='video' and clip.get('link'):
            clip=next((x for x in self.timeline.clips
                       if x.get('kind')=='audio' and x.get('link')==clip['link']),None)
        return clip if clip and clip.get('kind')=='audio' else None

    def _on_clip_selected(self,clip_id):
        self.audio_effects_panel.set_selected(self._selected_audio())
        clip=self._selected_video()
        self.effects_panel.set_selected(clip)
        self.properties_panel.set_selected(self.timeline.selected())
        self.text_panel.set_selected(self.timeline.selected())
        self.keyframe_panel.set_context(self.timeline.selected(),self.timeline.playhead)
        self.monitor.video.set_selected_overlay(self.timeline.selected()['id'] if self.timeline.selected() and self.timeline.selected().get('kind') in ('title','subtitle','image') else None)
        if clip is not None and (self.timeline.playhead < clip['start_ms'] or
                                 self.timeline.playhead >= clip['start_ms']+clip['duration_ms']):
            self.sequence.pause()
            self.seek_timeline(clip['start_ms'])
        else:self._sync_effects_view()

    def _sync_effects_view(self):
        from timeline.fades import fade_factor
        if self.mode!='timeline':
            self.monitor.video.set_title_overlays([],0)
            self.monitor.video.set_composition(None,0)
            self.monitor.video.set_active_clip(None)
            return
        from effects.compositor import active_layers
        self.monitor.video.set_title_overlays(self.timeline.clips,self.timeline.playhead)
        selected=self.timeline.selected()
        self.monitor.video.set_selected_overlay(selected['id'] if selected and
            selected.get('kind') in ('title','subtitle','image') else None)
        layers=active_layers(self.timeline.clips,self.timeline.playhead)
        clip=layers[-1] if layers else None
        self.monitor.video.set_composition(layers,self.timeline.playhead)
        if clip:
            self.monitor.video.set_active_clip(clip['id'],clip.get('effects'),
                      source_position(clip,self.timeline.playhead),
                      fade_alpha=1.0 if len(layers)>1 else fade_factor(clip,self.timeline.playhead))
        else:
            self.monitor.video.set_active_clip(None)
            self.monitor.video.clear_frame()

    def _audio_effect_apply(self,clip_id,settings):
        self.audio_preview.pause()
        self.sequence.pause()
        if self.timeline.update_audio_effects(clip_id,settings):
            self.audio_effects_panel.set_selected(self._selected_audio())
            self.statusBar().showMessage('Audio actualizado. Pulsa Play para escuchar todos los efectos.', 7000)

    def _effect_apply(self,clip_id,changes):
        self.audio_preview.pause()
        self.sequence.pause()
        if self.timeline.update_effects(clip_id,changes):
            self._sync_effects_view()
            self.effects_panel.set_selected(self._selected_video())
            self.seek_timeline(self.timeline.playhead)

    def _effect_key(self,kind):
        selected=self._selected_video()
        if selected:
            self.timeline.set_effect_keyframe(selected['id'],kind,self.timeline.playhead)
            self._sync_effects_view()

    def _effect_clear(self,kind):
        selected=self._selected_video()
        if not selected:
            return
        if kind in ('censor', 'all'):
            self.effects_panel.stop_mask_editing()
            self.monitor.video.set_mask_editing(False)
        if hasattr(self, "audio_preview"):
            self.audio_preview.pause()
        self.sequence.pause()
        if self.timeline.clear_effects(selected['id'],kind):
            # Sincronizar controles, inspector y frame mostrado después de
            # borrar, no solo los datos del modelo de Timeline.
            self.effects_panel.set_selected(self._selected_video())
            self.properties_panel.set_selected(self.timeline.selected())
            self._sync_effects_view()
            self.monitor.video.update()
            self.statusBar().showMessage(
                'Efecto eliminado. Ctrl+Z para recuperarlo.', 5000)


    def _track_selected(self,clip_id):
        clip=self.timeline.get_clip(clip_id)
        if clip is None or not clip.get('effects',{}).get('censor',{}).get('enabled'):
            return
        if self._tracking_dialog is not None:
            return
        self.sequence.pause()
        self.audio_preview.pause()
        self._tracking_cancel.clear()
        current=copy.deepcopy(clip)
        source_signature=repr(current)
        position=max(current['start_ms'],min(self.timeline.playhead,
                  current['start_ms']+current['duration_ms']-1))
        dialog=QProgressDialog('Siguiendo la máscara en el video…','Cancelar',0,100,self)
        dialog.setWindowTitle('Seguimiento automático · ModGames44')
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.canceled.connect(self._tracking_cancel.set)
        self._tracking_dialog=dialog
        dialog.show()
        def run():
            try:
                from services.object_tracking import track_censor
                points=track_censor(current,position,cancel=self._tracking_cancel,
                         progress=self._tracking_signals.progress.emit)
                self._tracking_signals.finished.emit(clip_id,points,source_signature)
            except Exception as exc:  # noqa: BLE001 - se informa al usuario
                _log.exception('Error en el seguimiento de objeto')
                self._tracking_signals.failed.emit(str(exc))
        self._tracking_pool.submit(run)

    def _track_progress(self,value):
        if self._tracking_dialog is not None:
            self._tracking_dialog.setValue(int(value))

    def _finish_tracking(self):
        dialog,self._tracking_dialog=self._tracking_dialog,None
        if dialog:
            dialog.close()
            dialog.deleteLater()

    def _track_error(self,message):
        self._finish_tracking()
        QMessageBox.warning(self,'Seguimiento de objeto',message)

    def _track_done(self,clip_id,points,signature):
        cancelled=self._tracking_cancel.is_set()
        self._finish_tracking()
        if cancelled:
            self.statusBar().showMessage('Seguimiento cancelado; no se modificó el proyecto.',6000)
            return
        clip=self.timeline.get_clip(clip_id)
        if clip is None or repr(clip)!=signature:
            self.statusBar().showMessage('El clip cambió durante el seguimiento; se descartaron sus resultados.',7000)
            return
        from effects.model import merged_effects
        fx=merged_effects(clip.get('effects'))
        first,last=points[0]['time_ms'],points[-1]['time_ms']
        before=[k for k in fx['censor'].get('keys',[]) if k['time_ms']<first or k['time_ms']>last]
        fx['censor']['keys']=sorted(before+points,key=lambda x:x['time_ms'])
        fx['censor']['enabled']=True
        self.timeline.history.record(self.timeline.clips)
        clip['effects']=fx
        self.timeline.refresh()
        self.timeline.changed.emit()
        self._sync_effects_view()
        self.statusBar().showMessage(
            f'Seguimiento generado: {len(points)} puntos de máscara. Puedes corregirlos con el mouse.',9000)

    def _mask_committed(self,clip_id,rect):
        self.timeline.set_mask(clip_id,rect,self.timeline.playhead)
        self._sync_effects_view()
