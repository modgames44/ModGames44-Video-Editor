"""Barra compacta de herramientas con iconos originales y modos persistentes.

Los modos (V, C, recortar) afectan a las interacciones del ratón en la Timeline.
Las acciones (Supr, deshacer, etc.) se solicitan al controlador, no editan la UI.
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QToolButton, QButtonGroup

ICON_DIR = Path(__file__).resolve().parent.parent / 'assets' / 'icons'


class ToolsPanel(QWidget):
    toolChanged = Signal(str)
    editRequested = Signal(str)
    snapChanged = Signal(bool)

    MODES = (
        ('select', 'Seleccionar y mover clips', 'V'),
        ('razor', 'Cuchilla: haz clic en el clip para dividirlo', 'C'),
        ('trim_start', 'Recortar inicio: arrastra el borde inicial', '['),
        ('trim_end', 'Recortar final: arrastra el borde final', ']'),
    )
    ACTIONS = (
        ('delete', 'Eliminar clips seleccionados', 'Supr'),
        ('close_gaps', 'Cerrar huecos en las pistas', ''),
        ('undo', 'Deshacer', 'Ctrl+Z'),
        ('redo', 'Rehacer', 'Ctrl+Y'),
        ('unlink', 'Desvincular vídeo y audio seleccionados', ''),
    )

    def __init__(self):
        super().__init__()
        self.setObjectName('ToolsPanel')
        self.setMinimumWidth(95)
        self.setMaximumWidth(170)
        self.buttons = {}
        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.setExclusive(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(7, 7, 7, 8)
        root.setSpacing(8)
        root.addWidget(QLabel('Herramientas'))
        grid = QGridLayout()
        grid.setSpacing(5)
        root.addLayout(grid)

        entries = self.MODES + self.ACTIONS
        for index, (name, description, shortcut) in enumerate(entries):
            btn = QToolButton(self)
            btn.setObjectName('Tool_' + name)
            btn.setFixedSize(40, 40)
            btn.setIconSize(QSize(25, 25))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setAutoRaise(False)
            btn.setToolTip(description + (f' ({shortcut})' if shortcut else ''))
            icon_file = ICON_DIR / (name + '.png')
            if icon_file.is_file():
                btn.setIcon(QIcon(str(icon_file)))
            else:
                # Si los assets no están presentes al empaquetar, mantener la acción accesible.
                btn.setText(name[:2].upper())
            if index < len(self.MODES):
                btn.setCheckable(True)
                self.mode_buttons.addButton(btn)
                btn.clicked.connect(lambda checked=False, tool=name: self.toolChanged.emit(tool))
            else:
                btn.clicked.connect(lambda checked=False, action=name: self.editRequested.emit(action))
            self.buttons[name] = btn
            grid.addWidget(btn, index // 2, index % 2)

        snap = QToolButton(self)
        snap.setObjectName('Tool_snap')
        snap.setFixedSize(40, 40)
        snap.setIconSize(QSize(25, 25))
        snap.setCheckable(True)
        snap.setChecked(True)
        snap.setToolTip('Imán (Snapping): activar/desactivar')
        snap_icon = ICON_DIR / 'snap.png'
        if snap_icon.is_file(): snap.setIcon(QIcon(str(snap_icon)))
        else: snap.setText('SN')
        snap.toggled.connect(self.snapChanged.emit)
        self.buttons['snap'] = snap
        grid.addWidget(snap, 4, 1)
        self.buttons['select'].setChecked(True)

        root.addStretch(1)
        root.addWidget(QLabel('V · Selección\nC · Cuchilla'))
        # El tema compartido se aplica globalmente en ui/theme_manager.py.

    def set_mode(self, mode):
        """Sincroniza la selección visual desde atajos o desde la Timeline."""
        button = self.buttons.get(mode)
        if button is not None and button.isCheckable():
            button.setChecked(True)
