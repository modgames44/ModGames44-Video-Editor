"""Plan de actualización incremental de la escena de la Timeline (sin Qt).

Antes, cada cambio (mover, recortar, un efecto) vaciaba la escena y creaba
de nuevo todos los clips. Con cientos de fragmentos (Quitar silencios) eso
se nota. Este plan indica qué items quitar, cuáles crear y cuáles sólo
reposicionar; el panel aplica el resultado reutilizando los items.
"""
from dataclasses import dataclass, field


@dataclass
class ScenePlan:
    remove: list = field(default_factory=list)   # ids de items a eliminar
    create: list = field(default_factory=list)   # clips sin item
    update: list = field(default_factory=list)   # clips con item reutilizable


def plan_scene_sync(existing, clips):
    """`existing`: {clip_id: kind} de los items actuales."""
    plan = ScenePlan()
    wanted = {}
    for clip in clips:
        wanted[clip['id']] = clip.get('kind', 'video')
    for clip_id, kind in existing.items():
        # Un cambio de tipo (raro) exige otro item: colores y pintura difieren.
        if clip_id not in wanted or wanted[clip_id] != kind:
            plan.remove.append(clip_id)
    removed = set(plan.remove)
    for clip in clips:
        if clip['id'] in existing and clip['id'] not in removed:
            plan.update.append(clip)
        else:
            plan.create.append(clip)
    return plan


def clip_geometry(clip, scale, row_top, track_height, header):
    """(x, y, ancho, alto) del item de un clip; misma fórmula que antes."""
    return (header + clip['start_ms'] / 1000 * scale,
            row_top + 3,
            max(1, clip['duration_ms'] / 1000 * scale),
            track_height - 7)
