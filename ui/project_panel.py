"""Biblioteca de medios con miniaturas adaptativas, filtro y arrastre Qt URI."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QMimeData, QSize, QPoint
from PySide6.QtGui import QDrag, QIcon, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QListWidget,
                               QListWidgetItem, QHBoxLayout, QFileDialog,
                               QComboBox, QMenu, QAbstractItemView, QLineEdit,
                               QLabel, QSizePolicy, QApplication)
from ui.responsive_rules import media_columns


class MediaList(QListWidget):
    """Arrastre explícito también en IconMode/Movement.Static de QListWidget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_origin=None

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._drag_origin=(event.position().toPoint()
                           if event.button()==Qt.MouseButton.LeftButton else None)

    def mouseReleaseEvent(self, event):
        self._drag_origin=None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_origin is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint()-self._drag_origin).manhattanLength()
                    >= QApplication.startDragDistance()):
            # Evitar depender del drag automático que se comporta distinto
            # entre las vistas de miniaturas y lista cuando Movement=Static.
            self._drag_origin=None
            self.startDrag(Qt.DropAction.CopyAction)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def startDrag(self, supportedActions):
        from PySide6.QtCore import QUrl
        chosen=self.selectedItems()
        if not chosen and self.currentItem() is not None:
            chosen=[self.currentItem()]
        paths=[str(item.data(Qt.ItemDataRole.UserRole)) for item in chosen
               if item.data(Qt.ItemDataRole.UserRole)
               and Path(str(item.data(Qt.ItemDataRole.UserRole))).is_file()]
        if not paths:
            return
        mime=QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        mime.setText('\n'.join(paths))
        mime.setData('application/x-modgames44-media-paths',
                     '\n'.join(paths).encode('utf-8'))
        drag=QDrag(self)
        drag.setMimeData(mime)
        icon=chosen[0].icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(96,54))
            drag.setHotSpot(QPoint(18,18))
        drag.exec(Qt.DropAction.CopyAction)


class ProjectPanel(QWidget):
    selected = Signal(str)
    add_files = Signal(list)
    remove_files = Signal(list)
    insert_files = Signal(list)  # Doble clic / menú contextual / Enter

    def __init__(self):
        super().__init__()
        self.setObjectName('ProjectPanel')
        self._all_files = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 9, 9, 9)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(5)
        self.import_button = QPushButton('＋ Importar')
        self.import_button.setObjectName('ImportButton')
        self.import_button.clicked.connect(self.import_files)
        row.addWidget(self.import_button)
        self.mode = QComboBox()
        self.mode.addItems(['Miniaturas', 'Lista'])
        self.mode.setToolTip('Cambiar entre miniaturas y lista')
        self.mode.currentIndexChanged.connect(self.set_view)
        row.addWidget(self.mode)
        self.remove_button = QPushButton('✕')
        self.remove_button.setObjectName('RemoveMediaButton')
        self.remove_button.setToolTip('Eliminar selección del proyecto (sin borrar archivos del disco)')
        self.remove_button.clicked.connect(self.remove_selected)
        row.addWidget(self.remove_button)
        lay.addLayout(row)
        self.search = QLineEdit()
        self.search.setObjectName('MediaSearch')
        self.search.setPlaceholderText('⌕  Buscar en proyecto...')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)
        self.list = MediaList()
        self.list.setObjectName('ProjectMediaList')
        self.list.setDragEnabled(True)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.list.setUniformItemSizes(False)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setWrapping(True)
        self.list.setSpacing(7)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.currentItemChanged.connect(self._selected)
        self.list.itemDoubleClicked.connect(self._insert_item)
        lay.addWidget(self.list, 1)
        from services.media_visuals import VisualCache
        self.visuals = VisualCache(self)
        self.visuals.updated.connect(self._thumbnail_ready)
        self.footer = QLabel('0 elementos · Doble clic o arrastra a Timeline')
        self.footer.setObjectName('SecondaryHint')
        lay.addWidget(self.footer)
        self._refresh_grid()

    def import_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, 'Importar multimedia', '',
            'Multimedia (*.mp4 *.mov *.mkv *.avi *.webm *.mp3 *.wav *.flac *.png *.jpg *.jpeg);;Todos (*.*)')
        if files:
            self.add_files.emit(files)

    def _thumbnail_ready(self, path):
        img = self.visuals.images.get(path)
        if img is None or img.isNull():
            return
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(QIcon(QPixmap.fromImage(img)))

    def _refresh_grid(self):
        if self.mode.currentIndex() != 0:
            self.list.setIconSize(QSize(98, 56))
            self.list.setGridSize(QSize())
            return
        width = max(150, self.list.viewport().width())
        cols = media_columns(width, 140)
        card_w = max(96, min(196, (width - 16 - cols * 8) // cols))
        img_w = max(76, card_w - 12)
        self.list.setIconSize(QSize(img_w, max(45, int(img_w * 9 / 16))))
        self.list.setGridSize(QSize(card_w + 6, max(110, int(img_w * 9 / 16) + 43)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_grid()

    def set_view(self, index):
        self.list.setViewMode(QListWidget.ViewMode.ListMode if index else QListWidget.ViewMode.IconMode)
        self.list.setWrapping(index == 0)
        self._refresh_grid()

    def set_files(self, files):
        self._all_files = list(files)
        self.list.blockSignals(True)
        self.list.clear()
        for path in self._all_files:
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(str(path))
            if not Path(path).is_file():
                item.setText('⚠ ' + Path(path).name)
            self.list.addItem(item)
            img = self.visuals.images.get(path)
            if img is not None and not img.isNull():
                item.setIcon(QIcon(QPixmap.fromImage(img)))
            else:
                self.visuals.request(path)
        self.list.blockSignals(False)
        self._apply_filter(self.search.text())
        self._refresh_grid()

    def _apply_filter(self, text):
        query = text.strip().casefold()
        visible = 0
        for i in range(self.list.count()):
            item = self.list.item(i)
            show = query in item.text().casefold()
            item.setHidden(not show)
            visible += show
        self.footer.setText(f'{visible} de {len(self._all_files)} elementos  ·  Doble clic o arrastra')

    def _selected(self, current, previous):
        if current:
            self.selected.emit(current.data(Qt.ItemDataRole.UserRole))

    def selected_paths(self):
        return [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.list.selectedItems()
                if item.data(Qt.ItemDataRole.UserRole)]

    def _insert_item(self, item):
        """DoubleClick: añadir el medio, no sólo previsualizarlo."""
        if item is not None:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and Path(path).is_file():
                self.insert_files.emit([str(path)])

    def insert_selected(self):
        paths = [path for path in self.selected_paths() if Path(path).is_file()]
        if paths:
            self.insert_files.emit(paths)

    def remove_selected(self):
        paths = self.selected_paths()
        if paths:
            self.remove_files.emit(paths)

    def _context_menu(self, pos):
        target = self.list.itemAt(pos)
        if target is None:
            return
        if not target.isSelected():
            self.list.setCurrentItem(target)
        menu = QMenu(self)
        menu.addAction('Añadir a la Timeline', self.insert_selected)
        menu.addSeparator()
        menu.addAction('Eliminar del proyecto', self.remove_selected)
        menu.exec(self.list.mapToGlobal(pos))
