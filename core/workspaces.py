"""Metadatos de espacios de trabajo; persisten separadamente del proyecto .mg44."""
from dataclasses import dataclass

WORKSPACE_STATE_VERSION = 4  # el esquema visual de v0.4.2 ya no es compatible


@dataclass(frozen=True)
class WorkspaceSpec:
    key: str
    label: str
    description: str
    left_top: str
    left_bottom: str
    right_top: str
    right_bottom: str
    bottom_left: str
    bottom_main: str
    hidden: tuple[str, ...] = ()
    right_extra: str = ''


WORKSPACES = {
    'neon': WorkspaceSpec(
        'neon','Cyber Neon',
        'Herramientas y efectos accesibles mediante pestañas; editor despejado.',
        'Proyecto','Herramientas','Efectos (futuro)','Propiedades',
        '','Timeline',('Asistente IA',),'Audio Meter',
    ),
    'studio': WorkspaceSpec(
        'studio','Cyber Studio',
        'Pestañas compactas de Proyecto, Efectos y Textos; Timeline protagonista.',
        'Efectos (futuro)','Proyecto','Propiedades','Audio Meter',
        'Herramientas','Timeline',('Asistente IA',),
    ),
}


def normalized_workspace(key):
    return key if key in WORKSPACES else 'studio'
