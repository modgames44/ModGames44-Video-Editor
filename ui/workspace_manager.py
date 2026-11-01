"""Dos distribuciones de docks reales: Qt conserva un único motor multimedia.

Se guardan y restauran estados por espacio de trabajo, no por archivo de video.
El tamaño inicial se calcula a partir de los píxeles lógicos de la ventana.
"""
from PySide6.QtCore import QObject, Signal, Qt, QTimer
from core.workspaces import WORKSPACES, WORKSPACE_STATE_VERSION, normalized_workspace
from ui.responsive_rules import layout_metrics


class WorkspaceManager(QObject):
    changed = Signal(str)

    def __init__(self, window, docks, settings):
        super().__init__(window)
        self.window = window
        self.docks = docks
        self.settings = settings
        self.active = None
        self._pending_default = False

    @staticmethod
    def _state_key(key):
        # Cambia de versión al cambiar la composición; evita cargar una
        # geometría obsoleta que dejaría paneles de 150px como en v0.4.2.
        return f'workspaces/v{WORKSPACE_STATE_VERSION}/{key}/state'

    def save_active(self):
        if self.active in WORKSPACES:
            self.settings.setValue(self._state_key(self.active),
                                   self.window.saveState(WORKSPACE_STATE_VERSION))

    def activate(self, key, save_previous=True):
        key = normalized_workspace(key)
        if key == self.active:
            return
        if save_previous:
            self.save_active()
        self._apply_default(key)
        saved = self.settings.value(self._state_key(key))
        if saved is not None:
            try:
                restored = self.window.restoreState(saved, WORKSPACE_STATE_VERSION)
            except (TypeError, ValueError, RuntimeError):
                restored = False
            if not restored:
                self.settings.remove(self._state_key(key))
                saved = None
                self._apply_default(key)
        self.active = key
        self.settings.setValue('workspaces/active', key)
        self.changed.emit(key)
        if saved is None:
            # Además de primer arranque, se actualiza tras mostrar ventana.
            self._pending_default = True
            QTimer.singleShot(0, lambda selected=key: self._resize_defaults(selected))

    def reset_active(self):
        if self.active not in WORKSPACES:
            return
        key = self.active
        self.settings.remove(self._state_key(key))
        self._apply_default(key)
        self._pending_default = True
        QTimer.singleShot(0, lambda selected=key: self._resize_defaults(selected))
        self.changed.emit(key)

    def _apply_default(self, key):
        window = self.window
        spec = WORKSPACES[key]
        for dock in self.docks.values():
            window.removeDockWidget(dock)
            dock.setFloating(False)
            dock.hide()

        def get(name):
            return self.docks[name]

        L = Qt.DockWidgetArea.LeftDockWidgetArea
        R = Qt.DockWidgetArea.RightDockWidgetArea
        B = Qt.DockWidgetArea.BottomDockWidgetArea
        H = Qt.Orientation.Horizontal
        V = Qt.Orientation.Vertical
        window.addDockWidget(L, get(spec.left_top))
        window.splitDockWidget(get(spec.left_top), get(spec.left_bottom), V)
        window.addDockWidget(R, get(spec.right_top))
        window.splitDockWidget(get(spec.right_top), get(spec.right_bottom), V)
        if spec.right_extra:
            window.splitDockWidget(get(spec.right_bottom), get(spec.right_extra), V)
        if spec.bottom_left:
            window.addDockWidget(B, get(spec.bottom_left))
            window.splitDockWidget(get(spec.bottom_left), get(spec.bottom_main), H)
        else:
            window.addDockWidget(B, get(spec.bottom_main))

        # IA disponible como pestaña optativa pero nunca creada dos veces.
        ai = get('Asistente IA')
        window.tabifyDockWidget(get('Efectos (futuro)'), ai)
        for name, dock in self.docks.items():
            if name not in spec.hidden:
                dock.show()
        ai.hide()
        for name in spec.hidden:
            get(name).hide()

    def _resize_defaults(self, key):
        if self.active != key:
            return
        window = self.window
        spec = WORKSPACES[key]
        if hasattr(window, 'isVisible') and not window.isVisible():
            return
        width, height = window.width(), window.height()
        metrics = layout_metrics(width, height)
        H = Qt.Orientation.Horizontal
        V = Qt.Orientation.Vertical
        try:
            window.resizeDocks([self.docks[spec.left_top]], [metrics.left], H)
            window.resizeDocks([self.docks[spec.right_top]], [metrics.right], H)
            window.resizeDocks([self.docks[spec.bottom_main]], [metrics.timeline_height], V)
            if key == 'neon':
                window.resizeDocks([self.docks[spec.left_top], self.docks[spec.left_bottom]],
                                   [max(200, round(height * .65)), max(120, round(height * .2))], V)
                window.resizeDocks([self.docks[spec.right_top], self.docks[spec.right_bottom],
                                    self.docks[spec.right_extra]],
                                   [max(180, round(height * .36)),
                                    max(150, round(height * .30)),
                                    max(120, round(height * .20))], V)
            else:
                window.resizeDocks([self.docks[spec.left_top], self.docks[spec.left_bottom]],
                                   [max(160, round(height * .42)),
                                    max(150, round(height * .39))], V)
                window.resizeDocks([self.docks[spec.right_top], self.docks[spec.right_bottom]],
                                   [max(180, round(height * .52)),
                                    max(140, round(height * .27))], V)
                window.resizeDocks([self.docks[spec.bottom_left], self.docks[spec.bottom_main]],
                                   [105, max(340, width - 200)], H)
            self._pending_default = False
        except (TypeError, ValueError, RuntimeError):
            # QMainWindow podrá recalcular tras recibir su primer showEvent.
            pass
