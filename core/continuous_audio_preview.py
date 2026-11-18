"""Reproducción de audio filtrado mediante un solo QAudioSink y pipe FFmpeg.

El hilo lector sólo transporta bytes hacia una cola limitada. Qt permanece
exclusivamente en el hilo principal. Cada Seek cancela el proceso anterior.
"""
import copy
import queue
import subprocess
import threading
import time
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
from services.continuous_audio import build_stream_command, pcm_stereo_peaks
from services.preview_audio import audio_signature
from exporter.hardware import ffmpeg_candidates

class AudioPreview(QObject):
    status = Signal(str)
    error = Signal(str)
    levels = Signal(float,float)
    CHUNK = 16384 # 85 ms a 48 kHz estéreo

    def __init__(self, parent=None):
        super().__init__(parent)
        fmt=QAudioFormat()
        fmt.setSampleRate(48000)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.output=QAudioSink(QMediaDevices.defaultAudioOutput(),fmt,self)
        self.output.setBufferSize(48000*4//3)
        self.output.setVolume(.75)
        self.timer=QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._feed)
        self._chunks=queue.Queue(maxsize=18)
        self._generation=0
        self._process=None
        self._thread=None
        self._stop=threading.Event()
        self._device=None
        self._pending=b''
        self._want=None
        self._signature=''
        self._clips=[]
        self._total=0
        self._ffmpeg=None
        self._started=False
        self._waiting=False
        self._playing=False
        self._finished=False
        self._stalled_since=0

    @property
    def is_waiting(self):return self._waiting
    @property
    def has_audio(self):return any(c.get('kind')=='audio' for c in self._clips)

    def configure(self,clips,total_ms):
        signature=audio_signature(clips)
        self._clips=copy.deepcopy(clips)
        self._total=int(total_ms)
        if self._signature!=signature:
            self._signature=signature
            self.pause()
            self.status.emit('Efectos de audio actualizados')

    def _resolve_ffmpeg(self):
        if self._ffmpeg:return self._ffmpeg
        from pathlib import Path
        for exe in ffmpeg_candidates():
            if Path(exe).is_file() or exe=='ffmpeg':
                self._ffmpeg=str(exe)
                return self._ffmpeg
        raise FileNotFoundError('FFmpeg no está disponible')

    def _consume(self, process, generation, stop):
        try:
            while not stop.is_set():
                data=process.stdout.read(self.CHUNK)
                if not data:break
                while not stop.is_set():
                    try:
                        self._chunks.put((generation,data),timeout=.1)
                        break
                    except queue.Full:continue
            if not stop.is_set():
                process.wait(timeout=2)
                if process.returncode not in (0,None):
                    try:
                        message=process.stderr.read().decode('utf8',errors='replace')[-900:]
                    except (OSError,ValueError):message=''
                    self.error.emit('FFmpeg no pudo procesar el audio: '+message)
                self._chunks.put((generation,None),timeout=1)
        except (OSError,ValueError,queue.Full,subprocess.TimeoutExpired):
            pass
        finally:
            try:process.stdout.close()
            except (OSError,ValueError):pass
            try:process.stderr.close()
            except (OSError,ValueError):pass

    def play(self,position,clips,total_ms,start_video):
        self.configure(clips,total_ms)
        self.pause()
        self._generation+=1
        generation=self._generation
        if not self.has_audio:
            self._playing=True
            self.status.emit('Vista previa: video sin audio de Timeline')
            start_video()
            return
        try:
            command=build_stream_command(self._clips,position,self._total,self._resolve_ffmpeg())
            self._stop=threading.Event()
            self._chunks=queue.Queue(maxsize=18)
            self._process=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                   bufsize=0,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self._thread=threading.Thread(target=self._consume,
                 args=(self._process,generation,self._stop),daemon=True)
            self._thread.start()
        except (OSError,ValueError,RuntimeError) as exc:
            self.error.emit('No se pudo preparar la reproducción continua: '+str(exc))
            return
        self._want=start_video
        self._pending=b''
        self._started=False
        self._finished=False
        self._waiting=True
        self._stalled_since=time.monotonic()
        self.status.emit('Preparando audio continuo con efectos…')
        self.timer.start()

    def _feed(self):
        if not self._started:
            # ~250 ms antes de arrancar para suavizar el inicio de FFmpeg.
            if (self._chunks.qsize()<3 and time.monotonic()-self._stalled_since<.8
                    and self._process and self._process.poll() is None):
                return
            if self._chunks.empty():
                if time.monotonic()-self._stalled_since>12:
                    self.error.emit('La preparación de audio superó 12 segundos; revisa los filtros y el archivo.')
                    self.pause()
                    return
                if self._process and self._process.poll() is not None:
                    self.error.emit('FFmpeg terminó sin producir muestras PCM')
                    self.pause()
                return
            self._device=self.output.start()
            if self._device is None:
                self.error.emit('El dispositivo de sonido no pudo iniciar')
                self.pause()
                return
            self._started=True
            self._waiting=False
            self._playing=True
            callback,self._want=self._want,None
            if callback:callback()
            self.status.emit('Vista previa: audio y video con efectos (continuo)')
        if self._device is None:return
        budget=min(65536,max(0,int(self.output.bytesFree())))
        while budget>0:
            if not self._pending:
                try:generation,data=self._chunks.get_nowait()
                except queue.Empty:break
                if generation!=self._generation:continue
                if data is None:
                    self._finished=True
                    break
                self._pending=data
            count=min(len(self._pending),budget)
            piece=self._pending[:count]
            try:sent=self._device.write(piece)
            except (OSError,RuntimeError):sent=-1
            if sent is None or sent<=0:break
            self._pending=self._pending[sent:]
            budget-=sent
            self.levels.emit(*pcm_stereo_peaks(piece[:sent]))
        if self._finished and not self._pending and self._chunks.empty():
            # La secuencia de vídeo se detendrá por su reloj.
            self.timer.stop()

    def pause(self):
        self.timer.stop()
        self._generation+=1
        self._stop.set()
        process,self._process=self._process,None
        if process:
            try:process.kill()
            except OSError:pass
            try:process.stdout.close()
            except (OSError,ValueError):pass
            try:process.stderr.close()
            except (OSError,ValueError):pass
        self.output.stop()
        self._device=None
        self._want=None
        self._pending=b''
        self._waiting=False
        self._playing=False
        self._started=False
        self._finished=False
        self.levels.emit(0,0)

    def follow(self,timeline_ms,running,resume_video=None,pause_video=None):
        # Ningún corte de ventana: FFmpeg envía el flujo hasta el final.
        if not running and self._playing:
            self.pause()

    def shutdown(self):
        self.pause()
