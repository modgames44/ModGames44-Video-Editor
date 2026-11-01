"""Reglas de maquetación, independientes de Qt y del modelo del proyecto.

Todas las medidas son píxeles lógicos de Qt (DPI-aware), no píxeles físicos.
La Timeline nunca cambia de escala temporal al cambiar de resolución.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutMetrics:
    tier: str
    left: int
    right: int
    timeline_height: int
    quick_columns: int
    compact_labels: bool
    project_icon_width: int


def layout_metrics(width: int, height: int) -> LayoutMetrics:
    width = max(600, int(width))
    height = max(480, int(height))
    if width < 1150:
        tier, left_ratio, right_ratio, quick, compact, icon = ('compact', .205, .225, 2, True, 104)
    elif width < 1650:
        tier, left_ratio, right_ratio, quick, compact, icon = ('standard', .215, .23, 2, False, 120)
    else:
        tier, left_ratio, right_ratio, quick, compact, icon = ('wide', .235, .235, 3, False, 148)
    left = max(175, round(width * left_ratio))
    right = max(195, round(width * right_ratio))
    # Prioridad absoluta al monitor central: no forzar una anchura superior
    # a la disponible en pantallas más pequeñas.
    central_min = max(300, min(620, round(width * .42)))
    overflow = max(0, left + right + central_min - width)
    if overflow:
        left = max(165, left - overflow // 2)
        right = max(185, right - (overflow - overflow // 2))
    timeline_height = max(190, min(480, round(height * (.34 if height < 800 else .405))))
    return LayoutMetrics(tier, left, right, timeline_height, quick, compact, icon)


def media_columns(panel_width: int, desired_card_width: int = 150) -> int:
    return max(1, min(5, int(max(1, panel_width - 20) // max(1, desired_card_width))))
