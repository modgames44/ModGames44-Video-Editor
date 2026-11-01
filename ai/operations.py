"""Validación, simulación y ejecución atómica de propuestas de edición de IA.

NO importa Qt, NO ejecuta código remoto, NO altera archivos originales.
El modelo puede proponer únicamente el vocabulario de operaciones definido aquí.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from timeline.model import active, end, close_gap
from timeline.editing import split_at, linked_group, remove_linked

MAX_OPERATIONS = 80
ACTIONS = {'cut', 'remove_range', 'move', 'close_gaps', 'seek'}

class PlanError(ValueError):
    pass


def _time(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PlanError('Los tiempos deben ser números finitos en milisegundos.')
    result = int(round(value))
    if result < 0 or result > 24 * 60 * 60 * 1000:
        raise PlanError('Tiempo fuera del rango de 0 a 24 horas.')
    return result


def _clip(clips, clip_id, time_ms=None):
    if clip_id is not None:
        if not isinstance(clip_id, str):
            raise PlanError('ID de clip no válido.')
        clip = next((c for c in clips if c['id'] == clip_id), None)
        if clip is None:
            raise PlanError(f'El clip {clip_id[:12]} ya no existe.')
        return clip
    if time_ms is None:
        raise PlanError('Falta posición o clip de destino.')
    clip = active(clips, time_ms, 'video') or active(clips, time_ms, 'audio')
    if clip is None:
        raise PlanError(f'No hay clip en {time_ms / 1000:.3f} s.')
    return clip


def _one(clips, op, messages):
    if not isinstance(op, dict) or op.get('type') not in ACTIONS:
        raise PlanError('La IA solicitó una operación no autorizada.')
    name = op['type']
    clip_id = op.get('clip_id')
    if name == 'cut':
        t = _time(op.get('time_ms'))
        clip = _clip(clips, clip_id, t)
        if not clip['start_ms'] < t < end(clip):
            raise PlanError('El corte debe estar dentro del clip.')
        if split_at(clips, clip['id'], t) is None:
            raise PlanError('No pudo dividirse el clip.')
        messages.append(f'Cortar en {t/1000:.3f} s: {clip["path"].split("/")[-1].split(chr(92))[-1]}')
        return None
    if name == 'remove_range':
        start = _time(op.get('start_ms'))
        finish = _time(op.get('end_ms'))
        if finish - start < 20:
            raise PlanError('El intervalo para eliminar es demasiado corto.')
        clip = _clip(clips, clip_id, start)
        if not (clip['start_ms'] <= start < finish <= end(clip)):
            raise PlanError('Para eliminar un intervalo debe estar contenido en un solo segmento.')
        # Primero separar la parte derecha; luego el segmento que se va a borrar.
        if finish < end(clip):
            if split_at(clips, clip['id'], finish) is None:
                raise PlanError('No pudo separarse el final del intervalo.')
        if start > clip['start_ms']:
            right_id = split_at(clips, clip['id'], start)
            if right_id is None:
                raise PlanError('No pudo separarse el inicio del intervalo.')
            clip_id = right_id
        else:
            clip_id = clip['id']
        removed = remove_linked(clips, {clip_id})
        if not removed:
            raise PlanError('No se eliminó el segmento esperado.')
        messages.append(f'Eliminar contenido entre {start/1000:.3f} y {finish/1000:.3f} s (deja hueco).')
        return None
    if name == 'move':
        position = _time(op.get('start_ms'))
        clip = _clip(clips, clip_id)
        partners = linked_group(clips, clip['id'])
        delta = position - clip['start_ms']
        if any(c['start_ms'] + delta < 0 for c in partners):
            raise PlanError('El movimiento sobrepasa 00:00 en un clip vinculado.')
        for c in partners:
            c['start_ms'] += delta
        messages.append(f'Mover clip a {position/1000:.3f} s (y su audio vinculado).')
        return None
    if name == 'close_gaps':
        for track in range(3):
            close_gap(clips, track, 'video')
        for clip in clips:
            if clip.get('kind') == 'video':
                for partner in linked_group(clips, clip['id']):
                    if partner['id'] != clip['id'] and partner.get('kind') == 'audio':
                        partner['start_ms'] = clip['start_ms']
        for track in range(3):
            independent = [c for c in clips if c.get('kind') == 'audio' and not c.get('link') and c.get('track') == track]
            close_gap(independent, track, 'audio')
        messages.append('Cerrar espacios entre clips en todas las pistas.')
        return None
    if name == 'seek':
        t = _time(op.get('time_ms'))
        messages.append(f'Mover cabezal a {t/1000:.3f} s.')
        return t
    raise PlanError('Operación desconocida.')


def simulate(clips, operations):
    """Devuelve (copia_de_clips, nuevo_cabezal, descripción). No muta entrada."""
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise PlanError(f'Se requieren entre 1 y {MAX_OPERATIONS} acciones.')
    result = copy.deepcopy(clips)
    messages = []
    seek = None
    for op in operations:
        requested = _one(result, op, messages)
        if requested is not None:
            seek = requested
    if len(result) > 20000:
        raise PlanError('Plan excede el límite de segmentos.')
    return result, seek, messages


def prepare_plan(payload, clips):
    """Verifica respuesta incluso cuando viene de un modelo externo no confiable."""
    if not isinstance(payload, dict):
        raise PlanError('La respuesta debe ser un objeto JSON.')
    operations = payload.get('operations')
    result, seek, description = simulate(clips, operations)
    explanation = payload.get('explanation', '')
    if not isinstance(explanation, str):
        explanation = ''
    return {'operations': operations, 'preview_clips': result,
            'seek_ms': seek, 'messages': description, 'explanation': explanation[:1200]}
