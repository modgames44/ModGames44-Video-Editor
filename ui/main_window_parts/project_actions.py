"""Proyecto: medios, abrir/guardar, autoguardado y recuperación.

Métodos movidos sin cambios desde ui/main_window.py (v0.6.6).
"""
from pathlib import Path
import copy
from PySide6.QtWidgets import (QFileDialog,QMessageBox)
from core.project_manager import empty_project,load_project,save_project,missing_media,relink_media
from core.autosave_recovery import save_recovery,load_recovery,clear_recovery,recovery_path



class ProjectActionsMixin:
    def insert_project_media(self, paths):
        """Inserta archivos de Proyecto al final de la secuencia, sin solapes.

        Un doble clic debe producir el mismo resultado que soltar el archivo
        sobre una zona libre de V1. El MP4 añade su audio enlazado a A1.
        """
        if not paths:
            return
        paths=[p for p in paths if p]
        self.statusBar().showMessage(f'Analizando {len(paths)} medio(s)…')
        # El análisis (FFmpeg) va en segundo plano; la inserción, al terminar.
        self.timeline.probes.run(paths,lambda results:self._insert_probed_media(paths,results))

    def _insert_probed_media(self,paths,results):
        from services.media_probe import probe
        start=max([c['start_ms']+c['duration_ms']
                   for c in self.timeline.clips if c.get('kind')=='video']+[0])
        inserted=0
        first_ms=start
        for path in paths:
            if not path or not Path(path).is_file():
                self.statusBar().showMessage('Medio no encontrado; revisa la ruta.',6000)
                continue
            meta=results.get(str(path)) or probe(path)
            if not (meta['has_video'] or meta['has_audio']):
                self.statusBar().showMessage(f'Formato no reconocido: {Path(path).name}',6000)
                continue
            kind='video' if meta['has_video'] else 'audio'
            self.timeline.add_clip(str(path),start_ms=start,track=0,kind=kind)
            start+=self.timeline.default_duration(path)
            inserted+=1
        if inserted:
            self.seek_timeline(first_ms)
            self.statusBar().showMessage(
                f'{inserted} medio(s) añadido(s) a la Timeline · Ctrl+Z para deshacer',6000)
        else:
            self.statusBar().clearMessage()
    def add_files(self,files):
        for path in files:
            if path not in self.project['media']:self.project['media'].append(path)
        self.project_panel.set_files(self.project['media']);self.dirty=True
        # Analizar ya en segundo plano: así, al llevarlos a la Timeline, los
        # metadatos están en caché y la ventana no se congela.
        self.timeline.probes.run(list(files))
    def remove_project_files(self,paths):
        targets=set(paths)&set(self.project['media'])
        if not targets:return
        used=[c for c in self.timeline.clips if c['path'] in targets]
        message=f'¿Quitar {len(targets)} archivo(s) del proyecto?\nLos archivos originales no se borrarán.'
        if used:
            message+=f'\n\nAtención: también se eliminarán {len(used)} clip(s) de la Timeline.'
        ans=QMessageBox.question(self,'Eliminar del proyecto',message,
              QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
              QMessageBox.StandardButton.No)
        if ans!=QMessageBox.StandardButton.Yes:return
        if self.current_media in targets:
            self.sequence.pause();self.engine.player.stop()
            self.current_media=None;self.monitor.update_duration(0);self.monitor.update_position(0)
        self.timeline.remove_media(targets)
        self.project['media']=[p for p in self.project['media'] if p not in targets]
        self.project_panel.set_files(self.project['media'])
        self.dirty=True

    def _clips_changed(self):
        self.audio_preview.configure(self.timeline.clips,self.sequence.duration())
        self.ai_assistant.invalidated()
        self.project['clips']=copy.deepcopy(self.timeline.clips);self.dirty=True
        self.properties_panel.set_selected(self.timeline.selected())
        self.text_panel.set_selected(self.timeline.selected())
        self.keyframe_panel.set_context(self.timeline.selected(),self.timeline.playhead)
        # Deshacer/rehacer también debe actualizar el estado visible del botón
        # de quitar censura y de la casilla de edición con mouse.
        self.effects_panel.set_selected(self._selected_video())
        if self.timeline.clips and self.mode!='timeline':
            self.seek_timeline(self.timeline.playhead)
        if self.mode=='timeline':
            self.monitor.update_duration(self.sequence.duration())
            self._sync_effects_view()
    def _refresh(self):
        self.audio_preview.pause()
        self.engine.audio.setMuted(False)
        self.meter.set_mode('project')
        self.monitor.set_fx_state(None)
        self.sequence.pause();self.sequence.enabled=False;self.engine.player.stop();self.mode='project';self.current_media=None
        self.project_panel.set_files(self.project['media']);self.timeline.set_clips(self.project['clips'])
        # Precargar metadatos en segundo plano (recortes y efectos los usan).
        used=[c.get('path') for c in self.project['clips'] if c.get('kind') not in ('title','subtitle')]
        self.timeline.probes.run(list(dict.fromkeys(self.project['media']+[p for p in used if p])))
        self.monitor.update_duration(0);self.monitor.update_position(0);self.dirty=False
        self.effects_panel.set_selected(None)
        self.audio_effects_panel.set_selected(None)
        self.properties_panel.set_selected(None)
        self.text_panel.set_selected(None)
        self.keyframe_panel.set_context(None,0)
        self.monitor.video.set_title_overlays([],0)
        self.monitor.video.set_selected_overlay(None)
        self.monitor.video.set_composition(None,0)
        self.monitor.video.set_active_clip(None)
    def _check_dirty(self):
        """Guardar / Descartar / Cancelar. True si se puede continuar."""
        if not self.dirty:return True
        box=QMessageBox(QMessageBox.Icon.Warning,'Cambios sin guardar',
            '¿Quieres guardar los cambios del proyecto antes de continuar?',
            QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|
            QMessageBox.StandardButton.Cancel,self)
        save_button=box.button(QMessageBox.StandardButton.Save)
        discard_button=box.button(QMessageBox.StandardButton.Discard)
        box.setDefaultButton(save_button)
        save_button.setText('Guardar')
        discard_button.setText('Descartar')
        box.button(QMessageBox.StandardButton.Cancel).setText('Cancelar')
        box.exec()
        # clickedButton() evita depender de si exec() devuelve int o enum.
        clicked=box.clickedButton()
        if clicked is save_button:
            return bool(self.save())
        if clicked is discard_button:
            # Descartar a propósito: no ofrecer recuperar esta sesión al reabrir.
            clear_recovery(self.project_path)
            self.dirty=False
            return True
        return False
    def new_project(self):
        if not self._check_dirty():return
        clear_recovery(self.project_path)
        self.project=empty_project();self.project_path=None;self._refresh()
    def open_project(self):
        if not self._check_dirty():return
        path,_=QFileDialog.getOpenFileName(self,'Abrir proyecto','','Proyecto ModGames44 (*.mg44)')
        if path:
            try:
                project=load_project(path,resolve_relative=True)
                recovered=self._recover_project(path)
                self.project=recovered if recovered is not None else project
                self.project_path=path
                relinked=self._offer_relink()
                self._refresh()
                if recovered is not None or relinked:self.dirty=True
            except (OSError,ValueError) as e:QMessageBox.critical(self,'Error de proyecto',str(e))
    def save(self):
        if not self.project_path:return self.save_as()
        try:
            self._clips_changed();save_project(self.project_path,self.project,relative_paths=True)
            self.dirty=False;clear_recovery(self.project_path)
            self.statusBar().showMessage('Proyecto guardado',3000);return True
        except OSError as e:QMessageBox.critical(self,'Error al guardar',str(e));return False
    def save_as(self):
        path,_=QFileDialog.getSaveFileName(self,'Guardar proyecto','','Proyecto ModGames44 (*.mg44)')
        if path:
            previous=self.project_path
            self.project_path=str(Path(path).with_suffix('.mg44'))
            ok=self.save()
            if ok:clear_recovery(previous)
            return ok
        return False
    def autosave(self):
        if self.dirty:
            try:
                self.project['clips']=copy.deepcopy(self.timeline.clips)
                save_recovery(self.project,self.project_path)
            except OSError as e:self.statusBar().showMessage(f'Error autoguardado: {e}',10000)

    def _offer_relink(self):
        """Si faltan medios, permitir buscarlos en otra carpeta por nombre."""
        missing=missing_media(self.project)
        if not missing:return 0
        names='\n'.join(Path(p).name for p in missing[:12])+('\n…' if len(missing)>12 else '')
        answer=QMessageBox.question(self,'Medios no encontrados',
            f'No se encontraron {len(missing)} archivo(s) del proyecto:\n\n{names}\n\n'
            '¿Buscarlos en otra carpeta (se busca por nombre, incluidas subcarpetas)?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer!=QMessageBox.StandardButton.Yes:return 0
        folder=QFileDialog.getExistingDirectory(self,'Carpeta donde están los medios')
        if not folder:return 0
        count=relink_media(self.project,folder)
        still=len(missing_media(self.project))
        self.statusBar().showMessage(f'{count} medio(s) vuelto(s) a enlazar'
            +(f' · siguen faltando {still}' if still else ''),9000)
        return count

    def _recover_project(self,path):
        backup=recovery_path(path)
        original=Path(path)
        if not backup.exists() or backup.stat().st_mtime <= original.stat().st_mtime:
            return None
        try:data=load_recovery(path)
        except (OSError,ValueError):return None
        reply=QMessageBox.question(self,'Recuperar cambios',
            'Encontré un autoguardado más reciente que el proyecto. ¿Recuperarlo?\n'
            'El archivo original no se sobrescribirá.',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        return data if reply==QMessageBox.StandardButton.Yes else None

    def _offer_initial_recovery(self):
        if self.project_path or self.dirty:return
        try:data=load_recovery()
        except (OSError,ValueError):return
        if data is None:return
        answer=QMessageBox.question(self,'Recuperar proyecto sin guardar',
            'Se encontró una sesión sin guardar. ¿Recuperar la Timeline?',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if answer==QMessageBox.StandardButton.Yes:
            self.project=data
            self._refresh()
            self.dirty=True
        else:clear_recovery()
