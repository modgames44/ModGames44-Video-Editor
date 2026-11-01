"""Escucha de la mezcla REAL de FFmpeg, sincronizada con SequencePlayer.

Qt conserva la salida de vídeo (mutada en Timeline), mientras que un segundo
QMediaPlayer reproduce ventanas WAV de la mezcla filtrada de A1/A2/A3.
Ninguna operación de FFmpeg bloquea el hilo de UI; las ventanas se cachean.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import tempfile
import time

from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from services.preview_audio import (WINDOW_MS, audio_signature, window_bounds,
                                    render_audio_window)
from exporter.hardware import ffmpeg_candidates


class _Results(QObject):
    succeeded = Signal(str, str, int, int)  # clave, ruta, inicio, duración
    failed = Signal(str, str)


class AudioPreview(QObject):
    status = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(.75)
        self.player.setAudioOutput(self.output)
        self._results = _Results(self)
        self._results.succeeded.connect(self._on_ready)
        self._results.failed.connect(self._on_failed)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(self._player_error)
        self._directory = tempfile.TemporaryDirectory(prefix='ModGames44_audio_preview_')
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='ModGamesAudio')
        self._closing = threading.Event()
        self._known = set()
        self._pending = set()
        self._signature = ''
        self._clips = []
        self._total = 0
        self._ffmpeg = None
        self._want = None
        self._requested_seek = None
        self._active_start = None
        self._active_duration = 0
        self._active_key = None
        self._serial = 0
        self._next_sync = 0

    def configure(self, clips, total_ms):
        signature = audio_signature(clips)
        self._clips = copy.deepcopy(clips)
        self._total = max(0, int(total_ms))
        if signature != self._signature:
            self._signature = signature
            self.pause()
            self._active_key = None
            self._active_start = None
            self._known.clear()
            self.player.stop()
            self.status.emit('Se actualizaron los efectos de audio')

    @property
    def is_waiting(self):
        return self._want is not None

    @property
    def has_audio(self):
        return any(c.get('kind') == 'audio' for c in self._clips)

    def _window(self, timeline_ms):
        start, duration = window_bounds(timeline_ms, self._total)
        name = f'{self._signature}_{start}_{duration}.wav'
        return (name, str(Path(self._directory.name) / name), start, duration)

    def _ensure(self, timeline_ms):
        key, path, start, duration = self._window(timeline_ms)
        if duration <= 0:
            return None
        if Path(path).is_file():
            self._known.add(key)
            return key, path, start, duration
        if key not in self._pending:
            self._pending.add(key)
            clips = copy.deepcopy(self._clips)
            ffmpeg = self._ffmpeg
            if ffmpeg is None:
                candidates = ffmpeg_candidates()
                if not candidates:
                    self._pending.discard(key)
                    self.error.emit('FFmpeg no está disponible para previsualizar audio.')
                    return None
                ffmpeg = self._ffmpeg = candidates[0]
            def task():
                try:
                    render_audio_window(clips, start, duration, path, ffmpeg=ffmpeg)
                    if not self._closing.is_set():
                        self._results.succeeded.emit(key, path, start, duration)
                except Exception as exc:
                    if not self._closing.is_set():
                        self._results.failed.emit(key, str(exc))
            self._pool.submit(task)
        return None

    def play(self, position, clips, duration, start_video):
        """La llamada start_video se ejecuta una vez que el WAV puede sonar."""
        self.configure(clips, duration)
        self.pause()
        if not self.has_audio:
            self.status.emit('Secuencia sin pista de audio')
            start_video()
            return
        self._serial += 1
        self._want = (self._serial, int(position), start_video)
        self._prepare_wanted()

    def _prepare_wanted(self):
        if self._want is None:
            return
        _, pos, callback = self._want
        available = self._ensure(pos)
        if available:
            self._activate(available, pos, callback)
        else:
            self.status.emit('Preparando audio con efectos…')

    def _activate(self, window, timeline_ms, callback):
        key, path, start, duration = window
        if self._want is None:
            return
        self._active_key = key
        self._active_start = start
        self._active_duration = duration
        self._requested_seek = (max(0, int(timeline_ms - start)), callback)
        src = QUrl.fromLocalFile(path)
        if self.player.source() != src:
            self.player.stop()
            self.player.setSource(src)
        else:
            self._start_at_seek()

    def _media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                      QMediaPlayer.MediaStatus.BufferedMedia):
            self._start_at_seek()

    def _start_at_seek(self):
        pending, self._requested_seek = self._requested_seek, None
        if pending is None or self._want is None:
            return
        position, callback = pending
        self.player.setPosition(position)
        self.player.play()
        self._want = None
        # Comenzamos el video después de pedir Play en el WAV, no antes de
        # decodificar o renderizar el audio.
        self.status.emit('Vista previa: audio y video con efectos')
        callback()

    def _on_ready(self, key, path, start, duration):
        self._pending.discard(key)
        self._known.add(key)
        if self._want and self._window(self._want[1])[0] == key:
            self._prepare_wanted()

    def _on_failed(self, key, message):
        self._pending.discard(key)
        if self._want and self._window(self._want[1])[0] == key:
            self._want = None
            self.error.emit('No se pudo escuchar el audio procesado: ' + message[:1000])

    def _player_error(self, error, message):
        if message:
            self.error.emit('Reproductor de audio de efectos: ' + message)

    def pause(self):
        self._serial += 1
        self._want = None
        self._requested_seek = None
        self.player.pause()

    def follow(self, timeline_ms, running, resume_video=None, pause_video=None):
        if not running:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            return
        if not self.has_audio or self._active_start is None:
            return
        start = self._active_start
        end = start + self._active_duration
        pos = int(timeline_ms)
        if end - pos < 5000 and pos < self._total - 1:
            self._ensure(min(self._total - 1, end))
        if pos >= end:
            if resume_video and pause_video:
                pause_video()
                self.pause()
                self._want = (self._serial, pos, resume_video)
                self._prepare_wanted()
            return
        now = time.monotonic()
        if now < self._next_sync:
            return
        self._next_sync = now + .4
        desired = pos - start
        # Seek correctivo solo para desvíos audibles; hacer setPosition cada
        # 35 ms generaría chasquidos y bloqueo en FFmpeg/Windows.
        if abs(self.player.position() - desired) > 450:
            self.player.setPosition(max(0, desired))

    def shutdown(self):
        self._closing.set()
        self.pause()
        self.player.stop()
        self.player.setSource(QUrl())
        self._pool.shutdown(wait=False, cancel_futures=True)
        # Los WAV se almacenan sólo en la carpeta temporal de esta sesión.
        # Si un render de FFmpeg seguía activo, no borrar un WAV que Windows
        # mantiene abierto. Los temporales son de sesión y pueden limpiarse
        # desde la carpeta temporal del sistema tras cerrar la aplicación.
        if not self._pending:
            try:
                self._directory.cleanup()
            except OSError:
                pass
