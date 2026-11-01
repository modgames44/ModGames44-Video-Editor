"""Órdenes de edición simples disponibles sin conexión ni API.
No simula comprender tareas semánticas avanzadas.
"""
import re
import unicodedata
from ai.operations import PlanError

CLOCK = r'(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?'
NUMBER = r'\d+(?:[.,]\d+)?'
TIME = rf'(?:{CLOCK}|{NUMBER}\s*(?:segundos?|segs?|s)?)'


def parse_time(text):
    raw = str(text).strip().lower().replace(',', '.')
    raw = re.sub(r'\s*(?:segundos?|segs?|s)\s*$', '', raw)
    if ':' in raw:
        parts = raw.split(':')
        if not 2 <= len(parts) <= 3:
            raise PlanError('Formato de tiempo incorrecto.')
        numbers = [float(p) for p in parts]
        if any(n < 0 for n in numbers) or numbers[-1] >= 60 or (len(parts) == 3 and numbers[-2] >= 60):
            raise PlanError('Tiempo fuera del rango válido.')
        secs = 0
        for number in numbers:
            secs = secs * 60 + number
    else:
        secs = float(raw)
    if secs < 0 or secs > 86400:
        raise PlanError('Tiempo fuera del rango 0–24 horas.')
    return round(secs * 1000)


def _clean(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')


def parse_local(query, selected_id=None):
    q = _clean(query.strip())
    if not q:
        raise PlanError('Introduce una instrucción.')
    match = re.search(rf'(?:elimina|quita|borra)\s+(?:el\s+fragmento\s+)?(?:desde\s+|entre\s+|del\s+segundo\s+|de\s+)?({TIME})\s+(?:hasta|a|y|al)\s+({TIME})', q)
    if match:
        return {'explanation': 'Eliminar tramo (sin cerrar el hueco).', 'operations': [
            {'type': 'remove_range', 'clip_id': selected_id,
             'start_ms': parse_time(match.group(1)), 'end_ms': parse_time(match.group(2))}]}
    match = re.search(rf'(?:corta|divide|haz\s+un\s+corte)(?:\s+el\s+video)?(?:\s+en|\s+al|\s+a)?\s+({TIME})', q)
    if match:
        return {'explanation': 'Cortar clip y audio vinculado.', 'operations': [
            {'type': 'cut', 'time_ms': parse_time(match.group(1)), 'clip_id': selected_id}]}
    match = re.search(rf'(?:mueve|desplaza)(?:\s+el\s+clip(?:\s+seleccionado)?)?\s+(?:a|al|hasta)\s+({TIME})', q)
    if match:
        if selected_id is None:
            raise PlanError('Selecciona primero el clip que deseas mover.')
        return {'explanation': 'Mover clip y audio vinculado.', 'operations': [
            {'type': 'move', 'clip_id': selected_id, 'start_ms': parse_time(match.group(1))}]}
    if any(p in q for p in ('cierra huecos','cerrar huecos','cierra espacios','junta los clips','elimina espacios vacios')):
        return {'explanation': 'Compactar las pistas manteniendo vínculos.', 'operations': [{'type': 'close_gaps'}]}
    match = re.search(rf'(?:ve|ir|coloca el cabezal|mueve el cabezal|salta)\s+(?:a|al|hasta|en)\s+({TIME})', q)
    if match:
        return {'explanation': 'Desplazar el cabezal.', 'operations': [{'type': 'seek', 'time_ms': parse_time(match.group(1))}]}
    raise PlanError('Orden no reconocida sin conexión. Prueba «corta en 00:05», «elimina desde 00:05 hasta 00:10», «mueve el clip a 00:20» o activa la API.')
