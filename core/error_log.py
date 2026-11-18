"""Registro de errores en archivo, también en el ejecutable sin consola.

Ruta: %LOCALAPPDATA%/ModGames44/VideoEditor/logs/editor.log (o ~/.cache en
otros sistemas). Rota a 1 MB con 3 copias. Las excepciones no capturadas en
slots de Qt quedan registradas en lugar de perderse en un stderr invisible.
"""
import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

LOGGER_NAME = 'modgames44'


def log_dir():
    base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.cache'))
    return base / 'ModGames44' / 'VideoEditor' / 'logs'


def get_logger(name=None):
    return logging.getLogger(LOGGER_NAME + ('.' + name if name else ''))


def install(on_unhandled=None):
    """Configura el log y los ganchos globales. Devuelve la ruta del archivo."""
    logger = get_logger()
    logger.setLevel(logging.INFO)
    path = log_dir() / 'editor.log'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000,
                                                       backupCount=3, encoding='utf-8')
    except OSError:
        handler = logging.StreamHandler()
        path = None
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    if not any(type(h) is type(handler) for h in logger.handlers):
        logger.addHandler(handler)

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical('Excepción no controlada', exc_info=(exc_type, exc, tb))
        if on_unhandled is not None:
            try:
                on_unhandled(exc_type, exc)
            except Exception:  # noqa: BLE001 - el aviso nunca debe fallar
                pass

    def thread_hook(args):
        logger.critical('Excepción en hilo %s', getattr(args.thread, 'name', '?'),
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = hook
    threading.excepthook = thread_hook
    return path


_last_logged = {}
_throttle_lock = threading.Lock()


def exception_throttled(logger, key, message, interval=10.0):
    """`logger.exception` como máximo una vez cada `interval` s por `key`.

    El monitor puede fallar en cada fotograma (30/s): sin límite llenaría
    el log en segundos.
    """
    import time
    now = time.monotonic()
    with _throttle_lock:
        if now - _last_logged.get(key, -interval) < interval:
            return
        _last_logged[key] = now
    logger.exception(message)
