"""Acceso compacto a efectos realmente implementados.

El panel es un navegador, NO duplica ni simula el render de efectos.
Los botones emiten la familia correspondiente y se reutilizan los controles
existentes en EffectsPanel / AudioEffectsPanel.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QToolButton, QSizePolicy, QScrollArea


class QuickEffectsPanel(QWidget):
    openRequested = Signal(str)
    # Usar únicamente efectos existentes y conectados al motor.
    ITEMS = (
        ('◉', 'Corrección de color', 'color', 'Brillo, contraste y saturación'),
        ('⌗', 'Zoom', 'zoom', 'Zoom y fotogramas clave'),
        ('▤', 'Censura', 'censor', 'Desenfoque o mosaico en una región'),
        ('◷', 'Velocidad', 'speed', 'Cámara lenta y rápida'),
        ('♫', 'Audio y voz', 'voice', 'Perfiles de voz, volumen y normalización'),
        ('≈', 'Reducir ruido', 'noise', 'Reducir ruido de audio al exportar'),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('QuickEffectsPanel')
        self.columns = 2
        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 10, 9, 8)
        outer.setSpacing(8)
        self.heading = QLabel('ACCESO RÁPIDO')
        self.heading.setObjectName('SectionOverline')
        outer.addWidget(self.heading)
        scroll = QScrollArea()
        scroll.setObjectName('QuickEffectsScroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll, 1)
        self.holder = QWidget()
        self.holder.setObjectName('QuickEffectsHolder')
        self.layout_grid = QGridLayout(self.holder)
        self.layout_grid.setContentsMargins(0, 0, 0, 0)
        self.layout_grid.setSpacing(8)
        self.buttons = []
        for symbol, label, key, hint in self.ITEMS:
            b = QToolButton(self.holder)
            b.setObjectName('EffectTile')
            b.setProperty('effectKey', key)
            b.setText(symbol + '\n' + label)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            b.setToolTip(hint)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(72)
            b.clicked.connect(lambda checked=False, kind=key: self.openRequested.emit(kind))
            self.buttons.append(b)
        scroll.setWidget(self.holder)
        self.set_columns(2)

    def set_columns(self, count):
        count = max(1, min(3, int(count)))
        if count == self.columns and self.layout_grid.count():
            return
        self.columns = count
        for button in self.buttons:
            self.layout_grid.removeWidget(button)
        for i, button in enumerate(self.buttons):
            self.layout_grid.addWidget(button, i // count, i % count)
        self.layout_grid.setRowStretch((len(self.buttons) + count - 1)//count, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # El QDockWidget puede ser redimensionado manualmente; el grid se
        # adapta al ancho REAL del panel y no depende de la resolución física.
        width = self.width()
        self.set_columns(3 if width >= 410 else 2 if width >= 225 else 1)
