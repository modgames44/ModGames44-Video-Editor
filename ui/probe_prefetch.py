"""Análisis de medios en segundo plano con respuesta en el hilo de la interfaz.

`probe()` lanza FFmpeg y puede tardar hasta 12 s (disco de red, USB lento).
Antes se hacía en el hilo de la interfaz al insertar medios y la ventana se
congelaba. Aquí se analiza en un hilo y el callback se ejecuta en el hilo de
Qt mediante una señal (conexión en cola automática).
"""
import itertools
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from core.error_log import get_logger
from services.media_probe import probe_many

_log = get_logger('probe')


class ProbePrefetcher(QObject):
    _done = Signal(int, object)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='probe')
        self._callbacks = {}
        self._ids = itertools.count(1)
        self._done.connect(self._deliver)

    def run(self, paths, callback=None):
        """Analiza `paths`; luego llama a `callback({ruta: meta})` en el hilo UI."""
        paths = [str(p) for p in paths if p]
        token = next(self._ids)
        self._callbacks[token] = callback
        if len(self._callbacks) == 1:
            self.busy_changed.emit(True)

        def work():
            try:
                results = probe_many(paths)
            except Exception:  # noqa: BLE001 - la interfaz siempre recibe respuesta
                _log.exception('Error analizando medios')
                results = {}
            self._done.emit(token, results)

        try:
            self._pool.submit(work)
        except RuntimeError:  # el pool ya se cerró (aplicación saliendo)
            self._callbacks.pop(token, None)

    def _deliver(self, token, results):
        callback = self._callbacks.pop(token, None)
        if not self._callbacks:
            self.busy_changed.emit(False)
        if callback is not None:
            callback(results)

    def shutdown(self):
        self._callbacks.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)
