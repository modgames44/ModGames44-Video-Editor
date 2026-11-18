"""Asistente IA: propuestas, silencios y aplicación de planes.

Métodos movidos sin cambios desde ui/main_window.py (v0.6.6).
"""
import copy
import hashlib
import json
from PySide6.QtWidgets import (QMessageBox)
from ai.operations import prepare_plan, PlanError
from ai.local_commands import parse_local
from ai.openai_planner import propose as cloud_propose
from ai.silence import analyze_silences, silence_plan



class AIActionsMixin:
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
