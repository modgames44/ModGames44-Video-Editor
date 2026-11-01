"""Extracción asíncrona de miniaturas y PCM. No bloquea el hilo de Qt."""
from collections import OrderedDict
from pathlib import Path
import subprocess
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QImage
from services.waveform import get_waveform, get_effect_waveform, effect_signature

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

VIDEO = {'.mp4','.mov','.mkv','.avi','.webm','.m4v','.wmv'}
AUDIO = {'.mp3','.wav','.flac','.ogg','.m4a','.aac','.wma'}
PICTURES = {'.png','.jpg','.jpeg','.bmp','.webp'}


def executable():
    if imageio_ffmpeg is None:
        raise RuntimeError('Falta imageio-ffmpeg: pip install imageio-ffmpeg')
    return imageio_ffmpeg.get_ffmpeg_exe()


def frame(path, seconds=0.0, width=160, height=90):
    suffix = Path(path).suffix.lower()
    if suffix not in VIDEO | PICTURES:
        return QImage()
    # Para archivos estáticos no buscamos tiempos >0.
    args = [executable(), '-hide_banner', '-nostdin', '-loglevel', 'error']
    if suffix in VIDEO:
        args += ['-ss', str(max(0, seconds))]
    args += ['-i', str(path), '-frames:v', '1', '-vf',
             f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
             '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1']
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=40, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    img = QImage()
    if result.returncode == 0:
        img.loadFromData(result.stdout)
    return img


class VisualSignals(QObject):
    thumbnail_ready = Signal(str, object)
    wave_ready = Signal(str, object, str)
    frame_ready = Signal(str, int, object)
    effect_wave_ready = Signal(object, object, str)


class ThumbnailTask(QRunnable):
    def __init__(self, path, signals):
        super().__init__(); self.path = path; self.signals = signals
    def run(self):
        img = QImage()
        try: img = frame(self.path)
        except (OSError, RuntimeError, subprocess.TimeoutExpired): pass
        self.signals.thumbnail_ready.emit(self.path, img)


class WaveTask(QRunnable):
    def __init__(self, path, signals):
        super().__init__(); self.path=path; self.signals=signals
    def run(self):
        wave = None; message = ''
        try: wave = get_waveform(self.path, executable())
        except (OSError, RuntimeError, ValueError, TimeoutError) as e: message = str(e)
        self.signals.wave_ready.emit(self.path, wave, message)


class EffectWaveTask(QRunnable):
    def __init__(self, path, settings, key, signals):
        super().__init__()
        self.path = path
        self.settings = settings.copy()
        self.key = key
        self.signals = signals

    def run(self):
        wave = None
        message = ''
        try:
            wave = get_effect_waveform(self.path, executable(), self.settings)
        except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
            message = str(exc)
        self.signals.effect_wave_ready.emit(self.key, wave, message)


class FrameTask(QRunnable):
    def __init__(self, path, ms, signals):
        super().__init__(); self.path=path; self.ms=ms; self.signals=signals
    def run(self):
        img = QImage()
        try: img = frame(self.path, self.ms/1000)
        except (OSError, RuntimeError, subprocess.TimeoutExpired): pass
        self.signals.frame_ready.emit(self.path, self.ms, img)


class VisualCache(QObject):
    updated=Signal(str)
    error=Signal(str,str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals=VisualSignals(self)
        self.signals.thumbnail_ready.connect(self._thumbnail_ready)
        self.signals.wave_ready.connect(self._wave_ready)
        self.signals.frame_ready.connect(self._frame_ready)
        self.signals.effect_wave_ready.connect(self._effect_wave_ready)
        self.frames=OrderedDict()
        self.images={}
        self.waves={}
        self.wave_errors={}
        self.effect_waves={}
        self.effect_pending=set()
        self.effect_errors=set()
        self.thumb_pending=set();self.wave_pending=set();self.frame_pending=set()
        self.frame_pool=QThreadPool(self);self.frame_pool.setMaxThreadCount(2)
        self.wave_pool=QThreadPool(self);self.wave_pool.setMaxThreadCount(1)

    def request(self,path, need_wave=False):
        if path not in self.images and path not in self.thumb_pending:
            self.thumb_pending.add(path);self.frame_pool.start(ThumbnailTask(path,self.signals))
        if need_wave and path not in self.waves and path not in self.wave_pending and path not in self.wave_errors:
            self.wave_pending.add(path);self.wave_pool.start(WaveTask(path,self.signals))

    def request_effect_wave(self, path, settings):
        """Devuelve onda ya procesada o inicia análisis asíncrono."""
        key = (str(path), effect_signature(settings))
        if key in self.effect_waves:
            return self.effect_waves[key]
        if key not in self.effect_pending and key not in self.effect_errors:
            self.effect_pending.add(key)
            self.wave_pool.start(EffectWaveTask(path, settings, key, self.signals))
        return None

    def _effect_wave_ready(self, key, wave, message):
        self.effect_pending.discard(key)
        if wave is not None:
            self.effect_waves[key] = wave
            if len(self.effect_waves) > 16:
                self.effect_waves.pop(next(iter(self.effect_waves)))
        else:
            self.effect_errors.add(key)
            self.error.emit(key[0], message)
        self.updated.emit(key[0])

    def _thumbnail_ready(self,path,img):
        self.thumb_pending.discard(path)
        self.images[path]=img
        self.updated.emit(path)

    def _wave_ready(self,path,wave,message):
        self.wave_pending.discard(path)
        if wave is not None:self.waves[path]=wave
        else:
            self.wave_errors[path]=message
            self.error.emit(path,message)
        self.updated.emit(path)

    @staticmethod
    def frame_key(path,ms):
        # Buckets de 250 ms limitan nuevas decodificaciones al hacer pequeños zoom.
        return (str(path),max(0,int(ms)//250*250))

    def request_frame(self,path,ms):
        key=self.frame_key(path,ms)
        if key in self.frames:
            self.frames.move_to_end(key)
            return
        if key in self.frame_pending or len(self.frame_pending)>=6:return
        self.frame_pending.add(key)
        self.frame_pool.start(FrameTask(key[0],key[1],self.signals))

    def _frame_ready(self,path,ms,img):
        key=(path,ms)
        self.frame_pending.discard(key)
        self.frames[key]=img
        self.frames.move_to_end(key)
        while len(self.frames)>256:self.frames.popitem(last=False)
        self.updated.emit(path)
