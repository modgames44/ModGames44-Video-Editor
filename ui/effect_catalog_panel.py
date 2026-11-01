"""Catálogo compacto, como el panel de efectos de Premiere, sin acciones falsas."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem, QLabel


class EffectCatalogPanel(QWidget):
    openRequested = Signal(str)
    CATEGORIES = (
        ('Efectos de video', (
            ('Corrección de color', 'color'),
            ('Zoom y transformación', 'zoom'),
            ('Desenfoque y censura', 'censor'),
            ('Cámara lenta / rápida', 'speed'),
        )),
        ('Efectos de audio', (
            ('Volumen y normalización', 'voice'),
            ('Voz tipo podcast', 'voice'),
            ('Ecualización de voz', 'voice'),
            ('Reducción de ruido', 'noise'),
        )),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('EffectCatalogPanel')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 9, 8, 8)
        lay.setSpacing(7)
        self.search = QLineEdit()
        self.search.setPlaceholderText('⌕  Buscar efectos...')
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        lay.addWidget(self.tree, 1)
        for group, entries in self.CATEGORIES:
            parent_item = QTreeWidgetItem([group]); self.tree.addTopLevelItem(parent_item)
            parent_item.setExpanded(True)
            for title, key in entries:
                child = QTreeWidgetItem([title]); child.setData(0, 256, key)
                parent_item.addChild(child)
        self.tree.itemDoubleClicked.connect(self._open_item)
        self.tree.itemActivated.connect(self._open_item)
        hint = QLabel('Doble clic para abrir los controles del efecto.')
        hint.setObjectName('SecondaryHint')
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.search.textChanged.connect(self._filter)

    def _open_item(self, item, col=0):
        key = item.data(0, 256)
        if key:
            self.openRequested.emit(str(key))

    def _filter(self, text):
        text = text.strip().casefold()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            matched = 0
            for j in range(group.childCount()):
                child = group.child(j)
                visible = not text or text in child.text(0).casefold() or text in group.text(0).casefold()
                child.setHidden(not visible)
                matched += visible
            group.setHidden(not matched)
            if text and matched:
                group.setExpanded(True)
