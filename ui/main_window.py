from pathlib import Path
import copy
import hashlib
import json
from PySide6.QtCore import Qt,QSettings,QTimer,QSize
from PySide6.QtGui import QAction,QKeySequence,QActionGroup,QIcon,QPixmap
from PySide6.QtWidgets import (QMainWindow,QDockWidget,QFileDialog,QMessageBox,QLabel,
    QTabWidget,QToolBar,QPushButton,QComboBox,QWidget,QSizePolicy,QApplication,QHBoxLayout)
from PySide6.QtMultimedia import QMediaPlayer
from core.project_manager import empty_project,load_project,save_project
from core.media_engine import MediaEngine
from core.sequence_player import SequencePlayer
from core.audio_preview import AudioPreview
from ui.project_panel import ProjectPanel
from ui.program_monitor import ProgramMonitor
from ui.timeline_panel import TimelinePanel
from ui.tools_panel import ToolsPanel
from ui.audio_meter import AudioMeter
from ui.ai_assistant_panel import AIAssistantPanel
from ui.effects_panel import EffectsPanel
from ui.audio_effects_panel import AudioEffectsPanel
from ui.export_dialog import ExportDialog
from ui.clip_properties_panel import ClipPropertiesPanel
from ui.workspace_manager import WorkspaceManager
from ui.quick_effects_panel import QuickEffectsPanel
from ui.effect_catalog_panel import EffectCatalogPanel
from ui.responsive_rules import layout_metrics
from core.workspaces import WORKSPACES, normalized_workspace
from timeline.model import active, source_position
from ai.operations import prepare_plan, PlanError
from ai.local_commands import parse_local
from ai.openai_planner import propose as cloud_propose
from ai.silence import analyze_silences, silence_plan

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('ModGames44 Video Editor · v0.4.12 Cyber Studio · Nuitka Onefile');self.resize(1536,900)
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1]/'assets'/'icons'/'modgames44.ico')))
        self.settings=QSettings('ModGames44','VideoEditor');self.project=empty_project();self.project_path=None
        self.mode='project';self.dirty=False;self.current_media=None
        self.monitor=ProgramMonitor();self.setCentralWidget(self.monitor)
        self.engine=MediaEngine(self.monitor.video);self.project_panel=ProjectPanel()
        self.timeline=TimelinePanel();self.tools=ToolsPanel();self.meter=AudioMeter()
        self.effects_panel=EffectsPanel()
        self.audio_effects_panel=AudioEffectsPanel()
        self.effects_tabs=QTabWidget()
        self.effects_tabs.setObjectName('EffectsHub')
        self.quick_effects=QuickEffectsPanel()
        self.effect_catalog=EffectCatalogPanel()
        self.effects_tabs.addTab(self.quick_effects,'Rápidos')
        self.effects_tabs.addTab(self.effect_catalog,'Catálogo')
        self.effects_tabs.addTab(self.effects_panel,'Video')
        self.effects_tabs.addTab(self.audio_effects_panel,'Audio / Voz')
        self.quick_effects.openRequested.connect(self._open_effect_category)
        self.effect_catalog.openRequested.connect(self._open_effect_category)
        self.meter.attach(self.engine.player, 'project')
        self.audio_preview=AudioPreview(self)
        self.meter.attach(self.audio_preview.player, 'timeline')
        self.meter.set_mode('project')
        self.audio_preview.status.connect(self._audio_preview_status)
        self.audio_preview.error.connect(lambda message:self.statusBar().showMessage(message,15000))
        self.sequence=SequencePlayer(self.engine,self.timeline)
        self.sequence.stop_at_cuts=self.settings.value('stop_at_cuts',True,type=bool)
        self.audio_preview.configure(self.timeline.clips, self.sequence.duration())
        self._pending_timeline_seek=None
        self._scrub_timer=QTimer(self)
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.setInterval(130)
        self._scrub_timer.timeout.connect(self._flush_scrub)
        self.setDockNestingEnabled(True)
        self._dock('Proyecto',self.project_panel,Qt.DockWidgetArea.LeftDockWidgetArea)
        self._dock('Herramientas',self.tools,Qt.DockWidgetArea.LeftDockWidgetArea)
        self._dock('Audio Meter',self.meter,Qt.DockWidgetArea.RightDockWidgetArea)
        self._dock('Timeline',self.timeline,Qt.DockWidgetArea.BottomDockWidgetArea)
        self._dock('Efectos (futuro)',self.effects_tabs,Qt.DockWidgetArea.RightDockWidgetArea)
        self._docks['Efectos (futuro)'].setWindowTitle('Efectos rápidos')
        self.properties_panel=ClipPropertiesPanel()
        self._dock('Propiedades',self.properties_panel,Qt.DockWidgetArea.RightDockWidgetArea)
        self.ai_assistant=AIAssistantPanel()
        self._dock('Asistente IA',self.ai_assistant,Qt.DockWidgetArea.LeftDockWidgetArea)
        self._menu();self._connect()
        self.autosave_timer=QTimer(self);self.autosave_timer.timeout.connect(self.autosave);self.autosave_timer.start(60000)
        saved_geometry=self.settings.value('geometry')
        if saved_geometry:
            self.restoreGeometry(saved_geometry)
        self.workspaces=WorkspaceManager(self,self._docks,self.settings)
        self.workspaces.changed.connect(self._workspace_changed)
        # En esta actualización Cyber Studio pasa a ser la opción inicial.
        # Se respeta cualquier elección posterior del usuario.
        if not self.settings.value('workspaces/studio_default_v044', False, type=bool):
            starting = 'studio'
            self.settings.setValue('workspaces/studio_default_v044', True)
        else:
            starting = normalized_workspace(self.settings.value('workspaces/active', 'studio'))
        self.workspaces.activate(starting,save_previous=False)
        self._apply_responsive_metrics()
        # El layout inicial se recalcula al recibir showEvent, no sólo en __init__.
        QTimer.singleShot(0, self._apply_responsive_metrics)

    def _dock(self,title,widget,area):
        dock=QDockWidget(title,self);dock.setObjectName('dock_'+title);dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable |
                         QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas);self.addDockWidget(area,dock)
        if not hasattr(self,'_docks'):self._docks={}
        self._docks[title]=dock
    def _action(self,menu,title,shortcut,fn):
        a=QAction(title,self)
        if shortcut:a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(fn);menu.addAction(a);return a
    def _select_tool(self,tool):
        self.timeline.set_tool(tool)
        self.tools.set_mode(tool)

    def _tool_action(self,action):
        actions={
            'delete':self.timeline.remove_selected,
            'close_gaps':self.timeline.close_gaps,
            'undo':self.timeline.undo,
            'redo':self.timeline.redo,
            'unlink':self.timeline.unlink_selected,
        }
        fn=actions.get(action)
        if fn:fn()

    def _menu(self):
        f=self.menuBar().addMenu('Archivo')
        for args in [('Nuevo','Ctrl+N',self.new_project),('Abrir proyecto','Ctrl+O',self.open_project),
          ('Importar multimedia','Ctrl+I',self.project_panel.import_files),('Añadir seleccionado a Timeline','Ctrl+Return',self.add_selected_to_timeline),
          ('Guardar','Ctrl+S',self.save),('Guardar como','Ctrl+Shift+S',self.save_as),
          ('Exportar video...','Ctrl+M',self.export_video)]:
            self._action(f,*args)
        edit=self.menuBar().addMenu('Editar')
        for args in (
            ('Selección','V',lambda:self._select_tool('select')),
            ('Cuchilla','C',lambda:self._select_tool('razor')),
            ('Recortar inicio','[',lambda:self._select_tool('trim_start')),
            ('Recortar final',']',lambda:self._select_tool('trim_end')),
            ('Volver a seleccionar','Esc',lambda:self._select_tool('select')),
            ('Cortar clip seleccionado en cabezal','Ctrl+K',self.timeline.cut_selected),
            ('Eliminar','Delete',self.timeline.remove_selected),
            ('Desvincular audio/vídeo',None,self.timeline.unlink_selected),
            ('Deshacer','Ctrl+Z',self.timeline.undo),
            ('Rehacer','Ctrl+Y',self.timeline.redo),
            ('Cerrar huecos',None,self.timeline.close_gaps),
        ):
            self._action(edit,*args)
        playback=self.menuBar().addMenu('Reproducción')
        self._action(playback,'Play / Pause','Space',self.toggle)
        stop_action=QAction('Detener reproducción en los cortes',self)
        stop_action.setCheckable(True)
        stop_action.setChecked(self.sequence.stop_at_cuts)
        stop_action.setToolTip('Detener el cabezal al final del segmento cortado; Play continúa con el siguiente')
        stop_action.toggled.connect(self._set_stop_at_cuts)
        playback.addAction(stop_action)
        ai_menu = self.menuBar().addMenu('IA')
        self._action(ai_menu, 'Abrir asistente de edición', 'Ctrl+Shift+A', self._show_ai)
        ai_menu.addAction(self._docks['Asistente IA'].toggleViewAction())
        view=self.menuBar().addMenu('Ver')
        spaces=view.addMenu('Espacio de trabajo')
        self.workspace_actions={}
        self.workspace_action_group=QActionGroup(self)
        self.workspace_action_group.setExclusive(True)
        for key,spec in WORKSPACES.items():
            action=QAction(spec.label,self)
            action.setCheckable(True)
            action.setToolTip(spec.description)
            action.setShortcut(QKeySequence('Ctrl+Alt+1' if key=='neon' else 'Ctrl+Alt+2'))
            action.triggered.connect(lambda checked=False,name=key:self._switch_workspace(name))
            spaces.addAction(action)
            self.workspace_action_group.addAction(action)
            self.workspace_actions[key]=action
        self._action(view,'Restablecer distribución actual',None,self._reset_workspace)
        self._action(view,'Copiar diagnóstico de Timeline','Ctrl+Alt+D',self.copy_timeline_diagnostics)
        view.addSeparator()
        for name in ('Proyecto','Timeline','Herramientas','Efectos (futuro)',
                     'Propiedades','Audio Meter'):
            view.addAction(self._docks[name].toggleViewAction())
        self._create_global_toolbar()

    def copy_timeline_diagnostics(self):
        """Copiar datos de la geometría Qt para reportar un fallo persistente."""
        diag=self.timeline.navigation_diagnostics()
        diag['mode']=self.mode
        diag['sequence_duration_ms']=self.sequence.duration()
        QApplication.clipboard().setText(json.dumps(diag,ensure_ascii=False,indent=2))
        self.statusBar().showMessage('Diagnóstico de Timeline copiado al portapapeles',5000)

    def _create_global_toolbar(self):
        toolbar=QToolBar('Barra principal',self)
        toolbar.setObjectName('GlobalToolbar')
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(20,20))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea,toolbar)
        # Identidad visual original: logo a la izquierda del nombre.
        brand_container = QWidget(self)
        brand_container.setObjectName('BrandContainer')
        brand_layout = QHBoxLayout(brand_container)
        brand_layout.setContentsMargins(6, 0, 14, 0)
        brand_layout.setSpacing(9)
        logo = QLabel(brand_container)
        logo.setObjectName('BrandLogo')
        logo.setFixedSize(33, 33)
        logo_file = Path(__file__).resolve().parents[1] / 'assets' / 'icons' / 'modgames44_logo.png'
        pixmap = QPixmap(str(logo_file))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))
        brand_layout.addWidget(logo)
        brand = QLabel('ModGames44 Video Editor', brand_container)
        brand.setObjectName('BrandLabel')
        brand_layout.addWidget(brand)
        self.brand_logo = logo
        self.brand_label = brand
        toolbar.addWidget(brand_container)
        spacer=QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        space_label=QLabel('Espacio:')
        space_label.setObjectName('WorkspaceTitle')
        self.space_label=space_label
        toolbar.addWidget(space_label)
        selector=QComboBox(self)
        selector.setObjectName('WorkspaceSelector')
        for key,spec in WORKSPACES.items():
            selector.addItem(spec.label,key)
            selector.setItemData(selector.count()-1,spec.description,
                                 Qt.ItemDataRole.ToolTipRole)
        selector.currentIndexChanged.connect(self._workspace_combo_changed)
        self.workspace_selector=selector
        toolbar.addWidget(selector)
        export=QPushButton('⇧  Exportar',self)
        export.setObjectName('ExportButton')
        export.setToolTip('Exportar video (Ctrl+M)')
        export.clicked.connect(self.export_video)
        toolbar.addWidget(export)
        self.export_button=export
        self.global_toolbar=toolbar

    def _workspace_combo_changed(self,index):
        if index>=0:
            self._switch_workspace(self.workspace_selector.itemData(index))

    def _switch_workspace(self,key):
        if hasattr(self,'workspaces'):
            self.workspaces.activate(key)

    def _workspace_changed(self,key):
        index=self.workspace_selector.findData(key)
        self.workspace_selector.blockSignals(True)
        self.workspace_selector.setCurrentIndex(index)
        self.workspace_selector.blockSignals(False)
        for name,action in self.workspace_actions.items():
            action.setChecked(name==key)
        self.statusBar().showMessage(
            f'Espacio de trabajo: {WORKSPACES[key].label} · mismo proyecto y herramientas',4500)
        self._docks['Efectos (futuro)'].setWindowTitle(
            'Efectos rápidos' if key=='neon' else 'Efectos')
        self.effects_tabs.setCurrentWidget(
            self.quick_effects if key=='neon' else self.effect_catalog)
        self._apply_responsive_metrics()

    def _reset_workspace(self):
        if hasattr(self,'workspaces'):
            self.workspaces.reset_active()

    def _open_effects_tab(self,kind):
        dock=self._docks['Efectos (futuro)']
        dock.show()
        dock.raise_()
        self.effects_tabs.setCurrentWidget(
            self.audio_effects_panel if kind=='audio' else self.effects_panel)

    def _open_effect_category(self,kind):
        if kind in ('noise','voice'):
            self._open_effects_tab('audio')
            if kind == 'noise':
                self.audio_effects_panel.noise.setFocus()
            else:
                self.audio_effects_panel.voice.setFocus()
        else:
            self._open_effects_tab('video')
            # QTimer evita desplazar antes de que Qt muestre la pestaña.
            QTimer.singleShot(0,lambda name=kind:self.effects_panel.focus_section(name))

    def _apply_responsive_metrics(self):
        if not hasattr(self,'global_toolbar') or not hasattr(self,'quick_effects'):
            return
        metrics=layout_metrics(self.width(),self.height())
        self.monitor.set_compact(metrics.compact_labels)
        # El panel de Proyecto se adapta también si se redimensiona a mano.
        self.project_panel._refresh_grid()
        # QuickEffectsPanel reordena sus mosaicos usando su ancho real.
        self.global_toolbar.setIconSize(QSize(18,18) if metrics.compact_labels else QSize(20,20))
        self.space_label.setVisible(not metrics.compact_labels)
        self.export_button.setText('Exportar' if metrics.compact_labels else '⇧  Exportar')

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._apply_responsive_metrics()

    def showEvent(self,event):
        super().showEvent(event)
        if hasattr(self,'workspaces') and self.workspaces._pending_default:
            QTimer.singleShot(0,lambda:self.workspaces._resize_defaults(self.workspaces.active))

    def _show_ai(self):
        self._docks['Asistente IA'].show()
        self._docks['Asistente IA'].raise_()
        self.ai_assistant.query.setFocus()

    def _ai_signature(self):
        # Si el usuario edita manualmente mientras la IA analiza, nunca aplicar
        # una propuesta calculada con una Timeline desactualizada.
        data = json.dumps(self.timeline.clips, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    def _ai_selected(self):
        selected = self.timeline.selected()
        return selected['id'] if selected else None

    def _ai_receive(self, payload, signature):
        if signature != self._ai_signature():
            self.ai_assistant.message('La Timeline cambió durante el análisis. Repite la instrucción.')
            return
        if isinstance(payload, dict) and payload.get('operations') == []:
            explanation = payload.get('explanation', 'Esta acción aún no está disponible.')
            self.ai_assistant.message(str(explanation)[:1200])
            return
        try:
            plan = prepare_plan(payload, self.timeline.clips)
        except (PlanError, ValueError, TypeError) as exc:
            self.ai_assistant.message('Plan rechazado: ' + str(exc))
            return
        if not plan['operations']:
            self.ai_assistant.message(plan['explanation'] or 'La solicitud no puede realizarse con las funciones disponibles.')
            return
        self.ai_assistant.display_plan(plan, signature)

    def _ai_propose(self, query, online, model):
        if self.ai_assistant.busy:
            return
        clips = copy.deepcopy(self.timeline.clips)
        signature = self._ai_signature()
        selected_id = self._ai_selected()
        playhead = self.timeline.playhead
        fps = self.project.get('fps', 30)
        def task():
            if online:
                return cloud_propose(query, clips, selected_id, playhead, model, fps)
            # Un corte local a una posición determinada apunta al clip activo,
            # no al seleccionado si éste está en otro momento de la secuencia.
            return parse_local(query, selected_id)
        self._show_ai()
        self.ai_assistant.start_task(task, lambda payload: self._ai_receive(payload, signature))

    def _ai_silence(self):
        if self.ai_assistant.busy:
            return
        selected = self.timeline.selected()
        if not selected:
            self.ai_assistant.message('Selecciona primero un video con audio en la Timeline.')
            return
        if selected.get('kind') == 'audio' and selected.get('link'):
            selected = next((c for c in self.timeline.clips
                             if c.get('link') == selected['link'] and c.get('kind') == 'video'), selected)
        from services.media_probe import probe
        if not probe(selected['path']).get('has_audio'):
            self.ai_assistant.message('El clip seleccionado no contiene una pista de audio.')
            return
        selected = copy.deepcopy(selected)
        signature = self._ai_signature()
        def task():
            return silence_plan(selected, analyze_silences(selected))
        self._show_ai()
        self.ai_assistant.start_task(task, lambda payload: self._ai_receive(payload, signature))

    def _ai_apply(self):
        pending = self.ai_assistant.pending
        if pending is None or self.ai_assistant.busy:
            return
        plan, signature = pending
        if self._ai_signature() != signature:
            self.ai_assistant.invalidated()
            return
        answer = QMessageBox.question(self, 'Confirmar edición asistida',
            f'¿Aplicar {len(plan["operations"])} operación(es) a la Timeline?\n'
            'Puedes deshacer todos los cambios juntos con Ctrl+Z.\n'
            'Los archivos originales no se modificarán.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            # SEGUNDA validación justo antes de modificar el estado.
            fresh = prepare_plan({'operations': plan['operations']}, self.timeline.clips)
        except PlanError as exc:
            self.ai_assistant.message('No se pudieron aplicar los cambios: '+str(exc))
            return
        self.audio_preview.pause()
        self.sequence.pause()
        modified = fresh['preview_clips'] != self.timeline.clips
        if modified:
            self.timeline.history.record(self.timeline.clips)
            self.timeline.clips = fresh['preview_clips']
            self.timeline.refresh()
            self.timeline.changed.emit()
        if fresh['seek_ms'] is not None:
            self.seek_timeline(fresh['seek_ms'])
        elif modified:
            self.seek_timeline(min(self.timeline.playhead, self.timeline.timeline_duration()))
        self.ai_assistant.message(f'Aplicadas {len(plan["operations"])} operación(es). Ctrl+Z para deshacer.')
        self.statusBar().showMessage('Edición asistida aplicada sin modificar medios originales.', 7000)

    def _set_stop_at_cuts(self,enabled):
        self.sequence.stop_at_cuts=bool(enabled)
        self.settings.setValue('stop_at_cuts',bool(enabled))

    def _on_cut_performed(self,time_ms):
        # Si la cuchilla se usa durante Play, cortar debe pausar el motor
        # ANTES de pedir un seek. No reiniciar reproducción automáticamente.
        self._scrub_timer.stop()
        self._pending_timeline_seek=None
        self.sequence.pause()
        self.engine.player.pause()
        self.seek_timeline(time_ms)

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
        if clip is not None and (self.timeline.playhead < clip['start_ms'] or
                                 self.timeline.playhead >= clip['start_ms']+clip['duration_ms']):
            self.sequence.pause()
            self.seek_timeline(clip['start_ms'])
        else:self._sync_effects_view()

    def _sync_effects_view(self):
        from timeline.fades import fade_factor
        if self.mode!='timeline':
            self.monitor.video.set_active_clip(None)
            return
        clip=active(self.timeline.clips,self.timeline.playhead,'video')
        if clip:
            self.monitor.video.set_active_clip(clip['id'],clip.get('effects'),
                      source_position(clip,self.timeline.playhead),
                      fade_alpha=fade_factor(clip,self.timeline.playhead))
        else:
            self.monitor.video.set_active_clip(None)
            self.monitor.video.clear_frame()

    def _audio_effect_apply(self,clip_id,settings):
        self.audio_preview.pause()
        self.sequence.pause()
        if self.timeline.update_audio_effects(clip_id,settings):
            self.audio_effects_panel.set_selected(self._selected_audio())
            self.statusBar().showMessage('Audio actualizado. Pulsa Play para escuchar todos los efectos.', 7000)

    def export_video(self):
        if not self.timeline.clips:
            QMessageBox.information(self,'Exportar','Primero añade clips a la Timeline.')
            return
        self.audio_preview.pause()
        self.sequence.pause()
        dialog=ExportDialog(self.timeline.clips,self)
        dialog.exec()

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


    def _mask_committed(self,clip_id,rect):
        self.timeline.set_mask(clip_id,rect,self.timeline.playhead)
        self._sync_effects_view()

    def _connect(self):
        self.timeline.clip_selected.connect(self._on_clip_selected)
        self.effects_panel.applyRequested.connect(self._effect_apply)
        self.audio_effects_panel.applyRequested.connect(self._audio_effect_apply)
        self.effects_panel.keyframeRequested.connect(self._effect_key)
        self.effects_panel.clearRequested.connect(self._effect_clear)
        self.properties_panel.removeCensorRequested.connect(
            lambda: self._effect_clear('censor'))
        self.effects_panel.editMaskChanged.connect(self.monitor.video.set_mask_editing)
        self.monitor.video.maskCommitted.connect(self._mask_committed)
        self.ai_assistant.proposeRequested.connect(self._ai_propose)
        self.ai_assistant.silenceRequested.connect(self._ai_silence)
        self.ai_assistant.applyRequested.connect(self._ai_apply)
        self.properties_panel.editRequested.connect(self._open_effects_tab)
        self.tools.toolChanged.connect(self._select_tool)
        self.timeline.modeChanged.connect(self.tools.set_mode)
        self.tools.editRequested.connect(self._tool_action)
        self.tools.snapChanged.connect(lambda enabled:setattr(self.timeline,'snap',enabled))
        self.timeline.info.connect(lambda msg:self.statusBar().showMessage(msg,5000))
        self.project_panel.add_files.connect(self.add_files)
        self.project_panel.remove_files.connect(self.remove_project_files)
        self.project_panel.insert_files.connect(self.insert_project_media)
        self.project_panel.selected.connect(self.preview)
        self.timeline.changed.connect(self._clips_changed)
        self.timeline.cutPerformed.connect(self._on_cut_performed)
        self.timeline.seek_requested.connect(self.seek_timeline)
        self.timeline.scrub_started.connect(self._begin_timeline_scrub)
        self.timeline.scrub_preview.connect(self._preview_timeline_scrub)
        self.monitor.toggle.connect(self.toggle)
        self.monitor.seek_requested.connect(self.seek)
        self.monitor.start_requested.connect(self.jump_to_start)
        self.monitor.end_requested.connect(self.jump_to_end)
        self.monitor.frame_step.connect(self.step)
        self.monitor.volume_changed.connect(self._preview_volume)
        self.engine.player.positionChanged.connect(self._position)
        self.sequence.positionChanged.connect(self._sequence_position)
        self.engine.player.durationChanged.connect(self._duration)
        self.engine.player.errorOccurred.connect(self._media_error)
        self.engine.player.mediaStatusChanged.connect(self._media_status)
        self.engine.player.playbackStateChanged.connect(self._playback_state)
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
            self.monitor.update_position(pos)
            self.timeline.set_playhead(pos)
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
            self.audio_preview.pause()
            self.sequence.pause()
            self.sequence.seek(ms)
            self.timeline.reveal_playhead(ms, alignment='center')
            self._sync_effects_view()
        else:self.engine.seek(ms)
    def step(self,frames):
        fps=max(1,self.project.get('fps',30));delta=round(frames*1000/fps)
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
        self.audio_preview.pause()
        self.sequence.pause()
        self.engine.audio.setMuted(True)
        self.meter.set_mode('timeline')
        self._scrub_timer.stop()
        self._pending_timeline_seek=None
        self.monitor.set_fx_state('FX · Listos para reproducir')
        self.mode='timeline';self.sequence.seek(ms);self.monitor.update_duration(self.sequence.duration())
        self._sync_effects_view()
    def preview(self,path):
        if not Path(path).is_file():QMessageBox.warning(self,'Archivo no encontrado',path);return
        self.audio_preview.pause()
        self.engine.audio.setMuted(False)
        self.meter.set_mode('project')
        self.monitor.set_fx_state(None)
        self.sequence.pause();self.sequence.enabled=False
        self.timeline.set_playhead(0)
        self.mode='project';self.current_media=path;self.monitor.video.set_active_clip(None);self.engine.load(path)
    def add_selected_to_timeline(self):
        """Ctrl+Enter también usa la misma ruta que doble clic."""
        paths=self.project_panel.selected_paths()
        if not paths:
            item=self.project_panel.list.currentItem()
            if item:
                paths=[item.data(Qt.ItemDataRole.UserRole)]
        self.insert_project_media(paths)

    def insert_project_media(self, paths):
        """Inserta archivos de Proyecto al final de la secuencia, sin solapes.

        Un doble clic debe producir el mismo resultado que soltar el archivo
        sobre una zona libre de V1. El MP4 añade su audio enlazado a A1.
        """
        from services.media_probe import probe
        if not paths:
            return
        start=max([c['start_ms']+c['duration_ms']
                   for c in self.timeline.clips if c.get('kind')=='video']+[0])
        inserted=0
        first_ms=start
        for path in paths:
            if not path or not Path(path).is_file():
                self.statusBar().showMessage('Medio no encontrado; revisa la ruta.',6000)
                continue
            meta=probe(path)
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
    def add_files(self,files):
        for path in files:
            if path not in self.project['media']:self.project['media'].append(path)
        self.project_panel.set_files(self.project['media']);self.dirty=True
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
        self.project['clips']=[dict(c) for c in self.timeline.clips];self.dirty=True
        self.properties_panel.set_selected(self.timeline.selected())
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
        self.monitor.update_duration(0);self.monitor.update_position(0);self.dirty=False
        self.effects_panel.set_selected(None)
        self.audio_effects_panel.set_selected(None)
        self.properties_panel.set_selected(None)
        self.monitor.video.set_active_clip(None)
    def _check_dirty(self):
        if not self.dirty:return True
        ans=QMessageBox.question(self,'Cambios sin guardar','¿Descartar los cambios del proyecto?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        return ans==QMessageBox.StandardButton.Yes
    def new_project(self):
        if not self._check_dirty():return
        self.project=empty_project();self.project_path=None;self._refresh()
    def open_project(self):
        if not self._check_dirty():return
        path,_=QFileDialog.getOpenFileName(self,'Abrir proyecto','','Proyecto ModGames44 (*.mg44)')
        if path:
            try:self.project=load_project(path);self.project_path=path;self._refresh()
            except (OSError,ValueError) as e:QMessageBox.critical(self,'Error de proyecto',str(e))
    def save(self):
        if not self.project_path:return self.save_as()
        try:
            self._clips_changed();save_project(self.project_path,self.project)
            self.dirty=False;self.statusBar().showMessage('Proyecto guardado',3000);return True
        except OSError as e:QMessageBox.critical(self,'Error al guardar',str(e));return False
    def save_as(self):
        path,_=QFileDialog.getSaveFileName(self,'Guardar proyecto','','Proyecto ModGames44 (*.mg44)')
        if path:self.project_path=str(Path(path).with_suffix('.mg44'));return self.save()
        return False
    def autosave(self):
        if self.project_path and self.dirty:
            try:self._clips_changed();save_project(self.project_path+'.autosave',self.project)
            except OSError as e:self.statusBar().showMessage(f'Error autoguardado: {e}',10000)
    def closeEvent(self,event):
        if not self._check_dirty():event.ignore();return
        self.audio_preview.shutdown()
        self.settings.setValue('geometry',self.saveGeometry())
        self.workspaces.save_active()
        super().closeEvent(event)
